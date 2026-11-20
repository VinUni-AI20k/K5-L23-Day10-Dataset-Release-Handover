Release: lab250_7fa680a7413b_v2
Parent: lab250_7fa680a7413b
Số ảnh: 239
Số nhãn: 1638
QC v1: 21/250 (8.4%)
Kết luận v1: Hold — tỷ lệ vượt ngưỡng 2%.
Kết luận v2: Release — bản detection sau khi loại ảnh rework và sửa metadata handover.
Ghi chú:
- wrong_hash: đã mở ảnh 000000005600; ảnh hiển thị bình thường, dùng bytes/hash hiện tại trong manifest v2.
- guideline_mismatch: truyvet.csv lấy guideline từ jobs.csv; giữ nhãn gốc, không sửa tay.
- scene_leak: toàn bộ scene_801 được gán split val trong truyvet.csv (split chiếm đa số ở v1).
- Detection có lỗi đã chuyển sang rework_queue.csv và bị loại khỏi v2; nhãn YOLO không bị sửa tay.
- Lỗi chỉ thuộc panoptic được giữ trong release detection và cần chuyển team panoptic: category_swap:000000007278, category_swap:000000025394, instance_merge:000000015338, instance_merge:000000017714, thing_overlap:000000007795, thing_overlap:000000012748.
- Ảnh thiếu 000000021839 không có trong v2; đã giao lại theo jobs.csv.
