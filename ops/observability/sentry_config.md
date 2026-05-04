# Sentry error taxonomy and payload design

## Error categories

### Auth
- Invalid token
- Expired token
- Unauthorized role
- Session revoked

### WebSocket
- Connect auth failure
- Disconnect storm
- Receive loop crash
- Broadcast fanout failure
- Heartbeat timeout

### AI
- Provider timeout
- Provider 5xx
- Moderation parser failure
- Prompt/schema mismatch
- Fallback activation

### Upload
- Invalid MIME type
- Oversized file
- Presign generation failure
- S3 upload failure
- Corrupt media payload

### DB
- Deadlock
- Lock timeout
- Serialization failure
- Query timeout
- Constraint violation

## Tagging strategy

Use only bounded-cardinality tags.

### Required tags
- `environment`
- `service`
- `category`
- `severity`
- `endpoint`
- `operation`
- `provider`
- `feature_flag`
- `release`
- `region`

### User/session tags
- `user_id` only if sanitized and sampled
- `session_id`
- `match_id`
- `chat_room_id`

Do not attach email, phone, free-form prompts, or file contents.

## Context payload structure

```json
{
  "category": "AI",
  "severity": "error",
  "service": "aken-api",
  "environment": "production",
  "endpoint": "/chat/tone-check",
  "operation": "moderation",
  "provider": "anthropic",
  "user": {
    "id": "12345",
    "session_id": "sess_abc123",
    "match_id": "m_9981"
  },
  "request": {
    "method": "POST",
    "path": "/chat/tone-check",
    "request_id": "req_7f3b...",
    "duration_ms": 1840
  },
  "resource": {
    "redis": "ok",
    "db": "ok",
    "ai_provider": "timeout"
  },
  "degradation": {
    "mode": "fallback",
    "fallback_type": "cached_response"
  },
  "extra": {
    "retry_count": 2,
    "timeout_seconds": 15
  }
}
```

## Sentry SDK rules

- Set `before_send` to redact:
  - Authorization headers
  - cookies
  - message bodies
  - image payloads
  - prompt text
- Set `traces_sample_rate` to `0.05` in production
- Set `profiles_sample_rate` to `0.0` unless needed for an incident
- Use `send_default_pii=false`
- Use `attach_stacktrace=true`

## Capture points

- HTTP exception middleware
- WebSocket exception handler
- AI provider wrapper
- Upload presign + upload confirmation path
- Database transaction wrappers
- Redis client wrapper

## Severity mapping

- `info`: handled fallback, user-visible degradation without hard failure
- `warning`: elevated error rate, retry exhausted once
- `error`: single user request failed after retry
- `fatal`: startup failure, dependency outage, data corruption, repeated deadlocks

## Graceful degradation tags

- `degraded=true`
- `fallback_type=cached|static|blank|manual`
- `fallback_reason=ai_timeout|redis_outage|db_lock|upload_failure`
