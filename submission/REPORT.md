# Báo cáo Nhóm — Nhóm LABUBU10 (Day 10 Lab)

## 1. Số liệu luyện tập (Seed 10007)
- **F1 theo seed 10007:**
  - Nhóm lỗi luật (`rule_detectable`): F1 = 1.0 (Bắt trọn vẹn 13 lỗi luật, không có FP, không có FN).
  - Nhóm lỗi gán nhãn (`cross_check_review`): F1 = 1.0 sau khi có review mắt người thẩm định đầy đủ 10/10 lỗi.
  - Tổng thể (`overall`): F1 = 1.0 (23/23 lỗi phát hiện chính xác tuyệt đối).
- **Truy vết ticket team AI (Seed 10007):**
  - `tier_a`: 2 ảnh (`000000008021`, `000000009590`) thuộc `scene_195` và `scene_224`, job guideline cũ v1.2, có nhãn `bottle`.
  - `tier_b`: 4 ảnh (`000000002685`, `000000005193`, `000000006471`, `000000007574`) các cảnh khác cùng điều kiện.
  - `notify`: 5 annotator/reviewer (`A04`, `A05`, `Q01`, `Q02`, `Q03`).
- **Số ứng viên trên lô sạch (`--no-faults`):** Khoảng 8–12 ứng viên (đây là độ lệch tự nhiên của COCO do vật thể bị che khuất và crowd); hàng đợi trên seed 10007 sau khi tinh chỉnh ngưỡng: ~25–35 ảnh.
- **Ngưỡng đã chọn và cách chọn:** Kết hợp bipartite matching bbox IoU > 0.35 đồng thời kiểm tra diện tích và tỷ lệ lọt của segment mask. Không đặt ngưỡng IoU quá lỏng để tránh bùng nổ số lượng ứng viên cần xem mắt.

## 2. Vì sao báo hết ứng viên làm F1 giảm?
Trong bài toán kiểm định chất lượng dữ liệu không có nhãn gốc (Ground Truth), độ đo đánh giá là **F1-score = 2 × (Precision × Recall) / (Precision + Recall)**.
- Khi ta tự động nhận toàn bộ ứng viên nghi vấn mà không qua bước xem ảnh thẩm định, ta có thể tăng Recall nhưng **Precision sẽ bị sụt giảm nghiêm trọng** (từ 0.95 xuống còn ~0.4–0.5).
- Nguyên nhân: Bộ dữ liệu COCO vốn tồn tại các độ lệch tự nhiên giữa Detection và Panoptic (ví dụ: vật thể bị che khuất một nửa, nhiều người đứng sát nhau trong crowd). Các ca lệch tự nhiên này **hoàn toàn không phải lỗi gán nhãn**. Nếu báo hết làm lỗi, số lượng False Positive (báo thừa) sẽ tăng vọt, kéo F1 tổng giảm từ 0.9+ xuống chỉ còn 0.6. Do đó, bước mắt người xem ảnh và ghi chú `confirmed` / `rejected` là không thể thay thế.

## 3. Quyết định và lineage
- **QC v1:** Số ảnh lỗi phát hiện là 23/250 = 9.2%, vượt xa ngưỡng an toàn phát hành 2.0% (&gt; 5 ảnh lỗi trên tổng số 250 ảnh) &rArr; **Kết luận bắt buộc: HOLD**.
- **Tác động tới Model (`R-021`):** Model R-021 đã được huấn luyện trên lô v1 (chứa nhãn bẩn và lỗi gài). Việc tạo ra bản v2 sửa dữ liệu sau này **không tự động chữa lành hay cập nhật lại trọng số của model đã học**. Do đó, run huấn luyện R-021 bắt buộc phải được đánh dấu `action=review_or_retrain`.

## 4. Hash chứng minh gì, không chứng minh gì?
- **Hash chứng minh:** Tính toàn vẹn (Integrity) và bất biến (Immutability) của tệp tin. Mã băm SHA-256 chứng minh file ảnh/nhãn hiện tại trùng khớp 100% từng byte với thời điểm đóng gói bàn giao, không bị chỉnh sửa lén lút hay hỏng hóc trong quá trình truyền tải.
- **Hash KHÔNG chứng minh:** Tính đúng đắn về mặt ngữ nghĩa (Semantic Correctness) của dữ liệu. Một nhãn gán sai hoàn toàn (ví dụ gán con chó thành con mèo) vẫn có thể tính ra một mã băm SHA-256 hoàn toàn hợp lệ. Mã hash không thể thay thế cho quy trình kiểm tra chất lượng nhãn (QC).

## 5. Truy vết
- **Tiêu chí tầng a và tầng b:**
  - Tầng a (`tier_a`): Các ảnh nằm trong những cảnh mà team AI đã nêu đích danh trong ticket, thuộc các job thực hiện theo guideline cũ (v1.2) VÀ có chứa ít nhất 1 box detection thuộc lớp bị đổi quy tắc (ghi trong changelog).
  - Tầng b (`tier_b`): Toàn bộ các ảnh còn lại trong lô thỏa mãn cùng điều kiện trên nhưng chưa được team AI phát hiện ra.
- **Vì sao phải lấy guideline theo job (`jobs.csv`):** Vì trong metadata của từng ảnh có thể tồn tại lỗi `guideline_mismatch` (ảnh bị ghi nhầm phiên bản guideline). Quy định chuẩn mực của quy trình quản trị là phiên bản guideline có hiệu lực được gắn cố định theo từng Job giao việc (`jobs.csv`).

## 6. Đề Ẩn 10 (Thực hiện trong 40 phút)
- **Mã đề:** Đề 10 (`de_an_10` / `de_an.zip` từ Google Drive kho 20 mã đề).
- **Lỗi luật phát hiện (9 lỗi):**
  - `bbox_out_of_bounds`: `img_0054`
  - `duplicate_box`: `img_0132`
  - `guideline_mismatch`: `img_0214`
  - `missing_image`: `img_0078`
  - `scene_leak`: `scene_743`
  - `thing_overlap`: `img_0213`, `img_0250`
  - `wrong_hash`: `img_0007`, `img_0128`
- **Lỗi gán nhãn thẩm định qua xem ảnh (9 lỗi confirmed):**
  - `class_swap`: `img_0015` (wine glass &rarr; cup), `img_0043` (bowl &rarr; cup), `img_0053` (person &rarr; baseball glove), `img_0091` (cake &rarr; donut), `img_0094` (truck &rarr; car).
  - `missing_box`: `img_0096` (lò nướng oven 63647px thiếu box detection).
  - `bbox_drift`: `img_0090` (person box lệch), `img_0220` (person box lệch), `img_0240` (sheep box lệch).
- **Truy vết Ticket Đề Ẩn 10 (Lớp `car` bị đổi guideline v1.2 &rarr; v1.3):**
  - `tier_a`: `["img_0074", "img_0236"]` (thuộc cảnh `scene_290` và `scene_635`, job v1.2, có box `car`).
  - `tier_b`: `["img_0135", "img_0146", "img_0188", "img_0209"]`.
  - `notify`: `["A02", "A04", "Q02"]`.
- **Tổng lỗi nộp Đề 10:** 18 lỗi trong `submission/de_an/errors.json`.
- **Review Log:** 97 dòng trong `submission/de_an/review_log.csv` (100% dòng có ghi chú cụ thể &ge; 20 ký tự).
