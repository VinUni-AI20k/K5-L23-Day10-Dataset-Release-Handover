# Dùng AI

| # | Ai dùng | Công cụ | Prompt (tóm tắt) | AI sai ở đâu | Nhóm kiểm lại thế nào |
|---|---|---|---|---|---|
| 1 | Đỗ Quang Tùng (dqtung1703) | Antigravity AI | Rà soát `validator/validate.py` và `validator/rules_file_det.py`, tìm nguy cơ FP/FN cho 5 lỗi luật (`missing_image`, `wrong_hash`, `invalid_class`, `bbox_out_of_bounds`, `duplicate_box`) và giải thích ngưỡng. | AI ban đầu nghi ngờ cần kiểm cả `label_sha256` / `mask_sha256` cho `wrong_hash` và tự tạo thêm các script phụ trong `tools/` ngoài yêu cầu nộp bài của repo. | Yêu cầu bỏ thư mục `tools/`; đối chiếu `docs/DELIVERY.md` và kiểm trực tiếp trên lô sạch `runs/clean` (50 ảnh, ra 0 lỗi luật), `runs/r30007` (6 lỗi: `missing_image` 2, `wrong_hash` 1, `bbox_out_of_bounds` 1, `duplicate_box` 2 — kiểm độc lập số file ảnh thiếu bằng PowerShell khớp 2=2) và `runs/r30008` (7 lỗi, bắt được 2 `invalid_class`). |
| 2 | <<>> | <<>> | <<>> | <<>> | <<>> |
