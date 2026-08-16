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
  <a-card v-if="nodes.length" class="workflow-map" :bordered="false">
    <a-steps direction="vertical" size="small" :current="nodes.length">
      <a-step
      v-for="(node, index) in nodes"
      :key="node.id"
      :title="`${String(index + 1).padStart(2, '0')} · ${node.name}`"
    >
        <template #description>
          <a-space direction="vertical" size="small">
            <a-space wrap>
            <AppIcon :name="executorMeta[node.executor]?.icon || 'cpu'" :size="19" />
              <a-tag>{{ executorMeta[node.executor]?.label || node.executor }}</a-tag>
              <a-tag v-if="node.human_gate" color="orange">审批门</a-tag>
              <a-typography-text type="secondary">{{ node.component_id }}</a-typography-text>
            </a-space>
            <a-alert v-if="node.gate_reason" type="warning" :message="node.gate_reason" />
          </a-space>
        </template>
      </a-step>
    </a-steps>
  </a-card>
  <a-empty v-else class="empty-state" description="当前方案暂无流程节点" />
</template>
