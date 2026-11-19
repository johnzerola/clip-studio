"""Bounded rolling live analysis. It never makes the recorder wait for inference."""
import collections
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
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from engine import FF, command, inspect, probe, transcribe
from decision_bank import record
from viral_rank import candidates, chat_bonus, judge_local
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


class TwitchPulse:
    def __init__(self, channel, log):
        self.channel, self.log = channel, log
        self.stop = threading.Event()
        self.messages = collections.deque(maxlen=36000)
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
                                        self.messages.append(time.monotonic())
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
            now = sum(1 for t in self.messages if end - seconds <= t <= end)
            before = sum(1 for t in self.messages if end - seconds - 90 <= t < end - seconds)
        ratio = (now / max(seconds, 1)) / max(.08, before / 90)
        return now, round(min(5., ratio), 2)


class LiveScout:
    """Closed segments provide bounded context while recording continues."""
    def __init__(self, capture_root, url, settings, schedule, log):
        self.root = capture_root.resolve()
        self.settings, self.schedule, self.log = settings, schedule, log
        self.pending = queue.Queue(maxsize=12 if settings.catchup else 5)
        self.entries = collections.deque(maxlen=max(3, math.ceil(settings.clip_seconds / 15) + 1))
        self.last_clip = -math.inf
        self.last_judge = -math.inf
        self.last_segment = None
        self.finished = threading.Event()
        parsed = urlparse(url)
        self.chat = TwitchPulse(parsed.path.strip("/"), log) if parsed.hostname == "www.twitch.tv" else None
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
        self.worker.join()
        if self.chat:
            self.chat.stop.set()

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
            seconds, audio = probe(path)
            features = inspect(path, seconds, audio, normalized=False)
            quiet = runtime.active.quiet_pass and features and all(rms < 100 and motion < 2
                                                                  for rms, motion, _ in features)
            words = transcribe(path, 0, seconds, model="tiny") if audio and not quiet else []
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
        pick = max(picks, key=lambda row: row["av_score"])
        start, end = pick["start"], pick["end"]
        # Chat reacts after the moment. Use a short local window, not the entire buffer.
        chat_end = min(arrival, arrival - (duration - end) + 4)
        count, ratio = self.chat.measure(chat_end, 10) if self.chat and near_realtime else (0, 0.)
        bonus = chat_bonus(count, ratio)
        score = min(100, pick["av_score"] + bonus)
        verdict = None
        judge_status = "disabled" if not self.settings.model else "not_eligible"
        if (self.settings.model and pick["transcript"] and (score >= 40 or pick["features"]["story_link"])
                and arrival - self.last_judge >= 25):
            verdict = judge_local(self.settings.model, pick["transcript"], pick["features"])
            judge_status = "scored" if verdict else "busy_or_unavailable"
            if verdict:
                self.last_judge = arrival
        combined = min(100, round(.42 * pick["av_score"] + .58 * verdict["score"] + bonus)) if verdict else score
        preliminary_threshold = (max(15, self.settings.threshold - 16)
                                 if self.settings.review_final else self.settings.threshold)
        accepted = combined >= preliminary_threshold
        from uuid import uuid4
        key = f"candidato_{time.strftime('%H%M%S')}_{uuid4().hex[:6]}"
        result = {"id": key, "raw_score": score, "score": combined, "accepted": accepted, "chat_messages": count,
                  "chat_ratio": ratio, "chat_bonus": bonus, "chat_connected": bool(self.chat and self.chat.active),
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
        try:
            listing.write_text("".join(f"file '{item[0].name}'\n" for item in window), encoding="ascii")
            command(FF + ["-y", "-f", "concat", "-safe", "1", "-i", str(listing), "-map", "0:v:0",
                          "-map", "0:a:0?", "-c", "copy", "-movflags", "+faststart", str(partial)])
            partial.replace(target)
            target.with_suffix(".json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            enqueued = self.schedule(target, target.with_suffix(""), tuple(result["selected_range"]))
            return enqueued if isinstance(enqueued, Path) else target if enqueued is not False else None
        finally:
            listing.unlink(missing_ok=True)
            partial.unlink(missing_ok=True)
