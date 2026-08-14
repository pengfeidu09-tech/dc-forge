# CHAT-M3: Feishu QR Registration and WebSocket Transport

**Status:** implemented

## Goal

Let a DCForge operator scan a QR code with Feishu to create a personal bot
application, store the returned application credentials locally, and receive
customer messages through Feishu's long-connection transport without requiring a
public callback URL.

This is a DCForge integration. It uses Feishu's device-code application-registration
protocol directly and does not run or depend on OpenClaw.

## Architecture Boundary

```text
Feishu personal bot
        │ WebSocket: im.message.receive_v1
        ▼
CHAT-M3 transport adapter
        │ normalized Feishu event
        ▼
FeishuBotService
        │ conversation request
        ▼
DCForge conversation agent
        │ next_action / later business orchestration
        ▼
Requirement Intelligence -> Requirement Truth -> Solution Intelligence
```

- CHAT-M3 owns application registration, local credential storage, and WebSocket
  event transport.
- The existing `FeishuBotService` owns Feishu conversation identity, deduplication,
  bounded chat memory, and replies.
- The DCForge conversation/agent layer decides when to invoke Requirement
  Intelligence and Solution Intelligence.
- CHAT-M3 must not create, confirm, or mutate Requirement Truth itself.
- OpenClaw is neither a runtime dependency nor part of the message path.

## Scope

- Implement Feishu account-center application registration:
  1. `action=init` and require `client_secret` support.
  2. `action=begin`, `archetype=PersonalAgent`, `auth_method=client_secret`, and
     `request_user_info=open_id`.
  3. Display `verification_uri_complete` as a terminal QR code.
  4. Poll with `action=poll`, the device code, and `tp=ob_cli_app`.
- Handle `authorization_pending`, `slow_down`, `access_denied`, `expired_token`,
  timeout, transient network errors, and sanitized unknown errors.
- Store `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, the API domain, and the registering
  user's `open_id` in the local `.env` file without printing the app secret.
- Preserve unrelated `.env` entries and make a newly written credential file
  owner-readable and owner-writable only.
- Add a CLI for registration and long-connection startup.
- Use the official Python `lark-oapi` SDK to subscribe to
  `im.message.receive_v1` over WebSocket.
- Normalize SDK event objects into the existing `FeishuBotService.process_event`
  payload shape.
- Dispatch model work outside the SDK callback so the WebSocket event can be
  acknowledged promptly.
- When QR registration returns an owner `open_id`, accept messages only from that
  user by default.

## Configuration

- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_ALLOWED_OPEN_ID` (written by QR setup when available)
- `FEISHU_API_BASE_URL` (`https://open.feishu.cn` for Feishu)
- `FEISHU_VERIFICATION_TOKEN` remains required only by the optional HTTP callback
  transport from CHAT-M2.

DeepSeek remains configured independently through the existing OpenAI-compatible
variables:

- `LLM_API_KEY`
- `LLM_BASE_URL=https://api.deepseek.com/v1`
- `LLM_MODEL=deepseek-chat`

## Operator Commands

```bash
python -m backend.app.solution.feishu_setup setup
python -m backend.app.solution.feishu_setup listen
```

`setup --listen` may perform both operations in one process.

## Safety and Reliability

- Never print, log, return, or include `client_secret` in an exception.
- Registration requests are sent only to fixed Feishu/Lark account-center hosts.
- Credentials are stored only in the operator-selected local env file, which is
  ignored by Git in this repository.
- QR-created personal bots default to the registering user's `open_id` allowlist.
- The current process-local event deduplicator remains the idempotency boundary.
- WebSocket delivery and chat memory are not durable across process restarts.
- Model output cannot choose arbitrary Feishu API operations.

## Acceptance Criteria

1. Registration initialization rejects environments without `client_secret`.
2. Begin registration sends the PersonalAgent parameters and returns a scannable QR
   URL with the CLI registration marker.
3. Polling waits on pending authorization and increases its delay on `slow_down`.
4. Denial, expiry, timeout, network failure, and unknown errors are handled without
   exposing credentials or response bodies.
5. Successful registration returns App ID, App Secret, domain, and owner `open_id`.
6. Credential persistence preserves unrelated env entries and never writes secrets
   to stdout.
7. SDK message events are normalized and delivered once to `FeishuBotService`.
8. The SDK callback schedules conversation work asynchronously.
9. A configured owner allowlist ignores messages from other Feishu users.
10. CHAT-M1, CHAT-M2, new CHAT-M3, and public contract tests remain green.

## Out of Scope

- Reimplementing OpenClaw or using it as a gateway.
- Editing frozen Requirement Intelligence contracts or process semantics.
- Durable message queues or multi-process conversation memory.
- Rich-text, image, audio, and document ingestion.
- Frontend bot-management UI.
- Automatically confirming requirements or publishing a formal solution.

## Implementation

- `backend/app/solution/feishu_registration.py`
- `backend/app/solution/feishu_ws.py`
- `backend/app/solution/feishu_setup.py`
- `backend/app/solution/feishu_bot.py`
- `.env.example`
- `requirements.txt`
- `tests/solution/test_feishu_registration.py`
- `tests/solution/test_feishu_ws.py`

## Verification

- CHAT-M1, CHAT-M2, and CHAT-M3 tests: 43 passed.
- Public contract tests: 3 passed.
- Full suite: 474 passed, 1 unrelated existing fixture precision mismatch.
  The failing assertion compares `82.64285714285715` with
  `82.64285714285714` in `test_solution_quality_fixture.py`.
