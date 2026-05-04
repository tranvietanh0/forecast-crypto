## Phase 1: Foundation Contracts & Storage

### Mục tiêu
Tạo nền tảng SSOT cho toàn hệ thống: repo skeleton, shared contracts, migration/storage schema, config, và event semantics đủ để mọi phase sau cùng bám vào một định nghĩa dữ liệu thống nhất.

### Phạm vi / Boundary sở hữu
- Shared domain contracts
- Storage schema cho raw market events, feature sets metadata, model registry metadata, forecasts, notification snapshots, evaluation metrics
- Config + environment strategy
- Repo structure và local dev bootstrap

### Deliverables
- Repo skeleton theo module boundary:
  - `contracts/`
  - `services/ingestion/`
  - `services/pipeline/`
  - `services/inference/`
  - `services/api/`
  - `apps/dashboard/`
  - `services/telegram/`
  - `services/monitoring/`
- Shared contract definitions:
  - `MarketEvent`
  - `FeatureSetBuilt`
  - `ModelRegistered`
  - `ForecastGenerated`
  - `NotificationSnapshot`
- DB schema/migrations:
  - `raw_market_events`
  - `forecast_batches`
  - `forecasts`
  - `model_versions`
  - `dataset_versions`
  - `notification_runs`
  - `realized_outcomes`
- Append-only event log hoặc outbox table cho evolution sang event bus.
- Config contract:
  - coin universe
  - forecast horizons
  - provider endpoints
  - scheduler cadences
  - retention windows
- Architecture note mô tả rõ boundary giữa service và ownership dữ liệu.

### Validation
- Contract tests parse/serialize cho toàn bộ shared events.
- Migration up/down chạy sạch trên local DB.
- Seed dữ liệu tối thiểu tạo được một forecast batch giả lập end-to-end ở mức schema.
- Config validation fail-fast khi thiếu env bắt buộc.

### Success Criteria
- Có thể tạo và đọc một `ForecastGenerated` record bằng schema chính thức.
- Dashboard/API/Telegram tương lai có thể dùng chung 1 payload contract cho `trend` + `target_price`.
- Không có trường dữ liệu dẫn xuất lưu dư thừa nếu có thể tính từ nguồn.
- Mọi module đều import contract từ 1 nơi duy nhất.

### File Ownership
- `contracts/**`
- `infra/migrations/**` hoặc tương đương
- `config/**`
- `plans/docs kiến trúc liên quan`

### Rollback Plan
- Revert migrations của phase này.
- Gỡ skeleton modules nếu cần mà không ảnh hưởng dữ liệu thật vì chưa có production traffic.

### Risk Assessment
| Risk | Likelihood (1-5) | Impact (1-5) | Score | Mitigation |
|------|-----------------|--------------|-------|------------|
| Schema thiết kế quá rộng từ đầu | 4 | 3 | 12 | Chỉ thêm field phục vụ use case 1-2 horizon, nhiều coin, dashboard + Telegram |
| Contract đổi sớm làm lan sửa nhiều nơi | 3 | 4 | 12 | Dùng version field ngay từ đầu, review contract trước khi code phase sau |
| Chọn storage schema không hỗ trợ backtest tốt | 3 | 5 | 15 | Thiết kế append-only raw events + timestamp chuẩn UTC + partition strategy từ đầu |

### Timeline
| Phase | Effort | Notes |
|-------|--------|-------|
| Schema & contracts | S (~1 ngày) | Nền tảng SSOT |
| Migrations & config bootstrap | S (~1 ngày) | Phụ thuộc stack đã chốt |
| Architecture note & validation harness | S (~1 ngày) | Chốt boundary trước khi build logic |
| Total | M (~3 ngày) | Blocker cho toàn bộ phase sau |
