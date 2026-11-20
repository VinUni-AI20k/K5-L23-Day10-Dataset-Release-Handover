# Nhật ký sử dụng AI

Nhật ký này ghi lại các prompt và hỗ trợ AI được lưu cho những phần việc bên dưới. AI được dùng không chỉ để tra cứu công thức/cú pháp mà còn đưa ra gợi ý lập trình và thuật toán; thành viên chịu trách nhiệm rà soát, chỉnh sửa và kiểm chứng phần mình nộp. Các ghi chú gỡ lỗi hồi cứu được ghi rõ là tóm tắt, không phải prompt nguyên văn nếu không có nội dung prompt gốc. AI không được dùng để quyết định verdict thay người review.

---

## Phần A: Thành viên D — Truy vết và Bảo mật
Người thực hiện: Nguyễn Thanh Quang (2A202603083)  
Công cụ: Copilot SDK trong VS Code

### 1. Xác định phần việc được giao
**Prompt nguyên văn:**
> đọc nội dung này cần làm những j và làm vào dự án giup tôi, lưu ý chỉ làm phần của mình ko đụng phần của người khác và làm thật cẩn thận

**Kết quả AI:** Tóm tắt các đầu việc của Thành viên D (truy vết ticket, bảo mật, tài liệu).  
**Kiểm chứng:** Đối chiếu với `GUIDE.md` và `RULES.md`.

### 2. Chuyển sang nhánh D-Trace
**Prompt nguyên văn:**
> tiếp tục đi và làm vào nhánh D-Trace cho tôi

**Kết quả AI:** Chuyển sang làm việc trên nhánh `D-Trace`.  
**Kiểm chứng:** Kiểm tra nhánh bằng Git; chỉ thao tác trên các file thuộc phân công.

### 3. Tạo lô theo seed 3007 (sau đó được đính chính)
**Prompt nguyên văn:**
> Nhóm mình thống nhất dùng seed 3007 (nếu chưa có seed chính thức khác).
> Do `runs/` và `data_source/` bị Git ignore nên pull GitHub sẽ không có dữ liệu.
> Nếu máy bạn chưa có delivery thì chạy:
> `python scripts/download_public.py`
> `python scripts/run_lab.py --seeds 3007`
> Sau đó làm tiếp phần truy vết:
> - Đọc `incoming/ticket.md` và `guideline/changelog.md`.
> - Đối chiếu `jobs.csv`, `metadata.json` và `labels/`.
> - Xác định `tier_a`, `tier_b`, `notify`.
> - Tạo `trace.json` từ dữ liệu thật.
> - Hoàn thành `security.md`, trong đó phần xác nhận ảnh khuôn mặt phải có người xem ảnh thật.
> Không đọc `_private/`, không sửa `delivery/`.
> Xong thì báo lại kết quả, các file đã tạo và những phần cần nhóm hỗ trợ.

**Kết quả AI:** Tạo lô 3007.  
**Sai sót và khắc phục:** Nhóm đính chính seed chính thức là `2902`. Thành viên D đã xóa lô 3007, loại sự kiện thừa khỏi lineage và chạy lại đúng trên `2902`.

### 4. Đính chính seed về 2902
**Prompt nguyên văn:**
> nhom_va_repo=bạn cần đổi chút seed là seed 2902 , github_username=Nguyễn Thanh Quang, thanh_vien_va_phan_cong=Nguyễn Thanh Quang, 2A202603083, nguyenvantuc07102015@gmail.com, xac_nhan_lineage=seed là 2902 còn 3007 là nhầm

**Kết quả AI:** Cập nhật thông tin sang seed 2902.  
**Kiểm chứng:** Đối chiếu ticket, changelog, `jobs.csv`. Guideline xác định theo `jobs.csv`.

### 5. Kiểm tra ảnh khuôn mặt
**Prompt nguyên văn:**
> Bạn tiếp tục hoàn thiện phần Security nhé.
> Với danh sách 20 ảnh ứng viên có class person, bạn tự mở ảnh để kiểm tra trực tiếp, chọn một ảnh có khuôn mặt người thật nhìn thấy rõ.
> Sau đó ghi đúng image ID và tình huống xử lý vào security.md theo template của đề.
> Phần khuôn mặt phải kết luận HOLD + báo người phụ trách, không tự ý làm mờ hoặc sửa dataset gốc.
> Khi hoàn thành, bạn kiểm tra lại trace.json và security.md, rồi commit và push lên branch D-Trace, tạo Pull Request để mình review và merge.
> Báo lại mình file nào đã hoàn thành và kết quả kiểm tra nhé.

**Kết quả AI:** Gợi ý ảnh `000000001000.jpg`.  
**Kiểm chứng:** Thành viên Quang tự mở file ảnh kiểm tra thực tế, thấy nhiều khuôn mặt người thật nhìn rõ. Điền kết luận HOLD và báo cáo theo đúng quy định.

---

## Phần B: Thành viên C — Đối chiếu Detection ↔ Panoptic và Công cụ Review
Người thực hiện: Trịnh Xuân Toàn (2A202603121)  
Hỗ trợ AI được ghi lại: công thức, API và gợi ý thuật toán; thành viên kiểm tra kết quả trước khi dùng.

### 1. Tra cứu công thức chuyển đổi tọa độ và tính IoU bằng thư viện chuẩn
**Mục đích:** Xây dựng module `validator/cross_check.py` tuân thủ nguyên tắc validator chỉ dùng thư viện chuẩn (`math`, `json`, `sys`, `pathlib`).

**Prompt nguyên văn:**
> Viết giúp tôi một hàm Python thuần (chỉ dùng math/thư viện chuẩn) tính IoU giữa 2 bounding box dạng [x, y, w, h] tọa độ pixel, và công thức đổi từ nhãn YOLO normalized (xc, yc, w, h) sang pixel [x_min, y_min, w_px, h_px] khi biết width, height ảnh.

**Kết quả AI:** Cung cấp code mẫu cho hàm `calculate_iou(box_a, box_b)` và công thức chuyển đổi `x_min = (xc - w/2) * width`.
**Phần việc của thành viên:** Trịnh Xuân Toàn chịu trách nhiệm tích hợp và kiểm tra phần đọc `labels/*.txt` và `panoptic.json`, cũng như rà soát trường hợp union không dương. Module có các heuristic do nhóm lựa chọn và triển khai; không nên hiểu prompt tra cứu này là bằng chứng AI không tham gia gợi ý lập trình khác.

### 2. Tra cứu cú pháp Pillow để vẽ bounding box trực quan
**Mục đích:** Xây dựng công cụ xem ảnh `tools/review_tool.py` phục vụ cả nhóm mở ảnh review nhanh.

**Prompt nguyên văn:**
> Tôi dùng thư viện Pillow để vẽ các bounding box detection (màu xanh lá) và segment panoptic (màu cam) lên ảnh JPG, ghi nhãn text phía trên box. Cho tôi cú pháp chuẩn của ImageDraw.Draw và draw.rectangle, draw.text.

**Kết quả AI:** Cung cấp code mẫu sử dụng `ImageDraw.Draw(im).rectangle` và `draw.text`.
**Phần việc của thành viên:** Trịnh Xuân Toàn tích hợp công cụ đọc dữ liệu, xuất ảnh vào `visualized/` và dashboard HTML (`review_dashboard.html`); AI hỗ trợ bằng ví dụ API nêu trên. Code hiện trực quan hóa box của detection và bbox của segment panoptic, chưa vẽ contour pixel của mask.

### 3. Gợi ý AI và các lần thử/điều chỉnh thuật toán

Hai mục dưới đây là tóm tắt hồi cứu quá trình thử nghiệm, không phải prompt nguyên văn. Chỉ giữ các chi tiết về lần thử và số lượng ứng viên nếu thành viên có thể xác nhận chúng từ lịch sử làm việc của nhóm.

Trong quá trình phát triển bộ lọc candidates, nhóm đã xem xét các gợi ý thuật toán và điều chỉnh dựa trên kết quả chạy/review:

1. **Xử lý ca `missing_box` ở ảnh `000000023937`:**
   - *Gợi ý ban đầu được ghi nhận:* kiểm tra một segment panoptic với bất kỳ box nào trong ảnh bằng ngưỡng IoU.
   - *Lỗi thực tế:* Trên ảnh `000000023937` (đàn bò trên đồng cỏ), có một con bò bị thiếu box detection. Tuy nhiên, con bò bên cạnh đã được gán box và box đó vô tình giao với segment con bò này với IoU 0.388. Logic của AI khiến ca này bị bỏ qua (False Negative).
   - *Điều chỉnh:* Toàn dùng ghép một-đối-một theo IoU giảm dần và chỉ xét các đối tượng chưa ghép cho bước tiếp theo. Bản hiện tại bỏ qua cặp có IoU bằng 0. Trên seed đang kiểm tra, module phát ra candidate cho ảnh này; không khẳng định đây là độ chính xác 100% trên các lô khác.

2. **Lọc candidate `instance_merge`:**
   - *Gợi ý ban đầu được ghi nhận:* dùng ngưỡng IoU thô để phát hiện nhiều box cùng lớp trong một segment.
   - *Điều chỉnh được triển khai:* dùng tỷ lệ containment của box trong segment bbox (>=65%), yêu cầu tối thiểu hai box và so sánh số box với số segment cùng lớp. Candidate seed 2902 có một dòng `instance_merge` cho ảnh `000000015440`.

3. **Quyết định review:**
   - Verdict phải do thành viên trực tiếp mở ảnh và quyết định; AI không được dùng để phán quyết đúng/sai của nhãn.
   - Hai file review hiện có 24 dòng (6 `confirmed`, 18 `rejected`). Format hiện tại chưa ghi tên reviewer trong từng dòng. Trước khi nộp, nhóm cần bổ sung tên đúng của người đã xem vào ghi chú từng ca theo RULES; không suy đoán hoặc tự gán reviewer sau sự việc.
