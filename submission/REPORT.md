# Báo cáo nhóm <<XX>>

## 1. Số liệu luyện tập
- F1 theo seed (rule / cross_check / overall): <<seed: ... / ... / ...>>
- Số ứng viên trên lô sạch (`--no-faults`): <<...>>; hàng đợi trên seed luyện tập: <<... ảnh>>
- Ngưỡng đã chọn và cách chọn (không dùng `_private`): <<...>>

## 2. Vì sao báo hết ứng viên làm F1 giảm?
<<Trả lời bằng số của nhóm.>>

## 3. Quyết định và lineage
<<QC v1 a/b, kết luận, vì sao R-021 phải xem lại hoặc train lại.>>

## 4. Hash chứng minh gì, không chứng minh gì?
<<>>

## 5. Truy vết
Công cụ: `tools/trace_query.py <delivery> --out trace.json` (thư viện chuẩn, chỉ đọc `delivery/`, không ghi cứng tên lớp, cảnh hay ảnh).

- **Lớp bị đổi quy tắc:** đọc `guideline/changelog.md`. Seed 5007: `cup`, quy tắc mới từ v1.3 (cup bị che >50% hoặc ở mép ảnh vẫn phải gán box).
- **Cảnh team AI nêu:** các `scene_id` có trong `metadata.json` xuất hiện trong `incoming/ticket.md`. Seed 5007: `scene_473`, `scene_493`.
- **Điều kiện chung:** ảnh thuộc job có guideline cũ hơn v1.3 theo `jobs.csv` (seed 5007: J01–J04) **và** `labels/<ảnh>.txt` có ít nhất một box lớp đó.
- **tier_a** = ảnh đạt điều kiện nằm trong cảnh ticket nêu (3 ảnh); **tier_b** = các ảnh đạt điều kiện còn lại, chưa ai báo (6 ảnh).
- **notify** = annotator và reviewer của các job chứa ảnh tier_a/tier_b: A04, A05, Q01. Không báo hết người của mọi job cũ, vì có job cũ không có ảnh nào chứa `cup`.
- Kết quả tự đo (`score_findings.py`): tier_a 1.0, tier_b 1.0, notify 1.0.

**Vì sao lấy guideline theo job, không theo ảnh:** người gán làm theo guideline đang áp dụng cho job khi job được tạo, nên job mới quyết định ảnh có bị gán theo quy tắc cũ hay không. Cột guideline ghi ở từng ảnh trong `metadata.json` có thể sai, chính là lỗi `guideline_mismatch` mà validator bắt; dùng cột đó sẽ đưa nhầm hoặc bỏ sót ảnh.

Đề ẩn: chạy cùng công cụ trên `delivery/` của đề, ra lớp `truck`, cảnh `scene_100`, `scene_777`; tier_a 3 ảnh, tier_b 3 ảnh, notify A01, A02, Q01, Q03, khớp với kết quả Duy làm độc lập.

## 6. Bug hoặc điểm chưa rõ trong lab (nếu có)
<<>>
