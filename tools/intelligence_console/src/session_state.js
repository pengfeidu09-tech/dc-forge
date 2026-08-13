export const cloneArtifact = (value) => value == null ? null : JSON.parse(JSON.stringify(value))

export function capturePreviousSolutionSnapshot(session) {
  if (session.previousBaseline) return session
  session.previousBaseline = cloneArtifact(session.baseline)
  session.previousProcessSpec = cloneArtifact(session.processSpec)
  session.previousRecommendedSolution = cloneArtifact(session.recommendedSolution)
  session.previousBlueprint = cloneArtifact(session.blueprint)
  return session
}

export function hasCompletePreviousSolutionSnapshot(session) {
  return Boolean(
    session.previousBaseline &&
    session.previousProcessSpec &&
    session.previousRecommendedSolution &&
    session.previousBlueprint,
  )
}

export function buildRecompilePayload(session) {
  if (!hasCompletePreviousSolutionSnapshot(session)) {
    throw new Error('previous solution snapshot is incomplete')
  }
  return {
    project_id: session.projectId,
    previous_baseline_version: session.previousBaseline.baseline_version,
    current_baseline_version: session.baseline.baseline_version,
    previous_process: session.previousProcessSpec,
    selected_solution: session.previousRecommendedSolution,
    selected_blueprint: session.previousBlueprint,
  }
}

export const approvalThresholdAmount = (item) => item?.parameters?.threshold_amount
