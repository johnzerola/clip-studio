"""Choose a portrait crop on a stable two-person interview shot."""
import cv2
import numpy as np

from vendor.openshorts.active_speaker import attribute_windows, audio_envelope, mouth_region, shares


def focus(source, start, end):
    capture = cv2.VideoCapture(str(source))
    try:
        width, height = (capture.get(prop) for prop in (cv2.CAP_PROP_FRAME_WIDTH, cv2.CAP_PROP_FRAME_HEIGHT))
        if not height or width <= height * .65:
            return None
        small_height = round(384 * height / width)

        def read(at):
            capture.set(cv2.CAP_PROP_POS_MSEC, at * 1000)
            ok, frame = capture.read()
            if ok:
                return cv2.cvtColor(cv2.resize(frame, (384, small_height)), cv2.COLOR_BGR2GRAY)
            return None

        center = read((start + end) / 2)
        if center is None:
            return None
        detector = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        boxes = sorted(detector.detectMultiScale(center, 1.15, 4, minSize=(25, 25)),
                       key=lambda box: box[0])
        if len(boxes) != 2 or boxes[1][0] - boxes[0][0] < 60:
            return None
        regions = [mouth_region(box, 384, small_height) for box in boxes]
        activity = []
        previous = read(start)
        for index in range(int((end - start) / .4)):
            current = read(start + (index + 1) * .4)
            if previous is None or current is None:
                return None
            difference = cv2.absdiff(previous, current)
            activity.append([float(np.mean(difference[y0:y1, x0:x1])) for x0, y0, x1, y1 in regions])
            previous = current
        loudness = audio_envelope(str(source), start, end - start)
        counts = shares(attribute_windows(activity, loudness)) if loudness else (0., 0.)
        if max(counts) < .65:
            return None
        x, _, w, _ = boxes[counts.index(max(counts))]
        crop_fraction = (9 / 16) * height / width
        return max(0., min(1., ((x + w / 2) / 384 - crop_fraction / 2) / (1 - crop_fraction)))
    finally:
        capture.release()
