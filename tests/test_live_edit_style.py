from contextlib import closing
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from engine import subtitles
from live_edit_style import kit_direction, post_copy
from posting_queue import db_open, enqueue


def transcript(text):
    return [(i * .3, i * .3 + .28, word) for i, word in enumerate(text.split())]


class LiveKitStyleTest(unittest.TestCase):
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
