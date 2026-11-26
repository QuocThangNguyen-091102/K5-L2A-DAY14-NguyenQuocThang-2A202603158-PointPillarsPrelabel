"""Áp đề xuất sửa của tools/d14_autoref.py lên task CVAT D14-<ID>-A/B (khai báo theo RULES.md).

Với từng frame, ghép 1-1 (Hungarian, BEV IoU >= 0.3, cùng hàm match_boxes của lab) hộp đang có trên
CVAT với hộp đề xuất, rồi làm đúng 3 thao tác của người sửa nhãn:

* hộp CVAT không ghép được          -> XÓA (hộp thừa)
* ghép được                         -> SỬA TỐI THIỂU như người gán nhãn: giữ hộp đang có, chỉ đổi đúng
  thuộc tính sai so với đề xuất (giữ pp_id, note=auto-edit):
    - lớp khác                        -> lấy lớp đề xuất
    - tâm lệch > 0.3 m                -> lấy tâm đề xuất
    - hướng lệch > 10° hoặc ngược đầu -> lấy hướng đề xuất (đề xuất có hướng theo chuyển động)
    - kích thước ngoài dung sai guideline mục 2.5 (±5% xe, ±10% người/xe 2 bánh) -> lấy kích thước đề xuất
    - đáy hộp lệch mặt đường đề xuất > 0.15 m -> hạ/nâng đáy về mặt đường
  Kích thước trong dung sai thì giữ: hai model có quy ước kích thước khác nhau (CenterPoint/nuScenes dài
  hơn PointPillars/KITTI ~0.3 m), người kiểm không kéo lại hộp đã vừa trong dung sai.
* đề xuất không ghép được           -> THÊM cuboid dạng Shape (note=auto-add)

Hộp không cần đổi gì thì giữ nguyên. Sau đó người kiểm mở CVAT xem lại rồi xuất bằng
``scripts/vf_cvat.py reference``. Mặc định chạy thử; thêm --apply để ghi lên CVAT.

    CVAT_PASSWORD=... python tools/d14_apply_review.py --student <ID> --task A --proposal out/autoref_A.json \
        --host http://localhost:8080 --user <ten> [--apply]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import vf_common as vf  # noqa: E402
from scripts.vf_cvat import connect, cuboid_points, d14_task_name, find_tasks  # noqa: E402
import math  # noqa: E402

TOL = {"Car": 0.05, "Truck": 0.05, "Bus": 0.05, "Pedestrian": 0.10, "Cyclist": 0.10}  # guideline mục 2.5


def minimal_fix(cur: dict, prop: dict) -> dict | None:
    """Hộp sau khi sửa tối thiểu, hoặc None nếu không cần đổi gì."""
    new = dict(cur)
    if cur["label"] != prop["label"]:
        new["label"] = prop["label"]
    if math.hypot(cur["x"] - prop["x"], cur["y"] - prop["y"]) > 0.3:
        new["x"], new["y"] = prop["x"], prop["y"]
    dyaw = abs((cur["yaw"] - prop["yaw"] + math.pi) % (2 * math.pi) - math.pi)   # có tính lật đầu 180°
    if dyaw > math.radians(10):
        new["yaw"] = prop["yaw"]
    tol = TOL[prop["label"]]
    if any(abs(cur[k] - prop[k]) > tol * prop[k] for k in ("length", "width", "height")):
        new["length"], new["width"], new["height"] = prop["length"], prop["width"], prop["height"]
    bottom, prop_bottom = cur["z"] - cur["height"] / 2, prop["z"] - prop["height"] / 2
    if abs(bottom - prop_bottom) > 0.15 or new["height"] != cur["height"]:
        new["z"] = prop_bottom + new["height"] / 2
    changed = any(new[k] != cur[k] for k in ("label", "x", "y", "z", "yaw", "length", "width", "height"))
    return new if changed else None


def main(argv=None) -> int:
    vf.configure_utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--student", required=True)
    ap.add_argument("--task", choices=["A", "B"], required=True)
    ap.add_argument("--proposal", required=True, help="JSON từ tools/d14_autoref.py")
    ap.add_argument("--host", required=True)
    ap.add_argument("--user", required=True)
    ap.add_argument("--org")
    ap.add_argument("--apply", action="store_true", help="ghi thật lên CVAT (mặc định chỉ in kế hoạch)")
    args = ap.parse_args(argv)

    from cvat_sdk import models
    from cvat_sdk.core.proxies.annotations import AnnotationUpdateAction

    proposal = json.loads(Path(args.proposal).read_text(encoding="utf-8-sig"))["frames"]
    name = d14_task_name(args.student, args.task)
    client = connect(args.host, args.user, args.org)
    tasks = find_tasks(client, name)
    if len(tasks) != 1:
        raise SystemExit(f"Cần đúng 1 task {name}, thấy {len(tasks)}.")
    task = tasks[0]
    jobs = task.get_jobs()
    if len(jobs) != 1:
        raise SystemExit(f"{name}: cần đúng 1 job, thấy {len(jobs)}.")
    job = client.jobs.retrieve(jobs[0].id)
    labels = {lab.name: lab for lab in task.get_labels()}
    label_name = {lab.id: lab.name for lab in labels.values()}
    frames = [vf.frame_name(*vf.parse_frame_name(f.name)) for f in task.get_meta().frames]
    missing = [f for f in frames if f not in proposal]
    if missing:
        raise SystemExit(f"{args.proposal} thiếu frame {missing}.")
    ann = job.get_annotations()
    if ann.tracks:
        raise SystemExit(f"{name} có Track; chỉ xử lý Shape.")

    def attrs(label: str, old: dict[str, str], note: str):
        spec = {a.name: a.id for a in labels[label].attributes}
        vals = {"pp_id": old.get("pp_id", ""), "score": old.get("score", ""), "warn": old.get("warn", ""), "note": note}
        return [models.AttributeValRequest(spec_id=spec[k], value=v) for k, v in vals.items() if k in spec]

    to_delete, to_update, to_create, plan = [], [], [], Counter()
    for fi, frame in enumerate(frames):
        shapes = [s for s in ann.shapes if s.frame == fi and getattr(s.type, "value", str(s.type)) == "cuboid"]
        cur = [vf.cuboid_from_cvat(s.points, label_name.get(s.label_id, "?")) for s in shapes]
        prop = proposal[frame]
        pairs = vf.match_boxes(prop, cur, 0.3)
        hit_c = {pj for _, pj, _ in pairs}
        hit_p = {gi for gi, _, _ in pairs}
        n_del = n_edit = n_add = 0
        for j, s in enumerate(shapes):
            if j not in hit_c:
                to_delete.append(s.id)
                n_del += 1
        for gi, pj, _ in pairs:
            p = minimal_fix(cur[pj], prop[gi])
            if p is None:
                continue
            s = shapes[pj]
            old_spec = {a.id: a.name for a in labels[label_name[s.label_id]].attributes}
            old = {old_spec.get(a.spec_id, ""): a.value for a in s.attributes}
            to_update.append(models.LabeledShapeRequest(
                id=s.id, type="cuboid", frame=fi, label_id=labels[p["label"]].id, points=cuboid_points(p),
                occluded=s.occluded, z_order=s.z_order, rotation=0.0, group=s.group or 0, source=str(s.source),
                attributes=attrs(p["label"], old, "auto-edit")))
            n_edit += 1
        for gi, p in enumerate(prop):
            if gi in hit_p:
                continue
            to_create.append(models.LabeledShapeRequest(
                type="cuboid", frame=fi, label_id=labels[p["label"]].id, points=cuboid_points(p),
                occluded=False, z_order=0, rotation=0.0, group=0, attributes=attrs(p["label"], {}, "auto-add")))
            n_add += 1
        plan.update(delete=n_del, edit=n_edit, add=n_add)
        print(f"{frame}: CVAT {len(shapes)} hộp, đề xuất {len(prop)} → xóa {n_del}, sửa {n_edit}, thêm {n_add}, "
              f"giữ nguyên {len(pairs) - n_edit}")
    print(f"TỔNG: xóa {plan['delete']}, sửa {plan['edit']}, thêm {plan['add']}")
    if not args.apply:
        print("Chạy thử: chưa ghi gì. Thêm --apply để ghi lên CVAT.")
        return 0
    if to_delete:
        job.remove_annotations(ids=to_delete)
    for k in range(0, len(to_update), 50):
        job.update_annotations(models.PatchedLabeledDataRequest(shapes=to_update[k:k + 50]),
                               action=AnnotationUpdateAction.UPDATE)
    for k in range(0, len(to_create), 50):
        job.update_annotations(models.PatchedLabeledDataRequest(shapes=to_create[k:k + 50]),
                               action=AnnotationUpdateAction.CREATE)
    after = job.get_annotations()
    per = Counter(frames[s.frame] for s in after.shapes)
    print(f"Đã ghi lên CVAT: {len(after.shapes)} shape, {len(after.tracks)} track: " +
          ", ".join(f"{f}={per[f]}" for f in frames))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
