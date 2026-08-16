import { ref } from 'vue'
import { ApiError } from '../api/client'

export type AsyncStatus = 'idle' | 'loading' | 'success' | 'error'

/** Tracks loading/success/error state for a fetch and exposes a retry-friendly execute(). */
export function useAsyncResource<T>(fetcher: () => Promise<T>) {
  const status = ref<AsyncStatus>('idle')
  const data = ref<T | null>(null)
  const error = ref<string | null>(null)

  async function execute(): Promise<void> {
    status.value = 'loading'
    error.value = null
    try {
      data.value = await fetcher()
      status.value = 'success'
    } catch (err) {
      error.value = err instanceof ApiError ? err.message : 'Something went wrong'
      status.value = 'error'
    }
  }

  return { status, data, error, execute }
}
