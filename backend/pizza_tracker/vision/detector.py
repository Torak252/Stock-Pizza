"""Vehicle counting on DOT still frames with YOLO.

Only aggregate counts leave this module; frames are processed in memory and discarded
(no plates, faces or images are retained), which keeps us clear of most privacy issues.

COCO has no "delivery driver" class, so Phase 1 counts cars/trucks/motorcycles and treats
small trucks + vans as a delivery proxy. Phase 2 fine-tunes on labelled frames to add a
real `delivery_vehicle` class (branded cars, Amazon vans, scooters).
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

COCO_VEHICLES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
DELIVERY_PROXY = {"truck", "motorcycle"}


@dataclass
class FrameCounts:
    vehicle_count: int
    delivery_vehicle_count: int
    by_class: dict[str, int]


@lru_cache(maxsize=1)
def _model(weights: str = "yolo11n.pt"):
    from ultralytics import YOLO  # optional dependency: pip install -e ".[vision]"

    return YOLO(weights)


Roi = tuple[float, float, float, float]


def _in_roi(box: list[float], w: int, h: int, roi: Roi | None) -> bool:
    if not roi:
        return True
    cx, cy = (box[0] + box[2]) / 2 / w, (box[1] + box[3]) / 2 / h
    return roi[0] <= cx <= roi[2] and roi[1] <= cy <= roi[3]


def _detect(image, conf: float):
    """image: encoded bytes (JPEG/PNG) or a decoded BGR array.

    Input size follows the frame: HD stream frames run at 1280 px so distant cars survive;
    small stills (e.g. Caltrans 320x260) stay at 640, where upscaling further adds noise.
    """
    import cv2
    import numpy as np

    frame = image if isinstance(image, np.ndarray) else cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("could not decode camera frame")
    imgsz = 1280 if frame.shape[1] >= 960 else 640
    result = _model()(frame, imgsz=imgsz, conf=conf, classes=list(COCO_VEHICLES), verbose=False)[0]
    boxes = [(box, COCO_VEHICLES[int(cls)]) for box, cls in zip(result.boxes.xyxy.tolist(), result.boxes.cls.tolist())]
    return frame, boxes


def _counts(by_class: dict[str, int]) -> FrameCounts:
    return FrameCounts(
        vehicle_count=sum(by_class.values()),
        delivery_vehicle_count=sum(v for k, v in by_class.items() if k in DELIVERY_PROXY),
        by_class=by_class,
    )


def is_placeholder(image) -> bool:
    """True for "Temporarily Unavailable" cards and blank frames: mostly one flat colour.

    A real road scene has texture almost everywhere; a placeholder is a flat background with
    a little text. Recording 0 vehicles for those would drag the baseline down.
    """
    import cv2
    import numpy as np

    frame = image if isinstance(image, np.ndarray) else cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        return True
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)[: int(frame.shape[0] * 0.85)]  # skip the timestamp bar
    edges = cv2.Laplacian(gray, cv2.CV_64F)
    flat_share = float((np.abs(edges) < 2).mean())
    return flat_share > 0.8 or float(gray.std()) < 8


def detect_boxes(image_bytes, conf: float = 0.25, roi: Roi | None = None) -> list[tuple[tuple[float, float, float, float], str]]:
    """Vehicles inside the ROI as (normalized box, class name)."""
    frame, boxes = _detect(image_bytes, conf)
    h, w = frame.shape[:2]
    return [((b[0] / w, b[1] / h, b[2] / w, b[3] / h), name) for b, name in boxes if _in_roi(b, w, h, roi)]


def counts_from(detections: list[tuple[tuple[float, float, float, float], str]]) -> FrameCounts:
    by_class: dict[str, int] = {}
    for _, name in detections:
        by_class[name] = by_class.get(name, 0) + 1
    return _counts(by_class)


def count_vehicles(image_bytes, conf: float = 0.25, roi: Roi | None = None) -> FrameCounts:
    """roi = (x1, y1, x2, y2) as fractions of the frame, e.g. just the lanes into the campus gate."""
    return counts_from(detect_boxes(image_bytes, conf, roi))


def annotate(image_bytes, conf: float = 0.25, roi: Roi | None = None) -> tuple[bytes, FrameCounts]:
    """Draw the ROI and every detection (green = counted, grey = outside ROI) for manual review."""
    import cv2

    frame, boxes = _detect(image_bytes, conf)
    h, w = frame.shape[:2]
    by_class: dict[str, int] = {}
    if roi:
        cv2.rectangle(frame, (int(roi[0] * w), int(roi[1] * h)), (int(roi[2] * w), int(roi[3] * h)), (0, 165, 255), 2)
    for box, name in boxes:
        inside = _in_roi(box, w, h, roi)
        if inside:
            by_class[name] = by_class.get(name, 0) + 1
        color = (0, 200, 0) if inside else (150, 150, 150)
        x1, y1, x2, y2 = map(int, box)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 1)
        cv2.putText(frame, name, (x1, max(y1 - 3, 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
    ok, jpg = cv2.imencode(".jpg", frame)
    if not ok:
        raise ValueError("could not encode preview")
    return jpg.tobytes(), _counts(by_class)
