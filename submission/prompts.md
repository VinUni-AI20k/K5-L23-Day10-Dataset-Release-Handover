# Dùng AI

## Bổ sung ngày 19/11/2026 — Data Validation

- Người yêu cầu: thành viên phụ trách Data Validation (chưa xác nhận danh tính trong chat).
- Công cụ: Codex. Prompt: “tôi là người thực hiện phần data_validation. Bạn hãy đọc folder và roadmap-nhóm rồi thực hiện làm phần bài làm của tôi vào trong folder đi”.
- AI triển khai 9 kiểm tra luật, CLI, 13 unit tests, hướng dẫn tích hợp và rules.json.
- Điểm cần lưu ý: chưa tích hợp candidates của Người 2; không coi rules.json là kết quả review cuối cùng. Lệnh chạy script ban đầu thiếu -X utf8 gây lỗi in tiếng Việt trên Windows; đã đổi cách gọi, không sửa script lab.
- AI kiểm tra: 13/13 unit tests đạt; seed 12007 có 12 lỗi luật, seed 12008 có 13, F1 lỗi luật của cả hai ≈ 1.0 theo bộ chấm làm tròn; lô sạch calib seed 5 có 0 lỗi luật. Chi tiết ở DATA_VALIDATION.md.
- Nhóm cần tự đọc code, chạy lại và xác nhận kết quả; các kiểm thử trên do AI chạy, không phải bằng chứng nhóm đã review bằng mắt. AI không tạo review confirmed/rejected.

Bảng dưới ghi lại việc sử dụng AI trong cuộc trò chuyện chuẩn bị lab. Tên thành viên và kết quả kiểm tra của nhóm cần được bổ sung trung thực; việc AI đọc tài liệu không có nghĩa là nhóm đã tự kiểm tra hoặc chạy validator.

| # | Ai dùng | Công cụ | Prompt (tóm tắt) | AI sai ở đâu / điểm cần lưu ý | Nhóm kiểm lại thế nào |
|---|---|---|---|---|---|
| 1 | Lê Tuấn Khôi (2A202603024) | ChatGPT / Codex | Đọc và tóm tắt repo làm gì. | Chưa ghi nhận lỗi cụ thể. | AI đã đối chiếu README, GUIDE và cấu trúc repo; **nhóm chưa ghi nhận kết quả tự kiểm**. |
| 2 | Lê Tuấn Khôi (2A202603024) | ChatGPT / Codex | Hỏi kiến thức cần có, nhiệm vụ validator và quyết định Hold/Release/rework. | Giải thích ban đầu về tỷ lệ ảnh lỗi chưa nêu ngay quy tắc riêng của lab: mỗi `scene_leak` tính là một ảnh sai split. | AI đã đối chiếu lại GUIDE khi lập roadmap; **nhóm cần tự kiểm lại quy tắc và ghi kết quả**. |
| 3 | Lê Tuấn Khôi (2A202603024) | ChatGPT / Codex | Hỏi cách xác định dấu hiệu lỗi và chọn ngưỡng. | Các ngưỡng tỷ lệ phủ mask 50%, 80%, 95% được đưa ra để minh họa, không phải ngưỡng do repo quy định. | AI đã đối chiếu danh sách lỗi với DELIVERY; **nhóm cần kiểm guideline và tự đo ngưỡng thực tế**. |
| 4 | Lê Tuấn Khôi (2A202603024) | ChatGPT / Codex | Lập roadmap từ chuẩn bị đến báo cáo và nộp, phân tích checkpoint. | Cần đối chiếu các mốc, lệnh và điều kiện với tài liệu gốc; chưa ghi nhận lỗi cụ thể khác. | AI đã đọc GUIDE, CHECKPOINTS, RULES, RUBRIC và SUBMISSION; **nhóm chưa ghi nhận kết quả tự kiểm**. |
| 5 | Lê Tuấn Khôi (2A202603024) | ChatGPT / Codex | Tạo file HTML đẹp, dễ nhìn để nhóm đọc roadmap. | HTML là bản tóm tắt; các ô checklist không lưu trạng thái khi tải lại. | AI đã kiểm tra file có thể được phân tích cú pháp HTML; **nhóm cần mở trang và kiểm nội dung, lệnh**. |
| 6 | Lê Tuấn Khôi (2A202603024) | ChatGPT / Codex | Chia việc cho 4 người và lập đặc tả theo PRD. | Phân công là đề xuất của AI; đề gốc quy định nhóm 5–6 người, cần xác nhận nhóm 4 người với giảng viên. | AI đã đối chiếu phạm vi với tài liệu lab; **nhóm cần xác nhận số thành viên và tự duyệt phân công**. |
| 7 | Lê Tuấn Khôi (2A202603024) | ChatGPT / Codex | Tạo bốn file công việc trong `work/`, kiểm tra và ghi chú phụ thuộc artifact giữa các phần. | Các file là kế hoạch làm việc, không phải bằng chứng validator, review hay bàn giao đã hoàn thành. | AI đã đọc lại bốn file và phân tích phụ thuộc; **nhóm cần kiểm tra, phân người và xác nhận giao diện tích hợp**. |

Chưa có ảnh nào được AI review trong cuộc trò chuyện này. Nếu sau đó dùng AI để hỏi về ảnh COCO hoặc hỗ trợ các công việc khác, thêm dòng mới và ghi rõ việc kiểm tra của nhóm. Các kết luận `confirmed`/`rejected` phải do thành viên nhóm xem ảnh và ghi nhận.
