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
  <button
    class="plan-card"
    :class="[`plan-card--${plan.plan_type}`, { 'plan-card--active': active }]"
    @click="$emit('select')"
  >
    <span v-if="recommended" class="plan-card__recommended">推荐</span>
    <span class="plan-card__icon"><AppIcon :name="planMeta[plan.plan_type]?.icon || 'spark'" /></span>
    <span class="plan-card__content">
      <span class="plan-card__eyebrow">{{ planMeta[plan.plan_type]?.label }}</span>
      <strong>{{ plan.name }}</strong>
      <small>{{ planMeta[plan.plan_type]?.description }}</small>
    </span>
    <span class="plan-card__score">
      <strong>{{ plan.review_score?.toFixed(1) }}</strong>
      <small>评分</small>
    </span>
    <span class="plan-card__stats">
      <span><b>{{ plan.selected_components?.length || 0 }}</b> 能力组件</span>
      <span><b>{{ plan.to_be_nodes?.length || 0 }}</b> 流程节点</span>
    </span>
    <span class="plan-card__check"><AppIcon name="check" :size="14" /></span>
  </button>
</template>
