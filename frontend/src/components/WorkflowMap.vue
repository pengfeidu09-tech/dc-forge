<script setup>
import AppIcon from './AppIcon.vue'

defineProps({
  nodes: { type: Array, default: () => [] },
})

const executorMeta = {
  ai: { label: 'AI 智能', icon: 'bot' },
  human: { label: '人工节点', icon: 'user' },
  system: { label: '系统自动', icon: 'cpu' },
}
</script>

<template>
  <div v-if="nodes.length" class="workflow-map">
    <div class="workflow-map__rail"></div>
    <div
      v-for="(node, index) in nodes"
      :key="node.id"
      class="workflow-node"
      :class="[`workflow-node--${node.executor}`, { 'workflow-node--gate': node.human_gate }]"
    >
      <div class="workflow-node__step">{{ String(index + 1).padStart(2, '0') }}</div>
      <div class="workflow-node__card">
        <div class="workflow-node__top">
          <span class="workflow-node__icon">
            <AppIcon :name="executorMeta[node.executor]?.icon || 'cpu'" :size="19" />
          </span>
          <span class="executor-badge">{{ executorMeta[node.executor]?.label || node.executor }}</span>
          <span v-if="node.human_gate" class="gate-badge">审批门</span>
        </div>
        <strong>{{ node.name }}</strong>
        <small>{{ node.component_id }}</small>
        <p v-if="node.gate_reason">{{ node.gate_reason }}</p>
      </div>
      <AppIcon v-if="index < nodes.length - 1" class="workflow-node__arrow" name="arrow" :size="18" />
    </div>
  </div>
  <div v-else class="empty-state">当前方案暂无流程节点</div>
</template>
