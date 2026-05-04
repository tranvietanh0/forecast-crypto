## Phase 2: Ingestion + Offline Feature/Model Pipeline

### Mục tiêu
Xây đường ống dữ liệu và ML offline ưu tiên accuracy: ingest dữ liệu nhiều coin, dựng feature set ổn định, huấn luyện baseline model, và backtest có kiểm soát leakage.

### Phạm vi / Boundary sở hữu
- Data ingestion service
- Feature engineering pipeline
- Dataset versioning
- Model training, evaluation, registration
- Backtest offline đầu tiên

### Deliverables
- Ingestion jobs cho nhiều coin theo cùng schema.
- Data quality checks:
  - missing candles
  - duplicate events
  - out-of-order timestamps
  - provider drift
- Feature pipeline cho time-series/multi-coin:
  - returns, volatility, momentum, rolling stats
  - market regime proxies
  - cross-coin relative strength / correlation features nếu thực sự cần
- Dataset builder với point-in-time correctness.
- Baseline model strategy:
  - trend classification
  - target price regression
  - hoặc multi-head model nếu reuse feature set tốt hơn
- Model registry metadata:
  - model version
  - training window
  - feature schema version
  - metrics
- Offline backtest report theo rolling window.

### Validation
- Re-ingest cùng khoảng thời gian không tạo duplicate business records.
- Dataset build reproducible từ cùng raw inputs.
- Backtest chạy xong và xuất metrics theo coin/horizon.
- Manual leakage review: mọi feature timestamp đều <= forecast cutoff.

### Success Criteria
- Có forecast baseline cho toàn bộ coin khởi đầu và ít nhất 1-2 horizon.
- Metrics baseline rõ ràng để so sánh các iteration sau.
- Có khả năng replay/backfill khi provider lỗi hoặc thay đổi.
- Mô hình xuất đồng thời `trend`, `target_price`, `confidence` hoặc score tương đương.

### File Ownership
- `services/ingestion/**`
- `services/pipeline/**`
- `artifacts/metadata/**` hoặc registry metadata tương đương
- `tests/ingestion/**`, `tests/pipeline/**`

### Rollback Plan
- Disable model version mới và giữ model baseline trước đó.
- Rebuild dataset version cũ từ raw events vì raw layer là append-only.

### Risk Assessment
| Risk | Likelihood (1-5) | Impact (1-5) | Score | Mitigation |
|------|-----------------|--------------|-------|------------|
| Data quality thấp phá accuracy | 4 | 5 | 20 | Thiết lập quality gates bắt buộc trước train; alert khi gap/duplicate vượt ngưỡng |
| Lookahead bias trong feature engineering | 3 | 5 | 15 | Point-in-time dataset builder, code review cutoff timestamps, rolling-window backtest |
| Multi-coin feature set trở nên quá nặng | 3 | 4 | 12 | Bắt đầu với feature template dùng chung; chỉ thêm cross-coin features nếu metrics chứng minh lợi ích |
| Training pipeline khó tái lập | 3 | 4 | 12 | Version hóa data slice, feature schema, random seed, model config |

### Timeline
| Phase | Effort | Notes |
|-------|--------|-------|
| Ingestion baseline + data quality | M (~3 ngày) | Phụ thuộc Phase 1 schema |
| Feature engineering + dataset builder | M (~3 ngày) | Critical path accuracy |
| Baseline training + backtest | M (~3 ngày) | Cần metrics đủ tin cậy |
| Total | L (~1 tuần) | Blocker chính cho inference thật |
