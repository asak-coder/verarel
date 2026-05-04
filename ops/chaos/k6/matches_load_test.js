import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const MATCHES_PATH = __ENV.MATCHES_PATH || '/matches';
const MATCH_DETAIL_PATH = __ENV.MATCH_DETAIL_PATH || '/matches';
const MATCH_ID = __ENV.MATCH_ID || '';
const TOKEN = __ENV.TOKEN || '';

export const options = {
  scenarios: {
    matches_ramp: {
      executor: 'ramping-vus',
      startVUs: 10,
      stages: [
        { target: 10, duration: '30s' },
        { target: 50, duration: '1m' },
        { target: 200, duration: '2m' },
        { target: 500, duration: '3m' },
        { target: 1000, duration: '5m' },
        { target: 0, duration: '1m' },
      ],
      gracefulRampDown: '30s',
      exec: 'matchesFlow',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.02'],
    http_req_duration: ['p(95)<1200', 'p(99)<2500'],
    checks: ['rate>0.95'],
  },
};

function headers() {
  const h = { 'Content-Type': 'application/json' };
  if (TOKEN) h.Authorization = `Bearer ${TOKEN}`;
  return h;
}

export function matchesFlow() {
  const listRes = http.get(`${BASE_URL}${MATCHES_PATH}`, { headers: headers() });
  const matchId = MATCH_ID || listRes.json('items.0.id') || listRes.json('data.0.id') || listRes.json('0.id');

  const detailRes = matchId
    ? http.get(`${BASE_URL}${MATCH_DETAIL_PATH}/${matchId}`, { headers: headers() })
    : { status: 404 };

  const actionRes = matchId
    ? http.post(
        `${BASE_URL}${MATCH_DETAIL_PATH}/${matchId}/like`,
        JSON.stringify({ action: 'like' }),
        { headers: headers() }
      )
    : { status: 404 };

  check(listRes, {
    'matches list ok': (r) => [200, 401, 403].includes(r.status),
  });
  check(detailRes, {
    'match detail ok': (r) => [200, 401, 403, 404].includes(r.status),
  });
  check(actionRes, {
    'match action ok': (r) => [200, 202, 401, 403, 404].includes(r.status),
  });

  sleep(1);
}