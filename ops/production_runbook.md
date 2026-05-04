# Production deployment, scaling, and reliability runbook

This repository is already structured for async FastAPI, PostgreSQL/PostGIS, Redis, Prometheus, Grafana, tracing, chaos testing, WebSockets, AI, and S3. The production system below is the deployable contract for real traffic.

## 1) Deployment architecture

### Target runtime
- **API**: FastAPI on Render Web Service or equivalent container platform
- **Worker**: Celery worker on a separate service
- **Database**: Managed PostgreSQL 16 + PostGIS
- **Cache / rate limiting**: Managed Redis
- **Object storage**: S3 or S3-compatible storage
- **Observability**: Prometheus scraping, Grafana dashboards, alertmanager, OpenTelemetry export, JSON logs
- **Synthetic monitoring**: cron job or separate worker running `ops/monitoring/synthetic_bot.py`

### Production topology
- One public API service behind platform load balancing
- One async worker pool for background jobs
- One managed PostgreSQL primary with automated backups and PITR
- One managed Redis instance with persistence and replica/failover enabled if available
- Separate alerting and dashboarding stack
- One scheduled synthetic monitor hitting `/healthz`, auth, chat, and websocket endpoints

### Runtime separation
- Put API, worker, and monitoring jobs in separate deploy targets
- Never run Celery workers inside the web container
- Never store secrets in source control

---

## 2) Config examples

### Render example
```yaml
services:
  - type: web
    name: aken-api
    env: python
    plan: starter
    region: oregon
    rootDir: .
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers
    autoDeploy: true
    healthCheckPath: /healthz
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: aken-postgres
          property: connectionString
      - key: REDIS_URL
        fromService:
          name: aken-redis
          type: redis
          property: connectionString
      - key: JWT_SECRET
        sync: false
      - key: AI_WEBHOOK_SECRET
        sync: false
      - key: AWS_ACCESS_KEY_ID
        sync: false
      - key: AWS_SECRET_ACCESS_KEY
        sync: false
      - key: AWS_SESSION_TOKEN
        sync: false
      - key: AWS_REGION
        value: us-east-1
      - key: AWS_S3_BUCKET
        sync: false
      - key: AWS_S3_ENDPOINT_URL
        sync: false
      - key: ANTHROPIC_API_KEY
        sync: false
      - key: ANTHROPIC_MODEL
        value: claude-3-5-sonnet-20240620
      - key: SERVICE_NAME
        value: aken-api
      - key: SERVICE_ENV
        value: production
      - key: ENVIRONMENT
        value: production
      - key: PYTHONUNBUFFERED
        value: "1"
      - key: LOG_LEVEL
        value: INFO
      - key: OTEL_EXPORTER_OTLP_ENDPOINT
        sync: false
      - key: OTEL_SERVICE_NAME
        value: aken-api

  - type: worker
    name: aken-worker
    env: python
    plan: starter
    region: oregon
    rootDir: .
    buildCommand: pip install -r requirements.txt
    startCommand: celery -A app.workers.tasks worker --loglevel=info --concurrency=4 --prefetch-multiplier=1
    autoDeploy: true
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: aken-postgres
          property: connectionString
      - key: REDIS_URL
        fromService:
          name: aken-redis
          type: redis
          property: connectionString
      - key: SERVICE_NAME
        value: aken-worker
      - key: SERVICE_ENV
        value: production
      - key: PYTHONUNBUFFERED
        value: "1"
```

### Environment variable setup
Required:
- `DATABASE_URL`
- `REDIS_URL`
- `JWT_SECRET`
- `AI_WEBHOOK_SECRET`
- `ANTHROPIC_API_KEY`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_S3_BUCKET`

Optional but recommended:
- `AWS_SESSION_TOKEN`
- `AWS_REGION`
- `AWS_S3_ENDPOINT_URL`
- `ANTHROPIC_MODEL`
- `OTEL_EXPORTER_OTLP_ENDPOINT`
- `SERVICE_NAME`
- `SERVICE_ENV`
- `FAILURE_INJECTION_ENABLED=false`

### Secrets handling
- Store secrets only in platform secret manager or external vault
- Rotate secrets on a fixed schedule
- Use separate secrets per environment
- Do not reuse staging credentials in production
- Restrict database and Redis network access to the app services only

---

## 3) Zero-downtime deployment strategy

### Deployment model
Use rolling deploys with health-gated cutover.

Release steps:
1. Build new image
2. Start new API instance
3. Wait for `/healthz` and `/metrics` readiness
4. Run database migrations in a separate one-off job
5. Shift traffic only after health checks pass
6. Keep old version alive until new version is healthy

### Migration strategy
Use expand/contract migrations:
- **Expand**: add nullable columns, new tables, dual-write code paths
- **Backfill**: populate new schema in background jobs
- **Switch**: read from new schema after backfill
- **Contract**: remove old columns only after all old code is drained

Rules:
- Never drop or rename a live column in the same deploy that depends on it
- Never deploy destructive schema changes without a backward-compatible transition
- Run migrations with explicit timeouts and lock limits
- Use `SELECT ... FOR UPDATE` only where strict consistency is required

### Migration rollback
- Backward-compatible migrations can be rolled back by redeploying the previous app version
- For irreversible migrations, ship a forward-fix migration immediately after validation
- Keep rollback SQL or Alembic downgrade scripts in the repository and test them in staging

---

## 4) Database safety

### Backups
- Enable automated daily full backups
- Keep WAL archiving / point-in-time recovery enabled
- Retain backups long enough to cover compliance and incident response windows
- Test restore procedures monthly

### PITR
- Restore to a timestamp before the incident
- Validate restored database against:
  - user count
  - match integrity
  - chat message integrity
  - profile integrity
  - webhook event replay status

### Data protection controls
- Use foreign keys and transactional writes
- Avoid long-running transactions in request paths
- Prefer idempotent writes for webhook and background jobs
- Use unique constraints for dedupe of retries and match creation

---

## 5) Auto-scaling

### API scaling triggers
Scale on a combination of:
- CPU > 65% for 5 minutes
- p95 latency > 800 ms for 5 minutes
- request rate above baseline by 2x
- websocket connection pressure
- worker queue depth growth

### Suggested instance bounds
- **API min**: 2
- **API max**: 6 for starter/low traffic, 10+ for growth
- **Worker min**: 1
- **Worker max**: based on queue depth and DB capacity

### Scaling rules
- Prefer horizontal scaling for API
- Do not scale past database write capacity
- Recompute worker concurrency after observing DB and Redis saturation
- Pin worker concurrency to a conservative number; increase only after queue latency remains low

---

## 6) Circuit breaker implementation

### Protected integrations
- AI APIs
- external moderation/verification services
- S3 presign/upload dependencies

### Recommended pattern
Use a per-provider async circuit breaker with:
- closed → open after repeated failures
- open → half-open after cooldown
- half-open → closed only after successful probe(s)

### Retry policy
- Retry only transient network and 5xx failures
- Maximum 3 attempts
- Exponential backoff with jitter
- Never retry validation errors or 4xx auth failures
- Cap total upstream timeout to a small bound so request threads do not hang

### Fallback responses
- AI timeout or breaker open:
  - return cached or deterministic fallback payload
  - emit metric `aken_ai_fallbacks_total`
- S3 failure:
  - return controlled 502 with retryable message
- External verification failure:
  - mark as pending or degraded, do not block the entire request flow

### Production contract
The app should never fail open on unsafe moderation or auth checks.
For user-facing AI features, degrade gracefully with deterministic fallback text.

---

## 7) Rate limiting setup

### Scope
Apply Redis-backed limits to:
- `/auth/login`
- `/auth/register`
- chat send endpoints
- AI endpoints
- websocket connect handshakes

### Policy
Recommended defaults:
- login/register: 5 requests/minute/IP, burst 10
- chat send: 30 requests/minute/user
- AI endpoints: 10 requests/minute/user
- websocket connect: 20 handshakes/minute/IP

### Redis limiter contract
- Use a token bucket or sliding window counter
- Key by route + user id + IP
- Return `429 Too Many Requests`
- Include `Retry-After`
- Make limits configurable per environment

### Required fallback
If Redis is unavailable:
- fail closed for auth and AI endpoints
- fail open only for low-risk reads if business policy allows
- emit Redis error metrics

---

## 8) Production monitoring

### Alerts
Connect Prometheus alerts to:
- email
- Slack or PagerDuty
- on-call escalation

Alert categories:
- p95 latency
- 5xx error rate
- websocket instability
- DB deadlocks / slow queries
- Redis latency / errors
- AI timeout / failure spikes
- upload failures
- cost overspend risk

### Dashboards
Dashboards should cover:
- traffic
- latency
- errors
- saturation
- websocket health
- AI latency and fallback rates
- DB query latency
- Redis command latency
- upload success/failure
- synthetic monitor status

### Synthetic monitoring
Run `ops/monitoring/synthetic_bot.py` every 5 minutes:
- auth flow
- profile fetch
- match/chat path
- websocket sanity check

Fail the synthetic job on repeated auth/profile/chat failures.

---

## 9) Load testing plan

### k6 baseline
Use the scripts under `ops/chaos/k6/`:
- auth
- matches
- chat HTTP + WebSocket
- AI endpoints
- upload flow
- geo queries
- latency and WS storm

### Production validation target
- 1000+ concurrent virtual users
- mixed read/write traffic
- websocket connect/disconnect churn
- AI fallback behavior under dependency failure
- upload signing under sustained load

### Success criteria
- p95 latency remains below SLO
- error rate remains below threshold
- websocket failure ratio stays within budget
- no DB deadlocks under normal load
- Redis remains responsive
- AI circuit breakers trip and recover cleanly
- no data loss during retries or connection churn

---

## 10) Disaster recovery plan

### DB failure recovery
1. Stop writes
2. Promote healthy replica or restore from PITR
3. Verify schema and row counts
4. Bring API back with read-only mode if needed
5. Re-enable writes after integrity checks

### Redis failure fallback
- rate limiting and presence degrade first
- websocket room coordination falls back to in-memory best effort
- chat persistence continues through Postgres
- notify ops if Redis is unavailable beyond the recovery window

### Service restart strategy
- Web API: automatic restart on process crash
- Worker: automatic restart with retry/backoff
- Use idempotent jobs so restart during processing does not duplicate irreversible effects
- Ensure startup health checks block traffic until the app is ready

### Incident runbook
- Confirm scope with metrics and logs
- Freeze deployments if the issue is release-related
- Restore service first, then recover data
- Use replayable events for webhook or stream processing where possible

---

## 11) Go-live checklist

- [ ] `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `AI_WEBHOOK_SECRET`, and cloud secrets are set in the platform secret store
- [ ] `/healthz` returns 200 and is wired into platform health checks
- [ ] `/metrics` is scrapeable from Prometheus
- [ ] JSON logs are enabled in production
- [ ] OpenTelemetry export endpoint is configured
- [ ] Database automated backups are enabled
- [ ] PITR restore test has been completed in staging
- [ ] Migrations are backward-compatible
- [ ] Rolling release strategy is enabled
- [ ] Redis-backed rate limiting is enabled for auth/chat/AI endpoints
- [ ] Circuit breakers and fallback paths are validated
- [ ] Slack/email alerting is connected
- [ ] Grafana dashboard is imported and live
- [ ] Synthetic monitoring job is scheduled
- [ ] k6 1000+ user load test has passed
- [ ] WebSocket storm test has passed
- [ ] Disaster recovery restore drill has been completed
- [ ] Rollback procedure is documented and tested

## 12) Implementation notes for this repository

The current codebase already has:
- JSON logging
- Prometheus metrics
- OpenTelemetry hooks
- Redis service abstraction
- S3 presign generation
- AI retry logic with tenacity
- failure injection helpers
- k6 scripts for stress testing

Missing production-hardening pieces to add next:
- `/healthz` endpoint
- Redis-backed rate limiter middleware/router integration
- explicit circuit breaker wrapper for external AI/S3 calls
- migration command/job and release gate
- restore/backups automation scripts

This runbook is the deployment contract for those additions.
