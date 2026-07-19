<script setup>
import AppIcon from './AppIcon.vue'

defineProps({
  plan: { type: Object, required: true },
})
</script>

<template>
  <div class="detail-grid">
    <section class="detail-card detail-card--steps">
      <div class="section-heading section-heading--compact">
        <span class="section-heading__icon"><AppIcon name="flow" /></span>
        <div>
          <small>DELIVERY PATH</small>
          <h3>实施路线</h3>
        </div>
      </div>
      <ol class="implementation-list">
        <li v-for="(step, index) in plan.implementation_steps" :key="step">
          <span>{{ index + 1 }}</span>
          <p>{{ step }}</p>
        </li>
      </ol>
    </section>

    <div class="detail-stack">
      <section class="detail-card">
        <div class="section-heading section-heading--compact">
          <span class="section-heading__icon section-heading__icon--green"><AppIcon name="target" /></span>
          <div>
            <small>VALUE PROOF</small>
            <h3>预期指标</h3>
          </div>
        </div>
        <div class="tag-cloud">
          <span v-for="metric in plan.expected_metrics" :key="metric">{{ metric }}</span>
        </div>
      </section>

      <section v-if="plan.assumptions?.length" class="detail-card">
        <div class="section-heading section-heading--compact">
          <span class="section-heading__icon section-heading__icon--amber"><AppIcon name="warning" /></span>
          <div>
            <small>TO BE CONFIRMED</small>
            <h3>待确认事项</h3>
          </div>
        </div>
        <ul class="plain-list">
          <li v-for="item in plan.assumptions" :key="item">{{ item.replace(/^待确认:\s*/, '') }}</li>
        </ul>
      </section>
    </div>

    <section v-if="plan.warnings?.length" class="detail-card detail-card--warning">
      <div class="section-heading section-heading--compact">
        <span class="section-heading__icon section-heading__icon--red"><AppIcon name="warning" /></span>
        <div>
          <small>QUALITY NOTICE</small>
          <h3>质量提示</h3>
        </div>
      </div>
      <ul class="warning-list">
        <li v-for="warning in plan.warnings" :key="warning">{{ warning }}</li>
      </ul>
    </section>
  </div>
</template>
