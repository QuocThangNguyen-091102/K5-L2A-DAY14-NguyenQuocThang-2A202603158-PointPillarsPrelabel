"""Quay video ngắn (Playwright): trang Models có function pp-<id>, rồi job 3D với cuboid do function sinh, qua 3 frame.

    CVAT_PASSWORD=... <python có playwright> bonus/nuclio-pp/record_demo.py --task 21 --job 21 --out bonus/nuclio-pp/demo.webm
Mật khẩu chỉ đọc từ biến môi trường, không ghi ra file hay video.
"""
import argparse
import os
import shutil
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument("--host", default="http://localhost:8080")
ap.add_argument("--user", default="quocthang9112")
ap.add_argument("--task", type=int, required=True)
ap.add_argument("--job", type=int, required=True)
ap.add_argument("--frames", type=int, default=3)
ap.add_argument("--out", required=True)
a = ap.parse_args()

size = {"width": 1600, "height": 900}
tmp = Path(tempfile.mkdtemp())
with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport=size, record_video_dir=str(tmp), record_video_size=size)
    pg = ctx.new_page()
    pg.goto(f"{a.host}/auth/login")
    pg.wait_for_timeout(2500)
    pg.locator("input").first.fill(a.user)
    pg.fill("input[type=password]", os.environ["CVAT_PASSWORD"])
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(4000)
    pg.goto(f"{a.host}/models")                       # function xuất hiện trong trang Models
    pg.wait_for_timeout(5000)
    pg.goto(f"{a.host}/tasks/{a.task}")               # task 3D đích
    pg.wait_for_timeout(4000)
    pg.goto(f"{a.host}/tasks/{a.task}/jobs/{a.job}?frame=0")
    pg.wait_for_timeout(15000)
    cx, cy = 510, 380                                  # giữa khung 3D (perspective)

    def zoom_in():
        pg.mouse.move(cx, cy)
        for _ in range(5):
            pg.mouse.wheel(0, -120)
            pg.wait_for_timeout(150)

    zoom_in()
    pg.wait_for_timeout(5000)
    for _ in range(a.frames - 1):
        pg.mouse.click(cx, cy)                         # focus canvas
        pg.keyboard.press("f")                        # frame kế tiếp
        pg.wait_for_timeout(4000)
        zoom_in()
        pg.wait_for_timeout(5000)
    video = pg.video.path()
    ctx.close()
    browser.close()
shutil.move(video, a.out)
shutil.rmtree(tmp, ignore_errors=True)
print("Đã ghi", a.out, f"{Path(a.out).stat().st_size / 1e6:.1f} MB")
