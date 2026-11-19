# P4 — Dataset v2, Manifest & Handover

- **Phụ trách chính:** Đỗ Anh Hoàng (`2A202604061` · GitHub: `@AnhHoangDepTrai`)
- **Phạm vi module:** `handover/builder.py`, `handover/__init__.py`, `tests/test_handover_builder.py`
- **Mục tiêu kỹ thuật:**
  1. Tạo lập gói bàn giao v2 (`runs/r<seed>/handover/<release_id>_v2/`) phục vụ cho mô hình Object Detection mà **tuyệt đối không sửa đè lên lô v1**.
  2. Phân loại chuẩn xác 3 luồng xử lý lỗi:
     - **Luồng Rework:** Các lỗi nhãn detection hoặc thiếu file (`missing_image`, `invalid_class`, `bbox_out_of_bounds`, `duplicate_box`, `class_swap`, `bbox_drift`, `missing_box`) -> Tách ra `rework_queue.csv`, loại khỏi `images/` và `labels/` của v2, phân công lại đúng `annotator` và `reviewer` theo `jobs.csv`.
     - **Luồng Sửa kỹ thuật trực tiếp trong v2:**
       * `wrong_hash`: Mở file ảnh kiểm tra bytes nguyên vẹn (valid JPEG header), tính lại sha256 chuẩn vào `manifest.csv`.
       * `guideline_mismatch`: Đồng bộ lại guideline theo chuẩn job trong `jobs.csv` vào `truyvet.csv`.
       * `scene_leak`: Quy hoạch thống nhất toàn bộ các ảnh trong cùng scene về split đa số (`train`), loại bỏ rò rỉ dữ liệu.
     - **Luồng Panoptic độc lập:** Các lỗi chỉ xảy ra ở phía panoptic (`invalid_category_id`, `thing_overlap`, `category_swap`, `instance_merge`) thì nhãn detection vẫn chuẩn xác, ảnh được **giữ lại trong v2** và ghi chú bàn giao cho team panoptic.
  3. Tạo đầy đủ 7 thành phần cấu trúc:
     - `images/`: Tập hợp ảnh sạch.
     - `labels/`: Tập hợp nhãn YOLO sạch, giữ nguyên byte sha256 (không sửa tay).
     - `rework_queue.csv`: Danh sách ảnh cần gán lại kèm người phụ trách.
     - `manifest.csv`: Bảng sha256 mọi file ảnh và nhãn trong v2.
     - `label_summary.csv`: Thống kê số lượng box từng class và tổng `TOTAL`.
     - `truyvet.csv`: Bảng truy vết nguồn gốc từng ảnh theo job, annotator, reviewer, guideline chuẩn.
     - `README.txt`: Báo cáo release theo mẫu chuẩn với mẫu số QC v1, kết luận v1/v2 và giải trình chi tiết.
  4. Đóng gói zip tái lập và file `.sha256` bằng `scripts/pack_release.py`.
  5. Ghi sự kiện `release` v2 với quan hệ `parent` trỏ về v1 trong `lineage.jsonl`.
  6. Vượt qua bộ kiểm định tự động `scripts/check_handover.py` (H1–H15).

## Hướng dẫn vận hành

```bash
python handover/builder.py --run runs/r9007
```
