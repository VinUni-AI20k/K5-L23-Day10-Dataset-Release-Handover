## Mô tả thay đổi
- Issue liên quan: Closes #

## Thư mục đã sửa (đúng phạm vi phân công)
- [ ] `validator/` / `tests/validator/`
- [ ] `qc/crosscheck/` / `tests/crosscheck/`
- [ ] `qc/review/`
- [ ] `release/` / `handover/`
- [ ] `trace/`
- [ ] `security/` / `reporting/`

## Bằng chứng kiểm thử
- Lệnh đã chạy:
```bash
python -m unittest discover -s tests
```
- Kết quả thực tế:

## Checklist tuân thủ `RULES.md`
- [ ] Không sửa `scripts/` của giảng viên
- [ ] Không đọc `_private/` hoặc `data_source/` trong `validator/`
- [ ] Không commit `runs/`, `data_source/`, `*.zip`, hoặc thông tin nhạy cảm
- [ ] Commit mang đúng tên và email cá nhân
