# Dùng AI

| # | Ai dùng | Công cụ | Prompt (tóm tắt) | AI sai ở đâu | Nhóm kiểm lại thế nào |
|---|---|---|---|---|---|
| 1 | <<>> | <<>> | <<>> | <<>> | <<>> |
| 2 | Nguyễn Đức Cường | Claude Code | Đọc GUIDE Pha 5 rồi viết `tools/trace_query.py`: lấy lớp đổi quy tắc từ changelog, cảnh từ ticket, lọc ảnh theo guideline của job và box trong `labels/`, ra `trace.json` | Kế hoạch nhóm ban đầu ghi H16 do `score_findings.py` chấm; thực ra H16 là bài kiểm của `check_handover.py` | Chạy `score_findings.py` (tier_a/tier_b/notify đều 1.0) và `check_handover.py` (H16); trên đề ẩn so với `trace.json` Duy làm độc lập, khớp hoàn toàn |
| 3 | Nguyễn Đức Cường | Claude Code | Gợi ý nội dung `security.md` cho 3 ca, tìm ảnh có mặt người trong lô 5007 | AI chọn ảnh theo box `person` lớn; cần người mở ảnh xác nhận mặt nhìn rõ | Cường mở `000000004395`, `000000001296` để xác nhận trước khi ghi vào ca khuôn mặt |
