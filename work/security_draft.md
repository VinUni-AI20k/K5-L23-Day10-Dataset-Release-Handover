# Bảo mật khi làm việc

> Gắn với lô luyện tập seed 13007 (`lab250_a13aacb20205`, 250 ảnh COCO, bàn giao v2 `lab250_a13aacb20205_v2`).

## 1. Ca USB: hết giờ, muốn chép lô về nhà làm tiếp

Không chép lô `lab250_a13aacb20205` ra USB hay máy cá nhân. Lô có 250 ảnh, trong đó nhiều ảnh có người thật nhìn rõ mặt (ví dụ `000000004395`, `000000016598`), kèm mã người gán và người kiểm trong `jobs.csv`. USB dễ mất, không mã hoá, và khi ra khỏi hệ thống thì không còn ai biết bản sao nằm ở đâu. Gửi qua email cá nhân cũng sai vì cùng lý do: dữ liệu rời khỏi hạ tầng công ty và nằm lại trên server bên ngoài. Nhờ người khác làm hộ cũng sai, vì người đó không được giao job, và nhật ký sẽ ghi sai người gán, người kiểm (đúng thứ `truyvet.csv` và `rework_queue.csv` dựa vào). Cách đúng: báo trưởng nhóm (Huy) phần còn dở, xin gia hạn hoặc làm tiếp trên máy công ty, hoặc qua VPN/remote desktop nếu công ty cấp quyền.

## 2. Năm việc: được hay không

1. **Mở job được giao trên máy công ty: ĐƯỢC.** Đúng người, đúng máy, đúng quyền, nên mọi thao tác có nhật ký và truy vết được về job (ví dụ J02 của A04/Q02).
2. **Chụp màn hình gửi người quen: KHÔNG.** Ảnh chụp màn hình vẫn là dữ liệu, và có thể lộ mặt người thật (như `000000023899`, ba người ngồi trên ghế sofa) ra ngoài phạm vi được phép, không thu hồi được.
3. **Chép lô ra USB: KHÔNG.** Dữ liệu rời khỏi hệ thống được kiểm soát, xem mục 1.
4. **Dán nhãn thật lên chatbot: KHÔNG.** Nội dung gửi lên dịch vụ ngoài có thể bị lưu, dùng để huấn luyện hoặc lộ ra. Khi nhờ AI viết code (validator, `build_handover.py`), nhóm chỉ mô tả định dạng và dùng dữ liệu giả, không dán ảnh, nhãn hay `jobs.csv` thật.
5. **Đưa tài khoản CVAT cho đồng nghiệp: KHÔNG.** Mỗi tài khoản gắn với một người. Dùng chung thì nhật ký ghi sai người, mất khả năng truy vết khi team AI báo lỗi (như ticket về `cup` ở scene_342 và scene_675). Cần thêm người thì xin trưởng nhóm cấp quyền riêng.

## 3. Ca khuôn mặt: thấy mặt người rõ trong lô, guideline yêu cầu làm mờ

Trong lô có nhiều ảnh thấy rõ mặt người, ví dụ:
- `000000004395` (scene_209, job J02, A04/Q02): chân dung cận một người đàn ông đeo cà vạt, mặt chiếm gần nửa khung hình.
- `000000016598` (scene_576, job J07, A05/Q01): ảnh selfie trước gương của một phụ nữ tóc xanh, mặt nhìn thẳng, góc ảnh còn có chữ ký tên người chụp.
- `000000023899` (scene_321, job J10, A04/Q03): ba người ngồi chơi game, hai khuôn mặt nhìn rõ.

Kết luận: **Hold** các ảnh này (không đưa vào bản Release cho team AI cho đến khi xử lý xong) và **báo người phụ trách dữ liệu / trưởng nhóm**, kèm danh sách tên ảnh, job, người gán và người kiểm. Không tự làm mờ hay tự xoá ảnh: làm vậy là sửa dữ liệu ngoài quy trình, khiến sha256 trong manifest không còn khớp, nhãn có thể lệch theo, và mất truy vết ai đã đổi gì. Việc làm mờ phải do người phụ trách quyết định, làm theo guideline, ra một phiên bản mới có lineage ghi rõ lô cha, giống cách nhóm làm v2 mà không ghi đè v1.
