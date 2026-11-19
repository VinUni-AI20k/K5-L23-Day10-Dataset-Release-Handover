# Bảo mật khi làm việc

> Gắn với lô nhóm 7 vừa bàn giao: v1 `lab250_5279e3fe917f` (250 ảnh, HOLD) và v2 `lab250_5279e3fe917f_v2` (243 ảnh).

## 1. Ca USB: hết giờ, muốn chép lô về nhà làm tiếp
Không chép lô ra USB. Lô `lab250_5279e3fe917f` gồm 250 ảnh, nhãn, mask và `jobs.csv` có mã người gán/người kiểm; USB dễ rơi, dễ bị chép tiếp và công ty không còn kiểm soát được bản sao đó. Gửi vào email cá nhân cũng sai vì dữ liệu ra khỏi hệ thống của công ty, nằm trên server ngoài và không thu hồi được. Nhờ đồng nghiệp làm hộ bằng tài khoản của mình thì nhật ký sẽ ghi sai người làm, đúng chỗ lab này đang dùng để truy vết. Cách đúng: dừng ở mốc đang làm, commit/lưu tiến độ trên máy công ty, báo trưởng nhóm xin thêm thời gian hoặc làm tiếp qua VPN/máy được cấp nếu công ty cho phép.

## 2. Năm việc: được hay không
- Mở job được giao trên máy công ty: **được**. Đúng người, đúng job, đúng thiết bị; mọi thao tác được ghi lại.
- Chụp màn hình gửi người quen: **không**. Ảnh chụp mang dữ liệu ra ngoài, lộ ảnh người thật (ví dụ ảnh `000000004395`), không thu hồi được.
- Chép lô ra USB: **không**. Mất kiểm soát bản sao, như mục 1.
- Dán nhãn thật lên chatbot: **không**. Dữ liệu dự án bị gửi cho bên thứ ba ngoài hợp đồng. Lab này chỉ được dán ảnh COCO vì là dữ liệu công khai và có ghi lại trong `prompts.md`.
- Đưa tài khoản CVAT cho đồng nghiệp: **không**. Nhật ký sẽ ghi sai người gán/người kiểm, làm hỏng truy vết kiểu `rework_queue.csv` và `notify` mà nhóm vừa làm; mỗi người dùng tài khoản của mình.

## 3. Ca khuôn mặt: thấy mặt người rõ trong lô, guideline yêu cầu làm mờ
Trong lô có ảnh thấy rõ mặt người: `000000004395` (người đàn ông áo sơ mi trắng, cà vạt, mặt nhìn nghiêng rõ) và `000000001296` (cô gái cầm điện thoại, mặt nhìn thẳng rõ). Theo guideline phải làm mờ, nên kết luận là **Hold** lô (không cho đi tiếp phần có ảnh đó) và **báo người phụ trách** (trưởng nhóm dữ liệu / người phụ trách bảo mật), ghi tên ảnh vào ticket. Không tự làm mờ hay tự xoá ảnh, vì như vậy là sửa lô đã giao mà không có quyết định: hash trong manifest đổi, lineage không ghi lại ai sửa và vì sao, và có thể làm mờ sai chỗ hoặc thiếu ảnh. Người phụ trách quyết định cách xử lý chung (làm mờ bằng quy trình chuẩn, ra bản mới có parent, ghi lineage), giống cách nhóm làm v2 thay vì sửa v1.
