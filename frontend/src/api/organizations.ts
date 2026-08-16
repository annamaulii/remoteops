import { apiFetch } from './client'
import type { OrganizationCreate, OrganizationRead, Page } from './types'

export function listOrganizations(token: string): Promise<Page<OrganizationRead>> {
  return apiFetch<Page<OrganizationRead>>('/organizations', { token })
}

export function createOrganization(
  token: string,
  data: OrganizationCreate,
): Promise<OrganizationRead> {
  return apiFetch<OrganizationRead>('/organizations', { method: 'POST', body: data, token })
}
