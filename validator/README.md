# Validator của nhóm

Viết `validate.py` ở đây. Giao diện cố định:

```
python validator/validate.py <thư_mục_delivery> --out <errors.json> [--candidates <candidates.json>]
```

Chỉ đọc thư mục delivery được truyền vào; chỉ thư viện chuẩn; không mạng. Xem [GUIDE.md](../GUIDE.md) Pha 1–2 và [RULES.md](../RULES.md).

---

## Module Phần 2: `cross_check.py` (Người 2 — Hà Khánh)

`validator/cross_check.py` thực hiện đối chiếu **Detection (YOLO) ↔ Panoptic** (`REV-01` .. `REV-06`) để sinh `candidates.json`:
- Thuần thư viện chuẩn Python + `scripts/pngutil.py` (**không dùng Pillow**, không đọc `_private/` hay `data_source/`, không dùng mạng).
- Ghép lớp qua **tên lớp** (`classes.txt` ↔ `panoptic.json`), chỉ xét segment `isthing=1` và bỏ qua `iscrowd=1`.
- Kết hợp IoU bbox và tỷ lệ pixel mask nằm trong box (`mask_in_box`) để sinh ứng viên cho 4 nhóm dấu hiệu: `class_swap`/`category_swap`, `bbox_drift`, `missing_box`, `instance_merge`.
- Chống báo nhầm `instance_merge` trên cặp `duplicate_box` và xử lý an toàn tên ảnh đề ẩn `img_0001` cũng như ảnh có lỗi luật (`missing_image`, `invalid_class`, `invalid_category_id`).

### Chạy độc lập để đo trên lô sạch hoặc kiểm thử trước khi tích hợp

```powershell
py validator/cross_check.py runs/clean/delivery --out runs/clean/candidates.json
py validator/cross_check.py runs/r<seed>/delivery --out runs/r<seed>/candidates.json
```

Có thể truyền `--thresholds-json <file.json>` để thử bộ ngưỡng mới khi hiệu chỉnh trên `runs/clean`.

### Giao diện tích hợp vào `validator/validate.py` (phối hợp Người 1 & Người 2)

> **Điểm dừng:** Chưa tự tạo `validator/validate.py` trên nhánh này để tránh ghi đè phần của Người 1. Khi hai người chốt chủ sở hữu entrypoint `validator/validate.py`, chỉ cần gọi:

```python
from pathlib import Path
from cross_check import write_candidates

# Trong main() của validator/validate.py sau khi parse --candidates:
if args.candidates:
    write_candidates(Path(args.delivery), Path(args.candidates))
```

