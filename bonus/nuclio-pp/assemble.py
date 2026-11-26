"""Ghép thư mục build cho Nuclio: main.py + function.yaml + vf_pp/ + mã upstream PointPillars + trọng số.

Nuclio chỉ build những gì nằm trong thư mục function. Đề cấm commit third_party/, nên repo chỉ giữ
main.py/function.yaml; script này chép phần còn lại vào out/nuclio-pp-build/ (đã .gitignore).

    python bonus/nuclio-pp/assemble.py
"""
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / "out" / "nuclio-pp-build"
UP = ROOT / "third_party" / "PointPillars"

if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)
for name in ("main.py", "function.yaml"):
    shutil.copy(HERE / name, OUT / name)
shutil.copytree(ROOT / "vf_pp", OUT / "vf_pp", ignore=shutil.ignore_patterns("__pycache__"))
shutil.copytree(UP / "pointpillars" / "model", OUT / "third_party" / "PointPillars" / "pointpillars" / "model",
                ignore=shutil.ignore_patterns("__pycache__"))
(OUT / "third_party" / "PointPillars" / "pretrained").mkdir(parents=True)
shutil.copy(UP / "pretrained" / "epoch_160.pth", OUT / "third_party" / "PointPillars" / "pretrained" / "epoch_160.pth")
shutil.copy(UP / "LICENSE", OUT / "third_party" / "PointPillars" / "LICENSE")
print("Đã ghép", OUT, sum(1 for _ in OUT.rglob("*") if _.is_file()), "file")
