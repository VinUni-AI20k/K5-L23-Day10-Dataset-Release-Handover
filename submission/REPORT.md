# Báo cáo nhóm — Lab Day 10: Dataset Release & Handover

*VinUni AI20K · Cohort 5 · Level 2–3*

## 1. Tổng quan và kết quả luyện tập

Lab mô phỏng quy trình tiếp nhận một lô dữ liệu, phát hiện lỗi, quyết định phát hành, đóng gói bản bàn giao cho team AI và truy vết khi có ticket. Nhóm thực hành trên seed `2902`, với release v1 `lab250_9f8af853f974` gồm 250 ảnh COCO val2017.

Validator **Detection** kiểm tra file ảnh, SHA-256, ID lớp và tọa độ, kích thước, trùng lặp của box YOLO. Validator **Metadata** kiểm tra scene bị chia giữa train và val, cùng phiên bản guideline của từng job. Validator **Panoptic** kiểm tra ID lớp và đối chiếu diện tích khai báo với số pixel của segment trong mask. Bước **Cross-check Detection ↔ Panoptic** đối chiếu hai nguồn nhãn trên cùng ảnh để tạo hàng đợi xem ảnh. [Validator](../validator/validate.py) · [Cross-check](../validator/cross_check.py)

| Chỉ số QC v1 | Kết quả |
| --- | ---: |
| Lỗi luật | 9 (Detection 5, Metadata 2, Panoptic 2) |
| Ứng viên gán nhãn | 24 trên 16 ảnh |
| Kết quả review | 6 `confirmed`, 18 `rejected` |
| Lỗi trong `errors.json` | 15 |
| Tỷ lệ lỗi và ngưỡng Release | 15/250 = **6,0%**, ngưỡng **2%** |
| Quyết định QC | **HOLD** |

Mỗi ứng viên là một nghi vấn theo cặp ảnh và loại lỗi. Một khác biệt về lớp có thể sinh hai ứng viên để người xem ảnh xác định nguồn nào sai. Kết quả đối chiếu cho thấy `errors.json` gồm đúng lỗi luật và các lỗi gán nhãn có verdict `confirmed`. [Danh sách lỗi](r2902/errors.json) · [Ứng viên](r2902/candidates.json) · [Nhật ký review](r2902/review_log.csv)

## 2. Cross-check, ngưỡng và đánh giá F1

Code đổi box YOLO chuẩn hóa sang tọa độ pixel và đối chiếu theo tên lớp. Phía Panoptic chỉ xét segment `thing` và bỏ qua `iscrowd`. IoU là tỷ lệ giữa diện tích giao và diện tích hợp của hai bbox. Hai bước phát hiện drift và thiếu box dùng ghép tham lam một-đối-một theo IoU giảm dần trong từng lớp, với IoU > 0.

| Ứng viên | Điều kiện trong code |
| --- | --- |
| `class_swap`, `category_swap` | Với mỗi box detection, nếu segment có IoU cao nhất đạt ≥ 0,40 và tên lớp khác nhau, sinh cả hai loại ứng viên. `class_swap` nghi lỗi Detection, `category_swap` nghi lỗi Panoptic. |
| `bbox_drift` | Cặp đã ghép cùng lớp có IoU từ 0,35 đến 0,78, tâm lệch ≥ 8% đường chéo của box detection và box đó chiếm ≥ 0,5% diện tích ảnh. |
| `missing_box` | Segment chưa ghép có `area` ≥ 1.000 pixel và bbox chiếm ≥ 1% ảnh. IoU cao nhất với các box còn lại ở lượt xét lớp đó phải < 0,40. |
| `instance_merge` | Số box cùng lớp có diện tích ≥ 400 px² phải nhiều hơn số segment cùng lớp. Bbox của segment phải chứa ≥ 65% diện tích của mỗi box trong ít nhất hai box đạt điều kiện. Trong nhóm này phải có ít nhất một cặp box có IoU < 0,40. |

Ngưỡng IoU giúp loại các cặp giao nhau ít. Ngưỡng diện tích hạn chế ca nhiễu từ vật thể nhỏ, còn tỷ lệ phần box nằm trong segment và độ lệch tâm giúp lọc các ca gộp hoặc lệch hộp trước khi xem ảnh. Chạy lại trên lô sạch `--no-faults` (seed 5, pool calib), validator trả về **0 lỗi luật và 0 ứng viên trên 50 ảnh**. Kết quả này chỉ phản ánh mức nhiễu quan sát được trên lô calib. [Ngưỡng trong code](../validator/cross_check.py)

Kết quả lưu từ `score_findings.py` trong `runs/r2902/report.md` ghi **F1 tổng ≈ 1,0, F1 lỗi luật ≈ 1,0 và F1 lỗi gán nhãn ≈ 1,0**. Đây là kết quả tự đo trên seed luyện tập, làm tròn đến một chữ số thập phân. Điểm chính thức do giảng viên chấm riêng. [Công cụ tự đo](../scripts/score_findings.py)

Nếu đưa mọi ứng viên vào `errors.json`, các tín hiệu nhầm như khác biệt tự nhiên giữa `cup` và `bowl` có thể thành false positive, làm giảm precision và F1. **Ví dụ giả định cho riêng lỗi gán nhãn.** Nếu sáu ca `confirmed` là toàn bộ lỗi thật, báo cả 24 ứng viên sẽ cho precision = 6/24 = 0,25, recall = 1 và F1 = 0,40. Phép tính minh họa phụ thuộc vào giả thiết đó.

Nhật ký hiện có verdict và ghi chú cho từng ứng viên. Các hàng chỉ có cột `image,type,verdict,note`, và ghi chú thiếu tên người trực tiếp xem theo yêu cầu của lab. Ví dụ, ghi chú ảnh `000000000872` mô tả vật thể quá nhỏ ở rìa ảnh, còn bbox của segment được báo chiếm khoảng 32,1% ảnh. Ca này cần người đã xem ảnh đối chiếu lại ghi chú. Báo cáo ghi nhận verdict theo nhật ký hiện có. [Ứng viên](r2902/candidates.json) · [Nhật ký review](r2902/review_log.csv) · [Quy tắc review](../RULES.md#dùng-ai)

## 3. Quyết định QC và lineage

V1 vượt ngưỡng Release nên nhóm ghi **HOLD** trong `runs/lineage.jsonl`. Mẫu số QC là số ảnh trong manifest v1. Tử số là số target lỗi khác nhau, trong đó `scene_leak` được tính một lần cho ảnh sai split. Bản lineage nộp kèm cũng ghi sự kiện release v2 với parent là v1. [Lineage](lineage.jsonl) · [Hướng dẫn QC](../GUIDE.md)

Truy vấn impact trả về `R-021: affected=True action=review_or_retrain`. Run này đã huấn luyện trên v1. Khi dữ liệu thay đổi, trọng số đã học vẫn phản ánh dữ liệu lúc train. Team AI cần đánh giá lại model của R-021 và retrain với lô đã xử lý nếu cần. [Truy vấn lineage](../scripts/lineage.py)

## 4. Bàn giao dataset v2

Release `lab250_9f8af853f974_v2` có parent `lab250_9f8af853f974`. README ghi **Release** cho gói detection v2 sau khi tách ảnh lỗi để gán lại. Quyết định QC của v1 vẫn là **HOLD**. [README bàn giao](r2902/handover/lab250_9f8af853f974_v2/README.txt)

| Hạng mục v2 | Kết quả kiểm tra |
| --- | --- |
| Dữ liệu bàn giao | 242 cặp ảnh và file nhãn YOLO, tổng 1.664 nhãn. Bảng `classes.txt` của lô có 80 lớp. |
| Rework | 8 ảnh lỗi Detection được tách khỏi v2 để gán lại rồi review, giao theo annotator và reviewer trong `jobs.csv`. |
| Manifest | SHA-256 khớp cho 484 file ảnh và nhãn. Mã `.sha256` của gói tái tạo cũng khớp. |
| Tổng hợp và truy vết | `label_summary.csv` khớp với số dòng nhãn theo lớp. `truyvet.csv` có một dòng trên mỗi ảnh, gồm scene, split, job, người gán, người kiểm và guideline. |

- **`wrong_hash`** — README ghi nhận người vận hành đã mở được ảnh `000000005001.jpg`. Kiểm tra lại ảnh trong v2 cũng mở được và SHA-256 tính từ file khớp với manifest mới. Ảnh được giữ trong lô.
- **`scene_leak`** — Toàn bộ `scene_226` về split `train` trong bảng truy vết v2. Cụ thể, `000000025228` chuyển từ `val` sang `train`.
- **`guideline_mismatch`** — Điền guideline theo job. Ảnh `000000011149` dùng `v1.3` theo job `J05`, trong khi metadata v1 ghi `v1.2`.
- **Lỗi chỉ thuộc Panoptic** — Giữ ảnh và nhãn Detection tương ứng trong v2. README liệt kê bốn ca để báo team Panoptic gồm `category_swap` (`000000007818`), `thing_overlap` (`000000014007`), `instance_merge` (`000000015440`) và `invalid_category_id` (`000000024243`).

[`rework_queue.csv`](r2902/handover/lab250_9f8af853f974_v2/rework_queue.csv) · [`manifest.csv`](r2902/handover/lab250_9f8af853f974_v2/manifest.csv) · [`label_summary.csv`](r2902/handover/lab250_9f8af853f974_v2/label_summary.csv) · [`truyvet.csv`](r2902/handover/lab250_9f8af853f974_v2/truyvet.csv) · [Mã gói `.sha256`](r2902/handover/lab250_9f8af853f974_v2.sha256)

Chạy lại `python scripts/check_handover.py --run runs/r2902` cho kết quả **17/17 PASS, 0 FAIL**. Bộ kiểm xác nhận các điều kiện bàn giao mà lab quy định. [Checker](../scripts/check_handover.py)

## 5. Hash và tính toàn vẹn dữ liệu

SHA-256 giúp phát hiện khi các byte của file hiện tại khác với bản đã ghi nhận. Manifest kiểm từng file ảnh và nhãn, còn mã `.sha256` kiểm gói bàn giao tái tạo. Chất lượng ngữ nghĩa của nhãn cần được kiểm bằng review. Bảo mật nội dung và quyền truy cập cần được kiểm theo quy trình của tổ chức.

## 6. Truy vết và bảo mật

Ticket trong `runs/r2902/delivery/incoming/ticket.md` nêu hai cảnh `scene_814` và `scene_952` có vấn đề với lớp `cup` (ID YOLO `41`). Theo changelog, guideline `v1.3` yêu cầu gán box cả khi `cup` bị che trên 50% hoặc bị cắt ở mép ảnh. Bản `v1.2` cho phép bỏ qua các trường hợp đó. Truy vết lọc các ảnh đã có ít nhất một box `cup` trong job dùng `v1.2` để xác định phạm vi kiểm lại. Phiên bản lấy từ `jobs.csv` vì metadata ảnh có thể ghi sai như ca `000000011149`. [Kết quả truy vết](r2902/trace.json)

| Mục | Kết quả |
| --- | --- |
| Tier A — trong hai scene được báo | 3 ảnh gồm `000000003661` (`scene_952`), `000000003845` và `000000003934` (`scene_814`). |
| Tier B — ngoài hai scene được báo | 4 ảnh gồm `000000002157` và `000000002431` (`scene_308`), `000000002592` và `000000002685` (`scene_376`). |
| Notify | `A02` (người gán) và `Q03` (người kiểm) của job `J02`, chứa cả 7 ảnh. |

Theo `security.md`, Nguyễn Thanh Quang đã mở ảnh `000000001000.jpg` và xác nhận có nhiều khuôn mặt nhìn rõ. Với tình huống guideline yêu cầu làm mờ, kết luận bảo mật là **HOLD**, dừng phát hành và báo người phụ trách dataset hoặc đầu mối bảo mật. Giữ nguyên ảnh gốc trong lúc chờ hướng xử lý được duyệt. Dữ liệu dự án chỉ được xử lý trong môi trường được cấp quyền. [Ghi nhận bảo mật](r2902/security.md)

Ảnh trên vẫn có trong manifest v2. README ghi kết luận Release cho gói detection theo QC, còn `security.md` ghi HOLD cho tình huống khuôn mặt. Hồ sơ hiện tại chưa ghi nhận việc xử lý ảnh hoặc phê duyệt phát hành cho tình huống đó. [Manifest v2](r2902/handover/lab250_9f8af853f974_v2/manifest.csv) · [README bàn giao](r2902/handover/lab250_9f8af853f974_v2/README.txt)

## 7. Hạn chế và bài học

- Cross-check dùng bbox của segment và trường `area` đã khai báo. Các dấu hiệu hình học có thể bị nhiễu khi các vật thể nằm sát nhau, bị che khuất hoặc khó phân biệt lớp. Xem ảnh giúp xác định lỗi thuộc nguồn nhãn nào và ghi lý do cho từng quyết định.
- Checker kiểm cấu trúc gói, đối chiếu dữ liệu và các trường bắt buộc trong hồ sơ review. Chất lượng nhãn thực tế vẫn phụ thuộc vào kiểm tra trực quan và cách áp dụng guideline.
- QC cho căn cứ ra quyết định, lineage chỉ ra run bị ảnh hưởng, SHA-256 giúp kiểm tính toàn vẹn file và hàng đợi rework giao lại đúng ca cho người phụ trách.
- Nhóm từng ghi nhận lỗi hiển thị tiếng Việt với `cp1252` trên Windows. Lần chạy lại dùng `PYTHONUTF8=1` thành công, phù hợp với hướng dẫn chạy UTF-8 trong lab. [Hướng dẫn chạy trên Windows](../GUIDE.md#cách-gõ-lệnh)
