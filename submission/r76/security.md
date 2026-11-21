# Bảo mật khi làm việc

> Gắn với lô nhóm vừa nhận: seed 76, release v1 `lab250_f95ccfbc1285` (250 ảnh, 10 job, người gán A01–A05, người kiểm Q01–Q03). Riêng lỗi luật QC đã thấy 11/250 ảnh (4,4%), vượt ngưỡng 2%, nên lô v1 phải **HOLD**.

## 1. Ca USB: hết giờ, muốn chép lô về nhà làm tiếp

Không chép lô ra USB. Lô 76 có 250 ảnh, trong đó 138 ảnh có nhãn `person` (người thật), kèm mã người gán/kiểm và ticket nội bộ; ra khỏi máy công ty là mất kiểm soát: USB có thể rơi, không ai biết bản sao nằm ở đâu, và không truy vết được ai đã mở. Gửi qua email cá nhân cũng vậy (dữ liệu nằm trên hệ thống ngoài công ty), còn nhờ người khác làm hộ thì người đó không được giao job và phải dùng tài khoản của mình, phá truy vết theo `jobs.csv`. Cách đúng: dừng ở chỗ đang làm, lưu tiến độ trên máy/hệ thống của công ty, báo lead nếu bị trễ; nếu thật sự cần làm từ xa thì xin quyền truy cập từ xa (VPN, máy ảo) qua người phụ trách, không tự mang dữ liệu đi.

## 2. Năm việc: được hay không

- **Mở job được giao trên máy công ty: được.** Đúng job mình được giao trong `jobs.csv`, trên máy được quản lý, mọi thao tác truy vết được.
- **Chụp màn hình gửi người quen: không.** Ảnh chụp chứa ảnh người thật và nhãn của lô; gửi đi là rò rỉ dữ liệu, không thu hồi được.
- **Chép lô ra USB: không.** Như ca 1: mất kiểm soát bản sao, không truy vết được, nhất là khi lô v1 phải HOLD và chưa được phép phát hành.
- **Dán nhãn thật lên chatbot: không.** Dữ liệu thật đi ra dịch vụ bên ngoài, có thể bị lưu hoặc dùng để train. Trong lab này COCO là dữ liệu công khai nên nhóm được dán và đã ghi lại trong `prompts.md`; với dữ liệu thật của dự án thì không.
- **Đưa tài khoản CVAT cho đồng nghiệp: không.** Mỗi job ghi rõ người gán và người kiểm (ví dụ J01: A02/Q03); dùng chung tài khoản thì không biết ai thật sự gán, khi có lỗi (như ticket `wine glass`) không truy được đúng người cần báo.

## 3. Ca khuôn mặt: thấy mặt người rõ trong lô, guideline yêu cầu làm mờ

Ví dụ trong lô 76: ảnh `000000020992` (Tuấn Anh đã mở ảnh xác nhận: cận mặt một người, nhìn thẳng vào máy ảnh; nhãn detection có box `person` phủ gần hết khung ảnh). Khi thấy mặt người rõ mà guideline yêu cầu làm mờ: **Hold lô** (không bàn giao, không đưa cho team AI train) và **báo người phụ trách** (lead dữ liệu / người phụ trách bảo mật), ghi lại tên ảnh. Không tự làm mờ vì: sửa ảnh làm đổi sha256 so với manifest và phá lineage của lô; làm mờ đúng vùng, đúng mức là quyết định của người phụ trách theo quy trình, không phải của người gán; tự sửa một ảnh thì các ảnh tương tự khác vẫn lọt. Không tự xoá vì mất dấu vết để kiểm tra và có thể cần giữ lại để xử lý theo quy định. Lô chỉ được phát hành lại sau khi người phụ trách xử lý và ghi vào lineage.
