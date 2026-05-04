## Phase 5: Monitoring + Backtest + Event Bus Evolution

### Mục tiêu
Củng cố vận hành và chỉ khi cần mới tiến hóa sang event bus thực thụ: theo dõi freshness/quality, automation backtest, drift detection, và tách service/queue có kiểm soát.

### Phạm vi / Boundary sở hữu
- Monitoring service
- Backtest automation / evaluation service
- Queue/event bus introduction plan
- Consumer idempotency / replay strategy

### Deliverables
- Monitoring dashboards/alerts cho:
  - ingestion freshness
  - missing data rate
  - forecast generation success rate
  - Telegram delivery success rate
  - realized vs predicted error by coin/horizon
- Scheduled backtest / rolling re-evaluation.
- Drift checks:
  - feature distribution drift
  - prediction distribution drift
  - forecast error degradation
- Event bus evolution path:
  - từ DB outbox/event log
  - sang queue/broker thật nếu cần
- Consumer contracts và idempotency strategy cho các event:
  - `MarketEventIngested`
  - `ForecastBatchReady`
  - `NotificationRequested`

### Validation
- Simulate data gap và xác nhận alert kích hoạt.
- Replay 1 batch event từ outbox mà không tạo business duplicate.
- Backtest automation cập nhật metrics định kỳ và lưu lịch sử so sánh.

### Success Criteria
- Có thể phát hiện sớm degradation trước khi người dùng phàn nàn.
- Queue/service chỉ được tách sau khi có metric chứng minh cần thiết.
- Có playbook rõ ràng cho replay, retry, reforecast, và incident response.

### File Ownership
- `services/monitoring/**`
- `services/pipeline/backtest/**` hoặc tương đương
- `infra/queue/**` nếu đến ngưỡng tách queue
- `docs/operations/**` nếu được yêu cầu cập nhật docs dự án

### Rollback Plan
- Nếu queue gây instability, quay lại path DB-polling/outbox cũ.
- Drift alerts có thể downgrade thành dashboard-only nếu nhiễu cao.

### Risk Assessment
| Risk | Likelihood (1-5) | Impact (1-5) | Score | Mitigation |
|------|-----------------|--------------|-------|------------|
| Tách queue quá sớm làm tăng burden vận hành | 4 | 4 | 16 | Chỉ tách khi có số liệu về throughput, deploy cadence hoặc fault isolation cần thiết |
| Alert noise gây mù cảnh báo | 3 | 4 | 12 | Bắt đầu bằng ít signal quan trọng, hiệu chỉnh threshold theo lịch sử |
| Replay event tạo duplicate side effects | 3 | 5 | 15 | Idempotency keys cho notification/inference, append-only audit log |
| Monitoring không bao phủ chất lượng model | 2 | 5 | 10 | Bắt buộc theo dõi cả freshness lẫn forecast error / drift |

### Timeline
| Phase | Effort | Notes |
|-------|--------|-------|
| Monitoring baseline + alerts | M (~3 ngày) | Có thể bắt đầu cuối Phase 3 |
| Automated backtest + drift checks | S (~1 ngày) | Cần historical outcomes |
| Queue evolution pilot | S (~1 ngày) | Chỉ làm nếu có bằng chứng cần thiết |
| Total | L (~1 tuần) | Không nên chặn MVP nếu chưa cần tách queue |
