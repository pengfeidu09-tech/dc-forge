<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { consoleApi } from './api'

const STORAGE_KEY = 'dcforge-intelligence-console-v1'
const tabs = ['Requirement', 'Solution', 'Feedback & Diff']

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
const confirmationNote = ref('Explicit confirmation captured in the internal console.')
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
    success.value = `${name} completed`
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
  success.value = 'Automotive Golden raw sources loaded'
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
          <span class="badge badge--internal">INTERNAL</span>
        </div>
        <p>ENGINE DEBUG &amp; DEMO · 非最终客户展示界面</p>
      </div>
      <div class="header-status">
        <label>Project ID<input v-model="session.projectId" :disabled="Boolean(currentState)" /></label>
        <span :class="['health', `health--${health.status}`]">Backend {{ health.status }}</span>
        <span>State v{{ currentState?.state_version || '—' }}</span>
        <span>Baseline v{{ session.baseline?.baseline_version || '—' }}</span>
        <button class="button button--secondary" @click="rawOpen = true">Raw JSON</button>
      </div>
    </header>

    <div v-if="error" class="error-banner"><strong>Request failed</strong>{{ error }}</div>
    <div v-else-if="success" class="success-banner"><strong>Success</strong>{{ success }}</div>
    <div v-if="session.extractionWarnings.length" class="warning-banner">
      <strong>Extraction warnings</strong>
      <span v-for="warning in session.extractionWarnings" :key="`${warning.source_id}-${warning.code}-${warning.locator || ''}`">
        {{ warning.source_id }} · {{ warning.code }} · {{ warning.message }}
      </span>
    </div>
    <nav class="tabs">
      <button v-for="tab in tabs" :key="tab" :class="{ active: activeTab === tab }" @click="activeTab = tab">{{ tab }}</button>
    </nav>

    <main>
      <section v-if="activeTab === 'Requirement'" class="tab-layout">
        <aside class="panel source-panel">
          <div class="panel-heading"><div><small>RAW CUSTOMER SOURCES</small><h2>Customer Context</h2></div></div>
          <label>Meeting Minutes<textarea v-model="session.sources.meeting" rows="7" /></label>
          <label>Email<textarea v-model="session.sources.email" rows="4" /></label>
          <label>Requirement Document<textarea v-model="session.sources.document" rows="7" /></label>
          <label>Sales Note<textarea v-model="session.sources.sales" rows="3" /></label>
          <div class="button-row">
            <button class="button button--secondary" @click="loadGolden">Load Automotive Golden</button>
            <button class="button" :disabled="loading || !Object.values(session.sources).some(Boolean) || Boolean(currentState)" @click="analyzeRequirements">
              {{ loading === 'analyze' ? 'Analyzing…' : 'Analyze Requirements' }}
            </button>
          </div>
          <p class="hint">Golden 仅加载原始 customer source text；不会加载确认后的 State 或 Baseline。</p>
        </aside>

        <div class="content-stack">
          <section class="panel">
            <div class="panel-heading"><div><small>REQUIREMENT ANALYSIS</small><h2>Readiness</h2></div></div>
            <div v-if="readiness" class="metric-grid">
              <div><small>Stage</small><strong>{{ readiness.stage }}</strong></div>
              <div><small>Completeness</small><strong>{{ readiness.completeness_score }}</strong></div>
              <div><small>Preliminary</small><strong>{{ readiness.can_generate_preliminary_solution ? 'Eligible' : 'Blocked' }}</strong></div>
              <div><small>Formal</small><strong>{{ readiness.can_generate_formal_solution ? 'Eligible' : 'Blocked' }}</strong></div>
            </div>
            <p v-else class="empty">Load sources and run Analyze Requirements.</p>
          </section>

          <section v-if="currentState" class="panel">
            <div class="panel-heading"><div><small>CUSTOMER TRUTH CANDIDATES</small><h2>Requirements</h2></div><span>{{ currentState.items.length }} items</span></div>
            <div class="table-wrap">
              <table>
                <thead><tr><th>Select</th><th>Category</th><th>Subject</th><th>Value</th><th>Status</th><th>Confirmation</th><th>Provenance</th><th>Detail</th></tr></thead>
                <tbody>
                  <tr v-for="item in currentState.items" :key="item.requirement_id">
                    <td><input v-model="selectedIds" type="checkbox" :value="item.requirement_id" :disabled="['rejected','superseded'].includes(item.status) || (item.status === 'confirmed' && item.confirmation_level === 'customer')" /></td>
                    <td>{{ item.category }}</td><td>{{ item.subject }}</td><td>{{ item.value }}</td>
                    <td><span :class="['status', `status--${item.status}`]">{{ item.status }}</span></td>
                    <td>{{ item.confirmation_level }}</td><td>{{ item.provenance }}</td>
                    <td><details><summary>Open</summary><pre>{{ JSON.stringify({ requirement_id: item.requirement_id, source_refs: item.source_refs, confidence: item.confidence, parameters: item.parameters }, null, 2) }}</pre></details></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <div v-if="currentState" class="three-columns">
            <section class="panel compact"><h3>Gaps</h3><article v-for="gap in currentState.gaps" :key="gap.gap_id" class="record"><b>{{ gap.category }} · {{ gap.gap_type }}</b><span>{{ gap.description }}</span></article><p v-if="!currentState.gaps.length" class="empty">No gaps</p></section>
            <section class="panel compact"><h3>Conflicts</h3><article v-for="conflict in currentState.conflicts" :key="conflict.conflict_id" class="record record--danger"><b>{{ conflict.category }} · {{ conflict.status }}</b><span>{{ conflict.description }}</span></article><p v-if="!currentState.conflicts.length" class="empty">No conflicts</p></section>
            <section class="panel compact"><h3>Next Best Questions</h3><article v-for="question in session.analysis.next_questions" :key="question.question_id" class="record"><b>{{ question.priority }} · {{ question.target_category }}</b><span>{{ question.text }}</span></article><p v-if="!session.analysis.next_questions.length" class="empty">No questions</p></section>
          </div>

          <section v-if="currentState" class="panel confirmation-panel">
            <div><small>EXPLICIT HUMAN ACTION</small><h2>Confirmation</h2></div>
            <label>Level<select v-model="confirmationLevel"><option value="internal">Internal</option><option value="customer">Customer</option></select></label>
            <label>confirmed_by<input v-model="confirmedBy" /></label>
            <label>note<input v-model="confirmationNote" /></label>
            <button class="button" :disabled="loading || !selectedIds.length" @click="confirmSelected">Confirm Selected ({{ selectedIds.length }})</button>
            <strong v-if="session.baseline" class="success">RequirementBaseline v{{ session.baseline.baseline_version }} created</strong>
          </section>
        </div>
      </section>

      <section v-else-if="activeTab === 'Solution'" class="content-stack">
        <section class="panel action-panel">
          <div><small>FROZEN ENGINE HANDOFF</small><h2>RequirementBaseline → B-M8</h2><p v-if="!session.baseline">Compile is disabled because no formal customer-confirmed Baseline exists.</p></div>
          <button class="button" :disabled="loading || !session.baseline" @click="compileSolution">{{ loading === 'compile' ? 'Compiling…' : 'Compile Solution' }}</button>
        </section>

        <section v-if="session.processSpec" class="panel">
          <div class="panel-heading"><div><small>PROCESS SPEC V1</small><h2>Structured Handoff</h2></div><button class="link" @click="rawKey='ProcessSpec'; rawOpen=true">Raw JSON</button></div>
          <dl class="definition-grid">
            <div v-for="field in ['industry','department','business_goal','roles','available_data','existing_systems','constraints','target_metrics','readiness_score']" :key="field"><dt>{{ field }}</dt><dd>{{ typeof session.processSpec[field] === 'object' ? JSON.stringify(session.processSpec[field]) : session.processSpec[field] }}</dd></div>
          </dl>
        </section>

        <section v-if="session.solutionBundle" class="panel">
          <div class="panel-heading"><div><small>SOLUTION BUNDLE V2</small><h2>Three Frozen Strategies</h2></div></div>
          <div class="plan-grid">
            <button v-for="plan in session.solutionBundle.plans" :key="plan.solution_id" :class="['plan-card', { selected: currentPlan?.solution_id === plan.solution_id }]" @click="selectedPlanId = plan.solution_id">
              <span v-if="plan.solution_id === session.solutionBundle.recommended_solution_id" class="badge">RECOMMENDED</span>
              <small>{{ plan.display_strategy }}</small><h3>{{ plan.name }}</h3><p>{{ plan.summary }}</p><strong>{{ plan.review_score }}</strong><span>{{ plan.primary_asset_ids.join(', ') }}</span>
            </button>
          </div>
        </section>

        <section v-if="currentPlan" class="panel">
          <div class="panel-heading"><div><small>SOLUTION DETAIL</small><h2>{{ currentPlan.name }}</h2></div></div>
          <div class="detail-columns">
            <div><h3>Fit Assessments</h3><pre>{{ JSON.stringify(currentPlan.fit_assessments, null, 2) }}</pre></div>
            <div><h3>Reuse Decisions</h3><pre>{{ JSON.stringify(currentPlan.reuse_decisions, null, 2) }}</pre></div>
            <div><h3>Selected Components</h3><pre>{{ JSON.stringify(currentPlan.selected_components, null, 2) }}</pre></div>
            <div><h3>Implementation</h3><ul><li v-for="item in currentPlan.implementation_steps" :key="item">{{ item }}</li></ul><h3>Risks / Assumptions</h3><pre>{{ JSON.stringify({ risks: currentPlan.risks, assumptions: currentPlan.assumptions }, null, 2) }}</pre></div>
            <div><h3>Evidence</h3><pre>{{ JSON.stringify(currentPlan.evidence_refs, null, 2) }}</pre></div>
            <div><h3>Value Claims</h3><pre>{{ JSON.stringify(currentPlan.value_claims, null, 2) }}</pre></div>
          </div>
        </section>

        <section v-if="session.blueprint" class="panel">
          <div class="panel-heading"><div><small>RECOMMENDED PLAN</small><h2>DemoBlueprint</h2></div><button class="link" @click="rawKey='DemoBlueprint'; rawOpen=true">Raw JSON</button></div>
          <div class="node-list"><article v-for="node in session.blueprint.nodes" :key="node.id" :class="['node', { 'node--gate': node.human_gate }]"><small>{{ node.node_type }} · {{ node.executor }}</small><strong>{{ node.name }}</strong><span>{{ node.id }}</span></article></div>
        </section>

        <section v-if="session.blueprint" class="panel">
          <div class="panel-heading"><div><small>TRACEABILITY</small><h2>Approval Threshold Closure</h2></div></div>
          <div class="trace"><div><small>Customer Requirement</small><strong>{{ approvalRequirement?.value }}</strong><span>{{ approvalRequirement?.requirement_id }}</span></div><i>→</i><div><small>ProcessSpec Constraint</small><strong>{{ processApproval?.parameters?.threshold }}</strong><span>{{ processApproval?.id }}</span></div><i>→</i><div><small>Solution</small><strong>{{ solutionApproval?.parameters?.threshold }}</strong><span>{{ session.recommendedSolution?.solution_id }}</span></div><i>→</i><div><small>DemoBlueprint Node</small><strong>{{ gateNode?.id }}</strong><span>{{ gateNode?.gate_reason }}</span></div></div>
        </section>
      </section>

      <section v-else class="content-stack">
        <section class="panel action-panel">
          <div><small>CUSTOMER FEEDBACK SOURCE</small><h2>Feedback Analysis</h2><p>Current Baseline v{{ session.baseline?.baseline_version || '—' }}</p></div>
          <textarea v-model="session.feedback" rows="3" />
          <button class="button" :disabled="loading || !session.baseline || !session.analysis" @click="analyzeFeedback">Analyze Feedback</button>
        </section>

        <section v-if="feedbackCandidate" class="panel">
          <div class="feedback-compare"><div><small>OLD REQUIREMENT</small><strong>{{ oldApproval?.value }}</strong><span>{{ oldApproval?.requirement_id }}</span></div><div><small>NEW CANDIDATE</small><strong>{{ feedbackCandidate.value }}</strong><span :class="['status', `status--${feedbackCandidate.status}`]">{{ feedbackCandidate.status }}</span></div><div><small>CONFLICT / QUESTION</small><strong>{{ openApprovalConflict?.conflict_id }}</strong><span>{{ session.analysis.next_questions?.[0]?.text }}</span></div></div>
          <div class="button-row"><span>Customer must explicitly confirm the new candidate.</span><button class="button" :disabled="loading || !selectedIds.length" @click="confirmationLevel='customer'; confirmSelected()">Customer Confirm</button></div>
        </section>

        <section v-if="session.previousBaseline && session.baseline?.baseline_version === 2" class="panel action-panel">
          <div><small>BASELINE VERSION CHANGE</small><h2>Requirement Diff &amp; Route</h2><p>v{{ session.previousBaseline.baseline_version }} → v{{ session.baseline.baseline_version }}</p></div>
          <button class="button" :disabled="Boolean(loading)" @click="buildDiff">Build Diff</button>
        </section>

        <section v-if="session.requirementDiff" class="panel">
          <p v-if="session.route.decision === 'no_op'" class="success">No effective business change</p>
          <div class="metric-grid">
            <div><small>Old value</small><strong>{{ oldApproval?.parameters?.threshold }}</strong></div>
            <div><small>New value</small><strong>{{ approvalRequirement?.parameters?.threshold }}</strong></div>
            <div><small>Route</small><strong>{{ session.route.decision }}</strong></div>
            <div><small>Categories</small><strong>{{ session.route.changed_categories.join(', ') }}</strong></div>
          </div>
          <div class="detail-columns"><div><h3>RequirementDiff</h3><pre>{{ JSON.stringify(session.requirementDiff, null, 2) }}</pre></div><div><h3>New Constraints</h3><pre>{{ JSON.stringify(session.route.new_constraints, null, 2) }}</pre></div></div>
          <button class="button" :disabled="loading || !session.route" @click="recompileSolution">Recompile Solution</button>
        </section>

        <section v-if="session.recompileResult" class="panel">
          <div class="panel-heading"><div><small>SOLUTION INTELLIGENCE DIFF</small><h2>Recompile Result</h2></div><span class="success">{{ session.recompileResult.decision }}</span></div>
          <div class="metric-grid">
            <div><small>Old approval</small><strong>{{ oldApproval?.parameters?.threshold }}</strong></div>
            <div><small>New approval</small><strong>{{ approvalRequirement?.parameters?.threshold }}</strong></div>
            <div><small>Constraint ID unchanged</small><strong>{{ processApproval?.id === session.recompileResult.solution.applied_constraints.find(c => c.type === 'approval')?.id ? 'YES' : 'NO' }}</strong></div>
            <div><small>Old 500k residue</small><strong>{{ residue500k }}</strong></div>
          </div>
          <dl class="definition-grid diff-grid">
            <div v-for="field in ['changed_asset_ids','changed_fit_asset_ids','changed_module_ids','reuse_mode_changes','added_demo_node_ids','removed_demo_node_ids','changed_demo_node_ids','value_claim_changes','explanations']" :key="field"><dt>{{ field }}</dt><dd>{{ JSON.stringify(session.recompileResult.recompile_result?.diff?.[field] ?? []) }}</dd></div>
          </dl>
        </section>
      </section>
    </main>

    <div v-if="rawOpen" class="drawer-backdrop" @click.self="rawOpen = false">
      <aside class="drawer"><header><div><small>READ ONLY</small><h2>Raw JSON</h2></div><button class="button button--secondary" @click="rawOpen=false">Close</button></header><select v-model="rawKey"><option v-for="(_, key) in rawArtifacts" :key="key">{{ key }}</option></select><pre>{{ JSON.stringify(rawValue, null, 2) }}</pre></aside>
    </div>
  </div>
</template>
