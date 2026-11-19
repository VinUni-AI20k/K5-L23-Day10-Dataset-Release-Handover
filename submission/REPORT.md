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
- **QC v1:** `16/250 = 6.4%` (gồm 14 lỗi luật và 2 lỗi gán nhãn đã xác nhận qua human review, vượt xa ngưỡng `2.0%` = tối đa `5/250` ảnh).
- **Kết luận v1:** **HOLD** (`lab250_79c4d088f4c4`). Sự kiện đã được ghi nhận vào `runs/lineage.jsonl`.
- **Kết luận v2:** **RELEASE** (`lab250_79c4d088f4c4_v2`), gồm `243` ảnh sạch, tách `7` ảnh lỗi detection sang `rework_queue.csv`, giữ nguyên `4` ảnh chỉ lỗi panoptic và ghi chú cho team panoptic; sửa tự động hash, guideline, scene split. Lô v2 liên kết lineage với `parent: lab250_79c4d088f4c4`.
- **Vì sao `R-021` phải xem lại hoặc train lại:** Truy vấn `lineage.py impact --release-id lab250_79c4d088f4c4` trả về `R-021: affected=True action=review_or_retrain`. Training run `R-021` đã hấp thu các nhãn sai lệch và nhiễu từ v1 vào ma trận trọng số mô hình. Việc tạo dataset v2 và đặt trạng thái HOLD cho v1 không làm thay đổi trọng số mạng nơ-ron đã học của `R-021`. Đổi dữ liệu mới không tự sửa mô hình cũ; do đó `R-021` bắt buộc phải được đánh giá lại hoặc tái huấn luyện hoàn toàn trên tập dữ liệu sạch v2.

## 4. Hash chứng minh gì, không chứng minh gì?
- **SHA-256 chứng minh điều gì:**
  1. *Tính toàn vẹn (Integrity):* Chứng minh file ảnh và nhãn không bị biến đổi, cắt xén, lỗi bit hay hỏng hóc trong quá trình lưu trữ và truyền tải.
  2. *Tính bất biến & không ghi đè (Immutability):* Chứng minh phiên bản v1 được giữ nguyên trạng thái gốc, và nhãn v2 không bị can thiệp sửa tay trái quy trình (mọi nhãn trong v2 giữ nguyên byte sha256 so với v1).
  3. *Tính tái lập (Reproducibility):* Đảm bảo tính nhất quán trong lineage MLOps: bất kỳ ai tải lô với cùng mã hash đều nhận được chính xác tập dữ liệu đã kiểm định.
- **SHA-256 KHÔNG chứng minh điều gì:**
  1. *Độ đúng ngữ nghĩa của nhãn (Label Correctness):* Một file chứa nhãn gán sai lớp (`class_swap`, ví dụ gán nhãn `broccoli` cho `boat`) hoặc box lệch (`bbox_drift`) vẫn có mã SHA-256 hợp lệ 100% nếu manifest được tính từ chính file sai đó.
  2. *Chất lượng phân chia dữ liệu (Data Split Quality):* Hash không phát hiện được lỗi logic như rò rỉ dữ liệu cùng cảnh giữa train và val (`scene_leak`) hay vi phạm quy định (`guideline_mismatch`).
  3. *Quyền riêng tư & bảo mật (Privacy/Security):* Hash không thể phân biệt ảnh có chứa khuôn mặt người thật chưa làm mờ hay thông tin nhạy cảm.

## 5. Truy vết
- **Tiêu chí tầng `a` và `b` (`trace.json`):**
  - `tier_a` (4 ảnh): ảnh thuộc các scene nêu trong `incoming/ticket.md`, thuộc job dùng guideline cũ (`v1.2`) trong `jobs.csv`, và có ít nhất 1 box detection thuộc lớp bị đổi quy tắc trong `guideline/changelog.md`.
  - `tier_b` (5 ảnh): các ảnh còn lại toàn lô thỏa điều kiện (job guideline `v1.2`, có box lớp bị đổi quy tắc) nhưng chưa được nhắc trong ticket.
  - `notify` (4 người): mã `annotator` và `reviewer` từ `jobs.csv` của các job chứa ảnh `tier_a` và `tier_b`.
- **Vì sao lấy guideline theo `jobs.csv`:** Trường `guideline_version` trên từng ảnh trong `metadata.json` có thể chính là đối tượng bị lỗi `guideline_mismatch`; `jobs.csv` là nguồn chuẩn ghi phiên bản guideline áp dụng cho cả job.

## 6. Bug hoặc điểm chưa rõ trong lab (nếu có)
- Trên Windows, `sqlite3.connect()` dùng với `with` chỉ commit/rollback chứ không đóng file handle, gây lỗi `PermissionError` khi dọn thư mục tạm trong test; đã khắc phục bằng `@contextmanager` đóng connection tường minh trong `qc_factory_day10/review/review_store.py`.
