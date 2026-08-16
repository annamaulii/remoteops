<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useAsyncResource } from '../composables/useAsyncResource'
import { createContractor, createProject, listContractors, listProjects } from '../api/resources'
import { createWorkLog, decideWorkLog, listWorkLogs } from '../api/workflows'
import type {
  ContractorRead,
  Page,
  ProjectRead,
  WorkLogRead,
} from '../api/types'
import { ApiError } from '../api/client'

const route = useRoute()
const auth = useAuthStore()
const organizationId = computed(() => route.params.id as string)

const projects = useAsyncResource<Page<ProjectRead>>(() =>
  auth.withAuth((token) => listProjects(token, organizationId.value)),
)
const contractors = useAsyncResource<Page<ContractorRead>>(() =>
  auth.withAuth((token) => listContractors(token, organizationId.value)),
)
const workLogs = useAsyncResource<Page<WorkLogRead>>(() =>
  auth.withAuth((token) => listWorkLogs(token, organizationId.value)),
)

function projectName(id: string): string {
  return projects.data.value?.items.find((p) => p.id === id)?.name ?? id
}
function contractorName(id: string): string {
  return contractors.data.value?.items.find((c) => c.id === id)?.name ?? id
}

// --- Create project ---
const newProjectName = ref('')
const projectError = ref<string | null>(null)
const creatingProject = ref(false)

async function onCreateProject(): Promise<void> {
  projectError.value = null
  creatingProject.value = true
  try {
    await auth.withAuth((token) =>
      createProject(token, organizationId.value, { name: newProjectName.value }),
    )
    newProjectName.value = ''
    await projects.execute()
  } catch (err) {
    projectError.value = err instanceof ApiError ? err.message : 'Could not create project'
  } finally {
    creatingProject.value = false
  }
}

// --- Create contractor ---
const newContractorName = ref('')
const newContractorEmail = ref('')
const contractorError = ref<string | null>(null)
const creatingContractor = ref(false)

async function onCreateContractor(): Promise<void> {
  contractorError.value = null
  creatingContractor.value = true
  try {
    await auth.withAuth((token) =>
      createContractor(token, organizationId.value, {
        name: newContractorName.value,
        email: newContractorEmail.value,
      }),
    )
    newContractorName.value = ''
    newContractorEmail.value = ''
    await contractors.execute()
  } catch (err) {
    contractorError.value = err instanceof ApiError ? err.message : 'Could not create contractor'
  } finally {
    creatingContractor.value = false
  }
}

// --- Create work log ---
const newWorkLogProjectId = ref('')
const newWorkLogContractorId = ref('')
const newWorkLogDate = ref('')
const newWorkLogMinutes = ref(60)
const newWorkLogDescription = ref('')
const workLogError = ref<string | null>(null)
const creatingWorkLog = ref(false)

const canCreateWorkLog = computed(
  () => (projects.data.value?.items.length ?? 0) > 0 && (contractors.data.value?.items.length ?? 0) > 0,
)

async function onCreateWorkLog(): Promise<void> {
  workLogError.value = null
  creatingWorkLog.value = true
  try {
    await auth.withAuth((token) =>
      createWorkLog(token, organizationId.value, {
        project_id: newWorkLogProjectId.value,
        contractor_id: newWorkLogContractorId.value,
        work_date: newWorkLogDate.value,
        minutes: newWorkLogMinutes.value,
        description: newWorkLogDescription.value,
      }),
    )
    newWorkLogDate.value = ''
    newWorkLogMinutes.value = 60
    newWorkLogDescription.value = ''
    await workLogs.execute()
  } catch (err) {
    workLogError.value = err instanceof ApiError ? err.message : 'Could not create work log'
  } finally {
    creatingWorkLog.value = false
  }
}

// --- Approve / reject ---
const decidingId = ref<string | null>(null)
const decisionError = ref<string | null>(null)

async function onDecide(workLogId: string, decision: 'approved' | 'rejected'): Promise<void> {
  decisionError.value = null
  decidingId.value = workLogId
  try {
    await auth.withAuth((token) =>
      decideWorkLog(token, organizationId.value, workLogId, { decision }),
    )
    await workLogs.execute()
  } catch (err) {
    decisionError.value = err instanceof ApiError ? err.message : 'Could not record decision'
  } finally {
    decidingId.value = null
  }
}

onMounted(() => {
  void projects.execute()
  void contractors.execute()
  void workLogs.execute()
})
</script>

<template>
  <main>
    <RouterLink :to="{ name: 'dashboard' }">&larr; Organizations</RouterLink>

    <section aria-label="Projects">
      <h2>Projects</h2>
      <form @submit.prevent="onCreateProject">
        <label>
          New project name
          <input v-model="newProjectName" required maxlength="255" />
        </label>
        <button type="submit" :disabled="creatingProject">Add project</button>
      </form>
      <p v-if="projectError" role="alert">{{ projectError }}</p>

      <p v-if="projects.status.value === 'loading'" aria-busy="true">Loading projects…</p>
      <div v-else-if="projects.status.value === 'error'">
        <p role="alert">{{ projects.error.value }}</p>
        <button type="button" @click="projects.execute">Retry</button>
      </div>
      <p v-else-if="projects.data.value?.items.length === 0">No projects yet.</p>
      <ul v-else-if="projects.data.value">
        <li v-for="project in projects.data.value.items" :key="project.id">
          {{ project.name }}
        </li>
      </ul>
    </section>

    <section aria-label="Contractors">
      <h2>Contractors</h2>
      <form @submit.prevent="onCreateContractor">
        <label>
          Name
          <input v-model="newContractorName" required maxlength="255" />
        </label>
        <label>
          Email
          <input v-model="newContractorEmail" type="email" required />
        </label>
        <button type="submit" :disabled="creatingContractor">Add contractor</button>
      </form>
      <p v-if="contractorError" role="alert">{{ contractorError }}</p>

      <p v-if="contractors.status.value === 'loading'" aria-busy="true">Loading contractors…</p>
      <div v-else-if="contractors.status.value === 'error'">
        <p role="alert">{{ contractors.error.value }}</p>
        <button type="button" @click="contractors.execute">Retry</button>
      </div>
      <p v-else-if="contractors.data.value?.items.length === 0">No contractors yet.</p>
      <ul v-else-if="contractors.data.value">
        <li v-for="contractor in contractors.data.value.items" :key="contractor.id">
          {{ contractor.name }} ({{ contractor.email }})
        </li>
      </ul>
    </section>

    <section aria-label="Work logs">
      <h2>Work logs</h2>
      <form v-if="canCreateWorkLog" @submit.prevent="onCreateWorkLog">
        <label>
          Project
          <select v-model="newWorkLogProjectId" required>
            <option value="" disabled>Select a project</option>
            <option v-for="project in projects.data.value?.items" :key="project.id" :value="project.id">
              {{ project.name }}
            </option>
          </select>
        </label>
        <label>
          Contractor
          <select v-model="newWorkLogContractorId" required>
            <option value="" disabled>Select a contractor</option>
            <option
              v-for="contractor in contractors.data.value?.items"
              :key="contractor.id"
              :value="contractor.id"
            >
              {{ contractor.name }}
            </option>
          </select>
        </label>
        <label>
          Date
          <input v-model="newWorkLogDate" type="date" required />
        </label>
        <label>
          Minutes
          <input v-model.number="newWorkLogMinutes" type="number" min="1" max="1440" required />
        </label>
        <label>
          Description
          <input v-model="newWorkLogDescription" maxlength="2000" />
        </label>
        <button type="submit" :disabled="creatingWorkLog">Log work</button>
      </form>
      <p v-else>Add at least one project and one contractor before logging work.</p>
      <p v-if="workLogError" role="alert">{{ workLogError }}</p>
      <p v-if="decisionError" role="alert">{{ decisionError }}</p>

      <p v-if="workLogs.status.value === 'loading'" aria-busy="true">Loading work logs…</p>
      <div v-else-if="workLogs.status.value === 'error'">
        <p role="alert">{{ workLogs.error.value }}</p>
        <button type="button" @click="workLogs.execute">Retry</button>
      </div>
      <p v-else-if="workLogs.data.value?.items.length === 0">No work logs yet.</p>
      <table v-else-if="workLogs.data.value">
        <thead>
          <tr>
            <th scope="col">Date</th>
            <th scope="col">Project</th>
            <th scope="col">Contractor</th>
            <th scope="col">Minutes</th>
            <th scope="col">Status</th>
            <th scope="col">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="log in workLogs.data.value.items" :key="log.id">
            <td>{{ log.work_date }}</td>
            <td>{{ projectName(log.project_id) }}</td>
            <td>{{ contractorName(log.contractor_id) }}</td>
            <td>{{ log.minutes }}</td>
            <td>{{ log.status }}</td>
            <td>
              <template v-if="log.status === 'submitted'">
                <button
                  type="button"
                  :disabled="decidingId === log.id"
                  @click="onDecide(log.id, 'approved')"
                >
                  Approve
                </button>
                <button
                  type="button"
                  :disabled="decidingId === log.id"
                  @click="onDecide(log.id, 'rejected')"
                >
                  Reject
                </button>
              </template>
            </td>
          </tr>
        </tbody>
      </table>
    </section>
  </main>
</template>
