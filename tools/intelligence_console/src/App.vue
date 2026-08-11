<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { consoleApi } from './api'

const STORAGE_KEY = 'dcforge-intelligence-console-v1'
const tabs = ['Requirement', 'Solution', 'Feedback & Diff']
const tabLabels = {
  Requirement: '需求分析',
  Solution: '方案生成',
  'Feedback & Diff': '客户反馈与差异',
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
  processSpec: null,
  solutionBundle: null,
  recommendedSolution: null,
  blueprint: null,
  feedback: '审批规则调整，现在超过80万元才必须人工审批。',
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
const oldApproval = computed(() => session.previousBaseline?.confirmed_items?.find((item) => item.category === 'approval'))
const processApproval = computed(() => session.processSpec?.constraints?.find((item) => item.type === 'approval'))
const solutionApproval = computed(() => session.recommendedSolution?.applied_constraints?.find((item) => item.type === 'approval'))
const gateNode = computed(() => session.blueprint?.nodes?.find((item) => item.id === 'hard-approval-gate'))
const feedbackCandidate = computed(() => currentState.value?.items?.find((item) => item.category === 'approval' && item.parameters?.threshold === 800000))
const openApprovalConflict = computed(() => currentState.value?.conflicts?.find((item) => item.category === 'approval' && item.status === 'open'))
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
const residue500k = computed(() => {
  if (!session.recompileResult) return null
  const payload = JSON.stringify([
    session.recompileResult.solution,
    session.recompileResult.demo_blueprint,
  ])
  return (payload.match(/500000/g) || []).length
})

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
    session.previousBaseline = session.baseline
    const result = await consoleApi.analyze({
      project_id: session.projectId,
      sources: [{
        source_id: `feedback-state-${currentState.value.state_version + 1}`,
        project_id: session.projectId,
        source_type: 'conversation',
        title: '客户审批规则反馈',
        inline_content: session.feedback,
      }],
      previous_state_version: currentState.value.state_version,
      skill_id: 'automotive-procurement-v1',
    })
    session.analysis = result.analysis
    session.extractionWarnings = result.extraction_warnings
    const candidate = result.analysis.current_state.items.find(
      (item) => item.category === 'approval' && item.parameters?.threshold === 800000,
    )
    selectedIds.value = candidate ? [candidate.requirement_id] : []
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
    session.recompileResult = await consoleApi.recompile({
      project_id: session.projectId,
      previous_baseline_version: session.previousBaseline.baseline_version,
      current_baseline_version: session.baseline.baseline_version,
      previous_process: session.processSpec,
      selected_solution: session.recommendedSolution,
      selected_blueprint: session.blueprint,
    })
  })
}

onMounted(async () => {
  try { health.value = await consoleApi.health() }
  catch (reason) { health.value = { status: 'offline', service: reason.message } }
})
</script>

<template>
  <div class="console-shell">
    <header class="topbar">
      <div>
        <div class="title-line">
          <h1>DCForge Intelligence Console</h1>
          <span class="badge badge--internal">内部工具 <small>INTERNAL</small></span>
        </div>
        <p>智能引擎内部调试与演示工作台 <small>ENGINE DEBUG TOOL</small> · 非最终客户展示界面</p>
      </div>
      <div class="header-status">
        <label>项目 ID<input v-model="session.projectId" :disabled="Boolean(currentState)" /></label>
        <span :class="['health', `health--${health.status}`]">{{ health.status === 'ok' ? '后端已连接' : health.status === 'offline' ? '后端未连接' : '正在连接后端' }}</span>
        <span>需求状态 v{{ currentState?.state_version || '—' }}</span>
        <span>需求基线 v{{ session.baseline?.baseline_version || '—' }}</span>
        <button class="button button--secondary" @click="rawOpen = true">原始 JSON</button>
      </div>
    </header>

    <div v-if="error" class="error-banner"><strong>请求失败</strong>{{ error }}</div>
    <div v-else-if="success" class="success-banner"><strong>操作成功</strong>{{ success }}</div>
    <div v-if="session.extractionWarnings.length" class="warning-banner">
      <strong>需求提取提示</strong>
      <span v-for="warning in session.extractionWarnings" :key="`${warning.source_id}-${warning.code}-${warning.locator || ''}`">
        {{ warning.source_id }} · {{ warning.code }} · {{ warning.message }}
      </span>
    </div>
    <nav class="tabs">
      <button v-for="tab in tabs" :key="tab" :class="{ active: activeTab === tab }" @click="activeTab = tab">{{ tabLabels[tab] }}</button>
    </nav>

    <main>
      <section v-if="activeTab === 'Requirement'" class="tab-layout">
        <aside class="panel source-panel">
          <div class="panel-heading"><div><small>客户原始资料</small><h2>客户上下文</h2></div></div>
          <label>会议纪要<textarea v-model="session.sources.meeting" rows="7" /></label>
          <label>客户邮件<textarea v-model="session.sources.email" rows="4" /></label>
          <label>需求 / 招标材料<textarea v-model="session.sources.document" rows="7" /></label>
          <label>销售备注<textarea v-model="session.sources.sales" rows="3" /></label>
          <div class="button-row">
            <button class="button button--secondary" @click="loadGolden">加载汽车采购示例</button>
            <button class="button" :disabled="loading || !Object.values(session.sources).some(Boolean) || Boolean(currentState)" @click="analyzeRequirements">
              {{ loading === 'analyze' ? '正在分析客户需求…' : '开始需求分析' }}
            </button>
          </div>
          <p class="hint">示例仅加载客户原始资料，不会加载已确认的需求状态或需求基线。</p>
        </aside>

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
            <div class="table-wrap">
              <table>
                <thead><tr><th>选择</th><th>类别</th><th>主题</th><th>当前内容</th><th>状态</th><th>确认级别</th><th>来源类型</th><th>详情</th></tr></thead>
                <tbody>
                  <tr v-for="item in currentState.items" :key="item.requirement_id">
                    <td><input v-model="selectedIds" type="checkbox" :value="item.requirement_id" :disabled="['rejected','superseded'].includes(item.status) || (item.status === 'confirmed' && item.confirmation_level === 'customer')" /></td>
                    <td><b>{{ categoryLabel(item.category) }}</b><code>{{ item.category }}</code></td><td>{{ item.subject }}</td><td>{{ item.value }}</td>
                    <td><span :class="['status', `status--${item.status}`]">{{ statusLabels[item.status] || item.status }}</span><code>{{ item.status }}</code></td>
                    <td><b>{{ confirmationLabels[item.confirmation_level] || item.confirmation_level }}</b><code>{{ item.confirmation_level }}</code></td>
                    <td><b>{{ provenanceLabels[item.provenance] || item.provenance }}</b><code>{{ item.provenance }}</code></td>
                    <td><details><summary>查看详情</summary><dl class="requirement-detail"><div><dt>需求 ID</dt><dd>{{ item.requirement_id }}</dd></div><div><dt>AI 置信度</dt><dd>{{ item.confidence }}</dd></div><div><dt>结构化参数</dt><dd><pre>{{ JSON.stringify(item.parameters, null, 2) }}</pre></dd></div><div v-for="source in item.source_refs" :key="`${item.requirement_id}-${source.source_id}-${source.locator || ''}`"><dt>证据来源</dt><dd>{{ source.source_id }}<code v-if="source.locator">{{ source.locator }}</code></dd><dt>原文证据</dt><dd>{{ source.excerpt }}</dd></div></dl></details></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <div v-if="currentState" class="three-columns">
            <section class="panel compact"><h3>信息缺口</h3><article v-for="gap in currentState.gaps" :key="gap.gap_id" class="record"><b>{{ categoryLabel(gap.category) }} · {{ gapTypeLabels[gap.gap_type] || gap.gap_type }}</b><code>{{ gap.category }} · {{ gap.gap_type }}</code><span>{{ gap.description }}</span></article><p v-if="!currentState.gaps.length" class="empty">暂无信息缺口</p></section>
            <section class="panel compact"><h3>需求冲突</h3><article v-for="conflict in currentState.conflicts" :key="conflict.conflict_id" class="record record--danger"><b>{{ categoryLabel(conflict.category) }} · {{ conflict.status === 'resolved' ? '已解决' : '待解决' }}</b><code>{{ conflict.category }} · {{ conflict.status }}</code><span>{{ conflict.description }}</span></article><p v-if="!currentState.conflicts.length" class="empty">暂无需求冲突</p></section>
            <section class="panel compact"><h3>下一步澄清问题</h3><article v-for="question in session.analysis.next_questions" :key="question.question_id" class="record"><b>{{ priorityLabels[question.priority] || question.priority }}优先级 · {{ categoryLabel(question.target_category) }}</b><code>{{ question.priority }} · {{ question.target_category }}</code><span>{{ question.text }}</span></article><p v-if="!session.analysis.next_questions.length" class="empty">暂无待澄清问题</p></section>
          </div>

          <section v-if="currentState" class="panel confirmation-panel">
            <div><small>显式人工操作</small><h2>需求确认</h2></div>
            <label>确认级别<select v-model="confirmationLevel"><option value="internal">内部确认</option><option value="customer">客户确认</option></select></label>
            <label>确认人<input v-model="confirmedBy" /></label>
            <label>确认备注<input v-model="confirmationNote" /></label>
            <button class="button" :disabled="loading || !selectedIds.length" @click="confirmSelected">{{ loading === 'confirm' ? '正在确认需求…' : `确认所选需求（${selectedIds.length}）` }}</button>
            <strong v-if="session.baseline" class="success">需求基线 v{{ session.baseline.baseline_version }} 已生成</strong>
          </section>
        </div>
      </section>

      <section v-else-if="activeTab === 'Solution'" class="content-stack">
        <section class="panel action-panel">
          <div><small>冻结引擎交接</small><h2>需求基线 → B-M8 方案生成</h2><p v-if="!session.baseline">尚未形成客户确认的正式需求基线，暂不能生成解决方案。</p></div>
          <button class="button" :disabled="loading || !session.baseline" @click="compileSolution">{{ loading === 'compile' ? '正在生成解决方案…' : '生成解决方案' }}</button>
        </section>

        <section v-if="session.processSpec" class="panel">
          <div class="panel-heading"><div><small>售前流程规格 · ProcessSpec V1</small><h2>结构化交接</h2></div><button class="link" @click="rawKey='ProcessSpec'; rawOpen=true">原始 JSON</button></div>
          <dl class="definition-grid">
            <div v-for="field in ['industry','department','business_goal','roles','available_data','existing_systems','constraints','target_metrics','readiness_score']" :key="field"><dt>{{ processFieldLabels[field] }}<code>{{ field }}</code></dt><dd>{{ typeof session.processSpec[field] === 'object' ? JSON.stringify(session.processSpec[field]) : session.processSpec[field] }}</dd></div>
          </dl>
        </section>

        <section v-if="session.solutionBundle" class="panel">
          <div class="panel-heading"><div><small>方案包 V2 · SolutionBundleV2</small><h2>三套冻结策略方案</h2></div></div>
          <div class="plan-grid">
            <button v-for="plan in session.solutionBundle.plans" :key="plan.solution_id" :class="['plan-card', { selected: currentPlan?.solution_id === plan.solution_id }]" @click="selectedPlanId = plan.solution_id">
              <span v-if="plan.solution_id === session.solutionBundle.recommended_solution_id" class="badge">推荐方案</span>
              <small>{{ plan.display_strategy }}</small><h3>{{ strategyLabels[plan.display_strategy] || plan.name }}</h3><p>{{ strategyLabels[plan.display_strategy] || plan.name }}：基于已选复用决策生成的确定性方案。</p><strong>{{ plan.review_score }}</strong><span>{{ plan.primary_asset_ids.join(', ') }}</span>
            </button>
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
          <div class="panel-heading"><div><small>推荐方案</small><h2>演示流程蓝图 · DemoBlueprint</h2></div><button class="link" @click="rawKey='DemoBlueprint'; rawOpen=true">原始 JSON</button></div>
          <div class="node-list"><article v-for="node in session.blueprint.nodes" :key="node.id" :class="['node', { 'node--gate': node.human_gate }]"><small>{{ nodeTypeLabels[node.node_type] || node.node_type }} · {{ executorLabels[node.executor] || node.executor }}</small><code>{{ node.node_type }} · {{ node.executor }}</code><strong>{{ node.name }}</strong><span>{{ node.id }}</span></article></div>
        </section>

        <section v-if="session.blueprint" class="panel">
          <div class="panel-heading"><div><small>需求到方案追溯</small><h2>审批金额阈值闭环</h2></div></div>
          <div class="trace"><div><small>客户需求</small><strong>{{ approvalRequirement?.value }}</strong><span>{{ approvalRequirement?.requirement_id }}</span></div><i>→</i><div><small>流程约束</small><strong>{{ formatMoney(processApproval?.parameters?.threshold) }}</strong><code>{{ processApproval?.parameters?.threshold }}</code><span>{{ processApproval?.id }}</span></div><i>→</i><div><small>方案能力</small><strong>{{ formatMoney(solutionApproval?.parameters?.threshold) }}</strong><code>{{ solutionApproval?.parameters?.threshold }}</code><span>{{ session.recommendedSolution?.solution_id }}</span></div><i>→</i><div><small>演示流程节点</small><strong>人工审批节点</strong><code>{{ gateNode?.id }}</code><span>{{ gateNode?.gate_reason }}</span></div></div>
        </section>
      </section>

      <section v-else class="content-stack">
        <section class="panel action-panel">
          <div><small>客户最新反馈</small><h2>客户反馈分析</h2><p>当前需求基线 v{{ session.baseline?.baseline_version || '—' }}</p></div>
          <textarea v-model="session.feedback" rows="3" />
          <button class="button" :disabled="loading || !session.baseline || !session.analysis" @click="analyzeFeedback">{{ loading === 'feedback' ? '正在分析客户反馈…' : '分析客户反馈' }}</button>
        </section>

        <section v-if="feedbackCandidate" class="panel">
          <div class="feedback-compare"><div><small>原需求</small><strong>{{ oldApproval?.value }}</strong><span>{{ oldApproval?.requirement_id }}</span></div><div><small>新需求</small><strong>{{ feedbackCandidate.value }}</strong><span :class="['status', `status--${feedbackCandidate.status}`]">{{ statusLabels[feedbackCandidate.status] || feedbackCandidate.status }}</span><code>{{ feedbackCandidate.status }}</code></div><div><small>检测到需求冲突</small><strong>{{ openApprovalConflict?.conflict_id }}</strong><span>{{ session.analysis.next_questions?.[0]?.text }}</span></div></div>
          <div class="button-row"><span>新需求必须经过客户显式确认后才能进入需求基线。</span><button class="button" :disabled="loading || !selectedIds.length" @click="confirmationLevel='customer'; confirmSelected()">{{ loading === 'confirm' ? '正在确认需求…' : '确认新需求' }}</button></div>
        </section>

        <section v-if="session.previousBaseline && session.baseline?.baseline_version === 2" class="panel action-panel">
          <div><small>需求基线版本变化</small><h2>需求变化与更新策略</h2><p>v{{ session.previousBaseline.baseline_version }} → v{{ session.baseline.baseline_version }}</p></div>
          <button class="button" :disabled="Boolean(loading)" @click="buildDiff">{{ loading === 'diff' ? '正在计算需求变化…' : '计算差异' }}</button>
        </section>

        <section v-if="session.requirementDiff" class="panel">
          <p v-if="session.route.decision === 'no_op'" class="success">未检测到有效业务变化，无需重新生成方案</p>
          <div class="metric-grid">
            <div><small>原审批阈值</small><strong>{{ formatMoney(oldApproval?.parameters?.threshold) }}</strong><code>{{ oldApproval?.parameters?.threshold }}</code></div>
            <div><small>新审批阈值</small><strong>{{ formatMoney(approvalRequirement?.parameters?.threshold) }}</strong><code>{{ approvalRequirement?.parameters?.threshold }}</code></div>
            <div><small>更新策略</small><strong>{{ routeLabels[session.route.decision] || session.route.decision }}</strong><code>{{ session.route.decision }}</code></div>
            <div><small>受影响需求</small><strong>{{ session.route.changed_categories.map(categoryLabel).join('、') || '无' }}</strong><code>{{ session.route.changed_categories.join(', ') }}</code></div>
          </div>
          <div class="change-summary"><article v-for="change in session.requirementDiff.changes" :key="change.requirement_id"><b>{{ changeTypeLabels[change.change_type] || change.change_type }}</b><code>{{ change.change_type }}</code><span>{{ change.requirement_id }}</span></article></div>
          <div class="detail-columns"><div><h3>需求变化 · RequirementDiff</h3><pre>{{ JSON.stringify(session.requirementDiff, null, 2) }}</pre></div><div><h3>新增 / 更新约束</h3><pre>{{ JSON.stringify(session.route.new_constraints, null, 2) }}</pre></div></div>
          <button class="button" :disabled="loading || !session.route" @click="recompileSolution">{{ loading === 'recompile' ? '正在更新解决方案…' : '更新解决方案' }}</button>
        </section>

        <section v-if="session.recompileResult" class="panel">
          <div class="panel-heading"><div><small>方案智能差异</small><h2>解决方案更新结果</h2></div><span class="success">{{ routeLabels[session.recompileResult.decision] || session.recompileResult.decision }}<code>{{ session.recompileResult.decision }}</code></span></div>
          <div class="metric-grid">
            <div><small>原审批阈值</small><strong>{{ formatMoney(oldApproval?.parameters?.threshold) }}</strong><code>{{ oldApproval?.parameters?.threshold }}</code></div>
            <div><small>新审批阈值</small><strong>{{ formatMoney(approvalRequirement?.parameters?.threshold) }}</strong><code>{{ approvalRequirement?.parameters?.threshold }}</code></div>
            <div><small>约束 ID</small><strong>{{ processApproval?.id === session.recompileResult.solution.applied_constraints.find(c => c.type === 'approval')?.id ? '保持不变' : '发生变化' }}</strong></div>
            <div><small>旧 50 万规则残留</small><strong>{{ residue500k }}</strong></div>
          </div>
          <div v-if="session.recompileResult.decision !== 'no_op'" class="impact-summary"><span><b>更新方式：</b>{{ routeLabels[session.recompileResult.decision] }}</span><span><b>影响范围：</b>人工审批节点</span><span><b>未发生变化：</b>资产检索、方案模块、能力复用结构</span></div>
          <p v-else class="success">未检测到有效业务变化，无需重新生成方案</p>
          <dl class="definition-grid diff-grid">
            <div v-for="field in ['changed_asset_ids','changed_fit_asset_ids','changed_module_ids','reuse_mode_changes','added_demo_node_ids','removed_demo_node_ids','changed_demo_node_ids','value_claim_changes','explanations']" :key="field"><dt>{{ diffFieldLabels[field] }}<code>{{ field }}</code></dt><dd>{{ field === 'reuse_mode_changes' ? localizedReuseJson(session.recompileResult.recompile_result?.diff?.[field] ?? {}) : JSON.stringify(session.recompileResult.recompile_result?.diff?.[field] ?? []) }}</dd></div>
          </dl>
        </section>
      </section>
    </main>

    <div v-if="rawOpen" class="drawer-backdrop" @click.self="rawOpen = false">
      <aside class="drawer"><header><div><small>只读</small><h2>原始 JSON</h2></div><button class="button button--secondary" @click="rawOpen=false">关闭</button></header><label>数据对象<select v-model="rawKey"><option v-for="(_, key) in rawArtifacts" :key="key" :value="key">{{ artifactLabels[key] }} · {{ key }}</option></select></label><pre>{{ JSON.stringify(rawValue, null, 2) }}</pre></aside>
    </div>
  </div>
</template>
