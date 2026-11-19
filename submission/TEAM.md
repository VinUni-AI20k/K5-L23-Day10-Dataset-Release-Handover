# Nhóm — chờ bổ sung số nhóm

- Seed luyện tập: **24007**.
- Repo: https://github.com/Hieudevnekkk/K5-L23-Day10-NguyenMinhHieu-2A202603091-Dataset-Release-Handover
- Phân công theo ảnh người dùng cung cấp; người dùng phụ trách **B**.
- Họ tên, MSHV và tài khoản GitHub từng người chưa được cung cấp.

| Người | Họ và tên | MSHV | Tài khoản GitHub | Phần chính | Sản phẩm |
|---|---|---|---|---|---|
| A | Chưa cung cấp | Chưa cung cấp | Chưa cung cấp | Pha 1: missing_image, wrong_hash, invalid_class, bbox_out_of_bounds, duplicate_box; khung validator và giao diện dòng lệnh. | Phần đầu validator/validate.py |
| B (người dùng) | Chưa cung cấp | Chưa cung cấp | Chưa cung cấp | Pha 1: scene_leak, guideline_mismatch, invalid_category_id, thing_overlap (đếm pixel mask bằng scripts/pngutil.py); ghép với A; kiểm thử phần luật trên ít nhất 2 seed và lô sạch. | Phần sau validator/validate.py; rules.json trong thư mục run |
| C | Chưa cung cấp | Chưa cung cấp | Chưa cung cấp | Pha 2: đối chiếu detection và panoptic bằng pixel mask; sinh ứng viên; đo ứng viên trên lô sạch và chọn ngưỡng; gửi số liệu, lý do cho E. | candidates.json; số liệu và ngưỡng cho REPORT.md |
| D | Chưa cung cấp | Chưa cung cấp | Chưa cung cấp | Công cụ xem ảnh vẽ box và viền segment; chia hàng đợi review; gộp lỗi luật với kết quả review bằng merge_review.py; hoàn thiện công cụ trước đề ẩn. | Công cụ xem ảnh; review_log.csv; errors.json |
| E | Chưa cung cấp | Chưa cung cấp | Chưa cung cấp | Pha 3–6: lineage, HOLD v1, release v2 có parent; bàn giao v2, đóng gói và kiểm tra; truy vết, bảo mật; tổng hợp TEAM.md, REPORT.md, prompts.md và export bài nộp. | handover/; trace.json; security.md; các file submission/ |

## Phối hợp

- Cả nhóm tham gia xem ảnh ở Pha 2; mỗi người giải thích được phần mình làm.
- Sau Pha 1, A hỗ trợ trace.json (Pha 5) và prompts.md theo phần phân công nhìn thấy trong ảnh. Phần hỗ trợ thêm của B chưa có thông tin đầy đủ trong ảnh.
- Mỗi thành viên có ít nhất 2 commit có nội dung bằng tên và email của mình.
- Validator chỉ đọc delivery được truyền vào, dùng thư viện chuẩn; được import scripts/pngutil.py. Không sửa delivery v1 hoặc scripts của đề.
- Không commit data_source/, runs/ hoặc file .zip; xuất bài làm sang submission/ ở bước nộp.

## Lệnh chuẩn bị

Chạy từ thư mục gốc repo (PowerShell, Python 3.10+):

```powershell
py -X utf8 scripts/download_public.py
py -X utf8 scripts/run_lab.py --seeds 24007
```

Seed phụ để thử validator dùng inject_release.py, không chạy lại run_lab.py để thêm seed.

## Trạng thái Pha 0 (19/11/2026)

- Đã kiểm tra Python: 3.13.9, đáp ứng yêu cầu 3.10+.
- Đã xác nhận repo Git, ghi seed 24007 và phân công A–E; danh tính thành viên và số nhóm để nhóm bổ sung.
- Chưa hoàn tất tải dữ liệu: máy chủ COCO trả dữ liệu chậm và nhiều lượt kết nối bị timeout. Đã thử tải lại và truy cập S3, chưa có đủ archive để chạy bước tạo lô.
- Chưa chạy run_lab.py; chưa có runs/r24007/delivery hoặc lineage cho seed này; chưa thể đánh dấu CP0 hoàn tất.
- Khi kết nối tải ổn định: chạy lại lệnh download ở trên, sau khi thành công mới chạy run_lab.py --seeds 24007 và kiểm tra delivery cùng sự kiện train R-021 trong runs/lineage.jsonl.
- data_source/ và runs/ được .gitignore loại khỏi Git; không sửa script của đề.
