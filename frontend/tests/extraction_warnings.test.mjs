import assert from 'node:assert/strict'
import test from 'node:test'

import { summarizeExtractionWarnings } from '../src/utils/extractionWarnings.js'


test('groups strict candidate failures by human-readable source', () => {
  const summary = summarizeExtractionWarnings([
    {
      source_id: 'document-raw-v1',
      code: 'invalid_candidate',
      message: 'candidate 0 rejected by strict schema: invalid category',
      locator: null,
    },
    {
      source_id: 'document-raw-v1',
      code: 'invalid_candidate',
      message: 'candidate 1 rejected by strict schema: invalid category',
      locator: null,
    },
    {
      source_id: 'email-raw-v1',
      code: 'invalid_candidate',
      message: 'candidate 0 rejected by strict schema: confidence must be numeric',
      locator: null,
    },
  ])

  assert.equal(summary.headline, '有 3 条候选未通过需求合同校验')
  assert.match(summary.description, /已安全忽略/)
  assert.deepEqual(
    summary.groups.map((group) => [group.sourceLabel, group.count]),
    [['需求 / 招标材料', 2], ['客户邮件', 1]],
  )
  assert.equal(summary.groups[0].issues[0].label, '字段格式不符合需求合同')
  assert.equal(summary.details.length, 3)
})

test('summarizes provider and empty-response warnings without claiming success', () => {
  const summary = summarizeExtractionWarnings([
    {
      source_id: 'meeting-raw-v1',
      code: 'provider_warning',
      message: 'LLM 未配置',
      locator: null,
    },
    {
      source_id: 'meeting-raw-v1',
      code: 'empty_response',
      message: 'provider returned empty content',
      locator: null,
    },
  ])

  assert.equal(summary.headline, '需求提取有 2 条提示')
  assert.match(summary.description, /模型服务或返回格式/)
  assert.deepEqual(
    summary.groups[0].issues.map((issue) => issue.label),
    ['模型服务警告', '未返回内容'],
  )
})
