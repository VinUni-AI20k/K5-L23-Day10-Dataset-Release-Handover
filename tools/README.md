# Công cụ xem ảnh review (`tools/review_viewer.py`)

Công cụ riêng hỗ trợ **Phần 2 (`REV-07`, `REV-08`)** cho cả 4 thành viên xem ảnh ứng viên bằng mắt nhanh và chính xác (cả ở seed luyện tập và đề ẩn 40 phút).

- Nằm **ngoài** thư mục `validator/` nên được phép dùng **Pillow** (theo [RULES.md](../RULES.md)).
- **Không tự điền verdict hay ghi chú thay con người** — mọi dòng `confirmed`/`rejected` do thành viên tự nhìn ảnh quyết định.
- Luôn xuất thư mục ảnh trực quan vào `runs/` (đã nằm trong `.gitignore`) để không commit ảnh tạm lên repo.

## 1. Tạo giao diện xem ảnh & chia đều cho 4 người (`build`)

```powershell
py tools/review_viewer.py build --delivery runs/r<seed>/delivery --candidates runs/r<seed>/candidates.json --out runs/r<seed>/review_viz --members 4
```

Mở file `runs/r<seed>/review_viz/index.html` bằng trình duyệt:
- Mỗi ứng viên hiển thị **3 góc nhìn**: (1) ảnh gốc crop quanh vật, (2) ảnh crop overlay box Detection (đỏ/vàng) vs mask + viền Panoptic (xanh ngọc), (3) toàn ảnh overlay. Bấm vào ảnh để phóng to.
- Dùng tab **Thành viên 1..4** để mỗi người xem đúng phần của mình (các ứng viên cùng 1 ảnh luôn gom về cùng 1 người).
- Khi gặp cặp khác lớp (`class_swap` / `category_swap`): nhìn ảnh gốc để tự chọn đúng bên sai (**Detection sai → `class_swap`**, **Panoptic sai → `category_swap`**).
- Bộ đếm ký tự tự báo khi ghi chú chưa đủ **20 ký tự** (yêu cầu H3). Tiến độ tự lưu trên trình duyệt (`localStorage`).
- Xong phần mình, bấm **Tải review_log.csv** để xuất file CSV từng thành viên.

## 2. Gộp CSV 4 thành viên & kiểm tra chuẩn H3 (`merge`)

```powershell
py tools/review_viewer.py merge runs/r<seed>/review_log_member1.csv runs/r<seed>/review_log_member2.csv runs/r<seed>/review_log_member3.csv runs/r<seed>/review_log_member4.csv --out runs/r<seed>/review_log.csv
```

Lệnh kiểm tra tự động trước khi bàn giao:
- Đúng 4 cột `image,type,verdict,note`, đúng 5 loại lỗi gán nhãn và `confirmed`/`rejected`.
- Mọi dòng có ghi chú ≥ 20 ký tự và ≥ 70% ghi chú khác nhau (đúng chuẩn H3 của `scripts/check_handover.py`).
- Cảnh báo nếu trùng dòng hoặc một ảnh có nhiều hơn 1 lỗi `confirmed`.

## 3. Gộp `errors.json` sau khi nhận `rules.json` từ Người 1

```powershell
py scripts/merge_review.py --rules runs/r<seed>/rules.json --review runs/r<seed>/review_log.csv --out runs/r<seed>/errors.json
```

## 4. Quy trình nhanh cho Đề ẩn 40 phút (CP6b)

```powershell
py validator/validate.py delivery --out runs/de_an/rules.json --candidates submission/de_an/candidates.json
py tools/review_viewer.py build --delivery delivery --candidates submission/de_an/candidates.json --out runs/de_an/review_viz --members 4
# 4 thành viên xem ảnh, xuất 4 file CSV -> gộp bằng merge:
py tools/review_viewer.py merge runs/de_an/m1.csv runs/de_an/m2.csv runs/de_an/m3.csv runs/de_an/m4.csv --out submission/de_an/review_log.csv
py scripts/merge_review.py --rules runs/de_an/rules.json --review submission/de_an/review_log.csv --out submission/de_an/errors.json
```
