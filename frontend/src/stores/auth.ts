import { defineStore } from 'pinia'
import { login as apiLogin, logout as apiLogout, me as apiMe, refresh as apiRefresh } from '../api/auth'
import { ApiError } from '../api/client'
import type { UserRead } from '../api/types'

// Token handling: the access token lives only in memory (Pinia state) and is
// never written to storage, so it cannot be read back after a reload or by
// another tab. The refresh token is kept in sessionStorage rather than
// localStorage so it does not outlive the browser tab. Neither is immune to
// XSS reading in-page JS state; the backend issues bearer tokens rather than
// httpOnly cookies, so that stronger guarantee isn't available without a
// backend change out of scope for this increment.
const REFRESH_TOKEN_KEY = 'remoteops.refresh_token'

interface AuthState {
  accessToken: string | null
  refreshToken: string | null
  user: UserRead | null
}

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({
    accessToken: null,
    refreshToken: sessionStorage.getItem(REFRESH_TOKEN_KEY),
    user: null,
  }),

  getters: {
    isAuthenticated: (state): boolean => state.accessToken !== null,
  },

  actions: {
    setTokens(accessToken: string, refreshToken: string) {
      this.accessToken = accessToken
      this.refreshToken = refreshToken
      sessionStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
    },

    clearTokens() {
      this.accessToken = null
      this.refreshToken = null
      this.user = null
      sessionStorage.removeItem(REFRESH_TOKEN_KEY)
    },

    async login(email: string, password: string): Promise<void> {
      const token = await apiLogin(email, password)
      try {
        this.user = await apiMe(token.access_token)
      } catch (error) {
        this.clearTokens()
        throw error
      }
      this.setTokens(token.access_token, token.refresh_token)
    },

    async logout(): Promise<void> {
      if (this.refreshToken) {
        await apiLogout(this.refreshToken).catch(() => undefined)
      }
      this.clearTokens()
    },

    /** Exchange a stored refresh token for a fresh session on app startup. */
    async restoreSession(): Promise<void> {
      if (!this.refreshToken) {
        return
      }
      try {
        const token = await apiRefresh(this.refreshToken)
        this.setTokens(token.access_token, token.refresh_token)
        this.user = await apiMe(token.access_token)
      } catch {
        this.clearTokens()
      }
    },

    /**
     * Run an authenticated call, retrying once via a session refresh if the
     * access token expired mid-session. Clears the session if that also fails.
     */
    async withAuth<T>(fn: (token: string) => Promise<T>): Promise<T> {
      if (!this.accessToken) {
        throw new ApiError(401, 'unauthorized', 'Not authenticated', '')
      }
      try {
        return await fn(this.accessToken)
      } catch (error) {
        if (error instanceof ApiError && error.status === 401 && this.refreshToken) {
          await this.restoreSession()
          if (this.accessToken) {
            return await fn(this.accessToken)
          }
        }
        throw error
      }
    },
  },
})
