# Factory Reuse Architecture (`qc_factory_day10`)

Xem bảng chi tiết từng module tại [factory_reuse_matrix.md](factory_reuse_matrix.md).

## Nguyên tắc tách lớp (Rule Compliance)
1. **`validator/validate.py`**: Giữ nguyên **100% Python stdlib** (+ `scripts/pngutil.py`), chạy offline, chỉ đọc thư mục `delivery/` được truyền vào.
2. **`qc_factory_day10/`**: Nền tảng QC Intelligence Engine tái sử dụng kiến trúc từ `cvat` Factory (`cache`, `shapestore`, `review HTML`, `frame profiler`, `geometry/overlap`), nhưng **không** phụ thuộc PyTorch/OpenCV/Pillow/network để chạy được trên mọi máy nhóm trong 40–60 phút thi.
3. **`tools/qc_factory.py`**: CLI một lệnh (`doctor`, `benchmark`, `challenge`, `finalize`) điều phối toàn bộ pipeline từ preflight đến xuất `submission/de_an/`.
