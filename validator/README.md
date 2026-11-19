# Validator của nhóm

Chạy từ thư mục gốc repo. Trên Windows PowerShell, dùng `py` thay cho `python3`.

```sh
python3 validator/validate.py runs/r3007/delivery --out runs/r3007/rules.json --candidates runs/r3007/candidates.json
```

Validator chỉ đọc thư mục delivery được truyền vào, dùng thư viện chuẩn và chạy ngoại tuyến. Xem [GUIDE.md](../GUIDE.md) và [RULES.md](../RULES.md).

## Giao diện cho nhóm

| Người | File và hàm |
|---|---|
| Trần Phạm Hoàng Phong | `rulefiles.py` có `find_errors(delivery)` để kiểm file và metadata. |
| Trần Đình Quang Vinh | `rulelabels.py` có `find_errors(delivery)` để kiểm nhãn YOLO và panoptic. |
| Phùng Danh Khoa | `labelmatch.py` có `build_matches(delivery)` để chuẩn bị dữ liệu ghép theo ảnh và `find_candidates(matches)` để tìm lệch lớp, thiếu box. |
| Đinh Quốc Tiến | `maskchecks.py` có `find_candidates(matches)` để tìm box lệch và vật thể bị gộp. Khoa và Tiến thống nhất cấu trúc `matches` trước khi viết hai hàm kiểm. |
| Nguyễn Công Quý | `validate.py` gọi các hàm, gộp lỗi luật và ghi hai file JSON. |

`delivery` là một `pathlib.Path`. Mỗi hàm `find_errors` trả về danh sách mục có `type` và `target`. Với `scene_leak`, `target` là mã cảnh. Các lỗi còn lại dùng tên ảnh bỏ đuôi.

Hai hàm `find_candidates` dùng chung kết quả ghép và trả về danh sách mục có `image` (tên ảnh bỏ đuôi), `type` và thông tin hỗ trợ xem ảnh khi có. Có thể dùng `class_disagreement` cho ca lệch lớp chưa xác định nguồn sai. Khi xem ảnh, chọn `class_swap` hoặc `category_swap` để ghi lỗi đã xác nhận.

`--out` ghi lỗi luật. Thêm `--candidates` để chạy bước đối chiếu và ghi hàng đợi xem ảnh. Sau khi cả nhóm xem ảnh, gộp kết quả:

```sh
python3 scripts/merge_review.py --rules runs/r3007/rules.json --review runs/r3007/review_log.csv --out runs/r3007/errors.json
```
