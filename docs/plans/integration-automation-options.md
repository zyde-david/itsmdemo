# Integration automation options — Google API vs Zapier vs self-hosted

Status: decision note for review  
Scope: ITSM demo integrations that may connect tickets, assets, staff, calendar/leave, documents, email, chat, spreadsheets, and future BI/AI helper workflows.

## Short recommendation

Use more than one integration style instead of treating one tool as always safe or unsafe:

1. Sensitive ITSM data: prefer direct API integration or self-hosted/private automation so scopes, secrets, logs, and data retention stay under tighter control.
2. Low-risk cross-app automation: Zapier, Make, Pipedream, or similar can be appropriate when speed and app coverage matter more than full data control.
3. Local/private constraints: if payloads contain private ticket details, staff data, branch operations, asset history, debt/NPL/collateral context, or AI prompts with internal details, use self-hosted n8n or backend jobs with minimized payloads.
4. Human approval stays required before automation changes ticket status, priority, category, assignment, SLA, leave approval, or published KB content.

## Comparison matrix

| Option | Data exposure path | Least-privilege scopes | Secret storage | Audit / logs | Revocation | Cost | Maintenance | Supported apps | Build speed | Local/private fit |
|---|---|---|---|---|---|---|---|---|---|---|
| Direct Google API | ITSM server talks directly to Google services. Data goes only through app server + Google API. | Strong if OAuth scopes are narrow, e.g. specific Calendar/Drive/Gmail permissions only when needed. | Server-side env/secret manager; no browser-exposed tokens. | App can log exactly what was sent, who approved it, and API response IDs. Google admin/audit logs may help depending on account tier. | Revoke OAuth client, service account, refresh token, or individual user grant. | Usually low API cost, but engineering time is higher. | Higher: must handle OAuth, retries, quotas, schema changes, errors. | Mostly Google ecosystem unless more APIs are built. | Medium/slow. | Good for sensitive data when payloads are minimized and scopes are tight. |
| Zapier | ITSM payload goes to Zapier, then target apps. Zapier becomes an extra third-party data processor. | Depends on each connected app and Zap design; can be acceptable if only sending safe fields. | Secrets live in Zapier connected accounts and app connections. | Zap history is useful for troubleshooting but may contain payload data; app-side logs vary. | Disable Zap, disconnect app account, rotate target app credentials. | Easy start; ongoing task volume can become paid. | Low/medium: Zapier manages connectors, but complex workflows can become hard to version/test. | Very broad app library. | Fast. | Best for low-risk notifications, demo workflows, and non-sensitive summaries; avoid raw private records unless approved. |
| Make / Pipedream | Similar bridge path: ITSM -> automation platform -> target apps. Pipedream may involve code steps; Make has visual scenarios. | Depends on connector scopes and workflow design. | Platform-managed connected accounts/secrets. | Good execution history; risk that payloads appear in run logs. | Disable workflow, remove connections, rotate keys. | Often cheaper/flexible at small scale, varies by volume. | Medium: powerful but needs governance/versioning for serious use. | Broad; Pipedream strong for developer/API workflows. | Fast/medium. | Good for prototypes and controlled low/medium-risk automations; minimize payloads. |
| Self-hosted n8n | ITSM talks to an automation runner we operate. Data can stay inside our server/VPC if target app permits. | Good if credentials and nodes are scoped carefully. | Stored in our infrastructure; must secure DB, backups, admin access. | We control logs and retention, but must configure them safely. | Disable workflow, rotate credentials, shut down runner. | Hosting + ops cost; software may have license limits depending on deployment. | Medium/high: upgrades, backups, monitoring, security patches. | Broad, but less plug-and-play than Zapier for some apps. | Medium. | Strong option when privacy matters and no-code/low-code workflow is still desired. |
| Backend jobs / local scripts | ITSM backend performs the workflow directly; no bridge unless target API is external. | Strongest because code can enforce exact fields and role checks. | Same server-side secret pattern as the app. | Strong: write app-native audit trail tied to user/action/ticket. | Revoke app token/secret, deploy config change, disable feature flag. | Low platform cost, higher engineering cost. | Higher engineering ownership. | Only what we implement. | Slowest for new apps. | Best for private data, compliance-like flows, and workflows needing strict approval gates. |

## Practical policy for the ITSM demo

### Safe uses for Zapier / Make / Pipedream

Use automation bridges when the data is low-risk and the value is speed:

- Send a Slack/Telegram/email notification that a new generic ticket exists, without full private notes.
- Add a non-sensitive reminder to a calendar, e.g. branch visit planned, no staff/private detail in description.
- Copy public demo lead/contact form data into a spreadsheet or CRM.
- Trigger demo-only workflows during interviews or portfolio presentations.
- Send only a ticket ID/link + broad status, requiring login to see details inside ITSM.

### Prefer direct API or self-hosted/private automation

Use direct backend integration, self-hosted n8n, or local jobs when payloads contain:

- Staff personal data, leave details, HR context, or manager approval notes.
- Ticket descriptions with customer/member details, finance/cooperative details, or security incidents.
- Asset inventory and branch topology that should not leak externally.
- BI routes involving NPL/debt/collateral planning or field-visit prioritization.
- AI prompts/summaries that include private operational facts.

### Minimum controls for any option

- Send only the fields needed for the task; prefer IDs/links over full records.
- Keep secrets server-side or inside the approved automation platform account; never expose keys in frontend templates.
- Use separate demo credentials from production credentials.
- Add a clear audit trail: who/what triggered the workflow, payload category, target app, result, and timestamp.
- Keep human approval for state-changing actions.
- Provide a kill switch: feature flag, disabled workflow, revoked token, or disconnected app account.
- Review automation run logs so they do not store sensitive payloads longer than necessary.

## Recommended architecture by use case

| Use case | Default choice | Why |
|---|---|---|
| Google Calendar leave visibility | Direct Google Calendar API or backend calendar sync after approval | Branch/HR scope and approved-leave rules are sensitive; app can enforce manager branch-only visibility before syncing. |
| Public/interview demo notifications | Zapier/Make/Pipedream | Fast to build, low-risk if only demo/public fields are sent. |
| Ticket summary to chat | Bridge only for ticket ID + safe summary; direct/self-hosted for private details | Avoid leaking raw ticket text; require login for details. |
| KB draft generation | Backend AI/private mode first; bridge only for non-sensitive drafts | AI output should be reviewed before publishing. |
| BI map / route planning | Backend/local/self-hosted | Route priorities may reveal operational/financial context. |
| Spreadsheet export for management | Direct Google Sheets API if needed; bridge for demo-only anonymized exports | Direct API gives tighter scopes and better app-native audit. |

## Product wording for Vision / How To later

Suggested short copy after approval:

> Integrations are chosen by data sensitivity. For quick low-risk workflows, tools like Zapier/Make can connect many apps fast. For private ITSM data, Google direct APIs, backend jobs, or self-hosted automation keep scopes, secrets, audit logs, and data flow tighter. Automation helps prepare work, but people approve important changes.

Thai/local-friendly version:

> งานเชื่อมระบบเลือกตามความเสี่ยงของข้อมูล ถ้าเป็นงานแจ้งเตือนทั่วไปใช้ Zapier/Make ได้เร็ว แต่ถ้าเป็นข้อมูล ticket, staff, asset, leave หรือ BI ที่อ่อนไหว จะใช้ direct API, backend job หรือ self-hosted automation เพื่อคุมสิทธิ์ secret log และเส้นทางข้อมูลให้ชัดกว่า Automation ช่วยเตรียมงาน แต่การเปลี่ยนสถานะสำคัญยังให้คนกดยืนยันก่อน

## Decision

Adopt a risk-tiered integration policy:

- Tier 1 public/demo/low-risk: Zapier/Make/Pipedream are acceptable.
- Tier 2 internal but not highly sensitive: bridge tools allowed only with minimized payloads and explicit audit notes.
- Tier 3 sensitive ITSM/HR/BI/AI: direct API, backend job, local/private model, or self-hosted workflow by default.

This keeps Zapier in the toolbox without presenting it as automatically unsafe, while still protecting the data categories that matter most for the ITSM demo roadmap.
