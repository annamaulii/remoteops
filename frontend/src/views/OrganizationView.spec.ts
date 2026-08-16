import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import OrganizationView from './OrganizationView.vue'
import { useAuthStore } from '../stores/auth'
import * as resourcesApi from '../api/resources'
import * as workflowsApi from '../api/workflows'
import { ApiError } from '../api/client'

vi.mock('../api/resources')
vi.mock('../api/workflows')
const mockedResources = vi.mocked(resourcesApi)
const mockedWorkflows = vi.mocked(workflowsApi)

const project = {
  id: 'project-1',
  organization_id: 'org-1',
  name: 'Launch',
  description: '',
  created_at: '2026-01-01T00:00:00Z',
}
const contractor = {
  id: 'contractor-1',
  organization_id: 'org-1',
  name: 'Ada',
  email: 'ada@example.com',
  created_at: '2026-01-01T00:00:00Z',
}
const submittedWorkLog = {
  id: 'log-1',
  organization_id: 'org-1',
  contractor_id: 'contractor-1',
  project_id: 'project-1',
  work_date: '2026-01-05',
  minutes: 120,
  description: '',
  status: 'submitted' as const,
  created_at: '2026-01-05T00:00:00Z',
}

async function mountOrganizationView() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'dashboard', component: { template: '<div />' } },
      { path: '/organizations/:id', name: 'organization', component: OrganizationView },
    ],
  })
  router.push('/organizations/org-1')
  await router.isReady()
  const wrapper = mount(OrganizationView, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

function flushPromises(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0))
}

describe('OrganizationView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    const auth = useAuthStore()
    auth.accessToken = 'access-1'
    vi.clearAllMocks()
    mockedResources.listProjects.mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 })
    mockedResources.listContractors.mockResolvedValue({
      items: [],
      total: 0,
      limit: 20,
      offset: 0,
    })
    mockedWorkflows.listWorkLogs.mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 })
  })

  it('shows empty states when nothing exists yet', async () => {
    const wrapper = await mountOrganizationView()

    expect(wrapper.text()).toContain('No projects yet')
    expect(wrapper.text()).toContain('No contractors yet')
    expect(wrapper.text()).toContain('No work logs yet')
    expect(wrapper.text()).toContain('Add at least one project and one contractor')
  })

  it('lists projects, contractors, and work logs', async () => {
    mockedResources.listProjects.mockResolvedValue({
      items: [project],
      total: 1,
      limit: 20,
      offset: 0,
    })
    mockedResources.listContractors.mockResolvedValue({
      items: [contractor],
      total: 1,
      limit: 20,
      offset: 0,
    })
    mockedWorkflows.listWorkLogs.mockResolvedValue({
      items: [submittedWorkLog],
      total: 1,
      limit: 20,
      offset: 0,
    })

    const wrapper = await mountOrganizationView()

    expect(wrapper.text()).toContain('Launch')
    expect(wrapper.text()).toContain('Ada')
    expect(wrapper.text()).toContain('120')
  })

  it('creates a project and refreshes the list', async () => {
    mockedResources.createProject.mockResolvedValue(project)
    const wrapper = await mountOrganizationView()

    await wrapper.find('input').setValue('Launch')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(mockedResources.createProject).toHaveBeenCalledWith('access-1', 'org-1', {
      name: 'Launch',
    })
    expect(mockedResources.listProjects).toHaveBeenCalledTimes(2)
  })

  it('approves a submitted work log', async () => {
    mockedResources.listProjects.mockResolvedValue({
      items: [project],
      total: 1,
      limit: 20,
      offset: 0,
    })
    mockedResources.listContractors.mockResolvedValue({
      items: [contractor],
      total: 1,
      limit: 20,
      offset: 0,
    })
    mockedWorkflows.listWorkLogs.mockResolvedValue({
      items: [submittedWorkLog],
      total: 1,
      limit: 20,
      offset: 0,
    })
    mockedWorkflows.decideWorkLog.mockResolvedValue({
      id: 'approval-1',
      leave_request_id: null,
      work_log_id: 'log-1',
      reviewer_user_id: 'user-1',
      decision: 'approved',
      note: '',
      created_at: '2026-01-06T00:00:00Z',
    })

    const wrapper = await mountOrganizationView()
    const approveButton = wrapper.findAll('button').find((b) => b.text() === 'Approve')
    await approveButton?.trigger('click')
    await flushPromises()

    expect(mockedWorkflows.decideWorkLog).toHaveBeenCalledWith('access-1', 'org-1', 'log-1', {
      decision: 'approved',
    })
    expect(mockedWorkflows.listWorkLogs).toHaveBeenCalledTimes(2)
  })

  it('shows an error and retry control when work logs fail to load', async () => {
    mockedWorkflows.listWorkLogs.mockRejectedValueOnce(
      new ApiError(500, 'internal_error', 'Server error', 'r1'),
    )

    const wrapper = await mountOrganizationView()

    expect(wrapper.text()).toContain('Server error')
    expect(wrapper.findAll('button').some((b) => b.text() === 'Retry')).toBe(true)
  })
})
