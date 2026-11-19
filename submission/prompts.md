# Nhật ký sử dụng Trợ lý AI (Prompts Log)

| # | Ai dùng | Công cụ | Prompt (tóm tắt) | AI sai ở đâu | Nhóm kiểm lại thế nào |
|---|---|---|---|---|---|
| 1 | Hoàng Thuận Thiện (TV7) | Antigravity AI | Hướng dẫn phân rã quy trình 6 pha và xây dựng ma trận phân công 7 thành viên | Gợi ý phân công ban đầu chỉ chia theo mốc thời gian (T+15', T+55') mà chưa theo luồng sự kiện chuyển giao từng bước (Trigger/Handoff) | Yêu cầu AI tái cấu trúc lại thành quy trình 16 bước tác chiến rõ ràng người trước bàn giao cho người sau |
| 2 | Thành viên 1 | Antigravity AI | Viết hàm kiểm tra duplicate_box theo tọa độ YOLO | Ban đầu AI chỉ dùng IoU > 0.5 dẫn đến báo nhầm các cặp vật thể tự nhiên đứng che khuất nhau trong COCO | Sửa lại thuật toán: kiểm tra độ lệch kích thước < 5% và độ lệch tâm chỉ 1-2 pixel theo đúng đặc trưng lỗi gài |
| 3 | Thành viên 2 | Antigravity AI | Đọc mã màu RGB của mask PNG để tính segment ID | AI gợi ý dùng thư viện cv2 và PIL (bị cấm theo quy chế lab chỉ dùng thư viện chuẩn) | Yêu cầu AI chuyển sang dùng module pngutil.py thư viện chuẩn có sẵn của giảng viên |
| 4 | Thành viên 6 | Antigravity AI | Truy vết ticket của team AI từ ticket.md và changelog.md | AI lọc theo trường guideline_version ghi trong metadata.json của ảnh | Nhóm phát hiện trong metadata có lỗi guideline_mismatch, nên bắt buộc phải lấy guideline chuẩn theo jobs.csv |
