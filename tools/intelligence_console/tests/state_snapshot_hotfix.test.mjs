import assert from 'node:assert/strict'
import test from 'node:test'

import {
  approvalThresholdAmount,
  buildRecompilePayload,
  capturePreviousSolutionSnapshot,
  hasCompletePreviousSolutionSnapshot,
} from '../src/session_state.js'

function sessionV1() {
  return {
    projectId: 'snapshot-test',
    baseline: { baseline_version: 1 },
    processSpec: { constraints: [{ type: 'approval', parameters: { threshold_amount: 500000 } }] },
    recommendedSolution: { solution_id: 'solution-v1', applied_constraints: [{ type: 'approval', parameters: { threshold_amount: 500000 } }] },
    blueprint: { blueprint_id: 'blueprint-v1', nodes: [{ id: 'hard-approval-gate' }] },
    previousBaseline: null,
    previousProcessSpec: null,
    previousRecommendedSolution: null,
    previousBlueprint: null,
  }
}

test('captures deep, independent v1 solution artifacts', () => {
  const session = sessionV1()
  capturePreviousSolutionSnapshot(session)

  session.processSpec.constraints[0].parameters.threshold_amount = 800000

  assert.equal(session.previousProcessSpec.constraints[0].parameters.threshold_amount, 500000)
  assert.notStrictEqual(session.previousProcessSpec, session.processSpec)
  assert.notStrictEqual(session.previousRecommendedSolution, session.recommendedSolution)
  assert.notStrictEqual(session.previousBlueprint, session.blueprint)
})

test('current v2 compile replacements do not overwrite a captured v1 snapshot', () => {
  const session = sessionV1()
  capturePreviousSolutionSnapshot(session)
  session.baseline = { baseline_version: 2 }
  session.processSpec = { constraints: [{ type: 'approval', parameters: { threshold_amount: 800000 } }] }
  session.recommendedSolution = { solution_id: 'solution-v2' }
  session.blueprint = { blueprint_id: 'blueprint-v2' }

  assert.deepEqual(session.previousBaseline, { baseline_version: 1 })
  assert.equal(session.previousProcessSpec.constraints[0].parameters.threshold_amount, 500000)
  assert.equal(session.previousRecommendedSolution.solution_id, 'solution-v1')
  assert.equal(session.previousBlueprint.blueprint_id, 'blueprint-v1')
})

test('recompile payload exclusively uses the previous v1 artifacts', () => {
  const session = sessionV1()
  capturePreviousSolutionSnapshot(session)
  session.baseline = { baseline_version: 2 }
  session.processSpec = { constraints: [{ type: 'approval', parameters: { threshold_amount: 800000 } }] }
  session.recommendedSolution = { solution_id: 'solution-v2' }
  session.blueprint = { blueprint_id: 'blueprint-v2' }

  const payload = buildRecompilePayload(session)

  assert.equal(payload.previous_baseline_version, 1)
  assert.equal(payload.current_baseline_version, 2)
  assert.equal(payload.previous_process.constraints[0].parameters.threshold_amount, 500000)
  assert.notStrictEqual(payload.previous_process, session.processSpec)
  assert.equal(payload.selected_solution.solution_id, 'solution-v1')
  assert.equal(payload.selected_blueprint.blueprint_id, 'blueprint-v1')
})

test('incomplete previous snapshots block recompile payload construction', () => {
  for (const missingKey of ['previousProcessSpec', 'previousRecommendedSolution', 'previousBlueprint']) {
    const session = sessionV1()
    capturePreviousSolutionSnapshot(session)
    session[missingKey] = null
    assert.equal(hasCompletePreviousSolutionSnapshot(session), false)
    assert.throws(() => buildRecompilePayload(session), /snapshot is incomplete/)
  }
  const complete = sessionV1()
  capturePreviousSolutionSnapshot(complete)
  assert.equal(hasCompletePreviousSolutionSnapshot(complete), true)
})

test('approval threshold reads only threshold_amount', () => {
  assert.equal(approvalThresholdAmount({ parameters: { threshold_amount: 500000 } }), 500000)
  assert.equal(approvalThresholdAmount({ parameters: { threshold_amount: 800000 } }), 800000)
  assert.equal(approvalThresholdAmount({ parameters: { threshold: 500000 } }), undefined)
  assert.equal(approvalThresholdAmount(null), undefined)
})
