# Báo cáo nhóm 12

## 1. Số liệu luyện tập

- Seed: `12007`, release v1: `lab250_7fa680a7413b`.
- Validator luật ghi nhận 12 finding; báo cáo Data Validation hiện có ghi F1 luật xấp xỉ 1.0 (số làm tròn).
- Validator đối chiếu của PR #3 quét được 249/250 ảnh, bỏ qua ảnh thiếu `000000021839`, và sinh 10 ứng viên trên 10 ảnh. Review log có 10 xác nhận và 1 ứng viên cũ bị bác bỏ; cả 10 xác nhận khớp ứng viên của bản PR hiện tại. Chưa có đủ truth độc lập để báo F1 cross-check hoặc F1 tổng.
- Lô sạch để đo số ứng viên và hiệu chỉnh ngưỡng không có trong workspace này. Vì vậy chưa thể xác minh số ứng viên trên lô sạch. `validator/README.md` nói ngưỡng đã hiệu chỉnh trên `runs/clean`, còn `prompts.md` ghi thời điểm ban đầu ngưỡng chưa hiệu chỉnh; nhóm cần xác nhận bằng chứng và thống nhất lại hai ghi chép.
- Review log có 11 dòng; 10 `confirmed`, 1 `rejected`. V2 chuyển 11 target có lỗi detection/thiếu ảnh sang rework queue.

## 2. Vì sao báo hết ứng viên làm F1 giảm?

Các khác biệt tự nhiên giữa detection và panoptic, như che khuất, crowd hoặc nhiều vật chồng lấn, có thể trông giống lỗi nhưng không phải lúc nào cũng là lỗi. Review log ghi một `instance_merge` bị bác bỏ vì ba người chồng lấn tự nhiên; nếu đưa trường hợp đó vào `errors.json` như lỗi thật thì sẽ tăng false positive và giảm precision. PR #3 hiện không phát sinh ứng viên này. Không suy ra F1/recall từ số xác nhận của hàng đợi vì review không phải nhãn truth độc lập cho toàn bộ lô.

## 3. Quyết định và lineage

`errors.json` có 22 finding, ứng với 21 target duy nhất trên 250 ảnh (`scene_leak` tính một target): `21/250 = 8.4%`, cao hơn ngưỡng 2%, nên giữ v1 ở trạng thái **HOLD**. Lineage ghi v1 bị HOLD và release `lab250_7fa680a7413b_v2` có parent v1. Truy vấn lineage xác nhận `R-021` bị ảnh hưởng; cần review hoặc retrain trước khi dùng tiếp.

V2 là release detection gồm 239 ảnh và 1.638 box. Mười một target lỗi detection hoặc thiếu ảnh được giao lại đúng annotator/reviewer theo `jobs.csv` và loại khỏi v2. Ảnh `000000005600` được mở kiểm tra, nội dung ảnh hiển thị bình thường nên giữ lại và tạo hash mới trong manifest v2. Metadata handover dùng guideline theo job; toàn bộ `scene_801` được đặt vào split `val`. Sáu finding chỉ thuộc panoptic được giữ trong release detection và ghi trong README v2 để chuyển team panoptic.

Bàn giao đã đóng gói; `check_handover.py` hiện đạt 17/17 mục. PASS xác nhận định dạng và tính nhất quán, không chứng minh nhãn đúng.

## 4. Hash chứng minh gì, không chứng minh gì?

Hash khớp là bằng chứng file hiện tại không đổi so với nội dung được dùng để tính hash. Hash khác cho biết nội dung khác hoặc cặp file/hash không khớp. Hash không chứng minh nhãn đúng: một box sai vẫn có thể có hash hợp lệ nếu file không bị thay đổi sau khi hash.

## 5. Truy vết

Ticket yêu cầu kiểm tra box `cup` bị che hoặc nằm ở mép ảnh tại `scene_609` và `scene_868`. Lớp `cup` có ID 41. Guideline v1.3 yêu cầu gán box cho các trường hợp này, trong khi v1.2 cho phép bỏ qua; guideline được lấy từ `jobs.csv` vì metadata từng ảnh có thể sai.

- Tầng A: `000000002157`, `000000002431`, `000000002592`, `000000002685`.
- Tầng B: `000000003661`, `000000003845`, `000000003934`.
- Báo `A02` và `Q03`, annotator và reviewer của job `J02`.

Các ảnh này là phạm vi truy vết theo ticket, không phải khẳng định từng ảnh đã được xác nhận lỗi. Danh sách nằm trong `runs/r12007/trace.json`.

## 6. Bug hoặc điểm cần chốt

- Bằng chứng chạy hiệu chỉnh ngưỡng trên lô sạch `runs/clean` không có trong checkout hiện tại; đối chiếu lại với ghi chép trong `prompts.md` trước khi nộp.
- Nhóm hiện khai báo 4 thành viên trong `TEAM.md`, trong khi `RULES.md` nêu nhóm 5–6 người; xác nhận quy mô nhóm với giảng viên.
- Chưa có dữ liệu đề ẩn được giao nên chưa tạo `submission/de_an/`. Không tạo giả kết quả đề ẩn.
