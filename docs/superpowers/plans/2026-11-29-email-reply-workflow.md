# Email Reply Workflow Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans task by task.

**Goal:** Let the user select images and confirm later stages by replying to email, with automatic production continuation.

**Architecture:** Preserve the existing producer and immutable admission records. Add a read-only IMAP adapter, interactive mail mode, review request helpers and a durable coordinator around make_managed_video. Separate files permit independent implementation and focused tests.

**Tech Stack:** Python 3.12 standard library, existing QQ SMTP and production APIs, Windows PowerShell launcher.

**Spec:** docs/superpowers/specs/2026-11-29-email-reply-workflow-design.md

## Global constraints

- Keep reference dependency batches; preserve frozen narration and previous work.
- Do not revalidate or regenerate historical media while merely waiting for mail.
- No real mail in tests. Reuse config/secrets.local.json for credentials.
- Work in the operational checkout and preserve all unrelated edits; no commits or branch switching during production (existing operational ruling).
- Only explicit human confirmations create review submissions. No arbitrary email commands.

## Review focus

Quoted outbound templates must not count as replies; duplicate/replayed replies must not run twice; partial selections must not advance; interrupted SMTP must not resend blindly; a completed action with a lost local completion receipt must resume idempotently.

### Task 1: IMAP reply transport

Files: src/video_ai/mail_replies.py and tests/unit/test_mail_replies.py.

Interface: MailboxSettings(host='imap.qq.com', port=993, mailbox='INBOX', poll_seconds=30, timeout_seconds=30); MailReply(key, message_id, sender, text); ImapReplyReader(settings=None, *, credential_name='VIDEO_AI_SMTP_AUTH_CODE', imap_factory=None).poll(message_ids)->list[MailReply]. extract_reply_text(message)->str. MailboxError contains only safe error categories.

- [x] Write failing local fake-IMAP tests for matching replies, PEEK, filtering and safe failures.
- [x] Implement TLS login with existing local credentials and no mailbox mutations.
- [x] Verify targeted tests, including quoted plain/HTML replies and UIDVALIDITY identity.

### Task 2: One email per image batch and reply instructions

Files: src/video_ai/adapters/selection_email.py; src/video_ai/runtime/production_image_selection.py; src/video_ai/mail_workflow_context.py; related tests.

Interface: build_messages(..., reply_mode=False); mail_reply_mode() and mail_reply_context() context manager. Existing defaults and historical bytes remain unchanged.

- [x] Write failing tests for a single preview email covering more than eight candidates and a complete reply template.
- [x] Implement preview-first one-message sizing and explicit confirmation instructions only in reply mode.
- [x] Connect reply mode at notification creation and verify legacy MIME/SMTP tests.

### Task 3: Confirmation requests and reply mapping

Files: src/video_ai/mail_review_requests.py and tests/unit/test_mail_review_requests.py.

Interface: build_review_request(result:dict)->dict|None returning kind, binding, subject, body_template, templates (list of canonical JSON templates), attachments (list of paths), action (production keyword). parse_review_reply(request:dict,text:str,*,reviewer:str,viewed_at:str)->list[dict]. Image-group review and publish are explicit kinds. Full current sources are preserved in the request.

- [x] Read actual clip/final/continuity template schemas; write meaningful failing tests.
- [x] Build concise authored-field reply templates; preserve source identities and require viewing declarations.
- [x] Verify failure/unverified replies never become passed and each supported gate maps to its existing consumer.

### Task 4: Durable coordinator and launcher

Files: src/video_ai/mail_workflow.py; src/video_ai/cli.py; scripts/migrate_windows.ps1; workflow tests and operator documentation.

Interface: run_mail_workflow(config=None, *, video=None, title=None, script=None, text=None, wan_mode='fast', once=False, ...injected dependencies)->int. New CLI mail-video accepts normal production inputs. User-facing launcher invokes it; direct make-video behavior stays unchanged.

- [x] Write failing tests for waiting, reply submission, next-stage advancement and recovery without duplicate effects.
- [x] Implement separate workflow ownership lock, durable request/reply/action journal, IMAP polling, safe email sends and explicit publishing.
- [x] Add exact scene/candidate parsing and image-group acceptance after all choices.
- [x] Connect launcher, document account IMAP prerequisite and restart behavior.
- [x] Run focused combined tests, inspect diffs and independently review changes. Final result: 203 passed; launcher syntax, CLI help and scoped diff checks passed. Independent re-review reports no remaining P1/P2 findings.
- [x] Check the real mailbox once without displaying credentials. IMAP read-only connection succeeded.
- [x] Preserve video 0003 first-batch selections. User requested manual startup; provide its resume command instead of activating or generating the next batch.

## Review notes

Independent review found and fixed persistent viewing timestamps, partial request
initialization, accepted reply completion ordering, independent OS wait locking,
pinned revision resumes, reply-local continuity staging and repeated unverified
gate handling. Focused aggregate verification is recorded after integration.
Adjacent pre-existing integration fixtures reject tool/continuity paths outside
their isolated runtime; no broad fixture migration is part of this change.

Detailed verification and named adjacent fixture failures are recorded in
`docs/research/email-reply-workflow-verification-20261129.json`.
