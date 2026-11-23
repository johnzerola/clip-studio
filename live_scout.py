"""Bounded rolling live analysis. It never makes the recorder wait for inference."""
import collections
import hashlib
import json
import math
import os
import queue
import random
import re
import shutil
import socket
import ssl
import statistics
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from engine import FF, command, inspect, probe, transcribe
from decision_bank import record
from viral_rank import candidates, has_chat_reaction, judge_local, rank_chat
import runtime_profile as runtime

INFERENCE = {False: threading.BoundedSemaphore(2), True: threading.BoundedSemaphore(1)}


@dataclass(frozen=True)
class ScoutSettings:
    enabled: bool = True
    model: str = "qwen3:4b"
    threshold: int = 60
    clean: bool = True
    clip_seconds: int = 45
    review_final: bool = False
    continuous: bool = False
    catchup: bool = False
    replay_count: int = 0
    replay_period: int = 0
    replay_only: bool = False
    replay_gib: int = 12
    live_poll_hours: int = 0
    performance: str = "equilibrado"
    trim_inactive: bool = True
    vision_model: str = ""
    transcribe_recordings: bool = False
    autopilot: object = field(default=None, repr=False)
    speech_language: str = "auto"
    capture_height: int | None = None
    replay_after_live: bool = False
    replay_height: int = 1440
    acceleration: str = "auto"
    auto_finalize: bool = False


class TwitchPulse:
    def __init__(self, channel, log):
        self.channel, self.log = channel, log
        self.stop = threading.Event()
        self.messages = collections.deque(maxlen=36000)
        self.salt = os.urandom(16)
        self.lock = threading.Lock()
        self.active = False
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self):
        import truststore

        host = "irc.chat.twitch.tv"
        context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        while not self.stop.is_set():
            try:
                with socket.create_connection((host, 6697), timeout=8) as raw:
                    with context.wrap_socket(raw, server_hostname=host) as connection:
                        connection.settimeout(8)
                        nick = random.randint(10000, 999999)
                        connection.sendall(f"PASS SCHMOOPIIE\r\nNICK justinfan{nick}\r\nJOIN #{self.channel}\r\n".encode("ascii"))
                        pending = b""
                        while not self.stop.is_set():
                            try:
                                chunk = connection.recv(8192)
                            except socket.timeout:
                                continue
                            if not chunk:
                                break
                            lines = (pending + chunk).split(b"\r\n")
                            pending = lines.pop()[-8192:]
                            for line in lines:
                                if line.startswith(b"PING "):
                                    connection.sendall(b"PONG " + line[5:] + b"\r\n")
                                elif b" 366 " in line or b" 353 " in line:
                                    if not self.active:
                                        self.log("Chat Twitch conectado: contando mensagens, sem guardar conteúdo.")
                                    self.active = True
                                elif b" PRIVMSG #" in line:
                                    self.active = True
                                    with self.lock:
                                        sender = line.split(b"!", 1)[0].lstrip(b":")
                                        user = hashlib.blake2b(sender, key=self.salt, digest_size=6).digest()
                                        body = line.partition(b" PRIVMSG #")[2].partition(b" :")[2]
                                        self.messages.append((time.monotonic(), user,
                                                              has_chat_reaction(body.decode("utf-8", errors="replace"))))
                                elif b"Login authentication failed" in line:
                                    self.log("Chat Twitch anônimo recusado; análise segue sem chat.")
                                    return
            except OSError:
                if not self.stop.is_set():
                    self.log("Chat Twitch indisponível neste momento; análise segue sem chat.")
            finally:
                self.active = False
            self.stop.wait(12)

    def measure(self, end, seconds):
        with self.lock:
            current = [(person, reaction) for t, person, reaction in self.messages if end - seconds <= t <= end]
            before = sum(1 for t, _, _ in self.messages if end - seconds - 90 <= t < end - seconds)
        now = len(current)
        ratio = (now / max(seconds, 1)) / max(.08, before / 90)
        participants = {person for person, _ in current}
        reactions = {person for person, reaction in current if reaction}
        return now, round(min(5., ratio), 2), len(participants), len(reactions)


class YouTubePulse(TwitchPulse):
    def run(self):
        from datetime import datetime
        from urllib.parse import urlencode
        from youtube_publish import API, account, exchange, read_json

        try:
            key = os.getenv("CLIP_STUDIO_YOUTUBE_CHAT_KEY", "").strip()
            saved = None if key else account()
            if not key and not saved:
                self.log("Chat do YouTube requer autorização do YouTube ou chave de chat.")
                return
            token = (exchange(saved["client"], grant_type="refresh_token",
                              refresh_token=saved["refresh_token"])["access_token"] if saved else None)

            def api(path, params):
                if key:
                    params["key"] = key
                return read_json(API + path + "?" + urlencode(params), token=token)

            result = api("videos", {"id": self.channel, "part": "liveStreamingDetails"})
            details = result["items"][0]["liveStreamingDetails"]
            if not details.get("activeLiveChatId"):
                self.log("YouTube sem chat ativo para esta live.")
                return
            params = {"liveChatId": details["activeLiveChatId"], "part": "snippet,authorDetails", "maxResults": 200}
            self.active = True
            self.log("Chat YouTube conectado pela API. Somente contagem em memória.")
            while not self.stop.is_set():
                result = api("liveChatMessages", params)
                now, monotonic = time.time(), time.monotonic()
                additions = []
                for item in result.get("items", []):
                    snippet = item.get("snippet", {})
                    who = item.get("authorDetails", {}).get("channelId")
                    if not who or snippet.get("type") != "textMessageEvent":
                        continue
                    at = datetime.fromisoformat(snippet["publishedAt"]).timestamp()
                    if -3 <= now-at <= 120:
                        user = hashlib.blake2b(who.encode(), key=self.salt, digest_size=6).digest()
                        additions.append((min(monotonic, monotonic - (now-at)), user,
                                          has_chat_reaction(snippet.get("displayMessage") or "")))
                with self.lock:
                    self.messages.extend(additions)
                if result.get("offlineAt") or not result.get("nextPageToken"):
                    return
                params["pageToken"] = result["nextPageToken"]
                self.stop.wait(max(5., float(result.get("pollingIntervalMillis", 5000))/1000))
        except (OSError, ValueError, IndexError, KeyError, TypeError, RuntimeError):
            self.log("Chat YouTube indisponível. A triagem segue com áudio, fala e movimento.")
        finally:
            self.active = False


class LiveScout:
    """Closed segments provide bounded context while recording continues."""
    def __init__(self, capture_root, url, settings, schedule, log, *, editorial_weights=None):
        self.root = capture_root.resolve()
        self.settings, self.schedule, self.log = settings, schedule, log
        self.pending = queue.Queue(maxsize=12 if settings.catchup else 5)
        self.entries = collections.deque(maxlen=max(3, math.ceil(settings.clip_seconds / 15) + 1))
        self.last_clip = -math.inf
        self.last_judge = -math.inf
        self.last_segment = None
        self.finished = threading.Event()
        parsed = urlparse(url)
        self.editorial_weights = editorial_weights or {}
        self.chat = TwitchPulse(parsed.path.strip("/"), log) if parsed.hostname == "www.twitch.tv" else None
        youtube_id = re.fullmatch(r"/live/([A-Za-z0-9_-]{11})", parsed.path)
        if parsed.hostname == "www.youtube.com" and youtube_id:
            self.chat = YouTubePulse(youtube_id[1], log)
        if self.chat:
            self.chat.thread.start()
        self.worker = threading.Thread(target=self.run, daemon=True)
        self.worker.start()

    def release(self, path):
        path = path.resolve()
        if (self.settings.clean and path.parent.parent == self.root
                and re.fullmatch(r"conexao_\d+", path.parent.name)
                and re.fullmatch(r"live_\d+\.ts", path.name)):
            try:
                path.unlink(missing_ok=True)
            except OSError as error:
                self.log(f"Não consegui liberar {path.name}: {error}")

    def receive(self, path, _):
        item = (path, time.monotonic())
        try:
            self.pending.put_nowait(item)
        except queue.Full:
            try:
                old, _ = self.pending.get_nowait()
                self.release(old)
                self.log("Triagem atrasada: bloco antigo descartado da fila.")
            except queue.Empty:
                pass
            self.pending.put_nowait(item)

    def close(self):
        self.finished.set()
        if self.chat:
            self.chat.stop.set()
        self.worker.join()
        if self.settings.clean:
            # The recorder has stopped. This also catches a tail without a CSV entry.
            for path in self.root.glob("conexao_*/live_*.ts"):
                self.release(path)

    def run(self):
        runtime.lower_worker_priority()
        while not self.finished.is_set() or not self.pending.empty():
            try:
                path, arrival = self.pending.get(timeout=.3)
            except queue.Empty:
                continue
            try:
                self.analyze(path, arrival)
            except Exception as error:
                self.log(f"Falha na triagem de {path.name}: {error}")
                if not any(item[0] == path for item in self.entries):
                    self.release(path)
        for path, *_ in self.entries:
            self.release(path)

    def analyze(self, path, arrival):
        if self.entries:
            prior = self.entries[-1][0]
            if prior.parent != path.parent or int(path.stem[5:]) != int(prior.stem[5:]) + 1:
                while self.entries:
                    self.release(self.entries.popleft()[0])
        with INFERENCE[runtime.active.low_priority]:
            seconds, audio = probe(path, timeout=15)
            features = inspect(path, seconds, audio, normalized=False, timeout=max(25, seconds * 2),
                               fast_video=runtime.active.low_priority, log=self.log)
            quiet = runtime.active.quiet_pass and features and all(rms < 100 and motion < 2
                                                                  for rms, motion, _ in features)
            try:
                words = (transcribe(path, 0, seconds, model="tiny", language=self.settings.speech_language)
                         if audio and not quiet else [])
            except (OSError, RuntimeError) as error:
                words = []
                self.log(f"Transcrição indisponível ({type(error).__name__}). Triagem por áudio e movimento.")
            if audio and quiet:
                self.log(f"{path.name}: áudio baixo e imagem estável. Triagem preservou o tempo sem transcrever.")
        previous = self.last_segment
        self.last_segment = (path.parent, arrival)
        near_realtime = (not self.settings.catchup or
                         bool(previous and previous[0] == path.parent and arrival - previous[1] >= .65 * seconds))
        if len(self.entries) == self.entries.maxlen:
            self.release(self.entries.popleft()[0])
        self.entries.append((path, seconds, words, features))
        if len(self.entries) < 2:
            self.log("Triagem: primeiro bloco analisado, aguardando o próximo para avaliar o contexto.")
            return
        if arrival - self.last_clip < self.settings.clip_seconds:
            return
        window = list(self.entries)
        duration = 0.
        all_words, signals = [], []
        baseline = [row for _, _, _, bins in window[:-1] for row in bins]
        audio_base = max(100., statistics.median(row[0] for row in baseline)) if baseline else 100.
        motion_base = max(2., statistics.median(row[1] for row in baseline)) if baseline else 2.
        for _, length, spoken, bins in window:
            all_words.extend((duration + a, duration + b, word) for a, b, word in spoken)
            signals.extend((duration + 2 * i, 20 * math.log10(max(1., audio / audio_base)),
                            min(5., motion / motion_base))
                           for i, (audio, motion, _) in enumerate(bins))
            duration += length
        picks = candidates(all_words, signals, duration, self.settings.clip_seconds, duration - seconds)
        if not picks:
            return
        measure = self.chat.measure if self.chat and near_realtime else None
        from workspace_data import topic
        for item in picks:
            theme = topic(item["transcript"])
            bias = self.editorial_weights.get(theme, 0)
            item["features"].update(topic=theme, retention_bias=bias)
            item["av_score"] = max(0, min(100, item["av_score"] + bias))
        pick = rank_chat(picks, duration, arrival, measure)[0]
        start, end = pick["start"], pick["end"]
        count, ratio, people, bonus = pick["chat"]
        reactions = pick["features"]["chat_reactors"]
        pick["features"].update(chat_messages=count, chat_ratio=ratio, chat_people=people)
        score = min(100, pick["av_score"] + bonus)
        verdict = None
        judge_status = "disabled" if not self.settings.model else "not_eligible"
        defer_to_video = self.settings.review_final and self.settings.vision_model and self.settings.performance == "leve"
        if (not defer_to_video and self.settings.model and pick["transcript"] and (score >= 40 or pick["features"]["story_link"])
                and arrival - self.last_judge >= 25):
            verdict = judge_local(self.settings.model, pick["transcript"], pick["features"])
            judge_status = "scored" if verdict else "busy_or_unavailable"
            if verdict:
                self.last_judge = arrival
        elif defer_to_video:
            judge_status = "revisao_final"
        combined = min(100, round(.42 * pick["av_score"] + .58 * verdict["score"] + bonus)) if verdict else score
        preliminary_threshold = (max(15, self.settings.threshold - 16)
                                 if self.settings.review_final else self.settings.threshold)
        accepted = combined >= preliminary_threshold
        from uuid import uuid4
        key = f"candidato_{time.strftime('%H%M%S')}_{uuid4().hex[:6]}"
        result = {"id": key, "raw_score": score, "score": combined, "accepted": accepted, "chat_messages": count,
                  "chat_ratio": ratio, "chat_people": people, "chat_reactors": reactions, "chat_bonus": bonus,
                  "chat_connected": bool(self.chat and self.chat.active),
                  "chat_aligned": bool(self.chat and near_realtime), "signals": pick["features"],
                  "selected_range": [start, end], "judge_status": judge_status,
                  "preliminary_threshold": preliminary_threshold,
                  "model": self.settings.model if verdict else None}
        if verdict:
            result["judge"] = verdict
        logfile = self.root / "triagem.jsonl"
        if logfile.exists() and logfile.stat().st_size > 1_000_000:
            logfile.replace(self.root / "triagem-anterior.jsonl")
        with logfile.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
        database = self.root / "triagem.sqlite3"
        record(database, key, result)
        self.log(f"Triagem {combined}/100 (mínimo da triagem {preliminary_threshold}) | "
                 f"chat +{bonus} | modelo {judge_status} | {'selecionado' if accepted else 'descartado'}")
        if not accepted:
            return
        delivery = self.combine(window, result)
        record(database, key, result, os.path.relpath(delivery, self.root) if delivery else None)
        self.last_clip = arrival
        while self.entries:
            self.release(self.entries.popleft()[0])

    def combine(self, window, result):
        key = result["id"]
        needed = sum(item[0].stat().st_size for item in window)
        if shutil.disk_usage(self.root).free < needed + 128 * 1024 * 1024:
            self.log(f"Sem espaço para montar o candidato {key}; decisão preservada no banco.")
            return None
        capture_dir = window[0][0].parent
        listing = capture_dir / f"{key}.ffconcat"
        target = self.root / f"{key}.mp4"
        partial = target.with_suffix(".partial.mp4")
        manifest = target.with_suffix(".json")
        handed_off = False
        try:
            listing.write_text("".join(f"file '{item[0].name}'\n" for item in window), encoding="ascii")
            command(FF + ["-y", "-f", "concat", "-safe", "1", "-i", str(listing), "-map", "0:v:0",
                          "-map", "0:a:0?", "-c", "copy", "-movflags", "+faststart", str(partial)], timeout=30)
            partial.replace(target)
            manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            enqueued = self.schedule(target, target.with_suffix(""), tuple(result["selected_range"]))
            handed_off = enqueued is not False
            return enqueued if isinstance(enqueued, Path) else target if handed_off else None
        finally:
            listing.unlink(missing_ok=True)
            partial.unlink(missing_ok=True)
            if self.settings.clean and not handed_off:
                target.unlink(missing_ok=True)
                manifest.unlink(missing_ok=True)
