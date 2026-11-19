"""Shared monitor, download, capture, review and export orchestration."""
import json
import queue
import shutil
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from dataclasses import replace
from uuid import uuid4
from urllib.parse import urlsplit

from decision_bank import record_final
from engine import capture, fetch_vod, process, probe
from posting_queue import enqueue
from replay_library import claim, finish, list_replays
from live_scout import LiveScout, ScoutSettings
from runtime_profile import configure, lower_worker_priority


def run_session(sources, options, minutes, workers, output, wait_minutes, stop, write_log,
                scout=ScoutSettings(False)):
    batch = output / (datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:6])
    errors = queue.SimpleQueue()
    log_lock = threading.Lock()
    log_failed = False

    def log(message):
        nonlocal log_failed
        with log_lock:
            write_log(message)
            if not log_failed:
                try:
                    with (batch / "sessao.log").open("a", encoding="utf-8") as handle:
                        handle.write(f"{datetime.now():%H:%M:%S} {message}\n")
                except OSError as error:
                    log_failed = True
                    write_log(f"Não foi possível gravar sessao.log: {error}")

    def safely(task, *args):
        try:
            task(*args)
        except Exception as error:
            errors.put(str(error))
            log(f"Erro: {error}")

    try:
        batch.mkdir(parents=True)
        log(f"Sessão: {batch}")
        profile = configure(scout.performance)
        workers = min(workers, profile.max_renders)
        available = shutil.disk_usage(output).free / 1024**3
        log(f"Modo {profile.label} · até {workers} render(es) simultâneo(s) · {available:.1f} GiB livres.")
        live_count = sum(kind == "live" for _, kind, _ in sources)
        if profile.low_priority and live_count > 2 and not scout.replay_only:
            log("Modo Leve com mais de dois canais: a triagem pode acumular atraso.")
        with (ThreadPoolExecutor(max_workers=workers) as analysis,
              ThreadPoolExecutor(max_workers=8) as lives, ThreadPoolExecutor(max_workers=2) as downloads,
              ThreadPoolExecutor(max_workers=8) as archives):
            capacity = threading.BoundedSemaphore(max(3, workers * 3))
            archive_slots = threading.BoundedSemaphore(1)

            def render_job(path, folder, settings, release_source, screening, live_review=False):
                lower_worker_priority()
                log(f"Edição iniciada: {path.name}.")

                def review(candidate, media, verdict, words, hook):
                    enqueue(output, candidate, media, verdict, " ".join(word for _, _, word in words),
                            hook, screening[0])

                report = process(path, folder, settings, log, screening=screening,
                                 staging_dir=path.parent if live_review else None, on_review=review if screening else None)
                if live_review and report:
                    variants = [(style, variant["screening"]) for clip in report["clips"]
                                for style, variant in clip["variants"].items() if "screening" in variant]
                    record_final(path.parent / "triagem.sqlite3", path.stem, variants)
                if release_source and report and (screening is not None or any(folder.glob("clip_*.mp4"))):
                    path.unlink()
                    path.with_suffix(".json").unlink(missing_ok=True)
                    (folder / "midia-revisao.mp4").unlink(missing_ok=True)

            def schedule(path, folder, settings, bounded=False, managed=False, screening=None, live_review=False):
                release_source = managed and settings.render and scout.clean
                if bounded and not capacity.acquire(blocking=False):
                    if release_source:
                        path.unlink()
                        path.with_suffix(".json").unlink(missing_ok=True)
                        log("Fila de render cheia. Candidato descartado; decisão disponível na triagem.")
                    else:
                        log(f"Fila de render cheia. Candidato guardado em {path.parent}.")
                    return False
                log(f"{'Fila de edição' if settings.render else 'Fila de análise'}: {path.name}.")
                job = analysis.submit(safely, render_job, path, folder,
                                      replace(settings, save_review=False) if release_source else settings,
                                      release_source, screening, live_review)
                if bounded:
                    job.add_done_callback(lambda _: capacity.release())
                return folder

            def vod(url, folder, result, settings):
                log(f"Baixando VOD: {url}")
                try:
                    path = fetch_vod(sys.executable, url, folder, max_bytes=scout.replay_gib * 1024**3, stop=stop)
                except (OSError, RuntimeError, ValueError):
                    if scout.clean:
                        for file in folder.glob("vod*"):
                            if file.is_file():
                                file.unlink(missing_ok=True)
                    if stop.is_set():
                        return False
                    raise
                log(f"Download concluído: {path.name}.")
                release = settings.render and scout.clean
                screening = (scout.model, scout.threshold, {}) if scout.review_final and settings.render else None
                finished = analysis.submit(render_job, path, result,
                                           replace(settings, save_review=False) if release else settings,
                                           release, screening)
                finished.result()
                return True

            def import_replays(source, folder, target, settings):
                db = output / "replays.sqlite3"
                while not stop.is_set():
                    next_check = time.monotonic() + scout.replay_period * 3600
                    try:
                        replays = list_replays(sys.executable, source, scout.replay_count)
                        log(f"Replays encerrados encontrados: {len(replays)} em {source}.")
                        for replay in replays:
                            if stop.is_set():
                                break
                            if not claim(db, replay):
                                log(f"Replay {replay.id} já processado ou em andamento.")
                                continue
                            ok = False
                            try:
                                replay_dir = folder / replay.id
                                replay_dir.mkdir(parents=True, exist_ok=True)
                                with archive_slots:
                                    if not stop.is_set():
                                        ok = vod(replay.url, replay_dir, target / replay.id, settings)
                            except Exception as error:
                                log(f"Replay {replay.id}: {error}")
                                if not scout.replay_period:
                                    errors.put(str(error))
                            finally:
                                finish(db, replay, ok and settings.render)
                    except Exception as error:
                        log(f"Busca de replays falhou: {error}")
                        if not scout.replay_period:
                            errors.put(str(error))
                    if not scout.replay_period:
                        return
                    stop.wait(max(0, next_check - time.monotonic()))

            def schedule_live(path, block, selected=None, *, capture_dir, result, settings):
                screening = None
                if selected:
                    end = min(selected[1], probe(path)[0])
                    settings = replace(settings, manual=((min(selected[0], max(0., end - 1)), end),))
                    if scout.review_final and settings.render:
                        prior = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
                        screening = (scout.model, scout.threshold, prior)
                        settings = replace(settings, save_review=False)
                return schedule(path, result / block.relative_to(capture_dir), settings,
                                bounded=scout.enabled, managed=scout.enabled, screening=screening, live_review=screening is not None)

            def monitor(url, folder, callback):
                if not scout.enabled:
                    capture(sys.executable, url, folder, minutes, callback, stop, log, wait_minutes,
                            continuous=scout.continuous, catchup=scout.catchup,
                            offline_seconds=scout.live_poll_hours * 3600 or 45)
                    return
                detector = LiveScout(folder, url, scout, callback, log)
                try:
                    capture(sys.executable, url, folder, minutes, detector.receive, stop,
                            log, wait_minutes, segment_seconds=15,
                            continuous=scout.continuous, catchup=scout.catchup,
                            offline_seconds=scout.live_poll_hours * 3600 or 45)
                finally:
                    detector.close()

            futures = []
            from functools import partial
            for i, (source, kind, regions) in enumerate(sources, 1):
                host = urlsplit(source).hostname or ""
                channel = urlsplit(source).path.strip("/") if kind != "file" else ""
                identity = re.sub(r"[^A-Za-z0-9_-]+", "_", f"{host}_{channel}").strip("_")[:78]
                source_name = f"{i:02}_{identity or kind}"
                result = batch / "Clipes prontos" / source_name
                overrides = dict(zip(("face", "game"), regions))
                if len(regions) == 3:
                    overrides["close_focus"] = float(regions[2])
                settings = replace(options, **overrides)
                if kind == "file":
                    screening = (scout.model, scout.threshold, {}) if scout.review_final and settings.render else None
                    schedule(Path(source), result, settings, screening=screening)
                else:
                    folder = batch / "Capturas" / source_name
                    folder.mkdir(parents=True)
                    if kind == "vod":
                        futures.append(downloads.submit(safely, vod, source, folder, result, settings))
                    else:
                        if scout.replay_count:
                            futures.append(archives.submit(safely, import_replays, source, folder / "Replays",
                                                           result / "Replays", settings))
                        if scout.replay_only:
                            continue
                        callback = partial(schedule_live, capture_dir=folder, result=result,
                                           settings=replace(settings, count=1, montage=False) if scout.enabled else settings)
                        futures.append(lives.submit(safely, monitor, source, folder, callback))
            for future in futures:
                future.result()
        clips = sum(1 for _ in (batch / "Clipes prontos").rglob("clip_*.mp4"))
        if errors.empty():
            if options.render:
                log(f"Sessão concluída: {clips} MP4(s).")
                if not clips:
                    log("Nenhum clipe foi exportado. Confira captura, nota mínima e decisões acima.")
            else:
                log("Sessão concluída no modo de plano de cortes.")
        else:
            log(f"Sessão encerrada com erros e {clips} MP4(s). Consulte sessao.log.")
    except Exception as error:
        write_log(f"Sessão interrompida: {error}")
        return 1
    return 0 if errors.empty() else 1
