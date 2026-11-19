# Người 4: Truy vết, bảo mật và nộp bài

## Mục tiêu

Truy vết phạm vi ảnh hưởng từ ticket, hoàn thành phần bảo mật và tổng hợp báo cáo, bằng chứng, sản phẩm nộp của nhóm.

## Đầu vào

- `incoming/ticket.md`, `guideline/changelog.md`, `jobs.csv`, `metadata.json` và `labels/` của từng lô.
- Số liệu validator và review từ Người 1, Người 2.
- Quyết định, lineage và số liệu v2 từ Người 3.
- Thông tin thành viên, commit và việc dùng AI của cả nhóm.

## Phụ thuộc và điểm dừng cho agent

- **Làm ngay khi có `delivery/`:** đọc ticket, changelog, jobs, metadata và labels để lập `trace.json`; chuẩn bị `security.md`, `TEAM.md` và khung báo cáo. Không cần đợi validator hoặc v2 để bắt đầu truy vết.
- **Cần người và bằng chứng thật:** thông tin thành viên, prompt AI, ghi chú review và ảnh cụ thể cho ca khuôn mặt phải do nhóm cung cấp hoặc kiểm tra trên dữ liệu được phép. Nếu thiếu, để mục chờ rõ ràng; không tự bịa tên, prompt, kết quả review hay ảnh.
- **Cần từ Người 1 và Người 2 để chốt báo cáo:** F1 thực tế, số ứng viên, ngưỡng và kết quả review. Nếu chưa có, để mục chờ, không tự tạo số liệu.
- **Cần từ Người 3 để chốt báo cáo và export:** quyết định QC, lineage, số liệu và handover cuối của đúng seed. Không chạy export cuối hoặc tuyên bố đã nộp khi artifact còn thiếu/chưa được chốt; export có thể thay thế bản handover đã xuất.
- **Cần cả nhóm và đề ẩn thật để nộp:** `errors.json`, `candidates.json`, `review_log.csv` và `trace.json` của đề ẩn, cùng commit/push theo phân công. Không tự tạo kết quả đề ẩn hoặc đánh dấu hoàn thành khi chưa có bằng chứng.
- **Bàn giao sớm cho Người 3:** `trace.json` và `security.md` của lô luyện tập ngay khi hoàn tất, không chờ đến lúc v2 xong.

## Yêu cầu truy vết

Tạo `runs/r<seed>/trace.json` theo mẫu trong `templates/trace.json`:

| Khóa | Nội dung |
|---|---|
| `tier_a` | Ảnh trong cảnh team AI nêu, thuộc job guideline cũ và có box detection thuộc lớp đổi quy tắc. |
| `tier_b` | Ảnh khác chưa được báo nhưng cùng điều kiện về job guideline cũ và lớp đó. |
| `notify` | Mã người gán và người kiểm của các job chứa ảnh ở hai tầng. |

Lấy guideline theo **job** trong `jobs.csv`, vì guideline ghi ở ảnh có thể là dữ liệu sai. Làm truy vết riêng cho lô luyện tập và đề ẩn.

## Yêu cầu bảo mật

Điền `runs/r<seed>/security.md` theo `templates/security.md`:

1. Ca USB và cách xử lý khi hết giờ.
2. Năm hành động được/không được và lý do.
3. Ca khuôn mặt: Hold và báo người phụ trách; nêu ít nhất một ảnh có mặt người rõ trong lô của nhóm.

Bàn giao `trace.json` và `security.md` cho Người 3 để chạy bộ kiểm handover.

## Báo cáo và nộp bài

- `submission/TEAM.md`: thành viên, tài khoản, seed và phân công.
- `submission/REPORT.md`: F1 theo nhóm lỗi, số ứng viên lô sạch, ngưỡng và lý do; quyết định, lineage, hash, truy vết và bug nếu có.
- `submission/prompts.md`: ai dùng AI, prompt, AI sai ở đâu nếu có và cách kiểm lại.
- Export bài luyện tập và kiểm tra bài đề ẩn.

```powershell
py scripts/export_submission.py --run runs/r3007
```

Thay seed bằng seed của nhóm. Lệnh export thay thế handover đã xuất bằng bản trong `runs/`; phối hợp Người 3 để bản trong `runs/` là bản cuối.

## Sản phẩm cần có

```text
submission/
├── TEAM.md
├── REPORT.md
├── prompts.md
├── lineage.jsonl
├── r<seed>/
└── de_an/
    ├── errors.json
    ├── candidates.json
    ├── review_log.csv
    └── trace.json
```

## Kiểm tra và nghiệm thu

- [ ] Trace đủ ba khóa, ảnh và người đúng theo ticket và job.
- [ ] Security đủ ba mục và có ví dụ ảnh thật.
- [ ] Báo cáo dùng số liệu thật, không còn placeholder; giải thích được hash và ảnh hưởng đến run đã train.
- [ ] Prompt AI được ghi trung thực; mỗi người có ít nhất 2 commit có nội dung.
- [ ] Bài luyện tập và đề ẩn đủ file theo `SUBMISSION.md`.
- [ ] Không commit `data_source/`, `runs/`, ZIP, secret hoặc `delivery/` đề ẩn.
- [ ] Đã push và kiểm tra link repo trước khi nộp theo hướng dẫn giảng viên.

## Việc chung

Phối hợp điều phối checkpoint nhưng cả nhóm cùng chịu trách nhiệm review, đề ẩn và vấn đáp. Xem [GUIDE.md](../GUIDE.md), [RULES.md](../RULES.md) và [SUBMISSION.md](../SUBMISSION.md).
