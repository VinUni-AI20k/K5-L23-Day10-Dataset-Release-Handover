# Báo cáo nhóm 05

## 1. Số liệu luyện tập
- Người thực hiện phần đối chiếu: Hoàng Nhật Anh — 2A202603813; seed 5007. Kết quả đo lưu trong `measurements/cross_check_5007.json` và `measurements/clean_threshold_profiles.json`.
- Lô sạch `lab250_9144bc8fd60b`: 50 ảnh, 0 lỗi luật. Cách cũ chỉ xét bbox tạo 52 tín hiệu trên 22 ảnh; cách mới dùng pixel mask tạo 2 tín hiệu `instance_merge` trên 2 ảnh. Đây là bất đồng tự nhiên của lô không cài lỗi, vẫn cần người xem để giải thích.
- Lô luyện `lab250_afa095a47015`: 10 lỗi luật; 25 tín hiệu trên 21 ảnh, gồm 12 `instance_merge`, 8 bất đồng lớp, 3 `missing_box`, 2 `bbox_drift`. Kết quả lỗi luật của cả hai lô khớp bản chạy trước khi thay module đối chiếu.
- F1 rule / cross_check / overall: **chưa đo và chưa công bố**. Hàng đợi luyện tập chưa được nhóm review đầy đủ, chưa có `errors.json` cuối. Số ứng viên không phải số lỗi đúng hoặc recall.
- Ghép YOLO sang pixel, đối chiếu tên lớp, chọn segment thing không phải crowd có bbox IoU cao nhất. Tính containment bằng số pixel segment nằm trong box chia tổng pixel thật của segment; không lấy `area` khai báo thay số pixel.
- Bất đồng lớp: IoU ≥ 0,45 và containment ≥ 0,80. Đây chỉ là tín hiệu; người xem quyết định `class_swap` hay `category_swap`.
- Box lệch: cùng lớp, IoU ≥ 0,15, containment < 0,85, box chiếm ≥ 0,5% ảnh và segment đủ lớn. Segment đủ lớn nghĩa là ≥ max(256 pixel, 0,2% diện tích ảnh).
- Gộp instance: một segment có pixel riêng trong hai box cùng lớp; mỗi phần riêng ≥ 15%, hợp hai box chứa ≥ 80% pixel segment, IoU hai box ≤ 0,45. Không suy ra gộp chỉ vì bbox segment chứa hai tâm box. Thiếu box: segment đủ lớn và không có box ghép hợp lý; xem chi tiết ngưỡng trong `validator/cross_check.py`.
- Đo ba cấu hình trên cùng 50 ảnh sạch: sensitive = 4 tín hiệu/4 ảnh; balanced = 2/2; strict = 1/1. Giữ balanced vì hàng đợi sạch nhỏ và tránh siết tất cả ngưỡng chỉ để giảm thêm một tín hiệu. Chưa có bằng chứng recall; phải kiểm bằng review lô luyện. Không dùng đề ẩn hoặc `_private` để chọn ngưỡng.
- Giới hạn: nhiều đối tượng chồng nhau, segment gộp tự nhiên và matching nhầm vẫn có thể tạo ứng viên. Box quá rộng chứa trọn mask có thể không được quy tắc containment phát hiện. Ngưỡng diện tích có thể bỏ qua đối tượng nhỏ.
- Đề ẩn `lab250_62d7641abb98`: đã nhận 4 dòng confirmed của Nhật Anh cho `img_0061`, `img_0062`, `img_0079`, `img_0086`; chưa đủ review của nhóm. Giữ nguyên 206 tín hiệu/98 ảnh từ lượt chạy cũ đã dùng để xem ảnh; không ghi đè bằng thuật toán mới sau khi đã biết kết luận review.

## 2. Vì sao báo hết ứng viên làm F1 giảm?
Báo mọi ứng viên thành lỗi làm tăng FP: ngay trên lô sạch, cách cũ đã sinh 52 tín hiệu và cách mới vẫn sinh 2 tín hiệu dù lô không cài lỗi. Nếu coi các tín hiệu này là lỗi cài thì chúng đều là báo giả. Với cùng TP và FN, thêm FP làm mẫu số của F1 = 2TP/(2TP + FP + FN) tăng. Vì vậy phải xem ảnh và chỉ gộp những dòng người xem đã confirmed; giảm hàng đợi không tự chứng minh F1 tăng. Chưa có F1 trước/sau để tuyên bố mức cải thiện.

## 3. Quyết định và lineage
Hiện `runs/lineage.jsonl` mới có sự kiện inject seed 5007 và train R-021 trên v1. Nhóm còn phải chốt QC từ lỗi luật + review luyện tập, ghi quyết định HOLD và lý do, đánh giá ảnh hưởng tới R-021, rồi bàn giao v2 có parent trỏ v1. Chưa có handover hoàn chỉnh hoặc kết quả `check_handover.py` PASS để công bố. Phần này cần thành viên phụ trách lineage/bàn giao hoàn tất trước nộp cuối.

## 4. Hash chứng minh gì, không chứng minh gì?
SHA-256 khớp manifest chứng minh bytes hiện tại khớp bytes đã khai báo trong manifest; không chứng minh box đúng vị trí, lớp đúng vật thể hay guideline đúng. Manifest cũng phải được đối chiếu release_id; một manifest bị thay cùng dữ liệu không tự tạo bằng chứng nguồn đáng tin. Kiểm tra trước/sau phần việc này bằng hash toàn bộ file trong delivery để phát hiện thay đổi v1.

## 5. Truy vết
Ticket đề ẩn báo `truck` tại `scene_100` và `scene_777`, liên quan guideline v1.2 so với v1.3. Tầng a gồm ảnh có box truck, thuộc scene được báo và job còn v1.2: `img_0146`, `img_0157`, `img_0240`. Tầng b là các ảnh khác có cùng điều kiện job/lớp: `img_0019`, `img_0084`, `img_0169`. Danh sách cần thông báo từ các job liên quan: `A01`, `A02`, `Q01`, `Q03`. Lấy guideline theo job vì phiên bản của từng job là căn cứ đối chiếu metadata, không mặc định mọi ảnh dùng phiên bản mới nhất. Kết quả lưu trong `de_an/trace.json`; kết quả truy vết lô luyện vẫn cần thành viên phụ trách bổ sung.

## 6. Bug hoặc điểm chưa rõ trong lab (nếu có)
- Khi chạy `py -X utf8 -u scripts/run_lab.py --seeds 5007` trên Windows, tiến trình Python con do `run_lab.py` gọi không kế thừa cờ `-X utf8`. `inject_release.py` đã ghi xong lô nhưng phát sinh `UnicodeEncodeError` (console cp1252) khi in dòng thông báo tiếng Việt cuối cùng; `run_lab.py` dừng trước khi ghi lineage.
- Đã kiểm tra lô vừa tạo có 250 mục manifest/metadata, release_id khớp SHA-256 của manifest + metadata, hash label/mask khớp manifest. Sau đó dùng `scripts/lineage.py` ghi hai sự kiện còn thiếu: `inject` seed 5007 và `train` R-021 cho `lab250_afa095a47015`. Không sửa script hoặc dữ liệu v1.
- Với lần khởi tạo mới trên Windows, đặt `$env:PYTHONUTF8 = '1'` trước khi gọi `run_lab.py` để tiến trình con cũng dùng UTF-8. Không chạy lại lên lô hiện có vì script tạo lô có thể ghi đè thư mục đầu ra. Cần báo giảng viên về lỗi mã hóa này.
