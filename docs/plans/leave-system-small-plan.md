# HR Leave System Small Implementation Plan

> **For Hermes:** Keep this slow and small. Do not build calendar/activity yet. Avoid bloated workflow.

**Goal:** Add a practical leave request workflow for the ITSM demo using the existing `manager` role for approval.

**Architecture:** Leave is its own module first. Calendar, company holidays, activities, attachments, and automation come later as layers on top of stored leave data.

**Scope rule:** One small deploy at a time. First create space/navigation and MVP data flow; then add approval; then add balance/carry-forward.

---

## Phase 1 — Minimal Leave Space

**Objective:** Make the app visibly ready for Leave without touching calendar/activity.

**Files likely touched:**
- `templates/base.html` — sidebar item
- `app.py` — simple `/leave` route
- `templates/leave.html` — placeholder/list page

**Sidebar placement:**
- Add one item: `Leave`
- Icon: `bi-calendar-check`
- Put after `Route Planner` or before `ทีมงาน`
- Keep no nested HR menu for now to avoid bloat.

**Acceptance:**
- Sidebar shows Leave.
- `/leave` opens without error.
- No approval logic yet.

---

## Phase 2 — Leave Request MVP

**Objective:** User can submit a leave request and see own history.

**DB table:** `leave_requests`
- `id`
- `username`
- `leave_type`
- `start_date`
- `end_date`
- `days`
- `reason`
- `status` — `pending`, `approved`, `rejected`, `cancelled`
- `approver`
- `approval_note`
- `created_at`
- `updated_at`

**Thai labels:**
- `pending` → `รออนุมัติ`
- `approved` → `อนุมัติ`
- `rejected` → `ไม่อนุมัติ`
- `cancelled` → `ยกเลิก`

**Leave types:**
- `annual` → `ลาพักร้อน`
- `sick` → `ลาป่วย`
- `personal` → `ลากิจ`
- `other` → `อื่นๆ`

**Acceptance:**
- User creates request.
- Request appears in `/leave`.
- Default status is pending.

---

## Phase 3 — Manager Approval

**Objective:** Existing `manager` and `admin` roles can approve/reject.

**Route/page:**
- `/leave/approvals`

**Rules:**
- `manager` and `admin` see all pending leave.
- Regular `user` sees only own leave.
- `hr` may view leave records later, but manager approval is first.

**Actions:**
- Approve
- Reject
- Add short note

**Acceptance:**
- Manager approves/rejects pending leave.
- Status updates visibly.
- Approver name is stored.

---

## Phase 4 — Balance + Carry Forward

**Objective:** Show useful leave balance without full automation.

**Demo rule:**
- Annual quota: 10 days/year
- Carry forward max: 5 days
- Used days calculated from approved annual leave
- Remaining = quota + carried_forward - used

**Implementation note:**
- Keep carry-forward manually editable/configurable first.
- Do not build year-end cron yet.

**Acceptance:**
- Leave page shows cards:
  - `สิทธิ์ปีนี้`
  - `ยกมา`
  - `ใช้แล้ว`
  - `คงเหลือ`

---

## Later — Calendar + Company Holidays

Do not put this into Leave MVP.

Later tables/features:
- `company_holidays`
  - `date`
  - `name`
  - `type`
  - `is_paid`
- `/calendar`
- Calendar displays:
  - approved leave
  - pending leave
  - company holidays
  - site visits / activities later

Later calculation:
- Exclude weekends
- Exclude company holidays
- Count working days only

---

## Explicit Non-Goals for First Build

- No full calendar
- No activity/site visit module
- No attachments
- No auto carry-forward cron
- No Telegram/email notification
- No complex multi-level approval
- No holiday-aware day calculation yet

---

## First safe commit target

`[verified] add leave module placeholder`

Then next commit:

`[verified] add leave request workflow`
