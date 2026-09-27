import reflex as rx

import base64
import io
import logging
from app.components.deepshield.contracts import Evidence


def faces(image) -> list[Evidence]:
    import cv2
    import numpy as np

    try:
        cascade_classifier = getattr(cv2, "CascadeClassifier", None)
        cv2_data = getattr(cv2, "data", None)
        haarcascades = getattr(cv2_data, "haarcascades", None)
        if not callable(cascade_classifier) or not haarcascades:
            return [Evidence(kind="face_detection_unavailable")]

        detector = cascade_classifier(
            f"{haarcascades}haarcascade_frontalface_default.xml"
        )
        if detector.empty():
            return [Evidence(kind="face_detection_unavailable")]
        scale = min(1.0, 1024 / max(image.size))
        small = image.resize(
            (
                max(1, int(image.width * scale)),
                max(1, int(image.height * scale)),
            )
        )
        boxes = detector.detectMultiScale(
            cv2.cvtColor(np.asarray(small), cv2.COLOR_RGB2GRAY),
            1.1,
            5,
            minSize=(32, 32),
        )
        output = []
        for box in boxes[:4]:
            x, y, w, h = [int(v / scale) for v in box]
            crop = image.crop((x, y, x + w, y + h))
            crop.thumbnail((160, 160))
            buffer = io.BytesIO()
            crop.save(buffer, format="JPEG", quality=80)
            output.append(
                Evidence(
                    kind="face_crop",
                    data={
                        "box_xywh": [x, y, w, h],
                        "coordinate_space": "oriented_source_pixels",
                        "source_size": list(image.size),
                        "jpeg_base64": base64.b64encode(
                            buffer.getvalue()
                        ).decode("ascii"),
                        "detector": "opencv_haar_frontalface",
                        "scope": "localization_only_not_identity",
                    },
                )
            )
        return output
    except Exception as e:
        logging.exception(f"Error: {e}")
        return [Evidence(kind="face_detection_unavailable")]


def occlusion(image, scorer, original: float) -> Evidence:
    from PIL import ImageDraw

    changes = []
    for y in range(3):
        for x in range(3):
            modified = image.copy()
            box = [
                x * image.width // 3,
                y * image.height // 3,
                (x + 1) * image.width // 3,
                (y + 1) * image.height // 3,
            ]
            ImageDraw.Draw(modified).rectangle(box, fill=(123, 117, 104))
            changes.append(original - scorer(modified))
    return Evidence(
        kind="occlusion",
        data={
            "grid": [3, 3],
            "score_deltas": changes,
            "coordinate_space": "oriented_source_fraction",
            "target": "synthetic_score",
            "baseline_fill": [123, 117, 104],
            "disclaimer": "Sensitivity to artificial masking, not localization of proven manipulation; center-crop may exclude regions.",
        },
    )
