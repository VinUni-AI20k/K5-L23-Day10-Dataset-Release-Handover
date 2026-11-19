# Validator của nhóm

Viết `validate.py` ở đây. Giao diện cố định:

```
python validator/validate.py <thư_mục_delivery> --out <errors.json> [--candidates <candidates.json>]
```

Chỉ đọc thư mục delivery được truyền vào; chỉ thư viện chuẩn; không mạng. Xem [GUIDE.md](../GUIDE.md) Pha 1–2 và [RULES.md](../RULES.md).

## P1a–P1c: tích hợp cho nhóm

- `--out` chỉ ghi `{"errors": [{"type": "...", "target": "..."}]}` (lỗi luật).
- `--candidates` ghi list `[{"image", "type", "score", "detail"}]` từ crosscheck.
- `common.load(delivery_dir)` trả dict `ctx`; hợp đồng các khóa và box xem docstring `common.py`.
- `images` và `annotations` tra bằng tên ảnh như manifest; ID panoptic được nối qua `image_id`, không ép tên ảnh thành số.
- `common.yolo_to_pixel(x, y, w, h, width, height)` trả `(left, top, right, bottom)` theo pixel, không clip cạnh.
- Mỗi module luật cung cấp `check(ctx) -> list[dict]`. Ưu tiên lỗi ảnh: file → metadata → detection → panoptic. `scene_leak` là lỗi cảnh, được giữ riêng.
- `crosscheck.candidates(ctx, skip_images)` chỉ bỏ qua tên ảnh có lỗi luật, không bỏ cả cảnh rò split.
- `rules_panoptic.py` và `crosscheck.py` hiện là **stub**. Núi thay phần hàm và đổi `IMPLEMENTED = True` khi đã triển khai. CLI in cảnh báo cho đến lúc đó.
- Dung sai cạnh box: 0.01 chuẩn hóa. Box lặp: cùng lớp, chênh kích thước ≤ 0.01 pixel và chênh tâm mỗi trục ≤ 2.01 pixel; cần kiểm chứng tiếp trên lô sạch/seed phụ ở P1e.
- Lỗi cấu trúc dữ liệu không thuộc 7 loại trên (YOLO không đủ cột, số không hữu hạn, thiếu tham chiếu) làm CLI trả mã 2 kèm thông báo; không im lặng bỏ qua.
- Không ghi output vào delivery. Không dùng Pillow, mạng, dữ liệu gốc hoặc `_private/`.

Chạy seed nhóm:

```powershell
python -X utf8 validator/validate.py runs/r13007/delivery --out runs/r13007/rules.json --candidates runs/r13007/candidates.json
python -X utf8 -m unittest discover -s tests -p test_validator.py -v
```

`candidates.json` rỗng khi crosscheck còn stub không có nghĩa dataset không có lỗi gán nhãn. Chờ P1d trước khi đánh giá đủ 9 luật ở P1e.
