import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const TOKEN = __ENV.TOKEN || '';
const AI_CHAT_PATH = __ENV.AI_CHAT_PATH || '/chat/ai';
const AI_GENERATE_PATH = __ENV.AI_GENERATE_PATH || '/date-architect/generate';
const AI_IMAGE_PATH = __ENV.AI_IMAGE_PATH || '/image-edit';
const PROMPT = __ENV.PROMPT || 'Create a friendly first-date plan for a coffee shop and park walk.';
const IMAGE_URL = __ENV.IMAGE_URL || 'https://example.com/input.jpg';

export const options = {
  scenarios: {
    ai_ramp: {
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
      exec: 'aiFlow',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.05'],
    http_req_duration: ['p(95)<2000', 'p(99)<5000'],
    checks: ['rate>0.90'],
  },
};

function headers() {
  const h = { 'Content-Type': 'application/json' };
  if (TOKEN) h.Authorization = `Bearer ${TOKEN}`;
  return h;
}

export function aiFlow() {
  const chatRes = http.post(
    `${BASE_URL}${AI_CHAT_PATH}`,
    JSON.stringify({ message: PROMPT, conversation_id: `k6-${__VU}-${__ITER}` }),
    { headers: headers() }
  );

  const planRes = http.post(
    `${BASE_URL}${AI_GENERATE_PATH}`,
    JSON.stringify({ prompt: PROMPT, user_context: { age: 30, interests: ['coffee', 'music'] } }),
    { headers: headers() }
  );

  const imageRes = http.post(
    `${BASE_URL}${AI_IMAGE_PATH}`,
    JSON.stringify({ image_url: IMAGE_URL, instructions: 'make the image warmer and more cinematic' }),
    { headers: headers() }
  );

  check(chatRes, { 'chat ai ok': (r) => [200, 201, 202, 401, 403].includes(r.status) });
  check(planRes, { 'architect ai ok': (r) => [200, 201, 202, 401, 403].includes(r.status) });
  check(imageRes, { 'image ai ok': (r) => [200, 201, 202, 401, 403].includes(r.status) });

  sleep(1);
}