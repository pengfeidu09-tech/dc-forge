const baseUrl = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

async function request(path, options = {}) {
  const response = await fetch(`${baseUrl}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = payload?.detail
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail || payload || `HTTP ${response.status}`))
  }
  return payload
}
const post = (path, body) => request(path, { method: 'POST', body: JSON.stringify(body) })

export const consoleApi = {
  health: () => request('/health'),
  analyze: (body) => post('/internal-console/analyze', body),
  confirm: (body) => post('/internal-console/confirm', body),
  compile: (body) => post('/internal-console/compile', body),
  diff: (body) => post('/internal-console/diff', body),
  recompile: (body) => post('/internal-console/recompile', body),
  changeSet: (body) => post('/internal-console/change-set', body),
  reviewChangeSet: (body) => post('/internal-console/change-set/review', body),
}
