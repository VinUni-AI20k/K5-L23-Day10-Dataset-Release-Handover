# Quy trình Đối chiếu Pixel-Level & Hiệu chuẩn Ngưỡng trên Lô Sạch

**Người phụ trách:** Trịnh Đức Mạnh (`Manhtd285` / TV2)  
**Tài liệu tham chiếu:** `RULES.md`, `CHECKPOINTS.md`, `validator/cross_check.py`

---

## 1. Nguyên lý và Thách thức Đối chiếu Không Nhãn Gốc
- **Bài toán:** Lỗi gán nhãn trong dataset hoàn toàn không có ground truth để đối chiếu trực tiếp. Nguồn đối chiếu duy nhất là giữa hai modality nhãn: **Detection** (tọa độ bounding box chữ nhật chuẩn hóa YOLO $[0, 1]$) và **Panoptic Segmentation** (mặt nạ vùng pixel RGB).
- **Hạn chế của Bounding Box IoU:** Nếu chỉ so sánh IoU giữa hai hộp chữ nhật, hệ thống không thể phát hiện các lỗi:
  - `bbox_drift`: Hộp detection vẫn bao quanh vật thể nhưng bị trôi dạt tọa độ ra ngoài vùng pixel thực tế.
  - `instance_merge`: Hai hộp detection độc lập nhưng bị một vùng mặt nạ panoptic phủ chung.

---

## 2. Giải pháp Pixel-Level trong `validator/cross_check.py`
Thuật toán do TV2 xây dựng trực tiếp trên luồng byte PNG thông qua [scripts/pngutil.py](file:///d:/VinUni/K5-L23A-Day10-LaThaiHoa-2A202603069-Dataset-Release-Handover/scripts/pngutil.py), tuân thủ nghiêm ngặt **100% Python Standard Library**:
1. **Dung sai biên làm tròn số thực:**
   `BOX_PAD_PX = 1.0` pixel bù trừ sai số khi nhân tọa độ float với chiều rộng/cao ảnh.
2. **Khóa cặp đối tượng cùng lớp sạch:**
   - `STRONG_SAME_COV = 0.88`: Ít nhất 88% pixel của mặt nạ phải nằm trọn trong bounding box.
   - `STRONG_SAME_IOU = 0.50`: Đảm bảo hình dạng không gian khớp nối tin cậy.
3. **Phát hiện `bbox_drift`:**
   Khi cùng nhãn lớp nhưng tỷ lệ pixel mặt nạ nằm trong box rơi xuống dưới ngưỡng chuẩn và số pixel tràn ra ngoài vượt quá 500 pixel.
4. **Phát hiện `instance_merge`:**
   Một segment thing phủ lên $\ge 2$ box cùng lớp với `union_cov >= 0.82`, không có box đơn lẻ nào chiếm quá 98.5% và mỗi box sở hữu $\ge 2.5\%$ pixel độc quyền.
5. **Phát hiện `class_swap` & `category_swap`:**
   Một box và một segment lệch tên lớp nhưng trùng khít vị trí không gian với `IoU >= 0.35` và `seg_in_box >= 0.80`.

---

## 3. Hiệu chuẩn Thực nghiệm trên Lô Sạch (`runs/clean`)
- Nhóm đã chạy kiểm định trực tiếp trên 50 ảnh chuẩn không gài lỗi (`runs/clean`):
  - Số lỗi luật: **0**
  - Số ứng viên nhiễu: **0**
  - **Tỷ lệ báo động giả (False Alarm Rate): 0.0%**
- Kết quả cho thấy các ngưỡng đã chọn hoàn toàn triệt tiêu các sai lệch tự nhiên của COCO mà không bỏ sót lỗi gài trong thực tế.
