# Báo cáo nhóm 7

## 1. Số liệu luyện tập
- F1 làm tròn theo seed (lỗi luật / lỗi gán nhãn / tổng) ở pha 1
  - 7007 (seed Nhóm 7): 1,0 / — / 0,8, báo 12 lỗi luật.
  - 7008 (seed kiểm tra bổ sung): 1,0 / — / 0,7, báo 11 lỗi luật.
  - Lô sạch (seed 5, 50 ảnh): 1,0 / 1,0 / 1,0, báo 0 lỗi luật.
- F1 sau pha 2 (đối chiếu + xem ảnh, seed 7007): **1,0 / 0,7 / 0,9**, nộp **16** lỗi (12 lỗi luật + 4 lỗi gán nhãn đã `confirmed` trong `review_log.csv`).
- Dấu — là giá trị bộ chấm in cho lỗi gán nhãn khi chạy pha 1.
- Kết quả lỗi luật của seed chính được lưu riêng ở `runs/r7007/rules.json` để gộp với review ở pha 2. Lô sạch báo 0 lỗi luật trong `runs/clean/errors.json`.
- Kiểm tra box dùng dung sai làm tròn YOLO sáu chữ số thập phân. Hai box bị xem là trùng khi cùng lớp, cùng kích thước trong dung sai và tâm lệch tối đa 2 pixel theo mỗi trục.
- Số ứng viên trên lô sạch (`--no-faults`): **0** ứng viên trên 50 ảnh (seed 5); hàng đợi trên seed luyện tập (`7007`): **5** ứng viên trên **5** ảnh (`missing_box=1`, `bbox_drift=1`, `class_or_category_swap=2`, `instance_merge=1`).
- Ngưỡng đã chọn và cách chọn (không dùng `_private`): ghép theo tỷ lệ pixel mask panoptic nằm trong box detection kết hợp IoU (bỏ segment `iscrowd`), dùng `MATCH_IOU = 0.30`, `SWAP_IOU = 0.50`, `DRIFT_INSIDE_MAX = 0.82` (`DRIFT_IOU_MIN = 0.15`), `MISSING_MIN_FRAC = 0.008`, và kiểm `instance_merge` (`MERGE_SHARE_MIN = 0.25`, `MERGE_SINGLE_MAX = 0.80`, `MERGE_PAIR_IOU_MAX = 0.30`) trước `bbox_drift` để tránh báo đúp trên cùng segment. Đã kiểm chứng trên lô sạch `runs/clean` (50 ảnh `calib`) cho **0** ứng viên giả, đồng thời giữ hàng đợi `r7007` gọn ở 5 ảnh để xem hết bằng mắt.

## 2. Vì sao báo hết ứng viên làm F1 giảm?
Trên seed `7007`, bộ đối chiếu sinh 5 ứng viên trên 5 ảnh, nhưng khi mở ảnh xem thực tế chỉ có **4 ca lỗi thật (`confirmed`)** và **1 ca lệch tự nhiên (`rejected`)** là ảnh `000000001818` (hai con ngựa vằn đứng chồng lên nhau làm validator ghép nhầm box con bên phải với segment con lớn). Ngoài ra, với 2 ca `class_or_category_swap` (`000000006471`, `000000013177`), nếu không mở ảnh xem thì không phân biệt được `class_swap` hay `category_swap` — đoán sai sẽ bị tính đồng thời cả 1 FP lẫn 1 FN. Khi báo bừa toàn bộ ứng viên chưa qua review mắt, số báo thừa (`FP`) tăng lên làm `precision = TP / (TP + FP)` giảm, kéo theo `F1 = 2·P·R / (P + R)` giảm theo.

## 3. Quyết định và lineage
- QC v1: **16/250 = 6,4%** (16 mục trong `errors.json`: 12 lỗi luật + 4 lỗi gán nhãn `confirmed`; `scene_leak` của `scene_593` tính 1 mục). 6,4% > ngưỡng 2% (Day 7) nên v1 `lab250_5279e3fe917f` **Hold**.
- Lineage (`runs/lineage.jsonl`): `inject` → `train R-021` → `decision HOLD` cho v1 → `release lab250_5279e3fe917f_v2 --parent lab250_5279e3fe917f`. `lineage.py impact` trả về `R-021: affected=True action=review_or_retrain`.
- Vì sao R-021 phải xem lại hoặc train lại: R-021 đã học từ v1, trong đó có box sai lớp (`class_swap` 000000013177), box thiếu (`missing_box` 000000000785), box lặp, nhãn class ngoài 0–79 và một cảnh rò train/val (`scene_593`) làm điểm val bị ảo. Sửa dataset thành v2 không làm model quên những gì đã học; trọng số của R-021 vẫn mang lỗi. Phải đánh giá lại R-021 trên v2 (đặc biệt phần val sau khi gom `scene_593` về một split) hoặc train lại một run mới trên v2.
- v2 `lab250_5279e3fe917f_v2`: 243 ảnh, 1694 nhãn; 7 ảnh lỗi nhãn detection/thiếu file vào `rework_queue.csv` giao đúng người gán + người kiểm theo `jobs.csv`; 5 ảnh chỉ lỗi panoptic ở lại v2 và được ghi vào README để báo team panoptic; sửa trong v2: hash (`000000016010`, đã mở ảnh, ảnh còn nguyên), guideline theo job (2 ảnh), split theo cảnh (`scene_593` về train). `check_handover.py`: 17/17 PASS.

## 4. Hash chứng minh gì, không chứng minh gì?
- **Chứng minh:** từng file trong v2 đúng y từng byte như lúc đóng gói. `manifest.csv` ghi sha256 của 486 file trong `images/` và `labels/`; `lab250_5279e3fe917f_v2.sha256` là mã của zip tái lập. Ai sửa dù một ký tự thì mã đổi ngay, nên bên nhận biết được lô có bị đổi trên đường giao hay không. Hash nhãn trong v2 trùng hash nhãn ghi ở manifest v1 (H7) chứng minh nhóm **không sửa tay nhãn**, và `release_id` v1 không đổi (H1) chứng minh **v1 không bị ghi đè**.
- **Không chứng minh:** nhãn **đúng**. Một box gán nhầm lớp vẫn có hash hợp lệ; hash chỉ nói file không đổi, không nói nội dung đúng. Ví dụ ảnh `000000016010`: manifest v1 ghi sai hash nhưng ảnh không hỏng (đã mở xem), còn các ảnh lỗi `class_swap`/`missing_box` lại có hash hoàn toàn khớp. Đúng/sai của nhãn vẫn phải do đối chiếu hai nguồn và người xem ảnh quyết định.

## 5. Truy vết
- Ticket: model hay bỏ sót `truck` bị che hoặc ở mép, thấy rõ ở `scene_370`, `scene_532`. Changelog: từ v1.3, `truck` bị che > 50% hoặc cắt mép vẫn phải gán box; v1.2 cho phép bỏ qua. Vậy ảnh gán theo v1.2 có thể thiếu box truck.
- Tiêu chí (script `tools/trace_query.py`): ảnh thuộc job có guideline **v1.2 theo `jobs.csv`** (J01–J04) **và** có ít nhất một box detection lớp `truck` (id 7) trong `labels/`. Nằm trong cảnh ticket nêu → **tier_a** (2 ảnh: `000000001532`, `000000007088`); ở cảnh khác → **tier_b** (5 ảnh: `000000000724`, `000000006040`, `000000006723`, `000000007386`, `000000009769`).
- `notify` = người gán + người kiểm của các job **có** ảnh tầng a/b: J01, J03, J04 → `A03, A04, Q01, Q02, Q03`. J02 cũng là v1.2 nhưng không có ảnh nào chứa truck nên A01 không bị báo (báo thừa bị trừ điểm).
- Vì sao lấy guideline theo job: job là nơi quy định người gán làm theo bản nào. Guideline ghi ở từng ảnh có thể sai — chính là lỗi `guideline_mismatch` (2 ảnh trong lô này) — nên nếu lọc theo ảnh sẽ xếp nhầm tầng.
- `score_findings.py` (seed 7007): tier_a ≈ 1.0, tier_b ≈ 1.0, notify ≈ 1.0.

## 6. Bug hoặc điểm chưa rõ trong lab (nếu có)
- Khi chạy qua PowerShell với stdout dùng CP1252, script tạo lô và validator có thể ghi xong tệp rồi thoát lỗi khi in tiếng Việt. Đặt `$env:PYTHONUTF8 = '1'` trước khi chạy để Python và tiến trình con dùng UTF-8.

- **`release_id` của cùng seed khác nhau giữa Windows và Linux.** Nhóm tạo lô bằng `py scripts/run_lab.py --seeds 7007` trên Windows được `lab250_5279e3fe917f`; chạy `inject_release.py --seed 7007` trên Linux (Python 3.10, zlib 1.2.11) ra `lab250_42b020af0ffa`. So hai lô: 250 ảnh và 250 nhãn trùng sha256 hoàn toàn, nhưng `manifest.json`/`metadata.json` trên Windows được ghi xuống dòng CRLF và 241 mask PNG khác byte (zlib khác bản nén ra khác), nên `release_id` (sha256 của manifest + metadata) đổi. Nếu người chấm tạo lại lô bằng `export_submission.py --import` trên máy khác hệ điều hành thì tên thư mục `handover/<release_id>_v2` và dòng `Release:`/`Parent:` sẽ không khớp (H1/H4 FAIL) dù nội dung ảnh + nhãn v2 giống hệt. Nhóm không sửa `scripts/`; đề nghị chấm lại trên Windows hoặc báo nhóm để tạo lại v2 theo lô của máy chấm.
