export const API_BASE = process.env.API_BASE || 'http://localhost:8000';

export async function apiRequest<T = unknown>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...(options.headers || {}),
    },
    ...options,
  });

  const payload = response.headers.get('content-type')?.includes('application/json')
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const detail = typeof payload === 'string'
      ? payload
      : (payload as { detail?: string }).detail || JSON.stringify(payload);
    throw new Error(detail || 'Ошибка запроса');
  }

  return payload as T;
}

export function artifactUrl(kind: string, taskId: string, filename: string) {
  return `${API_BASE}/ui/artifacts/${encodeURIComponent(kind)}/${encodeURIComponent(taskId)}/${encodeURIComponent(filename)}`;
}
