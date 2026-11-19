# Validator của nhóm — phần Data Validation

```powershell
python -X utf8 -B validator/validate.py runs/r12007/delivery --out runs/r12007/rules.json
python -X utf8 -B -m unittest discover -s tests -p test_validation.py -v
```

`rules.py` cung cấp `validate_rules(delivery) -> {"errors": [...]}` để Người 2
import và tích hợp. Kết quả được loại trùng, sắp xếp ổn định theo type/target.
Target là tên ảnh không đuôi; riêng scene_leak dùng scene_id. Không phụ thuộc
tên ảnh dạng số, seed hoặc đáp án.

## Chín kiểm tra

- `missing_image`: file ảnh trong manifest không tồn tại; không báo thêm wrong_hash cho file thiếu.
- `wrong_hash`: SHA-256 đọc từ bytes của cả image, label và mask, so với manifest.
- `invalid_class`: class ID phải có trong classes.txt.
- `bbox_out_of_bounds`: kiểm bốn cạnh sau khi đổi tâm/kích thước sang cạnh;
  kích thước phải dương, các tọa độ phải hữu hạn. Dung sai 1e-6 cho làm tròn YOLO.
- `duplicate_box`: cùng class, chênh kích thước tối đa 0,01 pixel (dung sai
  serialization), tâm chênh tối đa 2 pixel mỗi trục; không chỉ dựa trên IoU.
- `scene_leak`: scene có cả train và val/validation.
- `guideline_mismatch`: guideline_version của ảnh khác guideline của job_id trong jobs.csv.
- `invalid_category_id`: category_id không có trong categories của panoptic.json.
- `thing_overlap`: với category isthing, area lớn hơn số pixel mang segment ID;
  giải mã ID = R + 256*G + 65536*B, bỏ qua segment ID 0.

Chỉ đọc dữ liệu trong delivery, dùng thư viện chuẩn và scripts/pngutil.py.
Đường dẫn manifest thoát khỏi delivery bị từ chối. Không ghi output vào delivery.
Thiếu label/mask hoặc sai cấu trúc dữ liệu gây mã thoát 1, không xuất báo cáo
thành công một phần. Phát hiện lỗi dữ liệu hợp lệ vẫn trả mã 0.

## Điểm tích hợp với Người 2

Chưa có chức năng đối chiếu/candidates trong repo tại thời điểm triển khai.
`--candidates` được nhận diện nhưng trả mã 2 sau khi lưu rules, có thông báo
chưa tích hợp và không tạo/ghi đè candidates giả. Người 2 có thể import
`validator.rules.validate_rules` rồi bổ sung bước tạo candidates vào CLI.
Không chuyển ứng viên tự động thành lỗi đã xác nhận.

Kết quả, lệnh kiểm tra và artifact bàn giao: [DATA_VALIDATION.md](../submission/DATA_VALIDATION.md).
