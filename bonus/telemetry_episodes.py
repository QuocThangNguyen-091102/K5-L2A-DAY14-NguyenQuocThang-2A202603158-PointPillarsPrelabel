"""Đếm thời gian / click / phím theo từng đoạn công việc của phiên sửa nhãn job 22 (bonus hướng 1).

Ranh giới đoạn lấy từ dòng thời gian event của CVAT (load:job, delete:object, change:frame, click nút
Shape, draw:object, save:job) trong ClickHouse. Cần chia tay vì với lượt THÊM, phần lớn công (căn hộp
trên Top/Side/Front, CVAT ghi là "Changed points") nằm SAU event draw:object, còn CVAT 3D không ghi
drag/resize cho các lần chỉnh đó, nên không gán tự động "công trước thao tác" được.

    python bonus/telemetry_episodes.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from telemetry_analysis import load_events, ts  # noqa: E402

JOB = 22
EPISODES = [  # (mô tả, bắt đầu UTC, kết thúc UTC) theo dòng thời gian event
    ("Xóa 1 Cyclist thừa (s01f13): mở job → phím Delete", "16:09:06.038", "16:10:08.719"),
    ("Xem s05f00, không sửa gì", "16:10:10.342", "16:10:37.665"),
    ("Thêm Car #1 (s05f43): vào frame → Shape → căn hộp → Save", "16:10:37.665", "16:12:07.465"),
    ("Thêm Car #2 + dời 1 Car có sẵn (s05f43)", "16:12:07.465", "16:13:21.573"),
    ("Kiểm lại, undo/redo, Save", "16:13:21.573", "16:13:49.561"),
]

evs = load_events(JOB, [])
print("| Đoạn | Giây | Click canvas | Phím tắt |\n|---|---:|---:|---:|")
tot = [0.0, 0, 0]
for name, a, b in EPISODES:
    t0, t1 = ts(f"2026-11-26T{a}Z"), ts(f"2026-11-26T{b}Z")
    seg = [e for e in evs if t0 <= e["t"] < t1]
    c = sum(e.get("obj_name") == "canvas-click" for e in seg)
    k = sum(e.get("obj_name") == "keydown" for e in seg)
    tot = [tot[0] + t1 - t0, tot[1] + c, tot[2] + k]
    print(f"| {name} | {t1 - t0:.0f} | {c} | {k} |")
print(f"| **Tổng** | **{tot[0]:.0f}** | **{tot[1]}** | **{tot[2]}** |")
