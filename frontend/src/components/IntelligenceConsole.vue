<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { consoleApi } from '../services/intelligenceConsoleApi'
import {
  buildRecompilePayload,
  captureFeedbackCycleSnapshot,
  capturePreviousSolutionSnapshot,
  hasCompletePreviousSolutionSnapshot,
  processOrSolutionThreshold,
} from '../utils/intelligenceConsoleSession'

const STORAGE_KEY = 'dcforge-intelligence-console-v1'
const tabs = ['Requirement', 'Solution', 'Feedback & Diff']
const tabLabels = {
  Requirement: '需求分析',
  Solution: '方案生成',
  'Feedback & Diff': '客户需求变更',
}

const statusLabels = {
  pending: '待确认', confirmed: '已确认', conflicted: '存在冲突',
  superseded: '已被新版本替代', rejected: '已拒绝',
}
const confirmationLabels = { none: '未确认', internal: '内部确认', customer: '客户确认' }
const provenanceLabels = {
  ai_extracted: 'AI 提取', ai_inferred: 'AI 推断', customer_raw: '客户原始信息',
  human_modified: '人工修改', sales_judgment: '销售判断', presales_judgment: '售前判断',
}
const categoryLabels = {
  industry: '行业', department: '部门', business_goal: '业务目标', role: '相关角色',
  available_data: '可用数据', existing_system: '现有系统', current_process: '当前流程',
  pain_point: '业务痛点', security: '安全要求', approval: '审批规则', budget: '预算约束',
  time: '时间约束', data: '数据要求', risk: '风险约束', target_metric: '目标指标',
  customer_context: '客户背景', business_rule: '业务规则', scope: '项目范围',
  deliverable: '交付要求', integration: '系统集成',
}
const readinessLabels = {
  DISCOVERY: '需求发现阶段', PRELIMINARY_READY: '可生成初步方案', CONFIRMED_READY: '正式需求已就绪',
}
const routeLabels = {
  no_op: '无需更新',
  incremental_constraint_recompile: '约束增量重编译',
  full_solution_recompile: '方案全量重编译',
}
const reuseLabels = {
  direct_reuse: '直接复用', configuration: '配置适配', customization: '定制开发', unresolved: '暂未确定',
}
const strategyLabels = {
  quick_win: '快速落地方案', production_fit: '生产适配方案', transform: '转型升级方案',
}
const processFieldLabels = {
  industry: '行业', department: '部门', business_goal: '业务目标', roles: '参与角色',
  available_data: '可用数据', existing_systems: '现有系统', constraints: '关键约束',
  target_metrics: '目标指标', readiness_score: '需求成熟度',
}
const artifactLabels = {
  RequirementAnalysis: '需求分析结果', RequirementBaseline: '需求基线', ProcessSpec: '流程规格',
  SolutionBundleV2: '方案包 V2', DemoBlueprint: '演示蓝图', RequirementDiff: '需求差异',
  RequirementDiffRoute: '差异路由', RecompileResult: '重编译结果',
}
const diffFieldLabels = {
  changed_asset_ids: '变化资产', changed_fit_asset_ids: '变化适配资产', changed_module_ids: '变化模块',
  reuse_mode_changes: '复用方式变化', added_demo_node_ids: '新增演示节点',
  removed_demo_node_ids: '移除演示节点', changed_demo_node_ids: '变化演示节点',
  value_claim_changes: '价值依据变化', explanations: '变化说明',
}
const taskSuccessLabels = {
  analyze: '需求分析已完成', confirm: '需求确认已完成', compile: '解决方案生成完成',
  feedback: '客户反馈分析完成', diff: '需求差异计算完成', recompile: '解决方案更新完成',
}
const gapTypeLabels = { missing: '缺失', ambiguous: '含义不明确', unconfirmed: '待确认', conflicted: '存在冲突' }
const changeTypeLabels = { updated: '已更新', added: '新增', removed: '移除', confirmed: '已确认', rejected: '已拒绝', conflicted: '存在冲突', resolved: '已解决', superseded: '已替代' }
const priorityLabels = { critical: '紧急', high: '高', medium: '中', low: '低' }
const nodeTypeLabels = { transform: '处理节点', human_gate: '人工审批节点', report: '验证报告节点' }
const executorLabels = { system: '系统执行', ai: 'AI 执行', human: '人工执行' }
const reviewDispositionOptions = [
  { value: 'ACCEPT', label: '接受' },
  { value: 'REJECT', label: '拒绝候选' },
  { value: 'MODIFY', label: '修改后接受' },
  { value: 'PENDING_CLARIFICATION', label: '等待澄清' },
  { value: 'REMOVE', label: '移除正式需求' },
  { value: 'NOT_APPLICABLE', label: '标记为不适用' },
]

const categoryLabel = (value) => value?.startsWith('ext:') ? '扩展信息' : (categoryLabels[value] || value)
const formatMoney = (value) => Number.isFinite(Number(value)) ? `${Number(value) / 10000} 万元` : '—'
const localizedReuseJson = (value) => JSON.stringify(value, (_, item) => (
  typeof item === 'string' && reuseLabels[item] ? `${reuseLabels[item]} (${item})` : item
), null, 2)

const goldenSources = {
  meeting: '客户为汽车制造企业，项目由采购中心负责。当前流程由采购专员接收招标文件，随后采购专员依据审查规则审查招标文件并定位风险。人工审查周期长且合规风险定位慢。',
  email: '项目目标是缩短招标文件编制与审查周期，降低合规风险。现有系统包括OA。',
  document: '可用材料包括历史招标文件、企业采购制度和审查规则。数据不得出企业私域。审批规则为超过50万元必须人工审批。目标指标包括processing_time、manual_steps和risk_findings。',
  sales: '客户希望先验证汽车采购招标文件审查场景。',
}

const emptySession = () => ({
  projectId: 'internal-console-project',
  sources: { meeting: '', email: '', document: '', sales: '' },
  analysis: null,
  extractionWarnings: [],
  baseline: null,
  previousBaseline: null,
  previousProcessSpec: null,
  previousRecommendedSolution: null,
  previousBlueprint: null,
  processSpec: null,
  solutionBundle: null,
  recommendedSolution: null,
  blueprint: null,
  feedback: '',
  feedbackSources: [],
  changeSet: null,
  requirementDiff: null,
  route: null,
  recompileResult: null,
})

function restoreSession() {
  try {
    return { ...emptySession(), ...JSON.parse(sessionStorage.getItem(STORAGE_KEY) || '{}') }
  } catch {
    return emptySession()
  }
}

const session = reactive(restoreSession())
const activeTab = ref('Requirement')
const health = ref({ status: 'checking', service: 'backend' })
const loading = ref('')
const error = ref('')
const success = ref('')
const selectedIds = ref([])
const confirmationLevel = ref('customer')
const confirmedBy = ref('internal-console-user')
const confirmationNote = ref('已在内部智能引擎工作台中完成显式确认。')
const selectedPlanId = ref('')
const rawOpen = ref(false)
const rawKey = ref('RequirementAnalysis')

watch(session, (value) => sessionStorage.setItem(STORAGE_KEY, JSON.stringify(value)), { deep: true })

const currentState = computed(() => session.analysis?.current_state)
const readiness = computed(() => session.analysis?.readiness)
const currentPlan = computed(() => {
  const plans = session.solutionBundle?.plans || []
  return plans.find((plan) => plan.solution_id === selectedPlanId.value) || session.recommendedSolution || plans[0]
})
const approvalRequirement = computed(() => session.baseline?.confirmed_items?.find((item) => item.category === 'approval'))
const processApproval = computed(() => session.processSpec?.constraints?.find((item) => item.type === 'approval'))
const solutionApproval = computed(() => session.recommendedSolution?.applied_constraints?.find((item) => item.type === 'approval'))
const gateNode = computed(() => session.blueprint?.nodes?.find((item) => item.id === 'hard-approval-gate'))
const canRecompile = computed(() => hasCompletePreviousSolutionSnapshot(session))
const rawArtifacts = computed(() => ({
  RequirementAnalysis: session.analysis,
  RequirementBaseline: session.baseline,
  ProcessSpec: session.processSpec,
  SolutionBundleV2: session.solutionBundle,
  DemoBlueprint: session.blueprint,
  RequirementDiff: session.requirementDiff,
  RequirementDiffRoute: session.route,
  RecompileResult: session.recompileResult,
}))
const rawValue = computed(() => rawArtifacts.value[rawKey.value])

async function withTask(name, task) {
  loading.value = name
  error.value = ''
  success.value = ''
  try {
    const result = await task()
    success.value = taskSuccessLabels[name] || `${name} 已完成`
    return result
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason)
    throw reason
  } finally {
    loading.value = ''
  }
}

function loadGolden() {
  Object.assign(session, emptySession())
  session.projectId = `automotive-golden-${Date.now()}`
  session.sources = { ...goldenSources }
  selectedIds.value = []
  selectedPlanId.value = ''
  activeTab.value = 'Requirement'
  error.value = ''
  success.value = '汽车采购示例原始资料已加载'
}

function setRequirementSelected(requirementId, checked) {
  selectedIds.value = checked
    ? [...new Set([...selectedIds.value, requirementId])]
    : selectedIds.value.filter((item) => item !== requirementId)
}

function sourceRecords() {
  const definitions = [
    ['meeting', 'meeting_minutes', '汽车采购访谈纪要'],
    ['email', 'email', '项目目标邮件'],
    ['document', 'requirement_document', '采购智能化需求文档'],
    ['sales', 'sales_note', '售前备注'],
  ]
  return definitions.filter(([key]) => session.sources[key]?.trim()).map(([key, sourceType, title]) => ({
    source_id: `${key}-raw-v1`,
    project_id: session.projectId,
    source_type: sourceType,
    title,
    inline_content: session.sources[key].trim(),
    ...(key === 'sales' ? { author_role: 'presales' } : {}),
  }))
}

async function analyzeRequirements() {
  await withTask('analyze', async () => {
    const result = await consoleApi.analyze({
      project_id: session.projectId,
      sources: sourceRecords(),
      previous_state_version: null,
      skill_id: 'automotive-procurement-v1',
    })
    session.analysis = result.analysis
    session.extractionWarnings = result.extraction_warnings
    selectedIds.value = result.analysis.current_state.items
      .filter((item) => ['pending', 'conflicted'].includes(item.status))
      .map((item) => item.requirement_id)
  })
}

async function confirmSelected() {
  if (!selectedIds.value.length) return
  await withTask('confirm', async () => {
    const result = await consoleApi.confirm({
      confirmation: {
        project_id: session.projectId,
        state_version: currentState.value.state_version,
        confirmation_level: confirmationLevel.value,
        confirmed_requirement_ids: selectedIds.value,
        rejected_requirement_ids: [],
        modifications: [],
        confirmed_by: confirmedBy.value,
        note: confirmationNote.value,
      },
    })
    session.analysis = result.analysis
    if (result.baseline) session.baseline = result.baseline
    selectedIds.value = result.analysis.current_state.items
      .filter(
        (item) =>
          !['rejected', 'superseded'].includes(item.status) &&
          !(item.status === 'confirmed' && item.confirmation_level === 'customer'),
      )
      .map((item) => item.requirement_id)
  })
}

async function compileSolution() {
  await withTask('compile', async () => {
    const result = await consoleApi.compile({
      project_id: session.projectId,
      baseline_version: session.baseline.baseline_version,
    })
    session.processSpec = result.process_spec
    session.solutionBundle = result.solution_bundle
    session.recommendedSolution = result.recommended_solution
    session.blueprint = result.demo_blueprint
    selectedPlanId.value = result.solution_bundle.recommended_solution_id
  })
}

async function analyzeFeedback() {
  await withTask('feedback', async () => {
    captureFeedbackCycleSnapshot(session)
    const sources = [{
      source_id: `feedback-state-${currentState.value.state_version + 1}`,
      project_id: session.projectId,
      source_type: 'conversation',
      title: '客户最新反馈',
      inline_content: session.feedback,
    }]
    const result = await consoleApi.analyze({
      project_id: session.projectId,
      sources,
      previous_state_version: currentState.value.state_version,
      skill_id: 'automotive-procurement-v1',
    })
    session.analysis = result.analysis
    session.extractionWarnings = result.extraction_warnings
    session.feedbackSources = sources
    session.changeSet = (await consoleApi.changeSet({
      project_id: session.projectId,
      previous_baseline_version: session.previousBaseline.baseline_version,
      state_version: result.analysis.current_state.state_version,
    })).change_set
  })
}

async function reviewChangeSet() {
  if (!session.changeSet) return
  await withTask('confirm', async () => {
    const result = await consoleApi.reviewChangeSet({
      project_id: session.projectId,
      previous_baseline_version: session.previousBaseline.baseline_version,
      state_version: currentState.value.state_version,
      feedback_sources: session.feedbackSources,
      actions: session.changeSet.items.map((item) => ({
        target_requirement_id: ['REMOVE', 'NOT_APPLICABLE'].includes(item.review_disposition)
          ? item.matched_baseline_requirement_id
          : item.candidate_requirement_id,
        disposition: item.review_disposition,
        ...(['REMOVE', 'NOT_APPLICABLE'].includes(item.review_disposition) ? {
          evidence: item.source_refs[0] && {
            source_id: item.source_refs[0].source_id,
            excerpt: item.source_refs[0].excerpt,
            locator: item.source_refs[0].locator,
          },
        } : {}),
      })),
      confirmation_level: confirmationLevel.value,
      confirmed_by: confirmedBy.value,
      note: confirmationNote.value,
    })
    session.analysis = result.analysis
    if (result.baseline) {
      session.baseline = result.baseline
      session.requirementDiff = result.requirement_diff
      session.route = result.route
    }
  })
}

async function buildDiff() {
  await withTask('diff', async () => {
    const result = await consoleApi.diff({
      project_id: session.projectId,
      previous_baseline_version: session.previousBaseline.baseline_version,
      current_baseline_version: session.baseline.baseline_version,
    })
    session.requirementDiff = result.requirement_diff
    session.route = result.route
  })
}

async function recompileSolution() {
  await withTask('recompile', async () => {
    session.recompileResult = await consoleApi.recompile(buildRecompilePayload(session))
  })
}

onMounted(async () => {
  try { health.value = await consoleApi.health() }
  catch (reason) { health.value = { status: 'offline', service: reason.message } }
})
</script>

<template>
  <a-layout class="console-shell">
    <a-card class="topbar" :bordered="false">
      <div>
        <div class="title-line">
          <h1>DCForge Intelligence Console</h1>
          <a-tag color="blue">内部工具 · INTERNAL</a-tag>
        </div>
        <p>智能引擎内部调试与演示工作台 <small>ENGINE DEBUG TOOL</small> · 非最终客户展示界面</p>
      </div>
      <div class="header-status">
        <label>项目 ID<a-input v-model:value="session.projectId" :disabled="Boolean(currentState)" /></label>
        <a-tag :color="health.status === 'ok' ? 'green' : health.status === 'offline' ? 'red' : 'orange'">{{ health.status === 'ok' ? '后端已连接' : health.status === 'offline' ? '后端未连接' : '正在连接后端' }}</a-tag>
        <a-tag>需求状态 v{{ currentState?.state_version || '—' }}</a-tag>
        <a-tag>需求基线 v{{ session.baseline?.baseline_version || '—' }}</a-tag>
        <a-button @click="rawOpen = true">原始 JSON</a-button>
      </div>
    </a-card>

    <a-alert v-if="error" class="error-banner" type="error" show-icon message="请求失败" :description="error" />
    <a-alert v-else-if="success" class="success-banner" type="success" show-icon message="操作成功" :description="success" />
    <a-alert v-if="session.extractionWarnings.length" class="warning-banner" type="warning" show-icon message="需求提取提示">
      <template #description><div v-for="warning in session.extractionWarnings" :key="`${warning.source_id}-${warning.code}-${warning.locator || ''}`">{{ warning.source_id }} · {{ warning.code }} · {{ warning.message }}</div></template>
    </a-alert>
    <a-segmented class="tabs" v-model:value="activeTab" :options="tabs.map((tab) => ({ label: tabLabels[tab], value: tab }))" block />

    <a-layout-content class="console-main">
      <section v-if="activeTab === 'Requirement'" class="tab-layout">
        <a-card class="panel source-panel" title="客户上下文">
          <div class="panel-heading"><div><small>客户原始资料</small><h2>客户上下文</h2></div></div>
          <label>会议纪要<a-textarea v-model:value="session.sources.meeting" :rows="7" /></label>
          <label>客户邮件<a-textarea v-model:value="session.sources.email" :rows="4" /></label>
          <label>需求 / 招标材料<a-textarea v-model:value="session.sources.document" :rows="7" /></label>
          <label>销售备注<a-textarea v-model:value="session.sources.sales" :rows="3" /></label>
          <div class="button-row">
            <a-button @click="loadGolden">加载汽车采购示例</a-button>
            <a-button type="primary" :loading="loading === 'analyze'" :disabled="loading || !Object.values(session.sources).some(Boolean) || Boolean(currentState)" @click="analyzeRequirements">
              {{ loading === 'analyze' ? '正在分析客户需求…' : '开始需求分析' }}
            </a-button>
          </div>
          <p class="hint">示例仅加载客户原始资料，不会加载已确认的需求状态或需求基线。</p>
        </a-card>

        <div class="content-stack">
          <section class="panel">
            <div class="panel-heading"><div><small>需求智能分析</small><h2>需求成熟度</h2></div></div>
            <div v-if="readiness" class="metric-grid">
              <div><small>当前阶段</small><strong>{{ readinessLabels[readiness.stage] || readiness.stage }}</strong><code>{{ readiness.stage }}</code></div>
              <div><small>需求完整度</small><strong>{{ readiness.completeness_score }}</strong></div>
              <div><small>可生成初步方案</small><strong>{{ readiness.can_generate_preliminary_solution ? '可以' : '暂不可' }}</strong></div>
              <div><small>可生成正式方案</small><strong>{{ readiness.can_generate_formal_solution ? '可以' : '暂不可' }}</strong></div>
            </div>
            <p v-else class="empty">请先加载客户资料，然后点击“开始需求分析”。</p>
          </section>

          <section v-if="currentState" class="panel">
            <div class="panel-heading"><div><small>客户需求候选</small><h2>已识别需求</h2></div><span>{{ currentState.items.length }} 条需求</span></div>
            <a-table
              class="table-wrap"
              :data-source="currentState.items"
              row-key="requirement_id"
              :pagination="false"
              :scroll="{ x: 1180 }"
              size="small"
            >
              <a-table-column title="选择" key="selection" :width="70" fixed="left">
                <template #default="{ record: item }">
                  <a-checkbox
                    :checked="selectedIds.includes(item.requirement_id)"
                    :disabled="['rejected','superseded'].includes(item.status) || (item.status === 'confirmed' && item.confirmation_level === 'customer')"
                    @change="setRequirementSelected(item.requirement_id, $event.target.checked)"
                  />
                </template>
              </a-table-column>
              <a-table-column title="类别" key="category" :width="140">
                <template #default="{ record: item }"><strong>{{ categoryLabel(item.category) }}</strong><code>{{ item.category }}</code></template>
              </a-table-column>
              <a-table-column title="主题" data-index="subject" key="subject" :width="180" />
              <a-table-column title="当前内容" data-index="value" key="value" :width="300" />
              <a-table-column title="状态" key="status" :width="130">
                <template #default="{ record: item }"><a-tag :color="item.status === 'confirmed' ? 'green' : item.status === 'conflicted' ? 'red' : 'blue'">{{ statusLabels[item.status] || item.status }}</a-tag><code>{{ item.status }}</code></template>
              </a-table-column>
              <a-table-column title="确认级别" key="confirmation" :width="130">
                <template #default="{ record: item }"><strong>{{ confirmationLabels[item.confirmation_level] || item.confirmation_level }}</strong><code>{{ item.confirmation_level }}</code></template>
              </a-table-column>
              <a-table-column title="来源类型" key="provenance" :width="150">
                <template #default="{ record: item }"><strong>{{ provenanceLabels[item.provenance] || item.provenance }}</strong><code>{{ item.provenance }}</code></template>
              </a-table-column>
              <a-table-column title="详情" key="details" :width="100" fixed="right">
                <template #default="{ record: item }">
                  <a-popover title="需求证据与参数" trigger="click" placement="leftTop" :overlay-style="{ width: '520px' }">
                    <template #content>
                      <a-descriptions bordered size="small" :column="1">
                        <a-descriptions-item label="需求 ID">{{ item.requirement_id }}</a-descriptions-item>
                        <a-descriptions-item label="AI 置信度">{{ item.confidence }}</a-descriptions-item>
                        <a-descriptions-item label="结构化参数"><pre>{{ JSON.stringify(item.parameters, null, 2) }}</pre></a-descriptions-item>
                        <a-descriptions-item v-for="source in item.source_refs" :key="`${item.requirement_id}-${source.source_id}-${source.locator || ''}`" label="证据来源">
                          {{ source.source_id }}<code v-if="source.locator">{{ source.locator }}</code><br />{{ source.excerpt }}
                        </a-descriptions-item>
                      </a-descriptions>
                    </template>
                    <a-button type="link" size="small">查看详情</a-button>
                  </a-popover>
                </template>
              </a-table-column>
            </a-table>
          </section>

          <div v-if="currentState" class="three-columns">
            <section class="panel compact"><h3>信息缺口</h3><article v-for="gap in currentState.gaps" :key="gap.gap_id" class="record"><b>{{ categoryLabel(gap.category) }} · {{ gapTypeLabels[gap.gap_type] || gap.gap_type }}</b><code>{{ gap.category }} · {{ gap.gap_type }}</code><span>{{ gap.description }}</span></article><p v-if="!currentState.gaps.length" class="empty">暂无信息缺口</p></section>
            <section class="panel compact"><h3>需求冲突</h3><article v-for="conflict in currentState.conflicts" :key="conflict.conflict_id" class="record record--danger"><b>{{ categoryLabel(conflict.category) }} · {{ conflict.status === 'resolved' ? '已解决' : '待解决' }}</b><code>{{ conflict.category }} · {{ conflict.status }}</code><span>{{ conflict.description }}</span></article><p v-if="!currentState.conflicts.length" class="empty">暂无需求冲突</p></section>
            <section class="panel compact"><h3>下一步澄清问题</h3><article v-for="question in session.analysis.next_questions" :key="question.question_id" class="record"><b>{{ priorityLabels[question.priority] || question.priority }}优先级 · {{ categoryLabel(question.target_category) }}</b><code>{{ question.priority }} · {{ question.target_category }}</code><span>{{ question.text }}</span></article><p v-if="!session.analysis.next_questions.length" class="empty">暂无待澄清问题</p></section>
          </div>

          <section v-if="currentState" class="panel confirmation-panel">
            <div><small>显式人工操作</small><h2>需求确认</h2></div>
            <label>确认级别<a-select v-model:value="confirmationLevel" :options="[{ value: 'internal', label: '内部确认' }, { value: 'customer', label: '客户确认' }]" /></label>
            <label>确认人<a-input v-model:value="confirmedBy" /></label>
            <label>确认备注<a-input v-model:value="confirmationNote" /></label>
            <a-button type="primary" :loading="loading === 'confirm'" :disabled="loading || !selectedIds.length" @click="confirmSelected">{{ loading === 'confirm' ? '正在确认需求…' : `确认所选需求（${selectedIds.length}）` }}</a-button>
            <strong v-if="session.baseline" class="success">需求基线 v{{ session.baseline.baseline_version }} 已生成</strong>
          </section>
        </div>
      </section>

        <section v-else-if="activeTab === 'Solution'" class="content-stack">
        <section class="panel action-panel">
          <div><small>冻结引擎交接</small><h2>需求基线 → B-M8 方案生成</h2><p v-if="!session.baseline">尚未形成客户确认的正式需求基线，暂不能生成解决方案。</p></div>
          <a-button type="primary" :loading="loading === 'compile'" :disabled="loading || !session.baseline" @click="compileSolution">{{ loading === 'compile' ? '正在生成解决方案…' : '生成解决方案' }}</a-button>
        </section>

        <section v-if="session.processSpec" class="panel">
          <div class="panel-heading"><div><small>售前流程规格 · ProcessSpec V1</small><h2>结构化交接</h2></div><a-button type="link" @click="rawKey='ProcessSpec'; rawOpen=true">原始 JSON</a-button></div>
          <dl class="definition-grid">
            <div v-for="field in ['industry','department','business_goal','roles','available_data','existing_systems','constraints','target_metrics','readiness_score']" :key="field"><dt>{{ processFieldLabels[field] }}<code>{{ field }}</code></dt><dd>{{ typeof session.processSpec[field] === 'object' ? JSON.stringify(session.processSpec[field]) : session.processSpec[field] }}</dd></div>
          </dl>
        </section>

        <section v-if="session.solutionBundle" class="panel">
          <div class="panel-heading"><div><small>方案包 V2 · SolutionBundleV2</small><h2>三套冻结策略方案</h2></div></div>
          <div class="plan-grid">
            <a-card
              v-for="plan in session.solutionBundle.plans"
              :key="plan.solution_id"
              hoverable
              role="button"
              tabindex="0"
              :class="['plan-card', { selected: currentPlan?.solution_id === plan.solution_id }]"
              @click="selectedPlanId = plan.solution_id"
              @keydown.enter="selectedPlanId = plan.solution_id"
            >
              <span v-if="plan.solution_id === session.solutionBundle.recommended_solution_id" class="badge">推荐方案</span>
              <small>{{ plan.display_strategy }}</small><h3>{{ strategyLabels[plan.display_strategy] || plan.name }}</h3><p>{{ strategyLabels[plan.display_strategy] || plan.name }}：基于已选复用决策生成的确定性方案。</p><strong>{{ plan.review_score }}</strong><span>{{ plan.primary_asset_ids.join(', ') }}</span>
            </a-card>
          </div>
        </section>

        <section v-if="currentPlan" class="panel">
          <div class="panel-heading"><div><small>方案详情</small><h2>{{ strategyLabels[currentPlan.display_strategy] || currentPlan.name }}</h2></div><code>{{ currentPlan.name }}</code></div>
          <div class="detail-columns">
            <div><h3>适配评估</h3><pre>{{ JSON.stringify(currentPlan.fit_assessments, null, 2) }}</pre></div>
            <div><h3>复用决策</h3><pre>{{ localizedReuseJson(currentPlan.reuse_decisions) }}</pre></div>
            <div><h3>选用能力</h3><pre>{{ JSON.stringify(currentPlan.selected_components, null, 2) }}</pre></div>
            <div><h3>实施步骤</h3><ul><li v-for="item in currentPlan.implementation_steps" :key="item">{{ item }}</li></ul><h3>风险项 / 前提假设</h3><pre>{{ JSON.stringify({ risks: currentPlan.risks, assumptions: currentPlan.assumptions }, null, 2) }}</pre></div>
            <div><h3>支撑证据</h3><pre>{{ JSON.stringify(currentPlan.evidence_refs, null, 2) }}</pre></div>
            <div><h3>价值依据</h3><pre>{{ JSON.stringify(currentPlan.value_claims, null, 2) }}</pre></div>
          </div>
        </section>

        <section v-if="session.blueprint" class="panel">
          <div class="panel-heading"><div><small>推荐方案</small><h2>演示流程蓝图 · DemoBlueprint</h2></div><a-button type="link" @click="rawKey='DemoBlueprint'; rawOpen=true">原始 JSON</a-button></div>
          <div class="node-list"><article v-for="node in session.blueprint.nodes" :key="node.id" :class="['node', { 'node--gate': node.human_gate }]"><small>{{ nodeTypeLabels[node.node_type] || node.node_type }} · {{ executorLabels[node.executor] || node.executor }}</small><code>{{ node.node_type }} · {{ node.executor }}</code><strong>{{ node.name }}</strong><span>{{ node.id }}</span></article></div>
        </section>

        <section v-if="session.blueprint" class="panel">
          <div class="panel-heading"><div><small>需求到方案追溯</small><h2>审批金额阈值闭环</h2></div></div>
          <div class="trace"><div><small>客户需求</small><strong>{{ approvalRequirement?.value }}</strong><span>{{ approvalRequirement?.requirement_id }}</span></div><i>→</i><div><small>流程约束</small><strong>{{ formatMoney(processOrSolutionThreshold(processApproval)) }}</strong><code>{{ processOrSolutionThreshold(processApproval) }}</code><span>{{ processApproval?.id }}</span></div><i>→</i><div><small>方案能力</small><strong>{{ formatMoney(processOrSolutionThreshold(solutionApproval)) }}</strong><code>{{ processOrSolutionThreshold(solutionApproval) }}</code><span>{{ session.recommendedSolution?.solution_id }}</span></div><i>→</i><div><small>演示流程节点</small><strong>人工审批节点</strong><code>{{ gateNode?.id }}</code><span>{{ gateNode?.gate_reason }}</span></div></div>
        </section>
      </section>

      <section v-else class="content-stack">
        <section class="panel action-panel">
          <div><small>客户最新反馈</small><h2>客户需求变更</h2><p>当前需求基线 v{{ session.baseline?.baseline_version || '—' }}；一段反馈可识别 0..N 条独立变化。</p></div>
          <a-textarea v-model:value="session.feedback" :rows="3" />
          <a-button type="primary" :loading="loading === 'feedback'" :disabled="loading || !session.baseline || !session.analysis" @click="analyzeFeedback">{{ loading === 'feedback' ? '正在分析客户反馈…' : '分析客户反馈' }}</a-button>
        </section>

        <section v-if="session.changeSet" class="panel">
          <div class="panel-heading"><div><small>Generic RequirementChangeSet</small><h2>AI 识别的需求变化</h2></div><span>{{ session.changeSet.items.length }} 条独立变化</span></div>
          <p v-if="!session.changeSet.items.length" class="empty">未检测到实质需求变化；不会生成新的 Baseline 或重编译方案。</p>
          <a-table
            v-else
            class="table-wrap"
            :data-source="session.changeSet.items"
            row-key="candidate_requirement_id"
            :pagination="false"
            :scroll="{ x: 1260 }"
            size="small"
          >
            <a-table-column title="变化" key="change" :width="130">
              <template #default="{ record: item }"><a-tag color="blue">{{ item.suggested_change_type }}</a-tag><code>{{ item.suggested_change_type }}</code></template>
            </a-table-column>
            <a-table-column title="类别 / 主题" key="topic" :width="190">
              <template #default="{ record: item }"><strong>{{ categoryLabel(item.category) }}</strong><code>{{ item.category }}</code><span>{{ item.subject }}</span></template>
            </a-table-column>
            <a-table-column title="旧值 → 新值" key="value" :width="260">
              <template #default="{ record: item }"><span>{{ item.previous_value || '—' }}</span><i> → </i><strong>{{ item.proposed_value }}</strong></template>
            </a-table-column>
            <a-table-column title="参数" key="parameters" :width="110">
              <template #default="{ record: item }">
                <a-popover title="参数变化" trigger="click" placement="leftTop" :overlay-style="{ width: '480px' }">
                  <template #content><pre>{{ JSON.stringify({ previous: item.previous_parameters, proposed: item.proposed_parameters }, null, 2) }}</pre></template>
                  <a-button type="link" size="small">查看参数</a-button>
                </a-popover>
              </template>
            </a-table-column>
            <a-table-column title="证据 / 置信度" key="evidence" :width="300">
              <template #default="{ record: item }"><span v-for="source in item.source_refs" :key="`${item.candidate_requirement_id}-${source.source_id}`">{{ source.source_id }}：{{ source.excerpt }}</span><a-tag>{{ item.confidence }}</a-tag></template>
            </a-table-column>
            <a-table-column title="冲突" key="conflict" :width="110">
              <template #default="{ record: item }"><a-tag :color="item.conflict_status === 'none' ? 'green' : 'orange'">{{ item.conflict_status }}</a-tag></template>
            </a-table-column>
            <a-table-column title="审核操作" key="review" :width="190" fixed="right">
              <template #default="{ record: item }">
                <a-select v-model:value="item.review_disposition" style="width: 170px">
                  <a-select-option
                    v-for="option in reviewDispositionOptions"
                    :key="option.value"
                    :value="option.value"
                    :disabled="['REMOVE', 'NOT_APPLICABLE'].includes(option.value) && !item.matched_baseline_requirement_id"
                  >{{ option.label }}</a-select-option>
                </a-select>
              </template>
            </a-table-column>
          </a-table>
          <a-form class="button-row" layout="inline">
            <a-form-item label="确认级别">
              <a-select v-model:value="confirmationLevel" style="width: 120px" :options="[{ value: 'internal', label: '内部确认' }, { value: 'customer', label: '客户确认' }]" />
            </a-form-item>
            <a-form-item label="确认人"><a-input v-model:value="confirmedBy" /></a-form-item>
            <a-form-item><a-button type="primary" :loading="loading === 'confirm'" :disabled="Boolean(loading) || !session.changeSet.items.length" @click="reviewChangeSet">提交变化审核</a-button></a-form-item>
          </a-form>
          <a-alert type="info" show-icon message="审核规则" description="拒绝只影响本轮候选；移除或标记不适用仅对已有正式需求开放，并受证据校验保护。" />
        </section>

        <section v-if="session.requirementDiff" class="panel">
          <div class="panel-heading"><div><small>方案影响</small><h2>Baseline v{{ session.previousBaseline?.baseline_version }} → v{{ session.baseline?.baseline_version }}</h2></div><code>{{ session.route?.decision }}</code></div>
          <p v-if="session.route.decision === 'no_op'" class="success">未检测到有效业务变化，无需重新生成方案</p>
          <div class="metric-grid">
            <div><small>更新策略</small><strong>{{ routeLabels[session.route.decision] || session.route.decision }}</strong><code>{{ session.route.decision }}</code></div>
            <div><small>受影响需求</small><strong>{{ session.route.changed_categories.map(categoryLabel).join('、') || '无' }}</strong><code>{{ session.route.changed_categories.join(', ') }}</code></div>
            <div><small>新增 / 更新 / 移除</small><strong>{{ session.requirementDiff.added_requirement_ids.length }} / {{ session.requirementDiff.changed_requirement_ids.length }} / {{ session.requirementDiff.removed_requirement_ids.length }}</strong></div>
          </div>
          <div class="change-summary"><article v-for="change in session.requirementDiff.changes" :key="change.requirement_id"><b>{{ changeTypeLabels[change.change_type] || change.change_type }}</b><code>{{ change.change_type }}</code><span>{{ change.requirement_id }}</span></article></div>
          <div class="detail-columns"><div><h3>需求变化 · RequirementDiff</h3><pre>{{ JSON.stringify(session.requirementDiff, null, 2) }}</pre></div><div><h3>ProcessSpec / constraints change</h3><pre>{{ JSON.stringify(session.route.new_constraints, null, 2) }}</pre></div><div><h3>方案影响</h3><pre>{{ JSON.stringify({ assets: session.recompileResult?.recompile_result?.diff?.changed_asset_ids || [], modules: session.recompileResult?.recompile_result?.diff?.changed_module_ids || [], blueprint: session.recompileResult?.recompile_result?.diff?.changed_demo_node_ids || [], value_claims: session.recompileResult?.recompile_result?.diff?.value_claim_changes || [] }, null, 2) }}</pre></div></div>
          <a-button type="primary" :loading="loading === 'recompile'" :disabled="loading || !session.route || !canRecompile" @click="recompileSolution">{{ loading === 'recompile' ? '正在更新解决方案…' : '更新解决方案' }}</a-button>
        </section>

        <section v-if="session.recompileResult" class="panel">
          <div class="panel-heading"><div><small>方案智能差异</small><h2>解决方案更新结果</h2></div><span class="success">{{ routeLabels[session.recompileResult.decision] || session.recompileResult.decision }}<code>{{ session.recompileResult.decision }}</code></span></div>
          <div class="metric-grid"><div><small>更新方式</small><strong>{{ routeLabels[session.recompileResult.decision] }}</strong></div><div><small>影响类别</small><strong>{{ session.recompileResult.route.changed_categories.map(categoryLabel).join('、') || '无' }}</strong></div><div><small>DemoBlueprint 变化</small><strong>{{ session.recompileResult.recompile_result?.diff?.changed_demo_node_ids?.length || 0 }}</strong></div></div>
          <div v-if="session.recompileResult.decision !== 'no_op'" class="impact-summary"><span><b>更新方式：</b>{{ routeLabels[session.recompileResult.decision] }}</span><span><b>方案影响：</b>以结构化 Diff 为准</span><span><b>未变化项：</b>见下方 Diff</span></div>
          <p v-else class="success">未检测到有效业务变化，无需重新生成方案</p>
          <dl class="definition-grid diff-grid">
            <div v-for="field in ['changed_asset_ids','changed_fit_asset_ids','changed_module_ids','reuse_mode_changes','added_demo_node_ids','removed_demo_node_ids','changed_demo_node_ids','value_claim_changes','explanations']" :key="field"><dt>{{ diffFieldLabels[field] }}<code>{{ field }}</code></dt><dd>{{ field === 'reuse_mode_changes' ? localizedReuseJson(session.recompileResult.recompile_result?.diff?.[field] ?? {}) : JSON.stringify(session.recompileResult.recompile_result?.diff?.[field] ?? []) }}</dd></div>
          </dl>
        </section>
      </section>
    </a-layout-content>

    <a-drawer v-model:open="rawOpen" title="原始 JSON（只读）" width="min(720px, 80vw)">
      <a-select v-model:value="rawKey" style="width: 100%; margin-bottom: 12px">
        <a-select-option v-for="(_, key) in rawArtifacts" :key="key" :value="key">{{ artifactLabels[key] }} · {{ key }}</a-select-option>
      </a-select>
      <pre>{{ JSON.stringify(rawValue, null, 2) }}</pre>
    </a-drawer>
  </a-layout>
</template>

<style scoped>
button, input, textarea, select { font: inherit; }
button { cursor: pointer; }
.console-shell {
  min-height: calc(100vh - 72px);
  color: #172033;
  background: #eef1f5;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-synthesis: none;
}
.console-shell,
.console-shell * { box-sizing: border-box; }
.topbar { display: flex; justify-content: space-between; gap: 28px; align-items: center; padding: 20px 28px; background: #fff; border-bottom: 1px solid #dce2ea; position: sticky; top: 72px; z-index: 5; }
.title-line { display: flex; align-items: center; gap: 12px; }
h1, h2, h3, p { margin-top: 0; }
h1 { margin-bottom: 4px; font-size: 22px; }
h2 { margin-bottom: 4px; font-size: 18px; }
h3 { font-size: 14px; }
.topbar p, .hint, .empty { margin: 0; color: #707b8f; font-size: 12px; }
.badge { display: inline-flex; padding: 3px 7px; border-radius: 5px; background: #dce9ff; color: #1556b6; font-size: 10px; font-weight: 800; letter-spacing: .06em; }
.badge--internal { color: #fff; background: #1f64d3; }
.badge--internal small { margin-left: 5px; opacity: .72; font-size: 8px; }
.topbar p small { margin-left: 5px; color: #8993a5; font-size: 9px; letter-spacing: .04em; }
code { display: block; margin-top: 3px; color: #8993a5; background: transparent; font: 9px/1.35 ui-monospace, SFMono-Regular, Consolas, monospace; overflow-wrap: anywhere; }
.header-status { display: flex; gap: 10px; align-items: end; font-size: 12px; color: #5e687a; }
.header-status label { width: 230px; }
label { display: grid; gap: 6px; color: #566176; font-size: 12px; font-weight: 650; }
input, textarea, select { width: 100%; border: 1px solid #cfd7e3; border-radius: 6px; background: #fff; padding: 9px 10px; color: #172033; outline: none; }
input:focus, textarea:focus, select:focus { border-color: #3478df; box-shadow: 0 0 0 2px #3478df20; }
textarea { resize: vertical; line-height: 1.5; }
.health { padding: 8px 9px; border-radius: 6px; background: #f1f3f6; }
.health--ok { color: #117548; background: #e4f5ed; }
.health--offline { color: #b42318; background: #feeceb; }
.tabs { display: flex; gap: 0; padding: 0 28px; background: #fff; border-bottom: 1px solid #dce2ea; }
.tabs button { padding: 14px 22px; border: 0; border-bottom: 3px solid transparent; background: transparent; color: #647087; font-weight: 700; }
.tabs button.active { color: #1f64d3; border-color: #1f64d3; }
.console-main { padding: 22px 28px 40px; }
.tab-layout { display: grid; grid-template-columns: 360px minmax(0, 1fr); gap: 18px; align-items: start; }
.content-stack { display: grid; gap: 18px; }
.panel { background: #fff; border: 1px solid #dce2ea; border-radius: 9px; padding: 18px; box-shadow: 0 2px 8px #1d2a3b08; }
.source-panel { display: grid; gap: 14px; position: sticky; top: 132px; }
.panel-heading { display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; margin-bottom: 14px; }
.panel-heading small, .panel > small, .action-panel small { color: #748097; font-size: 10px; font-weight: 800; letter-spacing: .1em; }
.button-row { display: flex; gap: 9px; align-items: center; flex-wrap: wrap; }
.button { border: 1px solid #1f64d3; border-radius: 6px; padding: 9px 13px; color: #fff; background: #1f64d3; font-weight: 700; font-size: 12px; }
.button--secondary { color: #24446f; background: #fff; border-color: #bdc9da; }
.button:disabled { cursor: not-allowed; opacity: .45; }
.link { border: 0; background: transparent; color: #1f64d3; font-weight: 700; }
.error-banner { margin: 16px 28px 0; padding: 12px 15px; border: 1px solid #f0aaa5; border-radius: 7px; background: #fff0ef; color: #9d241c; display: flex; gap: 12px; }
.success-banner, .warning-banner { margin: 16px 28px 0; padding: 12px 15px; border-radius: 7px; display: flex; gap: 12px; }
.success-banner { border: 1px solid #9bd5ba; background: #effaf4; color: #117548; }
.warning-banner { border: 1px solid #e6c16b; background: #fff8e8; color: #76540c; flex-direction: column; }
.metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.metric-grid > div { padding: 13px; border: 1px solid #e0e5ed; border-radius: 7px; background: #f8fafc; display: grid; gap: 5px; }
.metric-grid small { color: #707b8f; }
.metric-grid strong { font-size: 16px; overflow-wrap: anywhere; }
.table-wrap { overflow: auto; max-height: 520px; border: 1px solid #e0e5ed; }
table { width: 100%; border-collapse: collapse; font-size: 11px; }
th { position: sticky; top: 0; background: #f3f6fa; color: #58647a; text-align: left; }
th, td { padding: 8px; border-bottom: 1px solid #e5e9ef; vertical-align: top; }
td pre, details pre { max-width: 400px; max-height: 220px; overflow: auto; }
.requirement-detail { min-width: 330px; max-width: 470px; display: grid; gap: 8px; padding: 10px; background: #f7f9fc; border: 1px solid #e1e6ed; border-radius: 6px; }
.requirement-detail > div { display: grid; gap: 4px; }
.requirement-detail pre { max-width: 420px; }
.status { display: inline-flex; padding: 3px 6px; border-radius: 4px; font-size: 10px; font-weight: 800; }
.status--confirmed { color: #117548; background: #e4f5ed; }
.status--pending { color: #9a6200; background: #fff0c7; }
.status--conflicted { color: #b42318; background: #fee4e2; }
.status--superseded, .status--rejected { color: #667085; background: #eaecf0; }
.three-columns { display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; }
.compact { max-height: 350px; overflow: auto; }
.record { display: grid; gap: 4px; padding: 9px 0; border-top: 1px solid #e6eaf0; font-size: 11px; }
.record span { color: #647087; }
.record--danger b { color: #b42318; }
.confirmation-panel, .action-panel { display: flex; align-items: end; gap: 14px; }
.confirmation-panel > div, .action-panel > div { margin-right: auto; }
.confirmation-panel label { min-width: 150px; }
.success { color: #117548; }
.definition-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; background: #dfe4eb; border: 1px solid #dfe4eb; }
.definition-grid > div { background: #fff; padding: 10px; }
dt { color: #69758a; font-size: 10px; font-weight: 800; }
dd { margin: 5px 0 0; font-size: 11px; overflow-wrap: anywhere; }
.plan-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.plan-card { display: grid; gap: 7px; text-align: left; padding: 15px; border: 1px solid #d8dfe9; border-radius: 8px; background: #fff; color: inherit; }
.plan-card.selected { border-color: #3478df; box-shadow: 0 0 0 2px #3478df18; }
.plan-card p { color: #657187; font-size: 11px; }
.plan-card > strong { color: #1f64d3; font-size: 20px; }
.plan-card > span:last-child { font-size: 10px; color: #69758a; }
.detail-columns { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.detail-columns > div { min-width: 0; padding: 12px; background: #f7f9fc; border: 1px solid #e2e7ee; border-radius: 7px; }
pre { margin: 0; padding: 10px; border-radius: 5px; background: #172033; color: #d8e5f7; font: 10px/1.45 ui-monospace, SFMono-Regular, Consolas, monospace; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; }
.detail-columns pre { max-height: 300px; }
.node-list { display: flex; gap: 8px; overflow: auto; }
.node { min-width: 190px; display: grid; gap: 5px; padding: 12px; border: 1px solid #d9e1eb; border-radius: 7px; background: #f8fafc; }
.node small, .node span { color: #6d788b; font-size: 10px; }
.node--gate { border-color: #e5ab48; background: #fff8e8; }
.trace { display: grid; grid-template-columns: 1fr auto 1fr auto 1fr auto 1fr; gap: 8px; align-items: center; }
.trace > div { min-height: 105px; padding: 12px; border: 1px solid #cfd9e6; border-radius: 7px; display: grid; gap: 6px; align-content: start; background: #f8fafc; }
.trace small, .trace span { color: #69758a; font-size: 10px; overflow-wrap: anywhere; }
.trace i { color: #1f64d3; font-style: normal; font-size: 20px; }
.action-panel textarea { max-width: 600px; }
.feedback-compare { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 14px; }
.feedback-compare > div { display: grid; gap: 6px; padding: 12px; background: #f8fafc; border: 1px solid #dde4ec; border-radius: 7px; }
.feedback-compare small { color: #6c788d; }
.change-summary, .impact-summary { display: flex; gap: 10px; flex-wrap: wrap; margin: 12px 0; }
.change-summary article, .impact-summary span { display: grid; gap: 3px; padding: 9px 11px; border: 1px solid #dce3ec; border-radius: 6px; background: #f8fafc; font-size: 11px; }
.change-summary article span { color: #667085; }
.impact-summary span { display: block; }
.diff-grid { margin: 14px 0; }
.drawer-backdrop { position: fixed; inset: 0; z-index: 20; background: #17203355; display: flex; justify-content: flex-end; }
.drawer { width: min(720px, 70vw); height: 100%; padding: 20px; background: #fff; display: grid; grid-template-rows: auto auto 1fr; gap: 12px; box-shadow: -10px 0 30px #17203322; }
.drawer header { display: flex; justify-content: space-between; align-items: start; }
.drawer pre { overflow: auto; }
@media (max-width: 1300px) { .header-status { flex-wrap: wrap; justify-content: flex-end; } .metric-grid { grid-template-columns: repeat(2, 1fr); } }
</style>
