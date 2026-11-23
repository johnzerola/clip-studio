"""Shared monitor, download, capture, review and export orchestration."""
import json
import queue
import shutil
import re
import sys
import threading
import time
from tempfile import TemporaryDirectory
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from dataclasses import replace
from uuid import uuid4
from urllib.parse import urlsplit

from decision_bank import record_final
from engine import capture, process, probe
from posting_queue import enqueue
from replay_library import Replay, archive_url, claim, finish, list_replays
from live_scout import LiveScout, ScoutSettings
from live_render_queue import LiveRenderQueue
from runtime_profile import configure, lower_worker_priority


def run_session(sources, options, minutes, workers, output, wait_minutes, stop, write_log,
                scout=ScoutSettings(False), *, on_batch=None, activity=None):
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
        if on_batch:
            on_batch(batch)
        log(f"Sessão: {batch}")
        profile = configure(scout.performance, scout.acceleration)
        workers = min(workers, profile.max_renders)
        if scout.auto_finalize:
            from ai_setup import MODELS, installed_models, official_executable, start_model_service
            models = installed_models()
            if models is None and official_executable():
                log("Ativando o Ollama para a revisão automática.")
                try:
                    start_model_service()
                except (RuntimeError, OSError) as error:
                    log(f"Ollama indisponível no início: {error}")
                models = installed_models()
            names = (scout.vision_model, *MODELS)
            model = next((name for name in names if name and name in (models or ())), "")
            if model:
                log(f"Revisão automática com {model} · até uma correção por corte antes de salvar.")
            else:
                log("IA local indisponível. Captura, edição e nota continuam com as regras do V9.")
            scout = replace(scout, model=scout.model if scout.model in (models or ()) else model, vision_model=model)
            options = replace(options, effects_model=options.effects_model if options.effects_model in (models or ()) else model)
        elif not scout.model and not scout.vision_model:
            log("Montagem e avaliação com as regras locais do V9.")
        from workspace_data import editorial_weights, register_exports
        weights = editorial_weights(output)
        from viral_knowledge import load_history
        load_history(output)
        available = shutil.disk_usage(output).free / 1024**3
        log(f"Modo {profile.label} · até {workers} render(es) simultâneo(s) · {available:.1f} GiB livres.")
        if profile.low_priority:
            log("Modo Leve: transcrição na CPU, uma operação de análise ou edição por vez.")
        live_count = sum(kind == "live" for _, kind, _ in sources)
        if profile.low_priority and live_count > 2 and not scout.replay_only:
            log("Modo Leve com mais de dois canais: a triagem pode acumular atraso.")
        with (ThreadPoolExecutor(max_workers=1) as sending, ThreadPoolExecutor(max_workers=workers) as analysis,
              ThreadPoolExecutor(max_workers=8) as lives, ThreadPoolExecutor(max_workers=2) as downloads,
              ThreadPoolExecutor(max_workers=8) as archives):
            live_queue = LiveRenderQueue(analysis, workers)
            archive_slots = threading.BoundedSemaphore(1)
            upload_slots = threading.BoundedSemaphore(2)
            manual_review_slots = threading.BoundedSemaphore(3)

            def reserve_manual_review():
                return manual_review_slots.acquire(blocking=False)

            def send_approved(clip_id):
                from studio_services import auto_publish
                try:
                    if stop.is_set():
                        return
                    message = auto_publish(output, clip_id, scout.autopilot)
                    if message:
                        log(message)
                except (OSError, ValueError, RuntimeError) as error:
                    log(f"Piloto automático: {error}")
            states, edits = {}, {}
            activity_lock = threading.Lock()

            def activity_update(source, state=None, change=0):
                if not activity or not source:
                    return
                with activity_lock:
                    if state is not None:
                        states[source] = state
                    edits[source] = edits.get(source, 0) + change
                    suffix = f" · editando {edits[source]}" if edits[source] else ""
                    activity(source, states.get(source, "Preparando") + suffix)

            def render_job(path, folder, settings, screening, live_review=False, recording=False):
                lower_worker_priority()
                log(f"Edição iniciada: {path.name}.")
                if screening and scout.auto_finalize:
                    model, threshold, prior = screening
                    screening = (model, threshold, dict(prior, auto_finalize=True, stop=stop.is_set,
                                                        protect_edges=settings.keep_manual_edges,
                                                        reserve_manual_review=reserve_manual_review if live_review else lambda: True))
                if screening and not (scout.model or scout.vision_model):
                    model, threshold, prior = screening
                    screening = (model, threshold, dict(prior, allow_gemini=False))

                def review(candidate, media, verdict, words, hook):
                    clip_id = enqueue(output, candidate, media, verdict,
                                      verdict.get("studio_transcript", " ".join(word for _, _, word in words)),
                                      hook, screening[0])
                    if media and scout.autopilot and verdict.get("recommendation") == "recommended" and not stop.is_set():
                        if upload_slots.acquire(blocking=False):
                            pending = sending.submit(send_approved, clip_id)
                            pending.add_done_callback(lambda _: upload_slots.release())
                        else:
                            log("Piloto automático: fila ocupada. Clipe mantido para agendamento manual.")

                report = process(path, folder, settings, log, screening=screening,
                                 staging_dir=path.parent if live_review else None, on_review=review if screening else None,
                                 recording=(scout.model, stop.is_set, weights)
                                 if recording and scout.transcribe_recordings else None,
                                 on_export=lambda media: register_exports(output, (media,)))
                if live_review and report:
                    variants = [(style, variant["screening"]) for clip in report["clips"]
                                for style, variant in clip["variants"].items() if "screening" in variant]
                    record_final(path.parent / "triagem.sqlite3", path.stem, variants)
            def schedule(path, folder, settings, bounded=False, managed=False, screening=None, live_review=False,
                         recording=False, live_url=None, priority=0):
                release_source = managed and settings.render and scout.clean

                def cleanup():
                    if release_source:
                        for temporary in (path, path.with_suffix(".json"), folder / "midia-revisao.mp4"):
                            try:
                                temporary.unlink(missing_ok=True)
                            except OSError as error:
                                log(f"Limpeza de {temporary.name}: {error}")

                def discard(reason):
                    cleanup()
                    message = {"prioridade_da_fila": "candidatos mais fortes na fila",
                               "limite_temporarios": "limite de arquivos temporários",
                               "espaco_insuficiente": "espaço em disco insuficiente",
                               "sessao_cancelada": "sessão cancelada"}[reason]
                    log(f"Candidato sem exportação: {path.name} · {message}.")
                    if live_review:
                        safely(record_final, path.parent / "triagem.sqlite3", path.stem,
                               [("fila", {"score": priority, "status": "skipped", "reason": reason})])

                def run_render():
                    if bounded and stop.is_set():
                        discard("sessao_cancelada")
                        return
                    activity_update(live_url, change=1)
                    try:
                        safely(render_job, path, folder, replace(settings, save_review=False) if release_source else settings,
                               screening, live_review, recording)
                    finally:
                        cleanup()
                        activity_update(live_url, change=-1)

                if bounded:
                    from engine import CAPTURE_RESERVE
                    if shutil.disk_usage(output).free < CAPTURE_RESERVE + 128 * 1024**2:
                        discard("espaco_insuficiente")
                        return False
                    if not live_queue.offer(priority, path.stat().st_size, lambda: safely(run_render), discard):
                        return False
                else:
                    analysis.submit(run_render)
                log(f"{'Fila de edição' if settings.render else 'Fila de análise'}: {path.name}.")
                return folder

            def vod(url, folder, result, settings):
                from recording_analysis import select
                from replay_media import download, gameplay_candidates, replay_duration
                from vendor.openshorts.twitch_signals import fetch_viewer_clips, parse_vod_id

                folder.mkdir(parents=True, exist_ok=True)
                result.mkdir(parents=True, exist_ok=True)
                try:
                    with TemporaryDirectory(prefix="replay-audio-", dir=folder) as audio_stage:
                        log(f"Baixando apenas a faixa de áudio da gravação: {url}")
                        vod_id = parse_vod_id(url)
                        viewer_clips = fetch_viewer_clips(vod_id, timeout=4)[:20] if vod_id else ()
                        if viewer_clips:
                            log(f"Twitch · {len(viewer_clips)} clipes de espectadores usados como sinais de triagem.")
                        try:
                            audio, duration = download(url, Path(audio_stage), "audio", stop,
                                                       limit=scout.replay_gib * 1024**3)
                        except RuntimeError:
                            audio, duration = None, replay_duration(url)
                        if audio:
                            try:
                                periods, _, picks = analysis.submit(select, audio, result, duration, None,
                                                                    settings, scout.model, stop.is_set, weights, log,
                                                                    viewer_clips).result()
                            except (OSError, RuntimeError) as error:
                                log(f"Transcrição do replay indisponível ({type(error).__name__}). Buscando por ação.")
                                periods, picks = [], []
                        else:
                            periods, picks = [], []
                        if not picks:
                            log("Replay sem candidato pela fala. Buscando ação em até três amostras leves.")
                            picks = analysis.submit(gameplay_candidates, url, folder, stop,
                                                    duration, settings, log).result()
                            periods = [[(pick["start"], pick["end"])] for pick in picks]
                    (result / "selecao-replay.json").write_text(
                        json.dumps({"source": url, "duration": duration, "candidates": picks},
                                   ensure_ascii=False, indent=2), encoding="utf-8")
                    if not settings.render:
                        return True
                    for index, (period, pick) in enumerate(zip(periods, picks), 1):
                        if stop.is_set():
                            return False
                        low, high = period[0]
                        minimum = max(15, scout.threshold - 16)
                        if pick["av_score"] < minimum:
                            log(f"Trecho {index}: {pick['av_score']}/100 ficou abaixo da triagem de replay ({minimum}).")
                            continue
                        padding = min(5., max(0., (180. - (high - low)) / 2)) if scout.auto_finalize else 0.
                        download_low, download_high = max(0., low - padding), min(duration, high + padding)
                        log(f"Baixando somente {download_low:.1f}–{download_high:.1f} s em até {scout.replay_height}p.")
                        with TemporaryDirectory(prefix="replay-clip-", dir=folder) as clip_stage:
                            path, size = download(url, Path(clip_stage), "video", stop,
                                                  window=(download_low, download_high), limit=1024**3, max_height=scout.replay_height)
                            log(f"Trecho {index} recebido em {size[0]} × {size[1]}.")
                            local_end = min(high - download_low, probe(path)[0])
                            clip_options = replace(settings, count=1, manual=((low - download_low, local_end),),
                                                   precompress=settings.precompress and not profile.low_priority,
                                                   full_hd=max(size) >= 1920, save_review=False, trim_inactive=True)
                            prior = {"vision_model": scout.vision_model, "origin_url": url,
                                     "origin_offset": download_low, "speech_language": settings.speech_language,
                                     "raw_score": pick["av_score"], "signals": pick.get("features") or {}}
                            screening = (scout.model, scout.threshold, prior) if scout.review_final else None
                            analysis.submit(render_job, path, result / f"Trecho-{index:02d}", clip_options,
                                            screening).result()
                    return True
                except InterruptedError:
                    if stop.is_set():
                        return False
                    raise

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

            def schedule_live(path, block, selected=None, *, capture_dir, result, settings, live_url):
                screening = None
                priority = 0
                settings = replace(settings, live_edit=True)
                if profile.low_priority:
                    settings = replace(settings, precompress=False)
                if selected:
                    end = min(selected[1], probe(path, timeout=15)[0])
                    settings = replace(settings, manual=((min(selected[0], max(0., end - 1)), end),),
                                       trim_inactive=scout.trim_inactive)
                    prior = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
                    priority = int(prior["score"])
                    if scout.review_final and settings.render:
                        screening = (scout.model, scout.threshold, dict(prior, vision_model=scout.vision_model))
                        settings = replace(settings, save_review=False)
                elif scout.review_final and settings.render:
                    screening = (scout.model, scout.threshold, {"vision_model": scout.vision_model})
                return schedule(path, result / block.relative_to(capture_dir), settings,
                                bounded=scout.enabled, managed=scout.enabled, screening=screening, live_review=screening is not None,
                                live_url=live_url, priority=priority)

            def monitor(url, folder, callback, replay_result, options):
                def state(value):
                    activity_update(url, state=value)
                on_ended = None
                if scout.replay_after_live and not scout.replay_count:
                    direct = re.fullmatch(r"/live/([\w-]{11})", urlsplit(url).path, re.ASCII)
                    if direct and urlsplit(url).hostname == "www.youtube.com":
                        replay = Replay("youtube", direct[1], f"https://www.youtube.com/watch?v={direct[1]}")
                        on_ended = lambda: downloads.submit(safely, process_new_replay, url, folder, replay_result, options, replay, set())
                    else:
                        try:
                            archive_url(url)
                            seen = {item.id for item in list_replays(sys.executable, url, 3)}
                        except (RuntimeError, OSError, ValueError):
                            seen = None
                        if seen is not None:
                            on_ended = lambda: downloads.submit(safely, process_new_replay, url, folder, replay_result, options, None, seen)
                try:
                    monitor_source(url, folder, callback, state, on_ended)
                finally:
                    state("Captura encerrada")

            def process_new_replay(url, folder, result, settings, direct, seen):
                database = output / "replays.sqlite3"
                for attempt in range(6):
                    if attempt and stop.wait(25):
                        return
                    if stop.is_set():
                        return
                    try:
                        new = [direct] if direct else [item for item in list_replays(sys.executable, url, 3)
                                                       if item.id not in seen]
                        if not new:
                            continue
                        replay = new[0]
                        if not claim(database, replay):
                            return
                        ok = False
                        try:
                            with archive_slots:
                                ok = vod(replay.url, folder / "Replays" / replay.id,
                                         result / "Replays" / replay.id, replace(settings, count=max(3, settings.count)))
                        finally:
                            finish(database, replay, ok and settings.render)
                        if ok:
                            seen.add(replay.id)
                            return
                    except (OSError, RuntimeError, ValueError) as error:
                        if attempt == 5 and not stop.is_set():
                            log(f"Replay recente indisponível: {error}")
                if not stop.is_set():
                    log("Replay recente não disponível nesta janela de busca. Você pode adicionar a URL do VOD.")

            def monitor_source(url, folder, callback, state, on_ended):
                if not scout.enabled:
                    capture(sys.executable, url, folder, minutes, callback, stop, log, wait_minutes,
                            continuous=scout.continuous, catchup=scout.catchup,
                            offline_seconds=scout.live_poll_hours * 3600 or 45, on_state=state,
                            capture_height=scout.capture_height, on_ended=on_ended)
                    return
                detector = LiveScout(folder, url, scout, callback, log, editorial_weights=weights)
                try:
                    capture(sys.executable, url, folder, minutes, detector.receive, stop,
                            log, wait_minutes, segment_seconds=15,
                            continuous=scout.continuous, catchup=scout.catchup,
                            offline_seconds=scout.live_poll_hours * 3600 or 45, on_state=state,
                            capture_height=scout.capture_height, discard_short=scout.clean,
                            on_ended=on_ended)
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
                    screening = (scout.model, scout.threshold, {"vision_model": scout.vision_model}) if scout.review_final and settings.render else None
                    schedule(Path(source), result, settings, screening=screening, recording=True)
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
                        callback = partial(schedule_live, capture_dir=folder, result=result, live_url=source,
                                           settings=replace(settings, count=1, montage=False) if scout.enabled else settings)
                        futures.append(lives.submit(safely, monitor, source, folder, callback, result, settings))
            for future in futures:
                future.result()
            live_queue.wait()
        clips = sum(1 for _ in (batch / "Clipes prontos").rglob("clip_*.mp4"))
        if errors.empty():
            if options.review_visuals:
                previews = sum(1 for _ in (batch / "Clipes prontos").rglob("preview-*.mp4"))
                log(f"Sessão concluída: {previews} prévia(s) aguardando revisão.")
            elif options.render:
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
