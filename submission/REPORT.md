# Báo cáo nhóm TranTuanAnh

## 1. Số liệu luyện tập
- Seed 76 sau review: 22 lỗi trong errors.json, gồm 11 lỗi luật và 11 lỗi gán nhãn được xác nhận. F1 làm tròn theo script tự đo: lỗi luật ≈ 1,0, lỗi gán nhãn ≈ 0,4, tổng ≈ 0,7.
- Lô sạch có 0 lỗi luật, 6 ứng viên trên 4 ảnh. Seed 76 có 21 ứng viên trên 17 ảnh.
- Ngưỡng chạy hiện tại: IoU-mask từ 0,30 để ghép và từ 0,50 để xét khác lớp. Ứng viên lệch box có dưới 75% pixel segment nằm trong box. Ca thiếu box xét segment từ 1.500 pixel với độ phủ tối đa dưới 30%. Ca gộp vật bỏ các cặp box có IoU trên 0,60. Với các ngưỡng này, nhóm xem được cả 21 ứng viên của seed 76. Nhật ký loại 10 ứng viên, và F1 lỗi gán nhãn sau review ≈ 0,4, nên kết quả còn dư địa cải thiện.

## 2. Vì sao báo hết ứng viên làm F1 giảm?
Lô sạch vẫn sinh 6 ứng viên do hai nguồn nhãn có thể lệch tự nhiên. Nếu báo tất cả, các ứng viên lệch tự nhiên bị tính là dương tính giả. Khi số lỗi phát hiện đúng giữ nguyên, dương tính giả làm giảm precision và F1. Ở seed 76, nhật ký ghi 11 ca xác nhận và 10 ca loại bỏ trên 21 ứng viên. Ghi cả 21 ca thành lỗi sẽ đưa thêm 10 ca bị loại vào danh sách.

CP2: Mỹ Tâm xem ban đầu toàn bộ 21 thẻ. Bốn thành viên xem lại và đồng ý với kết luận: Trần Tuấn Anh (#1, #2, #3), Doãn Tùng Lâm (#4, #5, #9), Trần Thị Ngọc Ánh (#6, #7, #10), Lương Quốc Việt (#8, #11, #12).

## 3. Quyết định và lineage
- QC v1 có **22 lỗi trên 250 ảnh**, tức `22/250 = 8,8%`. Vì 8,8% lớn hơn
  ngưỡng 2%, kết luận của nhóm cho lô v1 là **HOLD**, không được Release.
- Quyết định này được ghi append-only vào `lineage.jsonl` với event
  `decision`, `decision=HOLD`, và đúng `release_id` của v1. Không sửa hoặc
  ghi đè các event trước đó.
- Lệnh kiểm tra ảnh hưởng:
  `python scripts/lineage.py impact --release-id <release_id_v1>`.
  Kết quả mong đợi là `R-021: affected=True action=review_or_retrain`.
- `R-021` phải được xem lại hoặc train lại vì model đã học từ release v1;
  thay đổi dataset sau đó không thể tự sửa các trọng số đã học. Khi phát hiện
  v1 bị giữ, lineage giúp truy ra đúng training run bị ảnh hưởng và ngăn dùng
  kết quả cũ như thể dữ liệu vẫn hợp lệ.

Việc ghi event được thực hiện bởi `scripts/record_cp3.py`. Script đọc
`runs/r76/delivery/release.json`, nên không phải tự điền hoặc đoán
`release_id`.

## 4. Hash chứng minh gì, không chứng minh gì?
<<>>

## 5. Truy vết
<<Tiêu chí tầng a/b, vì sao lấy guideline theo job.>>

## 6. Bug hoặc điểm chưa rõ trong lab (nếu có)
<<>>
