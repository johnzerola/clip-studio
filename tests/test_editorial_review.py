import unittest
from unittest.mock import patch

from editorial_review import DIMENSIONS, interpret, review, transcript_cues
from viral_rank import candidates


class EditorialReviewTests(unittest.TestCase):
    def test_high_motion_cannot_replace_payoff(self):
        values = dict.fromkeys(DIMENSIONS, 4)
        values.update(desfecho=0, obstaculo="nenhum", motivo="A ação não conclui.")
        verdict = interpret(values, 60)
        self.assertEqual(verdict["recommendation"], "weak")
        self.assertLess(verdict["score"], 60)

    def test_review_requires_simultaneous_frames_and_transcript_context(self):
        words = [(0.4, 0.7, "Consegui!")]
        frames = [(1., "a"), (3., "b"), (6., "c"), (8.5, "d")]
        values = dict.fromkeys(DIMENSIONS, 4)
        values.update(obstaculo="nenhum", motivo="A jogada termina com a vitória visível.")
        with patch("editorial_review.editorial_json", return_value=values) as send:
            self.assertIsNone(review("modelo", words, {}, frames[:3], 60))
            self.assertEqual(review("modelo", words, {}, frames, 60)["recommendation"], "recommended")
        call = send.call_args.args
        self.assertEqual(call[2]["transcricao"], transcript_cues(words))
        self.assertEqual(call[2]["quadros_segundos"], [item[0] for item in frames])
        self.assertEqual(call[4], ["a", "b", "c", "d"])

    def test_repetitive_audio_does_not_win_cheap_triage(self):
        words = [(i * .6, i * .6 + .4, "mano") for i in range(18)]
        signals = [(float(at), 12., .95) for at in range(0, 14, 2)]
        self.assertLessEqual(max(row["av_score"] for row in candidates(words, signals, 14, 14, 4)), 32)

    def test_invalid_model_scores_are_ignored(self):
        values = dict.fromkeys(DIMENSIONS, 4)
        values.update(gancho=True, obstaculo="nenhum", motivo="Incompleto")
        self.assertIsNone(interpret(values, 60))
