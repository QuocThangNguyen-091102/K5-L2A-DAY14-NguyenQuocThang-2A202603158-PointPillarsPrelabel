"""Nuclio function cho CVAT: PointPillars (KITTI, vf_pp của lab) chạy trên frame PCD của task 3D.

CVAT gửi file PCD của frame, mã hóa base64, trong body["image"]. PCD của lab (scripts/vf_common.bin_to_pcd)
có các trường x y z rgb binary; rgb là mức xám g = 40 + 215*min(1, log1p(v)/log1p(50)) của intensity v
(g = 40 khi v <= 0). Hàm read_pcd đảo ngược công thức đó. Vì g bị làm tròn xuống số nguyên và bị cắt ở
v >= 50, intensity khôi phục chỉ là xấp xỉ.
"""

import base64
import json
import math

import numpy as np

from vf_pp.core import VF_NAMES, Config, Detector

LOG50 = math.log1p(50.0)


def read_pcd(data: bytes) -> np.ndarray:
    """PCD binary x y z rgb (layout của lab) -> float32 (N, 4): x y z intensity."""
    marker = b"DATA binary\n"
    start = data.index(marker) + len(marker)
    header = {}
    for line in data[:start].decode("ascii").splitlines():
        parts = line.split()
        if parts and not parts[0].startswith("#"):
            header[parts[0]] = parts[1:]
    if header.get("FIELDS") != ["x", "y", "z", "rgb"] or header.get("SIZE") != ["4", "4", "4", "4"]:
        raise ValueError(f"PCD không đúng layout x y z rgb (4 byte): {header.get('FIELDS')} {header.get('SIZE')}")
    n = int(header["POINTS"][0])
    rec = np.frombuffer(data, dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("rgb", "<u4")], count=n, offset=start)
    gray = (rec["rgb"] & 0xFF).astype(np.float32)
    intensity = np.where(gray <= 40, 0.0, np.expm1((gray - 40.0) / 215.0 * LOG50)).astype(np.float32)
    return np.stack([rec["x"], rec["y"], rec["z"], intensity], axis=1).astype(np.float32)


def init_context(context):
    context.user_data.detector = Detector(Config())   # nạp model một lần
    context.logger.info("PointPillars đã nạp")


def handler(context, event):
    body = event.body if isinstance(event.body, dict) else json.loads(event.body)
    threshold = float(body.get("threshold", 0.1))
    detector = context.user_data.detector
    detector.set_config(Config(score_thr=threshold))
    points = read_pcd(base64.b64decode(body["image"]))
    boxes = detector.detect(points)
    results = [{
        "type": "cuboid",
        "label": VF_NAMES[b["label"]],
        "confidence": f"{b['score']:.3f}",
        "points": [float(b["x"]), float(b["y"]), float(b["z"]), 0.0, 0.0, float(b["yaw"]),
                   float(b["length"]), float(b["width"]), float(b["height"])] + [0.0] * 7,
    } for b in boxes]
    context.logger.info(f"{len(points)} điểm -> {len(results)} cuboid (threshold {threshold})")
    return context.Response(body=json.dumps(results), content_type="application/json", status_code=200)
