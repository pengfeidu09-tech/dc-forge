<script setup>
import { computed, onMounted, ref } from 'vue'
import AppIcon from './components/AppIcon.vue'
import ScoreRing from './components/ScoreRing.vue'
import WorkflowMap from './components/WorkflowMap.vue'
import CapabilityGrid from './components/CapabilityGrid.vue'
import DetailPanel from './components/DetailPanel.vue'
import { useEnterprisePortal } from './composables/useEnterprisePortal'

const {
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
} = useEnterprisePortal()

const activeView = ref('overview')
const selectedPlanType = ref('balanced')
const assistantInput = ref('')

const views = [
  { id: 'overview', label: '企业招采驾驶舱', icon: 'grid' },
  { id: 'requirements', label: '需求版本', icon: 'flow' },
  { id: 'suppliers', label: '供应商风险', icon: 'shield' },
  { id: 'reviews', label: '文档审查', icon: 'check' },
  { id: 'solutions', label: '方案生成', icon: 'spark' },
  { id: 'assistant', label: 'AI 助手', icon: 'bot' },
]

const metricLabels = {
  raw_evidence: ['原始证据', 'database'],
  requirement_truth_items: ['需求真相', 'target'],
  suppliers: ['供应商画像', 'user'],
  document_review_samples: ['审查样本', 'check'],
  communications: ['沟通记录', 'flow'],
  rag_chunks: ['RAG知识块', 'layers'],
  eval_cases: ['评测问题', 'code'],
  adversarial_scenarios: ['异常剧本', 'warning'],
  requirements: ['需求对象', 'target'],
  meetings: ['会议纪要', 'flow'],
  documents: ['业务文档', 'layers'],
  wechat_threads: ['即时沟通', 'bot'],
  communication_timeline: ['沟通时间线', 'flow'],
  requirement_versions: ['需求版本', 'target'],
  vehicles: ['车辆与VIN', 'database'],
  shipments: ['物流批次', 'arrow'],
  delivery_batches: ['交付批次', 'flow'],
  acceptances: ['验收批次', 'check'],
  exceptions: ['异常记录', 'warning'],
  customer_invoices: ['客户发票', 'layers'],
  after_sales_cost_records: ['售后记录', 'shield'],
}

const selectedPlan = computed(() =>
  solutionBundle.value?.plans?.find((plan) => plan.plan_type === selectedPlanType.value)
    || solutionBundle.value?.plans?.[0],
)

const currentRequirement = computed(() => {
  const history = dashboard.value?.requirement_history
  return history?.versions?.find(
    (version) => version.requirement_version_id === history.applicable_version_id,
  )
})

const solutionUnavailable = computed(() =>
  dashboard.value?.solution_status?.status === 'not_available_for_project_type',
)

const solutionForbidden = computed(() =>
  dashboard.value?.solution_status?.status === 'forbidden_for_role',
)

function versionBudget(version) {
  return version.unit_budget_cny ?? version.budget?.unit_landed_price_cny_max ?? null
}

function versionMilestone(version) {
  return version.sop_date || version.expected_final_delivery_date || ''
}

function versionOccurredAt(version) {
  return version.valid_from || version.created_at || version.occurred_at || ''
}

function versionRecordedAt(version) {
  return version.recorded_at || version.confirmed_at || version.created_at || ''
}

function quantityUnit() {
  return dashboard.value?.portal_mode === 'vehicle_lifecycle' ? '台' : '套'
}

const riskCount = computed(() =>
  dashboard.value?.supplier_view?.suppliers?.reduce(
    (total, supplier) => total + (supplier.risk_records?.length || 0),
    0,
  ) || 0,
)

function submitAssistant() {
  const message = assistantInput.value
  assistantInput.value = ''
  askAssistant(message)
}

onMounted(loadDashboard)
</script>

<template>
  <div class="enterprise-shell">
    <aside class="enterprise-sidebar">
      <div class="enterprise-brand">
        <span class="enterprise-brand__mark"><AppIcon name="spark" :size="20" /></span>
        <div>
          <strong>DC FORGE</strong>
          <small>企业智能招采中心</small>
        </div>
      </div>

      <div class="sidebar-section-label">工作台</div>
      <nav class="enterprise-nav">
        <button
          v-for="view in views"
          :key="view.id"
          :class="{ active: activeView === view.id }"
          @click="activeView = view.id"
        >
          <AppIcon :name="view.icon" :size="18" />
          <span>{{ view.label }}</span>
        </button>
      </nav>

      <div class="sidebar-section-label sidebar-section-label--projects">项目资料库</div>
      <div class="enterprise-projects">
        <button
          v-for="project in projects"
          :key="project.project_id"
          :class="{ active: selectedProjectId === project.project_id }"
          @click="selectProject(project.project_id)"
        >
          <span>{{ project.project_id === 'PRJ-TENDER-001' ? '电' : project.project_id === 'PRJ-AUTO-001' ? '车' : '知' }}</span>
          <div>
            <strong>{{ project.project }}</strong>
            <small>{{ project.portal_ready ? '已接入知识服务' : '资料索引' }}</small>
          </div>
        </button>
      </div>

      <div class="enterprise-sidebar__footer">
        <span class="status-dot"></span>
          <div>
          <strong>MCP 工具就绪</strong>
            <small>只读 · ACL · as_of</small>
        </div>
      </div>
    </aside>

    <main class="enterprise-main">
      <header class="enterprise-topbar">
        <div>
          <small>ENTERPRISE PROCUREMENT INTELLIGENCE</small>
          <strong>{{ views.find((view) => view.id === activeView)?.label }}</strong>
        </div>
        <div class="viewer-controls">
          <label>
            <span>查看角色</span>
            <select v-model="selectedUserId" @change="updateViewer">
              <option v-for="role in roleOptions" :key="role.userId" :value="role.userId">
                {{ role.label }}
              </option>
            </select>
          </label>
          <label>
            <span>数据时间点</span>
            <input v-model="asOf" type="datetime-local" @change="updateViewer" />
          </label>
          <span class="viewer-badge"><AppIcon name="shield" :size="15" />{{ selectedRole?.label }}</span>
        </div>
      </header>

      <div v-if="loading" class="portal-state">
        <span class="portal-spinner"></span>
        <strong>正在读取企业知识服务</strong>
        <p>应用权限、时间点和证据规则……</p>
      </div>

      <div v-else-if="error" class="portal-state portal-state--error">
        <AppIcon name="warning" :size="32" />
        <strong>服务暂不可用</strong>
        <p>{{ error }}</p>
        <button @click="loadDashboard">重新连接</button>
      </div>

      <div v-else-if="dashboard" class="enterprise-content">
        <div class="synthetic-banner">
          <AppIcon name="shield" :size="17" />
          <span><b>模拟验收数据</b> {{ dashboard.disclaimer }} 页面中的数量是语料对象计数，方案评分与预期指标不是实际经营成果。</span>
          <code>{{ dashboard.data_classification }}</code>
        </div>

        <section v-if="activeView === 'overview'" class="portal-view">
          <div class="portal-hero">
            <div>
              <span class="portal-kicker">GOLDEN ACCEPTANCE PROJECT · {{ dashboard.project.project_id }}</span>
              <h1>{{ dashboard.project.project_name }}</h1>
              <p>{{ dashboard.project.customer_name }} · {{ dashboard.project.procurement_object }}</p>
              <div class="portal-tags">
                <span>{{ dashboard.project.industry }}</span>
                <span>{{ dashboard.project.department }}</span>
                <span v-if="dashboard.project.annual_quantity">数量 {{ dashboard.project.annual_quantity.toLocaleString() }}</span>
                <span>基线 {{ dashboard.project.confirmed_requirement_version_id }}</span>
              </div>
            </div>
            <div class="hero-pulse">
              <strong>{{ dashboard.procurement_stages.length }}</strong>
              <span>过程阶段</span>
              <small>按当前时间点展示</small>
            </div>
          </div>

          <div class="portal-metrics">
            <article v-for="(value, key) in dashboard.metrics" :key="key">
              <span><AppIcon :name="metricLabels[key]?.[1] || 'database'" :size="18" /></span>
              <div><strong>{{ value }}</strong><small>{{ metricLabels[key]?.[0] || key }}</small></div>
            </article>
          </div>

          <template v-if="dashboard.portal_mode === 'knowledge_management'">
            <section class="portal-panel">
              <div class="portal-panel__heading"><div><small>KNOWLEDGE PROJECT</small><h2>需求、会议与业务文档</h2></div><span>{{ dashboard.milestones.length }}个已发生里程碑</span></div>
              <div class="knowledge-project-grid">
                <article v-for="requirement in dashboard.requirements" :key="requirement.requirement_id">
                  <span>{{ requirement.requirement_id }}</span>
                  <h3>{{ requirement.name }}</h3>
                  <p>{{ requirement.business_problem }}</p>
                  <footer>{{ requirement.priority }} · {{ requirement.versions.length }}个版本 · {{ requirement.acceptance_criteria.length }}条验收条件</footer>
                </article>
              </div>
            </section>
          </template>

          <template v-else-if="dashboard.portal_mode === 'vehicle_lifecycle'">
            <section class="portal-panel">
              <div class="portal-panel__heading"><div><small>VEHICLE LIFECYCLE</small><h2>100台车辆与分批履约</h2></div><span>{{ dashboard.vehicles.length }}个唯一模拟VIN</span></div>
              <div class="vehicle-batch-grid">
                <article v-for="batch in dashboard.delivery_batches" :key="batch.delivery_batch_id">
                  <span>{{ batch.delivery_batch_id }}</span>
                  <strong>{{ batch.quantity }} 台</strong>
                  <small>{{ batch.delivery_location }} · {{ batch.status }}</small>
                </article>
              </div>
              <div class="mask-note"><AppIcon name="shield" :size="18" /><div><strong>角色化财务视图</strong><small>{{ dashboard.finance ? '当前角色可查看模拟财务结算' : '当前角色的财务金额已隐藏' }}</small></div></div>
            </section>
          </template>

          <section v-if="!dashboard.portal_mode" class="portal-panel">
            <div class="portal-panel__heading">
              <div><small>PROCUREMENT FLOW</small><h2>采购主链</h2></div>
              <span>与智能招采PPT业务链对齐</span>
            </div>
            <div class="procurement-chain">
              <article v-for="(stage, index) in dashboard.procurement_stages" :key="stage.code">
                <span>{{ String(index + 1).padStart(2, '0') }}</span>
                <strong>{{ stage.name }}</strong>
                <small>{{ stage.status.replace('_simulation', '') }}</small>
                <AppIcon v-if="index < dashboard.procurement_stages.length - 1" name="arrow" :size="16" />
              </article>
            </div>
          </section>

          <div v-if="!dashboard.portal_mode" class="portal-grid portal-grid--two">
            <section class="portal-panel">
              <div class="portal-panel__heading">
                <div><small>REQUIREMENT TRUTH</small><h2>当前需求基线</h2></div>
                <span>{{ dashboard.requirement_history.applicable_version_id }}</span>
              </div>
              <div v-if="currentRequirement" class="baseline-card">
                <strong>{{ currentRequirement.quantity.toLocaleString() }} 套</strong>
                <span>SOP {{ currentRequirement.sop_date }}</span>
                <span>单套预算上限 ¥{{ currentRequirement.unit_budget_cny.toLocaleString() }}</span>
              </div>
              <div class="open-items">
                <article v-for="item in dashboard.open_items" :key="item.item_id">
                  <AppIcon name="warning" :size="16" />
                  <div><strong>{{ item.topic }}</strong><small>{{ item.status }} · {{ item.due_date }}</small></div>
                </article>
              </div>
            </section>
            <section class="portal-panel">
              <div class="portal-panel__heading">
                <div><small>CONTROL CENTER</small><h2>能力与风险概览</h2></div>
                <span>{{ riskCount }} 条风险记录</span>
              </div>
              <div class="capability-pills">
                <span v-for="capability in dashboard.ai_acceptance_capabilities" :key="capability">
                  <AppIcon name="check" :size="14" />{{ capability }}
                </span>
              </div>
              <div class="mask-note">
                <AppIcon name="shield" :size="18" />
                <div><strong>权限决定已执行</strong><small>脱敏字段：{{ dashboard.viewer.masked_fields.join('、') || '无' }}</small></div>
              </div>
            </section>
          </div>
        </section>

        <section v-else-if="activeView === 'requirements'" class="portal-view">
          <div class="view-heading"><div><small>REQUIREMENT HISTORY</small><h1>需求版本与时间语义</h1></div><p>只展示在当前数据时间点已经发生且已经记录的版本。</p></div>
          <div class="requirement-timeline">
            <article
              v-for="version in dashboard.requirement_history?.versions || []"
              :key="version.requirement_version_id"
              :class="{ active: version.requirement_version_id === dashboard.requirement_history.applicable_version_id }"
            >
              <span class="timeline-dot"></span>
              <div class="timeline-card">
                <header><strong>{{ version.requirement_version_id }}</strong><span>{{ version.status }}</span></header>
                <div class="timeline-stats">
                  <span><b>{{ version.quantity.toLocaleString() }}</b>{{ quantityUnit() }}</span>
                  <span v-if="versionMilestone(version)"><b>{{ versionMilestone(version) }}</b>{{ version.sop_date ? 'SOP' : '最终交付' }}</span>
                  <span v-if="versionBudget(version) !== null"><b>¥{{ versionBudget(version).toLocaleString() }}</b>单{{ quantityUnit() }}预算上限</span>
                </div>
                <footer>形成 {{ versionOccurredAt(version) }}<br />记录 {{ versionRecordedAt(version) }}</footer>
              </div>
            </article>
          </div>
          <section v-if="dashboard.portal_mode === 'knowledge_management'" class="portal-panel">
            <div class="knowledge-project-grid">
              <article v-for="requirement in dashboard.requirements" :key="requirement.requirement_id">
                <span>{{ requirement.requirement_id }}</span><h3>{{ requirement.name }}</h3><p>{{ requirement.business_problem }}</p>
                <footer>{{ requirement.source_ids.join(' · ') }}</footer>
              </article>
            </div>
          </section>
          <section class="portal-panel">
            <div class="portal-panel__heading"><div><small>OPEN ITEMS</small><h2>非阻断未决事项</h2></div></div>
            <div class="review-list">
              <article v-for="item in dashboard.open_items" :key="item.item_id">
                <span class="severity medium">OPEN</span>
                <div><strong>{{ item.topic }}</strong><small>负责人：{{ item.owner }} · 截止：{{ item.due_date }}</small></div>
              </article>
            </div>
          </section>
        </section>

        <section v-else-if="activeView === 'suppliers'" class="portal-view">
          <div class="view-heading"><div><small>SUPPLIER INTELLIGENCE</small><h1>供应商风险与履约画像</h1></div><p>评分严格限定时间、工厂和品类，不自动形成中标。</p></div>
          <div class="supplier-grid">
            <article v-for="supplier in dashboard.supplier_view?.suppliers || []" :key="supplier.supplier_id" class="supplier-card">
              <header>
                <div><span>{{ supplier.supplier_id }}</span><h3>{{ supplier.supplier_name }}</h3><small>{{ supplier.factory_coverage.join(' · ') }}</small></div>
                <ScoreRing v-if="supplier.score_detail" :score="supplier.score_detail.final_score" :size="68" label="综合分" />
                <span v-else class="masked-score"><AppIcon name="shield" :size="18" />已脱敏</span>
              </header>
              <div class="supplier-certificates">
                <span v-for="cert in supplier.certificates" :key="cert.certificate_no" :class="cert.status">
                  {{ cert.certificate_type }} · {{ cert.status }}
                </span>
              </div>
              <div class="supplier-risks">
                <article v-for="risk in supplier.risk_records" :key="risk.risk_id">
                  <span :class="`severity ${risk.level}`">{{ risk.level }}</span>
                  <div><strong>{{ risk.type }}</strong><small>{{ risk.description }}</small></div>
                </article>
              </div>
              <footer>证据 {{ supplier.source_ids.join(' · ') }}</footer>
            </article>
          </div>
          <div v-if="!dashboard.supplier_view?.suppliers?.length" class="portal-state portal-state--inline"><AppIcon name="database" :size="30" /><strong>当前项目未配置供应商画像视图</strong><p>可返回企业招采驾驶舱查看该项目已有的真实数据对象。</p></div>
        </section>

        <section v-else-if="activeView === 'reviews'" class="portal-view">
          <div class="view-heading"><div><small>DOCUMENT REVIEW</small><h1>文档审查黄金样本</h1></div><p>{{ dashboard.document_reviews?.samples?.length ? '4份控制样本、6份缺陷样本，所有高影响命中进入人工复核。' : '当前项目或时间点没有可见的审查黄金样本。' }}</p></div>
          <div class="review-summary">
            <article><strong>{{ dashboard.document_reviews?.summary?.control || 0 }}</strong><span>控制样本</span></article>
            <article><strong>{{ dashboard.document_reviews?.summary?.defective || 0 }}</strong><span>缺陷样本</span></article>
            <article><strong>{{ dashboard.document_reviews?.summary?.findings || 0 }}</strong><span>预期命中</span></article>
            <article><strong>{{ dashboard.document_reviews?.rules?.length || 0 }}</strong><span>规则数量</span></article>
          </div>
          <section class="portal-panel">
            <div class="review-list">
              <article v-for="sample in dashboard.document_reviews?.samples || []" :key="sample.sample_id">
                <span :class="['sample-type', sample.sample_type]">{{ sample.sample_type }}</span>
                <div>
                  <strong>{{ sample.sample_id }} · {{ sample.document_type }}</strong>
                  <small v-if="sample.expected_findings.length">
                    {{ sample.expected_findings.map((finding) => `${finding.rule_id} / ${finding.severity}`).join('；') }}
                  </small>
                  <small v-else>无预期问题，用于控制误报。</small>
                </div>
                <span>{{ sample.expected_findings.length }} 项</span>
              </article>
            </div>
            <div v-if="!dashboard.document_reviews?.samples?.length" class="portal-state portal-state--inline"><AppIcon name="database" :size="30" /><strong>当前项目未配置文档审查黄金样本</strong><p>该能力在PRJ-TENDER-001中提供完整控制与缺陷样本。</p></div>
          </section>
        </section>

        <section v-else-if="activeView === 'solutions' && selectedPlan" class="portal-view">
          <div class="view-heading"><div><small>SOLUTION COMPILER</small><h1>方案生成与能力编排</h1></div><p>由Requirement Truth通过现有ProcessSpec和方案编译器生成。</p></div>
          <div class="solution-switcher">
            <button
              v-for="plan in solutionBundle.plans"
              :key="plan.solution_id"
              :class="{ active: selectedPlanType === plan.plan_type }"
              @click="selectedPlanType = plan.plan_type"
            >
              <span>{{ plan.plan_type }}</span><strong>{{ plan.name }}</strong><small>设计评分 {{ plan.review_score.toFixed(1) }}</small>
            </button>
          </div>
          <section class="solution-stage">
            <div class="solution-stage__header">
              <div><span>{{ selectedPlan.solution_id }}</span><h2>{{ selectedPlan.name }}</h2><p>{{ selectedPlan.summary }}</p></div>
              <ScoreRing :score="selectedPlan.review_score" :size="96" label="设计评分" />
            </div>
            <div class="solution-tabs-copy"><strong>目标流程</strong><span>{{ selectedPlan.to_be_nodes.length }}个节点 · {{ selectedPlan.to_be_nodes.filter((node) => node.human_gate).length }}个人工审批门</span></div>
            <WorkflowMap :nodes="selectedPlan.to_be_nodes" />
            <div class="solution-tabs-copy"><strong>能力组件</strong><span>{{ selectedPlan.selected_components.length }}项</span></div>
            <CapabilityGrid :components="selectedPlan.selected_components" />
            <DetailPanel :plan="selectedPlan" />
          </section>
        </section>

        <section v-else-if="activeView === 'solutions'" class="portal-view">
          <div class="view-heading"><div><small>SOLUTION COMPILER</small><h1>方案生成</h1></div></div>
          <div class="portal-state portal-state--inline">
            <AppIcon name="warning" :size="30" />
            <strong v-if="solutionUnavailable">当前项目仅提供知识与履约浏览</strong>
            <strong v-else-if="solutionForbidden">当前角色无权生成正式方案</strong>
            <strong v-else>当前时间点尚未形成正式需求基线</strong>
            <p v-if="solutionUnavailable">三套方案编译仅对PRJ-TENDER-001的Requirement Truth开放；可使用AI助手查询本项目资料。</p>
            <p v-else-if="solutionForbidden">请切换至采购负责人或法务财务复核角色；系统不会绕过权限生成方案。</p>
            <p v-else>需要记录 {{ dashboard.solution_status.required_source_id }}（{{ dashboard.solution_status.required_recorded_at }}）后才能生成正式三套方案。</p>
          </div>
        </section>

        <section v-else-if="activeView === 'assistant'" class="portal-view assistant-view">
          <div class="view-heading"><div><small>MCP-POWERED ASSISTANT</small><h1>AI 助手</h1></div><p>知识查询、供应商分析、文档审查和方案生成全部经MCP调用。</p></div>
          <div class="assistant-shell">
            <div class="assistant-intro">
              <span><AppIcon name="bot" :size="28" /></span>
              <div><strong>企业招采AI机器人</strong><small>当前项目 {{ selectedProjectId }} · {{ selectedRole?.label }}</small></div>
              <em>MCP ONLINE</em>
            </div>
            <div class="assistant-messages">
              <article v-for="(message, index) in assistantMessages" :key="index" :class="message.role">
                <span>{{ message.role === 'assistant' ? 'AI' : '你' }}</span>
                <div>
                  <p>{{ message.content }}</p>
                  <small v-if="message.toolName">工具：{{ message.toolName }}</small>
                  <div v-if="message.citations.length" class="citations">
                    <code v-for="citation in message.citations" :key="citation">{{ citation }}</code>
                  </div>
                </div>
              </article>
              <article v-if="assistantLoading" class="assistant"><span>AI</span><div><p>正在通过MCP调用受权限控制的工具……</p></div></article>
            </div>
            <form class="assistant-composer" @submit.prevent="submitAssistant">
              <input v-model="assistantInput" placeholder="例如：供应商三为什么未进入推荐？" />
              <button :disabled="assistantLoading"><AppIcon name="arrow" :size="18" />发送</button>
            </form>
            <div class="assistant-suggestions">
              <button @click="askAssistant('2026-08-14当时客户确认了什么？')">时间点需求</button>
              <button @click="askAssistant('供应商三为什么未进入推荐？')">供应商分析</button>
              <button @click="askAssistant('请生成这个项目的三套方案')">生成三套方案</button>
            </div>
          </div>
        </section>
      </div>
    </main>
  </div>
</template>
