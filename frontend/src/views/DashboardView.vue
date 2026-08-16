<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()

async function onLogout(): Promise<void> {
  await auth.logout()
  await router.push({ name: 'login' })
}
</script>

<template>
  <div>
    <p v-if="auth.user">Logged in as {{ auth.user.email }}</p>
    <button type="button" @click="onLogout">Log out</button>
  </div>
</template>
