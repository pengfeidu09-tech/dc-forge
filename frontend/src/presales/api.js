const TOKEN_STORAGE_KEY = 'dcforgeInternalToken'

export function getStoredToken() {
  return localStorage.getItem(TOKEN_STORAGE_KEY) || ''
}

export function storeToken(token) {
  localStorage.setItem(TOKEN_STORAGE_KEY, token.trim())
}

async function request(path, options = {}) {
  const token = getStoredToken()
  const response = await fetch(path, {
    ...options,
    headers: {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { 'X-DCForge-Internal-Token': token } : {}),
      ...(options.headers || {}),
    },
  })
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = payload?.detail
    throw new Error(typeof detail === 'string' ? detail : `请求失败（HTTP ${response.status}）`)
  }
  return payload
}

const projectPath = (projectId) => `/presales/projects/${encodeURIComponent(projectId)}`

export const presalesApi = {
  listProjects: () => request('/presales/projects'),
  createProject: (payload) => request('/presales/projects', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  getProject: (projectId) => request(projectPath(projectId)),
  addSource: (projectId, payload) => request(`${projectPath(projectId)}/sources`, {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  runResearch: (projectId, payload) => request(`${projectPath(projectId)}/research`, {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  generateDraft: (projectId) => request(`${projectPath(projectId)}/drafts`, {
    method: 'POST',
    body: JSON.stringify({ generated_by: 'demo-workbench' }),
  }),
  updateDeliverable: (projectId, draftVersion, payload) => request(
    `${projectPath(projectId)}/drafts/${draftVersion}/deliverable`,
    { method: 'POST', body: JSON.stringify(payload) },
  ),
  reviewDraft: (projectId, payload) => request(`${projectPath(projectId)}/reviews`, {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  publishDraft: (projectId, payload) => request(`${projectPath(projectId)}/publish`, {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
}
