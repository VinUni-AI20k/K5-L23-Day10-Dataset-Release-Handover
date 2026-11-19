# P3 — Release Gate (Ngưỡng 2%) & Lineage

- **Owner:** Nguyễn Xuân Việt (`2A202604045` · `@ngxuanviet`)
- **Mục tiêu:** Áp dụng ngưỡng 2% ảnh lỗi trên lô v1, ghi quyết định `HOLD` cho v1 vào `runs/lineage.jsonl`, chạy `impact` để xác định `R-021: affected=True`, và ghi nhận `RELEASE` cho v2 kèm `parent`.
- **Công cụ chính thức:** `scripts/lineage.py` (không sửa script gốc).
