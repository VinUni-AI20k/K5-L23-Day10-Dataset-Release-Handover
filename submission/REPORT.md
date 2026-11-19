# Báo cáo Nhóm sIx4Nhd0cTh4n

## 1. Số liệu luyện tập
- **Seed luyện tập:** `9007` (v1 `lab250_79c4d088f4c4`, 250 ảnh); lô sạch đối chứng: `clean` (seed `5`, 50 ảnh).
- **F1 đo trước human review (chỉ lỗi luật):** `overall ≈ 0.8` · `rule_detectable ≈ 1.0` · `cross_check_review ≈ —` (14 lỗi luật phát hiện đúng toàn bộ 9 loại).
- **Số ứng viên trên lô sạch (`--no-faults`, 50 ảnh):** `0` lỗi luật, `7` ứng viên gán nhãn (`class_swap: 1`, `missing_box: 6`); cả 7 ca đều được bộ phân tầng xếp vào nhóm `HARD`.
- **Hàng đợi trên seed `9007` (250 ảnh):** `31` ứng viên (`bbox_drift: 1`, `class_swap: 10`, `instance_merge: 5`, `missing_box: 15`), phân tầng `EASY: 14 / MEDIUM: 3 / HARD: 28`.
- **Ngưỡng đã chọn và cách chọn (không dùng `_private`):**
  - `PAIR_MIN_MASK_IOU = 0.5` (IoU pixel-mask với box detection) để tránh ghép nhầm segment nhỏ nằm trong box lớn.
  - `MISSING_BOX_MIN_FRAC = 0.005` (diện tích segment ≥ 0.5% ảnh) và bỏ qua segment `iscrowd` để giảm báo thừa vật quá nhỏ/bị che.
  - `DUP_SIZE_TOL_PX = 1`, `DUP_CENTER_TOL_PX = 2` cho `duplicate_box` để tách box lặp thật khỏi cặp vật cạnh nhau tự nhiên.

## 2. Vì sao báo hết ứng viên làm F1 giảm?
Trong bộ `clean` (50 ảnh không gài lỗi), vẫn có `7` ứng viên sinh ra do khác biệt tự nhiên của COCO giữa detection và panoptic (che khuất, `iscrowd`, ranh giới mask). Nếu nhận hết toàn bộ `31` ứng viên trên `r9007` mà không xem ảnh, phần chênh lệch là **False Positive (FP)** lớn, kéo **Precision** tụt mạnh và làm **F1** giảm (theo công thức F1, FP bị phạt nặng tương đương FN).

## 3. Quyết định và lineage
- **QC v1:** `14/250 = 5.6%` (tính riêng lỗi luật, đã vượt ngưỡng `2%` = tối đa `5/250` ảnh).
- **Kết luận v1:** **HOLD** (`lab250_79c4d088f4c4`).
- **Vì sao `R-021` phải xem lại hoặc train lại:** Truy vấn `lineage.py impact --release-id lab250_79c4d088f4c4` trả về `R-021: affected=True action=review_or_retrain`. Việc tách/sửa tạo lô v2 (`lab250_79c4d088f4c4_v2`) không tự sửa trọng số mô hình `R-021` đã train trên v1; do đó run `R-021` bắt buộc phải đánh giá lại hoặc train lại trên v2.

## 4. Hash chứng minh gì, không chứng minh gì?
- **SHA-256 chứng minh:** File không bị thay đổi từng byte kể từ lúc lập manifest (`manifest.json` / `manifest.csv` / `.sha256`), đảm bảo tính toàn vẹn lưu trữ và truyền tải.
- **SHA-256 không chứng minh:** Nhãn bên trong có đúng ngữ nghĩa hay không. Một file có nhãn sai (`class_swap`, `bbox_drift`) vẫn có mã SHA-256 khớp 100% nếu manifest được tính từ chính file sai đó.

## 5. Truy vết
- **Tiêu chí tầng `a` và `b` (`trace.json`):**
  - `tier_a` (4 ảnh): ảnh thuộc các scene nêu trong `incoming/ticket.md`, thuộc job dùng guideline cũ (`v1.2`) trong `jobs.csv`, và có ít nhất 1 box detection thuộc lớp bị đổi quy tắc trong `guideline/changelog.md`.
  - `tier_b` (5 ảnh): các ảnh còn lại toàn lô thỏa điều kiện (job guideline `v1.2`, có box lớp bị đổi quy tắc) nhưng chưa được nhắc trong ticket.
  - `notify` (4 người): mã `annotator` và `reviewer` từ `jobs.csv` của các job chứa ảnh `tier_a` và `tier_b`.
- **Vì sao lấy guideline theo `jobs.csv`:** Trường `guideline_version` trên từng ảnh trong `metadata.json` có thể chính là đối tượng bị lỗi `guideline_mismatch`; `jobs.csv` là nguồn chuẩn ghi phiên bản guideline áp dụng cho cả job.

## 6. Bug hoặc điểm chưa rõ trong lab (nếu có)
- Trên Windows, `sqlite3.connect()` dùng với `with` chỉ commit/rollback chứ không đóng file handle, gây lỗi `PermissionError` khi dọn thư mục tạm trong test; đã khắc phục bằng `@contextmanager` đóng connection tường minh trong `qc_factory_day10/review/review_store.py`.
