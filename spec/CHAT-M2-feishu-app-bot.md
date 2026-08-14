# CHAT-M2: Feishu Application Bot Chat Adapter

**Status:** implemented

## Goal

Connect Feishu application-bot text events to the CHAT-M1 requirement conversation
agent and send the generated reply back to the originating Feishu message.

## Scope

- Add `POST /integrations/feishu/events`.
- Support Feishu URL verification challenges.
- Verify the configured Feishu verification token.
- Accept schema 2.0 `im.message.receive_v1` text events.
- Ignore bot senders, unsupported event types, and unsupported message types.
- Remove Feishu mention placeholders from the customer text.
- Deduplicate event IDs within the running process.
- Keep at most 20 recent user/assistant turns per Feishu conversation in memory.
- Call the existing CHAT-M1 agent with a stable project ID derived from tenant and
  chat IDs.
- Obtain an internal-app tenant access token and reply to the source message through
  the Feishu Open API.
- Keep Feishu transport isolated from Requirement Intelligence and Solution
  Intelligence business logic.

## Configuration

- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_VERIFICATION_TOKEN`
- `FEISHU_API_BASE_URL` (optional, defaults to `https://open.feishu.cn`)

`WEBHOOK_URL` and `SIGNING_SECRET` belong to a one-way custom bot and are not
sufficient for receiving customer chat messages.

## Event Flow

1. Feishu posts an event to `/integrations/feishu/events`.
2. The adapter verifies the token and acknowledges the event.
3. A background task deduplicates and normalizes a supported text message.
4. The adapter calls CHAT-M1 with recent conversation history.
5. The generated answer is stored in the in-memory conversation window.
6. The Feishu client replies to the original message.

## Safety and Reliability

- Event IDs are idempotency keys.
- App secrets and tenant tokens must never appear in API responses or warnings.
- The callback acknowledges accepted events without returning the model answer to
  Feishu's event delivery request.
- The model cannot select Feishu API methods or arbitrary tools.
- Conversation memory is process-local and is not Requirement Truth.
- Customer confirmation is not applied by this adapter.

## Acceptance Criteria

1. A valid URL verification request returns the supplied challenge.
2. An invalid verification token returns HTTP 401.
3. A valid text event is acknowledged and produces one Feishu reply.
4. Replayed event IDs do not produce a second reply.
5. Bot messages and unsupported message types are ignored.
6. Mention placeholders are removed before CHAT-M1 receives the message.
7. Recent conversation history is supplied on later turns and remains bounded.
8. Feishu token and reply API failures do not expose secrets.
9. Missing server configuration returns HTTP 503.
10. Existing CHAT-M1 and public contract tests remain green.

## Out of Scope

- Encrypted Feishu callback payloads.
- Persistent event queues, distributed locks, or durable conversation storage.
- Rich-text, image, audio, and document extraction.
- Interactive confirmation cards.
- Requirement analysis, confirmation, solution compilation, and frontend publication.

## Implementation

- `backend/app/solution/feishu_bot.py`
- `backend/app/solution/api.py`
- `backend/app/solution/__init__.py`
- `.env.example`
- `tests/solution/test_feishu_bot.py`
- `tests/solution/test_feishu_bot_api.py`

## Verification

- CHAT-M2 tests: 15 passed.
- CHAT-M1 and CHAT-M2 combined: 30 passed.
- Public contract tests: 3 passed.
- Full suite: 461 passed, 1 unrelated existing fixture precision mismatch.
  The failing assertion compares `82.64285714285715` with
  `82.64285714285714` in `test_solution_quality_fixture.py`.
