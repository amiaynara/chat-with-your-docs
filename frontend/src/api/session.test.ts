import { afterEach, describe, expect, it, vi } from 'vitest'
import { resetSession, ResetSessionError } from './session'

describe('resetSession', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('posts to /session/reset with credentials included', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal('fetch', fetchMock)

    await resetSession()

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('http://localhost:8000/session/reset')
    expect(init).toEqual({ method: 'POST', credentials: 'include' })
  })

  it('throws when the response is not ok', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500 }))

    await expect(resetSession()).rejects.toThrow(ResetSessionError)
  })
})
