<script setup>
import { computed, ref } from 'vue'
import AppIcon from './components/AppIcon.vue'
import AppSidebar from './components/AppSidebar.vue'
import CapabilityGrid from './components/CapabilityGrid.vue'
import DataImportModal from './components/DataImportModal.vue'
import DetailPanel from './components/DetailPanel.vue'
import MetricTile from './components/MetricTile.vue'
import PlanCard from './components/PlanCard.vue'
import ScoreRing from './components/ScoreRing.vue'
import WorkflowMap from './components/WorkflowMap.vue'
import { useSolutionData } from './composables/useSolutionData'

const {
  projects,
  selectedProjectId,
  selectedPlanType,
  selectedBundle,
  selectedInput,
  selectedPlan,
  totalPlans,
  averageScore,
  selectProject,
  replaceData,
} = useSolutionData()

const activeTab = ref('workflow')
const sidebarCollapsed = ref(false)
const importOpen = ref(false)
const jsonOpen = ref(false)

const selectedProject = computed(() =>
  projects.value.find((project) => project.project_id === selectedProjectId.value),
)

const recommendedType = computed(() => {
  const sorted = [...(selectedBundle.value?.plans || [])].sort(
    (left, right) => (right.review_score || 0) - (left.review_score || 0),
  )
  return sorted[0]?.plan_type
})

const humanGateCount = computed(
  () => selectedPlan.value?.to_be_nodes?.filter((node) => node.human_gate).length || 0,
)

const inputOutputDelta = computed(() => {
  if (!selectedInput.value || !selectedPlan.value) return 0
  return (selectedPlan.value.review_score || 0) - (selectedInput.value.review_score || 0)
})

const tabs = [
  { id: 'workflow', label: '流程蓝图', icon: 'flow' },
  { id: 'capabilities', label: '能力组件', icon: 'layers' },
  { id: 'delivery', label: '实施与价值', icon: 'target' },
]

function selectPlan(type) {
  selectedPlanType.value = type
  activeTab.value = 'workflow'
}

function handleImport({ type, raw }) {
  replaceData(type, raw)
}
</script>

<template>
  <div class="app-shell">
    <AppSidebar
      :projects="projects"
      :selected-id="selectedProjectId"
      :collapsed="sidebarCollapsed"
      @select="selectProject"
      @import="importOpen = true"
    />

    <main class="workspace">
      <header class="topbar">
        <div class="topbar__left">
          <button
            class="icon-button sidebar-toggle"
            aria-label="切换侧边栏"
            @click="sidebarCollapsed = !sidebarCollapsed"
          >
            <span></span><span></span><span></span>
          </button>
          <div class="breadcrumb">
            <span>方案工作台</span>
            <AppIcon name="chevron" :size="14" />
            <strong>{{ selectedProject?.meta.name }}</strong>
          </div>
        </div>
        <div class="topbar__right">
          <span class="data-status"><i></i> 数据已就绪</span>
          <button class="ghost-button" @click="jsonOpen = !jsonOpen">
            <AppIcon name="code" :size="17" />
            {{ jsonOpen ? '隐藏原始数据' : '查看原始数据' }}
          </button>
          <button class="primary-button" @click="importOpen = true">
            <AppIcon name="upload" :size="17" /> 导入 JSONL
          </button>
        </div>
      </header>

      <div v-if="selectedBundle && selectedPlan" class="workspace__content">
        <section class="hero">
          <div class="hero__glow hero__glow--one"></div>
          <div class="hero__glow hero__glow--two"></div>
          <div class="hero__content">
            <div class="eyebrow"><AppIcon name="spark" :size="15" /> SOLUTION FORGE</div>
            <div class="hero__title-row">
              <div>
                <h1>{{ selectedProject?.meta.name }}</h1>
                <p>{{ selectedPlan.summary }}</p>
              </div>
              <ScoreRing :score="selectedPlan.review_score" :size="104" label="方案评分" />
            </div>
            <div class="hero__meta">
              <span><b>项目 ID</b>{{ selectedBundle.project_id }}</span>
              <span><b>行业</b>{{ selectedProject?.meta.industry }}</span>
              <span><b>数据源</b>{{ selectedProject?.meta.source }}</span>
              <span><b>Schema</b>v{{ selectedPlan.schema_version }}</span>
            </div>
          </div>
          <div class="hero__signal">
            <span></span><span></span><span></span><span></span><span></span>
          </div>
        </section>

        <section class="overview-strip">
          <MetricTile
            icon="database"
            label="场景总数"
            :value="projects.length"
            hint="已成功解析"
            tone="blue"
          />
          <MetricTile
            icon="layers"
            label="候选方案"
            :value="totalPlans"
            hint="三种策略生成"
            tone="violet"
          />
          <MetricTile
            icon="target"
            label="平均评分"
            :value="averageScore.toFixed(1)"
            hint="跨全部方案"
            tone="green"
          />
          <MetricTile
            icon="spark"
            label="当前评分差"
            :value="`${inputOutputDelta >= 0 ? '+' : ''}${inputOutputDelta.toFixed(1)}`"
            hint="相较输入基线"
            tone="amber"
          />
        </section>

        <section class="strategy-section">
          <div class="section-heading">
            <div>
              <span class="section-heading__number">01</span>
              <div>
                <small>STRATEGY COMPARISON</small>
                <h2>选择方案策略</h2>
              </div>
            </div>
            <p>从风险控制、交付效率与智能化程度三个方向比较生成结果</p>
          </div>
          <div class="plan-grid">
            <PlanCard
              v-for="plan in selectedBundle.plans"
              :key="plan.solution_id"
              :plan="plan"
              :active="plan.plan_type === selectedPlanType"
              :recommended="plan.plan_type === recommendedType"
              @select="selectPlan(plan.plan_type)"
            />
          </div>
        </section>

        <Transition name="slide">
          <section v-if="jsonOpen" class="json-inspector">
            <div class="json-inspector__header">
              <div>
                <span>INPUT / 输入基线</span>
                <strong>{{ selectedInput?.solution_id || '未匹配输入' }}</strong>
              </div>
              <div>
                <span>OUTPUT / 当前输出</span>
                <strong>{{ selectedPlan.solution_id }}</strong>
              </div>
            </div>
            <div class="json-inspector__body">
              <pre>{{ JSON.stringify(selectedInput, null, 2) }}</pre>
              <pre>{{ JSON.stringify(selectedPlan, null, 2) }}</pre>
            </div>
          </section>
        </Transition>

        <section class="solution-section">
          <div class="solution-header">
            <div class="section-heading">
              <div>
                <span class="section-heading__number">02</span>
                <div>
                  <small>DESIGN BLUEPRINT</small>
                  <h2>{{ selectedPlan.name }}</h2>
                </div>
              </div>
              <p>{{ selectedPlan.summary }}</p>
            </div>
            <div class="solution-kpis">
              <span><b>{{ selectedPlan.selected_components.length }}</b>能力组件</span>
              <span><b>{{ selectedPlan.to_be_nodes.length }}</b>流程节点</span>
              <span><b>{{ humanGateCount }}</b>人工审批</span>
            </div>
          </div>

          <div class="content-tabs" role="tablist">
            <button
              v-for="tab in tabs"
              :key="tab.id"
              :class="{ active: activeTab === tab.id }"
              role="tab"
              :aria-selected="activeTab === tab.id"
              @click="activeTab = tab.id"
            >
              <AppIcon :name="tab.icon" :size="17" />
              {{ tab.label }}
              <span v-if="tab.id === 'capabilities'">{{ selectedPlan.selected_components.length }}</span>
            </button>
          </div>

          <div class="tab-content">
            <WorkflowMap
              v-if="activeTab === 'workflow'"
              :key="selectedPlan.solution_id"
              :nodes="selectedPlan.to_be_nodes"
            />
            <CapabilityGrid
              v-else-if="activeTab === 'capabilities'"
              :key="selectedPlan.solution_id"
              :components="selectedPlan.selected_components"
            />
            <DetailPanel v-else :key="selectedPlan.solution_id" :plan="selectedPlan" />
          </div>
        </section>

        <footer class="page-footer">
          <span>DC Forge · Decision Intelligence Workspace</span>
          <span>数据更新时间：刚刚</span>
        </footer>
      </div>

      <div v-else class="page-empty">
        <span><AppIcon name="database" :size="30" /></span>
        <h2>暂无可展示的方案</h2>
        <p>请导入包含项目与方案列表的 JSONL 输出文件。</p>
        <button class="primary-button" @click="importOpen = true">
          <AppIcon name="upload" :size="17" /> 导入数据
        </button>
      </div>
    </main>

    <DataImportModal :open="importOpen" @close="importOpen = false" @import="handleImport" />
  </div>
</template>
