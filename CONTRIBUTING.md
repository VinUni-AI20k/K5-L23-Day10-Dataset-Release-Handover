# Contributing Guide — Day 10 Team

## 1. Branch & Pull Request Workflow

- **Repo làm việc & nộp bài:** Chỉ push và mở Pull Request trên **repo chính thức của nhóm** (`origin`: `https://github.com/phamphunguyenhung/K5-L23-DAY10-sIx4Nhd0cTh4n-Release`), **tuyệt đối không** push vào link cũ (`hungpixi/K5-L23-Day10-Dataset-Release-Handover`) hoặc mở PR lên repo gốc `VinUni-AI20k` (`upstream`).
- Nhánh chính của fork: `main` (và nhánh tích hợp `team/day10-integration`).
- Mỗi thành viên tạo nhánh riêng theo mẫu:
  - `feat/<github-username>-p1-validator`
  - `feat/<github-username>-p2-crosscheck`
  - `feat/<github-username>-p2-review`
  - `feat/<github-username>-p3-p4-handover`
  - `feat/<github-username>-p5-trace`
  - `feat/<github-username>-p6-security`
- Mở Pull Request nhắm vào `main` (hoặc `team/day10-integration`) **trên repo `phamphunguyenhung/K5-L23-DAY10-sIx4Nhd0cTh4n-Release`** và gắn link Issue (`Closes #<issue_number>`).

## 2. Commit Rules (Rubric Compliance)

- Mỗi thành viên bắt buộc có **ít nhất 2 commit có nội dung thực chất**, sử dụng đúng `git config user.name` và `git config user.email` của cá nhân.
- **Cấm** tạo commit dưới danh tính người khác hoặc fake commit hộ.
- Không commit các file bị cấm trong `.gitignore` (`data_source/`, `runs/`, `_private/`, `*.zip`, `.env`).

## 3. Coding & QC Standards

- `validator/` chỉ dùng **Python Standard Library** (+ `scripts/pngutil.py`), tuyệt đối không dùng mạng, không đọc `_private/` hay `data_source/`.
- Không chỉnh sửa `scripts/` của giảng viên.
- Mọi thay đổi code phải đi kèm test trong `tests/validator/` hoặc `tests/crosscheck/` và pass CI workflow.
