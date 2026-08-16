import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '../stores/auth'
import router from './index'

describe('router auth guard', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    sessionStorage.clear()
    await router.push('/login')
  })

  it('redirects unauthenticated visitors away from protected routes', async () => {
    await router.push('/')

    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/')
  })

  it('lets authenticated users reach protected routes', async () => {
    const auth = useAuthStore()
    auth.accessToken = 'access-1'

    await router.push('/')

    expect(router.currentRoute.value.name).toBe('dashboard')
  })

  it('redirects authenticated users away from the login page', async () => {
    const auth = useAuthStore()
    auth.accessToken = 'access-1'
    await router.push('/')

    await router.push('/login')

    expect(router.currentRoute.value.name).toBe('dashboard')
  })
})
