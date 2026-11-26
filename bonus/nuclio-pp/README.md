# Bonus hướng 2: PointPillars chạy bên trong CVAT (Nuclio)

**Kết quả: chạy được.** CVAT gọi function `pp-2a202603158` qua API lambda trên task 3D `D14-2A202603158-A-nuclio` (task 21). Đây là task riêng gồm 3 frame tập A. Tôi không chạy trên task 19/20 vì `cleanup` sẽ xóa nhãn nộp bài. Function tự sinh 107 cuboid trong 15 giây.

- Video: [`demo.webm`](demo.webm), khoảng 1 phút. Video gồm trang **Models** có function, trang task, rồi job 3D qua 3 frame với Items 45, 34, 28.
- Thư mục function: [`bonus/nuclio-pp/`](.). Các file chính:
  - `main.py`: handler, đọc PCD và đảo ngược intensity.
  - `function.yaml`: cấu hình function.
  - `assemble.py`: ghép `vf_pp/`, mã upstream và trọng số vào thư mục build. Đề cấm commit `third_party/`, nên các phần này không nằm trong repo.
  - `run_and_compare.py`: gọi API và so khớp.
  - `record_demo.py`: quay video.

## So khớp với `pred_A.json` offline

Cả hai cùng cấu hình gốc, `threshold`/`score_thr` = 0,1. Một box CVAT tính là "trùng" nếu có box offline cùng lớp, tâm cách tối đa 0,5 m, ghép 1-1. Cuboid được đọc bằng `GET /api/jobs/21/annotations`, không qua export (tránh lỗi cvat#9144).

| Frame | Box CVAT | Box offline | Trùng tâm ≤ 0,5 m (cùng lớp) | Ghi chú |
|---|---:|---:|---:|---|
| s02f51 | 45 | 48 | 45 | lệch do intensity xấp xỉ |
| s03f43 | 34 | 32 | 31 | lệch do intensity xấp xỉ |
| s05f27 | 28 | 30 | 28 | lệch do intensity xấp xỉ |
| **Tổng** | **107** | **110** | **104** | |

104/107 box của CVAT trùng box offline. Kết quả **không giống hệt**, và nguyên nhân đã kiểm chứng được:

- PCD lab đưa lên CVAT không còn intensity gốc. Nó chỉ chứa mức xám `g = 40 + 215·min(1, log1p(v)/log1p(50))`, làm tròn xuống số nguyên.
- `main.py` đảo ngược thành `v = expm1((g−40)/215·log1p(50))`, nên chỉ được giá trị xấp xỉ.
- Tôi chạy đúng `handler` này ngay trên máy, với PCD tạo bằng `vf_common.bin_to_pcd`. Số box từng frame ra giống hệt bản trong CVAT (45/34/28). Như vậy toàn bộ chênh lệch đến từ intensity, không phải từ phần tích hợp CVAT.

## Các bước đã làm

1. **Bật serverless.** Chạy lại CVAT kèm `components/serverless/docker-compose.serverless.yml` (dashboard `quay.io/nuclio/dashboard:1.16.3-amd64`). Task cũ vẫn giữ nguyên. Dashboard không publish cổng 8070 ra máy, chỉ nằm trong mạng docker.
2. **`nuctl` 1.16.3.** Windows chặn chạy file `.exe` tải về, và tôi không gỡ chốt an toàn đó. Thay vào đó, tôi chạy bản `nuctl` **Linux** bên trong container `docker:27-cli` có mount `/var/run/docker.sock`. Đây vẫn là `--platform local` như hướng dẫn:

   ```
   MSYS_NO_PATHCONV=1 docker run --rm -v <thư mục nuctl>:/opt/nuctl:ro -v //var/run/docker.sock:/var/run/docker.sock \
     -v <repo>/out/nuclio-pp-build:/fn:ro docker:27-cli sh -c "cp /opt/nuctl/nuctl /usr/local/bin/ && \
     nuctl create project cvat --platform local; \
     nuctl deploy --project-name cvat --path /fn --file /fn/function.yaml --platform local"
   ```

   Build image mất khoảng 2 phút, phần lớn là cài torch CPU. Function đạt trạng thái `ready`.
3. **Gọi API.** Ô chọn model trong hộp thoại Automatic annotation bị khóa với task 3D, nên tôi gọi thẳng `POST /api/lambda/requests {"function": "pp-2a202603158", "task": 21, "threshold": 0.1, "cleanup": true}`, rồi theo dõi `GET /api/lambda/requests/<id>` đến khi `finished`.

## Ghi chú

- Mọi label trong `spec` của `function.yaml` trùng tên label của task (Car, Truck, Bus, Cyclist, Pedestrian), nên không cần `mapping`.
- `maxRequestBodySize` được đặt 32 MB. PCD khoảng 1 MB một frame, sau base64 còn lớn hơn.
- `eventTimeout` là 300 s, model nạp một lần trong `init_context`.
- Nuclio mở cổng HTTP của function ra máy (`0.0.0.0:57049`). Làm xong nên xóa function bằng `nuctl delete function pp-2a202603158 --platform local`, hoặc tắt CVAT.
- Mật khẩu CVAT chỉ đọc từ biến môi trường `CVAT_PASSWORD`. Mật khẩu không nằm trong file, và trong video chỉ hiện dạng dấu chấm.
