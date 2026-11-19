# Challenge Runbook (40-Minute / 60-Minute Window)

## Mốc thời gian chuẩn (40 phút đề ẩn / hoặc 60 phút nếu giảng viên mở rộng)

1. **Phút 0–5 | Preflight + Rule Validator + Cross-check + Triage:**
   ```powershell
   python tools/qc_factory.py doctor
   python tools/qc_factory.py challenge --input delivery --out-dir submission/de_an --serve
   ```
   - Tự động kiểm tra `preflight_report.json`, chạy `validator/validate.py` (9 lỗi luật + ứng viên), phân loại `EASY/MEDIUM/HARD` ra `triage.csv`, dựng `trace.json` và mở Review UI tại `http://127.0.0.1:8765/`.

2. **Phút 5–30 | Human Visual Review song song:**
   - Mở `http://127.0.0.1:8765/`.
   - Dùng phím tắt: `C` (Confirm), `R` (Reject), `S` (Skip), `←`/`→` chuyển ảnh.
   - Chọn đúng `class_swap` (box sai) hoặc `category_swap` (mask sai), ghi chú mô tả **thấy gì trong ảnh** (tối thiểu 20 ký tự).

3. **Phút 30–36 | Finalize & Kiểm tra định dạng:**
   ```powershell
   python tools/qc_factory.py finalize --run submission/de_an
   ```
   - Xuất `submission/de_an/review_log.csv` và gộp lỗi `confirmed` vào `submission/de_an/errors.json`.
   - Kiểm tra đủ 4 file trong `submission/de_an/`: `errors.json`, `candidates.json`, `review_log.csv`, `trace.json`.

4. **Phút 36–40 | Commit & Push (chỉ khi người dùng/nhóm xác nhận nộp):**
   - Đảm bảo **không** commit thư mục `delivery/` của đề ẩn.
   - Kiểm tra `git status` trước khi commit/push lên repo nhóm (`origin`).
