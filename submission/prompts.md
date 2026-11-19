# Nhật ký dùng AI (`prompts.md`)

> Ghi lại prompt đã dùng, chỗ AI làm sai/chưa đủ và cách nhóm tự kiểm chứng lại theo [RULES.md](../RULES.md).

## 1. Thiết kế & nâng cấp `qc_factory_day10/` + `validator/validate.py`
- **Prompt / Yêu cầu:** Tái sử dụng kiến trúc từ CVAT Factory (`cache`, `shapestore`, `HTML review`, `frame_profiler`) sang nền tảng QC thuần Python stdlib cho Day10 (`qc_factory_day10/`, `tools/qc_factory.py`, `tools/build_handover.py`), giữ `validator/validate.py` 100% stdlib, bổ sung `instance_merge` và bảo vệ path traversal.
- **Chỗ AI sai / cần sửa:**
  1. Test tổng hợp ban đầu dùng ảnh giả lập `4x4` với 2 box cách tâm `2px`, khiến rule `duplicate_box` (`DUP_CENTER_TOL_PX = 2`) bắt nhầm thành box trùng; nhóm đã sửa fixture lên `20x20` để tách biệt `duplicate_box` và `instance_merge`.
  2. `ReviewStore._connect()` dùng `with sqlite3.connect(...)` trên Windows không tự đóng file descriptor sau transaction, gây `WinError 32` khi cleanup thư mục tạm; đã sửa sang `@contextmanager` gọi `conn.close()` tường minh.
- **Cách kiểm lại:** Chạy `python -m pytest tests/validator/test_validator_rules.py tests/test_qc_factory.py -v` (7/7 PASS), `python tools/qc_factory.py doctor`, `python tools/qc_factory.py benchmark` trên `runs/clean` và `runs/r9007`, và `python scripts/check_handover.py --run runs/r9007`.

## 2. Quy tắc con người review ảnh
- Toàn bộ `review_log.csv` (mục H3) **không** dùng AI tự điền `confirmed`/`rejected`; thành viên nhóm mở ảnh thật qua Review UI (`http://127.0.0.1:8765/`) để tự xác nhận và ghi chú ≥ 20 ký tự.
