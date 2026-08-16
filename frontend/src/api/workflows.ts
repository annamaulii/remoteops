import { apiFetch } from './client'
import type { ApprovalRead, DecisionCreate, Page, WorkLogCreate, WorkLogRead } from './types'

export function listWorkLogs(
  token: string,
  organizationId: string,
): Promise<Page<WorkLogRead>> {
  return apiFetch<Page<WorkLogRead>>(`/organizations/${organizationId}/work-logs`, { token })
}

export function createWorkLog(
  token: string,
  organizationId: string,
  data: WorkLogCreate,
): Promise<WorkLogRead> {
  return apiFetch<WorkLogRead>(`/organizations/${organizationId}/work-logs`, {
    method: 'POST',
    body: data,
    token,
  })
}

export function decideWorkLog(
  token: string,
  organizationId: string,
  workLogId: string,
  data: DecisionCreate,
): Promise<ApprovalRead> {
  return apiFetch<ApprovalRead>(
    `/organizations/${organizationId}/work-logs/${workLogId}/decision`,
    { method: 'POST', body: data, token },
  )
}
