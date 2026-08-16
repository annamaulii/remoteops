import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from './auth'
import * as authApi from '../api/auth'

vi.mock('../api/auth')

const mockedAuthApi = vi.mocked(authApi)

describe('useAuthStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    sessionStorage.clear()
    vi.clearAllMocks()
  })

  it('starts unauthenticated with no stored refresh token', () => {
    const store = useAuthStore()

    expect(store.isAuthenticated).toBe(false)
    expect(store.refreshToken).toBeNull()
  })

  it('stores tokens and the current user after a successful login', async () => {
    mockedAuthApi.login.mockResolvedValue({
      access_token: 'access-1',
      refresh_token: 'refresh-1',
      token_type: 'bearer',
    })
    mockedAuthApi.me.mockResolvedValue({
      id: 'user-1',
      email: 'anna@example.com',
      created_at: '2026-01-01T00:00:00Z',
    })

    const store = useAuthStore()
    await store.login('anna@example.com', 'strong-password')

    expect(store.isAuthenticated).toBe(true)
    expect(store.accessToken).toBe('access-1')
    expect(store.user?.email).toBe('anna@example.com')
    expect(sessionStorage.getItem('remoteops.refresh_token')).toBe('refresh-1')
  })

  it('does not persist tokens if fetching the user fails after login', async () => {
    mockedAuthApi.login.mockResolvedValue({
      access_token: 'access-1',
      refresh_token: 'refresh-1',
      token_type: 'bearer',
    })
    mockedAuthApi.me.mockRejectedValue(new Error('network error'))

    const store = useAuthStore()
    await expect(store.login('anna@example.com', 'strong-password')).rejects.toThrow()

    expect(store.isAuthenticated).toBe(false)
    expect(store.accessToken).toBeNull()
    expect(sessionStorage.getItem('remoteops.refresh_token')).toBeNull()
  })

  it('clears session state on logout even if the API call fails', async () => {
    mockedAuthApi.login.mockResolvedValue({
      access_token: 'access-1',
      refresh_token: 'refresh-1',
      token_type: 'bearer',
    })
    mockedAuthApi.me.mockResolvedValue({
      id: 'user-1',
      email: 'anna@example.com',
      created_at: '2026-01-01T00:00:00Z',
    })
    mockedAuthApi.logout.mockRejectedValue(new Error('network error'))

    const store = useAuthStore()
    await store.login('anna@example.com', 'strong-password')
    await store.logout()

    expect(store.isAuthenticated).toBe(false)
    expect(store.user).toBeNull()
    expect(sessionStorage.getItem('remoteops.refresh_token')).toBeNull()
  })

  it('clears session state when restoring an invalid refresh token', async () => {
    sessionStorage.setItem('remoteops.refresh_token', 'stale-token')
    mockedAuthApi.refresh.mockRejectedValue(new Error('expired'))

    const store = useAuthStore()
    await store.restoreSession()

    expect(store.isAuthenticated).toBe(false)
    expect(sessionStorage.getItem('remoteops.refresh_token')).toBeNull()
  })
})
