<script setup>
import AppIcon from './AppIcon.vue'

defineProps({
  plan: { type: Object, required: true },
  active: { type: Boolean, default: false },
  recommended: { type: Boolean, default: false },
})

defineEmits(['select'])

const planMeta = {
  conservative: {
    label: '稳健型',
    icon: 'shield',
    description: '人工可控 · 风险优先',
  },
  balanced: {
    label: '平衡型',
    icon: 'balance',
    description: '效率与风险兼顾',
  },
  innovative: {
    label: '创新型',
    icon: 'rocket',
    description: '高自动化 · 智能增强',
  },
}
</script>

<template>
  <a-card
    class="plan-card"
    :class="[`plan-card--${plan.plan_type}`, { 'plan-card--active': active }]"
    hoverable
    @click="$emit('select')"
  >
    <template #title><a-space><AppIcon :name="planMeta[plan.plan_type]?.icon || 'spark'" /><span>{{ plan.name }}</span></a-space></template>
    <template #extra><a-tag v-if="recommended" color="blue">推荐</a-tag></template>
    <a-typography-text type="secondary">{{ planMeta[plan.plan_type]?.label }} · {{ planMeta[plan.plan_type]?.description }}</a-typography-text>
    <a-row :gutter="12" class="plan-card__stats">
      <a-col :span="8"><a-statistic title="评分" :value="plan.review_score || 0" :precision="1" /></a-col>
      <a-col :span="8"><a-statistic title="能力组件" :value="plan.selected_components?.length || 0" /></a-col>
      <a-col :span="8"><a-statistic title="流程节点" :value="plan.to_be_nodes?.length || 0" /></a-col>
    </a-row>
  </a-card>
</template>
