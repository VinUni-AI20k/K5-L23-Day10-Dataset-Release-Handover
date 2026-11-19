# P3 — Release Gate (Ngưỡng 2%) & Lineage

- **Phụ trách chính:** Đỗ Anh Hoàng (`2A202604061` · GitHub: `@AnhHoangDepTrai`)
- **Phạm vi module:** `release/gate.py`, `release/__init__.py`, `tests/test_release_gate.py`
- **Mục tiêu kỹ thuật:**
  1. Đọc và phân tích số liệu lỗi từ `errors.json` đối chiếu với tổng số mẫu ảnh trong `manifest.json`.
  2. Áp dụng quy tắc ngưỡng 2.0% (Day 7) để ra quyết định khách quan (`HOLD` nếu tỉ lệ lỗi > 2%, `RELEASE` nếu đạt chuẩn).
  3. Ghi sự kiện quyết định vào nhật ký bất biến `runs/lineage.jsonl`.
  4. Phân tích vùng ảnh hưởng (blast radius / lineage impact) tới các training run kế thừa dữ liệu (cụ thể `R-021`).

## 1. Cách vận hành CLI

```bash
python release/gate.py --run runs/r9007
```

Lệnh sẽ:
- Tính tỉ lệ ảnh lỗi trên v1.
- Ghi nhận `{"event": "decision", "release_id": "lab250_79c4d088f4c4", "decision": "HOLD", ...}` vào `runs/lineage.jsonl`.
- Truy vấn impact trên `R-021`, trả về:
  `R-021: affected=True action=review_or_retrain`.

## 2. Ý nghĩa kỹ thuật & Lineage Governance
- **Ngưỡng 2% theo số ảnh (không tính theo tổng số lỗi):** Một ảnh có thể có nhiều lỗi phát sinh cùng lúc, nhưng tỉ lệ ảnh hỏng là chỉ số đại diện thực sự cho độ sạch của dữ liệu huấn luyện.
- **Tại sao đổi dataset không tự sửa model đã train?** Trọng số mạng nơ-ron được cập nhật cố định từ dữ liệu lô cũ. Khi dataset v1 bị phát hiện có lỗi và đặt ở trạng thái `HOLD`, model `R-021` đã hấp thu nhiễu và bias sai lệch, do đó bắt buộc phải `review_or_retrain`.
