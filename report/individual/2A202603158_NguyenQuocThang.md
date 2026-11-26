# Báo cáo Day 14 — Nguyễn Quốc Thắng — 2A202603158

- Mã học viên dùng với `--student`: `2A202603158`
- `seed_tag` trong `frames_A.txt`: `393590736f`
- Tập A: `s02f51`, `s03f43`, `s05f27`. Tập B: `s01f13 s01f31 s01f56 s03f06 s03f33 s03f53 s04f04 s04f26 s04f54 s05f00 s05f15 s05f43`.

## 1. Dự đoán trước sweep (bước 5b)

Viết trước khi chạy `scripts/pp_sweep.py`, chỉ dựa trên ảnh BEV/camera trong `png_A/` và số đo bước 5 của cấu hình gốc trên tập A: **xóa 80, thêm 18, sửa 23 → chi phí 53,5** (GT 48 hộp, dự đoán 110 hộp, khớp 30).

- **Tham số tôi nghĩ giảm công sửa nhiều nhất: `score_thr`, tăng từ 0,1 lên khoảng 0,4–0,5.** `min_points` gần như không giúp.
- **Vì sao.** Tập A thừa hộp nhiều hơn hẳn thiếu hộp. 80/110 hộp phải xóa, tốn 24 điểm (45% chi phí), trong khi thêm 18 hộp tốn 18 điểm. Trên ảnh BEV và camera, hộp thừa tập trung ở ba chỗ:
  - Cyclist và Car "mọc" trên bồn hoa, hàng cây dải phân cách và gốc cây ở s02f51, s05f27. Riêng s02f51 có 16 Cyclist dự đoán, nhưng tôi chỉ giữ 1.
  - Các hộp Cyclist vỡ vụn bên trong chiếc SUV trắng chạy sát xe ở s03f43.
  - Hộp Car trên hàng rào cây phía xa.

  Các hộp thừa này có điểm tin cậy thấp: trung vị 0,37, 49/80 hộp dưới 0,4 và 68/80 hộp dưới 0,5. Hộp đúng có trung vị 0,89, chỉ 4/30 hộp dưới 0,4 và 7/30 hộp dưới 0,5. Ngược lại, hộp thừa lại **nhiều điểm LiDAR** (trung vị 66 điểm) vì bồn cây và hàng rào cho điểm dày. Chỉ 7/80 hộp thừa có dưới 10 điểm, nên `min_points=5` hoặc `10` chỉ bớt được vài hộp.
- **Ước lượng.** Ở `score_thr=0.4`, bớt khoảng 49 hộp thừa giảm chừng 14,7 điểm. Đổi lại, khoảng 4 hộp đúng mất đi và thành hộp phải thêm, tăng chừng 4 điểm. Chi phí có thể giảm còn khoảng 40–43. Ở `0.5`, số hộp xóa bớt nhiều hơn (68) nhưng mất khoảng 7 hộp đúng, nên kết quả có thể ngang hoặc tốt hơn `0.4` một chút. Tôi đoán cấu hình tốt nhất sẽ là `score_thr` 0,4 hoặc 0,5 với `min_points` 0 hoặc 5, giảm khoảng 20–25% chi phí.
- **Điều tôi chưa chắc.** Lọc điểm chạy trước bước gộp NMS giữa 4 lượt xoay. Khi tăng ngưỡng, một số hộp khác có thể còn lại sau khi gộp, nên con số thực có thể lệch ước lượng.
