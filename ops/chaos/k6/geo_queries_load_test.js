import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const TOKEN = __ENV.TOKEN || '';
const GEO_SEARCH_PATH = __ENV.GEO_SEARCH_PATH || '/profile/location/search';
const GEO_NEARBY_PATH = __ENV.GEO_NEARBY_PATH || '/profile/location/nearby';
const LAT = __ENV.LAT || '40.7128';
const LNG = __ENV.LNG || '-74.0060';
const RADIUS_KM = __ENV.RADIUS_KM || '25';

export const options = {
  scenarios: {
    geo_ramp: {
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
      exec: 'geoFlow',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.02'],
    http_req_duration: ['p(95)<1200', 'p(99)<3000'],
    checks: ['rate>0.95'],
  },
};

function headers() {
  const h = { 'Content-Type': 'application/json' };
  if (TOKEN) h.Authorization = `Bearer ${TOKEN}`;
  return h;
}

export function geoFlow() {
  const searchRes = http.get(
    `${BASE_URL}${GEO_SEARCH_PATH}?q=coffee&lat=${encodeURIComponent(LAT)}&lng=${encodeURIComponent(LNG)}`,
    { headers: headers() }
  );

  const nearbyRes = http.get(
    `${BASE_URL}${GEO_NEARBY_PATH}?lat=${encodeURIComponent(LAT)}&lng=${encodeURIComponent(LNG)}&radius_km=${encodeURIComponent(RADIUS_KM)}`,
    { headers: headers() }
  );

  check(searchRes, { 'geo search ok': (r) => [200, 401, 403, 404].includes(r.status) });
  check(nearbyRes, { 'geo nearby ok': (r) => [200, 401, 403, 404].includes(r.status) });

  sleep(1);
}