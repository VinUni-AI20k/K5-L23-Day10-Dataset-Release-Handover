# P2 — Detection ↔ Panoptic Cross-check

- **Owner:** Đỗ Anh Hoàng (`2A202604061` · `@AnhHoangDepTrai`)
- **Mục tiêu:** Giảm false positive trên lô sạch, tinh chỉnh ngưỡng ghép box ↔ mask (`IoU`, diện tích tối thiểu, `class_swap` vs `missing_box` vs `missing_mask`) để hàng đợi `candidates.json` đủ nhỏ cho người xem ảnh duyệt hết.
- **Test:** `python -m unittest discover -s tests/crosscheck`
