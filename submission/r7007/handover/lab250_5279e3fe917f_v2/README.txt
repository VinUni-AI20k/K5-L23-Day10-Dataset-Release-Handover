Release: lab250_5279e3fe917f_v2
Parent: lab250_5279e3fe917f
Số ảnh: 243
Số nhãn: 1694
Guideline: v1.2 (J01-J04), v1.3 (J05-J10)
QC v1: 16/250 = 6,4%
Kết luận v1: Hold — 6,4% ảnh lỗi > ngưỡng 2% (Day 7)
Kết luận v2: Release — tách 7 ảnh lỗi nhãn detection sang rework; sửa hash, guideline theo job, split theo cảnh; nhãn còn lại giữ nguyên như v1
Ghi chú: split: đưa cả cảnh về một split (scene_593 -> train) | hash: đã mở ảnh kiểm, ảnh còn nguyên, chỉ manifest v1 ghi sai; manifest.csv v2 tính lại sha256 (000000016010) | guideline: ghi theo job trong jobs.csv thay cho guideline ghi sai ở ảnh (000000011615, 000000024567) | rework: 7 ảnh lỗi nhãn detection/thiếu file tách khỏi v2, giao lại người gán+kiểm theo job (A01+Q01, A03+Q02, A04+Q01, A04+Q02, A05+Q01), xem rework_queue.csv | lỗi chỉ ở panoptic, nhãn detection vẫn đúng nên ảnh ở lại v2, báo team panoptic: 000000006471 (category_swap), 000000011511 (thing_overlap), 000000015079 (instance_merge), 000000018491 (invalid_category_id), 000000018833 (invalid_category_id)
