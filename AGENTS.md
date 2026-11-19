# AGENTS.md — Quy chuẩn cho AI Agent hỗ trợ nhóm Day 10

1. **Đọc trước khi làm:** Luôn tuân thủ [RULES.md](RULES.md), [RUBRIC.md](RUBRIC.md), [SUBMISSION.md](SUBMISSION.md) và [CHECKPOINTS.md](CHECKPOINTS.md).
2. **Các ranh giới tuyệt đối:**
   - `validator/` chỉ đọc thư mục `delivery/` được truyền vào, chỉ dùng Python stdlib (+ `scripts/pngutil.py`), KHÔNG dùng mạng, KHÔNG đọc `_private/`, `data_source/`, hay annotation COCO gốc.
   - KHÔNG sửa các file trong `scripts/` của giảng viên.
   - KHÔNG chạy `score_findings.py --truth-dir` để dò đáp án.
   - KHÔNG tự ý đánh dấu `confirmed`/`rejected` trong `review_log.csv` thay cho mắt người thật.
   - KHÔNG tạo commit giả dưới tên hoặc email của thành viên khác.
   - KHÔNG đưa dữ liệu nhạy cảm (`_private/`, `data_source/`, `runs/`, `*.zip`, API keys) lên GitHub hoặc Issues.
3. **Phân quyền thư mục:** Chỉ sửa đúng module được giao theo Issue; không ghi đè file của thành viên khác.
4. **Ghi nhận AI:** Mọi prompt dùng AI, chỗ AI sai và cách kiểm lại phải được ghi vào `submission/prompts.md`.
