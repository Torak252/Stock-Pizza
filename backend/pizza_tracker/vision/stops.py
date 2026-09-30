"""Delivery-style short stops from a sequence of camera stills.

A pizza run at a campus gate looks like: a car appears, sits still for a few minutes, leaves.
DOT stills refresh every 1-5 min, so we match detections frame to frame by box overlap and
count vehicles that stayed put for >= 2 frames and then left within `max_stop_s`.
Longer stays (parked employees) and pass-through traffic (seen once) don't count.
"""
from __future__ import annotations

from dataclasses import dataclass, field

Box = tuple[float, float, float, float]  # x1, y1, x2, y2 as fractions of the frame


def iou(a: Box, b: Box) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


@dataclass
class Track:
    box: Box
    cls: str
    first_seen: float
    last_seen: float
    frames: int = 1


@dataclass
class StopTracker:
    min_iou: float = 0.5        # same spot = stationary
    max_stop_s: float = 15 * 60  # longer than this is parking, not a drop-off
    tracks: list[Track] = field(default_factory=list)

    def update(self, detections: list[tuple[Box, str]], ts: float) -> int:
        """Feed one frame (timestamp in seconds). Returns short stops that ended at this frame."""
        unmatched = list(range(len(detections)))
        survivors: list[Track] = []
        ended = 0
        for tr in self.tracks:
            best, best_iou = None, self.min_iou
            for i in unmatched:
                box, cls = detections[i]
                if cls == tr.cls and (score := iou(box, tr.box)) >= best_iou:
                    best, best_iou = i, score
            if best is not None:
                unmatched.remove(best)
                tr.box, tr.last_seen, tr.frames = detections[best][0], ts, tr.frames + 1
                survivors.append(tr)
            elif tr.frames >= 2 and tr.last_seen - tr.first_seen <= self.max_stop_s:
                ended += 1  # sat still for 2+ frames, then left: a short stop
        for i in unmatched:
            box, cls = detections[i]
            survivors.append(Track(box, cls, ts, ts))
        self.tracks = survivors
        return ended
