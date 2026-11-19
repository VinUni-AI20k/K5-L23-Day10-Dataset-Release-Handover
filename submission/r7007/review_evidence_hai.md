# Biên bản kiểm tra chéo — Phạm Hải

- Nhóm: 7
- Seed: 7007
- Vai trò: Đối chiếu detection và panoptic, kiểm tra bằng mắt
- Dữ liệu: 250 ảnh luyện tập, 50 ảnh hiệu chỉnh sạch
- Không sử dụng ground truth ẩn hoặc thư mục `_private`

## 1. Kết quả kiểm tra tự động

Chạy validator của nhóm trên seed 7007:
- 12 lỗi luật
- 6 ứng viên gán nhãn trên 5 ảnh

Chạy trên 50 ảnh sạch:
- 0 lỗi luật
- 0 ứng viên

Kết quả lô sạch cho thấy không có cảnh báo trên mẫu hiệu chỉnh này, nhưng không chứng minh validator đạt recall tuyệt đối.

## 2. Kiểm tra trực quan

Đã xem ảnh gốc cùng bounding box detection và vùng panoptic cho các ảnh:

- 000000000785: Detection thiếu box skis. Mask còn thiếu một phần nhỏ của ván trượt.
- 000000001818: Hai con ngựa vằn đứng sát nhau. Hai chân ở giữa thuộc con bên trái, nhưng mask lại tính sang con bên phải. Box detection không bị lệch.
- 000000006471: Vật ở khu vực sân bóng chày là bench, không phải couch.
- 000000013177: Xe ở phía sau là bicycle, không phải motorcycle.
- 000000015079: Hai sandwich riêng biệt bị panoptic gộp một instance; không xác nhận thêm bbox_drift.

Các verdict chi tiết nằm trong review_hai.csv.

## 3. Giới hạn và bàn giao

- Đây là kết quả review cá nhân, chưa thay thế review_log.csv cuối của nhóm.
- Các thành viên còn lại cần tự xem ảnh theo quy định lab.
- Sau khi thống nhất, nhóm gộp lỗi luật với review confirmed để tạo errors.json.
