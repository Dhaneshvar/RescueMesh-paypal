const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8001'

export async function api(path, options = {}) {
  const response = await fetch(`${API}${path}`, { headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }, ...options })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.detail || body.error || 'Request failed')
  return body
}

