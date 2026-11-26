"""Gọi function Nuclio qua API lambda của CVAT trên một task 3D, rồi so với pre-label offline.

UI "Automatic annotation" của CVAT khóa ô chọn model với task 3D, nên phải gọi thẳng API.
Đọc cuboid về bằng GET /api/jobs/<id>/annotations (không dựa vào export, cvat#9144).
So khớp: một box CVAT "trùng" nếu có box offline cùng lớp, tâm cách <= 0.5 m (ghép 1-1, tham lam).

    CVAT_PASSWORD=... python bonus/nuclio-pp/run_and_compare.py --task-name D14-<ID>-A-nuclio \
        --function pp-<id> --offline d14_<ID>/pred_A.json --threshold 0.1 --out bonus/nuclio-pp/compare.md
"""
import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import vf_common as vf  # noqa: E402


def main() -> int:
    vf.configure_utf8_stdio()
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="http://localhost:8080")
    ap.add_argument("--user", default="quocthang9112")
    ap.add_argument("--task-name", required=True)
    ap.add_argument("--function", required=True)
    ap.add_argument("--offline", required=True)
    ap.add_argument("--threshold", type=float, default=0.1)
    ap.add_argument("--out")
    a = ap.parse_args()
    s = requests.Session()
    s.auth = (a.user, os.environ["CVAT_PASSWORD"])
    api = a.host.rstrip("/") + "/api"

    tasks = [t for t in s.get(f"{api}/tasks", params={"name": a.task_name, "page_size": 100}).json()["results"]
             if t["name"] == a.task_name]
    if len(tasks) != 1:
        raise SystemExit(f"Cần đúng 1 task {a.task_name}, thấy {len(tasks)}")
    task_id = tasks[0]["id"]
    funcs = [f["id"] for f in s.get(f"{api}/lambda/functions").json()]
    print("Function CVAT thấy:", funcs)
    if a.function not in funcs:
        raise SystemExit(f"CVAT chưa thấy function {a.function}")

    t0 = time.time()
    r = s.post(f"{api}/lambda/requests", json={"function": a.function, "task": task_id,
                                               "threshold": a.threshold, "cleanup": True})
    r.raise_for_status()
    rid = r.json()["id"]
    print(f"Request {rid} cho task {task_id}")
    while True:
        st = s.get(f"{api}/lambda/requests/{rid}").json()
        status = st.get("status")
        if status in ("finished", "failed"):
            break
        time.sleep(3)
    print(f"Trạng thái: {status} sau {time.time() - t0:.0f} s", st.get("exc_info") or "")
    if status != "finished":
        return 1

    job_id = s.get(f"{api}/jobs", params={"task_id": task_id}).json()["results"][0]["id"]
    ann = s.get(f"{api}/jobs/{job_id}/annotations").json()
    labels = {lab["id"]: lab["name"] for lab in s.get(f"{api}/labels", params={"task_id": task_id, "page_size": 100}).json()["results"]}
    frames = [vf.frame_name(*vf.parse_frame_name(f["name"])) for f in s.get(f"{api}/tasks/{task_id}/data/meta").json()["frames"]]
    cvat = {f: [] for f in frames}
    for sh in ann["shapes"]:
        cvat[frames[sh["frame"]]].append(vf.cuboid_from_cvat(sh["points"], labels[sh["label_id"]]))
    offline = json.loads(Path(a.offline).read_text(encoding="utf-8-sig"))["frames"]

    lines = ["| Frame | Box CVAT | Box offline | Trùng tâm ≤ 0,5 m (cùng lớp) | Ghi chú |", "|---|---:|---:|---:|---|"]
    tot = [0, 0, 0]
    for f in frames:
        off = offline[f]
        used, hit = set(), 0
        for b in cvat[f]:
            best = min(((math.hypot(b["x"] - o["x"], b["y"] - o["y"]), j) for j, o in enumerate(off)
                        if j not in used and o["label"] == b["label"]), default=(9e9, None))
            if best[0] <= 0.5:
                used.add(best[1])
                hit += 1
        tot = [tot[0] + len(cvat[f]), tot[1] + len(off), tot[2] + hit]
        lines.append(f"| {f} | {len(cvat[f])} | {len(off)} | {hit} | |")
    lines.append(f"| **Tổng** | **{tot[0]}** | **{tot[1]}** | **{tot[2]}** | |")
    table = "\n".join(lines)
    print(table)
    print(f"Job: {a.host}/tasks/{task_id}/jobs/{job_id}")
    if a.out:
        Path(a.out).write_text(table + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
