# 7-Day Soak Test Daily Operational Execution System

This document converts the 7-day soak test into a daily production execution system for a live FastAPI platform with Prometheus, Grafana, tracing, Sentry, Redis, PostgreSQL, WebSockets, autoscaling, rate limiting, AI circuit breakers, and cost controls.

## Operating rules

- Run this system every day for all 7 soak-test days.
- Use production metrics, logs, traces, and synthetic checks only.
- Every daily action must produce a written artifact:
  - checklist completion
  - alert triage notesgit push -u origin main
  - incident log entries
  - optimization decisions
  - end-of-day report
- If a critical issue is observed, pause optimization changes until the incident is stabilized.
- Do not rely on manual memory. Use the templates below verbatim.

---

## 1) Daily checklist

## Morning review checklist
Run at the start of every day.

- [ ] Open Grafana dashboard
- [ ] Review API p95 latency for the last 24h
- [ ] Review API p99 latency for the last 24h
- [ ] Review 5xx error rate for the last 24h
- [ ] Review WebSocket connect success rate
- [ ] Review WebSocket disconnect / drop rate
- [ ] Review WebSocket active connection count
- [ ] Review PostgreSQL health: connections, replication lag, slow queries, deadlocks
- [ ] Review Redis health: latency, error rate, memory, evictions, hit rate
- [ ] Review Sentry new issues
- [ ] Review any open critical or warning alerts from the prior 24h
- [ ] Confirm synthetic checks passed in the last run
- [ ] Confirm autoscaling did not thrash overnight
- [ ] Record all findings in the end-of-day report template

## Mid-day checklist
Run once during peak traffic.

- [ ] Review scaling behavior over the last 6h
- [ ] Review request rate vs replica count
- [ ] Review CPU and memory saturation
- [ ] Review AI request latency
- [ ] Review AI failure rate
- [ ] Review AI timeout count
- [ ] Review circuit breaker open/half-open state
- [ ] Review synthetic test results
- [ ] Review rate-limit hits by route
- [ ] Review cache hit rate and cache miss trend
- [ ] Log any anomalies or trend changes
- [ ] Decide whether any tuning is needed today

## End-of-day checklist
Run before sign-off every day.

- [ ] Review all alerts triggered since the previous check
- [ ] Classify each alert as critical, warning, or noise
- [ ] Verify alert acknowledgements and resolutions
- [ ] Review anomalies detected today
- [ ] Log every incident in structured format
- [ ] Review cost usage and daily run rate
- [ ] Review whether optimization actions improved or degraded the system
- [ ] Confirm failure injection results for the day
- [ ] Update the day’s report
- [ ] Decide whether tomorrow’s thresholds need adjustment

## Daily review format

Use this exact format in the daily ops log:

```text
DATE:
DAY OF SOAK:
REVIEW WINDOW:
OWNER:

MORNING REVIEW
- p95 latency:
- p99 latency:
- 5xx error rate:
- WebSocket stability:
- PostgreSQL health:
- Redis health:
- Synthetic status:

MID-DAY REVIEW
- Scaling behavior:
- AI latency:
- AI failure rate:
- Synthetic results:
- Cache hit rate:
- Rate-limit pressure:

END-OF-DAY REVIEW
- Alerts triggered:
- Alerts classified critical:
- Alerts classified warning:
- Alerts classified noise:
- Anomalies:
- Incidents logged:
- Cost usage:
- Actions completed:
- Actions deferred:
```

---

## 2) Alert response playbook

### Classification rules

#### Critical
Use critical when any of the following occur:

- 5xx error rate exceeds alert threshold
- p95 latency stays above threshold for the alert window
- WebSocket active connections drop sharply or disconnect rate spikes
- PostgreSQL deadlocks occur
- Redis errors spike
- AI failure rate crosses threshold
- cost overspend risk becomes material
- synthetic checks fail repeatedly

#### Warning
Use warning when:

- latency is elevated but service is still functional
- scaling is occurring but not yet unstable
- AI timeout rate is rising but fallback is working
- Redis latency increases without full outage
- cache hit rate drops
- upload or geo latency drifts upward
- traffic patterns shift unexpectedly without impact

#### Noise
Use noise when:

- alert clears before the full operating window and no impact is visible
- the alert duplicates a known incident already under control
- the alert is explained by planned failure injection
- metric fluctuation is below operational significance
- a dashboard artifact is caused by low traffic or sampling

### Response playbooks

#### Critical response playbook
- [ ] Acknowledge immediately
- [ ] Freeze non-essential deploys and config changes
- [ ] Check current blast radius in metrics, logs, and traces
- [ ] Identify whether the issue is API, DB, Redis, WebSocket, AI, or cost-related
- [ ] Confirm whether recent deployment or failure injection triggered the issue
- [ ] Restore service first
- [ ] Escalate to incident channel / on-call
- [ ] Record incident start time
- [ ] Capture mitigation action and recovery time
- [ ] Verify alert clears after mitigation
- [ ] Write root cause and preventive action

#### Warning response playbook
- [ ] Acknowledge within the same work block
- [ ] Confirm whether the trend is worsening
- [ ] Compare against previous day and baseline
- [ ] Validate synthetic checks
- [ ] Inspect saturation, queue depth, or dependency health
- [ ] Adjust a single control if needed
- [ ] Re-check after one monitoring window
- [ ] Log whether the warning was resolved, stabilized, or escalated

#### Noise response playbook
- [ ] Mark as noise only if evidence supports it
- [ ] Note why it is noise
- [ ] Adjust alert threshold only if repeat noise occurs
- [ ] Do not suppress real incidents
- [ ] If uncertain, keep it as warning until verified

### Alert handling checklist

```text
ALERT NAME:
TIME DETECTED:
SEVERITY:
CATEGORY: critical | warning | noise
SYSTEM:
EVIDENCE:
ACTION TAKEN:
OWNER:
RECOVERY TIME:
FOLLOW-UP:
```

---

## 3) Anomaly detection rules

## Sudden latency spikes

### Thresholds
- API p95 increases by 30% or more within 15 minutes
- API p99 increases by 40% or more within 15 minutes
- WebSocket handshake latency doubles within 15 minutes
- DB query p95 exceeds the baseline by 50% within 15 minutes
- Redis p95 command latency doubles within 15 minutes

### Detection logic
- Compare current 15-minute window against the previous 24-hour rolling median
- Trigger if the delta exceeds threshold on two consecutive evaluation windows
- Confirm the spike is not caused by a planned failure injection or low-volume artifact

## Gradual performance degradation

### Thresholds
- p95 latency rises by 10% or more for 3 consecutive evaluation windows
- error rate rises by 1% absolute and stays elevated for 30 minutes
- WebSocket disconnect rate rises slowly over 1 hour
- DB or Redis latency shows monotonic drift over 2+ hours

### Detection logic
- Compare 1-hour moving average to 24-hour baseline
- Trigger only when slope remains positive across at least 3 samples
- Cross-check with scaling, queue depth, and dependency metrics

## Unusual traffic patterns

### Thresholds
- Request volume doubles without a corresponding traffic event
- WebSocket connect/disconnect churn exceeds 2x baseline
- AI endpoint volume rises without product event correlation
- Route-level skew: one endpoint exceeds 40% of total traffic unexpectedly

### Detection logic
- Compare route mix, user counts, IP concentration, and connect churn against baseline
- Trigger when traffic distribution deviates materially from the previous 24h pattern
- Correlate with rate-limit hits and auth failures

## Cost anomalies

### Thresholds
- Estimated hourly spend rises 25% above baseline
- AI cost per request rises 20% above baseline
- Redis or DB cost proxies increase due to saturation or over-scaling
- Cost trend remains elevated for 30 minutes or more

### Detection logic
- Compare current hourly run rate to trailing 7-day baseline
- Trigger if increase is sustained for two windows
- Correlate spend change with AI traffic, retries, or over-scaling

### Anomaly log format

```text
TIME:
ANOMALY TYPE:
SYSTEM:
DETECTION RULE:
BASELINE:
CURRENT VALUE:
IMPACT:
ACTION:
STATUS:
```

---

## 4) Incident logging system

Use this exact structured format for every incident.

```text
INCIDENT ID:
TIMESTAMP:
ISSUE TYPE:
AFFECTED SYSTEM:
SEVERITY:
DETECTED BY:
TRIGGER:
ROOT CAUSE:
USER IMPACT:
MITIGATION:
RESOLUTION:
RECOVERY TIME:
PREVENTIVE ACTION:
FOLLOW-UP OWNER:
CLOSED:
```

## Mandatory incident logging rules
- Log every critical issue.
- Log repeated warnings if they occur more than once in a day.
- Log all failure-injection events with outcome and recovery time.
- Link the incident to the alert name and dashboard snapshot.
- Add the preventive action before closing the incident.

---

## 5) Daily optimization actions

Perform one optimization pass each day after the morning review and before the end-of-day sign-off.

### Autoscaling thresholds
Decision rules:
- If p95 latency is rising while CPU remains low, lower the latency trigger slightly.
- If replicas are thrashing up and down, widen the scaling cooldown.
- If queue depth rises before CPU does, scale on queue depth earlier.
- If DB or Redis is saturated, do not increase API scale further.
- If synthetic latency improves after scale-out, keep the adjustment and validate next day.

### Rate limits
Decision rules:
- If abuse or bursts are visible, tighten the relevant route limit.
- If legitimate traffic is hitting limits and error rate stays clean, relax the limit slightly.
- If AI cost is rising faster than traffic, reduce AI request allowance or add tighter user quotas.
- If WebSocket handshake churn is high, tighten connection rate limits.
- Never loosen limits during an active incident unless the limit is clearly the cause of a false positive.

### Cache hit rates
Decision rules:
- If DB load is rising and cache hit rate is low, increase cache TTL where safe.
- If stale reads appear, reduce TTL or refine invalidation.
- If repeated identical reads are hitting Postgres, add or enlarge cache coverage.
- If Redis memory pressure rises, reduce low-value cache entries first.
- If hit rate drops after a deployment, treat as regression and investigate.

### AI cost usage
Decision rules:
- If AI latency is stable but cost per request is rising, shorten prompts or reduce retries.
- If circuit breakers are opening frequently, improve fallback usage and lower upstream pressure.
- If a route has low user value and high AI spend, reduce invocation frequency.
- If AI success rate is good but cost is high, prefer cached or deterministic responses.
- If AI failure rate rises, do not increase concurrency until upstream health recovers.

### Daily optimization checklist

```text
DATE:
OPTIMIZATION AREA:
CURRENT STATE:
CHANGE MADE:
EXPECTED OUTCOME:
RISK:
VALIDATION METHOD:
RESULT:
```

---

## 6) Controlled failure schedule

Inject one controlled failure per specified day. Validate response, alerting, and recovery.

## Failure injection rules
- Use only the documented failure injection helpers or approved production-safe mechanisms.
- Inject during the defined test window, not during peak incident activity.
- Observe alert behavior, synthetic behavior, and recovery time.
- Stop the injection immediately if user impact exceeds expectation.

## Schedule

### Day 2 - AI timeout
Inject:
- AI upstream timeout
- verify circuit breaker opens
- verify fallback response is served

Verify:
- AI timeout alert triggers
- circuit breaker state changes
- fallback path works
- recovery time is recorded

### Day 3 - Redis disconnect
Inject:
- Redis connection loss or forced dependency timeout

Verify:
- rate limiting behavior is correct
- Redis error alert triggers
- fallback policy behaves as designed
- presence / cache degradation is logged
- recovery is observed and recorded

### Day 4 - DB latency spike
Inject:
- PostgreSQL latency increase or slow query pressure

Verify:
- DB slow query alert triggers
- API latency response is visible
- queue or connection pressure is captured
- recovery time is recorded

### Day 5 - WebSocket drop
Inject:
- WebSocket disconnect storm or connection failure

Verify:
- WebSocket instability alert triggers
- active connection count drops as expected
- reconnect behavior is measured
- message path remains stable where possible

## Failure injection execution checklist

```text
DAY:
FAILURE TYPE:
START TIME:
END TIME:
EXPECTED ALERT:
ALERT FIRED:
EXPECTED FALLBACK:
OBSERVED RESPONSE:
RECOVERY TIME:
INCIDENT LOGGED:
```

---

## 7) End-of-day report template

Use this format every day.

```text
DATE:
DAY OF SOAK:
OWNER:
REPORT STATUS:

SYSTEM HEALTH SUMMARY
- API latency:
- API error rate:
- WebSocket health:
- PostgreSQL health:
- Redis health:
- AI health:
- Cost health:

INCIDENTS
- Incident ID:
- Severity:
- Summary:
- Status:

METRICS TRENDS
- p95 trend:
- p99 trend:
- error trend:
- connection trend:
- cache hit trend:
- AI latency trend:
- cost trend:

SCALING BEHAVIOR
- Scale-out events:
- Scale-in events:
- Thrashing observed:
- Current replica count:
- Recommendation:

COST USAGE
- AI spend:
- DB/Redis saturation effect:
- Estimated daily run rate:
- Budget risk:

ACTION ITEMS
- Action:
- Owner:
- Due date:
- Priority:
```

## Report rules
- Include only measured facts.
- Include action items with owners.
- Include whether the day’s failure injection was successful.
- Include whether the system stayed within acceptable operational limits.

---

## 8) Final decision framework

Use at the end of day 7.

## Ready for full-scale rollout
Choose this only if all are true:
- No unresolved critical incidents
- No repeated unmitigated critical alerts
- p95 and p99 latency stay within agreed SLOs
- 5xx error rate remains within threshold
- WebSocket stability stays within budget
- PostgreSQL and Redis remain healthy
- AI circuit breakers and fallbacks behave correctly
- Cost usage stays inside budget trend
- Failure injections were handled correctly and recovered within target times
- No data loss or integrity issues

## Needs tuning
Choose this if:
- No critical unresolved issue exists
- One or more warning trends persist
- Scaling behavior needs refinement
- Rate limits require calibration
- Cache hit rate or AI cost needs optimization
- One failure injection exposed a weakness but recovery was acceptable

## Critical issues remain
Choose this if any of the following are true:
- Any critical incident remains unresolved
- Repeated severe failures occurred
- Data integrity is uncertain
- Recovery time exceeded acceptable limits
- WebSocket, DB, Redis, or AI reliability is unstable
- Cost controls are failing materially
- Synthetic checks cannot complete reliably

## Final decision checklist

```text
DAY 7 SUMMARY:
UNRESOLVED CRITICAL ISSUES:
UNRESOLVED WARNINGS:
SLO STATUS:
WEB SOCKET STATUS:
DB STATUS:
REDIS STATUS:
AI STATUS:
COST STATUS:
FAILURE INJECTION STATUS:
DATA INTEGRITY STATUS:
DECISION: ready for full-scale rollout | needs tuning | critical issues remain
REASON:
NEXT ACTION:
```

---

## 7-day daily operating cadence

### Day 1
- Baseline all dashboards
- Establish medians and normal ranges
- Capture first report
- No failure injection

### Day 2
- Run daily checklist
- Inject AI timeout
- Verify breaker and fallback behavior
- Log incident and recovery

### Day 3
- Run daily checklist
- Inject Redis disconnect
- Verify degradation and recovery
- Adjust cache and rate-limit settings if needed

### Day 4
- Run daily checklist
- Inject DB latency spike
- Verify DB alerts and recovery
- Tune autoscaling only if safe

### Day 5
- Run daily checklist
- Inject WebSocket drop
- Verify reconnect behavior and alerts
- Adjust websocket thresholds if justified

### Day 6
- Run daily checklist
- No failure injection unless a prior issue needs re-validation
- Validate the system under normal load
- Review all optimization actions from prior days

### Day 7
- Run final daily checklist
- Confirm all reports are complete
- Make final rollout decision
- Archive incident logs and daily reports

---

## Required operational artifacts

At the end of the soak test, the following must exist:

- 7 completed daily checklists
- 7 end-of-day reports
- all incident logs
- all anomaly logs
- all failure injection logs
- all optimization action records
- final rollout decision record

---

## Operational success criteria

The soak test is successful only if:

- no blind spots remain in the daily review cycle
- anomalies are detected early enough to act on them
- incidents are logged in a structured way
- optimization happens daily and is documented
- failure injections prove resilience and recovery
- the final rollout decision is supported by evidence
