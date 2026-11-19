# Bảo mật khi làm việc — Lô r9007 (`lab250_79c4d088f4c4`)

## 1. Ca USB: hết giờ, muốn chép lô về nhà làm tiếp
Không được chép lô dữ liệu ra USB cá nhân, gửi qua email cá nhân hay nhờ người ngoài làm hộ vì làm mất kiểm soát truy cập, dễ rò rỉ dữ liệu chưa phát hành và vi phạm quy trình bàn giao. Thay vào đó, chỉ làm việc trên máy/không gian được cấp quyền (hoặc VPN/máy trạm nội bộ của dự án), lưu tiến độ review tại chỗ và bàn giao ca cho thành viên có quyền trong nhóm.

## 2. Năm việc: được hay không
- **Mở job được giao trên máy công ty:** Được, đây là môi trường làm việc được cấp quyền chính thức.
- **Chụp màn hình gửi người quen:** Không, vì làm lộ dữ liệu nội bộ ra ngoài phạm vi dự án.
- **Chép lô ra USB:** Không, tạo bản sao không kiểm soát và có nguy cơ thất lạc/rò rỉ dữ liệu.
- **Dán nhãn thật lên chatbot:** Không (với dữ liệu dự án thật), vì dữ liệu có thể bị lưu/huấn luyện trên máy chủ bên thứ ba ngoài hợp đồng bảo mật.
- **Đưa tài khoản CVAT cho đồng nghiệp:** Không, vi phạm nguyên tắc định danh cá nhân (audit trail sẽ ghi sai người gán/người kiểm và mất khả năng truy vết).

## 3. Ca khuôn mặt: thấy mặt người rõ trong lô, guideline yêu cầu làm mờ
- **Kết luận trạng thái lô:** **Hold + báo người phụ trách** (Data Governance / PM).
- **Hành động:** Dừng bàn giao lô `lab250_79c4d088f4c4`, ghi nhận ảnh có khuôn mặt người rõ vào báo cáo sự cố và chuyển lại bộ phận xử lý dữ liệu gốc để thực hiện làm mờ (anonymization) đúng quy trình trước khi phát hành. Tuyệt đối không tự ý dùng phần mềm ngoài để làm mờ hay tự xóa ảnh vì sẽ làm lệch manifest, sai hash SHA-256 và mất tính toàn vẹn của v1.
- **Ví dụ ảnh có người trong lô `r9007`:** `000000000139`, `000000000785`, `000000000872` (đều có nhãn `person` trong `delivery/labels/`).
