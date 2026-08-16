import { apiFetch } from './client'
import type { ContractorCreate, ContractorRead, Page, ProjectCreate, ProjectRead } from './types'

export function listProjects(token: string, organizationId: string): Promise<Page<ProjectRead>> {
  return apiFetch<Page<ProjectRead>>(`/organizations/${organizationId}/projects`, { token })
}

export function createProject(
  token: string,
  organizationId: string,
  data: ProjectCreate,
): Promise<ProjectRead> {
  return apiFetch<ProjectRead>(`/organizations/${organizationId}/projects`, {
    method: 'POST',
    body: data,
    token,
  })
}

export function listContractors(
  token: string,
  organizationId: string,
): Promise<Page<ContractorRead>> {
  return apiFetch<Page<ContractorRead>>(`/organizations/${organizationId}/contractors`, {
    token,
  })
}

export function createContractor(
  token: string,
  organizationId: string,
  data: ContractorCreate,
): Promise<ContractorRead> {
  return apiFetch<ContractorRead>(`/organizations/${organizationId}/contractors`, {
    method: 'POST',
    body: data,
    token,
  })
}
