# Note — Release Handover (Quang)

## Thông tin run

- Repo: `K5-L23-DAY10-NHOM012-Release`
- Seed: `12007`
- Release v1: `lab250_7fa680a7413b`
- Training run dùng v1: `R-021`
- Thư mục nguồn: `runs/r12007/delivery/`
- Thư mục bàn giao dự kiến: `runs/r12007/handover/lab250_7fa680a7413b_v2/`

## Trạng thái hiện tại (cập nhật 20/11/2026)

- Đã tích hợp review log, chạy validator và merger: `errors.json` có 22 finding, 21 target duy nhất.
- QC v1 là 21/250 = 8,4%; lineage ghi HOLD và xác nhận `R-021` cần review hoặc retrain.
- Đã tạo v2 với 239 ảnh, 1.638 nhãn, rework queue 11 target; ảnh v1 giữ nguyên.
- Đã tạo `trace.json`, `security.md`, đóng gói v2; `check_handover.py` đạt 17 PASS, 0 FAIL.
- Mọi thay đổi dataset nằm trong `handover/`; không sửa `runs/r12007/delivery/`.

## Checklist đã hoàn tất cho run luyện tập

- [x] Nhận `errors.json` đã gộp lỗi luật và lỗi gán nhãn được xác nhận, cùng `review_log.csv`, từ Người 1, Người 2 và nhóm review.
- [x] Tính QC v1 bằng số target lỗi duy nhất / 250 ảnh. Mỗi `scene_leak` tính một target cảnh. Trên 2% thì Hold; không đoán hoặc tự tạo danh sách lỗi rỗng.
- [x] Ghi quyết định theo số liệu đã chốt rồi kiểm tra tác động đến `R-021`:

   ```bash
   python3 scripts/lineage.py record --event decision --release-id lab250_7fa680a7413b --decision HOLD
   python3 scripts/lineage.py impact --release-id lab250_7fa680a7413b
   ```

   Chỉ ghi `HOLD` khi kết quả QC hỗ trợ quyết định đó. Nếu kết quả khác kỳ vọng checkpoint, kiểm tra lại dữ liệu và hỏi giảng viên; không sửa số liệu.

- [x] Tạo v2 theo quy tắc:
   - `wrong_hash`: mở ảnh kiểm tra trước; nếu ảnh nguyên thì dùng hash thật, nếu ảnh hỏng thì đưa đi rework.
   - `guideline_mismatch`: cập nhật thông tin guideline theo guideline của job.
   - `scene_leak`: đưa cả cảnh về cùng một split.
   - Lỗi nhãn detection hoặc thiếu ảnh: ghi vào `rework_queue.csv`, giao đúng annotator/reviewer theo `jobs.csv`, loại ảnh khỏi v2.
   - Lỗi chỉ ở panoptic: giữ ảnh trong v2 và ghi chú để báo team panoptic.
   - Không sửa tay nhãn YOLO.

- [x] Tạo đủ các đầu ra trong thư mục v2:
   - `images/`, `labels/`
   - `rework_queue.csv`
   - `manifest.csv` — SHA-256 mọi file ảnh/nhãn
   - `label_summary.csv` — số nhãn theo lớp và dòng `TOTAL`
   - `truyvet.csv` — scene, split, job, người gán/kiểm, guideline theo job
   - `README.txt` — release/parent, số ảnh/nhãn, QC v1, kết luận v1/v2 và ghi chú

- [x] Đóng gói v2, ghi lineage release có parent v1 và chạy kiểm tra:

   ```bash
   python3 scripts/pack_release.py runs/r12007/handover/lab250_7fa680a7413b_v2
   python3 scripts/lineage.py record --event release --release-id lab250_7fa680a7413b_v2 --parent lab250_7fa680a7413b
   python3 scripts/check_handover.py --run runs/r12007
   ```

- [x] Nhận `trace.json` và `security.md` từ Người 4, chạy lại `check_handover.py`, sửa mọi mục FAIL. Nếu sửa nội dung v2 sau khi đóng gói thì chạy lại `pack_release.py`.
- [x] Cập nhật `submission/REPORT.md` bằng số liệu và kết quả thật sau khi chốt.

## Tài liệu tham khảo

- `work/03-release-handover.md`
- `GUIDE.md` — Pha 3 và Pha 4
- `scripts/README.md` — mã kiểm H1–H17
