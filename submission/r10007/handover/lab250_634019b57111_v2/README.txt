Release: lab250_634019b57111_v2
Parent: lab250_634019b57111
Số ảnh: 236
Số nhãn: 1666
QC v1: 23/250 ảnh lỗi (9.2%)
Kết luận v1: Hold
Kết luận v2: Release

Ghi chú:
- Đã tách 14 ảnh lỗi gán nhãn detection và file sang rework_queue.csv để phân công gán lại đúng người theo jobs.csv.
- Đã khắc phục lỗi rò rỉ phân chia train/val (scene_leak) và đồng bộ guideline theo phiên bản chuẩn của job trong truyvet.csv.
- Các ảnh có lỗi panoptic (invalid_category_id, thing_overlap, category_swap, instance_merge) được giữ lại an toàn trong v2 vì nhãn detection vẫn chính xác; đã lưu ý thông báo cho đội ngũ panoptic xử lý riêng.
