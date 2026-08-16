<script setup>
import AppIcon from './AppIcon.vue'

defineProps({
  plan: { type: Object, required: true },
})
</script>

<template>
  <a-row class="detail-grid" :gutter="[16, 16]">
    <a-col :xs="24" :lg="14">
      <a-card class="detail-card detail-card--steps" title="实施路线" :bordered="false">
        <a-timeline>
          <a-timeline-item v-for="(step, index) in plan.implementation_steps" :key="step">
            <strong>{{ index + 1 }}</strong> · {{ step }}
          </a-timeline-item>
        </a-timeline>
      </a-card>
    </a-col>
    <a-col :xs="24" :lg="10">
      <a-card class="detail-card" title="预期指标" :bordered="false">
        <a-space wrap><a-tag v-for="metric in plan.expected_metrics" :key="metric" color="green">{{ metric }}</a-tag></a-space>
      </a-card>
      <a-card v-if="plan.assumptions?.length" class="detail-card" title="待确认事项" :bordered="false">
        <a-list :data-source="plan.assumptions" size="small">
          <template #renderItem="{ item }"><a-list-item>{{ item.replace(/^待确认:\s*/, '') }}</a-list-item></template>
        </a-list>
      </a-card>
    </a-col>
    <a-col v-if="plan.warnings?.length" :span="24">
      <a-alert type="warning" show-icon message="质量提示">
        <template #description>
          <ul class="warning-list"><li v-for="warning in plan.warnings" :key="warning">{{ warning }}</li></ul>
        </template>
      </a-alert>
    </a-col>
  </a-row>
</template>
