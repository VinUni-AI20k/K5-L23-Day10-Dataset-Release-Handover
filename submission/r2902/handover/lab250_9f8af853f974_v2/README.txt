Release: lab250_9f8af853f974_v2
Parent: lab250_9f8af853f974
Số ảnh: 242
Số nhãn: 1664
Guideline: v1.2 (J01-J02-J03), v1.3 (J04-J05-J06-J07-J08-J09-J10)
QC v1: 15/250 = 6.0%
Kết luận v1: Hold — 15/250 lỗi = 6.0%, vượt ngưỡng 2%.
Kết luận v2: Release — loại 8 ảnh lỗi detection vào rework, chưa đưa các ảnh đó vào lô bàn giao.
Ghi chú: scene_226 thống nhất split train (000000025228 val -> train); wrong_hash 000000005001 đã được người vận hành mở ảnh xác nhận bình thường, hash SHA256=99600c56dc25c72dc1cc1d1f2b09aa33b97142560b54d034fa83a38fcf3c5b0f; guideline lấy theo jobs.csv (không dùng guideline_version trong metadata); rework: 000000000885 (A05/Q02), 000000009378 (A04/Q02), 000000012639 (A05/Q01), 000000014888 (A01/Q03), 000000016228 (A03/Q03), 000000017207 (A03/Q03), 000000019924 (A03/Q03), 000000023937 (A02/Q03); lỗi panoptic giữ detection ở v2, báo team panoptic: 000000007818: category_swap, 000000014007: thing_overlap, 000000015440: instance_merge, 000000024243: invalid_category_id.
