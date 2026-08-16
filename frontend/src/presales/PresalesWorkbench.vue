<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { Modal, message } from 'ant-design-vue'
import {
  AppstoreOutlined,
  AuditOutlined,
  CheckCircleOutlined,
  CloudSyncOutlined,
  FileAddOutlined,
  FileSearchOutlined,
  FolderOpenOutlined,
  KeyOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MessageOutlined,
  PlusOutlined,
  ReloadOutlined,
  RocketOutlined,
  SafetyCertificateOutlined,
  SendOutlined,
  SettingOutlined,
  TeamOutlined,
  WarningOutlined,
} from '@ant-design/icons-vue'
import { getStoredToken, presalesApi, storeToken } from './api'
import SolutionWorkflowGraph from './SolutionWorkflowGraph.vue'

const projects = ref([])
const selectedProjectId = ref('')
const workspace = ref(null)
const projectSearch = ref('')
const activeTab = ref('overview')
const loadingProjects = ref(false)
const loadingWorkspace = ref(false)
const actionLoading = ref('')
const siderCollapsed = ref(false)
const tokenInput = ref(getStoredToken())
const projectsError = ref('')
const selectedFlowPlanName = ref('')

const dialogs = reactive({
  create: false,
  source: false,
  research: false,
  deliverable: false,
  review: false,
})

const createForm = reactive({
  title: '',
  owner: 'presales-owner',
  industry: '',
  reference_project_id: '',
})
const sourceForm = reactive({
  source_type: 'customer_document',
  title: '',
  content: '',
  source_url: '',
  occurred_at: '',
  added_by: 'presales-owner',
})
const researchForm = reactive({
  query: '汽车制造企业供应商准入、询比价与采购合规',
  user_id: 'user-procurement-owner',
  generated_by: 'presales-owner',
})
const deliverableForm = reactive({
  title: '',
  recommended_solution: '',
  updated_by: 'presales-owner',
})
const reviewForm = reactive({
  decision: 'approved',
  reviewed_by: 'solution-owner',
  note: '方案结构和风险边界可以对客展示。',
})

const sourceTypes = [
  { value: 'customer_document', label: '客户资料' },
  { value: 'meeting_minutes', label: '会议纪要' },
  { value: 'internal_material', label: '内部资料' },
  { value: 'external_intelligence', label: '外部情报' },
]

const requirementColumns = [
  { title: '需求', key: 'requirement', width: 300 },
  { title: '类别', dataIndex: 'category', key: 'category', width: 150 },
  { title: '状态', key: 'status', width: 120 },
  { title: '置信度', key: 'confidence', width: 100 },
]
const gapColumns = [
  { title: '缺口', key: 'gap', width: 340 },
  { title: '类别', dataIndex: 'category', key: 'category', width: 180 },
  { title: '影响', key: 'blocking', width: 110 },
]
const sourceColumns = [
  { title: '资料', key: 'source', width: 360 },
  { title: '类型', key: 'type', width: 140 },
  { title: '录入信息', key: 'metadata', width: 220 },
  { title: '来源', key: 'link', width: 90 },
]
const reviewColumns = [
  { title: '结论', key: 'decision', width: 100 },
  { title: '版本', key: 'version', width: 150 },
  { title: '评审意见', dataIndex: 'note', key: 'note' },
  { title: '评审人 / 时间', key: 'reviewer', width: 220 },
]
const publicationColumns = [
  { title: '发布版本', key: 'publication', width: 140 },
  { title: '草稿 / 修订', key: 'draft', width: 160 },
  { title: '发布依据', key: 'basis' },
]

const filteredProjects = computed(() => {
  const query = projectSearch.value.trim().toLocaleLowerCase()
  if (!query) return projects.value
  return projects.value.filter((project) =>
    [project.title, project.project_id, project.owner, project.industry]
      .filter(Boolean)
      .some((value) => String(value).toLocaleLowerCase().includes(query)),
  )
})

const projectSummary = computed(() =>
  projects.value.find((project) => project.project_id === selectedProjectId.value) || {},
)
const currentProject = computed(() => ({
  ...projectSummary.value,
  ...(workspace.value?.project || {}),
}))
const requirements = computed(() => workspace.value?.requirement_state?.items || [])
const gaps = computed(() => workspace.value?.requirement_state?.gaps || [])
const blockingGaps = computed(() => gaps.value.filter((gap) => gap.blocking))
const latestResearch = computed(() => workspace.value?.research_snapshots?.at(-1) || null)
const latestDraft = computed(() => workspace.value?.drafts?.at(-1) || null)
const flowPlanOptions = computed(() => (latestDraft.value?.plans || []).map((plan) => ({
  label: plan.recommended ? `${plan.name} · 推荐` : plan.name,
  value: plan.name,
})))
const selectedFlowPlan = computed(() =>
  latestDraft.value?.plans?.find((plan) => plan.name === selectedFlowPlanName.value)
    || latestDraft.value?.plans?.find((plan) => plan.recommended)
    || latestDraft.value?.plans?.[0]
    || null,
)
const publications = computed(() =>
  workspace.value?.published_deliverables || workspace.value?.publications || [],
)
const latestDraftApproved = computed(() => {
  const draft = latestDraft.value
  if (!draft) return false
  return (workspace.value?.reviews || []).some((review) =>
    review.draft_version === draft.draft_version
      && review.deliverable_revision === draft.deliverable_revision
      && review.decision === 'approved',
  )
})
const stageItems = computed(() => (workspace.value?.stages || []).map((stage) => ({
  title: stage.label,
  status: stage.status === 'completed' ? 'finish' : stage.status === 'current' ? 'process' : 'wait',
})))
const currentStageLabel = computed(() =>
  workspace.value?.stages?.find((stage) => stage.status === 'current')?.label
    || projectSummary.value.current_stage_label
    || '待识别',
)
const projectMetrics = computed(() => [
  {
    key: 'messages',
    label: '沟通记录',
    value: workspace.value?.conversation?.length || 0,
    suffix: '条',
    icon: MessageOutlined,
  },
  {
    key: 'requirements',
    label: '结构化需求',
    value: requirements.value.length,
    suffix: '项',
    icon: AuditOutlined,
  },
  {
    key: 'gaps',
    label: '阻断缺口',
    value: blockingGaps.value.length,
    suffix: '项',
    icon: WarningOutlined,
    tone: blockingGaps.value.length ? 'warning' : 'success',
  },
  {
    key: 'deliverables',
    label: '已发布版本',
    value: publications.value.length,
    suffix: '版',
    icon: SendOutlined,
    tone: publications.value.length ? 'success' : '',
  },
])

watch(latestDraft, (draft) => {
  const plans = draft?.plans || []
  if (!plans.some((plan) => plan.name === selectedFlowPlanName.value)) {
    selectedFlowPlanName.value = plans.find((plan) => plan.recommended)?.name || plans[0]?.name || ''
  }
}, { immediate: true })

function displayProjectTitle(project) {
  if (project.title && project.title !== project.project_id) return project.title
  const id = project.project_id || '未命名项目'
  if (id.startsWith('feishu:')) {
    const parts = id.split(':')
    const sessionIndex = parts.indexOf('session')
    if (sessionIndex >= 0 && parts[sessionIndex + 1]) return `飞书会话 · ${parts[sessionIndex + 1]}`
    const chatId = parts[2] || id
    return `飞书客户群 · ${chatId.slice(-8)}`
  }
  const shortId = id.length > 28 ? `${id.slice(0, 14)}...${id.slice(-8)}` : id
  return project.channel === 'feishu' ? `飞书项目 · ${shortId}` : shortId
}

function formatTime(value) {
  if (!value) return '时间未记录'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  }).format(date)
}

function requirementStatusColor(status) {
  return { confirmed: 'success', pending: 'processing', conflicted: 'error' }[status] || 'default'
}

function sourceTypeLabel(value) {
  return sourceTypes.find((item) => item.value === value)?.label || value
}

function researchResults(snapshot) {
  return snapshot?.knowledge_results || []
}

function externalSources(snapshot) {
  return snapshot?.external_sources || []
}

function capabilityName(capability) {
  return typeof capability === 'string' ? capability : capability?.name || '未命名能力'
}

function capabilityReason(capability) {
  return typeof capability === 'string' ? '' : capability?.reason || ''
}

async function loadProjects(preferredProjectId = selectedProjectId.value) {
  loadingProjects.value = true
  projectsError.value = ''
  try {
    const data = await presalesApi.listProjects()
    projects.value = data.projects || []
    const nextProjectId = projects.value.some((project) => project.project_id === preferredProjectId)
      ? preferredProjectId
      : projects.value[0]?.project_id || ''
    selectedProjectId.value = nextProjectId
    if (nextProjectId) await loadWorkspace(nextProjectId)
    else workspace.value = null
    return true
  } catch (error) {
    projects.value = []
    workspace.value = null
    projectsError.value = error.message
    return false
  } finally {
    loadingProjects.value = false
  }
}

async function loadWorkspace(projectId = selectedProjectId.value) {
  if (!projectId) return
  selectedProjectId.value = projectId
  loadingWorkspace.value = true
  try {
    workspace.value = await presalesApi.getProject(projectId)
  } catch (error) {
    workspace.value = null
    message.error(error.message)
  } finally {
    loadingWorkspace.value = false
  }
}

function selectProject({ key }) {
  loadWorkspace(key)
}

async function runAction(name, action, successText, refresh = true) {
  actionLoading.value = name
  try {
    const result = await action()
    message.success(successText)
    if (refresh) await loadWorkspace()
    return result
  } catch (error) {
    message.error(error.message)
    return null
  } finally {
    actionLoading.value = ''
  }
}

async function connectWithToken() {
  storeToken(tokenInput.value)
  const connected = await loadProjects()
  if (connected) message.success(tokenInput.value.trim() ? '内部访问令牌已更新' : '已切换到本地访问模式')
}

async function submitCreateProject() {
  if (!createForm.title.trim() || !createForm.owner.trim()) {
    message.warning('请填写项目名称和项目负责人')
    return
  }
  const created = await runAction(
    'create',
    () => presalesApi.createProject({
      title: createForm.title.trim(),
      owner: createForm.owner.trim(),
      industry: createForm.industry.trim() || null,
      reference_project_id: createForm.reference_project_id.trim() || null,
    }),
    '售前项目已创建',
    false,
  )
  if (!created) return
  dialogs.create = false
  Object.assign(createForm, { title: '', owner: 'presales-owner', industry: '', reference_project_id: '' })
  await loadProjects(created.project_id)
}

function openSourceDialog(type = 'customer_document') {
  Object.assign(sourceForm, {
    source_type: type,
    title: '',
    content: '',
    source_url: '',
    occurred_at: '',
    added_by: 'presales-owner',
  })
  dialogs.source = true
}

async function submitSource() {
  const external = sourceForm.source_type === 'external_intelligence'
  if (
    !sourceForm.title.trim()
    || !sourceForm.content.trim()
    || !sourceForm.added_by.trim()
    || (external && !sourceForm.source_url.trim())
  ) {
    message.warning(external ? '请填写标题、正文、公开来源 URL 和录入人' : '请填写标题、正文和录入人')
    return
  }
  const result = await runAction(
    'source',
    () => presalesApi.addSource(selectedProjectId.value, {
      source_type: sourceForm.source_type,
      title: sourceForm.title.trim(),
      content: sourceForm.content.trim(),
      source_url: external ? sourceForm.source_url.trim() : null,
      occurred_at: external && sourceForm.occurred_at
        ? new Date(sourceForm.occurred_at).toISOString()
        : null,
      added_by: sourceForm.added_by.trim(),
    }),
    '项目资料已添加',
  )
  if (result) dialogs.source = false
}

async function submitResearch() {
  if (!researchForm.query.trim() || !researchForm.user_id.trim() || !researchForm.generated_by.trim()) {
    message.warning('请填写研究主题、知识库访问用户和研究负责人')
    return
  }
  const result = await runAction(
    'research',
    () => presalesApi.runResearch(selectedProjectId.value, {
      query: researchForm.query.trim(),
      user_id: researchForm.user_id.trim(),
      as_of: new Date().toISOString(),
      generated_by: researchForm.generated_by.trim(),
    }),
    '知识与情报研究已更新',
  )
  if (result) dialogs.research = false
}

async function generateDraft() {
  await runAction(
    'draft',
    () => presalesApi.generateDraft(selectedProjectId.value),
    '三套方案与成果草稿已生成',
  )
}

function openDeliverableDialog() {
  const deliverable = latestDraft.value?.deliverable
  if (!deliverable) return
  Object.assign(deliverableForm, {
    title: deliverable.title || '',
    recommended_solution: deliverable.recommended_solution || '',
    updated_by: 'presales-owner',
  })
  dialogs.deliverable = true
}

async function submitDeliverable() {
  const draft = latestDraft.value
  if (!draft || !deliverableForm.recommended_solution.trim() || !deliverableForm.updated_by.trim()) {
    message.warning('请填写推荐方案说明和编辑人')
    return
  }
  const result = await runAction(
    'deliverable',
    () => presalesApi.updateDeliverable(selectedProjectId.value, draft.draft_version, {
      content: {
        ...draft.deliverable,
        title: deliverableForm.title.trim(),
        recommended_solution: deliverableForm.recommended_solution.trim(),
      },
      updated_by: deliverableForm.updated_by.trim(),
    }),
    '客户成果稿已更新，原批准状态已失效',
  )
  if (result) dialogs.deliverable = false
}

function openReviewDialog(decision) {
  Object.assign(reviewForm, {
    decision,
    reviewed_by: 'solution-owner',
    note: decision === 'approved'
      ? '方案结构和风险边界可以对客展示。'
      : '请补充信息并修订方案。',
  })
  dialogs.review = true
}

async function submitReview() {
  const draft = latestDraft.value
  if (!draft || !reviewForm.reviewed_by.trim()) {
    message.warning('请填写评审人')
    return
  }
  const result = await runAction(
    'review',
    () => presalesApi.reviewDraft(selectedProjectId.value, {
      draft_version: draft.draft_version,
      decision: reviewForm.decision,
      reviewed_by: reviewForm.reviewed_by.trim(),
      note: reviewForm.note.trim(),
    }),
    reviewForm.decision === 'approved' ? '方案草稿已批准' : '方案草稿已驳回',
  )
  if (result) dialogs.review = false
}

function confirmPublish() {
  const draft = latestDraft.value
  if (!draft || !latestDraftApproved.value) return
  Modal.confirm({
    title: '发布当前客户成果？',
    content: `将发布草稿 v${draft.draft_version}、成果修订 ${draft.deliverable_revision}。`,
    okText: '确认发布',
    cancelText: '取消',
    async onOk() {
      await runAction(
        'publish',
        () => presalesApi.publishDraft(selectedProjectId.value, {
          draft_version: draft.draft_version,
          published_by: 'presales-owner',
        }),
        '客户中心已更新',
      )
    },
  })
}

onMounted(() => loadProjects())
</script>

<template>
  <a-layout class="presales-workbench">
    <a-layout-sider
      v-model:collapsed="siderCollapsed"
      class="project-sider"
      :width="292"
      :collapsed-width="0"
      breakpoint="lg"
      collapsible
      :trigger="null"
    >
      <div class="workbench-brand">
        <span class="brand-mark"><RocketOutlined /></span>
        <div><strong>DCForge</strong><small>售前协同中心</small></div>
      </div>

      <div class="project-tools">
        <a-input-search v-model:value="projectSearch" allow-clear placeholder="搜索项目、负责人或行业" />
        <a-button type="primary" block @click="dialogs.create = true">
          <template #icon><PlusOutlined /></template>
          新建售前项目
        </a-button>
      </div>

      <div class="project-list-heading">
        <span>客户项目</span>
        <a-badge :count="projects.length" :overflow-count="99" />
      </div>
      <a-spin :spinning="loadingProjects">
        <a-menu
          class="project-menu"
          mode="inline"
          theme="dark"
          :selected-keys="selectedProjectId ? [selectedProjectId] : []"
          @click="selectProject"
        >
          <a-menu-item v-for="project in filteredProjects" :key="project.project_id">
            <div class="project-menu-item">
              <strong>{{ displayProjectTitle(project) }}</strong>
              <span>{{ project.current_stage_label || '阶段待识别' }}</span>
              <small>{{ project.owner || '负责人未分配' }} · {{ project.message_count || 0 }} 条沟通</small>
            </div>
          </a-menu-item>
        </a-menu>
      </a-spin>
      <a-empty v-if="!loadingProjects && !filteredProjects.length" class="sider-empty" :image="null" description="没有匹配项目" />

      <div class="sider-footer">
        <SafetyCertificateOutlined />
        <span>内部工作区</span>
        <a-tag :color="tokenInput ? 'green' : 'default'">{{ tokenInput ? '令牌已配置' : '本地模式' }}</a-tag>
      </div>
    </a-layout-sider>

    <a-layout class="workbench-main">
      <a-layout-header class="workbench-topbar">
        <div class="topbar-title">
          <a-button type="text" class="sider-toggle" @click="siderCollapsed = !siderCollapsed">
            <template #icon><MenuUnfoldOutlined v-if="siderCollapsed" /><MenuFoldOutlined v-else /></template>
          </a-button>
          <div>
            <span>售前运营</span>
            <strong>统一售前工作台</strong>
          </div>
        </div>
        <div class="topbar-actions">
          <a-popover placement="bottomRight" trigger="click">
            <template #content>
              <div class="token-popover">
                <label>内部访问令牌</label>
                <a-input-password v-model:value="tokenInput" placeholder="本地开发可留空" />
                <a-button type="primary" block :loading="loadingProjects" @click="connectWithToken">连接服务</a-button>
              </div>
            </template>
            <a-button><template #icon><KeyOutlined /></template>访问设置</a-button>
          </a-popover>
          <a-button :loading="loadingWorkspace" :disabled="!selectedProjectId" @click="loadWorkspace()">
            <template #icon><ReloadOutlined /></template>
            刷新
          </a-button>
        </div>
      </a-layout-header>

      <a-layout-content class="workbench-content">
        <a-result
          v-if="projectsError && !loadingProjects"
          status="error"
          title="售前项目服务暂不可用"
          :sub-title="projectsError"
        >
          <template #extra><a-button type="primary" @click="loadProjects()">重新连接</a-button></template>
        </a-result>

        <a-result
          v-else-if="!selectedProjectId && !loadingProjects"
          status="info"
          title="暂无售前项目"
          sub-title="创建项目后即可进入售前编排工作区。"
        >
          <template #extra><a-button type="primary" @click="dialogs.create = true">新建项目</a-button></template>
        </a-result>

        <div v-else-if="loadingWorkspace" class="workspace-loading">
          <a-skeleton active :paragraph="{ rows: 12 }" />
        </div>

        <a-result
          v-else-if="!workspace"
          status="warning"
          title="项目工作区暂不可用"
        >
          <template #extra><a-button @click="loadWorkspace()">重新加载</a-button></template>
        </a-result>

        <template v-else>
          <section class="project-commandbar">
            <div class="project-identity">
              <div class="project-avatar"><TeamOutlined /></div>
              <div>
                <div class="project-title-line">
                  <h1>{{ displayProjectTitle(currentProject) }}</h1>
                  <a-tag color="processing">{{ currentStageLabel }}</a-tag>
                </div>
                <p>
                  <span>{{ currentProject.project_id }}</span>
                  <span>{{ currentProject.owner || '负责人未分配' }}</span>
                  <span>{{ currentProject.industry || '行业待补充' }}</span>
                </p>
              </div>
            </div>
            <div class="command-actions">
              <a-button v-if="workspace.customer_url" :href="workspace.customer_url" target="_blank" rel="noreferrer">
                <template #icon><FolderOpenOutlined /></template>
                打开客户中心
              </a-button>
              <a-button type="primary" :loading="actionLoading === 'draft'" @click="generateDraft">
                <template #icon><RocketOutlined /></template>
                生成方案草稿
              </a-button>
            </div>
          </section>

          <section class="metric-strip" aria-label="项目对象统计">
            <article v-for="metric in projectMetrics" :key="metric.key" :class="metric.tone">
              <component :is="metric.icon" />
              <div><strong>{{ metric.value }}</strong><span>{{ metric.suffix }}</span><small>{{ metric.label }}</small></div>
            </article>
          </section>

          <section class="pipeline-section">
            <div class="section-heading">
              <div><span>售前阶段</span><strong>{{ currentStageLabel }}</strong></div>
              <a-tag>{{ stageItems.filter((item) => item.status === 'finish').length }} / {{ stageItems.length }} 已完成</a-tag>
            </div>
            <a-steps :items="stageItems" size="small" responsive />
          </section>

          <a-tabs v-model:active-key="activeTab" class="workspace-tabs">
            <a-tab-pane key="overview">
              <template #tab><span><AppstoreOutlined />项目总览</span></template>
              <div class="overview-grid">
                <section class="workspace-panel conversation-panel">
                  <div class="panel-heading">
                    <div><strong>飞书与客户沟通</strong><span>{{ workspace.conversation.length }} 条记录</span></div>
                    <MessageOutlined />
                  </div>
                  <a-empty v-if="!workspace.conversation.length" description="暂无沟通记录" />
                  <a-timeline v-else class="conversation-timeline">
                    <a-timeline-item
                      v-for="item in workspace.conversation"
                      :key="item.message_id || `${item.recorded_at}-${item.content}`"
                      :color="item.role === 'customer' ? 'blue' : item.role === 'employee' ? 'green' : 'gray'"
                    >
                      <div class="timeline-message">
                        <header>
                          <strong>{{ item.role === 'customer' ? '客户' : item.role === 'employee' ? '企业员工' : '机器人' }}</strong>
                          <span>{{ formatTime(item.recorded_at) }}</span>
                        </header>
                        <p>{{ item.content }}</p>
                        <footer>{{ item.channel }} · {{ item.delivery_status }}</footer>
                      </div>
                    </a-timeline-item>
                  </a-timeline>
                </section>

                <section class="workspace-panel requirements-panel">
                  <div class="panel-heading">
                    <div><strong>需求智能分析</strong><span>State {{ workspace.requirement_state?.state_version || '-' }}</span></div>
                    <AuditOutlined />
                  </div>
                  <a-table
                    :columns="requirementColumns"
                    :data-source="requirements"
                    :pagination="false"
                    :scroll="{ x: 670, y: 360 }"
                    row-key="requirement_id"
                    size="small"
                  >
                    <template #bodyCell="{ column, record }">
                      <template v-if="column.key === 'requirement'">
                        <div class="primary-cell"><strong>{{ record.subject }}</strong><span>{{ record.value }}</span></div>
                      </template>
                      <template v-else-if="column.key === 'category'"><a-tag>{{ record.category }}</a-tag></template>
                      <template v-else-if="column.key === 'status'">
                        <a-tag :color="requirementStatusColor(record.status)">{{ record.status }}</a-tag>
                      </template>
                      <template v-else-if="column.key === 'confidence'">{{ Math.round((record.confidence || 0) * 100) }}%</template>
                    </template>
                  </a-table>
                  <a-empty v-if="!requirements.length" description="尚未形成结构化需求" />
                </section>
              </div>

              <section class="workspace-panel gap-panel">
                <div class="panel-heading">
                  <div><strong>需求缺口</strong><span>{{ blockingGaps.length }} 个阻断缺口，{{ gaps.length }} 个待澄清项</span></div>
                  <WarningOutlined />
                </div>
                <a-alert
                  v-if="blockingGaps.length"
                  type="warning"
                  show-icon
                  message="当前需求仍有阻断缺口"
                  description="缺口是待澄清事项，不代表客户已经确认或拒绝。"
                />
                <a-table
                  :columns="gapColumns"
                  :data-source="gaps"
                  :pagination="gaps.length > 8 ? { pageSize: 8, showSizeChanger: false } : false"
                  :scroll="{ x: 630 }"
                  row-key="gap_id"
                  size="small"
                >
                  <template #bodyCell="{ column, record }">
                    <template v-if="column.key === 'gap'">
                      <div class="primary-cell"><strong>{{ record.description }}</strong><span>{{ record.reason }}</span></div>
                    </template>
                    <template v-else-if="column.key === 'category'"><code>{{ record.category }}</code></template>
                    <template v-else-if="column.key === 'blocking'">
                      <a-tag :color="record.blocking ? 'error' : 'default'">{{ record.blocking ? '阻断' : '建议' }}</a-tag>
                    </template>
                  </template>
                </a-table>
              </section>
            </a-tab-pane>

            <a-tab-pane key="research">
              <template #tab><span><FileSearchOutlined />资料与研究</span></template>
              <div class="tab-toolbar">
                <div><strong>项目资料与知识研究</strong><span>{{ workspace.sources.length }} 份资料 · {{ workspace.research_snapshots.length }} 个研究快照</span></div>
                <a-space wrap>
                  <a-button @click="openSourceDialog('customer_document')"><template #icon><FileAddOutlined /></template>添加资料</a-button>
                  <a-button @click="openSourceDialog('external_intelligence')">添加外部情报</a-button>
                  <a-button type="primary" @click="dialogs.research = true"><template #icon><CloudSyncOutlined /></template>运行研究</a-button>
                </a-space>
              </div>

              <section class="workspace-panel">
                <div class="panel-heading"><div><strong>项目资料</strong><span>客户事实、内部材料和外部情报分层保存</span></div><FileAddOutlined /></div>
                <a-table
                  :columns="sourceColumns"
                  :data-source="workspace.sources"
                  :pagination="workspace.sources.length > 6 ? { pageSize: 6, showSizeChanger: false } : false"
                  :scroll="{ x: 820 }"
                  row-key="source_id"
                  size="small"
                >
                  <template #bodyCell="{ column, record }">
                    <template v-if="column.key === 'source'">
                      <div class="primary-cell"><strong>{{ record.title }}</strong><span>{{ record.content }}</span></div>
                    </template>
                    <template v-else-if="column.key === 'type'"><a-tag>{{ sourceTypeLabel(record.source_type) }}</a-tag></template>
                    <template v-else-if="column.key === 'metadata'">
                      <div class="primary-cell"><strong>{{ record.added_by }}</strong><span>{{ formatTime(record.occurred_at || record.added_at) }}</span></div>
                    </template>
                    <template v-else-if="column.key === 'link'">
                      <a v-if="record.source_url" :href="record.source_url" target="_blank" rel="noreferrer">打开</a><span v-else>-</span>
                    </template>
                  </template>
                </a-table>
                <a-empty v-if="!workspace.sources.length" description="尚未录入项目资料" />
              </section>

              <section class="workspace-panel research-panel">
                <div class="panel-heading">
                  <div><strong>最新研究快照</strong><span>{{ latestResearch ? `v${latestResearch.research_version} · ${formatTime(latestResearch.generated_at)}` : '尚未生成' }}</span></div>
                  <CloudSyncOutlined />
                </div>
                <a-empty v-if="!latestResearch" description="尚未生成研究快照" />
                <div v-else class="research-grid">
                  <div>
                    <h3>企业知识</h3>
                    <a-list :data-source="researchResults(latestResearch)" size="small">
                      <template #renderItem="{ item }">
                        <a-list-item><a-list-item-meta :title="item.title" :description="item.summary" /></a-list-item>
                      </template>
                    </a-list>
                    <a-empty v-if="!researchResults(latestResearch).length" :image="null" description="没有匹配结果" />
                  </div>
                  <div>
                    <h3>外部情报</h3>
                    <a-list :data-source="externalSources(latestResearch)" size="small">
                      <template #renderItem="{ item }">
                        <a-list-item>
                          <a-list-item-meta :title="item.title" :description="item.summary || item.source_type" />
                          <template #actions><a v-if="item.source_url" :href="item.source_url" target="_blank" rel="noreferrer">来源</a></template>
                        </a-list-item>
                      </template>
                    </a-list>
                    <a-empty v-if="!externalSources(latestResearch).length" :image="null" description="尚无外部情报" />
                  </div>
                </div>
              </section>
            </a-tab-pane>

            <a-tab-pane key="solution">
              <template #tab><span><SettingOutlined />方案编排</span></template>
              <div class="tab-toolbar">
                <div><strong>Skill 模板与方案草稿</strong><span>实时读取当前需求；未确认信息保持为待确认假设</span></div>
                <a-button type="primary" :loading="actionLoading === 'draft'" @click="generateDraft"><template #icon><RocketOutlined /></template>生成新草稿</a-button>
              </div>

              <section class="workspace-panel">
                <div class="panel-heading"><div><strong>Skill 模板链</strong><span>{{ workspace.template_chain.length }} 个模板</span></div><SettingOutlined /></div>
                <div class="skill-chain">
                  <article v-for="skill in workspace.template_chain" :key="skill.skill_id || skill.name" :class="{ connected: skill.execution_status === 'connected' }">
                    <header><strong>{{ skill.name }}</strong><a-tag>v{{ skill.version }}</a-tag></header>
                    <p>{{ skill.description }}</p>
                    <footer>{{ skill.connected_step ? `已连接：${skill.connected_step}` : '本阶段未自动执行' }}</footer>
                  </article>
                </div>
              </section>

              <section class="workspace-panel draft-panel">
                <div class="panel-heading">
                  <div><strong>当前方案草稿</strong><span>{{ latestDraft ? `v${latestDraft.draft_version} · 成果修订 ${latestDraft.deliverable_revision}` : '尚未生成' }}</span></div>
                  <a-space v-if="latestDraft">
                    <a-tag :color="latestDraft.requirement_basis === 'latest_requirement_state' ? 'orange' : 'green'">
                      {{ latestDraft.requirement_basis === 'latest_requirement_state' ? '当前需求演示预览' : `正式基线 v${latestDraft.baseline_version}` }}
                    </a-tag>
                    <a-button @click="openDeliverableDialog">编辑成果稿</a-button>
                  </a-space>
                </div>
                <a-empty v-if="!latestDraft" description="尚未生成方案草稿" />
                <template v-else>
                  <a-alert
                    v-for="warning in latestDraft.warnings || []"
                    :key="warning"
                    class="draft-warning"
                    type="warning"
                    show-icon
                    :message="warning"
                  />
                  <div class="deliverable-summary">
                    <span>客户成果稿</span><strong>{{ latestDraft.deliverable?.title }}</strong><p>{{ latestDraft.deliverable?.recommended_solution }}</p>
                  </div>
                  <section class="solution-flow-section">
                    <header>
                      <div><span>目标工作流</span><strong>{{ selectedFlowPlan?.name }}</strong></div>
                      <a-segmented v-model:value="selectedFlowPlanName" :options="flowPlanOptions" />
                    </header>
                    <SolutionWorkflowGraph :plan="selectedFlowPlan" />
                  </section>
                  <div class="solution-grid">
                    <article v-for="plan in latestDraft.plans" :key="plan.solution_id || plan.name" :class="['solution-plan', { recommended: plan.recommended }]">
                      <header><div><span>{{ plan.recommended ? '推荐方案' : '备选方案' }}</span><h3>{{ plan.name }}</h3></div><CheckCircleOutlined v-if="plan.recommended" /></header>
                      <p>{{ plan.summary }}</p>
                      <h4>能力模块</h4>
                      <ul><li v-for="capability in plan.capabilities || []" :key="capabilityName(capability)"><strong>{{ capabilityName(capability) }}</strong><span>{{ capabilityReason(capability) }}</span></li></ul>
                    </article>
                  </div>
                </template>
              </section>
            </a-tab-pane>

            <a-tab-pane key="review">
              <template #tab><span><SafetyCertificateOutlined />评审发布</span></template>
              <div class="tab-toolbar">
                <div><strong>内部评审与客户发布</strong><span>批准严格绑定草稿版本和成果修订号</span></div>
                <a-space wrap>
                  <a-button :disabled="!latestDraft" @click="openReviewDialog('rejected')">驳回</a-button>
                  <a-button type="primary" ghost :disabled="!latestDraft" @click="openReviewDialog('approved')">批准</a-button>
                  <a-tooltip :title="latestDraftApproved ? '' : '当前成果修订尚未批准'">
                    <a-button type="primary" :disabled="!latestDraftApproved" :loading="actionLoading === 'publish'" @click="confirmPublish">
                      <template #icon><SendOutlined /></template>发布给客户
                    </a-button>
                  </a-tooltip>
                </a-space>
              </div>

              <section class="workspace-panel">
                <div class="panel-heading"><div><strong>内部评审记录</strong><span>{{ workspace.reviews.length }} 条记录</span></div><SafetyCertificateOutlined /></div>
                <a-table :columns="reviewColumns" :data-source="workspace.reviews.slice().reverse()" :pagination="false" :scroll="{ x: 750 }" row-key="review_id" size="small">
                  <template #bodyCell="{ column, record }">
                    <template v-if="column.key === 'decision'"><a-tag :color="record.decision === 'approved' ? 'success' : 'error'">{{ record.decision === 'approved' ? '已批准' : '已驳回' }}</a-tag></template>
                    <template v-else-if="column.key === 'version'">草稿 {{ record.draft_version }} / 修订 {{ record.deliverable_revision }}</template>
                    <template v-else-if="column.key === 'reviewer'"><div class="primary-cell"><strong>{{ record.reviewed_by }}</strong><span>{{ formatTime(record.reviewed_at) }}</span></div></template>
                  </template>
                </a-table>
                <a-empty v-if="!workspace.reviews.length" description="尚无内部评审记录" />
              </section>

              <section class="workspace-panel">
                <div class="panel-heading"><div><strong>客户发布记录</strong><span>{{ publications.length }} 个版本</span></div><SendOutlined /></div>
                <a-table :columns="publicationColumns" :data-source="publications" :pagination="false" :scroll="{ x: 650 }" row-key="publication_version" size="small">
                  <template #bodyCell="{ column, record }">
                    <template v-if="column.key === 'publication'"><strong>v{{ record.publication_version }}</strong></template>
                    <template v-else-if="column.key === 'draft'">草稿 {{ record.draft_version }} / 修订 {{ record.deliverable_revision }}</template>
                    <template v-else-if="column.key === 'basis'"><a-tag>{{ record.publication_basis || record.requirement_basis || '正式发布' }}</a-tag></template>
                  </template>
                </a-table>
                <a-empty v-if="!publications.length" description="尚无客户发布版本" />
              </section>
            </a-tab-pane>
          </a-tabs>
        </template>
      </a-layout-content>
    </a-layout>

    <a-modal v-model:open="dialogs.create" title="新建售前项目" :confirm-loading="actionLoading === 'create'" ok-text="创建项目" @ok="submitCreateProject">
      <a-form layout="vertical">
        <a-form-item label="项目名称" required><a-input v-model:value="createForm.title" placeholder="客户或机会名称" /></a-form-item>
        <a-form-item label="项目负责人" required><a-input v-model:value="createForm.owner" /></a-form-item>
        <a-form-item label="所属行业"><a-input v-model:value="createForm.industry" /></a-form-item>
        <a-form-item label="参考项目 ID"><a-input v-model:value="createForm.reference_project_id" /></a-form-item>
      </a-form>
    </a-modal>

    <a-modal v-model:open="dialogs.source" title="添加项目资料" :confirm-loading="actionLoading === 'source'" ok-text="保存资料" @ok="submitSource">
      <a-form layout="vertical">
        <a-form-item label="资料类型" required><a-select v-model:value="sourceForm.source_type" :options="sourceTypes" /></a-form-item>
        <a-form-item label="资料标题" required><a-input v-model:value="sourceForm.title" /></a-form-item>
        <a-form-item label="资料正文" required><a-textarea v-model:value="sourceForm.content" :rows="6" /></a-form-item>
        <template v-if="sourceForm.source_type === 'external_intelligence'">
          <a-form-item label="公开来源 URL" required><a-input v-model:value="sourceForm.source_url" type="url" /></a-form-item>
          <a-form-item label="发生时间"><a-input v-model:value="sourceForm.occurred_at" type="datetime-local" /></a-form-item>
        </template>
        <a-form-item label="录入人" required><a-input v-model:value="sourceForm.added_by" /></a-form-item>
      </a-form>
    </a-modal>

    <a-modal v-model:open="dialogs.research" title="运行知识与情报研究" :confirm-loading="actionLoading === 'research'" ok-text="开始研究" @ok="submitResearch">
      <a-form layout="vertical">
        <a-form-item label="研究主题" required><a-textarea v-model:value="researchForm.query" :rows="4" /></a-form-item>
        <a-form-item label="知识库访问用户" required><a-input v-model:value="researchForm.user_id" /></a-form-item>
        <a-form-item label="研究负责人" required><a-input v-model:value="researchForm.generated_by" /></a-form-item>
      </a-form>
    </a-modal>

    <a-modal v-model:open="dialogs.deliverable" title="编辑客户成果稿" width="680px" :confirm-loading="actionLoading === 'deliverable'" ok-text="保存修订" @ok="submitDeliverable">
      <a-form layout="vertical">
        <a-form-item label="成果标题"><a-input v-model:value="deliverableForm.title" /></a-form-item>
        <a-form-item label="推荐方案说明" required><a-textarea v-model:value="deliverableForm.recommended_solution" :rows="8" /></a-form-item>
        <a-form-item label="编辑人" required><a-input v-model:value="deliverableForm.updated_by" /></a-form-item>
      </a-form>
    </a-modal>

    <a-modal v-model:open="dialogs.review" :title="reviewForm.decision === 'approved' ? '批准方案草稿' : '驳回方案草稿'" :confirm-loading="actionLoading === 'review'" :ok-text="reviewForm.decision === 'approved' ? '确认批准' : '确认驳回'" :ok-button-props="{ danger: reviewForm.decision === 'rejected' }" @ok="submitReview">
      <a-alert :type="reviewForm.decision === 'approved' ? 'info' : 'warning'" show-icon :message="`草稿 v${latestDraft?.draft_version || '-'} · 成果修订 ${latestDraft?.deliverable_revision || '-'}`" />
      <a-form class="review-form" layout="vertical">
        <a-form-item label="评审人" required><a-input v-model:value="reviewForm.reviewed_by" /></a-form-item>
        <a-form-item label="评审意见"><a-textarea v-model:value="reviewForm.note" :rows="5" /></a-form-item>
      </a-form>
    </a-modal>
  </a-layout>
</template>
