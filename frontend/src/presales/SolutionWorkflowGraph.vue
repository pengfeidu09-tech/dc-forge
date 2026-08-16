<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Handle, VueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import { ApartmentOutlined, SafetyCertificateOutlined } from '@ant-design/icons-vue'
import { buildSolutionWorkflowGraph } from './solutionWorkflowGraph'

import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'

const props = defineProps({
  plan: { type: Object, default: null },
})

const compact = ref(false)
const compactQuery = window.matchMedia('(max-width: 700px)')
const syncCompact = () => { compact.value = compactQuery.matches }

const graph = computed(() => buildSolutionWorkflowGraph(
  props.plan,
  { columns: compact.value ? 1 : 4 },
))
const graphKey = computed(
  () => `${props.plan?.name || 'empty'}-${graph.value.nodes.length}-${compact.value ? 'compact' : 'wide'}`,
)
const defaultViewport = computed(() => compact.value
  ? { x: 60, y: 18, zoom: 0.9 }
  : { x: 0, y: 0, zoom: 1 })

function executorClass(executor) {
  return { AI: 'ai', 系统: 'system', 人工: 'human' }[executor] || 'system'
}

function minimapNodeColor(node) {
  if (node.data?.humanGate) return '#c2410c'
  return { AI: '#2563eb', 系统: '#0f766e', 人工: '#7c3aed' }[node.data?.executor] || '#64748b'
}

onMounted(() => {
  syncCompact()
  compactQuery.addEventListener('change', syncCompact)
})
onBeforeUnmount(() => compactQuery.removeEventListener('change', syncCompact))
</script>

<template>
  <div class="solution-flow-graph">
    <div class="solution-flow-legend" aria-label="流程节点图例">
      <span class="ai"><i></i>AI 执行</span>
      <span class="system"><i></i>系统执行</span>
      <span class="human"><i></i>人工执行</span>
      <span class="gate"><i></i>人工审批门</span>
    </div>

    <div v-if="graph.nodes.length" class="solution-flow-canvas">
      <VueFlow
        :key="graphKey"
        :nodes="graph.nodes"
        :edges="graph.edges"
        :nodes-draggable="false"
        :nodes-connectable="false"
        :edges-updatable="false"
        :zoom-on-scroll="false"
        :pan-on-scroll="true"
        :min-zoom="0.35"
        :max-zoom="1.35"
        :default-viewport="defaultViewport"
        :fit-view-on-init="!compact"
        :fit-view-on-init-options="{ padding: 0.18, maxZoom: 1 }"
        class="solution-vue-flow"
      >
        <Background pattern-color="#cbd5e1" :gap="20" :size="1" />
        <Controls position="bottom-left" :show-interactive="false" />
        <MiniMap
          position="bottom-right"
          :node-color="minimapNodeColor"
          :pannable="true"
          :zoomable="true"
        />

        <template #node-workflowStep="{ data, sourcePosition, targetPosition }">
          <Handle type="target" :position="targetPosition" class="workflow-handle" />
          <article :class="['workflow-node', executorClass(data.executor), { gate: data.humanGate }]">
            <header>
              <span>{{ String(data.order).padStart(2, '0') }}</span>
              <em>{{ data.executor }}</em>
            </header>
            <strong>{{ data.label }}</strong>
            <footer v-if="data.humanGate">
              <SafetyCertificateOutlined />人工审批门
            </footer>
            <p v-if="data.gateReason">{{ data.gateReason }}</p>
            <ApartmentOutlined v-else class="node-type-icon" />
          </article>
          <Handle type="source" :position="sourcePosition" class="workflow-handle" />
        </template>
      </VueFlow>
    </div>

    <a-empty v-else class="solution-flow-empty" description="当前方案尚未提供目标工作流" />
  </div>
</template>
