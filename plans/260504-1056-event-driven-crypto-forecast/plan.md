## Plan: Nền tảng AI dự đoán giá crypto theo hướng event-driven

### Bối cảnh
- Hiện trạng repo: gần như trống, mới có `/README.md`.
- Mục tiêu sản phẩm: ưu tiên độ chính xác hơn tốc độ MVP, hỗ trợ nhiều coin ngay từ đầu, dashboard và Telegram đều hiển thị cả xu hướng dự báo lẫn giá mục tiêu, Telegram gửi theo lịch.
- Mục tiêu kỹ thuật: thiết kế theo hướng event-driven nhưng triển khai tăng dần để tránh over-engineering; ưu tiên shared contracts + storage + pipeline chạy nội bộ trước khi tách queue/services độc lập.

### Nguyên tắc kiến trúc
- Reuse-first: repo trống nên tận dụng thư viện chuẩn và managed services trước, không tự dựng hạ tầng phức tạp sớm.
- YAGNI: giai đoạn đầu chưa cần full microservices, distributed stream processing hay online learning.
- KISS: bắt đầu bằng modular monolith hoặc vài worker process dùng chung schema sự kiện, sau đó mới tách service khi tải/vận hành yêu cầu.
- DRY: shared contracts, feature definitions, model metadata, forecast schema là SSOT.
- No hardcoded values: coin universe, lịch Telegram, horizon dự báo, model params, retention, alert thresholds phải đi qua config/env.

### Target Architecture Boundaries
1. Data Ingestion Service
   - Thu thập market candles/order-book-lite/funding/open-interest/news-sentiment macro feeds.
   - Chuẩn hóa raw event thành market events có schema/version.
2. Feature/Model Pipeline
   - Tạo feature store offline từ raw events.
   - Train, evaluate, register model artifacts theo từng horizon/coin cluster.
3. Inference Service
   - Sinh dự báo định kỳ hoặc theo trigger event.
   - Xuất cả `trend` và `target_price` cùng confidence/metadata.
4. Forecast Storage / Serving API
   - Lưu forecast, model version, realized outcome, explanation snapshots.
   - Phục vụ dashboard và Telegram qua API thống nhất.
5. Dashboard
   - Hiển thị multi-coin watchlist, forecast trend, target price, horizon, confidence, realized vs predicted.
6. Telegram Notification Service
   - Lấy forecast mới nhất theo lịch, format message đa coin, gửi định kỳ.
7. Monitoring / Backtest
   - Theo dõi freshness, data gaps, forecast drift, model quality, backtest rolling-window.

### Lộ trình khuyến nghị
- Bước 1: Thiết kế event-driven ở mức contract và table schema trước.
- Bước 2: Chạy ingestion, feature build, inference như các job/process nội bộ dùng chung DB/object storage.
- Bước 3: Khi đã ổn định schema, SLA và khối lượng dữ liệu, mới thêm queue/event bus để tách ingestion ↔ inference ↔ notification.
- Bước 4: Chỉ tách service vật lý khi có nhu cầu rõ ràng về scale, deploy cadence, fault isolation.

### Tradeoff của hướng event-driven
| Chủ đề | Lợi ích | Tradeoff / Chi phí |
|---|---|---|
| Tách rời ingestion, inference, notify | Dễ scale độc lập, fault isolation tốt hơn | Tăng độ phức tạp vận hành, tracing, retry, idempotency |
| Dữ liệu theo sự kiện | Phù hợp time-series, replay/backfill tốt | Cần schema versioning, dedup, ordering strategy |
| Multi-coin từ đầu | Cùng một pipeline cho nhiều tài sản | Dễ nổ complexity nếu coin-specific logic rải rác |
| Telegram theo lịch | Phù hợp batch forecast và UX tài chính | Cần snapshot consistency để không gửi dữ liệu nửa chừng |
| Ưu tiên accuracy | Cho phép feature/model pipeline kỹ hơn | MVP chậm hơn, compute/backtest tốn hơn |

### Feasibility
- Reuse check: NEW, vì repo hiện chỉ có README; nên bootstrap theo skeleton tối thiểu.
- Complexity: Moderate ở giai đoạn 1-3, tăng lên Complex từ lúc tách queue/services và thêm monitoring drift/backtest production-grade.

### Dependencies
- Blocks: Chưa có code nền, schema, infra baseline, test harness.
- Blocked by:
  - Chốt stack chính (gợi ý: Python cho data/ML, API Python hoặc Node tùy đội, Postgres + object storage).
  - Chốt danh sách coin ban đầu, horizon dự báo, cadence Telegram.
  - Chốt nguồn dữ liệu ưu tiên và chi phí API.

### Phases
- Phase 1: Foundation Contracts & Storage — shared schemas, repo skeleton, config, storage SSOT | Effort: M
- Phase 2: Ingestion + Offline Feature/Model Pipeline — ingest multi-coin, feature engineering, baseline training/backtest | Effort: L
- Phase 3: Inference + Serving API — scheduled forecast generation, forecast persistence, read API | Effort: M
- Phase 4: Dashboard + Telegram Delivery — UI đa coin, scheduled notifications, message formatting | Effort: M
- Phase 5: Monitoring + Event Bus Evolution — quality monitoring, drift/backtest automation, queue extraction | Effort: L

### Data Flow Ownership
1. External providers → Ingestion Service owns raw capture + normalization.
2. Normalized market events → Feature/Model Pipeline owns feature derivation + dataset versioning.
3. Registered model + feature snapshot → Inference Service owns prediction generation.
4. Forecast records → Forecast Storage/API owns persistence + retrieval contract.
5. Forecast API responses → Dashboard/Telegram consume read-only projections.
6. Realized outcomes + metrics → Monitoring/Backtest owns evaluation and alerting.

### Backwards Compatibility Strategy
- Giai đoạn đầu là additive, chưa có legacy clients.
- Dù repo mới, vẫn phải version hóa event schema (`schema_version`) và API response (`api_version`) từ ngày đầu.
- Khi đổi feature schema hoặc forecast payload, dùng new version + dual-read window, không sửa silent in-place.

### Rollback Strategy
- Phase 1: rollback bằng migration down + xóa skeleton module nếu cần.
- Phase 2: rollback bằng disable dataset/model version mới, giữ artifact cũ.
- Phase 3: rollback bằng switch active model/version hoặc tắt scheduler inference.
- Phase 4: rollback bằng disable dashboard widgets / Telegram job qua config.
- Phase 5: rollback bằng chạy synchronous/local path thay cho queue consumer.

### Test Matrix
| Phase | Validation command / check | Pass condition |
|---|---|---|
| 1 | schema validation + migration test + contract tests | event/forecast schema parse đúng, DB migrate lên/xuống sạch |
| 2 | deterministic backtest run trên sample period | sinh feature set, train xong, metrics baseline đạt ngưỡng đã định |
| 3 | end-to-end forecast generation on schedule | 1 batch multi-coin tạo đủ forecast records + API trả đúng payload |
| 4 | UI smoke test + Telegram dry-run snapshot | dashboard hiển thị đúng trend/target, Telegram render đúng nhiều coin |
| 5 | replay/backfill + monitoring alert simulation | consumer idempotent, drift/freshness alert hoạt động |

### Risk Assessment
| Risk | Likelihood (1-5) | Impact (1-5) | Score | Mitigation |
|------|-----------------|--------------|-------|------------|
| Chọn event-driven quá sớm làm chậm delivery | 4 | 4 | 16 | Bắt đầu bằng shared contracts + DB/outbox; chỉ tách queue khi có dấu hiệu nghẽn rõ ràng |
| Chất lượng dữ liệu kém làm giảm accuracy | 4 | 5 | 20 | Ưu tiên validation nguồn dữ liệu, data quality gates, gap detection, replay/backfill |
| Multi-coin ngay từ đầu làm phức tạp feature/model logic | 4 | 4 | 16 | Chuẩn hóa coin config, shared feature templates, tách coin-specific overrides qua config |
| Forecast không nhất quán giữa dashboard và Telegram | 3 | 5 | 15 | Cùng đọc từ forecast snapshot table theo forecast batch ID |
| Backtest leakage / lookahead bias | 3 | 5 | 15 | Thiết kế rolling-window evaluation, strict feature cutoff timestamps, review dataset builder |
| Chi phí vận hành dữ liệu + training tăng nhanh | 3 | 4 | 12 | Chọn coin set nhỏ ban đầu, train theo cadence cố định, lưu artifacts có vòng đời |

### Timeline
| Phase | Effort | Notes |
|-------|--------|-------|
| Phase 1: Foundation Contracts & Storage | M (~3 ngày) | Mở đường cho mọi phase sau |
| Phase 2: Ingestion + Offline Feature/Model Pipeline | L (~1 tuần) | Critical path về accuracy |
| Phase 3: Inference + Serving API | M (~3 ngày) | Phụ thuộc schema + model artifact |
| Phase 4: Dashboard + Telegram Delivery | M (~3 ngày) | Phụ thuộc API snapshot ổn định |
| Phase 5: Monitoring + Event Bus Evolution | L (~1 tuần) | Chỉ nên làm sau khi có baseline chạy ổn định |
| Total | ~4 tuần | Critical path: 1 → 2 → 3 → 4; Phase 5 song song hóa một phần sau Phase 3 |

### Behavioral Checklist
- [x] Data flows — đã trace từ provider đến dashboard/Telegram/monitoring
- [x] Dependency graph — có blockers, critical path, điểm có thể trì hoãn queue tách riêng
- [x] Risk assessment — mọi risk lớn đều có mitigation; risk >= 15 được chặn trước phase tương ứng
- [x] Backwards compatibility — additive + versioning from day one
- [x] Test matrix — mỗi phase có check pass/fail rõ ràng
- [x] Rollback plan — có rollback theo phase
- [x] File ownership — phase ownership tách theo module/boundary
- [x] Success criteria — định nghĩa khách quan trong phase files

### Ghi chú triển khai thực tế
- Accuracy-first gợi ý bắt đầu với offline batch forecasting theo horizon cố định (ví dụ 4h / 24h) thay vì realtime tick-by-tick.
- Event-driven nên bắt đầu ở mức semantic contract (`MarketEvent`, `FeatureSetBuilt`, `ModelRegistered`, `ForecastGenerated`, `NotificationScheduled`) nhưng chưa cần Kafka/RabbitMQ ngay.
- Outbox table hoặc append-only event log trong Postgres là bước chuyển tiếp thực tế trước khi dùng queue thật.
- Không nên xây feature store online, model registry riêng, hay stream processor chuyên dụng trong 1-2 tuần đầu.

### Bắt đầu từ đâu
Trong 1-2 tuần đầu, nên tập trung vào một đường đi hoàn chỉnh nhưng hẹp:
1. Chốt 3-5 coin đầu tiên, 1-2 horizon dự báo, và 1 cadence Telegram cố định.
2. Dựng Phase 1 hoàn chỉnh: shared contracts, schema DB/object storage, repo skeleton, config chuẩn.
3. Làm ingestion lịch sử + offline feature pipeline đủ để backtest trên dữ liệu thật.
4. Huấn luyện baseline model đầu tiên và lưu forecast vào storage chung.
5. Chỉ sau khi nhìn thấy forecast records ổn định mới mở API, dashboard tối thiểu và Telegram snapshot.

/t1k:cook C:/Projects/MyProject/forecast-crypto/plans/260504-1056-event-driven-crypto-forecast/plan.md
