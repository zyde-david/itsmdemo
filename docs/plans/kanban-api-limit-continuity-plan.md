# Kanban API Limit Continuity Plan

> **For Hermes:** This is a planning/spec card only. Do not implement, deploy, or change provider credentials from this plan without a separate approved Kanban implementation card.

**Goal:** Keep the user's Kanban-first ITSM workflow moving when the main LLM/API provider hits rate, quota, or transient availability limits.

**Architecture:** Split continuity into deterministic operations first, low-cost reasoning fallback second, and human-visible status last. A no-agent watchdog should inspect board state and send operational summaries without spending LLM tokens; only cards that truly need reasoning should dispatch to an available fallback profile/model. The system must avoid tight retry loops, respect QA/GG deployment gates, and schedule non-urgent heavy work for night windows.

**Scope rule:** This plan specifies behavior and an implementation breakdown only. Implementation, provider credential changes, cron creation, and deployment require separate user approval.

---

## Product stance

### What should continue during API limits

1. Board visibility:
   - Report tasks that are `blocked`, `done`, `failed/spawn_failed`, or waiting for review.
   - Summarize what can safely run now vs what should wait.
2. Deterministic queue hygiene:
   - Reclaim stale claims if Hermes already supports it through the dispatcher.
   - Promote/unblock only when an existing explicit user/human approval exists.
   - Never invent approval or silently push deployment work forward.
3. Small urgent work:
   - Allow daytime dispatch for urgent/small cards when a fallback agent is available.
4. Heavy/non-urgent work:
   - Defer to night schedule by default.
   - Prefer batching QA/review/spec cards before build/deploy cards.

### What must not continue automatically

- No auto-deploy.
- No bypass of QA or user `GG` gate.
- No hidden repeated retries against an exhausted provider.
- No credential/key rotation that hides cost or quota problems from the user.
- No agent-generated changes when all available providers are failing; send status instead.

---

## Proposed operating modes

### Mode A — No-agent watchdog, default first line

Use a Hermes cron job with `no_agent=True` and a script that performs deterministic board inspection and emits a plain-text summary only when there is something useful to say.

Responsibilities:
- Read Kanban board state from the active board database.
- Count tasks by status and priority.
- Identify recently done/blocked/spawn-failed cards since the last successful watchdog tick.
- Identify ready urgent/small cards that may be dispatched by the normal dispatcher.
- Identify heavy cards that should be left for night.
- Emit concise operational status to the origin/home channel.

Silence rule:
- If no change and no action required, print nothing so the cron run stays quiet.

Suggested schedule:
- Daytime: every 30–60 minutes, no-agent summary only.
- Night: every 1–2 hours, include heavier queued-card summary.
- Optional one-shot recovery: manually run watchdog after the user reports provider/API limit.

### Mode B — Fallback reasoning agent

Use an LLM-backed cron/dispatch profile only when a card needs interpretation, coding, review, or planning.

Fallback selection order:
1. Primary provider/model if healthy.
2. Cheaper provider/model for planning, triage, summaries, and docs.
3. Local/private model if configured and adequate for simple status or spec drafting.
4. No-agent status-only output if no model can answer safely.

Rules:
- Fallback profiles should have lower-risk toolsets where possible (`kanban`, `file`, maybe `terminal`; avoid broad deploy tooling unless needed).
- Use per-job `model` override for cron jobs when appropriate.
- Prefer profile-level/provider-level credential pools for rotation, but surface exhaustion state in status summaries.

### Mode C — Night heavy queue

Use schedule windows rather than repeatedly trying heavy cards during the day.

Daytime allowed:
- Urgent production fixes.
- Small QA/audit/spec cards.
- Review-required handoff summaries.
- No-agent board status.

Night preferred:
- Multi-file builds.
- Large browser QA sweeps.
- Full test suites.
- Research/long docs.
- Non-urgent UI enhancement batches.

---

## State to track

Create a small local state file for the continuity layer, separate from app data and never committed if it contains operational timestamps.

Recommended path:
- `~/.hermes/kanban-continuity-state.json` for machine-local state, or
- a profile-scoped state under `~/.hermes/` if multiple profiles need isolation.

Fields:

```json
{
  "providers": {
    "openrouter": {
      "state": "healthy|limited|exhausted|unknown",
      "last_success_at": "2026-06-06T10:00:00+07:00",
      "last_failure_at": "2026-06-06T10:30:00+07:00",
      "next_retry_at": "2026-06-06T11:00:00+07:00",
      "failure_count": 2,
      "last_error_class": "rate_limit|quota|auth|network|server|unknown"
    }
  },
  "last_watchdog_summary_at": "2026-06-06T10:45:00+07:00",
  "last_seen_task_events": {
    "t_example": 1780718406
  },
  "cooldowns": {
    "profile:default": "2026-06-06T11:00:00+07:00"
  }
}
```

Backoff rules:
- Rate limit: retry after provider header if available; otherwise exponential backoff starting at 15 minutes, capped at 4 hours.
- Quota exhausted: no automatic retry until next known reset window or manual `hermes auth reset PROVIDER` / credential update.
- Auth error: block/status only; do not retry tightly.
- Network/server error: retry with jitter, capped; fail over if another provider is healthy.
- After 3 consecutive failures on the same card/profile/provider, stop dispatching that combination and report it.

---

## Board/status policy

### Status summary shape

Use short, human-readable text:

```text
Kanban continuity status:
- Main provider: limited until ~11:00; no tight retry.
- Board: 2 ready, 1 blocked, 3 done since last check.
- Safe daytime action: dispatch small QA card t_xxx if approved.
- Deferred to night: heavy UI build cards.
- Deployment: none; QA + user GG still required.
```

### Block/done notifications

No-agent watchdog can report:
- New `done` handoffs.
- New `blocked` reasons.
- Spawn failures that need credentials/provider action.
- Review-required cards waiting for human eyes.

It should not summarize every unchanged card repeatedly.

### Approval gates

Allowed automatically:
- Notify status.
- Dispatch ready cards that were already approved and assigned to a worker profile.
- Run deterministic QA/status scripts with no side effects.

Requires user approval/GG:
- Deploy.
- Provider credential changes.
- New fallback provider spend.
- Running a broad/heavy card during daytime if not urgent.
- Unblocking a card when the unblock reason is a product decision rather than an operational retry.

---

## Implementation breakdown for a future card

### Task 1: Add a deterministic board-inspection script

**Objective:** Produce a concise board status from SQLite without using an LLM.

**Files:**
- Create: `scripts/kanban_continuity_watchdog.py` or profile script under `~/.hermes/scripts/kanban_continuity_watchdog.py`

**Behavior:**
- Open the active Kanban DB.
- Read tasks/events/runs needed for counts and deltas.
- Read/write continuity state JSON.
- Print nothing if no user-visible change.
- Print a status summary if blocked/done/spawn-failed/review-required changed.

**Verification:**
- Run once against the current board.
- Run twice and verify the second run is silent if nothing changed.
- Simulate a blocked/done event and verify one summary appears.

### Task 2: Add provider-limit classifier

**Objective:** Normalize rate-limit, quota, auth, network, and server failures into state + next retry time.

**Files:**
- Modify/create the watchdog helper module from Task 1.

**Behavior:**
- Classify known error text/status codes.
- Respect retry headers when available.
- Use exponential backoff with jitter when no retry time exists.
- Persist `failure_count`, `last_error_class`, and `next_retry_at`.

**Verification:**
- Unit-test sample errors for OpenRouter/Anthropic/OpenAI-style messages if available.
- Confirm quota/auth errors do not tight-loop.

### Task 3: Create no-agent cron job

**Objective:** Schedule deterministic status without model usage.

**Command shape:**
- Use Hermes cron with `script` and `no_agent=True`.
- Deliver to origin/home channel as configured by the user.

**Acceptance:**
- Empty stdout sends no message.
- Non-empty stdout sends exactly the status summary.
- Broken script sends an error alert rather than failing silently.

### Task 4: Define fallback model/profile policy

**Objective:** Make reasoning fallback explicit and cheap.

**Config/spec:**
- Primary coding/review profile remains unchanged.
- Add optional fallback cron jobs or worker profiles for planning/status only.
- Pin lower-cost model overrides for planning summaries.
- Keep deploy-capable tasks on normal gated workflow.

**Acceptance:**
- Fallback is visible in config/cron list.
- User can disable/pause it quickly.
- Status summary names which provider/profile is limited.

### Task 5: Add day/night priority rules

**Objective:** Prevent heavy non-urgent tasks from burning daytime quota.

**Behavior:**
- Tag or infer heavy tasks by title/body keywords and priority.
- Daytime watchdog reports heavy cards as deferred.
- Night window may dispatch approved heavy cards if provider healthy.

**Acceptance:**
- Urgent/small cards are not delayed unnecessarily.
- Heavy non-urgent cards are summarized, not retried all day.

### Task 6: Document operator runbook

**Objective:** Give the user simple commands and decisions.

**Files:**
- Create/update: `docs/plans/kanban-api-limit-continuity-plan.md`
- Optional later: `docs/howto` or internal Dev Log entry if implemented.

**Runbook should include:**
- How to see cron jobs.
- How to pause/resume continuity watchdog.
- How to reset provider exhaustion after fixing credentials.
- What statuses mean.
- Reminder: deploy still needs QA + GG.

---

## Acceptance criteria for the future implementation

- When the main provider is limited, the user still receives board status instead of silence.
- Deterministic watchdog uses no LLM tokens in normal status mode.
- Reasoning fallback is opt-in/configured and visible.
- Provider failure state includes next retry time and failure count.
- Retry loops are bounded and jittered.
- Heavy non-urgent cards are deferred to night.
- Daytime urgent/small cards can continue if an approved provider/profile is available.
- No deploy happens automatically.
- QA + user GG remains mandatory before deployment.

---

## Recommended default decision

Start with Mode A only: a no-agent watchdog that reports board state and provider-limit status. After that is stable, add Mode B fallback reasoning for planning/review cards, then Mode C night heavy queue. This keeps cost and surprise low while solving the main pain: Kanban should not go silent when the primary API is limited.
