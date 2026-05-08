export type CompatibilityResponse = {
  score: number;
  reasons: string[];
  last_updated: string;
  cache_hit: boolean;
};

export type ChatSuggestionsResponse = {
  suggestions: string[];
  cache_hit: boolean;
};

export type TrustResponse = {
  score: number;
  tier: string;
  verified: boolean;
  reports_count?: number;
  blocks_count?: number;
  verification_type?: string | null;
  last_updated?: string | null;
  cached?: boolean;
};

export type DatePlanVenue = {
  name: string;
  rating: number;
  venue_type: string;
  address?: string | null;
  photo_url?: string | null;
  distance_meters?: number | null;
};

export type DatePlanResponse = {
  match_id: number;
  midpoint: {
    latitude: number;
    longitude: number;
  };
  venues: DatePlanVenue[];
};

const API_BASE_URL = typeof window !== "undefined" && window.location.origin ? window.location.origin : "http://localhost:8000";

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed with ${response.status}`);
  }

  return (await response.json()) as T;
}

export async function getCompatibility(matchId: number, token: string): Promise<CompatibilityResponse> {
  return fetchJson<CompatibilityResponse>(`/api/compatibility/${matchId}`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
}

export async function getChatSuggestions(matchId: number, userId: number): Promise<ChatSuggestionsResponse> {
  return fetchJson<ChatSuggestionsResponse>(`/api/chat/suggestions/${matchId}?user_id=${userId}`);
}

export async function getTrustScore(userId: number): Promise<TrustResponse> {
  return fetchJson<TrustResponse>(`/api/trust/${userId}`);
}

export async function getDatePlan(matchId: number, targetUserId: number): Promise<DatePlanResponse> {
  return fetchJson<DatePlanResponse>(`/api/date-plan/${matchId}`, {
    method: "GET",
    headers: {
      "X-User-Id": String(targetUserId),
    },
  });
}
