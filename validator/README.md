# Validator của nhóm

Viết `validate.py` ở đây. Giao diện cố định:

```
python validator/validate.py <thư_mục_delivery> --out <errors.json> [--candidates <candidates.json>]
```

Chỉ đọc thư mục delivery được truyền vào; chỉ thư viện chuẩn; không mạng. Xem [GUIDE.md](../GUIDE.md) Pha 1–2 và [RULES.md](../RULES.md).

## Phần B đã tích hợp với A

- `scene_leak`: gom split theo scene, báo một lần với target là scene_id nếu có cả train và val.
- `guideline_mismatch`: so guideline_version của ảnh với guideline của đúng job trong jobs.csv.
- `invalid_category_id`: kiểm mọi segment theo bảng categories, không mặc định id liên tục.
- `thing_overlap`: đọc mask bằng pngutil, đếm id RGB 24 bit và báo khi area của thing lớn hơn số pixel thực. Kiểm cả crowd, không báo stuff hoặc void; không dùng giao bbox làm bằng chứng.

Giữ thứ tự kiểm của A: mỗi ảnh chỉ nhận lỗi luật đầu tiên. Scene leak kiểm riêng toàn lô.
Phần C tiếp tục triển khai `find_candidates`; hiện hàm này trả danh sách rỗng.

Ghi riêng lỗi luật để D gộp với review:

```powershell
py -X utf8 validator/validate.py runs/r24007/delivery --out runs/r24007/rules.json
```

Kiểm thử không cần tải dữ liệu:

```powershell
py -X utf8 -m unittest discover -s tests -p test_validator_b.py -v
```

Sau khi tải đủ dữ liệu, chạy hai seed 24007, 24008 và lô sạch calib seed 5:

```powershell
py -X utf8 tests/verify_rule_seeds.py
```

Công cụ tạo lô riêng trong `runs/b_checks/`, ghi rules.json và errors.json giống nhau để gọi
score_findings.py chế độ học viên, lưu report.md từng lô và summary.json tổng hợp.
Không ghi lineage, không chạm kết quả review hoặc delivery của nhóm, từ chối ghi đè thư mục cũ
(muốn chạy lại dùng `--out runs/b_checks_2`). Đọc F1 **lỗi luật**; chưa có review nên F1 tổng
không đại diện kết quả bài hoàn chỉnh. Lô sạch phải có 0 lỗi luật.

Trạng thái kiểm chứng ngày 19/11/2026: 7 test B và 3 test MetricsTest đã pass.
Chưa chạy được hai seed/lô sạch thực do tải COCO timeout, chưa có đủ dữ liệu Pha 0;
chưa có rules.json thực hoặc số F1 để báo cáo. Không thay số liệu kiểm thử bằng số giả định.
