# Quy chuẩn Đóng gói Lô Bàn giao v2 & Kiểm định Chất lượng (H1–H15)

**Người phụ trách:** Phan Lê Hoàng Phúc (`phuchoangpath` / TV4)  
**Tài liệu tham chiếu:** `RULES.md`, `CHECKPOINTS.md`, `scripts/check_handover.py`

---

## 1. Mục tiêu và Nguyên tắc Bàn giao v2
- Lô v2 (`<release_id>_v2`) là sản phẩm đóng gói bàn giao nhãn phát hiện vật thể (Object Detection: hình ảnh + nhãn YOLO `.txt`) chuyển giao cho Đội ngũ Kỹ sư Huấn luyện Mô hình AI.
- **Nguyên tắc bất biến:**
  1. *Tuyệt đối không sửa đè lên v1:* Thư mục bàn giao v1 (`delivery/`) phải được bảo toàn nguyên vẹn mã băm và cấu trúc để phục vụ đối soát và kiểm toán (H1).
  2. *Không sửa tay file nhãn:* Không tự ý sửa tọa độ, thêm/bớt dòng trong các file `.txt` của v2 để tránh sai lệch phân phối gán nhãn gốc (H7).
  3. *Tách biệt xử lý lỗi:*
     - Lỗi thuộc về nhãn Detection hoặc thiếu file (`missing_image`, `invalid_class`, `bbox_out_of_bounds`, `duplicate_box`, `class_swap`, `bbox_drift`, `missing_box`): Bắt buộc chuyển sang `rework_queue.csv` và **loại hoàn toàn khỏi v2** (H5).
     - Lỗi thuộc về Panoptic (`invalid_category_id`, `thing_overlap`, `category_swap`, `instance_merge`): Nhãn Detection vẫn hợp lệ nên **ảnh ở lại v2**, ghi chú bàn giao cho team Panoptic trong `README.txt`.

---

## 2. Cấu trúc 7 Thành phần Bắt buộc của Lô v2 (H4)

```text
handover/<release_id>_v2/
├── images/             # Tập hợp ảnh hợp lệ copy nguyên vẹn từ v1
├── labels/             # Tập hợp file nhãn tương ứng (1 ảnh = 1 file .txt)
├── manifest.csv        # Danh mục file (file, sha256) với đường dẫn dạng POSIX
├── label_summary.csv   # Thống kê số lượng theo từng lớp và dòng TOTAL
├── truyvet.csv         # Bảng thông tin nguồn gốc (job_id, split, scene_id, annotator, reviewer, guideline)
├── rework_queue.csv    # Danh sách ảnh lỗi kèm thông tin người gán/duyệt để gán lại
└── README.txt          # Báo cáo tổng hợp số lượng, tỷ lệ QC v1, quyết định phát hành và ghi chú
```

---

## 3. Quy trình Tự động hóa qua `tools/build_v2.py`
Script [tools/build_v2.py](file:///d:/VinUni/K5-L23A-Day10-LaThaiHoa-2A202603069-Dataset-Release-Handover/tools/build_v2.py) được TV4 phát triển nhằm tự động hóa 100% các tiêu chí:
1. **Xử lý `scene_leak` (H11):** Thuật toán tìm split chiếm đa số (`majority_split`) cho mỗi `scene_id` và chuẩn hóa toàn bộ các ảnh cùng cảnh về duy nhất một split (train hoặc val), giải quyết triệt để rò rỉ dữ liệu giữa tập học và tập kiểm thử.
2. **Khắc phục `guideline_mismatch`:** Tự động đồng bộ hóa phiên bản hướng dẫn trong `truyvet.csv` theo phiên bản ghi nhận tại `jobs.csv` của dự án.
3. **Cập nhật mã băm thật (H8):** Tính toán lại mã SHA-256 từ luồng nhị phân thật của từng file trong `images/` và `labels/`, khắc phục các lỗi `wrong_hash` của v1.
4. **Phân phối danh sách Rework (H6):** Trích xuất đúng `annotator` và `reviewer` từ `jobs.csv` tương ứng với từng ảnh lỗi để chuyển giao trách nhiệm gán lại chính xác.

---

## 4. Kết quả Kiểm định Bàn giao Thực tế
Chạy kiểm định qua lệnh `python scripts/check_handover.py --run runs/r3007`:
- **H4 (Đủ 7 phần):** PASS
- **H5 (Ảnh lỗi ra khỏi v2):** PASS (241 ảnh giữ lại, 9 ảnh chuyển rework)
- **H6 (Đúng annotator/reviewer):** PASS
- **H7 (Nhãn không bị sửa tay):** PASS
- **H8 (Manifest sha256 chuẩn):** PASS (482 file)
- **H9 (Label summary khớp):** PASS (1,647 nhãn)
- **H10 (Truy vết đúng job/guideline):** PASS
- **H11 (Không còn scene leak):** PASS
- **H12, H13 (README và QC rate):** PASS
- **H15 (Mã đóng gói zip tái lập):** PASS
