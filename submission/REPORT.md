# Báo cáo kết quả Day 10 Lab — Nhóm 03

## 1. Số liệu luyện tập
- **F1 theo seed chính (seed 3007):**
  - F1 tổng thể: **0.9** (rank F1 = 0.90)
  - F1 lỗi luật (`rule_detectable`): **1.0** (11/11 lỗi luật bắt chính xác tuyệt đối, 0 False Positive)
  - F1 lỗi gán nhãn (`cross_check_review`): **0.9** (vượt xa ngưỡng yêu cầu 0.6 của RUBRIC.md)
  - F1 truy vết ticket AI: **tier_a = 1.0 · tier_b = 1.0 · notify = 1.0**
- **Hiệu chuẩn trên lô sạch (`runs/clean`, 50 ảnh chuẩn không gài lỗi):**
  - Số lỗi luật phát hiện: **0**
  - Số ứng viên nghi ngờ sinh ra: **0** (Zero False Alarm)
- **Hàng đợi ứng viên trên seed luyện tập 3007:**
  - Tổng số ứng viên: **11 ảnh**
  - Sau quy trình review 5 thành viên: **8 ảnh confirmed** (phát hiện lỗi thật), **3 ảnh rejected** (lệch tự nhiên/vật thể nền của COCO).
- **Ngưỡng đã chọn và phương pháp chọn (Hoàn toàn không truy cập `_private/`):**
  - Phân tích ranh giới toán học giữa tọa độ YOLO normalized $[0, 1]$ và không gian pixel nguyên của ảnh.
  - Áp dụng dung sai tọa độ `BOX_PAD_PX = 1.0` để bù trừ sai số làm tròn số thực của YOLO.
  - Ngưỡng ghép trùng lớp mạnh: `STRONG_SAME_COV = 0.88` (tỷ lệ pixel mask nằm trọn trong box) và `STRONG_SAME_IOU = 0.50`.
  - Bắt `bbox_drift`: khi segment thing và detection box cùng lớp nhưng tỷ lệ pixel mask nằm trong box rơi xuống dưới 0.88 và chênh lệch trên 1500 pixel.
  - Bắt `instance_merge`: 1 segment thing phủ lên $\ge 2$ box detection cùng lớp với tổng diện tích phủ `union_cov >= 0.82` và mỗi box giữ $\ge 2.5\%$ pixel độc quyền.
  - Bắt `class_swap` / `category_swap`: 1 box và 1 segment lệch lớp có `IoU >= 0.35` và `seg_in_box >= 0.80`.

## 2. Vì sao báo hết ứng viên làm F1 giảm?
- **Nguyên lý đánh giá F1:** Công thức $F1 = \frac{2 \times \text{Precision} \times \text{Recall}}{\text{Precision} + \text{Recall}}$. Trong đó, hệ thống chấm điểm quy định: báo thừa (False Positive) bị trừ điểm ngang với bỏ sót (False Negative).
- **Thực tế số liệu của Nhóm 03 trên seed 3007:**
  - Bộ lọc đối chiếu phát hiện 11 ứng viên. Trong đó chỉ có **8 ứng viên là lỗi thật** (`class_swap`, `category_swap`, `missing_box`, `bbox_drift`, `instance_merge`).
  - **3 ứng viên còn lại** (`000000000872`, `000000001818`, `000000012748`) là các trường hợp vật thể bị khuất lấp nặng, nằm mờ xa ở hậu cảnh (background) hoặc bị cắt cụt quá 70% ở rìa ảnh trong tập gốc COCO, theo quy tắc gán nhãn chuẩn không đủ điều kiện đóng bounding box.
  - Nếu nhóm báo bừa toàn bộ 11 ứng viên mà không qua bước visual review để loại bỏ 3 trường hợp này, ta sẽ bị dính **3 False Positives**.
  - Kết quả: Precision bị tụt từ 1.0 xuống 0.73, kéo F1 tổng thể giảm từ **0.9** xuống **~0.7**. Do đó, quy trình xem ảnh bằng mắt (human review) và ghi nhận `verdict=rejected` kèm lý do cụ thể trong `review_log.csv` là mắt xích bắt buộc để đạt F1 tối đa.

## 3. Quyết định và Lineage
- **Tỷ lệ kiểm định chất lượng (QC v1):**
  - Tổng số lỗi tìm thấy trong v1: **19 lỗi / 250 ảnh = 7.6%**.
  - Đối chiếu với ngưỡng tiêu chuẩn dự án (2.0% theo Day 7): Tỷ lệ lỗi 7.6% vượt xa ngưỡng cho phép (7.6% > 2.0%).
  - **Kết luận:** Quyết định dứt khoát đưa lô v1 (`lab250_95697c6d4612`) về trạng thái **HOLD**.
- **Tác động đến Training Run R-021 (Lineage Impact):**
  - Khi tra cứu qua `scripts/lineage.py impact --release-id lab250_95697c6d4612`, hệ thống cảnh báo: `R-021: affected=True action=review_or_retrain`.
  - **Lý do kỹ thuật:** Model R-021 đã được huấn luyện trên lô dữ liệu v1 chứa 19 lỗi nghiêm trọng (bao gồm gán sai lớp `tv` $\leftrightarrow$ `laptop`, `bus` $\leftrightarrow$ `car`, trùng box, lệch box và rò rỉ cảnh giữa train/val). Việc đội dữ liệu đóng gói và bàn giao lô v2 sạch không thể tự động sửa chữa các trọng số (weights) đã hội tụ sai lệch trong checkpoint của R-021. Do đó, model R-021 bắt buộc phải được đánh giá lại độ suy giảm hiệu năng (benchmark regression) và tái huấn luyện (retrain) hoàn toàn trên lô v2.

## 4. Hash chứng minh gì, không chứng minh gì?
- **Hash SHA-256 chứng minh:**
  1. *Tính toàn vẹn bit (Bit-level Integrity):* Chứng minh chính xác file nhận được ở phía người dùng hoàn toàn trùng khớp từng byte với file tại thời điểm đóng gói, không bị lỗi suy hao đường truyền (packet loss, corrupted download) hay can thiệp trái phép.
  2. *Tính bất biến và dấu vết kiểm toán (Immutability & Auditability):* Xác nhận định danh duy nhất của snapshot dữ liệu tại thời điểm bàn giao, làm cơ sở ràng buộc trách nhiệm pháp lý giữa bên gán nhãn và bên tiêu thụ dữ liệu.
- **Hash SHA-256 KHÔNG chứng minh:**
  1. *Tính đúng đắn về mặt ngữ nghĩa (Semantic Correctness):* Một file nhãn chứa tọa độ sai, gán nhầm xe con thành xe bus hoặc sót vật thể vẫn có mã băm SHA-256 hoàn toàn hợp lệ.
  2. *Chất lượng dữ liệu & Tuân thủ đạo đức:* Mã băm không thể phát hiện ảnh bị rò rỉ giữa train/val (`scene_leak`), vi phạm phiên bản hướng dẫn (`guideline_mismatch`) hay ảnh vi phạm quyền riêng tư chứa khuôn mặt người chưa được làm mờ (PII violation).

## 5. Truy vết Ticket của Team AI
- **Tiêu chí phân loại tầng:**
  - **Tier A (Cảnh báo đỏ):** Các ảnh nằm trong đúng các cảnh team AI nêu (`scene_197`, `scene_309`), thuộc job theo phiên bản guideline cũ (v1.2) và có chứa ít nhất một bounding box detection thuộc lớp bị đổi quy tắc (`bottle`, ID 39).
  - **Tier B (Rủi ro tiềm ẩn):** Toàn bộ các ảnh còn lại trong lô thỏa mãn cùng điều kiện (thuộc job guideline v1.2 và chứa box `bottle`) nhưng chưa được team AI phát hiện trong quá trình vận hành thử nghiệm.
  - **Notify:** Tập hợp danh sách định danh duy nhất của người gán (`annotator`) và người kiểm duyệt (`reviewer`) chịu trách nhiệm đối với các job chứa ảnh tầng A và B.
- **Vì sao bắt buộc lấy guideline theo Job (`jobs.csv`) thay vì từng ảnh?**
  - Trường `guideline_version` ghi trong file `metadata.json` của từng ảnh là dữ liệu mức bản ghi có thể bị nhập sai lệch do sơ suất hệ thống (chính là lỗi `guideline_mismatch`).
  - Trong khi đó, `jobs.csv` đại diện cho hợp đồng pháp lý và quy chuẩn chính thức được giao khi mở lô công việc. Nếu lấy theo từng ảnh, một ảnh bị dính lỗi `guideline_mismatch` (bị ghi nhầm thành v1.3 trong khi thực chất job phân công là v1.2) sẽ bị bỏ sót khỏi danh sách truy vết, gây nguy cơ rò rỉ dữ liệu lỗi nghiêm trọng vào production.

## 6. Ghi chú kỹ thuật & Tối ưu hóa
- **Tối ưu tốc độ tải COCO:** Khi tải từ AWS S3 qua kênh đơn luồng tiêu chuẩn (`urllib`), tốc độ thường bị nghẽn mạng ở mức 15–30 KB/s. Nhóm đã xây dựng cơ chế tải phân đoạn đa luồng song song (HTTP Range Requests, 24 luồng) giúp tăng tốc độ tải lên 4.5 MB/s, hoàn tất trọn vẹn bộ ảnh mẫu trong hơn 8 phút mà không làm gián đoạn bài làm.
- **Tối ưu bảng Review Board:** Công cụ `render_review.py` của TV3 đã được bổ sung cơ chế tính toán ranh giới nhãn thông minh (bounding label calculations) tránh đè chữ lên bounding box, và xuất giao diện HTML tự chứa CSS/JS trực quan giúp cả nhóm duyệt 11 ứng viên nhanh chóng và chính xác.
