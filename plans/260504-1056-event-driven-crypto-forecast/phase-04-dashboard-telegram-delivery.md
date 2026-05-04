## Phase 4: Dashboard + Telegram Delivery

### Mục tiêu
Đưa forecast ra sản phẩm với hai kênh tiêu thụ chính nhưng vẫn dùng chung snapshot dữ liệu: dashboard đa coin và Telegram notification theo lịch.

### Phạm vi / Boundary sở hữu
- Dashboard frontend
- Telegram notification service
- Shared presentation contract từ serving API

### Deliverables
- Dashboard watchlist nhiều coin:
  - trend dự báo
  - target price
  - horizon
  - thời gian sinh forecast
  - confidence / status
  - history cơ bản theo coin
- Telegram scheduler:
  - lịch gửi cấu hình được
  - format message nhiều coin
  - snapshot consistency theo batch
- Notification audit log:
  - gửi thành công/thất bại
  - batch ID đã dùng
  - retry count
- UX rule thống nhất cho trend labels và target price formatting giữa dashboard/Telegram.

### Validation
- Dashboard smoke test: tải danh sách coin và render đúng các field bắt buộc.
- Telegram dry-run: render preview message từ cùng forecast batch với dashboard.
- Notification scheduler chạy đúng cadence cấu hình.

### Success Criteria
- Người dùng xem cùng forecast snapshot trên dashboard và Telegram.
- Telegram message đủ ngắn gọn nhưng vẫn chứa trend + target price cho nhiều coin.
- Lỗi gửi Telegram không làm mất forecast; có thể retry từ snapshot cũ.

### File Ownership
- `apps/dashboard/**`
- `services/telegram/**`
- `tests/dashboard/**`, `tests/telegram/**`

### Rollback Plan
- Disable Telegram schedule bằng config.
- Hide widget mới trên dashboard mà không đụng dữ liệu nền.

### Risk Assessment
| Risk | Likelihood (1-5) | Impact (1-5) | Score | Mitigation |
|------|-----------------|--------------|-------|------------|
| Message Telegram quá dài khi theo dõi nhiều coin | 4 | 3 | 12 | Giới hạn coin watchlist mặc định, nhóm theo priority, format compact |
| Dashboard và Telegram dùng logic format khác nhau | 3 | 4 | 12 | Tạo shared presentation mapping hoặc contract tests trên API payload |
| Notification chạy trước khi batch forecast hoàn tất | 3 | 5 | 15 | Scheduler chỉ đọc batch ở trạng thái publish-ready |

### Timeline
| Phase | Effort | Notes |
|-------|--------|-------|
| Dashboard watchlist baseline | S (~1 ngày) | Phụ thuộc API ổn định |
| Telegram scheduler + formatter | S (~1 ngày) | Phụ thuộc snapshot semantics |
| Audit log + integration tests | S (~1 ngày) | Đảm bảo retry an toàn |
| Total | M (~3 ngày) | Sau Phase 3 |
