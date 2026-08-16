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
  const knowledgeQuery = ref('')
  const knowledgeResults = ref([])
  const knowledgeMeta = ref(null)
  const knowledgeLoading = ref(false)
  const knowledgeError = ref('')
  const mcpTools = ref([])
  const selectedMcpToolName = ref('')
  const mcpArguments = ref({})
  const mcpResult = ref(null)
  const mcpLoading = ref(false)
  const mcpError = ref('')
  const mcpConnected = ref(false)
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
  const selectedMcpTool = computed(() =>
    mcpTools.value.find((tool) => tool.name === selectedMcpToolName.value) || null,
  )

  let mcpRequestId = 100

  async function callMcp(method, params = {}) {
    mcpRequestId += 1
    const response = await requestJson('/mcp', {
      method: 'POST',
      body: JSON.stringify({ jsonrpc: '2.0', id: mcpRequestId, method, params }),
    })
    if (response.error) {
      throw new Error(`MCP ${response.error.code}：${response.error.message}`)
    }
    return response.result
  }

  function defaultRequirementId() {
    return {
      'PRJ-TENDER-001': 'REQ-BAT-001',
      'PRJ-AUTO-001': 'REQ-AUTO-001',
      'PRJ-KM-001': 'REQ-001',
    }[selectedProjectId.value] || ''
  }

  function defaultMcpArgument(name, schema) {
    if (name === 'project_id') return selectedProjectId.value
    if (name === 'user_id') return selectedUserId.value
    if (name === 'as_of') return toApiTime(asOf.value)
    if (name === 'query') return '年需求量'
    if (name === 'requirement_id') return defaultRequirementId()
    if (name === 'document_id') return 'DEFECT-01'
    if (name === 'decision_or_object_id') return 'SUP-BAT-003'
    if (name === 'object_id' || name === 'contract_id') return 'CON-BAT-001'
    if (name === 'direction') return 'both'
    if (name === 'limit') return 8
    if (name === 'max_depth') return 2
    return schema.type === 'integer' ? 1 : ''
  }

  function selectMcpTool(toolName) {
    selectedMcpToolName.value = toolName
    const tool = mcpTools.value.find((item) => item.name === toolName)
    if (!tool) {
      mcpArguments.value = {}
      return
    }
    mcpArguments.value = Object.fromEntries(
      Object.entries(tool.inputSchema?.properties || {}).map(([name, schema]) => [
        name,
        defaultMcpArgument(name, schema),
      ]),
    )
    mcpResult.value = null
    mcpError.value = ''
  }

  function syncMcpContext() {
    if ('project_id' in mcpArguments.value) {
      mcpArguments.value.project_id = selectedProjectId.value
    }
    if ('user_id' in mcpArguments.value) {
      mcpArguments.value.user_id = selectedUserId.value
    }
    if ('as_of' in mcpArguments.value) {
      mcpArguments.value.as_of = toApiTime(asOf.value)
    }
    if ('requirement_id' in mcpArguments.value) {
      mcpArguments.value.requirement_id = defaultRequirementId()
    }
  }

  async function loadMcpTools() {
    mcpLoading.value = true
    mcpError.value = ''
    try {
      const result = await callMcp('tools/list')
      mcpTools.value = result.tools || []
      mcpConnected.value = true
      const preferred = mcpTools.value.some((tool) => tool.name === selectedMcpToolName.value)
        ? selectedMcpToolName.value
        : 'search_knowledge'
      selectMcpTool(preferred)
    } catch (reason) {
      mcpTools.value = []
      mcpConnected.value = false
      mcpError.value = reason instanceof Error ? reason.message : String(reason)
    } finally {
      mcpLoading.value = false
    }
  }

  async function searchKnowledge() {
    const query = knowledgeQuery.value.trim()
    if (!query || knowledgeLoading.value) return
    knowledgeLoading.value = true
    knowledgeError.value = ''
    knowledgeMeta.value = null
    try {
      const params = new URLSearchParams({
        query,
        user_id: selectedUserId.value,
        as_of: toApiTime(asOf.value),
        limit: '8',
      })
      const response = await requestJson(
        `/enterprise/projects/${encodeURIComponent(selectedProjectId.value)}/search?${params}`,
      )
      knowledgeResults.value = response.results || []
      knowledgeMeta.value = response
    } catch (reason) {
      knowledgeResults.value = []
      knowledgeError.value = reason instanceof Error ? reason.message : String(reason)
    } finally {
      knowledgeLoading.value = false
    }
  }

  async function runMcpTool() {
    const tool = selectedMcpTool.value
    if (!tool || mcpLoading.value) return
    const required = new Set(tool.inputSchema?.required || [])
    const argumentsPayload = {}
    for (const [name, schema] of Object.entries(tool.inputSchema?.properties || {})) {
      const value = mcpArguments.value[name]
      if (value === '' || value === null || value === undefined) {
        if (required.has(name)) {
          mcpError.value = `请填写必填参数：${name}`
          return
        }
        continue
      }
      if (schema.type === 'integer') {
        const parsed = Number.parseInt(value, 10)
        if (!Number.isInteger(parsed)) {
          mcpError.value = `${name} 必须是整数`
          return
        }
        argumentsPayload[name] = parsed
      } else {
        argumentsPayload[name] = value
      }
    }

    mcpLoading.value = true
    mcpError.value = ''
    mcpResult.value = null
    try {
      const result = await callMcp('tools/call', {
        name: tool.name,
        arguments: argumentsPayload,
      })
      mcpResult.value = {
        tool: tool.name,
        arguments: argumentsPayload,
        structuredContent: result.structuredContent,
        isError: result.isError === true,
      }
    } catch (reason) {
      mcpError.value = reason instanceof Error ? reason.message : String(reason)
    } finally {
      mcpLoading.value = false
    }
  }

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
    knowledgeResults.value = []
    knowledgeMeta.value = null
    mcpResult.value = null
    syncMcpContext()
    await loadDashboard()
  }

  async function updateViewer() {
    knowledgeResults.value = []
    knowledgeMeta.value = null
    mcpResult.value = null
    syncMcpContext()
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
    knowledgeQuery,
    knowledgeResults,
    knowledgeMeta,
    knowledgeLoading,
    knowledgeError,
    mcpTools,
    selectedMcpTool,
    selectedMcpToolName,
    mcpArguments,
    mcpResult,
    mcpLoading,
    mcpError,
    mcpConnected,
    loadDashboard,
    loadMcpTools,
    selectProject,
    selectMcpTool,
    updateViewer,
    searchKnowledge,
    runMcpTool,
    askAssistant,
  }
}
