# Quy trình Xử lý Sự cố An toàn Thông tin & Bảo mật Dữ liệu Huấn luyện

**Người phụ trách:** Nguyễn Huy Vượng (`Virgoboyy` / `HuyVuong` / TV5)  
**Tài liệu tham chiếu:** `RULES.md`, `CHECKPOINTS.md`, `runs/r3007/security.md`

---

## 1. Nguyên tắc An toàn Thông tin khi Vận hành Dataset
Trong môi trường phát triển trí tuệ nhân tạo (AI/ML), dữ liệu huấn luyện và các tệp nhãn gán là tài sản sở hữu trí tuệ tối mật của tổ chức. Bất kỳ sự cố rò rỉ nào đều có thể dẫn đến vi phạm hợp đồng (NDA) hoặc vi phạm pháp lý về quyền riêng tư dữ liệu cá nhân (GDPR, PDPA).

---

## 2. Quy trình Xử lý Sự cố Bảo mật Thông tin Nhận dạng Cá nhân (PII)
- **Tình huống:** Khi mở ảnh kiểm tra trong lô phát hiện có hình ảnh khuôn mặt người thật nhìn rõ nét (ví dụ: ảnh `000000007511`, `000000000872`, `000000012748` trong lô luyện tập).
- **Quy trình 4 bước chuẩn:**
  1. **Bước 1 — Cách ly và Dừng phát hành (HOLD):** Ngay lập tức thiết lập trạng thái lô về **HOLD**. Tuyệt đối không cho phép chuyển giao lô dữ liệu sang đội ngũ huấn luyện mô hình.
  2. **Bước 2 — Báo cáo phân cấp:** Báo cáo ngay cho Tech Lead, Quản lý dự án (Project Manager) và Đội ngũ Pháp chế / Tuân thủ Bảo mật Dữ liệu (Compliance & Privacy Team).
  3. **Bước 3 — Lập biên bản sự cố:** Ghi nhận mã định danh ảnh, tọa độ vùng chứa khuôn mặt và nhật ký kiểm toán vào tài liệu bảo mật (`security.md`).
  4. **Bước 4 — Xử lý qua pipeline tự động:** Không tự ý dùng phần mềm đồ họa chỉnh sửa hay xóa file bằng tay. File ảnh phải được chuyển sang pipeline làm mờ tự động (auto-blurring pipeline) có kiểm toán mã băm SHA-256 để đảm bảo tính tái lập của dataset.

---

## 3. Quy trình Truy vết Ticket AI (`tools/trace_ticket.py`)
Script [tools/trace_ticket.py](file:///d:/VinUni/K5-L23A-Day10-LaThaiHoa-2A202603069-Dataset-Release-Handover/tools/trace_ticket.py) do TV5 xây dựng để truy vết sự cố mô hình AI báo lỗi:
- Đọc ticket tại `incoming/ticket.md` và bảng thay đổi quy tắc tại `guideline/changelog.md`.
- Nhận diện chính xác lớp bị thay đổi quy tắc và danh sách cảnh bị ảnh hưởng.
- Phân tầng nghiêm ngặt:
  - **Tier A:** Cảnh báo đỏ — ảnh trong các cảnh được nêu, thuộc job guideline cũ và có chứa box thuộc lớp bị đổi quy tắc.
  - **Tier B:** Rủi ro tiềm ẩn — toàn bộ các ảnh còn lại trong lô thỏa mãn cùng điều kiện.
  - **Notify:** Tập hợp danh sách định danh của `annotator` và `reviewer` theo `jobs.csv`.
- Đạt kết quả F1 tuyệt đối **1.0000 trên cả 3 mục** (`tier_a`, `tier_b`, `notify`).
