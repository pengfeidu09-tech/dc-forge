import { MarkerType, Position } from '@vue-flow/core'

const COLUMN_GAP = 270
const ROW_GAP = 150

function nodePosition(index, columns) {
  const row = Math.floor(index / columns)
  const offset = index % columns
  const column = row % 2 === 0 ? offset : columns - 1 - offset
  return { row, offset, x: column * COLUMN_GAP, y: row * ROW_GAP }
}

export function buildSolutionWorkflowGraph(plan, options = {}) {
  const workflow = Array.isArray(plan?.target_workflow) ? plan.target_workflow : []
  const columns = Math.max(Number(options.columns) || 4, 1)
  const nodes = workflow.map((step, index) => {
    const { row, offset, x, y } = nodePosition(index, columns)
    const rowStart = offset === 0
    const rowEnd = offset === columns - 1 || index === workflow.length - 1
    const leftToRight = row % 2 === 0

    return {
      id: `step-${index}`,
      type: 'workflowStep',
      position: { x, y },
      sourcePosition: rowEnd ? Position.Bottom : leftToRight ? Position.Right : Position.Left,
      targetPosition: rowStart ? Position.Top : leftToRight ? Position.Left : Position.Right,
      draggable: false,
      connectable: false,
      data: {
        order: index + 1,
        label: step.name,
        executor: step.executor || '系统',
        humanGate: step.human_gate === true,
        gateReason: step.gate_reason || '',
      },
    }
  })

  const edges = Array.from({ length: Math.max(workflow.length - 1, 0) }, (_, index) => ({
    id: `edge-${index}-${index + 1}`,
    source: `step-${index}`,
    target: `step-${index + 1}`,
    type: 'smoothstep',
    markerEnd: MarkerType.ArrowClosed,
    animated: false,
  }))

  return { nodes, edges }
}
