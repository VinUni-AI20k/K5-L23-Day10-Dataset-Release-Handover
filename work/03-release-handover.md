# Người 3: Release và Handover

## Mục tiêu

Đưa ra quyết định QC theo quy tắc lab, tạo lô detection v2 và hồ sơ bàn giao có thể kiểm tra, đồng thời giữ nguyên lô v1.

## Đầu vào

- `delivery/` v1, `release_id`, manifest, metadata và `jobs.csv`.
- `errors.json` đã chốt từ Người 1, Người 2 và cả nhóm review.
- `trace.json` và `security.md` từ Người 4 để hoàn tất kiểm tra handover.

## Phụ thuộc và điểm dừng cho agent

- **Làm ngay khi có `delivery/`:** đọc cấu trúc lô, chuẩn bị quy trình hoặc code cho rework, manifest, thống kê, truy vết và README. Có thể dùng fixture nhỏ tự tạo để thử logic, đánh dấu rõ là dữ liệu thử và không đưa kết quả đó vào bài nộp.
- **Cần từ Người 1, Người 2 và nhóm review để chốt QC/v2:** `errors.json` của đúng seed, đã gộp lỗi luật và lỗi gán nhãn được người xem xác nhận. Nếu chưa có hoặc chưa rõ trạng thái, chỉ chuẩn bị khung và báo đang chờ; không tự đoán lỗi, tự tạo danh sách rỗng hoặc công bố v2 là hoàn chỉnh.
- **Cần kết quả QC thật để ghi quyết định:** tính tỷ lệ từ artifact đã chốt. Không ghi HOLD chỉ để qua checkpoint nếu số liệu chưa đủ hoặc không phù hợp; báo nhóm kiểm tra và hỏi giảng viên khi cần.
- **Cần từ Người 4 để nghiệm thu toàn bộ:** `trace.json` và `security.md` của cùng lô. Có thể chạy bộ kiểm sớm để tìm lỗi khác, nhưng ghi rõ H16/H17 còn chờ và không công bố đã PASS khi chưa có kết quả kiểm thật.
- **Bàn giao cho Người 4:** v2, lineage và số liệu cuối sau khi kiểm tra; đánh dấu rõ nếu còn thay đổi hoặc FAIL. Không thay đổi v1 để có đủ đầu vào.

## Yêu cầu chức năng

1. Tính QC v1 theo hướng dẫn: số mục trong `errors.json` / 250 ảnh; mỗi `scene_leak` tính một ảnh sai split. Trên 2% thì Hold.
2. Ghi quyết định trong lineage và kiểm tra tác động đến `R-021`.
3. Tạo v2 với parent v1, không sửa `delivery/` và không sửa tay nhãn YOLO.
4. Xử lý lỗi theo bảng dưới; bàn giao số liệu thật cho Người 4.
5. Đóng gói và chạy bộ kiểm H1–H17.

| Loại lỗi | Hướng xử lý |
|---|---|
| `wrong_hash`, `guideline_mismatch`, `scene_leak` | Kiểm tra và cập nhật thông tin tương ứng trong v2. Mở ảnh kiểm trước khi xử lý hash; ảnh hỏng đưa đi rework. |
| Thiếu ảnh hoặc lỗi nhãn detection | Đưa vào `rework_queue.csv`, giao đúng người và loại ảnh khỏi v2. |
| Chỉ lỗi panoptic | Giữ ảnh trong v2 detection và ghi chú để báo team panoptic. |

## Đầu ra

```text
runs/r<seed>/handover/<release_id_v1>_v2/
├── images/
├── labels/
├── rework_queue.csv
├── manifest.csv
├── label_summary.csv
├── truyvet.csv
└── README.txt
```

- `rework_queue.csv`: ảnh, loại lỗi, người gán, người kiểm, hành động.
- `manifest.csv`: đường dẫn và SHA-256 của các file ảnh/nhãn trong v2.
- `label_summary.csv`: số nhãn theo tên lớp và dòng `TOTAL`.
- `truyvet.csv`: ảnh, scene, split, job, người gán/kiểm và guideline theo job.
- `README.txt`: release, parent, số liệu, QC v1, kết luận v1/v2 và ghi chú xử lý.
- `runs/lineage.jsonl`, gói v2 và file `.sha256`.

## Lệnh tham khảo

```powershell
py scripts/lineage.py record --event decision --release-id <release_id_v1> --decision HOLD
py scripts/lineage.py impact --release-id <release_id_v1>
py scripts/pack_release.py runs/r3007/handover/<release_id_v1>_v2
py scripts/lineage.py record --event release --release-id <release_id_v1>_v2 --parent <release_id_v1>
py scripts/check_handover.py --run runs/r3007
```

Thay seed và release ID bằng giá trị thật. Nếu số liệu không phù hợp kỳ vọng HOLD của checkpoint, kiểm tra lại và hỏi giảng viên; không thay số liệu. Nếu sửa nội dung v2 sau đóng gói, cập nhật thông tin liên quan và đóng gói lại.

## Kiểm tra và nghiệm thu

- [ ] v1 giữ nguyên; QC có tử số, mẫu số, tỷ lệ và kết luận.
- [ ] Ảnh rework đúng loại, đúng người và không còn trong v2; lỗi panoptic được xử lý đúng.
- [ ] Hash, số ảnh, thống kê nhãn, truy vết và README nhất quán.
- [ ] Lineage có quyết định v1 và release v2 với parent; giải thích được tác động đến `R-021`.
- [ ] Sau khi nhận trace/security, `check_handover.py` không còn FAIL.
- [ ] Giải thích được hash xác nhận tính toàn vẹn, không chứng minh nhãn đúng.

## Việc chung

Chuẩn bị khung bàn giao sớm, sau đó tham gia review và đề ẩn. Ghi lại việc dùng AI và có ít nhất 2 commit có nội dung. Xem [GUIDE.md](../GUIDE.md) và [scripts/README.md](../scripts/README.md).
