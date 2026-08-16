// Typed contracts mirroring remoteops/users.py's Pydantic request/response models.

export interface UserRead {
  id: string
  email: string
  created_at: string
}

export interface Token {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface UserCreate {
  email: string
  password: string
}

export interface ApiErrorBody {
  error: {
    code: string
    message: string
    request_id: string
  }
}
