# Dùng AI

| # | Ai dùng | Công cụ | Prompt (tóm tắt) | AI sai ở đâu | Nhóm kiểm lại thế nào |
|---|---|---|---|---|---|
| 1 | Tuấn Anh | Claude Code | Viết `validator/validate.py` bắt 9 lỗi luật theo docs/DELIVERY.md, chỉ đọc delivery, chỉ thư viện chuẩn + pngutil | Bản đầu chỉ so hash của ảnh, bỏ sót hash của nhãn/mask (định nghĩa `wrong_hash` là "sha256 không phải của file đó") → đã sửa để kiểm cả 3 | Chạy trên lô sạch `runs/clean` (0 lỗi luật), seed 76 và 3 seed thử (11, 42, 93): đủ 9 loại xuất hiện, không ảnh nào bị gắn >1 lỗi; grep code không có `_private`, `data_source`, mạng, tên ảnh cứng; F1 đo bằng `score_findings.py` seed 76: lỗi luật ≈ 1.0 (tổng ≈ 0.7 vì chưa có lỗi gán nhãn); seed 11: lỗi luật ≈ 1.0 (13 lỗi); lô sạch: 0 lỗi luật |
