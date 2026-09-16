import { afterEach, describe, expect, it, vi } from 'vitest'
import { getCurrentUser, logout } from './auth'
import { fetchWithAuth } from './client'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('authenticated API client', () => {
  it('adds the decoded CSRF token to state-changing requests', async () => {
    vi.stubGlobal('document', { cookie: 'XSRF-TOKEN=token%2Fvalue' })
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await fetchWithAuth('/api/example', { method: 'POST' })

    expect(fetchMock).toHaveBeenCalledWith('/api/example', {
      method: 'POST',
      headers: { 'X-XSRF-TOKEN': 'token/value' },
    })
  })

  it('treats an unauthenticated current-user response as unauthorized', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(null, { status: 401 })),
    )

    await expect(getCurrentUser()).rejects.toThrow('UNAUTHORIZED')
  })

  it('uses a state-changing request for logout', async () => {
    vi.stubGlobal('document', { cookie: 'XSRF-TOKEN=logout-token' })
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await logout()

    expect(fetchMock).toHaveBeenCalledWith('/api/auth/logout', {
      method: 'POST',
      headers: { 'X-XSRF-TOKEN': 'logout-token' },
    })
  })
})
