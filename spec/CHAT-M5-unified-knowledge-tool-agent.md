# CHAT-M5: Unified Knowledge and Tool Agent

**Status:** implemented

## Goal

Upgrade the Feishu conversation backend from separate chat, requirement-analysis,
and explicit `/mcp` paths into one audience-aware Agent that can use the curated
knowledge package, the existing governed MCP server, Requirement Intelligence,
and the existing deterministic solution tools.

The LLM may plan calls and explain evidence. It must not directly read repository
files, bypass permissions, fabricate tool results, confirm requirements, approve a
supplier, or describe simulated metrics as real business outcomes.

## Existing Capabilities Reused

- CHAT-M1 customer intent classification and safe conversation boundary.
- CHAT-M4 durable Feishu Requirement Intelligence orchestration.
- `EnterpriseKnowledgeService` for ACL- and `as_of`-governed knowledge access.
- The eleven read-only MCP tools exposed by `MCPDispatcher`.
- Existing deterministic requirement, solution compilation, review, trace,
  supplier, document-review, communication, and reconciliation tools.

## Audience Boundary

### Customer

- Normal requirement and clarification messages continue through Requirement
  Intelligence.
- General capability questions may call only `search_knowledge` through MCP.
- Customer knowledge search is forced to a hidden `PUBLIC-CAPABILITIES` scope
  containing only curated company capability and automotive solution documents.
- A model-provided project ID, user ID, time point, or non-public MCP tool name is
  ignored.
- Customers cannot access internal project dashboards, requirement histories,
  supplier profiles, communications, contracts, finance, document-review samples,
  traces, or solution bundles.
- Internal Requirement Intelligence metadata remains customer-invisible.

### Internal employee

- A Feishu sender is internal only when its `open_id` is explicitly listed in
  `FEISHU_INTERNAL_OPEN_IDS`.
- Internal messages are automatically sent to the enterprise Agent without
  requiring `/mcp`.
- The Agent may use the existing eleven MCP tools, but every call is forced to the
  configured `project_id`, `user_id`, and `as_of`; MCP and the knowledge service
  remain responsible for ACL, revocation, masking, and point-in-time enforcement.
- `/mcp` remains as a compatibility command. It is available to explicitly listed
  internal senders and to the single creator account protected by
  `FEISHU_ALLOWED_OPEN_ID`; other customer senders are rejected.

## Agent Loop

1. Build an audience-filtered MCP tool catalog.
2. Ask the LLM for zero to three JSON tool-call plans.
3. Validate tool names and discard model-controlled identity or scope fields.
4. Execute validated calls only through `MCPDispatcher`.
5. Collect structured results, citations, permission outcomes, and tool traces.
6. Ask the LLM for a concise evidence-grounded answer; fall back to a deterministic
   answer when planning or synthesis is unavailable.

The LLM cannot invoke arbitrary Python functions or arbitrary MCP methods. Tool
calls are read-only and bounded to three per turn.

## Public Capability Knowledge

The existing `search_knowledge` MCP tool accepts the internal-only virtual scope
`PUBLIC-CAPABILITIES`. It searches only:

- `01_公司能力知识库/AI_Process能力.md`
- `01_公司能力知识库/智能招采能力.md`
- `02_行业解决方案库/汽车采购解决方案.md`

Results include stable source IDs and must preserve statements about human review,
evidence, permissions, and simulated examples. This scope is not an internal
project and is not added to the enterprise project index.

## Failure Behavior

- Invalid or unavailable LLM planning falls back to the existing deterministic
  router.
- Invalid tool names, excessive calls, and scope overrides are ignored.
- MCP permission denials remain permission denials for internal API callers.
- Customer knowledge failure falls back to the safe CHAT-M1 answer rather than
  exposing backend errors.
- Evidence-free search returns an explicit insufficient-evidence answer.

## Configuration

- `FEISHU_INTERNAL_OPEN_IDS`: comma-separated Feishu `open_id` values.
- Existing `FEISHU_ENTERPRISE_PROJECT_ID`, `FEISHU_ENTERPRISE_USER_ID`, and
  `FEISHU_ENTERPRISE_AS_OF` define the internal Agent context.
- Existing OpenAI-compatible `LLM_*` settings are reused for planning and answer
  synthesis.

## Acceptance Criteria

1. An internal natural-language Feishu question invokes the enterprise Agent
   without `/mcp`.
2. The LLM can plan multiple allowed MCP calls and all calls are recorded.
3. Model-controlled identity, project, and time fields cannot override backend
   context.
4. Invalid planning falls back to deterministic routing.
5. A customer capability question searches only `PUBLIC-CAPABILITIES` and returns
   citations.
6. A customer cannot invoke supplier, communication, contract, finance, trace,
   document-review, project-dashboard, requirement-history, or solution tools.
7. Customer requirement messages continue to create Requirement State versions.
8. `/mcp` is denied to customer senders unless the sender is the explicitly
   allowlisted bot creator.
9. Existing MCP ACL, masking, revocation, `as_of`, and human-review behavior remains
   unchanged.
10. CHAT-M1 through CHAT-M5, enterprise MCP tests, and public contract tests pass.
11. No frontend, frozen contract, process, runtime, or fixture files are modified.

## Implementation

- `backend/app/solution/enterprise_portal.py`
- `backend/app/solution/enterprise_assistant.py`
- `backend/app/solution/feishu_bot.py`
- `.env.example`
- `tests/solution/test_unified_knowledge_agent.py`
- `tests/solution/test_feishu_bot.py`

## Verification

- Real DeepSeek smoke classified a customer capability question as a solution
  request; the Feishu boundary correctly recognizes this customer-safe subtype and
  routes it to public capability search without weakening formal solution gates.
- The knowledge Agent returned `search_knowledge`, one governed MCP call, and the
  citation `CAP-SMART-PROCUREMENT` for the public capability question.
- CHAT-M1 through CHAT-M5, enterprise MCP/portal, Feishu, and public contract tests:
  91 passed.
- Full suite: 592 passed and one unrelated existing fixture precision mismatch.
  The existing failure compares `82.64285714285715` with
  `82.64285714285714` in `test_solution_quality_fixture.py`.
