# Day 10 Lab — Conversation Notes and Repository Analysis

> Ghi chú tổng hợp cuộc trò chuyện chuẩn bị làm lab, cập nhật ngày 19/11/2026.  
> Đây là tài liệu định hướng; hướng dẫn và rubric trong repo là nguồn chuẩn nếu có khác biệt.

## 1. Kết luận cuộc trò chuyện

- Nhóm có **5 người** và dự kiến phân công:
  - **Long (Leader):** tạo repo, chốt seed, theo dõi tiến độ, quyết định Release/Hold, lineage, handover v2, tích hợp và kiểm tra bài nộp.
  - **Bạn A:** validator cho lỗi detection/file.
  - **Bạn B:** validator cho metadata/panoptic và phối hợp tích hợp `validate.py`.
  - **Bạn C:** đối chiếu detection với panoptic, tạo candidates, chuẩn bị công cụ xem ảnh và tổng hợp `review_log.csv`.
  - **Bạn D:** truy vết ticket, `trace.json`, bảo mật, tài liệu và `prompts.md`.
- Phân công này phù hợp với cấu trúc lab. Nên thống nhất sớm schema đầu ra và giao diện giữa các phần; có thể viết module tách biệt để tránh nhiều người sửa đồng thời một `validate.py`.
- Cả 5 người đều phải tham gia review ảnh. Mọi kết luận lỗi gán nhãn là quyết định của người xem ảnh, không phải của AI.
- Mỗi thành viên cần ít nhất **2 commit có nội dung**. Dùng branch và PR là quy trình nhóm đề xuất, tương thích với yêu cầu đóng góp/commit của lab.
- **Seed luyện tập của nhóm: `2902`.** Seed dùng để tạo lô có thể tái lập; seed không phải đáp án và không cho biết lỗi cần báo.

## 2. Phân tích nội dung repo

### Mục tiêu

Lab mô phỏng quy trình kiểm soát chất lượng dataset, ra quyết định phát hành, tạo bản bàn giao mới và truy vết ảnh hưởng sau khi team AI báo lỗi. Lô có 250 ảnh với detection và panoptic; không có nhãn chuẩn để nhóm diff trực tiếp. Lỗi gán nhãn cần được phát hiện bằng đối chiếu hai nguồn và xác nhận bằng mắt.

### Các pha và sản phẩm chính

| Pha | Công việc | Sản phẩm / kiểm tra |
|---|---|---|
| 0 — Chuẩn bị | Tải dữ liệu, tạo lô, chia việc | `runs/r2902/delivery/` |
| 1 — Lỗi luật | Tự viết validator, kiểm tra file, nhãn và metadata | `validator/validate.py`, `errors.json` |
| 2 — Đối chiếu và review | Sinh candidates từ detection ↔ panoptic; đo nhiễu trên lô sạch; cả nhóm mở ảnh | `candidates.json`, `review_log.csv`, `errors.json` đã chốt |
| 3 — Quyết định | Tính tỷ lệ ảnh lỗi và ghi quyết định vào lineage | HOLD nếu vượt ngưỡng 2%; kiểm tra ảnh hưởng tới `R-021` |
| 4 — Handover v2 | Giữ nguyên v1; tạo bản v2, manifest/hash, thống kê, rework queue và truy vết | `handover/<release_id>_v2/`, gói `.sha256`, kết quả `check_handover.py` |
| 5 — Truy vết | Dùng ticket, changelog, job và nhãn để xác định vùng ảnh/người liên quan | `trace.json` gồm `tier_a`, `tier_b`, `notify` |
| 6 — Bảo mật và đề ẩn | Điền nội dung bảo mật; chạy validator và review đề ẩn trong thời gian quy định | `security.md`, các sản phẩm trong `submission/de_an/` |

### Validator: phạm vi 9 lỗi luật

- **Detection/file:** `missing_image`, `wrong_hash`, `invalid_class`, `bbox_out_of_bounds`, `duplicate_box`.
- **Metadata:** `scene_leak`, `guideline_mismatch`.
- **Panoptic:** `invalid_category_id`, `thing_overlap`.

Các lỗi này phải được kiểm từ nội dung `delivery/` được truyền vào validator. Hash phải được tính trên bytes thực của file. Với `duplicate_box`, không dùng IoU đơn thuần vì COCO có các box chồng lấn tự nhiên.

### Đối chiếu và review: 5 lỗi gán nhãn

Các loại là `class_swap`, `bbox_drift`, `missing_box`, `category_swap`, `instance_merge`. Có thể tạo ứng viên bằng cách ghép box detection với segment panoptic, nhưng ứng viên chưa phải lỗi đã xác nhận. Lô sạch cũng có thể có khác biệt tự nhiên, nên cần đo nhiễu, chọn hàng đợi có thể review hết và ghi cả ca `rejected` với lý do.

`review_log.csv` có các cột `image,type,verdict,note`. Ghi chú cần nêu bằng chứng quan sát được trong ảnh; mọi lỗi gán nhãn trong `errors.json` phải có dòng `confirmed` phù hợp.

### Quyết định release và handover

- Tỷ lệ lỗi v1 tính theo số ảnh/cảnh lỗi trên tổng 250 ảnh; `scene_leak` được tính theo ảnh bị đặt sai split.
- Ngưỡng của lab: **trên 2% thì không Release v1**. Ghi quyết định HOLD và dùng lineage để kiểm tra training run `R-021`.
- Không chỉnh v1. Lỗi detection cần gán lại thì đưa ảnh vào `rework_queue.csv` và loại khỏi v2. Lỗi chỉ thuộc panoptic thì ảnh vẫn ở v2, đồng thời báo team panoptic.
- Handover còn cần `manifest.csv` với SHA-256, `label_summary.csv`, `truyvet.csv`, `README.txt`, đóng gói bằng `pack_release.py`, và vượt các kiểm tra của `check_handover.py`.
- PASS của `check_handover.py` xác nhận tính nhất quán/định dạng bàn giao, không chứng minh nhãn đúng.

### Quy tắc quan trọng

- Validator chỉ đọc delivery được truyền vào; không dùng mạng, `_private/`, annotation COCO hay đáp án ẩn.
- Chỉ dùng thư viện chuẩn trong validator; không sửa script trong `scripts/` để qua bộ kiểm.
- Không bịa kết quả, hash, số liệu hoặc review. `score_findings.py` dùng để tự đo, không dùng để dò đáp án.
- AI có thể hỗ trợ viết code/giải thích, nhưng phải ghi prompt, lỗi của AI và cách kiểm chứng trong `prompts.md`; AI không thay việc xem ảnh.
- Không commit dữ liệu tải về, `runs/`, file zip hoặc delivery của đề ẩn. Xem [SUBMISSION.md](SUBMISSION.md) để biết cấu trúc nộp.

## 3. Thiết lập seed 2902

Chạy từ thư mục gốc repo trên Windows PowerShell:

```powershell
py scripts/download_public.py
py scripts/run_lab.py --seeds 2902
```

`download_public.py` cần chạy trước nếu dữ liệu chưa có. `run_lab.py` tạo `runs/r2902/` và lần chạy đầu ghi training run `R-021` vào `runs/lineage.jsonl`; vì vậy chỉ chạy một lần cho seed chính. Khi cần seed phụ để thử validator, dùng `inject_release.py`, không chạy lại `run_lab.py`.

Các bước tiếp theo theo hướng dẫn là đọc `docs/DELIVERY.md`, triển khai validator và thử trên seed chính, seed phụ và lô sạch; sau đó review, ghi lineage, tạo v2, truy vết, hoàn tất bảo mật và xuất bài nộp.

## 4. Trạng thái repo đã quan sát

- Repo: `K5-L23-Day10-LeVietLong-2A202603043-Dataset-Release-Handover`, nhánh `main`.
- Lần kiểm tra trước trong cuộc trò chuyện: working tree sạch; Python `3.12.10`.
- Bộ test: `python -m unittest discover -s tests` chạy **6 test, 3 skipped**. Các test cần dữ liệu/pool tương ứng nên bị skip khi dữ liệu chưa được tải.
- Lần khảo sát đó chưa có validator do nhóm viết hoặc sản phẩm bài làm; không có thay đổi code nào được thực hiện trong cuộc trò chuyện.

## 5. Tài liệu chuẩn trong repo

- [README.md](README.md) — tổng quan và bắt đầu nhanh.
- [GUIDE.md](GUIDE.md) — lộ trình, lệnh chạy và hướng dẫn từng pha.
- [docs/DELIVERY.md](docs/DELIVERY.md) — cấu trúc delivery, loại lỗi và định dạng.
- [CHECKPOINTS.md](CHECKPOINTS.md) — mốc tự kiểm tra.
- [RULES.md](RULES.md) — quy định validator, AI, dữ liệu và tính trung thực.
- [RUBRIC.md](RUBRIC.md) — thang điểm và tiêu chí chấm.
- [SUBMISSION.md](SUBMISSION.md) — cấu trúc và checklist nộp bài.
