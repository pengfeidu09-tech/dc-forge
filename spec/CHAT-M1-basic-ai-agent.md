# CHAT-M1: Basic Requirement Conversation Agent

**Status:** implemented

## Goal

Provide a Feishu-independent AI boundary that accepts one customer message, optional
conversation history, and an optional business-state snapshot. The agent returns a
customer-facing reply, a classified intent, and one deterministic next action for a
later orchestration layer.

## Scope

- Reuse the existing OpenAI-compatible `LLMProvider`.
- Add strict private request and response models under `backend/app/solution/`.
- Add `POST /agent/chat` without adding a Feishu dependency.
- Include the business-state snapshot and recent history in the model context.
- Treat all customer text and history as untrusted data.
- Derive the next action from validated intent and confirmed state, not from an
  arbitrary model-provided tool name.
- Return a safe unavailable response when the model is not configured or returns
  invalid output.

## Intents

- `greeting`
- `requirement_input`
- `clarification_answer`
- `confirmation`
- `solution_request`
- `feedback`
- `general`

## Next Actions

- `none`
- `analyze_requirements`
- `prepare_confirmation`
- `compile_solution`

Rules:

- `requirement_input`, `clarification_answer`, and `feedback` route to
  `analyze_requirements`.
- `confirmation` routes to `prepare_confirmation`; it never applies confirmation
  directly.
- `solution_request` routes to `compile_solution` only when the supplied business
  state explicitly says a formal solution can be generated.
- All other cases route to `none`.

## HTTP Contract

`POST /agent/chat`

Request fields:

- `project_id`
- `message_id`
- `message`
- `history` (optional, at most 20 turns)
- `state` (optional business-state snapshot)

Response fields:

- `status`: `ok` or `unavailable`
- `intent`
- `answer`
- `next_action`
- `warnings`

## Safety and Truth Boundary

- The agent does not write `RequirementState`.
- The agent does not create a `RequirementBaseline`.
- The agent does not call solution compilation in this milestone.
- Customer confirmation remains an explicit downstream operation.
- The reply must not claim measured ROI, verified customer outcomes, or completed
  execution.
- API keys and provider secrets must never appear in responses or warnings.

## Acceptance Criteria

1. A valid model response produces a strict `ChatAgentResponse`.
2. Business state and recent history are sent to the provider.
3. Requirement and feedback intents route to requirement analysis.
4. Confirmation only prepares confirmation.
5. Solution compilation is suggested only for a formally ready state.
6. Empty, invalid, or unavailable model output returns `status=unavailable`.
7. Unknown model fields and intents cannot select an arbitrary action.
8. Request extra fields are rejected with HTTP 422.
9. The endpoint is present in OpenAPI.
10. Existing contract tests remain unchanged and pass.

## Out of Scope

- Feishu webhook verification and event callbacks.
- Feishu message sending or interactive cards.
- Persistent conversation or business-state storage.
- Requirement analysis execution.
- Customer confirmation execution.
- Solution compilation and frontend publication.

## Implementation

- `backend/app/solution/chat_agent.py`
- `backend/app/solution/api.py`
- `backend/app/solution/__init__.py`
- `tests/solution/test_chat_agent.py`
- `tests/solution/test_chat_agent_api.py`

## Verification

- New CHAT-M1 tests: 15 passed.
- Public contract tests: 3 passed.
- Full suite: 446 passed, 1 unrelated existing fixture precision mismatch.
  The failing assertion compares `82.64285714285715` with
  `82.64285714285714` in `test_solution_quality_fixture.py`; CHAT-M1 does not
  modify the compiler, reviewer, or fixture involved in that assertion.
