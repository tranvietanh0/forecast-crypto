## Phase 3: Inference + Forecast Storage / Serving API

### Mục tiêu
Biến mô hình offline thành forecast chạy theo lịch với output ổn định cho product surfaces: lưu forecast snapshots, phục vụ API đọc nhất quán cho dashboard và Telegram.

### Phạm vi / Boundary sở hữu
- Inference service
- Forecast persistence
- Read API / serving layer
- Batch orchestration và snapshot semantics

### Deliverables
- Scheduled inference job theo horizon/cadence.
- Forecast batch lifecycle:
  - batch start
  - prediction generation
  - batch commit
  - publish ready state
- Forecast schema gồm:
  - coin
  - horizon
  - predicted trend
  - target price
  - confidence score
  - model version
  - generated_at
  - valid_until
- Serving API endpoints:
  - latest forecasts by watchlist
  - forecast history by coin/horizon
  - forecast batch detail
- Optional lightweight explanation fields: top features/notes nếu model hỗ trợ.
- Idempotent inference rerun theo batch key.

### Validation
- Chạy 1 batch multi-coin tạo đủ forecast records không trùng.
- API trả cùng snapshot cho dashboard và Telegram khi cùng `forecast_batch_id`.
- Retry inference không làm double-write business output.

### Success Criteria
- Có 1 nguồn forecast chính thức duy nhất để mọi consumer đọc.
- Latency batch phù hợp cadence gửi Telegram và refresh dashboard.
- Có thể truy vết từ forecast record về dataset/model version đã dùng.

### File Ownership
- `services/inference/**`
- `services/api/**`
- `tests/inference/**`, `tests/api/**`
- `contracts/**` nếu cần additive response fields có versioning

### Rollback Plan
- Switch active serving batch về batch trước.
- Tắt scheduler inference hoặc rollback sang model version cũ.

### Risk Assessment
| Risk | Likelihood (1-5) | Impact (1-5) | Score | Mitigation |
|------|-----------------|--------------|-------|------------|
| Double-run scheduler tạo dữ liệu mâu thuẫn | 3 | 5 | 15 | Dùng batch key duy nhất + transaction commit + idempotency guard |
| API và Telegram đọc snapshot khác nhau | 3 | 5 | 15 | Tất cả consumer phải đọc theo `forecast_batch_id` đã publish-ready |
| Forecast payload thiếu traceability | 2 | 4 | 8 | Bắt buộc lưu model_version, dataset_version, generated_at trong forecast record |

### Timeline
| Phase | Effort | Notes |
|-------|--------|-------|
| Inference batch runner | S (~1 ngày) | Phụ thuộc model artifact |
| Forecast persistence + snapshot state | S (~1 ngày) | Phụ thuộc storage schema |
| Serving API + tests | S (~1 ngày) | Consumer contract blocker |
| Total | M (~3 ngày) | Mở đường cho dashboard và Telegram |
