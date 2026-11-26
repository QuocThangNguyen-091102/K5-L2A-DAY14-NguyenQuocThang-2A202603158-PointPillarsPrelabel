"""Vẽ hộp từ một file JSON (pred/ref/đề xuất) lên 7 camera + BEV, để người kiểm xem nhanh.

    python tools/d14_render.py --data <Data-VF> --boxes out/autoref_A.json --out out/review_A [--frames s03f43]
"""
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import vf_common as vf, vf_d14, vf_qa  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--data", required=True); ap.add_argument("--boxes", required=True)
ap.add_argument("--out", required=True); ap.add_argument("--frames")
a = ap.parse_args()
vf.configure_utf8_stdio()
doc = json.loads(Path(a.boxes).read_text(encoding="utf-8-sig"))["frames"]
names = vf_d14.read_frame_list(a.frames) if a.frames else list(doc)
out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
calibs = {}
for row in vf_d14.frame_rows(Path(a.data), names):
    if row["seq"] not in calibs:
        calibs[row["seq"]] = vf_qa.load_calib(Path(a.data) / f"sequence_{row['seq']:02d}")
    boxes = [dict(b, idx=k) for k, b in enumerate(doc[row["name"]])]
    sheet, _ = vf_qa.render_frame(row, boxes, calibs[row["seq"]])
    sheet.save(out / f"{row['name']}.jpg", quality=85)
    print(out / f"{row['name']}.jpg", len(boxes))
