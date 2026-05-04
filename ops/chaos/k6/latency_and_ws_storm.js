import http from 'k6/http';
import ws from 'k6/ws';
import { check, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

export const options = {
  scenarios: {
    http_slow_mobile: {
      executor: 'constant-vus',
      vus: 50,
      duration: '10m',
      tags: { test: 'slow_mobile' },
    },
    websocket_storm: {
      executor: 'constant-vus',
      vus: 100,
      duration: '10m',
      tags: { test: 'ws_storm' },
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.05'],
    http_req_duration: ['p(95)<2000'],
  },
};

export const ws_connect_failures = new Rate('ws_connect_failures');
export const ws_disconnects = new Counter('ws_disconnects');
export const artificial_network_delay_ms = new Trend('artificial_network_delay_ms');

const BASE_URL = __ENV.BASE_URL || 'https://api.example.com';
const TOKEN = __ENV.TOKEN || '';
const MATCH_ID = __ENV.MATCH_ID || '1';

function sleepWithJitter(minMs, maxMs) {
  const delay = Math.floor(Math.random() * (maxMs - minMs + 1)) + minMs;
  artificial_network_delay_ms.add(delay);
  sleep(delay / 1000);
}

export default function () {
  const res = http.get(`${BASE_URL}/health`, {
    timeout: '30s',
    headers: TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {},
  });

  check(res, {
    'health endpoint is reachable': (r) => r.status === 200,
  });

  sleepWithJitter(250, 2500);

  const payload = JSON.stringify({
    message: 'mobile network simulation message',
  });

  const chatRes = http.post(`${BASE_URL}/chat/tone-check`, JSON.stringify({ draft_message: payload }), {
    headers: { 'Content-Type': 'application/json' },
    timeout: '25s',
  });

  check(chatRes, {
    'tone check responds': (r) => r.status !== 500,
  });
}

export function websocketStorm() {
  const url = `${BASE_URL.replace('https://', 'wss://').replace('http://', 'ws://')}/chat/ws/${MATCH_ID}?token=${TOKEN}`;
  const params = { tags: { test: 'ws_storm' } };

  const res = ws.connect(url, params, function (socket) {
    socket.on('open', function () {
      socket.send(JSON.stringify({ message: 'storm test hello' }));
      sleepWithJitter(100, 900);
      socket.close();
    });

    socket.on('close', function () {
      ws_disconnects.add(1);
    });

    socket.on('error', function () {
      ws_connect_failures.add(1);
    });
  });

  check(res, { 'ws session completed': (r) => r && r.status === 101 });
}
