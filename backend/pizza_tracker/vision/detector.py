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


def count_vehicles(image_bytes: bytes, conf: float = 0.35, roi: tuple[float, float, float, float] | None = None) -> FrameCounts:
    """roi = (x1, y1, x2, y2) as fractions of the frame, e.g. just the lanes into the campus gate."""
    import cv2
    import numpy as np

    frame = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("could not decode camera frame")
    h, w = frame.shape[:2]
    result = _model()(frame, conf=conf, classes=list(COCO_VEHICLES), verbose=False)[0]

    by_class: dict[str, int] = {}
    for box, cls in zip(result.boxes.xyxy.tolist(), result.boxes.cls.tolist()):
        if roi:
            cx, cy = (box[0] + box[2]) / 2 / w, (box[1] + box[3]) / 2 / h
            if not (roi[0] <= cx <= roi[2] and roi[1] <= cy <= roi[3]):
                continue
        name = COCO_VEHICLES[int(cls)]
        by_class[name] = by_class.get(name, 0) + 1

    return FrameCounts(
        vehicle_count=sum(by_class.values()),
        delivery_vehicle_count=sum(v for k, v in by_class.items() if k in DELIVERY_PROXY),
        by_class=by_class,
    )
