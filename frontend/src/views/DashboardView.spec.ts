import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import DashboardView from './DashboardView.vue'
import { useAuthStore } from '../stores/auth'
import * as organizationsApi from '../api/organizations'
import { ApiError } from '../api/client'

vi.mock('../api/organizations')
const mockedApi = vi.mocked(organizationsApi)

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'dashboard', component: DashboardView },
      { path: '/login', name: 'login', component: { template: '<div />' } },
      { path: '/organizations/:id', name: 'organization', component: { template: '<div />' } },
    ],
  })
}

async function mountDashboard() {
  const router = makeRouter()
  router.push('/')
  await router.isReady()
  const wrapper = mount(DashboardView, { global: { plugins: [router] } })
  await wrapper.vm.$nextTick()
  return wrapper
}

describe('DashboardView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    const auth = useAuthStore()
    auth.accessToken = 'access-1'
    vi.clearAllMocks()
  })

  it('shows an empty state when there are no organizations', async () => {
    mockedApi.listOrganizations.mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 })

    const wrapper = await mountDashboard()
    await flushPromises()

    expect(wrapper.text()).toContain('No organizations yet')
  })

  it('lists organizations returned by the API', async () => {
    mockedApi.listOrganizations.mockResolvedValue({
      items: [{ id: 'org-1', name: 'Acme', created_at: '2026-01-01T00:00:00Z' }],
      total: 1,
      limit: 20,
      offset: 0,
    })

    const wrapper = await mountDashboard()
    await flushPromises()

    expect(wrapper.text()).toContain('Acme')
  })

  it('shows a retry button on error and recovers on retry', async () => {
    mockedApi.listOrganizations
      .mockRejectedValueOnce(new ApiError(500, 'internal_error', 'Server error', 'r1'))
      .mockResolvedValueOnce({ items: [], total: 0, limit: 20, offset: 0 })

    const wrapper = await mountDashboard()
    await flushPromises()
    expect(wrapper.text()).toContain('Server error')

    const retryButton = wrapper.findAll('button').find((b) => b.text() === 'Retry')
    await retryButton?.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('No organizations yet')
  })

  it('creates an organization and refreshes the list', async () => {
    mockedApi.listOrganizations.mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 })
    mockedApi.createOrganization.mockResolvedValue({
      id: 'org-2',
      name: 'New Org',
      created_at: '2026-01-01T00:00:00Z',
    })

    const wrapper = await mountDashboard()
    await flushPromises()

    await wrapper.find('input').setValue('New Org')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(mockedApi.createOrganization).toHaveBeenCalledWith('access-1', { name: 'New Org' })
    expect(mockedApi.listOrganizations).toHaveBeenCalledTimes(2)
  })

  it('shows a validation error message if creation fails', async () => {
    mockedApi.listOrganizations.mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 })
    mockedApi.createOrganization.mockRejectedValue(
      new ApiError(409, 'http_error', 'Organization name already exists', 'r1'),
    )

    const wrapper = await mountDashboard()
    await flushPromises()

    await wrapper.find('input').setValue('Acme')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(wrapper.text()).toContain('Organization name already exists')
  })
})

function flushPromises(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0))
}
