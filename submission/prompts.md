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

## 3. Thiết kế P3 Release Gate (`release/`) & P4 Dataset v2 Handover (`handover/`) — Đỗ Anh Hoàng
- **Người thực hiện:** Đỗ Anh Hoàng (`2A202604061` · GitHub: `@AnhHoangDepTrai`)
- **Prompt / Yêu cầu:** Thiết kế module `release/gate.py` đánh giá ngưỡng 2% (Day 7) trên lô v1 và ghi nhận sự kiện `decision` (HOLD/RELEASE), truy vấn blast radius của `R-021` qua `scripts/lineage.py`. Thiết kế `handover/builder.py` tự động hóa toàn bộ quy trình xây dựng gói bàn giao v2 không sửa đè v1, phân loại đúng 3 luồng (rework, sửa kỹ thuật trực tiếp, panoptic độc lập), sinh đầy đủ 7 thành phần cấu trúc (images, labels, rework_queue.csv, manifest.csv, label_summary.csv, truyvet.csv, README.txt), đóng gói zip tái lập `.sha256`, ghi nhận lineage `release` v2 với `parent`, và vượt qua bộ kiểm `check_handover.py` (H1–H15).
- **Chỗ AI làm sai / chưa đủ:**
  1. Ban đầu AI xếp tất cả các ảnh có lỗi trong `errors.json` vào `rework_queue.csv`. Tuy nhiên, các lỗi chỉ thuộc panoptic (`invalid_category_id`, `thing_overlap`, `category_swap`, `instance_merge`) thì nhãn detection của ảnh vẫn hoàn toàn hợp lệ, do đó ảnh phải ở lại trong v2 (báo team panoptic ở phần Ghi chú README) thay vì tách sang rework (sẽ bị FAIL H5).
  2. Với `scene_leak`, AI ban đầu giữ nguyên metadata dẫn đến v2 vẫn bị scene xuất hiện ở cả train và val (FAIL H11). Đã bổ sung logic chuẩn hóa tự động toàn bộ ảnh trong scene về cùng một split (split đa số/train).
  3. Giá trị guideline trong `truyvet.csv` nếu lấy từ metadata của ảnh sẽ bị sai khi gặp lỗi `guideline_mismatch`. Đã sửa để guideline luôn truy xuất từ `jobs.csv` làm single source of truth (đạt H10).
- **Cách kiểm lại:** Viết unit tests (`tests/test_release_gate.py`, `tests/test_handover_builder.py` 4/4 PASS), chạy thực tế trên `runs/r9007`, xác nhận `python scripts/check_handover.py --run runs/r9007` đạt tuyệt đối 15/15 PASS ở các tiêu chí H1–H15.

