Release: lab250_79c4d088f4c4_v2
Parent: lab250_79c4d088f4c4
Số ảnh: 243
Số nhãn: 1662
Guideline: v1.2 (J01-J03), v1.3 (J04-J10)
QC v1: 16/250 = 6.4%
Kết luận v1: Hold — Tỉ lệ ảnh lỗi 6.4% (16/250) vượt ngưỡng cho phép 2.0%
Kết luận v2: Release — Đã tách 7 ảnh lỗi detection sang rework_queue.csv, giữ 243 ảnh chuẩn, sửa hash/guideline/split tự động, nhãn detection không sửa tay
Ghi chú: Cảnh lỗi scene_leak (scene_818) đã được chuẩn hóa toàn bộ các ảnh con về cùng split train, loại bỏ triệt để rò rỉ dữ liệu giữa tập huấn luyện và đánh giá. ; Ảnh lỗi wrong_hash (000000011760, 000000024144) đã được mở kiểm tra bytes thực tế, xác nhận file ảnh nguyên vẹn (valid JPEG header b'\xff\xd8\xff\xe0') và chỉ manifest v1 ghi sai sha256; đã tính lại mã băm chuẩn xác vào manifest.csv. ; Ảnh lỗi guideline_mismatch (000000012120, 000000013177) đã được đồng bộ chuẩn theo guideline ghi ở job trong jobs.csv vào truyvet.csv. ; Tách 7 ảnh lỗi nhãn detection (000000002923, 000000008277, 000000011197, 000000013774, 000000020571, 000000022935, 000000024610) vào rework_queue.csv và giao lại cho đúng annotator và reviewer theo jobs.csv để gán lại. ; Các ảnh chỉ lỗi panoptic (000000009590, 000000016249, 000000016502, 000000023781) có nhãn detection hoàn toàn chính xác nên được giữ lại trong v2; đã xuất danh sách bàn giao và thông báo cho team panoptic xử lý riêng.
