<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useAsyncResource } from '../composables/useAsyncResource'
import { createOrganization, listOrganizations } from '../api/organizations'
import type { OrganizationRead, Page } from '../api/types'
import { ApiError } from '../api/client'

const auth = useAuthStore()
const router = useRouter()

const { status, data, error, execute } = useAsyncResource<Page<OrganizationRead>>(() =>
  auth.withAuth((token) => listOrganizations(token)),
)

const newOrgName = ref('')
const createError = ref<string | null>(null)
const creating = ref(false)

async function onCreateOrganization(): Promise<void> {
  createError.value = null
  creating.value = true
  try {
    await auth.withAuth((token) => createOrganization(token, { name: newOrgName.value }))
    newOrgName.value = ''
    await execute()
  } catch (err) {
    createError.value = err instanceof ApiError ? err.message : 'Could not create organization'
  } finally {
    creating.value = false
  }
}

async function onLogout(): Promise<void> {
  await auth.logout()
  await router.push({ name: 'login' })
}

onMounted(execute)
</script>

<template>
  <main>
    <header>
      <h1>Organizations</h1>
      <p v-if="auth.user">Logged in as {{ auth.user.email }}</p>
      <button type="button" @click="onLogout">Log out</button>
    </header>

    <section aria-label="Create organization">
      <form @submit.prevent="onCreateOrganization">
        <label>
          New organization name
          <input v-model="newOrgName" required maxlength="255" />
        </label>
        <button type="submit" :disabled="creating">Create</button>
      </form>
      <p v-if="createError" role="alert">{{ createError }}</p>
    </section>

    <section aria-label="Your organizations">
      <p v-if="status === 'loading'" aria-busy="true">Loading organizations…</p>
      <div v-else-if="status === 'error'">
        <p role="alert">{{ error }}</p>
        <button type="button" @click="execute">Retry</button>
      </div>
      <p v-else-if="status === 'success' && data?.items.length === 0">
        No organizations yet. Create one above to get started.
      </p>
      <ul v-else-if="data">
        <li v-for="org in data.items" :key="org.id">
          <RouterLink :to="{ name: 'organization', params: { id: org.id } }">
            {{ org.name }}
          </RouterLink>
        </li>
      </ul>
    </section>
  </main>
</template>
