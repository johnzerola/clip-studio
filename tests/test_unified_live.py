import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from engine import Options, layout_graph, layouts, render_clip
from live_scout import TwitchPulse
from posting_queue import enqueue, ranked
from viral_rank import chat_bonus, has_chat_reaction, rank_chat


class UnifiedLiveTest(unittest.TestCase):
    def test_reviewed_local_render_is_added_to_posting_queue(self):
        with (TemporaryDirectory() as directory,
              patch("posting_queue.topic_matches", return_value=[]),
              patch("posting_queue.media_signature", return_value=[])):
            folder = Path(directory)
            original, clip = folder / "original.mp4", folder / "clip_01.mp4"
            original.write_bytes(b"original")
            clip.write_bytes(b"export")
            verdict = {"source": str(original), "score": 78, "status": "ready", "reason": "Gancho claro"}
            key = enqueue(folder, clip, clip, verdict, "Transcrição do trecho", "Destaque", "")
            self.assertEqual(ranked(folder)[0]["id"], key)

    def test_failed_gpu_render_retries_with_cpu(self):
        options = Options("dynamic", "", "", "direito", False, False, 10, 1, True)
        gpu = ["-c:v", "h264_nvenc"]
        cpu = ["-c:v", "libx264"]
        with (TemporaryDirectory() as folder,
              patch("engine.encoder", side_effect=[gpu, cpu]) as encode,
              patch("engine._render_clip", side_effect=[RuntimeError("encoder unavailable"), {}]) as render):
            result = render_clip(Path(folder) / "source.mp4", Path(folder) / "clip.mp4", [], [], options)
            self.assertTrue(result["gpu_fallback"])
            self.assertEqual(render.call_count, 2)
            self.assertTrue(encode.call_args.kwargs["software_only"])

    def test_chat_reactions_are_counted_per_viewer(self):
        pulse = TwitchPulse("example", lambda _: None)
        pulse.messages.extend([
            (10, b"a", False), (91, b"a", True), (92, b"a", True),
            (93, b"b", True), (94, b"c", False), (95, b"d", False), (96, b"e", False),
        ])
        count, ratio, people, reactors = pulse.measure(100, 10)
        self.assertEqual((count, people, reactors), (6, 5, 2))
        self.assertEqual(chat_bonus(count, ratio, people, reactors), 8)
        self.assertLess(chat_bonus(10, 3, 1, 1), 3)
        self.assertTrue(has_chat_reaction("KKKKK 🔥"))
        self.assertFalse(has_chat_reaction("vou sair agora"))

    def test_chat_unavailable_preserves_audiovisual_order(self):
        weak = {"end": 20, "av_score": 48, "features": {}}
        strong = {"end": 30, "av_score": 73, "features": {}}
        best, _ = rank_chat([weak, strong], duration=30, arrival=100)
        self.assertIs(best, strong)
        self.assertEqual(best["chat"], (0, 0., 0, 0))

    def test_approved_rhythm_moves_camera_change_without_splitting_speech(self):
        signals = [(1., 1., 1.), (1., 1., 1.), (1., 1.1, 1.), (1., 3., 1.)]
        words = [(0., 3.2, "frase."), (3.3, 4.7, "continua."), (5., 7.8, "fim.")]
        options = Options("dynamic", "0:0:100:100", "", "direito", True, False, 10, 1, True,
                          transition="v9", look="shorts", target_shot_seconds=4.7)
        self.assertEqual(layouts(signals, 0, 8, options, words),
                         [(0, 4.7, "split"), (4.7, 8, "game")])

    def test_portrait_fill_keeps_full_screen_without_a_detected_focus(self):
        options = Options("dynamic", ".1,.1,.2,.2", ".2,0,.75,1", "direito", True, False,
                          10, 1, True, transition="v9", smart_reframe=True)
        for layout, region in (("face", "crop=iw*0.2"), ("game", "crop=iw*0.75")):
            graph = layout_graph(layout, options)
            self.assertIn(region, graph)
            self.assertIn("crop=720:1280:(iw-ow)*0.5", graph)
            self.assertNotIn("gblur", graph)


if __name__ == "__main__":
    unittest.main()
