# Validator của nhóm (Data Validation + Annotation Review)

Giao diện CLI thống nhất (chỉ đọc thư mục `delivery/` truyền vào, thuần thư viện chuẩn Python + `scripts/pngutil.py`, không dùng Pillow, không dùng mạng):

```powershell
py -X utf8 -B validator/validate.py runs/r12007/delivery --out runs/r12007/rules.json --candidates runs/r12007/candidates.json
py -X utf8 -B -m unittest tests/test_validation.py tests/test_cross_check.py -v
```

- `--out` chỉ ghi **lỗi luật** (`rules.py`); **không** tự chuyển ứng viên gán nhãn sang lỗi đã xác nhận.
- `--candidates` ghi danh sách **ứng viên** đối chiếu Detection ↔ Panoptic (`cross_check.py`) để cả nhóm mở ảnh review bằng mắt, rồi gộp kết quả bằng `scripts/merge_review.py`.

---

## Phần 1: `rules.py` — Data Validation (Người 1 — Nguyễn Trường Giang)

`rules.py` cung cấp `validate_rules(delivery) -> {"errors": [...]}`. Kết quả được loại trùng, sắp xếp ổn định theo `type`/`target`. Target là tên ảnh không đuôi; riêng `scene_leak` dùng `scene_id`. Không phụ thuộc tên ảnh dạng số, seed hoặc đáp án.

### Chín kiểm tra luật
- `missing_image`: file ảnh trong manifest không tồn tại; không báo thêm `wrong_hash` cho file thiếu.
- `wrong_hash`: SHA-256 đọc từ bytes của cả image, label và mask, so với manifest.
- `invalid_class`: class ID phải có trong `classes.txt`.
- `bbox_out_of_bounds`: kiểm bốn cạnh sau khi đổi tâm/kích thước sang cạnh; kích thước dương, tọa độ hữu hạn (dung sai `1e-6` cho làm tròn YOLO).
- `duplicate_box`: cùng class, chênh kích thước tối đa `0,01` pixel, tâm chênh tối đa `2` pixel mỗi trục; không chỉ dựa trên IoU.
- `scene_leak`: scene có cả `train` và `val`/`validation`.
- `guideline_mismatch`: `guideline_version` của ảnh khác `guideline` của `job_id` trong `jobs.csv`.
- `invalid_category_id`: `category_id` không có trong `categories` của `panoptic.json`.
- `thing_overlap`: với category `isthing`, `area` lớn hơn số pixel mang segment ID (`R + 256*G + 65536*B`, bỏ qua ID `0`).

Đường dẫn manifest thoát khỏi `delivery/` bị từ chối; không cho phép ghi `--out` hoặc `--candidates` vào trong `delivery/`. Báo cáo chi tiết phần 1: [DATA_VALIDATION.md](../submission/DATA_VALIDATION.md).

---

## Phần 2: `cross_check.py` — Annotation Review Candidates (Người 2 — Hà Khánh)

`cross_check.py` cung cấp `find_candidates(delivery)` và `write_candidates(delivery, out_path)`, đã được tích hợp trực tiếp vào cờ `--candidates` của `validator/validate.py`:
- Ghép lớp qua **tên lớp** (`classes.txt` ↔ `panoptic.json`), chỉ xét segment `isthing=1` và bỏ qua `iscrowd=1`.
- Đếm pixel mask bằng `scripts/pngutil.py` để tính `mask_in_box` bổ sung cho IoU bbox.
- **Khóa ghép 1-1 chắc (`IoU ≥ 0.80`, `mask_in_box ≥ 0.90`) trước khi tìm `instance_merge`** nhằm tránh báo nhầm các vật cùng lớp chồng lấn góc nhìn trước/sau (như ca 3 người chồng nhau trong ảnh bóng chày).
- Sinh ứng viên cho 4 nhóm dấu hiệu: `class_swap`/`category_swap`, `bbox_drift`, `missing_box`, `instance_merge`; xử lý an toàn tên đề ẩn `img_0001` và ảnh có lỗi luật (`missing_image`, `invalid_class`, `invalid_category_id`, `duplicate_box`).
- Ngưỡng mặc định (`DEFAULT_THRESHOLDS`) đã hiệu chỉnh dựa trên đo phân bố thực tế trên lô sạch `runs/clean` (50 ảnh, 435 vật sạch, `0` ứng viên nhiễu).

Có thể chạy độc lập để thử ngưỡng mới trên lô sạch:
```powershell
py -X utf8 validator/cross_check.py runs/clean/delivery --out runs/clean/candidates.json [--thresholds-json thresh.json]
```
