# Người 2: Annotation Review

## Mục tiêu

Tạo danh sách ảnh có dấu hiệu lỗi gán nhãn, chuẩn bị cách xem ảnh và điều phối review để nhóm xác nhận lỗi bằng mắt.

## Đầu vào

- Ảnh, nhãn YOLO, mask và `panoptic.json` trong thư mục `delivery/`.
- `classes.txt` để ghép lớp theo **tên**, không giả định ID hai nguồn giống nhau.
- `rules.json` từ Người 1 để tổng hợp kết quả.

## Phụ thuộc và điểm dừng cho agent

- **Cần trước khi chạy trên dữ liệu thật:** `delivery/` và seed của nhóm. Khi chưa có, đọc định dạng, chuẩn bị logic và công cụ review; không tự chọn lô thay nhóm.
- **Không cần đợi `rules.json` để bắt đầu:** có thể tạo candidates, kiểm tra trên lô sạch và chuẩn bị công cụ xem ảnh song song với Người 1.
- **Cần từ Người 1 để gộp kết quả cuối:** `rules.json` sinh trên đúng lô. Nếu chưa có, giữ candidates và review riêng, báo đang chờ; không tự tạo `rules.json` rỗng rồi coi `errors.json` là hoàn chỉnh.
- **Cần con người review:** cả nhóm phải xem ảnh và ghi nhận `confirmed`/`rejected` trước khi chốt lỗi gán nhãn. Agent không tự điền verdict hoặc giả lập ghi chú quan sát.
- **Cần phối hợp tích hợp với Người 1:** thống nhất giao diện module, chủ sở hữu `validator/validate.py` và cách tích hợp `--candidates`; không ghi đè thay đổi của nhau.
- **Bàn giao:** chỉ chuyển `errors.json` cho Người 3 dưới dạng kết quả cuối sau khi đã gộp lỗi luật và review thật; nếu là bản chưa đủ, phải ghi rõ trạng thái.

## Yêu cầu chức năng

| Mã | Yêu cầu | Dấu hiệu cần xem |
|---|---|---|
| REV-01 | Chuyển box YOLO sang pixel và ghép với segment theo vị trí. | Cơ sở đối chiếu hai nguồn. |
| REV-02 | Ghép lớp detection và panoptic theo tên lớp. | Cơ sở so sánh lớp. |
| REV-03 | Tìm hai nguồn khác lớp tại cùng vị trí. | `class_swap` hoặc `category_swap`. |
| REV-04 | Tìm dấu hiệu box lệch khỏi vật. | `bbox_drift`. |
| REV-05 | Tìm segment đáng kể không có box phù hợp. | `missing_box`. |
| REV-06 | Tìm segment có dấu hiệu gộp hai vật cùng lớp. | `instance_merge`. |
| REV-07 | Tạo candidates và hỗ trợ xem ảnh cùng box/mask. | Nhóm review bằng mắt. |
| REV-08 | Ghi review và gộp kết quả đã xác nhận với lỗi luật. | Tạo `errors.json`. |

Sử dụng pixel mask bổ sung cho IoU; khác biệt giữa hai nguồn là **ứng viên**, chưa tự động là lỗi. Chạy trên lô sạch để đo nhiễu, ghi số ứng viên, ngưỡng và lý do lựa chọn.

## Đầu ra và bàn giao

- `candidates.json` cho lô luyện tập và đề ẩn.
- Công cụ hoặc quy trình xem ảnh đủ rõ để phân biệt hai nguồn nhãn.
- `review_log.csv` do cả nhóm cùng thực hiện, ghi `image,type,verdict,note`; ghi chú nói thấy gì và ai xem.
- `errors.json` gồm lỗi luật và lỗi gán nhãn đã `confirmed`, bàn giao cho Người 3.
- Số ứng viên trên lô sạch, số liệu hàng đợi và cách chọn ngưỡng, bàn giao cho Người 4.

```powershell
py scripts/merge_review.py --rules runs/r3007/rules.json --review runs/r3007/review_log.csv --out runs/r3007/errors.json
```

Thay `3007` bằng seed của nhóm. Phối hợp Người 1 để tích hợp tùy chọn `--candidates` trong giao diện validator chung.

## Ràng buộc

- Validator chỉ đọc `delivery/`, chỉ dùng thư viện chuẩn và không dùng mạng; có thể dùng `scripts/pngutil.py`.
- Công cụ xem ảnh riêng có thể dùng Pillow.
- Không coi mọi ứng viên là lỗi; không dùng AI thay việc xem ảnh.
- Cả 4 thành viên đều phải xem ảnh. Với đề ẩn, lỗi gán nhãn được nộp phải có dòng `confirmed` và ghi chú ít nhất 20 ký tự theo rubric.

## Kiểm tra và nghiệm thu

- [ ] Có candidates cho seed luyện tập và đề ẩn; xử lý được tên ảnh `img_0001`.
- [ ] Đo ứng viên trên lô sạch, ghi ngưỡng và lý do chọn.
- [ ] Chia hàng đợi cho cả nhóm và xem hết trong thời gian cho phép.
- [ ] Mọi lỗi gán nhãn trong `errors.json` có dòng `confirmed` tương ứng.
- [ ] Ghi chú phản ánh quan sát thật; trường hợp `rejected` có lý do.
- [ ] Giải thích được cách phân biệt `class_swap` với `category_swap`.

## Việc chung

Tham gia review, làm đề ẩn, ghi lại việc dùng AI và có ít nhất 2 commit có nội dung. Đọc [GUIDE.md](../GUIDE.md), [DELIVERY.md](../docs/DELIVERY.md) và [RUBRIC.md](../RUBRIC.md).
