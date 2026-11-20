"""From OpenShorts b3cd947bc48ad1fc8093bb8f8291b9fb02e9bb2f (MIT). See LICENSE."""

def dedupe_overlapping(shorts, ratio=0.25):
    """Drop clips that overlap an already-kept clip by ``ratio`` of the
    shorter one, keeping the higher ``predicted_score`` (earlier on a tie).

    0.25, not 0.5: two clips sharing 25 s of 59 s (42%) both survived the old
    bar and the same punchline came out twice in one batch.

    The detail prompt's DIVERSITY rule is the only thing that stopped two
    clips from sharing the same seconds, and a rule is not a guarantee: two
    picks from one window can cover the same moment with different edges,
    and the user then downloads the same short twice. Survivors come back in
    transcript order, like ``trim_to_best``.
    """
    def _score(c):
        try:
            return float(c.get("predicted_score") or 0)
        except (TypeError, ValueError, AttributeError):
            return 0.0

    def _span(c):
        try:
            return float(c.get("start", 0)), float(c.get("end", 0))
        except (TypeError, ValueError, AttributeError):
            return 0.0, 0.0

    indexed = list(enumerate(shorts))
    kept = []
    for idx, clip in sorted(indexed, key=lambda p: (-_score(p[1]), p[0])):
        s, e = _span(clip)
        clash = False
        for _, other in kept:
            os_, oe = _span(other)
            overlap = min(e, oe) - max(s, os_)
            shorter = max(1e-6, min(e - s, oe - os_))
            if overlap > 0 and overlap / shorter >= ratio:
                clash = True
                break
        if not clash:
            kept.append((idx, clip))
    return [c for _, c in sorted(kept, key=lambda p: p[0])]
