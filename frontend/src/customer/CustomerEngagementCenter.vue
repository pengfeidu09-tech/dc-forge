<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'

const pathParts = location.pathname.split('/').filter(Boolean)
const accessId = decodeURIComponent(pathParts.at(-1) || '')
const accessToken = new URLSearchParams(location.hash.slice(1)).get('access_token') || ''

const loading = ref(true)
const submitting = ref('')
const error = ref('')
const current = ref(null)
const feedback = ref('')
const acceptedKeys = ref([])
const selectedGroups = reactive({})

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-DCForge-Customer-Token': accessToken,
      ...(options.headers || {}),
    },
  })
  if (!response.ok) {
    let detail = response.statusText
    try { detail = (await response.json()).detail || detail } catch { /* response is not JSON */ }
    throw new Error(detail)
  }
  return response.json()
}

function initializeSelection() {
  acceptedKeys.value = []
  Object.keys(selectedGroups).forEach((key) => delete selectedGroups[key])
  const seenGroups = new Set()
  for (const item of current.value?.requirements || []) {
    if (item.status === '已由您确认') continue
    if (item.choice_group) {
      if (!seenGroups.has(item.choice_group)) {
        selectedGroups[item.choice_group] = item.item_key
        seenGroups.add(item.choice_group)
      }
    } else {
      acceptedKeys.value.push(item.item_key)
    }
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    current.value = await api(`/customer/engagement/${encodeURIComponent(accessId)}/data`)
    initializeSelection()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason)
  } finally {
    loading.value = false
  }
}

const pendingRequirements = computed(() =>
  (current.value?.requirements || []).filter((item) => item.status !== '已由您确认'),
)
const hasConflicts = computed(() =>
  pendingRequirements.value.some((item) => item.choice_group),
)
const selectedKeys = computed(() => [
  ...acceptedKeys.value,
  ...Object.values(selectedGroups).filter(Boolean),
])

function checkboxChanged(item, checked) {
  if (checked && !acceptedKeys.value.includes(item.item_key)) {
    acceptedKeys.value = [...acceptedKeys.value, item.item_key]
  } else if (!checked) {
    acceptedKeys.value = acceptedKeys.value.filter((key) => key !== item.item_key)
  }
}

async function confirmRequirements() {
  const accepted = selectedKeys.value
  const rejected = pendingRequirements.value
    .map((item) => item.item_key)
    .filter((key) => !accepted.includes(key))
  if (!accepted.length && !rejected.length) return
  submitting.value = 'confirm'
  try {
    const result = await api(`/customer/engagement/${encodeURIComponent(accessId)}/confirm`, {
      method: 'POST',
      body: JSON.stringify({
        confirmation_revision: current.value.confirmation_revision,
        accepted_item_keys: accepted,
        rejected_item_keys: rejected,
        note: '客户通过需求与方案中心确认',
      }),
    })
    message.success(result.message)
    await load()
  } catch (reason) {
    message.error(reason instanceof Error ? reason.message : String(reason))
  } finally {
    submitting.value = ''
  }
}

async function submitFeedback() {
  const content = feedback.value.trim()
  if (!content) return
  submitting.value = 'feedback'
  try {
    const result = await api(`/customer/engagement/${encodeURIComponent(accessId)}/feedback`, {
      method: 'POST',
      body: JSON.stringify({ message: content }),
    })
    message.success(result.message)
    feedback.value = ''
    await load()
  } catch (reason) {
    message.error(reason instanceof Error ? reason.message : String(reason))
  } finally {
    submitting.value = ''
  }
}

async function downloadDeliverable() {
  try {
    const response = await fetch(
      `/customer/engagement/${encodeURIComponent(accessId)}/deliverable`,
      { headers: { 'X-DCForge-Customer-Token': accessToken } },
    )
    if (!response.ok) throw new Error((await response.json()).detail || response.statusText)
    const blob = await response.blob()
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = 'dcforge-presales-solution.html'
    link.click()
    setTimeout(() => URL.revokeObjectURL(link.href), 1000)
  } catch (reason) {
    message.error(reason instanceof Error ? reason.message : String(reason))
  }
}

onMounted(() => {
  if (accessId && accessToken) load()
  else loading.value = false
})
</script>

<template>
  <a-layout class="customer-shell">
    <a-layout-header class="customer-header">
      <div class="customer-header__inner">
        <div>
          <a-typography-title :level="2">需求与方案中心</a-typography-title>
          <a-typography-text>核对当前需求理解，查看企业团队发布的解决方案。</a-typography-text>
        </div>
        <a-tag color="blue">DCForge Customer Portal</a-tag>
      </div>
    </a-layout-header>

    <a-layout-content class="customer-content">
      <a-result
        v-if="!accessId || !accessToken"
        status="warning"
        title="客户访问链接不完整"
        sub-title="请从飞书机器人重新获取需求与方案中心链接。"
      />
      <a-result
        v-else-if="error"
        status="error"
        title="项目暂时无法访问"
        :sub-title="error"
      >
        <template #extra><a-button type="primary" @click="load">重新加载</a-button></template>
      </a-result>
      <div v-else>
        <a-spin :spinning="loading" tip="正在读取项目…">
          <template v-if="current">
            <a-alert
              v-if="current.solution?.publication_basis === 'latest_requirement_state'"
              class="customer-block"
              type="warning"
              show-icon
              message="当前展示的是演示预览"
              :description="current.solution.notice"
            />

            <a-card class="customer-block" title="当前需求理解" :bordered="false">
              <template #extra>
                <a-tag :color="current.requirements_confirmed ? 'success' : 'processing'">
                  {{ current.requirements_confirmed ? '已形成确认基线' : '待核对' }}
                </a-tag>
              </template>
              <a-alert
                v-if="hasConflicts"
                type="warning"
                show-icon
                message="部分需求存在冲突，请在同组中选择一项。"
              />
              <a-empty v-if="!current.requirements.length" description="目前没有可确认的需求项" />
              <a-row v-else :gutter="[16, 16]" class="requirement-grid">
                <a-col
                  v-for="item in current.requirements"
                  :key="item.item_key"
                  :xs="24"
                  :lg="12"
                >
                  <a-card size="small" class="requirement-card">
                    <div class="requirement-card__head">
                      <a-radio
                        v-if="item.choice_group"
                        :checked="selectedGroups[item.choice_group] === item.item_key"
                        :disabled="item.status === '已由您确认'"
                        @change="selectedGroups[item.choice_group] = item.item_key"
                      />
                      <a-checkbox
                        v-else
                        :checked="item.status === '已由您确认' || acceptedKeys.includes(item.item_key)"
                        :disabled="item.status === '已由您确认'"
                        @change="checkboxChanged(item, $event.target.checked)"
                      />
                      <a-tag :color="item.status === '已由您确认' ? 'success' : 'blue'">
                        {{ item.category }}
                      </a-tag>
                      <a-typography-text type="secondary">{{ item.status }}</a-typography-text>
                    </div>
                    <a-typography-title :level="5">{{ item.subject }}</a-typography-title>
                    <a-typography-paragraph>{{ item.value }}</a-typography-paragraph>
                  </a-card>
                </a-col>
              </a-row>
              <a-button
                v-if="pendingRequirements.length"
                class="customer-action"
                type="primary"
                :loading="submitting === 'confirm'"
                @click="confirmRequirements"
              >提交需求确认</a-button>
            </a-card>

            <a-card class="customer-block" title="补充或纠正" :bordered="false">
              <a-textarea
                v-model:value="feedback"
                :rows="4"
                :maxlength="4000"
                show-count
                placeholder="例如：审批阈值应调整为80万元，数据必须部署在企业私域。"
              />
              <a-button
                class="customer-action"
                type="primary"
                :disabled="!feedback.trim()"
                :loading="submitting === 'feedback'"
                @click="submitFeedback"
              >提交补充信息</a-button>
            </a-card>

            <a-card class="customer-block" title="当前解决方案" :bordered="false">
              <a-empty v-if="!current.solution" description="企业团队尚未发布方案" />
              <template v-else>
                <a-alert type="info" show-icon :message="current.solution.notice" />
                <a-tabs class="solution-tabs">
                  <a-tab-pane
                    v-for="plan in current.solution.plans"
                    :key="plan.name"
                    :tab="plan.recommended ? `${plan.name}（推荐）` : plan.name"
                  >
                    <a-typography-title :level="4">{{ plan.name }}</a-typography-title>
                    <a-typography-paragraph>{{ plan.summary }}</a-typography-paragraph>
                    <a-descriptions bordered size="small" :column="1">
                      <a-descriptions-item label="方案定位">{{ plan.strategy }}</a-descriptions-item>
                      <a-descriptions-item label="能力数量">{{ plan.capabilities.length }} 项</a-descriptions-item>
                    </a-descriptions>
                    <a-list :data-source="plan.capabilities" class="solution-list" size="small">
                      <template #header><strong>能力模块</strong></template>
                      <template #renderItem="{ item }">
                        <a-list-item><a-list-item-meta :title="item.name" :description="item.reason" /></a-list-item>
                      </template>
                    </a-list>
                    <a-collapse ghost>
                      <a-collapse-panel key="workflow" header="目标工作流">
                        <a-steps
                          direction="vertical"
                          size="small"
                          :items="plan.target_workflow.map((node) => ({ title: node.name, description: `${node.executor}${node.gate_reason ? ` · ${node.gate_reason}` : ''}` }))"
                        />
                      </a-collapse-panel>
                      <a-collapse-panel key="steps" header="实施步骤">
                        <a-list :data-source="plan.implementation_steps" size="small" bordered>
                          <template #renderItem="{ item, index }"><a-list-item>{{ index + 1 }}. {{ item }}</a-list-item></template>
                        </a-list>
                      </a-collapse-panel>
                    </a-collapse>
                  </a-tab-pane>
                </a-tabs>
              </template>
            </a-card>

            <a-card v-if="current.deliverable" class="customer-block" title="客户解决方案成果" :bordered="false">
              <a-typography-title :level="4">{{ current.deliverable.title }}</a-typography-title>
              <a-typography-paragraph>{{ current.deliverable.recommended_solution }}</a-typography-paragraph>
              <a-alert
                type="warning"
                show-icon
                message="价值指标和方案效果需要在贵司环境中验证，不代表已经取得业务成果。"
              />
              <a-button class="customer-action" type="primary" @click="downloadDeliverable">
                下载可编辑 HTML 成果
              </a-button>
            </a-card>
          </template>
        </a-spin>
      </div>
    </a-layout-content>
  </a-layout>
</template>
