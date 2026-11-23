"""Find a recurring corner webcam in a small set of sampled frames."""
import statistics


def estimate(frames, width, height):
    import cv2
    import numpy as np

    cv2.setNumThreads(1)
    detector = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    alternate = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_alt2.xml")
    if detector.empty():
        raise RuntimeError("Classificador de facecam indisponível.")

    def corner_hits(boxes):
        for x, y, w, h in boxes:
            cx, cy = (x + w / 2) / width, (y + h / 2) / height
            on_edge = cx < .24 or cx > .76
            in_corner = (cx < .34 or cx > .66) and (cy < .38 or cy > .62)
            if (on_edge or in_corner) and w / width <= .19:
                yield cx, cy, w / width, h / height

    clusters = []
    for index, frame in enumerate(frames):
        gray = np.frombuffer(frame, dtype=np.uint8).reshape(height, width)
        hits = list(corner_hits(detector.detectMultiScale(gray, 1.12, 5, minSize=(20, 20))))
        if not hits and not alternate.empty():
            side = round(width * .34)
            for left in (0, width - side):
                detail = cv2.resize(gray[:, left:left + side], None, fx=1.5, fy=1.5)
                boxes = alternate.detectMultiScale(cv2.equalizeHist(detail), 1.1, 4, minSize=(21, 21))
                hits.extend(corner_hits((x / 1.5 + left, y / 1.5, w / 1.5, h / 1.5)
                                        for x, y, w, h in boxes))
        for hit in hits:
            cx, cy, _, _ = hit
            for group in clusters:
                if any(abs(cx - p[0]) + abs(cy - p[1]) < .075 for p in group.values()):
                    group.setdefault(index, hit)
                    break
            else:
                clusters.append({index: hit})
    if not clusters:
        return ""
    best = max(clusters, key=len)
    if len(best) < max(3, len(frames) * .35):
        return ""
    cx, cy, fw, fh = (statistics.median(items) for items in zip(*best.values()))
    w, h = min(.32, fw * 1.85), min(.36, fh * 1.85)
    x, y = min(max(0, cx - w / 2), 1 - w), min(max(0, cy - h * .43), 1 - h)
    return ",".join(f"{v:.5f}" for v in (x, y, w, h))


def gameplay_region(face):
    if not face:
        return ""
    x, y, w, h = map(float, face.split(","))
    # A corner webcam is baked into the source; leave it out of the gameplay crop.
    if x + w < .36:
        left = min(.4, x + w + .015)
        return f"{left:.5f},0,{1 - left:.5f},1"
    if x > .64:
        return f"0,0,{max(.6, x - .015):.5f},1"
    if y + h < .30:
        top = y + h
        return f"0,{top:.5f},1,{1 - top:.5f}"
    if y > .70:
        return f"0,0,1,{y:.5f}"
    return ""


if __name__ == "__main__":
    import sys

    width, height = map(int, sys.argv[1:3])
    size = width * height
    payload = sys.stdin.buffer.read()
    if len(payload) % size:
        raise ValueError("Quadros incompletos.")
    print(estimate([payload[i:i + size] for i in range(0, len(payload), size)], width, height))
