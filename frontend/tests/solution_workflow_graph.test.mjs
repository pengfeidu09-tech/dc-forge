import assert from 'node:assert/strict'
import test from 'node:test'

import { buildSolutionWorkflowGraph } from '../src/presales/solutionWorkflowGraph.js'

test('maps every workflow step and only connects adjacent steps', () => {
  const graph = buildSolutionWorkflowGraph({
    target_workflow: [
      { name: '需求抽取', executor: 'AI', human_gate: false, gate_reason: null },
      { name: '规则校验', executor: '系统', human_gate: false, gate_reason: null },
      { name: '风险审批', executor: '人工', human_gate: true, gate_reason: '高风险事项需要审批。' },
    ],
  })

  assert.equal(graph.nodes.length, 3)
  assert.equal(graph.edges.length, 2)
  assert.deepEqual(
    graph.edges.map(({ source, target }) => ({ source, target })),
    [
      { source: 'step-0', target: 'step-1' },
      { source: 'step-1', target: 'step-2' },
    ],
  )
  assert.equal(graph.nodes[2].data.humanGate, true)
  assert.equal(graph.nodes[2].data.gateReason, '高风险事项需要审批。')
  assert.equal(graph.nodes[2].data.executor, '人工')
})

test('returns an empty graph when the solution has no target workflow', () => {
  assert.deepEqual(buildSolutionWorkflowGraph(null), { nodes: [], edges: [] })
  assert.deepEqual(buildSolutionWorkflowGraph({}), { nodes: [], edges: [] })
})

test('uses fewer columns on compact canvases without changing graph order', () => {
  const plan = {
    target_workflow: Array.from({ length: 5 }, (_, index) => ({
      name: `步骤 ${index + 1}`,
      executor: '系统',
    })),
  }
  const graph = buildSolutionWorkflowGraph(plan, { columns: 2 })

  assert.equal(graph.nodes[0].position.y, graph.nodes[1].position.y)
  assert.ok(graph.nodes[2].position.y > graph.nodes[1].position.y)
  assert.deepEqual(
    graph.edges.map(({ source, target }) => `${source}->${target}`),
    ['step-0->step-1', 'step-1->step-2', 'step-2->step-3', 'step-3->step-4'],
  )
})
