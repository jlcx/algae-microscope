/** Client for the server API (SPEC.md §7). */

import type {
  Capabilities, ClientConfig, Delta, Neighborhood, RequestFilters, SearchHit,
} from './types.ts';

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(url, init);
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      detail = (await resp.json()).detail ?? detail;
    } catch { /* non-JSON error body */ }
    throw new Error(`${resp.status}: ${detail}`);
  }
  return resp.json() as Promise<T>;
}

function post<T>(url: string, body: unknown): Promise<T> {
  return request<T>(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export const api = {
  capabilities: () => request<Capabilities>('/api/capabilities'),
  config: () => request<ClientConfig>('/api/config'),
  search: (q: string, limit = 8) =>
    request<SearchHit[]>(`/api/search?q=${encodeURIComponent(q)}&limit=${limit}`),
  neighborhood: (seeds: string[], hops: number, budget: number,
                 filters: RequestFilters) =>
    post<Neighborhood>('/api/neighborhood', { seeds, hops, budget, filters }),
  expand: (state: string[], node: string, budget: number,
           filters: RequestFilters) =>
    post<Delta>('/api/neighborhood/expand', { state, node, budget, filters }),
  entity: (qid: string) => request<{
    qid: string; label: string; wp_count: number | null;
    dates: { property: string; time_value: string; precision: number }[];
  }>(`/api/entity/${qid}`),
  edge: (src: string, dst: string) =>
    request<Record<string, unknown>>(`/api/edge/${src}/${dst}`),
};
