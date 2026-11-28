# Email reply driven video production

The user approved keeping reference-dependent image batches, with each batch
continued automatically by replying to email. Current video 0003 has 55 scenes
in five batches. Its first three selections have already been accepted.

## User flow

The existing generate_video.cmd entry starts or resumes production and remains
available to receive replies. Each dependency batch sends one email containing
all candidate previews and a copyable plain-text selection template. The user
replies with scene=candidate lines and an explicit submission confirmation.
The program records the existing selection format and resumes automatically.
Existing image-group, video playback, continuity and final-film confirmation
gates also send the current artifacts and a reply template, then wait. Replies
must explicitly state the required viewing and judgment; no passed observations
are inferred from selecting an image. Publishing requires explicit email approval.

## Approaches

Generating every scene before human selection would require provisional
baselines and potentially regenerating descendants when a baseline changes.
The user instead selected preserving dependency batches and replying to each
email to continue. Existing production admission and frozen inputs are retained.

## Boundaries

- QQ IMAP over verified TLS at imap.qq.com:993 receives thread replies. The
  existing local VIDEO_AI_SMTP_AUTH_CODE and confirmed mailbox are reused.
- Reads use BODY.PEEK and never delete, move or mark unrelated messages.
- Replies are bound to current outbound Message-ID and exact pending request;
  unrelated senders, quoted templates, obsolete threads and duplicate UIDs do
  not advance production. Mail contents never execute commands.
- A durable workflow journal survives restarts and records pending requests,
  SMTP intents/receipts, raw reply evidence, submissions and completed actions.
  Unknown SMTP DATA outcomes do not cause automatic resend.
- Wait loops release production locks and do not repeatedly validate/rehash
  historical videos or regenerate accepted media.
- No narration, historical production snapshots or accepted selections change.
- Existing direct make-video remains available. The user-facing launcher uses
  a new mail-video coordinator; the computer and coordinator must remain running
  to continue automatically. Restarting the same video restores its pending wait.

## Verification

Local transports cover image batching, reply matching, quoted text, duplicates,
malformed selections, restarts and exactly-once coordinator progression. Existing
selection/SMTP tests run as regressions. A single read-only IMAP login check is
permitted by the user's request; actual production resumes only through the
normal coordinator. Report external account prerequisites separately.
