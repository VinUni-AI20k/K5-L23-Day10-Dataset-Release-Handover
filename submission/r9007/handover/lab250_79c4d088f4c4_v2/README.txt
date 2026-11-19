Release: lab250_79c4d088f4c4_v2
Parent: lab250_79c4d088f4c4
Số ảnh: 244
Số nhãn: 1669
Guideline: v1.2 (J01–J03), v1.3 (J04–J10)
QC v1: 14/250 (5.6%)
Kết luận v1: Hold — tỉ lệ lỗi 14/250 = 5.6% vượt ngưỡng 2% (<= 5/250).
Kết luận v2: Release — đã tách 6 ảnh lỗi detection/thiếu file vào rework_queue.csv, sửa metadata/hash/split/guideline trong v2; còn lại 244/250 ảnh sạch nhãn detection.
Ghi chú: Đã sửa trực tiếp trong v2 (guideline_mismatch:000000012120, guideline_mismatch:000000013177, scene_leak:scene_818, wrong_hash:000000011760, wrong_hash:000000024144): cập nhật sha256 thực sau khi kiểm ảnh, chuẩn hoá guideline theo job, và gộp scene bị leak về một split đa số. Ảnh rework giao đúng annotator/reviewer theo jobs.csv. Ảnh lỗi chỉ ở panoptic (giữ lại v2, báo team panoptic): 000000009590 (invalid_category_id), 000000016249 (thing_overlap), 000000023781 (thing_overlap).
