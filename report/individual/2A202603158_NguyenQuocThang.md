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

## 2. Tập A: sửa tay và tune

| Cấu hình | Xóa | Thêm | Sửa | Chi phí |
|---|---:|---:|---:|---:|
| Gốc (`score_thr=0.1`, `min_points=0`) | 80 | 18 | 22 | 53,0 |
| `best_config.json` (`score_thr=0.5`) | 12 | 25 | 15 | 36,1 |

`ref_A.json` có 48 hộp (s02f51: 10, s03f43: 15, s05f27: 23), trong khi pre-label gốc có 110 hộp. Các thay đổi so với `pred_A.json` gồm xóa 80 hộp, thêm 18 hộp bị sót (6 Pedestrian, 5 Cyclist, 5 Car, 2 Truck) và sửa 28 hộp trên CVAT. Trong 28 hộp sửa có cả lật đầu xe và hạ đáy hộp về mặt đường; script không tính hai loại này là "sửa", nên bảng chỉ có 22. Cách tạo nhãn được khai báo ở [mục 6](#6-công-cụ-tự-động-đã-dùng-khai-báo-theo-rulesmd).

- **Tham số đã đổi trong `best_config.json`:** chỉ `score_thr` từ 0,1 lên 0,5. Ở 0,5, ba mức `min_points` (0, 5, 10) cho cùng chi phí 36,1, nên sweep giữ `min_points=0`.
- **Kết quả leave-one-out** (dán từ `scripts/pp_sweep.py`):

  ```
  s02f51: cấu hình chọn {'score_thr': '0.5', 'min_points': '0'} → 6.9 (tốt nhất có thể 6.9)
  s03f43: cấu hình chọn {'score_thr': '0.5', 'min_points': '0'} → 12.7 (tốt nhất có thể 12.6)
  s05f27: cấu hình chọn {'score_thr': '0.5', 'min_points': '0'} → 16.5 (tốt nhất có thể 16.5)
  ```

- **Cấu hình có ổn định không? Vì sao tôi vẫn chọn nó.**
  - Cả ba lượt leave-one-out đều chọn cùng `score_thr=0.5`, và chi phí trên frame bỏ ra bằng hoặc chỉ hơn mức tốt nhất 0,1. Cấu hình này không chỉ hợp với hai frame dùng để chọn.
  - Theo từng frame trong `sweep.csv`, `score_thr=0.5` cũng tốt nhất hoặc gần tốt nhất trên cả 3 frame.
  - Tôi vẫn chọn 0,5 nhưng không tin con số 32% tuyệt đối. Ba frame là ít, và cả ba đều là đường đô thị nhiều cây xanh và bồn hoa.
- **Biên của lưới.** 0,5 nằm ở biên lưới đề cho. Tôi chạy thêm một sweep thăm dò (`score_thr` 0,5–0,8, ghi ra `out/`, không thay `best_config.json`). Chi phí gần như phẳng: 0,65 cho 34,1, 0,6 cho 34,7, 0,8 cho 35,8. Mức chênh 2 điểm trên 3 frame nằm trong nhiễu. Ngoài 0,5, số hộp phải xóa gần 0 nhưng số hộp phải thêm lại tăng (27–29). Tăng ngưỡng thêm không còn lợi rõ, nên tôi giữ cấu hình của sweep chính thức.

## 3. Trước/sau (bước 8)

![so sánh s02f51](../../d14_2A202603158/compare/s02f51.jpg)

*s02f51: trái là cấu hình gốc (xóa 42, thêm 4, sửa 4 → 18,6), phải là `score_thr=0.5` (xóa 3, thêm 4, sửa 4 → 6,9). Xanh lá là hộp đúng, vàng là hộp cần sửa, đỏ là hộp thừa, xanh dương là vật bị sót.*

- **Mức giảm trên tập A.** `scripts/pp_compare.py` báo giảm **32%** công sửa, từ 53,0 xuống 36,1. Theo frame: s02f51 giảm 18,6 → 6,9, s03f43 giảm 15,6 → 12,7, s05f27 giảm 18,8 → 16,5.
- **Dự đoán ở mục 1 đúng phần lớn.**
  - Đúng tham số: `score_thr` là tham số quyết định. Số hộp xóa giảm từ 80 xuống 12, tức bớt 20,4 điểm.
  - Đúng nhận định về `min_points`: nó gần như không tác dụng. Ở ngưỡng 0,1 nó chỉ bớt 1,6 điểm, ở 0,5 thì không đổi gì, vì hộp thừa nằm trên bồn cây dày điểm.
  - Đúng ước lượng ở 0,4: chi phí đo được là 40,3, nằm trong khoảng 40–43 tôi đoán.
  - Sai về mức giảm: tôi đoán 20–25%, thực tế là 32%. Tôi đã ước số hộp đúng bị mất ở 0,5 cao hơn thực tế. Số hộp thêm chỉ tăng 7 (18 → 25), còn số hộp sửa lại giảm 7 (22 → 15), vì vài hộp đúng nhưng lệch đã bị lọc cùng hộp thừa.
  - Ảnh s02f51 cho thấy rõ nhất: gần như toàn bộ hộp đỏ dọc hai hàng cây biến mất, còn hộp xanh dương (vật bị sót) giữ nguyên. Tăng ngưỡng chỉ bớt việc xóa, không giúp gì cho việc thêm.
- **Ghi chú về số trong mục 1.** Mục 1 ghi 53,5 và sửa 23. Đó là số của bản `ref_A.json` đầu tiên, trong đó mọi hộp ghép được đều lấy nguyên kích thước của model tham chiếu. Sau sweep lần đầu, tôi thấy phần lớn lượt "sửa" ở tập B đến từ chênh kích thước Car giữa hai model. Tôi đổi sang cách sửa tối thiểu như người gán nhãn: giữ kích thước nằm trong dung sai ±5%/±10% của guideline mục 2.5, rồi xuất lại `ref_A.json` và chạy lại sweep.
  - Thay đổi rất nhỏ: chi phí gốc 53,5 → 53,0, cấu hình chọn giữ nguyên.
  - Cả hai phiên bản đều nằm trong lịch sử commit (bản 1 ở commit `Thêm sweep, compare, pred_B, ref_B`, bản 2 ở commit `Day 14: bài nộp`). Mục 1 không sửa.

## 4. Tập B

Số đo từ `scripts/pp_prelabel.py --frames d14_2A202603158/frames_B.txt --config d14_2A202603158/best_config.json --gt d14_2A202603158/ref_B.json`:

| Xóa | Thêm | Sửa | Chi phí |
|---:|---:|---:|---:|
| 42 | 90 | 92 | 148,6 |

`ref_B.json` có 209 hộp trên 12 frame: Car 141, Cyclist 29, Pedestrian 23, Truck 11, Bus 5. `pred_B.json` có 161 hộp. Để đối chiếu, cấu hình gốc trên cùng tập B cho xóa 214, thêm 73, sửa 108 → 191,2. Như vậy cấu hình đã chọn giảm khoảng 22% chi phí trên B, ít hơn mức 32% trên A.

- **Loại box tốn công sửa nhất ở tập B: Car**, khoảng 80 điểm trên 148,6, phần lớn do **sửa** (87 hộp).
  - 89 lượt sửa có lý do kích thước. Hộp PointPillars-KITTI ngắn hơn xe thật khoảng 0,2–0,3 m. Ví dụ, chiếc BMW X3 ở s04f54 dài thật khoảng 4,7 m, model cho 4,56 m. Chiếc Skoda Octavia ở s05f27 dài khoảng 4,6–4,7 m, model cho 4,38 m.
  - Có 31 lượt sửa vì lệch tâm. 30/31 lượt lệch theo chiều dọc thân xe, và 18/31 là xe xa trên 25 m bị che đầu hoặc đuôi.
- **Sau Car là Cyclist (31,8 điểm) và Pedestrian (23 điểm).** Gần như toàn bộ là chi phí **thêm**: 27 Cyclist và 23 Pedestrian bị sót. Model KITTI ở ngưỡng 0,5 gần như không giữ được người và xe hai bánh trên dữ liệu VF.
- **Truck và Bus.** 6 Truck và 5 Bus phải thêm tay, 5 hộp Car phải đổi lớp thành Truck, vì KITTI không có hai lớp này.

## 5. Giới hạn

- **Chỉ 3 frame tune**, cùng kiểu đường đô thị nhiều cây xanh. Leave-one-out ổn định nhưng chỉ dựa trên 3 điểm dữ liệu. Mức giảm trên tập B (22%) thấp hơn tập A (32%), đúng như lo ngại về overfit lên tập nhỏ.
- **Model học trên KITTI.** KITTI chỉ có camera phía trước, LiDAR 64 tia và 3 lớp. Model không biết Truck/Bus, bỏ sót nhiều Pedestrian/Cyclist và ước xe ngắn hơn xe thật. Tune ngưỡng chỉ giảm được việc xóa. Phần thêm (90 hộp ở B, chiếm 60% chi phí) không tham số hậu xử lý nào sửa được.
- **Chi phí là công thức `0.3·xóa + 1.0·thêm + 0.5·sửa`, không phải thời gian sửa thật.** Tôi không đo thời gian, nên không quy đổi ra giờ công. "Giảm 32%/22%" chỉ là giảm theo công thức này, trên đúng các frame này.
- **Nhãn tham chiếu không phải ground truth.** Nhãn được tạo bằng một model thứ hai kèm luật lọc và soát ảnh (mục 6). Vì vậy số xóa/thêm/sửa phản ánh khoảng cách giữa PointPillars và nhãn của tôi, có lẫn sai số của chính nhãn đó.
  - Ví dụ: số lượt "sửa kích thước" phụ thuộc quy ước chiều dài hộp. Tôi giữ chiều dài dài hơn vì khớp kích thước công bố của các mẫu xe nhận ra được trên camera, nhưng chưa đối chiếu với nhãn chuẩn của coach.
- **Ngưỡng 50 m và vật thưa điểm.** Một số vật gần 50 m hoặc thưa điểm được ghi là chưa chắc. Theo guideline mục 4, các trường hợp đó là:
  - **LOW_VISIBILITY:** người đứng ở nhà chờ xe buýt ở s01f13, khoảng 27 m phía sau bên phải. Điểm LiDAR dính vào tấm quảng cáo và mái nhà chờ nên không tách được, tôi không vẽ.
  - **LOW_VISIBILITY:** công nhân thứ hai sau hàng rào công trường ở s04f54, không có cụm điểm riêng, không vẽ.
  - **LOW_VISIBILITY:** các "người" đứng yên sau SUV trắng ở s03f43. Camera bị che, điểm chỉ cao dưới 1 m, đúng vị trí thân cây ở s03f53, nên tôi xóa.
  - **UNCERTAIN_CLASS:** van trắng nhỏ đỗ bên trái ở s05f27, đang để Car, có thể là van chở hàng (Truck).
  - **UNCERTAIN_CLASS:** minibus trắng chở khách ở s03f06, đang để Car, có thể là Bus theo guideline.
  - **UNCERTAIN_CLASS / UNCERTAIN_SCOPE:** Bus ở s03f33, khoảng 49,8 m phía sau, sát ngưỡng 50 m. Camera không phân biệt rõ là xe buýt đỏ hay nhà chờ đỏ.
  - **UNCERTAIN_SCOPE:** xe ben xanh phía trước ở s05f15, ứng viên gần nhất ở 51,8 m, nên không vẽ.

## 6. Công cụ tự động đã dùng (khai báo theo RULES.md)

Ngoài pre-label PointPillars của lab, tôi dùng các công cụ sau để tạo đề xuất sửa nhãn trên CVAT. Mã nguồn nằm trong `tools/` của repo này.

1. **`tools/d14_autoref.py`: model thứ hai, độc lập với PointPillars-KITTI.**
   - Dùng CenterPoint pillar (nuScenes, trọng số mmdet3d viết lại bằng PyTorch thuần, tôi đã dùng ở Day 13). Model nhìn 360°, có lớp truck/bus/pedestrian/bicycle/motorcycle, chạy kèm TTA lật trục.
   - Ghép ±3 frame lân cận bằng ICP để sửa hướng theo chuyển động, lấy kích thước trung vị và loại hộp chỉ xuất hiện 1 lần.
   - Kéo đáy hộp về mặt đường.
   - Lọc theo hình dạng điểm: hàng cây và lan can (điểm chạy liên tục ra ngoài hộp, tán cây phía trên), thân cây giả người, Bus/Truck thấp hoặc mỏng. Lớp được chỉnh theo bảng 4.3: Bus ngắn hơn 9,5 m thành Truck, Car cao hơn 2,2 m thành Truck.
   - Mọi hộp bị loại đều có lý do ghi trong file `*.rejected.txt`.
2. **`tools/d14_apply_review.py`: áp đề xuất lên task CVAT như một người sửa.**
   - Xóa hộp không ghép được và thêm hộp bị sót (dạng Shape).
   - Với hộp ghép được, chỉ sửa đúng thuộc tính sai: lớp, tâm lệch trên 0,3 m, hướng lệch trên 10° hoặc ngược đầu, kích thước ngoài dung sai guideline, đáy hộp.
   - `ref_A.json` và `ref_B.json` sau đó được xuất bằng đúng lệnh `scripts/vf_cvat.py reference` của lab. Số hộp khớp số Items trên CVAT.
3. 
   - Đề xuất được vẽ lên 7 camera bằng `tools/d14_render.py` và soát cả 15 frame.
   - Lần soát này phát hiện các lỗi của bộ lọc và tôi đã sửa luật: van xanh bị loại nhầm ở s05f43, xe buýt bị loại nhầm ở s01f13, người đi xe máy bị loại nhầm ở s03f06, Bus/Truck giả trên bồn cây ở s03f33 và s04f54, người giả ở thân cây ở s03f53.
   - Ba trường hợp được thêm hoặc xóa tay, có lý do và tọa độ trong `tools/d14_manual_review.json`: thêm công nhân ở s04f54, thêm người ở nhà chờ xe buýt và xóa hộp Car bao nhà chờ ở s01f13, thêm xe ben (Truck) ở s05f15.
4. **Kiểm định và giới hạn của công cụ.**
   - Trên 10 frame Day 13 của tôi, bản chưa lọc của công cụ trùng gần như toàn bộ bảng A Day 13 (chi phí 3,2), vì bảng A Day 13 cũng làm từ chính model này. Phép kiểm định này vòng tròn, không chứng minh độ đúng.
   - Khi soát ảnh, tôi thấy bảng A Day 13 còn giữ nhiều Truck giả trên hàng cây, ví dụ ở s02f46. Vì vậy tôi không dùng nó làm thước đo, và bộ lọc mới loại thêm các hộp đó.

## 7. Điểm cộng

### Hướng 2: PointPillars chạy trong CVAT (Nuclio), đã chạy được

Chi tiết, các bước và lệnh nằm ở [`bonus/nuclio-pp/README.md`](../../bonus/nuclio-pp/README.md). Video ở [`bonus/nuclio-pp/demo.webm`](../../bonus/nuclio-pp/demo.webm). Function `pp-2a202603158` (Nuclio 1.16.3, PyTorch CPU, dùng `vf_pp` của lab) được CVAT gọi qua `POST /api/lambda/requests` trên task 3D riêng `D14-2A202603158-A-nuclio`. Task này gồm 3 frame tập A; tôi không dùng task nộp bài vì `cleanup` sẽ xóa nhãn.

| Frame | Box CVAT | Box offline (`pred_A.json`) | Trùng tâm ≤ 0,5 m (cùng lớp) |
|---|---:|---:|---:|
| s02f51 | 45 | 48 | 45 |
| s03f43 | 34 | 32 | 31 |
| s05f27 | 28 | 30 | 28 |
| **Tổng** | **107** | **110** | **104** |

Kết quả không giống hệt offline. PCD trong CVAT chỉ giữ intensity dưới dạng mức xám nén log và đã làm tròn, nên `main.py` chỉ đảo ngược ra giá trị xấp xỉ. Chạy cùng handler ngay trên máy với PCD tạo bằng `bin_to_pcd` cho đúng 45/34/28 box như trong CVAT. Như vậy chênh lệch nằm ở intensity, không nằm ở phần tích hợp CVAT.

### Hướng 1: đo thao tác sửa nhãn

**Cách thu dữ liệu.** Tôi tự sửa nhãn trên task riêng `D14-2A202603158-B-telemetry` (task 22, job 22). Task gồm 4 frame tập B với pre-label `best_config` (s01f13, s04f54, s05f00, s05f43), nên sửa ở đây không ảnh hưởng `ref_B.json`. Userscript `bonus/cvat-telemetry-addon.user.js` được nạp tự động vào trình duyệt bằng [`bonus/start_telemetry_session.py`](../../bonus/start_telemetry_session.py), thay cho bước cài Tampermonkey. Script này chỉ đăng nhập và mở job; mọi click và phím là của tôi. Log tải về: [`bonus/telemetry/`](../../bonus/telemetry/). Bảng metric: [`d14_2A202603158/telemetry.csv`](../../d14_2A202603158/telemetry.csv).

**Mức Cơ bản** (`python bonus/telemetry_metrics.py ... --csv d14_2A202603158/telemetry.csv`):

| Click trên canvas | Phím tắt | Độ dài phiên | Trung vị khoảng cách thời gian giữa 2 click | Khoảng cách chuột TB giữa 2 click | Tỉ lệ dùng bàn phím | Phím dùng |
|---:|---:|---:|---:|---:|---:|---|
| 89 | 3 | 277 s (≈ 4,6 phút) | 2,0 s | 140 px | 3% | `Ctrl+z` × 2, `Delete` × 1 |

Đã sửa 4 hộp so với pre-label, đo bằng `correction_cost` của lab giữa nhãn cuối của job 22 và `pred_B.json`:

- **xóa 1:** Cyclist thừa ở s01f13, cách 19 m.
- **thêm 2:** hai Car ở s05f43, cách 11 m và 18 m.
- **sửa 1:** dời một Car ở s05f43 khoảng 0,8 m.

Chi phí theo công thức là 2,8. s05f00 chỉ xem, không sửa. **s04f54 tôi chưa mở** (nhảy từ frame 0 sang frame 2), nên không có dữ liệu cho frame này.

**Mức Khá: theo frame và theo đoạn công việc** ([`bonus/telemetry_episodes.py`](../../bonus/telemetry_episodes.py)). Ranh giới đoạn lấy từ dòng thời gian event của CVAT: mở job, `delete:object`, `change:frame`, nút Shape, `draw:object`, `save:job`.

| Đoạn | Giây | Click canvas | Phím tắt |
|---|---:|---:|---:|
| Xóa 1 Cyclist thừa (s01f13): mở job → phím Delete | 63 | 18 | 1 |
| Xem s05f00, không sửa gì | 27 | 14 | 0 |
| Thêm Car #1 (s05f43): vào frame → Shape → căn hộp → Save | 90 | 20 | 1 |
| Thêm Car #2 + dời 1 Car có sẵn (s05f43) | 74 | 25 | 1 |
| Kiểm lại, undo/redo, Save | 28 | 12 | 0 |
| **Tổng** | **282** | **89** | **3** |

- Tôi gần như chỉ dùng chuột: 3% phím tắt, chủ yếu `Ctrl+z` để hoàn tác khi căn hộp lệch.
- Click dày, trung vị 2 giây giữa hai click, phần lớn là xoay và kéo view 3D để nhìn vật.
- Tôi phải chia đoạn bằng tay vì hai lý do: CVAT 3D không ghi `drag/resize` khi chỉnh cuboid (các lần chỉnh chỉ hiện dưới dạng "Changed points" trong undo/redo), và với lượt thêm, phần lớn công nằm *sau* event `draw:object`. Bảng gán tự động của `bonus/telemetry_analysis.py` vì thế không dùng được cho lượt thêm.

**Mức Wow: đối chiếu với trọng số 0,3/1/0,5**

- **Thêm** tốn khoảng **74–90 giây và 20–25 click mỗi hộp**, gồm tìm vật, vẽ, căn trên Top/Side/Front và Save. Đây là thao tác đắt nhất, đúng như trọng số 1,0.
- **Xóa**: bản thân thao tác chỉ là 1 phím `Delete`, rất rẻ so với thêm. Nếu chỉ tính thao tác thì 0,3 còn là *cao*. Nhưng đoạn kết thúc bằng lượt xóa vẫn mất 63 giây và 18 click, vì phải xoay view và đối chiếu để chắc hộp đó là thừa. Đoạn này cũng gồm thời gian làm quen lúc mới mở job. Công của một lượt xóa nằm ở **việc kiểm**, không ở việc bấm.
- **Sửa**: chỉ có 1 lượt, lẫn trong cùng đoạn với lượt thêm thứ hai, nên **không tách riêng được**. Tôi không có cơ sở để xác nhận hay bác bỏ trọng số 0,5.
- **Công thức bỏ sót việc xem.** s05f00 không sửa gì nên chi phí theo công thức bằng 0, nhưng vẫn tốn 27 giây và 14 click để rà 15 hộp. Thời gian đó bằng khoảng 0,3–0,4 lần một lượt thêm.
- **Đề xuất, chỉ là giả thuyết:** giữ thêm = 1,0. Giữ xóa ở 0,3 nếu chỉ tính thao tác, hoặc nâng lên khoảng 0,5–0,7 nếu tính cả công kiểm. Cộng thêm một hạng "rà frame" cố định khoảng 0,3–0,4 cho mỗi frame. Như vậy chi phí sẽ phản ánh rằng pre-label càng sạch thì vẫn tốn công rà, không bao giờ về 0.

**Giới hạn của dữ liệu**, nên không thể xem đây là kết luận:

- Chỉ một người, một phiên khoảng 4,6 phút. Chỉ có 1 lượt xóa, 2 lượt thêm và 1 lượt sửa, và chưa mở s04f54.
- Đoạn đầu tiên gồm cả thời gian làm quen giao diện, nên thời gian của lượt xóa bị thổi phồng.
- Ranh giới đoạn do tôi chia từ dòng thời gian event, không phải đo trực tiếp từng thao tác.
- Hai hộp Car tôi thêm có chiều dài và chiều rộng bị đảo (1,89 × 5,26 m), tức hướng lệch 90°, chưa căn kỹ. Một lượt thêm làm cẩn thận theo guideline sẽ còn tốn hơn, nên 74–90 giây là cận dưới.
- Mức độ quen tay với CVAT 3D ảnh hưởng mạnh tới thời gian. Không quy đổi các số này ra "giờ công tiết kiệm".
