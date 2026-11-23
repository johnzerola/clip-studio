import sqlite3
from array import array
from pathlib import Path
from tempfile import TemporaryDirectory
from contextlib import closing
from subprocess import TimeoutExpired
import unittest
from unittest.mock import patch

from auto_correction import correction, manual_review_score
from decision_bank import record, record_final
from editorial_review import DIMENSIONS, review
from engine import Options, inspect, render_clip
from final_screen import edited_words
from live_render_queue import LiveRenderQueue
from ollama_connection import CACHE_SERVICE, DEFAULT, active_endpoint


class ManualExecutor:
    def __init__(self):
        self.tasks = []

    def submit(self, callback):
        self.tasks.append(callback)


class LiveReliabilityTests(unittest.TestCase):
    def test_ollama_prefers_the_healthy_local_cache(self):
        with patch("ollama_connection.service_models", return_value={"qwen"}) as probe:
            self.assertEqual(active_endpoint("qwen"), CACHE_SERVICE)
            probe.assert_called_once_with(CACHE_SERVICE)
        with patch("ollama_connection.service_models", side_effect=[None, {"qwen"}]):
            self.assertEqual(active_endpoint("qwen"), DEFAULT)
        with patch("ollama_connection.service_models", side_effect=[{"another-model"}, None]):
            with self.assertRaises(ConnectionError):
                active_endpoint("qwen")

    def test_manual_review_requires_technical_quality_and_strong_signals(self):
        fallback = {"technical_ok": True, "score": 42, "local_score": 65, "editorial": {"summary": "Falta contexto"}}
        self.assertEqual(manual_review_score(fallback), 65)
        self.assertEqual(manual_review_score(dict(fallback, score=68)), 68)
        self.assertIsNone(manual_review_score(dict(fallback, local_score=64)))
        self.assertIsNone(manual_review_score(dict(fallback, technical_ok=False)))
        self.assertIsNone(manual_review_score(dict(fallback, review_engine="ollama_editorial",
                                                    recommendation="recommended")))

    def test_missing_context_recovers_prior_footage_even_without_model_adjustment(self):
        options = Options("game", "", "", "direito", False, False, 20, 1, True)
        verdict = {"technical_ok": True, "editorial": {"blocker": "sem_contexto", "adjustment": "nenhum"}}
        result = correction("input.mp4", 30, False, [(10, 25, "game")], [], options, verdict)
        self.assertEqual(result[1], [(2, 10, "game"), (10, 25, "game")])
        self.assertIsNone(correction("input.mp4", 30, False, [(0, 25, "game")], [], options, verdict))
        self.assertIsNone(correction("input.mp4", 30, False, [(10, 25, "game")], [], options, verdict,
                                     protect_edges=True))

    def test_live_triage_keeps_audio_when_video_sampling_times_out(self):
        pcm = array("h", [200] * 1600).tobytes()
        events = []
        with patch("engine.command", side_effect=[pcm, TimeoutExpired("ffmpeg", 25)]) as run:
            signals = inspect(Path("live_0001.ts"), 2, True, normalized=False, timeout=25,
                              fast_video=True, log=events.append)
        self.assertIn("-skip_frame", run.call_args.args[0])
        self.assertEqual(signals, [(200, 0, 0)])
        self.assertIn("continua pelo áudio", events[0])

    def test_timeout_on_gpu_uses_cpu_without_leaving_render_scratch(self):
        options = Options("game", "", "", "direito", False, False, 20, 1, True)
        with TemporaryDirectory() as scratch:
            folder = Path(scratch)
            source, output = folder / "source.mp4", folder / "clip.mp4"
            with (patch("engine.encoder", side_effect=[["-c:v", "h264_nvenc"], ["-c:v", "libx264"]]),
                  patch("engine._render_clip", side_effect=[TimeoutExpired("ffmpeg", 90), {}]) as render):
                report = render_clip(source, output, [(0, 20, "game")], [], options)
            self.assertTrue(report["gpu_fallback"])
            self.assertEqual(report["gpu_error"], "Tempo limite de 90 s")
            self.assertEqual(render.call_args.args[-1][-1], "libx264")
            self.assertEqual(list(folder.iterdir()), [])

    def test_words_are_mapped_to_the_export_after_cutting_silence(self):
        words = [(10, 11, "primeiro"), (12, 13, "removido"), (15, 16, "segundo")]
        shots = [(10, 11.5, "game"), (14.5, 16, "game")]
        self.assertEqual(edited_words(words, shots), [(0, 1, "primeiro"), (2, 3, "segundo")])

    def test_pending_candidates_keep_highest_scores_and_clean_evicted(self):
        executor = ManualExecutor()
        queue = LiveRenderQueue(executor, 1, pending_limit=2, byte_limit=12)
        rendered, discarded = [], []

        def offer(score, size):
            return queue.offer(score, size, lambda: rendered.append(score),
                               lambda reason: discarded.append((score, reason)))

        self.assertTrue(offer(53, 5))
        self.assertTrue(offer(64, 5))
        self.assertTrue(offer(79, 6))
        self.assertFalse(offer(60, 4))
        self.assertFalse(offer(95, 13))
        self.assertEqual(len(executor.tasks), 1)
        while executor.tasks:
            executor.tasks.pop(0)()
        self.assertEqual(rendered, [79, 64])
        self.assertEqual(discarded, [(53, "prioridade_da_fila"), (60, "prioridade_da_fila"),
                                      (95, "limite_temporarios")])
        self.assertEqual(queue.active, 0)

    def test_discarded_candidate_does_not_leave_a_path_in_the_history(self):
        decision = {"raw_score": 60, "score": 60, "chat_messages": 0, "model": None, "accepted": True}
        result = {"score": 60, "status": "skipped", "reason": "prioridade_da_fila"}
        with TemporaryDirectory() as scratch:
            path = Path(scratch) / "triagem.sqlite3"
            record(path, "clip-a", decision, "folder-a")
            record_final(path, "clip-a", [("fila", result)])
            record_final(path, "clip-b", [("fila", result)])
            record(path, "clip-b", decision, "folder-b")
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute("SELECT output FROM decisions ORDER BY id").fetchall(),
                                 [(None,), (None,)])

    def test_visual_review_reuses_same_four_frames_after_first_failure(self):
        reply = {key: 4 for key in DIMENSIONS}
        reply.update(obstaculo="nenhum", motivo="Desfecho visível.", ajuste="nenhum")
        frames = [(index, f"image-{index}") for index in range(4)]
        with patch("editorial_review.retrieve", return_value=[]), patch("editorial_review.time.sleep"), patch(
            "editorial_review.editorial_json", side_effect=[None, reply]
        ) as ollama:
            verdict = review("qwen", [], {}, frames, 60, retry=True)
        self.assertEqual(verdict["recommendation"], "recommended")
        self.assertEqual(ollama.call_count, 2)
        self.assertEqual(ollama.call_args_list[0], ollama.call_args_list[1])
        self.assertTrue(ollama.call_args.kwargs["final_review"])

    def test_visual_review_can_use_three_frames_if_one_sample_is_unavailable(self):
        reply = dict.fromkeys(DIMENSIONS, 4)
        reply.update(obstaculo="nenhum", motivo="A ação está visível.", ajuste="nenhum")
        frames = [(1, "beginning"), (5, "middle"), (9, "end")]
        with patch("editorial_review.retrieve", return_value=[]), patch("editorial_review.editorial_json", return_value=reply) as ollama:
            self.assertIsNone(review("qwen", [], {}, frames[:2], 60))
            verdict = review("qwen", [], {}, frames, 60)
        self.assertEqual(verdict["frame_seconds"], [1, 5, 9])
        ollama.assert_called_once()
