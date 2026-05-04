# Chaos Validation

This folder contains production-like k6 load and chaos validation scripts for the dating app backend.

## Scripts

| Script | Purpose |
| --- | --- |
| `ops/chaos/k6/auth_load_test.js` | Auth login/register/refresh/me load test |
| `ops/chaos/k6/matches_load_test.js` | Match list/detail/action traffic |
| `ops/chaos/k6/chat_http_ws_load_test.js` | Chat HTTP endpoints plus WebSocket connect/send storm |
| `ops/chaos/k6/ai_endpoints_load_test.js` | AI-assisted chat, date-architect, and image-edit workloads |
| `ops/chaos/k6/upload_flow_load_test.js` | S3 upload signing + completion flow |
| `ops/chaos/k6/geo_queries_load_test.js` | Location / geo search and nearby queries |
| `ops/chaos/k6/latency_and_ws_storm.js` | Existing baseline latency and WS storm scenario |

## Common runtime variables

Use these environment variables to target the correct deployment and credentials:

- `BASE_URL` - API base URL, e.g. `https://api.example.com`
- `TOKEN` - bearer token for authenticated endpoints
- `AUTH_EMAIL`, `AUTH_PASSWORD`, `AUTH_USERNAME`
- `MATCH_ID` - specific match to exercise
- `CHAT_THREAD_ID` - specific chat thread/conversation identifier
- `WS_URL` - explicit websocket URL when the default generator is not correct
- `UPLOAD_*` variables from `upload_flow_load_test.js`
- `LAT`, `LNG`, `RADIUS_KM` for geo queries
- `SIMULATE_SIGNING=true|false` for upload signing simulation
- Endpoint override vars such as `AUTH_LOGIN_PATH`, `MATCHES_PATH`, `CHAT_HTTP_PATH`, `PRESIGN_PATH`, etc.

## Load profile

Each script uses a ramping-vus scenario that grows from 10 users to 1000 users and then ramps back down. The intent is to validate:

- auth throughput under burst login/register pressure
- match retrieval and mutation under sustained read/write churn
- chat HTTP and WebSocket resilience under mixed traffic
- AI endpoint latency and error handling under contention
- upload signing and completion behaviour under concurrent traffic
- geo search and nearby lookup performance with cache and database pressure

## Expected metrics

Track these Prometheus / k6 signals during runs:

- `http_req_duration` p95/p99 latency
- `http_req_failed` error rate
- `checks` pass rate
- WebSocket connection stability / handshake latency
- Backend app metrics for:
  - HTTP request latency and error rate
  - WS accept/close counts
  - DB query duration and failures
  - Redis hit/miss and command duration
  - AI request latency/cost/error counters
  - upload signing / object completion latency
  - geo lookup latency and cache behaviour

## Suggested command examples

```bash
k6 run -e BASE_URL=http://localhost:8000 ops/chaos/k6/auth_load_test.js
k6 run -e BASE_URL=http://localhost:8000 -e TOKEN=... ops/chaos/k6/matches_load_test.js
k6 run -e BASE_URL=http://localhost:8000 -e TOKEN=... ops/chaos/k6/chat_http_ws_load_test.js
k6 run -e BASE_URL=http://localhost:8000 -e TOKEN=... ops/chaos/k6/ai_endpoints_load_test.js
k6 run -e BASE_URL=http://localhost:8000 -e TOKEN=... ops/chaos/k6/upload_flow_load_test.js
k6 run -e BASE_URL=http://localhost:8000 -e TOKEN=... ops/chaos/k6/geo_queries_load_test.js
```

## Validation notes

- Prefer stable fixtures for `MATCH_ID` and `CHAT_THREAD_ID` when running against seeded environments.
- If websocket routing differs between environments, set `WS_URL` explicitly.
- Upload flow scripts can be run in signing-only mode via `SIMULATE_SIGNING=true` to validate the control plane without transferring a large payload.
- For production chaos runs, start with a smaller subset of scenarios and verify error budgets before scaling to the full 1000-VU ramp.