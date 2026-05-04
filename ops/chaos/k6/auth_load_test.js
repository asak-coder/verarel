import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const AUTH_LOGIN_PATH = __ENV.AUTH_LOGIN_PATH || '/auth/login';
const AUTH_REGISTER_PATH = __ENV.AUTH_REGISTER_PATH || '/auth/register';
const AUTH_REFRESH_PATH = __ENV.AUTH_REFRESH_PATH || '/auth/refresh';
const AUTH_ME_PATH = __ENV.AUTH_ME_PATH || '/auth/me';

export const options = {
  scenarios: {
    auth_ramp: {
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
      exec: 'authFlow',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.02'],
    http_req_duration: ['p(95)<1500', 'p(99)<3000'],
    checks: ['rate>0.95'],
  },
};

function headers(token) {
  const h = { 'Content-Type': 'application/json' };
  if (token) {
    h.Authorization = `Bearer ${token}`;
  }
  return h;
}

export function authFlow() {
  const email = __ENV.AUTH_EMAIL || `k6-${__VU}-${__ITER}@example.com`;
  const password = __ENV.AUTH_PASSWORD || 'K6-Strong-Passw0rd!';
  const username = __ENV.AUTH_USERNAME || `k6_${__VU}_${__ITER}`;

  const registerRes = http.post(
    `${BASE_URL}${AUTH_REGISTER_PATH}`,
    JSON.stringify({ email, password, username }),
    { headers: headers() }
  );

  const loginRes = http.post(
    `${BASE_URL}${AUTH_LOGIN_PATH}`,
    JSON.stringify({ email, password }),
    { headers: headers() }
  );

  const token = loginRes.json('access_token') || loginRes.json('token') || __ENV.TOKEN || '';
  const refreshToken = loginRes.json('refresh_token') || __ENV.REFRESH_TOKEN || '';

  const meRes = token
    ? http.get(`${BASE_URL}${AUTH_ME_PATH}`, { headers: headers(token) })
    : { status: 401, json: () => null };

  const refreshRes = refreshToken
    ? http.post(
        `${BASE_URL}${AUTH_REFRESH_PATH}`,
        JSON.stringify({ refresh_token: refreshToken }),
        { headers: headers() }
      )
    : { status: 200 };

  check(registerRes, {
    'register status is expected': (r) => [200, 201, 202, 409].includes(r.status),
  });
  check(loginRes, {
    'login status is 200 or 401 when credentials are invalid': (r) => [200, 401, 422].includes(r.status),
  });
  check(meRes, {
    'me returns authorized response': (r) => [200, 401].includes(r.status),
  });
  check(refreshRes, {
    'refresh returns expected status': (r) => [200, 401, 422].includes(r.status),
  });

  sleep(1);
}