# JPS-One One-Click Email Outreach

This module is the controlled email sending path used by the Email Outreach UI.

## Current Rules

- A user may send another email to the same customer or same email address. The system does not block repeated sends by lead history.
- Browser double-clicks and network retries are still protected by the per-request `Idempotency-Key` for the same preview snapshot.
- SMTP sending remains asynchronous through the SQLite outbox and is still limited by the hourly and daily send caps.
- A queued message stores both `body_text` and optional sanitized `body_html`. SMTP sends multipart text/html when HTML exists.
- Email template variables are the only auto-filled content. The backend does not invent extra evidence, internal scoring notes, or customer research text inside the outbound email body.

## UI Flow

- Task groups use an `选项` action. The modal can edit the display name/note or remove the task from the email module.
- The one-click template editor and template library use a compact rich-text toolbar for basic font, size, bold, red/black, clear formatting, and JPS signature insertion.
- Preview remains the approval checkpoint. After preview, `确认进入队列` creates the queued send request and the status panel shows progress.

## Backend Touchpoints

- `backend/api/email_routes.py`: preview/start APIs, task preferences, template workspace/library payloads.
- `backend/emailing/store.py`: SQLite schema and migrations for HTML templates, task preferences, and message HTML.
- `backend/emailing/html_sanitizer.py`: safe HTML sanitizer and plain text fallback helpers.
- `backend/emailing/providers/smtp_provider.py`: multipart text/html SMTP sending through the unified provider.
