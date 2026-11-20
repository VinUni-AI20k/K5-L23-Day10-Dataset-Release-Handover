# Báo cáo nhóm (chờ bổ sung mã nhóm)

## 1. Số liệu luyện tập
- Seed thống nhất hiện tại: `2902` (release v1: `lab250_9f8af853f974`).
- F1 chính thức: **chưa có**. Chưa có `errors.json` hoàn chỉnh và chưa chạy được quy trình chấm hợp lệ; số dòng `confirmed` trong review log không tự nó chứng minh đã tìm đủ lỗi hoặc xác nhận được F1.
- Số ứng viên trên lô sạch (`--no-faults`) và hàng đợi trên seed:
  * Lô sạch (`runs/clean` - 50 ảnh calib): **0 ứng viên** trong lần chạy kiểm tra. Đây chỉ là kết quả trên pool calib này, không chứng minh không có báo nhầm trên các lô khác.
  * Seed 2902: **24 ứng viên thuộc 16 ảnh**, tái tạo được bằng `validator/cross_check.py`.
- Ngưỡng triển khai hiện tại trong `validator/cross_check.py` (đối chiếu bằng bounding box):
  * `class_swap` / `category_swap`: IoU giữa box detection và segment bbox >= 0.40.
  * `instance_merge`: box detection cùng lớp có diện tích >= 400 px; có ít nhất 2 box nằm trong segment bbox với containment >= 65%; số box cùng lớp lớn hơn số segment cùng lớp; có ít nhất một cặp box trong nhóm containment có IoU < 0.40. Code hiện không áp dụng ngưỡng diện tích tối thiểu cho segment.
  * `bbox_drift`: cặp cùng lớp được ghép một-đối-một nếu IoU > 0; ứng viên khi 0.35 <= IoU <= 0.78, tâm lệch >= 8% đường chéo box và box detection có diện tích chuẩn hóa >= 0.005 ảnh.
  * `missing_box`: segment chưa ghép có `area` >= 1000 px và segment bbox chiếm >= 1% diện tích ảnh; không có box chưa ghép nào đạt IoU >= 0.40.
- Giới hạn: cross-check và ảnh trực quan hóa hiện dùng bounding box từ annotation, chưa tính chồng lấp pixel của panoptic mask. Vì vậy candidates chỉ là hàng đợi nghi vấn; người review phải mở ảnh để quyết định.

## 2. Vì sao báo hết ứng viên làm F1 giảm?
Ứng viên (`candidates.json`) sinh ra từ thuật toán đối chiếu chỉ là các trường hợp có nghi vấn bất đồng giữa Detection và Panoptic, **không đồng nghĩa tất cả đều là lỗi gán nhãn**.
COCO có độ lệch tự nhiên giữa hai nguồn dữ liệu do:
1. Ranh giới lớp mập mờ trong tự nhiên: ví dụ xe tải thùng lớn vs xe bus ở ảnh `000000006723`, chén trà nhỏ cup vs bowl ở `000000009590`, bánh kẹp xúc xích hot dog vs sandwich ở `000000009914`, lọ hoa vs chai lọ ở `000000020553`.
2. Vật thể bị che khuất một phần ở viền ảnh hoặc bị vật thể khác che khuất trong phối cảnh đông đúc.
**Kết quả phân tích từ thực nghiệm của nhóm trên seed 2902:**
- Review log hiện có 24 dòng: 6 `confirmed`, 18 `rejected`. Đây là số liệu review, không phải ground truth độc lập.
- Minh họa có điều kiện: nếu giả sử 6 confirmed là toàn bộ lỗi thật và không có lỗi bị bỏ sót, nộp cả 24 ứng viên sẽ cho TP=6, FP=18, FN=0; precision=0.25, recall=1.0 và F1=0.40. Đây không phải F1 chính thức; nếu có lỗi bị bỏ sót, F1 thực tế sẽ thấp hơn.
- Báo cáo nhóm ghi nhận việc chia người review theo nhóm loại lỗi. Tuy nhiên, `review_log.csv` hiện không có tên người review trong các ghi chú, nên chưa đủ bằng chứng trong file để đối chiếu người xem từng ca. Cần bổ sung đúng tên người thực sự review vào ghi chú trước khi nộp; không suy đoán hoặc tự gán tên.

## 3. Quyết định và lineage
Lineage hiện ghi seed `2902` (`lab250_9f8af853f974`) và training run `R-021`. Chưa có `errors.json`, quyết định QC v1/HOLD, hay bản v2 để xác minh; không tự kết luận QC hoặc ghi nhận release. Nếu v1 bị HOLD, model R-021 cần được đánh giá lại hoặc huấn luyện lại vì sửa dataset không thay đổi dữ liệu model đã học.

## 4. Hash chứng minh gì, không chứng minh gì?
SHA-256 trong manifest giúp kiểm tra file hiện tại có trùng byte với file đã ghi nhận khi lập manifest hay không. Hash không chứng minh ảnh hoặc nhãn đúng ngữ nghĩa, người tạo có thẩm quyền, file không chứa dữ liệu nhạy cảm, hay nội dung có thể phát hành. Cần kiểm nội dung và quyền truy cập riêng.

## 5. Truy vết
Với seed `2902`, ticket báo `scene_814` và `scene_952`; changelog nêu quy tắc mới cho class `cup` (class ID `41`). Tier A gồm ảnh trong các scene được báo nếu job dùng guideline `v1.2` và nhãn có box cup; tier B là các ảnh khác thỏa cùng điều kiện. Guideline phải lấy từ `jobs.csv`, vì metadata từng ảnh có thể sai. Kết quả: tier A `000000003661`, `000000003845`, `000000003934`; tier B `000000002157`, `000000002431`, `000000002592`, `000000002685`; notify `A02`, `Q03`. Metadata của ảnh `000000011149` không khớp guideline trong job; phân loại vẫn dựa theo `jobs.csv`.

## 6. Bug hoặc điểm chưa rõ trong lab (nếu có)
Chưa xác minh được bug trong script của lab. Một lần chạy ban đầu bị lỗi encoding đầu ra tiếng Việt trên Windows (`cp1252`); chạy lại với `PYTHONUTF8=1` thành công, nên đây được ghi nhận là vấn đề cấu hình console của máy, không phải bug đã xác nhận của script.
