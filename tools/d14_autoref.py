"""Công cụ tự động hỗ trợ sửa nhãn Day 14 (khai báo theo RULES.md: "công cụ tự động khác ngoài pre-label của lab").

Tạo bộ hộp "đề xuất sửa" cho từng frame bằng một model thứ hai, ĐỘC LẬP với PointPillars-KITTI của lab:

  1. CenterPoint pillar (nuScenes, mmdet3d, viết lại bằng PyTorch thuần trong
     Lab/cvat_download/centerpoint_pure.py) + TTA lật trục. Model nuScenes nhìn 360° và có sẵn
     lớp truck/bus/pedestrian/motorcycle/bicycle.
  2. Chạy thêm trên ±3 frame lân cận cùng sequence, ghép bằng ICP (ego-motion), nối hộp qua thời gian:
     sửa hướng theo chuyển động / bỏ phiếu hướng, lấy kích thước trung vị có trọng số, loại hộp chỉ
     thấy một lần với điểm thấp, loại xe hai bánh đứng yên thấp (xe dựng không người -> guideline: không vẽ).
  3. Kéo đáy hộp về mặt đường ước từ điểm quanh hộp, loại hộp < 5 điểm, giữ hộp có tâm <= 50 m.
  4. Lọc theo hình dạng điểm (bài học duyệt tay trong cuboid3d/track.py + soát bằng mắt tập A Day 14):
     xe quá ít điểm/điểm phẳng, Truck/Bus điểm thấp hoặc có tán cây phía trên, điểm chạy liên tục ra
     ngoài hộp (hàng cây, lan can), "người" không ra hình người hoặc mảnh như cột. Hộp bị loại và lý do
     ghi ra <out>.rejected.txt để người kiểm xem lại.

Đây là bản chuyển thể của d13_temporal.py (bộ công cụ tôi đã dùng ở Day 13). Kết quả là ĐỀ XUẤT:
hộp được đưa lên CVAT để người kiểm, không phải nhãn đúng tuyệt đối.

    python tools/d14_autoref.py --data <Data-VF> --frames d14_<ID>/frames_A.txt --out out/autoref_A.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CVAT_TOOLS = ROOT.parent / "cvat_download"          # bộ công cụ Day 13 của tôi (ngoài repo nộp)
sys.path.insert(0, str(CVAT_TOOLS))

from scripts import vf_common as vf  # noqa: E402
from scripts import vf_d14, vf_qa  # noqa: E402

import centerpoint_pure as cp  # noqa: E402
import d13_temporal as tmp  # noqa: E402  (run_model, window_poses, link, refine, keep_box)
from cuboid_track import to_world  # noqa: E402

CKPT = CVAT_TOOLS / "cuboid3d" / "models" / tmp.CKPT
MAX_LIFT = {"Car": 1.6, "Pedestrian": 1.9, "Cyclist": 1.8, "Truck": 2.5, "Bus": 2.5}


def load_cloud(data: Path, seq: int, idx: int, stamps) -> np.ndarray:
    return np.fromfile(data / f"sequence_{seq:02d}" / "lidar" / f"{stamps[idx]}.bin", dtype=np.float32).reshape(-1, 4)


def detections(model, data, seq, idx, stamps, cache_dir: Path):
    cache = cache_dir / f"s{seq:02d}f{idx:02d}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    dets = tmp.run_model(model, load_cloud(data, seq, idx, stamps))
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(dets))
    return dets


def ground_fix(b: dict, pts: np.ndarray, grid) -> bool:
    """Kéo đáy về mặt đường (cách d13_ground.py). False = hộp lơ lửng quá cao (biển hiệu, mái che) -> bỏ."""
    st = vf_qa.box_stats(b, grid)
    c, s = math.cos(b["yaw"]), math.sin(b["yaw"])
    dx, dy = pts[:, 0] - b["x"], pts[:, 1] - b["y"]
    lx, ly = c * dx + s * dy, -s * dx + c * dy
    col = pts[(np.abs(lx) <= b["length"] / 2) & (np.abs(ly) <= b["width"] / 2), 2]
    r = np.hypot(dx, dy)
    ring = pts[(r > 4) & (r < 10), 2]
    g4 = st["ground"]
    g10 = float(np.percentile(ring, 3)) if len(ring) > 30 else None
    ground = g4 if g4 is not None else g10
    bottom = b["z"] - b["height"] / 2
    above = col[col > (ground if ground is not None else bottom) + 0.15]
    objmin = float(above.min()) if len(above) else None
    if ground is not None and objmin is not None and objmin - ground > MAX_LIFT[b["label"]]:
        return False
    if g4 is not None:
        new_bottom = g4
    elif g10 is not None and abs(bottom - g10) < 0.6 and (objmin is None or objmin >= g10 - 0.1):
        new_bottom = g10
    else:
        return True
    moved = {**b, "z": new_bottom + b["height"] / 2}
    if vf_qa.box_stats(moved, grid)["inside"] >= max(5, 0.5 * st["inside"]):
        b["z"] = moved["z"]
    return True


def shape_features(pts: np.ndarray, b: dict) -> dict:
    """Hình dạng điểm trong/quanh hộp: số điểm, bề cao điểm, độ loe, tán phía trên, điểm liên tục ra ngoài hộp."""
    c, s = math.cos(b["yaw"]), math.sin(b["yaw"])
    dx, dy = pts[:, 0] - b["x"], pts[:, 1] - b["y"]
    lx, ly = c * dx + s * dy, -s * dx + c * dy
    zb = b["z"] - b["height"] / 2
    zt = zb + b["height"]
    hl, hw = b["length"] / 2, b["width"] / 2
    inz = (pts[:, 2] > zb + 0.3) & (pts[:, 2] < zt)
    foot = (np.abs(lx) <= hl) & (np.abs(ly) <= hw)
    inside = foot & inz
    q = pts[inside]
    n = int(inside.sum())
    above = int((foot & (pts[:, 2] > zt) & (pts[:, 2] < zt + 3)).sum())
    ring = ((np.abs(lx) <= hl + 1.0) & (np.abs(ly) <= hw + 1.0) & ~foot & inz).sum()
    return {"n": n, "above": above, "cont": round(float(ring) / max(n, 1), 2),
            "wfrac": round(float(np.ptp(ly[inside])) / b["width"], 2) if n > 1 else 0.0,
            "zext": round(float(np.ptp(q[:, 2])), 2) if n > 1 else 0.0,
            "spread": round(float(np.percentile(np.linalg.norm(q[:, :2] - q[:, :2].mean(0), axis=1), 90)), 2)
            if n > 1 else 0.0}


def reject_reason(b: dict, f: dict) -> str | None:
    """Bài học từ lần duyệt tay trước (cuboid3d/track.py) + kiểm tra hàng cây/lan can khi soát tập A Day 14."""
    g, n, sc = tmp.GROUP[b["label"]], f["n"], b["score"]
    if g == "veh":
        if n < 8:
            return f"xe chỉ có {n} điểm"
        if n < 15 and f["zext"] < 0.3:
            return f"điểm phẳng thấp ({n} điểm, cao {f['zext']} m)"
        if b["label"] in ("Truck", "Bus") and sc < 0.4:
            return f"lớp hiếm nhưng điểm model thấp ({sc:.2f}) - thường là bụi cây/tường"
        if b["label"] in ("Truck", "Bus") and not b["moving"] and f["above"] > 25:
            return f"Truck/Bus đứng yên có {f['above']} điểm tán phía trên - hàng cây"
        if b["label"] in ("Truck", "Bus") and b["length"] >= 8.0 and f["zext"] < 2.0 and not b["moving"]:
            return f"xe dài {b['length']:.1f} m nhưng điểm chỉ cao {f['zext']} m - hàng rào/tường"
        if b["label"] == "Bus" and (f["zext"] < 2.0 or f["wfrac"] < 0.5):
            return f"Bus nhưng điểm chỉ cao {f['zext']} m / phủ {f['wfrac']:.0%} bề ngang - bồn cây/nhà chờ"
        if not b["moving"] and sc < 0.6 and (f["cont"] > 0.8 or (f["cont"] > 0.5 and f["above"] > 5)):
            return f"đứng yên, điểm chạy liên tục ra ngoài hộp (cont {f['cont']}, tán {f['above']}) - hàng cây/lan can"
    elif g == "ped":
        if n < 8 and not (b["moving"] and n >= 4):
            return f"người chỉ có {n} điểm"
        if f["zext"] < 0.6 and not b["moving"]:
            return f"điểm không ra hình người (cao {f['zext']} m)"
        if f["zext"] < 1.0 and not b["moving"] and n < 40:
            return f"đứng yên, chỉ thấy đoạn cao {f['zext']} m - thường là thân cây sau bồn cây"
        if f["above"] > 40:
            return "nhiều điểm phía trên đầu (tán cây)"
        if f["spread"] < 0.12:
            return f"điểm rất hẹp ({f['spread']} m) - giống cột"
    else:
        if sc < 0.4:
            return f"điểm model thấp ({sc:.2f})"
        if f["above"] > 40:
            return "có tán cây/biển báo phía trên"
        if f["zext"] < 0.3:
            return "điểm phẳng (mặt đường)"
        if f["cont"] > 0.8 and sc < 0.6 and not b["moving"]:
            return f"điểm chạy liên tục ra ngoài hộp (cont {f['cont']})"
    return None


def autoref_frame(model, data: Path, seqs, name: str, cache_dir: Path) -> tuple[list[dict], str]:
    s, i = vf.parse_frame_name(name)
    stamps = seqs[s]
    frames = [j for j in range(i - tmp.HALF, i + tmp.HALF + 1) if 0 <= j < len(stamps)]
    clouds = {j: load_cloud(data, s, j, stamps)[:, :3] for j in frames}
    dets = {j: detections(model, data, s, j, stamps, cache_dir) for j in frames}
    T, log, frames = tmp.window_poses(clouds, dets, i, frames)
    dets_w = {j: [to_world(d, T[j]) for d in dets[j]] for j in frames}
    boxes = [tmp.refine(c, tmp.link(c, dets_w, frames, i)) for c in dets[i] if c["score"] >= 0.2]
    boxes = [b for b in boxes if tmp.keep_box(b) and vf.dist_m(b) <= tmp.MAX_DIST + 1.0]
    boxes.sort(key=lambda b: -b["score"])
    chosen = []
    for b in boxes:
        if all(vf.bev_iou(b, k) <= tmp.DUP_IOU for k in chosen):
            chosen.append(b)
    pts = clouds[i]
    grid = vf_qa.PointGrid([tuple(q) for q in pts.tolist()])
    out = []
    for b in chosen:
        if not ground_fix(b, pts, grid):
            REJECTED.append((name, b, "lơ lửng cao hơn mặt đường (biển hiệu/mái che)"))
            continue
        b["points_in"] = vf_qa.box_stats(b, grid)["inside"]
        if b["points_in"] < tmp.MIN_POINTS or vf.dist_m(b) > tmp.MAX_DIST:
            continue
        why = reject_reason(b, shape_features(pts, b))
        if why:
            REJECTED.append((name, b, why))
            continue
        # lớp theo bảng 4.3 của guideline: bus thường dài 10-12.5 m, Car cao tối đa ~2.1 m (van chở hàng = Truck)
        if b["label"] == "Bus" and b["length"] < 9.5:
            b["label"], b["reason"] = "Truck", b["reason"] + "+bus_ngan_thanh_truck"
        elif b["label"] == "Car" and b["height"] > 2.2:
            b["label"], b["reason"] = "Truck", b["reason"] + "+car_cao_thanh_truck"
        out.append(b)
    out.sort(key=vf.dist_m)
    return out, " | ".join(log)


REJECTED: list = []


KEEP = ("x", "y", "z", "length", "width", "height", "yaw", "label", "score", "n_obs", "moving", "reason", "points_in")


def main(argv=None) -> int:
    vf.configure_utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True)
    ap.add_argument("--frames", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache", default="out/autoref_cache")
    ap.add_argument("--manual", default=str(Path(__file__).with_name("d14_manual_review.json")),
                    help="quyết định thêm tay sau khi soát camera")
    args = ap.parse_args(argv)
    manual = json.loads(Path(args.manual).read_text(encoding="utf-8")) if Path(args.manual).exists() else {"add": []}
    data = Path(args.data)
    seqs = vf.list_sequences(data)
    names = vf_d14.read_frame_list(args.frames)
    model = cp.load(str(CKPT))
    result = {}
    for name in names:
        t0 = time.time()
        boxes, log = autoref_frame(model, data, seqs, name, Path(args.cache))
        for m in manual.get("delete", []):
            if m["frame"] == name:
                near = [b for b in boxes if math.hypot(b["x"] - m["x"], b["y"] - m["y"]) < 1.0]
                if len(near) != 1:
                    raise SystemExit(f"Quyết định xóa tay {m} khớp {len(near)} hộp (cần đúng 1).")
                boxes.remove(near[0])
                REJECTED.append((name, near[0], "xóa tay: " + m["why"]))
        for m in manual.get("add", []):
            if m["frame"] == name:
                boxes.append({**m["box"], "score": 0.0, "reason": "them_tay: " + m["why"]})
        result[name] = [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in b.items() if k in KEEP}
                        for b in boxes]
        by = {}
        for b in boxes:
            by[b["label"]] = by.get(b["label"], 0) + 1
        print(f"{name}: {len(boxes)} hộp {by}  {time.time() - t0:.0f}s   ICP {log}", flush=True)
    meta = {"tool": "tools/d14_autoref.py (CenterPoint nuScenes + TTA + temporal ±3 + ICP + ground snap)",
            "frames": names}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({"meta": meta, "frames": result}, ensure_ascii=False, indent=1), encoding="utf-8")
    rej = Path(args.out).with_suffix(".rejected.txt")
    rej.write_text("".join(f"{n}\t{b['label']}\t{vf.dist_m(b):.1f} m\taz {vf.azimuth_deg(b):.0f}\tscore {b['score']:.2f}\t{why}\n"
                           for n, b, why in REJECTED), encoding="utf-8")
    print(f"Đã ghi {args.out} (loại {len(REJECTED)} hộp, lý do ở {rej})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
