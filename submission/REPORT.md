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
Hash giúp kiểm tra tính toàn vẹn của file. Khi tính lại hash của file và so với hash đã ghi trước đó:

- Hash khớp: có bằng chứng mạnh rằng nội dung file hiện tại không thay đổi so với lúc hash được ghi.
- Hash khác: nội dung file đã thay đổi, hoặc hash/file dùng để so không đúng.

Hash không chứng minh nội dung đúng. Ví dụ, một file nhãn có box sai nhưng không bị thay đổi trong lúc bàn giao thì hash vẫn khớp. Muốn biết nhãn đúng hay sai, nhóm vẫn phải đối chiếu và xem ảnh.

## 5. Truy vết
<<Tiêu chí tầng a/b, vì sao lấy guideline theo job.>>
Theo ticket của team AI, hai cảnh `scene_609` và `scene_868` có
nguy cơ bỏ sót box của lớp `cup` khi vật bị che hoặc nằm ở mép ảnh.
Changelog cho biết quy tắc gán box của lớp `cup` đã thay đổi từ
guideline v1.2 sang v1.3.

Nhóm đối chiếu `metadata.json`, `jobs.csv` và các file trong
`labels/` để tìm ảnh thuộc job dùng guideline v1.2 và có ít nhất
một box detection của lớp `cup` (mã lớp 41 trong `classes.txt`).
Phiên bản guideline được lấy từ `jobs.csv`, vì phiên bản ghi ở
từng ảnh trong metadata có thể bị sai.

Kết quả truy vết lô luyện tập seed 12007:

- Tầng A: 4 ảnh thỏa điều kiện và thuộc hai cảnh được nêu trong ticket.
- Tầng B: 3 ảnh thỏa điều kiện, thuộc các cảnh khác chưa được nêu.
- Người cần thông báo: `A02` và `Q03`, lần lượt là người gán nhãn
  và người kiểm của job `J02`, job chứa cả 7 ảnh trên.

Danh sách mã ảnh và người cần thông báo được lưu trong
`runs/r12007/trace.json`. Đây là phạm vi cần kiểm tra theo tiêu chí
truy vết của bài; không đồng nghĩa tất cả các ảnh đã được xác nhận
là có lỗi.

## 6. Bug hoặc điểm chưa rõ trong lab (nếu có)
<<>>
