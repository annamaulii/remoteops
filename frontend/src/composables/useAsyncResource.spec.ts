import { describe, expect, it, vi } from 'vitest'
import { useAsyncResource } from './useAsyncResource'
import { ApiError } from '../api/client'

describe('useAsyncResource', () => {
  it('transitions idle -> loading -> success with data', async () => {
    const fetcher = vi.fn().mockResolvedValue({ id: '1' })
    const resource = useAsyncResource(fetcher)

    expect(resource.status.value).toBe('idle')
    const promise = resource.execute()
    expect(resource.status.value).toBe('loading')
    await promise

    expect(resource.status.value).toBe('success')
    expect(resource.data.value).toEqual({ id: '1' })
    expect(resource.error.value).toBeNull()
  })

  it('transitions to error with the ApiError message on failure', async () => {
    const fetcher = vi.fn().mockRejectedValue(new ApiError(404, 'not_found', 'Not found', 'r1'))
    const resource = useAsyncResource(fetcher)

    await resource.execute()

    expect(resource.status.value).toBe('error')
    expect(resource.error.value).toBe('Not found')
  })

  it('retries by calling the fetcher again and can recover', async () => {
    const fetcher = vi
      .fn()
      .mockRejectedValueOnce(new ApiError(500, 'internal_error', 'Server error', 'r1'))
      .mockResolvedValueOnce({ id: '2' })
    const resource = useAsyncResource(fetcher)

    await resource.execute()
    expect(resource.status.value).toBe('error')

    await resource.execute()

    expect(resource.status.value).toBe('success')
    expect(resource.data.value).toEqual({ id: '2' })
    expect(fetcher).toHaveBeenCalledTimes(2)
  })
})
