import { computed, ref } from 'vue'
import inputRaw from '../../mock/input_solutions_10.jsonl?raw'
import outputRaw from '../../mock/solution_bundles_10.jsonl?raw'

const projectMeta = {
  'twitter-telecom-call-001': {
    name: '电信语音服务故障',
    shortName: '语音故障',
    industry: '电信运营',
    source: 'Twitter',
  },
  'twitter-rail-basket-002': {
    name: '铁路购票篮异常',
    shortName: '购票异常',
    industry: '智慧交通',
    source: 'Twitter',
  },
  'twitter-airline-app-login-003': {
    name: '航司 App 登录故障',
    shortName: '登录故障',
    industry: '航空服务',
    source: 'Twitter',
  },
  'twitter-domain-outage-004': {
    name: '域名服务中断',
    shortName: '域名中断',
    industry: '互联网服务',
    source: 'Twitter',
  },
  'twitter-bank-name-change-005': {
    name: '银行客户信息变更',
    shortName: '信息变更',
    industry: '银行服务',
    source: 'Twitter',
  },
  'cfpb-card-fraud-9999983': {
    name: '银行卡欺诈争议',
    shortName: '卡片欺诈',
    industry: '消费金融',
    source: 'CFPB',
  },
  'cfpb-credit-unauthorized-9999982': {
    name: '未授权信用记录',
    shortName: '未授权记录',
    industry: '征信服务',
    source: 'CFPB',
  },
  'cfpb-investigation-failed-9999995': {
    name: '争议调查处理失败',
    shortName: '调查失败',
    industry: '消费金融',
    source: 'CFPB',
  },
  'cfpb-unrecognized-inquiry-9999994': {
    name: '未识别征信查询',
    shortName: '异常查询',
    industry: '征信服务',
    source: 'CFPB',
  },
  'cfpb-credit-reinvestigation-9999965': {
    name: '信用报告复核',
    shortName: '报告复核',
    industry: '征信服务',
    source: 'CFPB',
  },
}

function parseJsonLines(raw) {
  return raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, index) => {
      try {
        return JSON.parse(line)
      } catch {
        throw new Error(`第 ${index + 1} 行不是有效的 JSON`)
      }
    })
}

function enrichProject(project) {
  return {
    ...project,
    meta: projectMeta[project.project_id] || {
      name: project.project_id,
      shortName: project.project_id,
      industry: '业务场景',
      source: 'JSONL',
    },
  }
}

export function useSolutionData() {
  const inputs = ref(parseJsonLines(inputRaw))
  const bundles = ref(parseJsonLines(outputRaw))
  const selectedProjectId = ref(bundles.value[0]?.project_id || '')
  const selectedPlanType = ref('balanced')

  const projects = computed(() => bundles.value.map(enrichProject))
  const selectedBundle = computed(() =>
    bundles.value.find((item) => item.project_id === selectedProjectId.value),
  )
  const selectedInput = computed(() =>
    inputs.value.find((item) => item.source_project_id === selectedProjectId.value),
  )
  const selectedPlan = computed(
    () =>
      selectedBundle.value?.plans.find((plan) => plan.plan_type === selectedPlanType.value) ||
      selectedBundle.value?.plans[0],
  )

  const totalPlans = computed(() =>
    bundles.value.reduce((total, item) => total + (item.plans?.length || 0), 0),
  )
  const averageScore = computed(() => {
    const plans = bundles.value.flatMap((item) => item.plans || [])
    if (!plans.length) return 0
    return plans.reduce((sum, plan) => sum + (plan.review_score || 0), 0) / plans.length
  })

  function selectProject(projectId) {
    selectedProjectId.value = projectId
    const bundle = bundles.value.find((item) => item.project_id === projectId)
    if (!bundle?.plans.some((plan) => plan.plan_type === selectedPlanType.value)) {
      selectedPlanType.value = bundle?.plans[0]?.plan_type || 'balanced'
    }
  }

  function replaceData(type, raw) {
    const parsed = parseJsonLines(raw)
    if (type === 'input') {
      if (!parsed.every((item) => item.source_project_id)) {
        throw new Error('输入数据缺少 source_project_id 字段')
      }
      inputs.value = parsed
      return
    }

    if (!parsed.every((item) => item.project_id && Array.isArray(item.plans))) {
      throw new Error('输出数据需要包含 project_id 与 plans 数组')
    }
    bundles.value = parsed
    if (!bundles.value.some((item) => item.project_id === selectedProjectId.value)) {
      selectedProjectId.value = bundles.value[0]?.project_id || ''
    }
  }

  return {
    projects,
    inputs,
    bundles,
    selectedProjectId,
    selectedPlanType,
    selectedBundle,
    selectedInput,
    selectedPlan,
    totalPlans,
    averageScore,
    selectProject,
    replaceData,
  }
}
