"""Phân tích log thao tác sửa nhãn (bonus hướng 1, mức Khá/Wow).

Nguồn event: ClickHouse của CVAT local (bảng cvat.events). Ở đây có cả event gốc của CVAT
(draw:object, delete:object, drag:object, resize:object, change:frame, save:job...) lẫn event do
bonus/cvat-telemetry-addon.user.js gửi lên /api/events (canvas-click, keydown). Nếu có file
d14-telemetry-job*.json tải từ trình duyệt thì gộp thêm, bỏ trùng.

Cách gán công cho từng thao tác: event thêm/xóa/sửa chia phiên thành các đoạn. Thời gian, click và
phím tắt nằm giữa thao tác trước (hoặc lúc mở frame) và một thao tác được tính cho thao tác đó.
Khoảng nghỉ dài hơn --idle giây bị cắt bớt. Các lượt drag/resize liên tiếp trên cùng một object,
cách nhau dưới --merge giây, gộp thành một lượt "sửa".

    python bonus/telemetry_analysis.py --job 22 [--log d14-telemetry-job22-*.json] \
        [--host http://localhost:8080 --pred d14_<ID>/pred_B.json] --out d14_<ID>/telemetry_analysis.md
Có --pred thì đọc nhãn cuối của job qua API và tính xóa/thêm/sửa theo đúng công thức của lab.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import vf_common as vf  # noqa: E402

ACTION = {"draw:object": "thêm", "paste:object": "thêm", "delete:object": "xóa",
          "drag:object": "sửa", "resize:object": "sửa"}


def ts(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T")).timestamp()


def clickhouse_events(job: int) -> list[dict]:
    q = ("SELECT scope, obj_name, obj_val, obj_id, toString(timestamp) AS timestamp, payload FROM cvat.events "
         f"WHERE job_id = {int(job)} ORDER BY timestamp FORMAT JSONEachRow")
    out = subprocess.run(["docker", "exec", "cvat_clickhouse", "clickhouse-client", "--query", q],
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def load_events(job: int, logs: list[str]) -> list[dict]:
    evs = clickhouse_events(job)
    seen = {(e["scope"], e.get("obj_name"), round(ts(e["timestamp"] + ("Z" if "+" not in e["timestamp"] else "")), 2))
            for e in evs}
    for path in logs:
        for e in json.loads(Path(path).read_text(encoding="utf-8")):
            key = (e["scope"], e.get("obj_name"), round(ts(e["timestamp"]), 2))
            if key not in seen:
                evs.append(e)
                seen.add(key)
    for e in evs:
        t = e["timestamp"]
        e["t"] = ts(t if ("Z" in t or "+" in t) else t + "Z")
        e["p"] = json.loads(e["payload"]) if e.get("payload") else {}
    return sorted(evs, key=lambda e: e["t"])


def analyse(evs: list[dict], idle: float, merge: float):
    frame, start = 0, None
    per_frame = defaultdict(lambda: {"clicks": 0, "keys": 0, "seconds": 0.0, "thêm": 0, "xóa": 0, "sửa": 0})
    actions = []          # (kind, frame, seconds, clicks, keys)
    keys_used = defaultdict(int)
    clicks = keys = 0
    last_t = None
    last_edit = None      # (obj_id, t, index in actions)
    for e in evs:
        if last_t is not None:
            dt = min(e["t"] - last_t, idle)
            per_frame[frame]["seconds"] += dt
        last_t = e["t"]
        if start is None:
            start = e["t"]
        if e["scope"] == "change:frame":
            frame = e["p"].get("to", frame)
            start, clicks, keys, last_edit = e["t"], 0, 0, None
            continue
        if e.get("obj_name") == "canvas-click":
            clicks += 1
            per_frame[frame]["clicks"] += 1
            continue
        if e.get("obj_name") == "keydown":
            keys += 1
            per_frame[frame]["keys"] += 1
            keys_used[e.get("obj_val") or "?"] += 1
            continue
        kind = ACTION.get(e["scope"])
        if not kind:
            continue
        span = min(e["t"] - start, idle)
        if (kind == "sửa" and last_edit and last_edit[0] == e.get("obj_id")
                and e["t"] - last_edit[1] < merge):
            k, f, s0, c0, k0 = actions[last_edit[2]]
            actions[last_edit[2]] = (k, f, s0 + span, c0 + clicks, k0 + keys)
            last_edit = (e.get("obj_id"), e["t"], last_edit[2])
        else:
            actions.append((kind, frame, span, clicks, keys))
            per_frame[frame][kind] += 1
            last_edit = (e.get("obj_id"), e["t"], len(actions) - 1) if kind == "sửa" else None
        start, clicks, keys = e["t"], 0, 0
    return per_frame, actions, keys_used


def final_costs(host: str, job: int, pred_path: str) -> dict:
    import requests
    from vf_pp.core import correction_cost
    s = requests.Session()
    s.auth = (os.environ.get("CVAT_USER", "quocthang9112"), os.environ["CVAT_PASSWORD"])
    api = host.rstrip("/") + "/api"
    job_info = s.get(f"{api}/jobs/{job}").json()
    task = job_info["task_id"]
    labels = {lab["id"]: lab["name"] for lab in s.get(f"{api}/labels", params={"task_id": task, "page_size": 100}).json()["results"]}
    frames = [vf.frame_name(*vf.parse_frame_name(f["name"])) for f in s.get(f"{api}/tasks/{task}/data/meta").json()["frames"]]
    final = {f: [] for f in frames}
    for sh in s.get(f"{api}/jobs/{job}/annotations").json()["shapes"]:
        final[frames[sh["frame"]]].append(vf.cuboid_from_cvat(sh["points"], labels[sh["label_id"]]))
    pred = json.loads(Path(pred_path).read_text(encoding="utf-8-sig"))["frames"]
    return {i: (f, correction_cost(final[f], pred[f])) for i, f in enumerate(frames)}


def med(xs):
    return round(statistics.median(xs), 1) if xs else None


def main() -> int:
    vf.configure_utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--job", type=int, required=True)
    ap.add_argument("--log", action="append", default=[])
    ap.add_argument("--host", default="http://localhost:8080")
    ap.add_argument("--pred")
    ap.add_argument("--idle", type=float, default=90.0, help="cắt khoảng nghỉ dài hơn (giây)")
    ap.add_argument("--merge", type=float, default=20.0, help="gộp drag/resize cùng object trong (giây)")
    ap.add_argument("--out")
    a = ap.parse_args()
    evs = load_events(a.job, a.log)
    if not evs:
        raise SystemExit(f"Không có event nào của job {a.job}.")
    per_frame, actions, keys_used = analyse(evs, a.idle, a.merge)
    n_click = sum(1 for e in evs if e.get("obj_name") == "canvas-click")
    lines = [f"# Phân tích thao tác: job {a.job}", "",
             f"{len(evs)} event, {n_click} click trên canvas, "
             f"{sum(1 for e in evs if e.get('obj_name') == 'keydown')} phím tắt, "
             f"từ {datetime.fromtimestamp(evs[0]['t']):%H:%M:%S} đến {datetime.fromtimestamp(evs[-1]['t']):%H:%M:%S}.", ""]
    if n_click == 0:
        lines += ["> Chưa có event của userscript (canvas-click/keydown) trong job này: chỉ có thời gian, chưa có số click.", ""]
    costs = final_costs(a.host, a.job, a.pred) if a.pred else {}
    lines += ["## Theo frame (mỗi frame một phiên)", "",
              "| Frame | Giây làm (cắt nghỉ) | Click | Phím | Thêm/Xóa/Sửa (event) | Xóa/Thêm/Sửa theo công thức lab | Chi phí |",
              "|---|---:|---:|---:|---|---|---:|"]
    for fi in sorted(per_frame):
        p = per_frame[fi]
        name, c = costs.get(fi, (str(fi), None))
        lab = f"{c['delete']}/{c['add']}/{c['edit']}" if c else ""
        lines.append(f"| {name} | {p['seconds']:.0f} | {p['clicks']} | {p['keys']} | {p['thêm']}/{p['xóa']}/{p['sửa']} | {lab} | {c['cost'] if c else ''} |")
    lines += ["", "## Theo loại thao tác", "",
              "| Thao tác | Số lượt | Giây (trung vị) | Click (trung vị) | Phím (trung vị) | Tỉ lệ thời gian so với thêm | Trọng số lab |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    by = defaultdict(list)
    for kind, _f, s, c, k in actions:
        by[kind].append((s, c, k))
    base = med([x[0] for x in by.get("thêm", [])])
    for kind, w in (("thêm", 1.0), ("xóa", 0.3), ("sửa", 0.5)):
        xs = by.get(kind, [])
        m = med([x[0] for x in xs])
        ratio = f"{m / base:.2f}" if (m is not None and base) else ""
        lines.append(f"| {kind} | {len(xs)} | {m if m is not None else ''} | {med([x[1] for x in xs]) or 0} | "
                     f"{med([x[2] for x in xs]) or 0} | {ratio} | {w} |")
    if keys_used:
        top = sorted(keys_used.items(), key=lambda kv: -kv[1])[:10]
        lines += ["", "Phím tắt dùng nhiều nhất: " + ", ".join(f"`{k}` × {v}" for k, v in top)]
    text = "\n".join(lines) + "\n"
    print(text)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
