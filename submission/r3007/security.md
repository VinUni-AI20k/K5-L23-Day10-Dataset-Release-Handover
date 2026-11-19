# Bảo mật khi làm việc với Dữ liệu Huấn luyện & Bàn giao Dataset

## 1. Ca USB: Hết giờ làm việc, muốn chép lô dữ liệu về nhà làm tiếp

Tuyệt đối **KHÔNG ĐƯỢC** cắm USB, ổ cứng di động cá nhân để sao chép dữ liệu của dự án ra ngoài, và cũng **KHÔNG ĐƯỢC** gửi dữ liệu qua email cá nhân, Google Drive cá nhân hay nhờ người quen làm hộ.
- **Lý do rủi ro & vi phạm:**
  1. *Vi phạm hợp đồng bảo mật (NDA) & rò rỉ dữ liệu (Data Leakage):* Dữ liệu hình ảnh và nhãn gán là tài sản sở hữu trí tuệ của tổ chức/khách hàng. Thiết bị cá nhân và hòm thư cá nhân không chịu sự kiểm soát bảo mật của mạng nội bộ công ty (thiếu endpoint encryption, DLP - Data Loss Prevention, kiểm toán truy cập), có nguy cơ cao bị nhiễm mã độc, trojan đánh cắp dữ liệu hoặc vô tình làm lộ dữ liệu chưa công bố ra bên ngoài.
  2. *Mất tính toàn vẹn (Integrity) và dấu vết kiểm toán (Audit Trail):* Khi mang về nhà hoặc nhờ người khác làm hộ, quy trình kiểm soát phiên bản và phân công trách nhiệm (annotator/reviewer trong jobs.csv) bị phá vỡ hoàn toàn. Nếu có sai sót về nhãn hoặc guideline mismatch, đội ngũ QA không thể truy vết ai là người thực sự thao tác.
- **Cách xử lý đúng chuẩn:**
  - Để nguyên dữ liệu tại môi trường máy trạm bảo mật của công ty hoặc hệ thống CVAT/storage được cấp phép.
  - Báo cáo trực tiếp với Quản lý dự án (Project Manager / Tech Lead) xin phê duyệt mở rộng thời hạn (overtime/remote work) thông qua kênh VPN bảo mật nội bộ và tài khoản doanh nghiệp được quản lý định danh (IAM). Nếu không kịp tiến độ, nhóm bàn giao theo phân công ca trực hoặc xin dời checkpoint theo quy trình vận hành tiêu chuẩn.

## 2. Năm việc: Được hay Không được phép thực hiện

1. **Mở job được giao trên máy công ty:**
   - **ĐƯỢC PHÉP.**
   - *Lý do:* Đây là quy trình làm việc chuẩn. Máy tính công ty đã được cài đặt chính sách bảo mật, phần mềm quét mã độc, tường lửa và chứng chỉ định danh nội bộ, đảm bảo mọi thao tác gán nhãn và kiểm tra dữ liệu nằm trong vòng kiểm soát an toàn.

2. **Chụp màn hình gửi người quen:**
   - **KHÔNG ĐƯỢC PHÉP.**
   - *Lý do:* Chụp ảnh màn hình (screenshot) các cảnh quay, vật thể, thông tin nhãn hoặc giao diện hệ thống nội bộ rồi gửi ra ngoài là hành vi phát tán trái phép tài sản dự án (unauthorized disclosure), vi phạm nghiêm trọng cam kết bảo mật thông tin khách hàng và có thể chịu chế tài kỷ luật hoặc pháp lý.

3. **Chép lô ra USB:**
   - **KHÔNG ĐƯỢC PHÉP.**
   - *Lý do:* Sử dụng thiết bị lưu trữ ngoại vi chưa qua phê duyệt (unauthorized removable media) là nguồn phát tán mã độc hàng đầu và là con đường gây thất thoát dữ liệu quy mô lớn. Các cổng kết nối USB trên máy trạm doanh nghiệp thông thường bị khóa chính sách hoặc giám sát nghiêm ngặt bởi phần mềm DLP.

4. **Dán nhãn thật lên chatbot công cộng (như ChatGPT, Claude web):**
   - **KHÔNG ĐƯỢC PHÉP.**
   - *Lý do:* Các chatbot công cộng thương mại trên Internet có chính sách thu thập dữ liệu người dùng để tái huấn luyện mô hình. Việc đưa dữ liệu nội bộ, tọa độ bounding box hoặc logic nhãn gán lên chatbot công cộng sẽ biến tài sản độc quyền thành dữ liệu huấn luyện công khai, gây vi phạm bản quyền và rò rỉ bí mật công nghệ.

5. **Đưa tài khoản CVAT cho đồng nghiệp:**
   - **KHÔNG ĐƯỢC PHÉP.**
   - *Lý do:* Tài khoản truy cập nền tảng gán nhãn (CVAT / Label Studio) được cấp phát riêng cho từng cá nhân và gắn liền với định danh `annotator` / `reviewer` trong hệ thống truy vết (`jobs.csv`). Việc chia sẻ tài khoản vi phạm nguyên tắc chống chối bỏ (Non-repudiation), làm sai lệch nhật ký kiểm toán trách nhiệm và tiềm ẩn nguy cơ leo thang đặc quyền trái phép.

## 3. Ca khuôn mặt: Thấy mặt người rõ trong lô, guideline yêu cầu làm mờ

- **Hành động của kỹ sư kiểm định:**
  - Ngay lập tức tạm dừng luồng phát hành và đưa trạng thái lô về **HOLD**.
  - Báo cáo khẩn cấp cho Quản trị viên dự án (Project Lead) và Đội ngũ Pháp lý / Bảo mật Dữ liệu (Compliance / Privacy Team).
  - Lập biên bản sự cố bảo mật thông tin nhận dạng cá nhân (PII - Personally Identifiable Information), trích dẫn bằng chứng cụ thể trong lô.
  - **Minh chứng cụ thể trong lô của nhóm:** Ảnh `000000007511` (cùng các ảnh `000000000872`, `000000012748`) có khuôn mặt và hình ảnh người thật nhìn rất rõ nét, cần phải được xử lý làm mờ theo tiêu chuẩn bảo vệ quyền riêng tư trước khi phát hành.
- **Vì sao không tự ý mở ảnh ra làm mờ hay xoá ảnh?**
  1. *Phá vỡ tính toàn vẹn (Integrity) và mã băm SHA-256:* Tự ý dùng phần mềm chỉnh sửa hoặc xóa ảnh sẽ làm sai lệch mã băm sha256 trong `manifest.csv`, sai lệch tổng số nhãn trong `label_summary.csv` và làm gãy hoàn toàn tính tái lập của lô dữ liệu so với hồ sơ bàn giao v1.
  2. *Làm lệch phân phối tập dữ liệu (Data Distribution Drift):* Xóa ảnh hoặc tự ý can thiệp pixel có thể làm thay đổi tỷ lệ phân bố giữa tập train/val hoặc làm mất cân bằng các scene trong `truyvet.csv`.
  3. *Quy trình xử lý PII chuẩn:* Việc làm mờ khuôn mặt (blurring / pixelation) phải tuân theo pipeline tự động đã được kiểm định của tổ chức (chuẩn hóa độ mờ, kernel size, lưu vết metadata phiên bản ẩn danh), đảm bảo tính nhất quán trên toàn bộ dataset thay vì thao tác thủ công tùy tiện.
