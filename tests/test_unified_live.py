import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from engine import Options, layout_graph, layouts, render_clip
from broll_library import configured_visuals, director_items
from finishing import pick_broll
from live_scout import TwitchPulse
from posting_queue import enqueue, ranked
from viral_rank import chat_bonus, has_chat_reaction, rank_chat


class UnifiedLiveTest(unittest.TestCase):
    def test_light_capture_accepts_the_reported_disk_reserve(self):
        from runtime_profile import PROFILES
        from engine import capture_space, CAPTURE_RESERVE
        from types import SimpleNamespace

        with patch("runtime_profile.active", PROFILES["leve"]), patch("engine.shutil.disk_usage") as usage:
            usage.return_value = SimpleNamespace(free=CAPTURE_RESERVE)
            self.assertTrue(capture_space(Path.cwd()))
            usage.return_value.free -= 1
            self.assertFalse(capture_space(Path.cwd()))

    def test_terminal_quality_limits_and_unrated_exports(self):
        from desktop_actions import library, action
        from engine import live_variant_order
        from jobs_cli import prepare
        from workspace_data import register_exports

        self.assertTrue(live_variant_order(2160).startswith("2160p60,2160p,1440p60"))
        self.assertNotIn("2160p", live_variant_order(1440))
        _, options, _, _, _, _, scout = prepare({"sources": ["https://twitch.tv/example"],
                                               "capture_height": 2160, "replay_height": 2160})
        self.assertTrue(options.full_hd)
        self.assertEqual((scout.capture_height, scout.replay_height), (2160, 2160))
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            clip = folder / "clip_01.mp4"
            clip.write_bytes(b"completed export")
            register_exports(folder, (clip,))
            with patch("desktop_actions.folders", return_value=[folder]):
                row, = library("YouTube")
                self.assertIsNone(row["score"])
                self.assertEqual(action("clip-preview", {"id": row["id"]}), {"file": str(clip.resolve())})

    def test_bundled_catalog_uses_only_manifest_media_with_matched_hashes(self):
        root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as directory, patch.dict("os.environ", {"LOCALAPPDATA": directory}):
            library, background, backdrop = configured_visuals(root, {"visual_mode": "local", "visual_background": "catalog"})
        self.assertEqual({item.path.suffix for item in library}, {".gif", ".mp4", ".jpg"})
        self.assertEqual(background, "catalog")
        self.assertTrue(backdrop and all(item.is_current() for item in [*library, backdrop]))

    def test_director_memes_follow_the_spoken_cue_and_skip_unapproved_media(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            asset = root / "reacao.png"
            asset.write_bytes(b"visual")
            item = {"relativePath": asset.name, "sha256": hashlib.sha256(b"visual").hexdigest(), "role": "meme",
                    "rightsStatus": "project-authored", "sourceKind": "camera", "tags": ["cue:olha isso"]}
            manifest = {"schemaVersion": 1, "assets": [item, dict(item, rightsStatus="user-provided-unverified"),
                                                       dict(item, sourceKind="ai-generated"),
                                                       dict(item, relativePath="../reacao.png")]}
            (root / "media-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            approved, = director_items(root)
            self.assertTrue(approved.is_current())
            selected = ((approved.path, approved.cues),)
            shots = [(0., 4., "face")]
            words = [(1., 1.2, "olha"), (1.2, 1.5, "isso!")]
            self.assertEqual(pick_broll("", shots, words, selected=selected, reaction=True), {0: (asset, 1.)})
            self.assertEqual(pick_broll("", shots, words[:1], selected=selected, reaction=True), {})
            asset.write_bytes(b"modified after approval")
            self.assertFalse(approved.is_current())

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
