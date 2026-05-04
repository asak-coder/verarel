import http from 'k6/http';
import ws from 'k6/ws';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const CHAT_HTTP_PATH = __ENV.CHAT_HTTP_PATH || '/chat';
const CHAT_THREAD_ID = __ENV.CHAT_THREAD_ID || '';
const TOKEN = __ENV.TOKEN || '';
const WS_URL = __ENV.WS_URL || buildWsUrl(BASE_URL);
const WS_PATH = __ENV.WS_PATH || '/ws/chat';
const MESSAGE_TEXT = __ENV.MESSAGE_TEXT || 'k6 chaos test message';

export const options = {
  scenarios: {
    chat_http_ramp: {
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
      exec: 'chatHttpFlow',
    },
    chat_ws_ramp: {
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
      exec: 'chatWsFlow',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.03'],
    http_req_duration: ['p(95)<1500', 'p(99)<3000'],
    ws_connecting: ['p(95)<2000'],
    checks: ['rate>0.90'],
  },
};

function headers() {
  const h = { 'Content-Type': 'application/json' };
  if (TOKEN) h.Authorization = `Bearer ${TOKEN}`;
  return h;
}

function buildWsUrl(base) {
  const url = new URL(base);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${url.origin}${WS_PATH}`;
}

export function chatHttpFlow() {
  const threadId = CHAT_THREAD_ID || `thread-${__VU}-${__ITER}`;
  const listRes = http.get(`${BASE_URL}${CHAT_HTTP_PATH}/${threadId}/messages`, { headers: headers() });
  const sendRes = http.post(
    `${BASE_URL}${CHAT_HTTP_PATH}/${threadId}/messages`,
    JSON.stringify({ message: MESSAGE_TEXT, thread_id: threadId }),
    { headers: headers() }
  );

  check(listRes, { 'chat list ok': (r) => [200, 401, 403, 404].includes(r.status) });
  check(sendRes, { 'chat send ok': (r) => [200, 201, 202, 401, 403, 404].includes(r.status) });

  sleep(1);
}

export function chatWsFlow() {
  const threadId = CHAT_THREAD_ID || `thread-${__VU}-${__ITER}`;
  const url = `${WS_URL}?token=${encodeURIComponent(TOKEN)}&thread_id=${encodeURIComponent(threadId)}`;

  const res = ws.connect(url, { headers: TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {} }, function (socket) {
    socket.on('open', function () {
      socket.send(JSON.stringify({ type: 'join', thread_id: threadId }));
      socket.send(JSON.stringify({ type: 'message', thread_id: threadId, content: MESSAGE_TEXT }));
    });

    socket.setTimeout(function () {
      socket.close();
    }, 5000);

    socket.on('message', function () {});
  });

  check(res, {
    'ws connected': (r) => r && r.status === 101,
  });

  sleep(1);
}