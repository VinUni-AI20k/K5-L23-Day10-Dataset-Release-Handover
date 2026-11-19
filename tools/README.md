# Công cụ xem ảnh (nhóm 30 — Phạm Huỳnh)

Vẽ **box detection** (đỏ, `D<số dòng>:lớp`) và **viền segment panoptic** (màu khác, `P:lớp`) lên ảnh để review bằng mắt.
Vàng = box/segment bị validator nghi. Có Pillow là chạy được (`pip install pillow`). Không phải validator.

```bash
# vài ảnh / một cảnh
python tools/viewer.py runs/r30007/delivery 000000004765
python tools/viewer.py runs/r30007/delivery --scene scene_497

# hàng đợi ứng viên, chia cho 5 người
python tools/viewer.py runs/r30007/delivery --candidates runs/r30007/candidates.json --semantic-only \
    --assign "Tung,Huong,Viet,Huynh,Khanh"

# đề ẩn
python tools/viewer.py delivery --candidates submission/de_an/candidates.json --semantic-only --assign "..."
```

Kết quả ở `<delivery>/../review_out/` (đã gitignore):
- `<ảnh>__<type>.png`: trái ảnh gốc, giữa ảnh có nhãn, phải (nếu có) phóng to vùng bị nghi.
- `index.html`: mở bằng trình duyệt, lọc theo người xem, chọn confirmed/rejected, ghi chú
  (cảnh báo khi < 20 ký tự / trùng nhau), bấm **Tải review_log.csv**. Trạng thái lưu trong trình duyệt.
- `phan_cong.csv`: ai xem ảnh nào.

`candidates.json`: `{"candidates": [{"target": "<ảnh>", "type": "class_swap", "box": 2, "segment": 123456, "note": "..."}]}`.
`box` (chỉ số dòng trong labels, 0-based) và `segment` (id panoptic) là tuỳ chọn, có thì tool tô vàng và phóng to.

Ghi chú review: nói **thấy gì** và **nguồn nào đúng**, vd `xe tải thùng kín, detection D2 ghi car; panoptic ghi truck đúng`.
