const SOURCE_LABELS = {
  'meeting-raw-v1': '会议纪要',
  'email-raw-v1': '客户邮件',
  'document-raw-v1': '需求 / 招标材料',
  'sales-raw-v1': '销售备注',
}
const ISSUE_LABELS = {
  invalid_candidate: '字段格式不符合需求合同',
  invalid_json: '返回内容不是有效 JSON',
  evidence_not_found: '引用内容无法在原文中定位',
  provider_warning: '模型服务警告',
  empty_response: '未返回内容',
  document_text_unavailable: '资料没有可读取文本',
}

export function summarizeExtractionWarnings(warnings = []) {
  const details = Array.isArray(warnings) ? warnings : []
  const invalidCount = details.filter((warning) => warning.code === 'invalid_candidate').length
  const groupsBySource = new Map()

  for (const warning of details) {
    const sourceId = warning.source_id || 'unknown-source'
    if (!groupsBySource.has(sourceId)) {
      groupsBySource.set(sourceId, {
        sourceId,
        sourceLabel: SOURCE_LABELS[sourceId] || sourceId,
        count: 0,
        issuesByCode: new Map(),
      })
    }
    const group = groupsBySource.get(sourceId)
    group.count += 1
    const issue = group.issuesByCode.get(warning.code) || {
      code: warning.code,
      label: ISSUE_LABELS[warning.code] || warning.code,
      count: 0,
    }
    issue.count += 1
    group.issuesByCode.set(warning.code, issue)
  }

  const groups = [...groupsBySource.values()].map(({ issuesByCode, ...group }) => ({
    ...group,
    issues: [...issuesByCode.values()],
  }))

  return {
    headline: invalidCount
      ? `有 ${invalidCount} 条候选未通过需求合同校验`
      : `需求提取有 ${details.length} 条提示`,
    description: invalidCount
      ? '不合规候选已安全忽略，不会写入需求事实；通过校验的其他候选会继续保留。'
      : '部分资料遇到模型服务或返回格式问题，请查看来源汇总并按需重新分析。',
    groups,
    details,
  }
}
