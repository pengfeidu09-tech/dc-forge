# CHAT-M4: Feishu Agent to Requirement Intelligence

**Status:** implemented

## Goal

Connect each qualifying Feishu customer turn to the existing frozen Requirement
Intelligence Engine so the bot maintains durable, versioned Requirement Truth for
the agreed validation scenario:

- Industry: automotive.
- Customer type: large manufacturing enterprise.
- Presales scenario: intelligent sourcing and procurement compliance.
- Requirement skill: `automotive-procurement-v1`.

Previous ad-hoc chat content is not imported as Requirement Truth. CHAT-M4 starts
with a newly configured repository outside the Git working tree.

## Flow

```text
Feishu text event
      │
      ▼
CHAT-M1 intent classification
      │ next_action=analyze_requirements
      ▼
CHAT-M4 conversation orchestrator
      │ CustomerSourceRecord(source_type=conversation)
      ▼
RequirementExtractor -> RequirementReducer -> RequirementAnalysisBuilder
      │
      ├── immutable RequirementState version
      ├── readiness stage and deterministic completeness score
      ├── gaps and conflicts
      └── next best question
      ▼
Deterministic Feishu reply
```

## Scope

- Derive a stable Requirement project ID from the Feishu tenant and chat IDs.
- Convert every analyzed Feishu customer message to a traceable
  `CustomerSourceRecord` whose source ID and locator are derived from the Feishu
  event ID.
- Use `InternalConsoleService.analyze()` as the existing orchestration boundary; do
  not copy or change frozen Requirement Intelligence semantics.
- Load the latest state version for later turns and create exactly one new immutable
  state version per analyzed message.
- Persist states under `REQUIREMENT_REPOSITORY_ROOT`, which must point outside the
  Git working tree.
- Fix the skill to `automotive-procurement-v1` by default, with an environment
  override reserved for controlled testing.
- Feed only a customer-safe projection of the business-state snapshot back into
  CHAT-M1 on subsequent turns: the natural-language requirement summary and
  pending clarification questions. Keep versions, readiness, baselines, scores,
  phases, and workflow flags out of the model prompt.
- Replace the free-form CHAT-M1 answer with a deterministic customer-safe reply
  when `next_action=analyze_requirements`.
- The customer reply may acknowledge the conversation and ask one next-best
  question, but must not expose state versions, skill IDs, readiness stages,
  completeness scores, requirement IDs, extraction warnings, candidate statuses,
  gaps, conflicts, baselines, or internal workflow terminology.
- Customer discovery must not repeat a category merely because its extracted
  evidence is still pending formal confirmation. Ask about missing information
  during discovery; reserve confirmation of accumulated pending items for the
  explicit confirmation flow.
- Keep the full stored state, readiness, changes, warnings, and next-question
  metadata available only to trusted internal services and future authenticated
  administration views.
- Reject a free-form CHAT-M1 answer before delivery if it contains known internal
  Requirement Intelligence field names, skill IDs, stage enums, or workflow
  terminology.
- Serialize analysis updates within the bot process to avoid local version races.

## State Semantics

- `DISCOVERY`: required information is still missing.
- `PRELIMINARY_READY`: enough information exists for a preliminary solution, but
  formal customer confirmation is incomplete.
- `CONFIRMED_READY`: only produced by the frozen explicit confirmation flow, never
  by CHAT-M4 analysis alone.
- LLM extraction creates pending, evidence-backed candidates; it cannot mark items
  as customer-confirmed.
- The deterministic completeness score is a requirement-information coverage
  score, not a measured business outcome.

## Configuration

- `REQUIREMENT_REPOSITORY_ROOT`: durable state directory outside this repository.
- `FEISHU_REQUIREMENT_SKILL_ID=automotive-procurement-v1`.
- Existing DeepSeek/OpenAI-compatible settings are reused for extraction.

## Failure Behavior

- If Requirement Intelligence fails, the bot returns a sanitized temporary-failure
  message and does not claim that a state was saved.
- Extraction warnings may be counted but their raw provider content is not exposed
  to the customer.
- A greeting or unrelated turn that does not request requirement analysis remains a
  normal CHAT-M1 conversation turn and does not create Requirement State.
- Event deduplication remains ahead of analysis, so a duplicate event in the active
  process cannot create a second state version.

## Acceptance Criteria

1. The first automotive procurement message creates RequirementState version 1.
2. Its source record is a Feishu conversation source tied to the event ID.
3. The configured skill is `automotive-procurement-v1`.
4. The Feishu answer comes from the deterministic analysis formatter rather than
   the free-form CHAT-M1 answer.
5. A second analyzed turn loads version 1 and persists version 2.
6. Recreating the orchestrator over the same repository preserves the latest
   business-state snapshot.
7. CHAT-M1 receives only the customer-safe summary and pending questions before
   classifying later turns; internal snapshot fields remain local to backend
   routing.
8. Greetings do not mutate Requirement State.
9. Analysis failures do not expose provider responses, repository paths, or
   credentials.
10. CHAT-M1 through CHAT-M4 and public contract tests remain green.
11. Customer-visible replies contain no internal Requirement Intelligence metadata.
12. Internal result fields still expose state version, readiness, completeness, and
    the next question to trusted backend callers.
13. Once approval, available-data, or security evidence exists, the next discovery
    reply does not repeat that category's original question solely because the
    stored item is pending customer confirmation.

## Out of Scope

- Automatically confirming all pending requirements from an ambiguous chat reply.
- Automatically creating Requirement Baseline or compiling a formal solution.
- Modifying frozen contracts, process semantics, runtime, or frontend code.
- Importing earlier process-local chat memory into Requirement Truth.
- Durable distributed locks or multiple concurrent bot processes.

## Implementation

- `backend/app/solution/feishu_requirement.py`
- `backend/app/solution/feishu_bot.py`
- `backend/app/solution/feishu_ws.py`
- `.env.example`
- `tests/solution/test_feishu_requirement.py`
- `tests/solution/test_feishu_requirement_integration.py`

## Verification

- A real DeepSeek extraction of the agreed automotive procurement example created
  RequirementState version 1 with 9 evidence-backed pending items.
- The deterministic engine reported `DISCOVERY`, 40% requirement-information
  coverage, and the next question about procurement approval rules.
- This score is deterministic information coverage, not a measured business result.
