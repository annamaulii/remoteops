<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { ApiError } from '../api/client'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const email = ref('')
const password = ref('')
const error = ref<string | null>(null)
const submitting = ref(false)

async function onSubmit(): Promise<void> {
  error.value = null
  submitting.value = true
  try {
    await auth.login(email.value, password.value)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    await router.push(redirect)
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : 'Login failed'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <form @submit.prevent="onSubmit">
    <h1>Log in</h1>
    <label>
      Email
      <input v-model="email" type="email" required autocomplete="username" />
    </label>
    <label>
      Password
      <input v-model="password" type="password" required autocomplete="current-password" />
    </label>
    <p v-if="error" role="alert">{{ error }}</p>
    <button type="submit" :disabled="submitting">Log in</button>
  </form>
</template>
