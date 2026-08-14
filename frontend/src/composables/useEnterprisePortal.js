import { computed, ref } from 'vue'

const roleOptions = [
  { userId: 'user-procurement-owner', label: '采购业务负责人' },
  { userId: 'user-legal-finance', label: '法务财务复核' },
  { userId: 'user-quality', label: '供应商质量管理' },
  { userId: 'user-observer', label: '受限观察员' },
  { userId: 'user-quality-temp', label: '临时质量用户' },
]

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  let body
  try {
    body = await response.json()
  } catch {
    throw new Error(`服务返回了不可解析的响应（HTTP ${response.status}）`)
  }
  if (!response.ok) {
    throw new Error(body.detail || `请求失败（HTTP ${response.status}）`)
  }
  return body
}

function toApiTime(value) {
  if (!value) return value
  if (/[+-]\d{2}:\d{2}$/.test(value) || value.endsWith('Z')) return value
  return `${value.length === 16 ? value : value.slice(0, 16)}:00+08:00`
}

export function useEnterprisePortal() {
  const projects = ref([])
  const selectedProjectId = ref('PRJ-TENDER-001')
  const selectedUserId = ref('user-procurement-owner')
  const asOf = ref('2026-10-30T23:59')
  const dashboard = ref(null)
  const loading = ref(false)
  const error = ref('')
  const assistantLoading = ref(false)
  const assistantMessages = ref([
    {
      role: 'assistant',
      content: '你好，我会通过MCP调用同一套企业招采知识服务。你可以询问需求版本、供应商风险、文档审查或生成方案。',
      citations: [],
      toolName: '',
    },
  ])

  const selectedProject = computed(() =>
    projects.value.find((project) => project.project_id === selectedProjectId.value),
  )
  const selectedRole = computed(() =>
    roleOptions.find((role) => role.userId === selectedUserId.value),
  )
  const solutionBundle = computed(() => dashboard.value?.solution_bundle || null)

  async function loadProjects() {
    const body = await requestJson('/enterprise/projects')
    projects.value = body.projects || []
  }

  async function loadDashboard() {
    loading.value = true
    error.value = ''
    try {
      if (!projects.value.length) await loadProjects()
      const params = new URLSearchParams({
        user_id: selectedUserId.value,
        as_of: toApiTime(asOf.value),
      })
      dashboard.value = await requestJson(
        `/enterprise/projects/${encodeURIComponent(selectedProjectId.value)}/dashboard?${params}`,
      )
    } catch (reason) {
      dashboard.value = null
      error.value = reason instanceof Error ? reason.message : String(reason)
    } finally {
      loading.value = false
    }
  }

  async function selectProject(projectId) {
    selectedProjectId.value = projectId
    await loadDashboard()
  }

  async function updateViewer() {
    await loadDashboard()
  }

  async function askAssistant(message) {
    const content = message.trim()
    if (!content || assistantLoading.value) return
    assistantMessages.value.push({ role: 'user', content, citations: [], toolName: '' })
    assistantLoading.value = true
    try {
      const response = await requestJson('/enterprise/assistant', {
        method: 'POST',
        body: JSON.stringify({
          project_id: selectedProjectId.value,
          user_id: selectedUserId.value,
          as_of: toApiTime(asOf.value),
          message: content,
        }),
      })
      assistantMessages.value.push({
        role: 'assistant',
        content: response.answer,
        citations: response.citations || [],
        toolName: response.tool_name || '',
      })
      if (response.solution_bundle && dashboard.value) {
        dashboard.value = { ...dashboard.value, solution_bundle: response.solution_bundle }
      }
    } catch (reason) {
      assistantMessages.value.push({
        role: 'assistant',
        content: `服务调用失败：${reason instanceof Error ? reason.message : String(reason)}`,
        citations: [],
        toolName: 'error',
      })
    } finally {
      assistantLoading.value = false
    }
  }

  return {
    roleOptions,
    projects,
    selectedProject,
    selectedProjectId,
    selectedRole,
    selectedUserId,
    asOf,
    dashboard,
    solutionBundle,
    loading,
    error,
    assistantLoading,
    assistantMessages,
    loadDashboard,
    selectProject,
    updateViewer,
    askAssistant,
  }
}
