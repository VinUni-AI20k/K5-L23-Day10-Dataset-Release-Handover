Release: lab250_f95ccfbc1285_v2
Parent: lab250_f95ccfbc1285
Số ảnh: 241
Số nhãn: 1660
Guideline: v1.2 (J01-J04), v1.3 (J05-J10), lấy theo job trong jobs.csv
QC v1: 21/250 = 8,4% (11 lỗi luật + 10 lỗi gán nhãn đã xác nhận khi xem ảnh; mỗi ảnh hoặc cảnh tính một lần)
Kết luận v1: Hold — 8,4% lớn hơn ngưỡng 2% nên không Release; quyết định HOLD đã ghi vào lineage, R-021 đã train trên v1 phải xem lại hoặc train lại
Kết luận v2: Release — giữ 241/250 ảnh, tách 9 ảnh lỗi nhãn detection hoặc thiếu file sang rework_queue.csv, sửa hash, guideline và split ngay trong v2; còn 0/241 ảnh lỗi detection, 8 ảnh chỉ lỗi panoptic ở lại v2 (xem Ghi chú)
Ghi chú: v1 giữ nguyên, không sửa gì trong delivery; nhãn trong v2 chép nguyên từ v1, không sửa tay.
- Hash. Ảnh 000000004795 bị wrong_hash (chỉ sha256 của ảnh lệch, nhãn và mask khớp). Nhóm đã mở ảnh kiểm, ảnh hiển thị đầy đủ và 3 box YOLO khớp đối tượng, nên chỉ manifest v1 ghi sai; ảnh ở lại v2 và manifest.csv ghi sha256 thực tế.
- Guideline. 000000007977 (J04) metadata ghi v1.3, sửa thành v1.2 theo job; 000000016451 (J07) metadata ghi v1.2, sửa thành v1.3 theo job (truyvet.csv).
- Split. scene_601 có 4 ảnh ở val và 000000007511 ở train; chuyển 000000007511 sang val để cả cảnh nằm ở một split (truyvet.csv).
- Rework (9 ảnh, giao đúng người gán và người kiểm theo jobs.csv). A02/Q03 nhận 000000001993; A04/Q01 nhận 000000006460; A04/Q03 nhận 000000009590; A01/Q01 nhận 000000009914, 000000012280; A03/Q02 nhận 000000021839, 000000022589, 000000022892 và 000000024919 (thiếu file ảnh, cần bàn giao lại).
- Báo team panoptic (8 ảnh chỉ lỗi panoptic, nhãn detection vẫn đúng nên ở lại v2). category_swap ở 000000001353, 000000006723, 000000018380, 000000020553, 000000025560; instance_merge ở 000000011051; thing_overlap ở 000000011813, 000000023230.
