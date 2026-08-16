import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiFetch, ApiError } from './client'

describe('apiFetch', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('returns parsed JSON on success', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ id: '1' }), { status: 200 }),
      ),
    )

    const result = await apiFetch<{ id: string }>('/users/me')

    expect(result).toEqual({ id: '1' })
  })

  it('sends the bearer token when provided', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({}), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await apiFetch('/users/me', { token: 'abc123' })

    const [, init] = fetchMock.mock.calls[0]
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer abc123')
  })

  it('throws ApiError with the backend error envelope on failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: { code: 'http_error', message: 'Not found', request_id: 'req-1' },
          }),
          { status: 404 },
        ),
      ),
    )

    await expect(apiFetch('/organizations/missing')).rejects.toMatchObject({
      status: 404,
      code: 'http_error',
      message: 'Not found',
      requestId: 'req-1',
    })
  })

  it('returns undefined for 204 responses', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))

    const result = await apiFetch('/auth/logout', { method: 'POST' })

    expect(result).toBeUndefined()
  })

  it('is an instance of ApiError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(JSON.stringify({}), { status: 500 })),
    )

    await expect(apiFetch('/anything')).rejects.toBeInstanceOf(ApiError)
  })
})
