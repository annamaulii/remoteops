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

export interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

export interface OrganizationRead {
  id: string
  name: string
  created_at: string
}

export interface OrganizationCreate {
  name: string
}

export interface ProjectRead {
  id: string
  organization_id: string
  name: string
  description: string
  created_at: string
}

export interface ProjectCreate {
  name: string
  description?: string
}

export interface ContractorRead {
  id: string
  organization_id: string
  name: string
  email: string
  created_at: string
}

export interface ContractorCreate {
  name: string
  email: string
}

export type WorkLogStatus = 'submitted' | 'approved' | 'rejected'

export interface WorkLogRead {
  id: string
  organization_id: string
  contractor_id: string
  project_id: string
  work_date: string
  minutes: number
  description: string
  status: WorkLogStatus
  created_at: string
}

export interface WorkLogCreate {
  contractor_id: string
  project_id: string
  work_date: string
  minutes: number
  description?: string
}

export type Decision = 'approved' | 'rejected'

export interface DecisionCreate {
  decision: Decision
  note?: string
}

export interface ApprovalRead {
  id: string
  leave_request_id: string | null
  work_log_id: string | null
  reviewer_user_id: string
  decision: Decision
  note: string
  created_at: string
}
