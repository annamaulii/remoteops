import { apiFetch } from './client'
import type { Token, UserCreate, UserRead } from './types'

export function register(data: UserCreate): Promise<UserRead> {
  return apiFetch<UserRead>('/users/register', { method: 'POST', body: data })
}

export function login(email: string, password: string): Promise<Token> {
  const formBody = new URLSearchParams({ username: email, password })
  return apiFetch<Token>('/auth/login', { method: 'POST', formBody })
}

export function refresh(refreshToken: string): Promise<Token> {
  return apiFetch<Token>('/auth/refresh', {
    method: 'POST',
    body: { refresh_token: refreshToken },
  })
}

export function logout(refreshToken: string): Promise<void> {
  return apiFetch<void>('/auth/logout', {
    method: 'POST',
    body: { refresh_token: refreshToken },
  })
}

export function me(accessToken: string): Promise<UserRead> {
  return apiFetch<UserRead>('/users/me', { token: accessToken })
}
