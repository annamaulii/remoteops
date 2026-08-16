import type { ApiErrorBody } from './types'

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly requestId: string

  constructor(status: number, code: string, message: string, requestId: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.requestId = requestId
  }
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  body?: unknown
  token?: string
  formBody?: URLSearchParams
}

/** Minimal typed fetch wrapper for the RemoteOps API's consistent error envelope. */
export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {}
  if (options.token) {
    headers.Authorization = `Bearer ${options.token}`
  }

  let body: BodyInit | undefined
  if (options.formBody) {
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
    body = options.formBody
  } else if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.body)
  }

  const response = await fetch(`${BASE_URL}${path}`, {
    method: options.method ?? 'GET',
    headers,
    body,
  })

  if (response.status === 204) {
    return undefined as T
  }

  const data: unknown = await response.json().catch(() => null)

  if (!response.ok) {
    const errorBody = data as ApiErrorBody | null
    throw new ApiError(
      response.status,
      errorBody?.error?.code ?? 'unknown_error',
      errorBody?.error?.message ?? response.statusText,
      errorBody?.error?.request_id ?? '',
    )
  }

  return data as T
}
