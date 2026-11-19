# Hướng dẫn làm việc nhóm Day 10 (TEAM GUIDE)

> **Mục tiêu:** Mọi thành viên đều có thể nhận việc, báo cáo kết quả, review ảnh và tạo commit/PR hợp lệ **ngay trên trình duyệt GitHub** (không bắt buộc cài Claude hay chạy terminal phức tạp nếu bạn phụ trách review/docs).

---

## 1. Bắt đầu nhanh trong 8 bước

1. **Đăng nhập GitHub** bằng tài khoản cá nhân của bạn và **Accept Invitation** (chấp nhận lời mời cộng tác vào repo `hungpixi/K5-L23-Day10-Dataset-Release-Handover`).
2. **Mở trang Issues:** https://github.com/hungpixi/K5-L23-Day10-Dataset-Release-Handover/issues
3. **Chọn Issue của bạn** (tìm theo tên hoặc label `phase:P0`..`phase:P6`).
4. **Đọc kỹ Checklist** và **Acceptance Criteria** trong Issue.
5. **Thực hiện phần việc** thuộc thư mục được phân công (xem bảng phân quyền bên dưới).
6. **Comment kết quả và bằng chứng thật** (output lệnh, số lượng ảnh đã xem, đường dẫn file) vào Issue.
7. **Tạo Pull Request (PR)** vào nhánh `team/day10-integration` (hoặc `main` theo hướng dẫn Lead) nếu có thay đổi file.
8. **Tick hoàn thành checklist** trong Issue khi đã có bằng chứng và PR được review.

---

## 2. Phân quyền thư mục để không bị Merge Conflict

| Thành viên | GitHub | Thư mục phụ trách | Không sửa trực tiếp |
|---|---|---|---|
| Phạm Phú Nguyễn Hưng | `@hungpixi` | `validator/`, `tests/validator/`, `.github/` | `scripts/` (của giảng viên) |
| Đỗ Anh Hoàng | `@AnhHoangDepTrai` | `qc/crosscheck/`, `tests/crosscheck/` | `scripts/` |
| Bùi Văn Thịnh | `@buivanthinhtxt-del` | `qc/review/`, `review_log.csv` | `scripts/` |
| Nguyễn Xuân Việt | `@ngxuanviet` | `release/`, `handover/` | `scripts/` |
| Hoàng Trọng Trà | `@trahoangdev` | `trace/` | `scripts/` |
| Nguyễn Quốc Hưng | `@Soraxolo` | `security/`, `reporting/` | `scripts/` |

---

## 3. Dành cho thành viên không code / không dùng Git CLI

Nếu bạn làm **Visual Review (P2)**, **Security (`security.md`)**, hoặc **Báo cáo (`REPORT.md`, `prompts.md`)**:
- Bạn **không cần cài AI hay Python** để xem ảnh và ghi kết quả.
- **Cách sửa file & tạo commit ngay trên GitHub Web:**
  1. Mở file cần sửa trên GitHub (ví dụ `qc/review/review_template.csv` hoặc `security/README.md`).
  2. Bấm biểu tượng **Cây bút (Edit this file)**.
  3. Nhập nội dung hoặc dán kết quả review.
  4. Bấm **Commit changes...** -> chọn **Create a new branch for this commit and start a pull request**.
  5. Điền mô tả ngắn gọn và bấm **Create pull request**.
- **Quy định rubric:** Mỗi thành viên cần tối thiểu **2 commit thực chất** mang tên và email của chính mình:
  - Commit 1: Phần việc chính được giao.
  - Commit 2: Sửa lỗi / bổ sung test / cập nhật tài liệu sau review.

---

## 4. Quy tắc an toàn & trung thực (Bắt buộc theo `RULES.md`)

- **TUYỆT ĐỐI KHÔNG** đưa dữ liệu riêng tư (`_private/`, `data_source/`, `runs/`, `*.zip`, ảnh khuôn mặt nhạy cảm, API key/token) lên Issue, Comment hoặc Git.
- **TUYỆT ĐỐI KHÔNG** sửa các file trong `scripts/` để qua mặt bộ kiểm.
- Mọi dòng `confirmed` / `rejected` trong `review_log.csv` phải do **người thật xem ảnh** và ghi rõ đã thấy gì trong ảnh (tối thiểu 20 ký tự).
- Không tự ý đánh dấu `status:done` nếu chưa có bằng chứng chạy thực tế.
