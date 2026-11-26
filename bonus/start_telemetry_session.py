"""Mở một cửa sổ Chrome (có giao diện) để NGƯỜI sửa nhãn, với userscript đo thao tác gắn sẵn.

Thay cho bước cài Tampermonkey: script bonus/cvat-telemetry-addon.user.js được nạp qua add_init_script,
nên nó ghi đúng các event như khi cài bằng Tampermonkey (click trên canvas, phím tắt) và gửi lên
/api/events. Cứ 20 giây log của phiên được tải về bonus/telemetry/ (ghi đè bản trước của cùng phiên).
Script KHÔNG tự click hay sửa gì: chỉ đăng nhập, mở job, rồi chờ người dùng đóng cửa sổ.

    CVAT_PASSWORD=... <python có playwright> bonus/start_telemetry_session.py --task 22 --job 22
"""
import argparse
import os
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--host", default="http://localhost:8080")
ap.add_argument("--user", default="quocthang9112")
ap.add_argument("--task", type=int, required=True)
ap.add_argument("--job", type=int, required=True)
a = ap.parse_args()

out = HERE / "telemetry"
out.mkdir(exist_ok=True)
userscript = (HERE / "cvat-telemetry-addon.user.js").read_text(encoding="utf-8")
stamp = time.strftime("%Y%m%d-%H%M%S")
saved = out / f"d14-telemetry-job{a.job}-{stamp}.json"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, args=["--start-maximized"])
    ctx = browser.new_context(no_viewport=True, accept_downloads=True)
    ctx.add_init_script(userscript)            # chạy ở mỗi lần tải trang; tự bỏ qua nếu không ở trang job
    pg = ctx.new_page()
    pg.on("download", lambda d: d.save_as(str(saved)))
    pg.goto(f"{a.host}/auth/login")
    pg.wait_for_timeout(2500)
    pg.locator("input").first.fill(a.user)
    pg.fill("input[type=password]", os.environ["CVAT_PASSWORD"])
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(4000)
    pg.goto(f"{a.host}/tasks/{a.task}/jobs/{a.job}")   # tải trực tiếp trang job để userscript được nạp
    print(f"Đã mở job {a.job}. Sửa nhãn trong cửa sổ Chrome, bấm Save, rồi ĐÓNG cửa sổ khi xong.", flush=True)
    last = 0.0
    while not pg.is_closed():
        try:
            pg.wait_for_timeout(1000)
            if time.time() - last > 20:
                n = pg.evaluate("window.__d14Telemetry ? (__d14Telemetry.flush(), __d14Telemetry.count()) : -1")
                if n and n > 0:
                    pg.evaluate("__d14Telemetry.download()")
                last = time.time()
        except Exception:
            break
    try:
        browser.close()
    except Exception:
        pass
print("Phiên kết thúc. Log:", saved if saved.exists() else "(chưa có event nào được lưu)", flush=True)
