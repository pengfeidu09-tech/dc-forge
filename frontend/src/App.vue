<script setup>
import { computed, onMounted, ref } from 'vue'
import AppIcon from './components/AppIcon.vue'
import ScoreRing from './components/ScoreRing.vue'
import WorkflowMap from './components/WorkflowMap.vue'
import CapabilityGrid from './components/CapabilityGrid.vue'
import DetailPanel from './components/DetailPanel.vue'
import IntelligenceConsole from './components/IntelligenceConsole.vue'
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
} = useEnterprisePortal()

const activeView = ref('overview')
const selectedPlanType = ref('balanced')
const assistantInput = ref('')

const views = [
  { id: 'overview', label: '企业招采驾驶舱', icon: 'grid' },
  { id: 'knowledge', label: '知识检索', icon: 'search' },
  { id: 'requirements', label: '需求版本', icon: 'flow' },
  { id: 'suppliers', label: '供应商风险', icon: 'shield' },
  { id: 'reviews', label: '文档审查', icon: 'check' },
  { id: 'solutions', label: '方案生成', icon: 'spark' },
  { id: 'tools', label: 'MCP 工具箱', icon: 'code' },
  { id: 'assistant', label: 'AI 助手', icon: 'bot' },
  { id: 'intelligence-console', label: '智能引擎控制台', icon: 'code' },
]

const metricLabels = {
  raw_evidence: ['原始证据', 'database'], requirement_truth_items: ['需求真相', 'target'],
  suppliers: ['供应商画像', 'user'], document_review_samples: ['审查样本', 'check'],
  communications: ['沟通记录', 'flow'], rag_chunks: ['RAG知识块', 'layers'],
  eval_cases: ['评测问题', 'code'], adversarial_scenarios: ['异常剧本', 'warning'],
  requirements: ['需求对象', 'target'], meetings: ['会议纪要', 'flow'],
  documents: ['业务文档', 'layers'], wechat_threads: ['即时沟通', 'bot'],
  communication_timeline: ['沟通时间线', 'flow'], requirement_versions: ['需求版本', 'target'],
  vehicles: ['车辆与VIN', 'database'], shipments: ['物流批次', 'arrow'],
  delivery_batches: ['交付批次', 'flow'], acceptances: ['验收批次', 'check'],
  exceptions: ['异常记录', 'warning'], customer_invoices: ['客户发票', 'layers'],
  after_sales_cost_records: ['售后记录', 'shield'],
}

const selectedPlan = computed(() =>
  solutionBundle.value?.plans?.find((plan) => plan.plan_type === selectedPlanType.value)
    || solutionBundle.value?.plans?.[0],
)
const currentRequirement = computed(() => {
  const history = dashboard.value?.requirement_history
  return history?.versions?.find((version) => version.requirement_version_id === history.applicable_version_id)
})
const solutionUnavailable = computed(() => dashboard.value?.solution_status?.status === 'not_available_for_project_type')
const solutionForbidden = computed(() => dashboard.value?.solution_status?.status === 'forbidden_for_role')
const riskCount = computed(() => dashboard.value?.supplier_view?.suppliers?.reduce(
  (total, supplier) => total + (supplier.risk_records?.length || 0), 0,
) || 0)

function versionBudget(version) { return version.unit_budget_cny ?? version.budget?.unit_landed_price_cny_max ?? null }
function versionMilestone(version) { return version.sop_date || version.expected_final_delivery_date || '' }
function versionOccurredAt(version) { return version.valid_from || version.created_at || version.occurred_at || '' }
function versionRecordedAt(version) { return version.recorded_at || version.confirmed_at || version.created_at || '' }
function quantityUnit() { return dashboard.value?.portal_mode === 'vehicle_lifecycle' ? '台' : '套' }
function submitAssistant() { const value = assistantInput.value; assistantInput.value = ''; askAssistant(value) }

const mcpFieldLabels = {
  project_id: '项目 ID', user_id: '用户 ID', as_of: '数据时间点', query: '查询内容',
  limit: '返回数量', requirement_id: '需求 ID', supplier_id: '供应商 ID', document_id: '文档 ID',
  decision_or_object_id: '决策或对象 ID', channel: '沟通渠道', object_id: '业务对象 ID',
  direction: '追踪方向', max_depth: '最大深度', contract_id: '合同 ID',
}
function isMcpFieldRequired(fieldName) { return selectedMcpTool.value?.inputSchema?.required?.includes(fieldName) || false }
function mcpFieldType(schema) { return schema.type === 'integer' ? 'number' : 'text' }
function knowledgeSource(result) { return result.source_id || result.source_ids?.join(' · ') || '未提供来源ID' }
const formattedMcpResult = computed(() => mcpResult.value ? JSON.stringify(mcpResult.value, null, 2) : '')

onMounted(() => { loadDashboard(); loadMcpTools() })
</script>

<template>
  <a-layout class="enterprise-shell enterprise-ant-shell">
    <a-layout-sider class="enterprise-sidebar" :width="260" breakpoint="lg" collapsed-width="0">
      <div class="enterprise-brand">
        <span class="enterprise-brand__mark"><AppIcon name="spark" :size="20" /></span>
        <div><strong>DC FORGE</strong><small>企业智能招采中心</small></div>
      </div>

      <a-button class="enterprise-workspace-link" type="primary" block href="/presales/workbench">
        <AppIcon name="flow" :size="16" />业务工作台 · 售前协作工作台
      </a-button>

      <div class="sidebar-section-label">门户功能</div>
      <a-menu
        theme="dark"
        mode="inline"
        :selected-keys="[activeView]"
        @click="({ key }) => activeView = key"
      >
        <a-menu-item v-for="view in views" :key="view.id">
          <AppIcon :name="view.icon" :size="17" /><span>{{ view.label }}</span>
        </a-menu-item>
      </a-menu>

      <div class="sidebar-section-label sidebar-section-label--projects">项目资料库</div>
      <a-list class="enterprise-projects" :data-source="projects" size="small">
        <template #renderItem="{ item: project }">
          <a-list-item>
            <a-button
              block
              :type="selectedProjectId === project.project_id ? 'primary' : 'text'"
              @click="selectProject(project.project_id)"
            >
              <span class="project-avatar">{{ project.project_id === 'PRJ-TENDER-001' ? '电' : project.project_id === 'PRJ-AUTO-001' ? '车' : '知' }}</span>
              <span class="project-copy"><strong>{{ project.project }}</strong><small>{{ project.portal_ready ? '已接入知识服务' : '资料索引' }}</small></span>
            </a-button>
          </a-list-item>
        </template>
      </a-list>

      <a-alert
        class="enterprise-sidebar__footer"
        :type="mcpConnected ? 'success' : 'warning'"
        :message="mcpConnected ? 'MCP 工具就绪' : 'MCP 尚未连接'"
        :description="mcpConnected ? `${mcpTools.length} 个只读工具` : '等待运行时响应'"
        show-icon
      />
    </a-layout-sider>

    <a-layout class="enterprise-main">
      <a-layout-header class="enterprise-topbar">
        <div class="topbar-title"><small>ENTERPRISE PROCUREMENT INTELLIGENCE</small><strong>{{ views.find((view) => view.id === activeView)?.label }}</strong></div>
        <a-space v-if="activeView !== 'intelligence-console'" class="viewer-controls" wrap>
          <a-select v-model:value="selectedUserId" style="width: 180px" @change="updateViewer">
            <a-select-option v-for="role in roleOptions" :key="role.userId" :value="role.userId">查看角色 · {{ role.label }}</a-select-option>
          </a-select>
          <a-input v-model:value="asOf" type="datetime-local" style="width: 210px" @change="updateViewer" />
          <a-tag color="blue"><AppIcon name="shield" :size="14" /> {{ selectedRole?.label }}</a-tag>
        </a-space>
      </a-layout-header>

      <a-layout-content class="enterprise-content enterprise-ant-content">
        <IntelligenceConsole v-if="activeView === 'intelligence-console'" />

        <a-result v-else-if="error" status="error" title="服务暂不可用" :sub-title="error">
          <template #extra><a-button type="primary" @click="loadDashboard">重新连接</a-button></template>
        </a-result>
        <div v-else-if="loading" class="portal-loading"><a-spin size="large" tip="正在读取企业知识服务…" /></div>

        <template v-else-if="dashboard">
          <a-alert
            class="portal-section"
            type="warning"
            show-icon
            message="模拟验收数据"
            :description="`${dashboard.disclaimer} 页面中的数量是语料对象计数，方案评分与预期指标不是实际经营成果。`"
          />

          <section v-if="activeView === 'overview'" class="portal-view">
            <a-card class="portal-section portal-hero-card" :bordered="false">
              <a-row align="middle" justify="space-between" :gutter="[24, 24]">
                <a-col :xs="24" :lg="18">
                  <a-typography-text type="secondary">GOLDEN ACCEPTANCE PROJECT · {{ dashboard.project.project_id }}</a-typography-text>
                  <a-typography-title :level="2">{{ dashboard.project.project_name }}</a-typography-title>
                  <a-typography-paragraph>{{ dashboard.project.customer_name }} · {{ dashboard.project.procurement_object }}</a-typography-paragraph>
                  <a-space wrap>
                    <a-tag color="blue">{{ dashboard.project.industry }}</a-tag>
                    <a-tag>{{ dashboard.project.department }}</a-tag>
                    <a-tag v-if="dashboard.project.annual_quantity">数量 {{ dashboard.project.annual_quantity.toLocaleString() }}</a-tag>
                    <a-tag color="green">基线 {{ dashboard.project.confirmed_requirement_version_id }}</a-tag>
                  </a-space>
                </a-col>
                <a-col :xs="24" :lg="6"><a-statistic title="过程阶段" :value="dashboard.procurement_stages.length" suffix="项" /></a-col>
              </a-row>
            </a-card>

            <a-row class="portal-section" :gutter="[14, 14]">
              <a-col v-for="(value, key) in dashboard.metrics" :key="key" :xs="12" :md="8" :xl="6">
                <a-card size="small" :bordered="false"><a-statistic :title="metricLabels[key]?.[0] || key" :value="value"><template #prefix><AppIcon :name="metricLabels[key]?.[1] || 'database'" /></template></a-statistic></a-card>
              </a-col>
            </a-row>

            <a-card v-if="dashboard.portal_mode === 'knowledge_management'" class="portal-section" title="需求、会议与业务文档" :bordered="false">
              <template #extra><a-tag>{{ dashboard.milestones.length }} 个已发生里程碑</a-tag></template>
              <a-list :data-source="dashboard.requirements" :grid="{ gutter: 16, column: 2 }">
                <template #renderItem="{ item }"><a-list-item><a-card size="small" :title="item.name"><a-tag>{{ item.requirement_id }}</a-tag><p>{{ item.business_problem }}</p><small>{{ item.priority }} · {{ item.versions.length }} 个版本 · {{ item.acceptance_criteria.length }} 条验收条件</small></a-card></a-list-item></template>
              </a-list>
              <a-space><a-tag>会议纪要</a-tag><a-tag>业务文档</a-tag></a-space>
            </a-card>

            <a-card v-else-if="dashboard.portal_mode === 'vehicle_lifecycle'" class="portal-section" title="100台车辆与分批履约" :bordered="false">
              <template #extra><a-tag>车辆与VIN · {{ dashboard.vehicles.length }}</a-tag></template>
              <a-table :data-source="dashboard.delivery_batches" :pagination="false" row-key="delivery_batch_id" size="small">
                <a-table-column key="delivery_batch_id" title="交付批次" data-index="delivery_batch_id" />
                <a-table-column key="quantity" title="数量" data-index="quantity" />
                <a-table-column key="delivery_location" title="交付地点" data-index="delivery_location" />
                <a-table-column key="status" title="状态" data-index="status" />
              </a-table>
              <a-alert class="inline-alert" type="info" show-icon :message="dashboard.finance ? '当前角色可查看模拟财务结算' : '当前角色的财务金额已隐藏'" />
            </a-card>

            <template v-else>
              <a-card class="portal-section" title="采购主链" :bordered="false">
                <template #extra><a-tag>与智能招采 PPT 业务链对齐</a-tag></template>
                <a-steps :items="dashboard.procurement_stages.map((stage) => ({ title: stage.name, description: stage.status.replace('_simulation', '') }))" size="small" responsive />
              </a-card>
              <a-row :gutter="[16, 16]">
                <a-col :xs="24" :xl="12">
                  <a-card title="当前需求基线" :bordered="false">
                    <a-descriptions v-if="currentRequirement" bordered size="small" :column="1">
                      <a-descriptions-item label="版本">{{ currentRequirement.requirement_version_id }}</a-descriptions-item>
                      <a-descriptions-item label="预算">{{ versionBudget(currentRequirement) || '待确认' }}</a-descriptions-item>
                      <a-descriptions-item label="里程碑">{{ versionMilestone(currentRequirement) || '待确认' }}</a-descriptions-item>
                    </a-descriptions>
                    <a-list :data-source="dashboard.open_items" size="small"><template #renderItem="{ item }"><a-list-item><a-list-item-meta :title="item.topic" :description="`${item.status} · ${item.due_date}`" /></a-list-item></template></a-list>
                  </a-card>
                </a-col>
                <a-col :xs="24" :xl="12"><a-card title="能力与风险概览" :bordered="false"><a-statistic title="供应商风险记录" :value="riskCount" /><a-divider /><a-space wrap><a-tag v-for="capability in dashboard.capabilities" :key="capability" color="blue">{{ capability }}</a-tag></a-space><a-alert class="inline-alert" type="info" show-icon :message="`脱敏字段：${dashboard.viewer.masked_fields.join('、') || '无'}`" /></a-card></a-col>
              </a-row>
            </template>
          </section>

          <section v-else-if="activeView === 'knowledge'" class="portal-view">
            <a-card class="portal-section" title="企业知识检索" :bordered="false">
              <template #extra><a-tag>GOVERNED KNOWLEDGE SEARCH</a-tag></template>
              <a-input-search v-model:value="knowledgeQuery" size="large" enter-button="检索" :loading="knowledgeLoading" placeholder="检索需求、制度、供应商、案例与历史沟通" @search="searchKnowledge" />
              <a-alert v-if="knowledgeError" class="inline-alert" type="error" show-icon :message="knowledgeError" />
              <a-result v-else-if="knowledgeMeta?.insufficient_evidence" status="info" title="当前证据不足" sub-title="系统不会在证据不足时补造结论。" />
              <a-list v-else :data-source="knowledgeResults" item-layout="vertical" class="knowledge-results">
                <template #renderItem="{ item }"><a-list-item><a-list-item-meta :title="item.title || knowledgeSource(item)" :description="knowledgeSource(item)" /><p>{{ item.snippet || item.content_preview || item.content }}</p><a-tag v-for="sourceId in item.source_ids || []" :key="sourceId">{{ sourceId }}</a-tag></a-list-item></template>
              </a-list>
              <a-empty v-if="!knowledgeLoading && !knowledgeError && !knowledgeResults.length && !knowledgeMeta?.insufficient_evidence" description="输入关键词开始检索" />
            </a-card>
          </section>

          <section v-else-if="activeView === 'requirements'" class="portal-view">
            <a-card class="portal-section" title="需求版本与时间语义" :bordered="false">
              <a-timeline>
                <a-timeline-item v-for="version in dashboard.requirement_history.versions" :key="version.requirement_version_id" :color="version.requirement_version_id === dashboard.requirement_history.applicable_version_id ? 'blue' : 'gray'">
                  <a-card size="small" :title="version.requirement_version_id"><a-space wrap><a-tag>{{ version.status }}</a-tag><a-tag>预算 {{ versionBudget(version) || '待确认' }}</a-tag><a-tag>里程碑 {{ versionMilestone(version) || '待确认' }}</a-tag></a-space><p>形成 {{ versionOccurredAt(version) }} · 记录 {{ versionRecordedAt(version) }}</p></a-card>
                </a-timeline-item>
              </a-timeline>
              <a-divider orientation="left">非阻断未决事项</a-divider>
              <a-table :data-source="dashboard.open_items" :pagination="false" row-key="item_id" size="small">
                <a-table-column key="topic" title="事项" data-index="topic" /><a-table-column key="owner" title="负责人" data-index="owner" /><a-table-column key="status" title="状态" data-index="status" /><a-table-column key="due_date" title="截止时间" data-index="due_date" />
              </a-table>
            </a-card>
          </section>

          <section v-else-if="activeView === 'suppliers'" class="portal-view">
            <a-card class="portal-section" title="供应商风险与履约画像" :bordered="false">
              <a-row :gutter="[16, 16]">
                <a-col v-for="supplier in dashboard.supplier_view?.suppliers || []" :key="supplier.supplier_id" :xs="24" :xl="12">
                  <a-card :title="supplier.supplier_name" size="small">
                    <template #extra><ScoreRing v-if="supplier.score_detail" :score="supplier.score_detail.final_score" :size="68" label="综合分" /><a-tag v-else>已脱敏</a-tag></template>
                    <a-typography-text type="secondary">{{ supplier.supplier_id }} · {{ supplier.factory_coverage.join(' · ') }}</a-typography-text>
                    <a-divider orientation="left">证书</a-divider><a-space wrap><a-tag v-for="cert in supplier.certificates" :key="cert.certificate_no" :color="cert.status === 'valid' ? 'green' : 'orange'">{{ cert.certificate_no }}</a-tag></a-space>
                    <a-list :data-source="supplier.risk_records" size="small"><template #header><strong>风险记录</strong></template><template #renderItem="{ item }"><a-list-item><a-list-item-meta :title="item.type" :description="item.description" /><a-tag :color="item.level === 'high' ? 'red' : 'orange'">{{ item.level }}</a-tag></a-list-item></template></a-list>
                  </a-card>
                </a-col>
              </a-row>
              <a-empty v-if="!dashboard.supplier_view?.suppliers?.length" description="当前项目未配置供应商画像视图" />
            </a-card>
          </section>

          <section v-else-if="activeView === 'reviews'" class="portal-view">
            <a-card class="portal-section" title="文档审查黄金样本" :bordered="false">
              <a-row :gutter="16"><a-col :span="6"><a-statistic title="控制样本" :value="dashboard.document_reviews?.summary?.control || 0" /></a-col><a-col :span="6"><a-statistic title="缺陷样本" :value="dashboard.document_reviews?.summary?.defective || 0" /></a-col><a-col :span="6"><a-statistic title="预期命中" :value="dashboard.document_reviews?.summary?.findings || 0" /></a-col><a-col :span="6"><a-statistic title="规则数量" :value="dashboard.document_reviews?.rules?.length || 0" /></a-col></a-row>
              <a-table class="review-table" :data-source="dashboard.document_reviews?.samples || []" :pagination="false" row-key="sample_id" size="small">
                <a-table-column key="sample_id" title="样本" data-index="sample_id" /><a-table-column key="sample_type" title="类型" data-index="sample_type" /><a-table-column key="title" title="文档" data-index="title" />
              </a-table>
              <a-empty v-if="!dashboard.document_reviews?.samples?.length" description="当前项目未配置文档审查黄金样本" />
            </a-card>
          </section>

          <section v-else-if="activeView === 'solutions'" class="portal-view">
            <a-card v-if="selectedPlan" class="portal-section" title="方案生成与能力编排" :bordered="false">
              <a-segmented v-model:value="selectedPlanType" :options="solutionBundle.plans.map((plan) => ({ label: plan.name, value: plan.plan_type }))" block />
              <a-tabs class="solution-detail-tabs">
                <a-tab-pane key="workflow" tab="目标流程"><a-row :gutter="16"><a-col :xs="24" :xl="5"><ScoreRing :score="selectedPlan.review_score" :size="96" label="设计评分" /></a-col><a-col :xs="24" :xl="19"><a-typography-title :level="3">{{ selectedPlan.name }}</a-typography-title><a-typography-paragraph>{{ selectedPlan.summary }}</a-typography-paragraph><a-tag>{{ selectedPlan.solution_id }}</a-tag></a-col></a-row><WorkflowMap :nodes="selectedPlan.to_be_nodes" /></a-tab-pane>
                <a-tab-pane key="capabilities" tab="能力组件"><CapabilityGrid :components="selectedPlan.selected_components" /></a-tab-pane>
                <a-tab-pane key="delivery" tab="实施与边界"><DetailPanel :plan="selectedPlan" /></a-tab-pane>
              </a-tabs>
            </a-card>
            <a-result v-else status="warning" title="当前时间点不能生成正式方案" :sub-title="solutionUnavailable ? '当前项目仅提供知识与履约浏览' : solutionForbidden ? '当前角色无权生成正式方案' : `需要记录 ${dashboard.solution_status.required_source_id || '需求基线'} 后才能生成正式三套方案。`" />
          </section>

          <section v-else-if="activeView === 'tools'" class="portal-view">
            <a-card class="portal-section" title="MCP 工具箱" :bordered="false">
              <template #extra><a-tag :color="mcpConnected ? 'green' : 'orange'">{{ mcpConnected ? `${mcpTools.length} 个运行时工具` : '连接中' }}</a-tag></template>
              <a-layout class="mcp-workbench">
                <a-layout-sider theme="light" :width="300"><a-menu :selected-keys="[selectedMcpToolName]" @click="({ key }) => selectMcpTool(key)"><a-menu-item v-for="tool in mcpTools" :key="tool.name"><strong>{{ tool.name }}</strong></a-menu-item></a-menu></a-layout-sider>
                <a-layout-content class="mcp-console">
                  <a-result v-if="mcpError && !selectedMcpTool" status="error" title="MCP 服务不可用" :sub-title="mcpError"><template #extra><a-button @click="loadMcpTools">重新连接</a-button></template></a-result>
                  <template v-else-if="selectedMcpTool">
                    <a-typography-title :level="4">{{ selectedMcpTool.description }}</a-typography-title>
                    <a-form layout="vertical" @submit.prevent="runMcpTool">
                      <a-form-item v-for="(schema, fieldName) in selectedMcpTool.inputSchema.properties" :key="fieldName" :label="mcpFieldLabels[fieldName] || fieldName" :required="isMcpFieldRequired(fieldName)"><a-input v-model:value="mcpArguments[fieldName]" :type="mcpFieldType(schema)" :readonly="['project_id', 'user_id', 'as_of'].includes(fieldName)" /></a-form-item>
                      <a-button type="primary" html-type="submit" :loading="mcpLoading">运行工具</a-button>
                    </a-form>
                    <a-alert v-if="mcpError" class="inline-alert" type="error" :message="mcpError" />
                    <a-divider orientation="left">structuredContent</a-divider><pre v-if="formattedMcpResult">{{ formattedMcpResult }}</pre><a-empty v-else description="等待工具调用" />
                  </template>
                </a-layout-content>
              </a-layout>
            </a-card>
          </section>

          <section v-else-if="activeView === 'assistant'" class="portal-view">
            <a-card class="portal-section assistant-shell" title="企业招采 AI 助手" :bordered="false">
              <template #extra><a-tag :color="mcpConnected ? 'green' : 'orange'">{{ mcpConnected ? 'MCP READY' : 'MCP OFFLINE' }}</a-tag></template>
              <a-list class="assistant-messages" :data-source="assistantMessages" item-layout="horizontal">
                <template #renderItem="{ item }"><a-list-item><a-list-item-meta :title="item.role === 'assistant' ? 'AI 助手' : '你'" :description="item.content" /><a-space wrap><a-tag v-if="item.toolName">工具：{{ item.toolName }}</a-tag><a-tag v-for="citation in item.citations" :key="citation">{{ citation }}</a-tag></a-space></a-list-item></template>
              </a-list>
              <a-spin v-if="assistantLoading" tip="正在通过 MCP 调用受权限控制的工具…" />
              <a-input-search v-model:value="assistantInput" size="large" enter-button="发送" :loading="assistantLoading" placeholder="例如：供应商三为什么未进入推荐？" @search="submitAssistant" />
              <a-space class="assistant-suggestions" wrap><a-button @click="askAssistant('2026-08-14当时客户确认了什么？')">时间点需求</a-button><a-button @click="askAssistant('供应商三为什么未进入推荐？')">供应商分析</a-button><a-button @click="askAssistant('请生成这个项目的三套方案')">生成三套方案</a-button></a-space>
            </a-card>
          </section>
        </template>
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>
