# Checklist đề ẩn — 40 phút

> Chủ: Nguyễn Quốc Hưng (`2A202603324` · `@Soraxolo`) — P6 Hidden-test Prep.
> Mốc thời gian và lệnh chính xem [docs/CHALLENGE_RUNBOOK.md](../docs/CHALLENGE_RUNBOOK.md).
> File này là phần **kiểm trước khi nhận đề**, **đường lui khi engine hỏng**, và **các bẫy mất điểm**.
> Mở sẵn trước giờ phát đề — trong 40 phút không có thời gian đọc tài liệu.

## 1. Phải xong TRƯỚC khi nhận đề

- [ ] `python3 tools/qc_factory.py doctor` → mọi khoá `true`.
- [ ] `python3 tools/qc_factory.py benchmark` chạy trót lọt trên `runs/clean` và `runs/r9007`.
- [ ] Review UI lên được và **mỗi người đã tự mở thử**: biết phím tắt `C` / `R` / `S`, `←` `→`, và
      biết chỗ đổi `class_swap` ↔ `category_swap`.
- [ ] Cổng `8765` còn rảnh: `ss -ltn | grep 8765` (bận thì chạy `--port 8766` và báo cả nhóm).
- [ ] Mỗi người đã **tự tay** review ít nhất 5 ca ở r9007, biết ghi chú thế nào cho đạt.
- [ ] Đường lui ở mục 4 đã chạy thử ít nhất một lần.

## 2. Nhận đề (phút 0–2)

Tải `de_an.zip` ở tab **Releases** của repo đề hoặc nhận từ LMS/nhóm chat, giải nén **vào thư mục gốc
repo nhóm** → được `delivery/` (tên ảnh dạng `img_0001`).

```bash
unzip -q de_an.zip -d . && ls delivery | head
```

**Không `git add delivery/`.** Đã có trong `.gitignore` — đừng phá bằng `git add -A -f`.

## 3. Đường chính (phút 2–36)

```bash
python3 tools/qc_factory.py challenge --input delivery --out-dir submission/de_an --serve
# ... cả nhóm review ở http://127.0.0.1:8765/ ...
python3 tools/qc_factory.py finalize --run submission/de_an
```

`challenge` ghi `preflight_report.json`, `rules_errors.json`, `candidates.json`, `triage.csv`,
`difficulty_summary.json`, `trace.json`, `review_state.db`.
`finalize` xuất `review_log.csv` và gộp dòng `confirmed` vào `errors.json`, rồi kiểm đủ 4 file bắt buộc:
`errors.json`, `candidates.json`, `review_log.csv`, `trace.json`.

## 4. Đường lui khi engine hỏng (tập trước, đừng chữa lúc đang thi)

Cả đường chính nằm trên một công cụ. Nếu `challenge` lỗi hoặc Review UI không lên, **không ngồi sửa** —
chuyển ngay sang đường tay, mất khoảng 3 phút:

```bash
# 1) lỗi luật + ứng viên, bằng chính validator của nhóm
python3 validator/validate.py delivery --out submission/de_an/rules.json \
        --candidates submission/de_an/candidates.json

# 2) render hàng đợi ra PNG, chia việc theo người
python3 tools/review_viewer.py delivery --candidates submission/de_an/candidates.json \
        --out-dir runs/de_an_queue --shard 1/3

# 3) điền verdict + note vào runs/de_an_queue/review_log_todo.csv, gộp lại thành review_log.csv
# 4) chốt errors.json
python3 scripts/merge_review.py --rules submission/de_an/rules.json \
        --review submission/de_an/review_log.csv --out submission/de_an/errors.json
```

`trace.json` khi đó làm tay theo tiêu chí ở `submission/REPORT.md` mục 5.

## 5. Xem ảnh — việc của người, không của AI

- `note` phải nói **thấy gì trong ảnh**, ≥ 20 ký tự, mỗi dòng viết khác nhau. Ghi "có lỗi" / "OK" chỉ
  được nửa điểm; chép giống nhau thì H3 FAIL.
- Ứng viên máy ghi `class_swap` chỉ là **một trong hai** khả năng. Mở ảnh rồi quyết: vật đúng là cái
  panoptic ghi → detection sai → `class_swap`; vật đúng là cái detection ghi → panoptic sai →
  **`category_swap`** (đổi trong ô chọn của Review UI, hoặc sửa cột `type` nếu làm tay).
- Ca `bbox_drift` và `instance_merge`: Review UI chỉ vẽ **bbox** của segment. Ca nào còn lưỡng lự thì
  mở thêm `tools/review_viewer.py --image <tên ảnh>` để nhìn **viền mask thật**.
- Lệch tự nhiên của COCO (vật bị che, `iscrowd`, box sát nhau) → `rejected` kèm lý do. Hàng đợi không
  có dòng `rejected` nào là dấu hiệu nhóm đang báo thừa — trên lô sạch 50 ảnh có tới 7 ca như vậy.
- Chỉ 5 loại được ghi là lỗi gán nhãn: `class_swap`, `bbox_drift`, `missing_box`, `category_swap`,
  `instance_merge`. Ghi loại lỗi luật vào `review_log.csv` thì `merge_review.py` **dừng với lỗi**.

## 6. Tự kiểm trước khi nộp (phút 36–40)

```bash
python3 - <<'PY'
import csv, json
err = json.load(open("submission/de_an/errors.json"))["errors"]
SEM = {"class_swap","bbox_drift","missing_box","category_swap","instance_merge"}
rows = list(csv.DictReader(open("submission/de_an/review_log.csv", encoding="utf-8")))
ok = {(r["type"].strip(), r["image"].strip()) for r in rows
      if r["verdict"].strip() == "confirmed" and len(r["note"].strip()) >= 20}
thieu = [e for e in err if e["type"] in SEM and (e["type"], e["target"]) not in ok]
print("tổng lỗi:", len(err), "| gán nhãn thiếu confirmed/ghi chú <20 ký tự:", thieu or "không")
print("số dòng rejected:", sum(1 for r in rows if r["verdict"].strip() == "rejected"))
PY

git status --short          # KHÔNG được thấy delivery/
git add submission/de_an security reporting tools
git commit -m "P6: de an - errors, review_log, trace"
git push origin main
```

Lỗi gán nhãn nào **không** có dòng `confirmed` kèm ghi chú ≥ 20 ký tự sẽ bị giảng viên **bỏ ra** trước
khi chấm — nộp thừa ở đây không được điểm mà còn kéo precision xuống.

## 7. Hỏng việc thường gặp

| Triệu chứng | Xử lý nhanh |
|---|---|
| Review UI không lên / cổng bận | `--port 8766`; vẫn không được thì sang mục 4, đừng sửa code |
| `merge_review.py` dừng: "type không phải lỗi gán nhãn" | `review_log.csv` có dòng ghi loại lỗi luật — xoá dòng đó |
| Validator chết vì tên ảnh lạ (`img_0001`) | Validator chỉ đọc tên từ `manifest.json`, không đoán theo tên — đã kiểm ở lô luyện tập |
| Hàng đợi quá lớn, không xem hết | Ưu tiên tầng `EASY`/`MEDIUM` trong `triage.csv` trước, ghi rõ trong `REPORT.md` đã bỏ bao nhiêu ca |
| Ảnh nhỏ nhìn không rõ | `tools/review_viewer.py` phóng tối thiểu 720 px và cắt riêng vùng nghi vấn |
| Hết giờ | Thà ít lỗi mà chắc, hơn là báo thừa: F1 trừ báo thừa đúng như bỏ sót |
