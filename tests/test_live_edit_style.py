from contextlib import closing
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from engine import Options, layout_graph, layouts, subtitles
from live_edit_style import focus_expression, gameplay_focus, gameplay_with_face, kit_direction, post_copy
from jobs_cli import prepare
from posting_queue import db_open, enqueue


def transcript(text):
    return [(i * .3, i * .3 + .28, word) for i, word in enumerate(text.split())]


class LiveKitStyleTest(unittest.TestCase):
    def test_gta_preset_is_available_from_a_link_and_preserves_native_gameplay(self):
        sources, options, *_, scout = prepare({"style": "gta6", "sources": ["https://kick.com/gabepeixe"]})
        self.assertEqual(sources[0][1], "live")
        self.assertEqual(options.style, "dynamic")
        self.assertEqual(options.live_kit_mode, "on")
        self.assertFalse(scout.auto_finalize)
        self.assertEqual(gameplay_with_face([(0, 10, "game")]), [(0, 2., "split"), (2., 10, "gamecam")])

    def test_gameplay_focus_ignores_edge_noise_and_tracks_a_local_change(self):
        import numpy as np
        before = np.zeros((54, 96), dtype=np.uint8)
        after = before.copy()
        after[15:45, :12] = 255
        self.assertEqual(gameplay_focus(before.tobytes() + after.tobytes()), [.5, .5])
        after[24:40, 26:36] = 255
        points = gameplay_focus(before.tobytes() + after.tobytes())
        self.assertLess(points[-1], .5)
        self.assertIn("clip(", focus_expression(points, 0))
    def test_live_gameplay_uses_a_detail_shot_at_a_spoken_cue(self):
        options = Options("dynamic", "", "", "direito", True, False, 20, 1, True,
                          live_edit=True, transition="v9", smart_reframe=True)
        words = [(8, 8.2, "senha,")]
        self.assertEqual(layouts([], 0, 20, options, words),
                         [(0, 8, "game"), (8, 10.1, "game_detail"), (10.1, 20, "game")])
        self.assertEqual(layouts([], 0, 20, options), [(0, 20, "game")])
        self.assertNotIn("crop=iw*0.82", layout_graph("game", options))
        self.assertIn("crop=iw*0.82", layout_graph("game_detail", options))

    def test_automatic_detection_and_forced_session(self):
        self.assertIsNone(kit_direction(transcript("Olha isso, GTA cinco!")))
        self.assertEqual(kit_direction(transcript("Como fazer no GTA VI"))["kind"], "dica")
        self.assertEqual(kit_direction(transcript("Meu Deus, GTA 6!"))["kind"], "reacao")
        forced = kit_direction(transcript("Repare no detalhe."), force=True)
        self.assertEqual(forced["kind"], "descoberta")
        self.assertNotIn("#GTA6", post_copy(forced, "Repare no detalhe.", "")["tags"])
        self.assertEqual(kit_direction([], force=True)["kind"], "momento")

    def test_subtitles_and_saved_draft(self):
        speech = "Olha isso no GTA 6! Repare no detalhe antes da ponte."
        words = transcript(speech)
        direction = kit_direction(words)
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            ass = folder / "test.ass"
            subtitles(ass, words, 0, 5, "split", "gta-kit", "Olha isso no GTA 6!", 0,
                      gta_accent=direction["accent"])
            text = ass.read_text(encoding="utf-8")
            self.assertIn("&HA02EFF&", text)
            self.assertIn(r"\t(0,100,", text)
            self.assertIn("0:00:02.00,Hook", text)
            media = folder / "clip_01.mp4"
            media.write_bytes(b"test")
            verdict = {"status": "ready", "score": 83, "reason": "teste", "live_kit": direction}
            with patch("posting_queue.media_signature", return_value=[]), patch(
                "posting_queue.copy_from_model", side_effect=AssertionError("extra model call")
            ), patch("posting_queue.topic_matches", side_effect=AssertionError("extra network call")):
                clip = enqueue(folder, media, media, verdict, speech, "Olha isso no GTA 6!", "modelo")
            with closing(db_open(folder)) as db:
                row = db.execute("SELECT title,description,tags FROM clips WHERE id=?", (clip,)).fetchone()
                review = db.execute("SELECT detail FROM clip_reviews WHERE clip=?", (clip,)).fetchone()
            self.assertEqual(row["title"], "Olha isso no GTA 6!")
            self.assertIn("Qual teria sido a sua reação?", row["description"])
            self.assertIn("#GTA6", row["tags"].split())
            self.assertEqual(json.loads(review["detail"])["live_kit"]["kind"], "reacao")
