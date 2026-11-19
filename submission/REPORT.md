# Báo cáo nhóm 30

## 1. Số liệu luyện tập
- F1 theo seed (rule / cross_check / overall): <<seed 30007: ≈ 1.0 / ... / ... (chờ review_log.csv)>>
  - Riêng phần lỗi luật file + detection (`rules_file_det.py` — Tùng):
    - Lô sạch `runs/clean` (`--seed 5 --no-faults`, 50 ảnh): **0 lỗi** (FP = 0).
    - Seed luyện tập `runs/r30007` (250 ảnh): **6 lỗi** (`missing_image`: 2, `wrong_hash`: 1, `bbox_out_of_bounds`: 1, `duplicate_box`: 2, `invalid_class`: 0).
    - Seed thử thêm `runs/r30008` (250 ảnh): **7 lỗi** (`wrong_hash`: 1, `invalid_class`: 2, `bbox_out_of_bounds`: 2, `duplicate_box`: 2, `missing_image`: 0).
  - Riêng phần lỗi luật metadata + panoptic (`rules_meta_pan.py` — Hương):
    - Lô sạch `runs/clean`: **0 lỗi** (FP = 0).
    - Seed luyện tập `runs/r30007`: **5 lỗi** (`scene_leak`: 1, `guideline_mismatch`: 1, `invalid_category_id`: 1, `thing_overlap`: 2).
    - Lô kiểu đề ẩn `runs/opaque77` (`inject_release.py --seed 77 --opaque`: tên ảnh mã hoá, id đánh lại, byte ảnh/mask đổi): **4 lỗi**, mỗi loại 1.
  - Validator đã ghép đủ 9 loại lỗi luật (`validate.py` gọi `rules_file_det` + `rules_meta_pan`): lô sạch 0 lỗi; F1 lỗi luật ≈ 1.0 trên seed 30007, 11, 12, 13 và `opaque77` (`score_findings.py`, F1 làm tròn).
- Số ứng viên trên lô sạch (`--no-faults`): <<...>>; hàng đợi trên seed luyện tập: <<... ảnh>>
- Ngưỡng đã chọn và cách chọn (không dùng `_private`):
  - **Luật file + detection (`rules_file_det.py`):** Chọn theo định nghĩa ở `docs/DELIVERY.md` và kiểm bằng lô sạch `runs/clean` (50 ảnh calib):
    - `BOUND_EPS = 1e-4` (toạ độ chuẩn hoá, tương đương ~0,064 px trên ảnh 640 px): bỏ qua sai số làm tròn 6 chữ số thập phân của nhãn YOLO gốc (trên lô sạch và `r30007`, box sát mép tự nhiên chỉ lệch tối đa ~0,0003 px, không gây FP), nhưng bắt được mọi box tràn mép thật (ở `r30007` tràn ~27,2 px).
    - `DUP_SIZE_TOL_PX = 0.5` và `DUP_SHIFT_MAX_PX = 2.5` (pixel): theo `docs/DELIVERY.md`, `duplicate_box` là box lặp cùng lớp, cùng kích thước, tâm chỉ lệch 1–2 px. Không dùng ngưỡng IoU thấp vì COCO có các cặp vật thật chồng nhau tự nhiên tới IoU ~0,66. Kiểm đồng thời chênh lệch kích thước (`|Δw|·W <= 0.5`, `|Δh|·H <= 0.5`) và độ lệch tâm (`|Δx|·W <= 2.5`, `|Δy|·H <= 2.5`) giúp lô sạch ra 0 FP (cặp box cùng lớp gần nhất trên lô sạch lệch tâm >= 6 px hoặc chênh kích thước >= 2,34 px) mà vẫn bắt đúng 2 cặp box lặp ở `r30007` (cùng kích thước `size_diff = 0`, lệch tâm đúng 1 px và 2 px).
  - **Luật metadata + panoptic (`rules_meta_pan.py`):** ba luật đầu là so khớp chính xác, không có ngưỡng; riêng `thing_overlap` chọn so sánh **không dung sai**.
    - `scene_leak`: gom ảnh theo `scene_id` trong `metadata.json`; cảnh nào có hơn một giá trị `split` thì báo, target là `scene_id`.
    - `guideline_mismatch`: so `guideline_version` của ảnh với cột `guideline` của **job** trong `jobs.csv` (không so với đa số ảnh trong job, vì guideline gốc ghi ở job).
    - `invalid_category_id`: `category_id` của segment không có trong `categories` của `panoptic.json`.
    - `thing_overlap`: đếm pixel từng segment trong mask (id = R + G·256 + B·256², bỏ id 0 là nền), báo khi `area` khai **lớn hơn** số pixel thật. Không đặt dung sai vì đo trực tiếp trên dữ liệu: ở lô sạch cả 643/643 segment có `area` **bằng đúng** số pixel; ở `r30007` 2688/2690 segment bằng đúng, 2 segment còn lại thừa 671 px (23,7% area) và 31 383 px (17,8%); ở `opaque77` 2689/2690 bằng đúng, segment còn lại thừa 17 556 px (26,6%). Không có segment nào `area` nhỏ hơn số pixel. Khoảng cách giữa "bằng đúng" và "thừa hàng trăm pixel" rất xa nên ngưỡng 0 không gây FP; mask là PNG (nén không mất dữ liệu) nên việc đổi byte ở đề ẩn không làm lệch số pixel.
  - **Đối chiếu detection ↔ panoptic:** <<phần của Việt>>

## 2. Vì sao báo hết ứng viên làm F1 giảm?
<<Trả lời bằng số của nhóm.>>

## 3. Quyết định và lineage
<<QC v1 a/b, kết luận, vì sao R-021 phải xem lại hoặc train lại.>>

## 4. Hash chứng minh gì, không chứng minh gì?
<<>>

## 5. Truy vết
<<Tiêu chí tầng a/b, vì sao lấy guideline theo job.>>

## 6. Bug hoặc điểm chưa rõ trong lab (nếu có)
<<>>
