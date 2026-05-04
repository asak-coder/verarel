import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const TOKEN = __ENV.TOKEN || '';
const PRESIGN_PATH = __ENV.PRESIGN_PATH || '/profile/upload-url';
const COMPLETE_PATH = __ENV.COMPLETE_PATH || '/profile/upload-complete';
const FILE_KEY_PREFIX = __ENV.FILE_KEY_PREFIX || 'k6-chaos/uploads';
const SIMULATE_SIGNING = (__ENV.SIMULATE_SIGNING || 'true').toLowerCase() === 'true';

export const options = {
  scenarios: {
    upload_ramp: {
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
      exec: 'uploadFlow',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.03'],
    http_req_duration: ['p(95)<1500', 'p(99)<4000'],
    checks: ['rate>0.95'],
  },
};

function headers() {
  const h = { 'Content-Type': 'application/json' };
  if (TOKEN) h.Authorization = `Bearer ${TOKEN}`;
  return h;
}

export function uploadFlow() {
  const filename = `${FILE_KEY_PREFIX}/${__VU}-${__ITER}.jpg`;
  const presignPayload = {
    filename,
    content_type: 'image/jpeg',
    simulate: SIMULATE_SIGNING,
    size_bytes: 204800,
  };

  const presignRes = http.post(`${BASE_URL}${PRESIGN_PATH}`, JSON.stringify(presignPayload), { headers: headers() });
  const uploadUrl = presignRes.json('upload_url') || presignRes.json('url') || '';
  const objectKey = presignRes.json('key') || presignRes.json('object_key') || filename;

  const completeRes = uploadUrl
    ? http.post(
        `${BASE_URL}${COMPLETE_PATH}`,
        JSON.stringify({ key: objectKey, filename, status: 'uploaded', simulate: SIMULATE_SIGNING }),
        { headers: headers() }
      )
    : { status: 400 };

  check(presignRes, {
    'presign ok': (r) => [200, 201, 202, 401, 403, 404].includes(r.status),
  });
  check(completeRes, {
    'complete ok': (r) => [200, 201, 202, 400, 401, 403, 404].includes(r.status),
  });

  sleep(1);
}