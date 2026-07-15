# Session Opener — reusable template

How to start a Claude Code session so the CHANGELOG archive + current-feature.md
swap happen automatically (per the CLAUDE.md session-workflow rule). Fill in the
blanks, paste as the first message of the session.

The habit: **do NOT hand-edit `current-feature.md` when a completed task is still
in it.** Hand the new task's content to Claude Code in the opener and let it manage
the file — otherwise you wipe the old task's Goals + History before it can be copied
to CHANGELOG. From now on you basically stop touching `current-feature.md` by hand.

---

## Case A — a completed task is still sitting in current-feature.md
(Archive the old, load the new, kick off audit-first — one atomic swap.)

```
The task currently in context/current-feature.md ([OLD TASK NAME]) is complete
and verified — I confirm it's done. Archive it per our workflow (final Goals +
full History to context/CHANGELOG.md, newest at top, matching existing format),
then reset current-feature.md to the content below.

Once that's done, begin the audit-first step from the new task: read the files
it names, show me the exact current state of what you'll change, confirm any
tenant/db plumbing, and propose your plan. Do NOT write code until I confirm.

--- new current-feature.md ---
[PASTE THE FULL NEW current-feature.md HERE]
```

Order matters: it archives *from* the existing file first (while the old text is
still there), then overwrites. Never pre-save the new file yourself.

---

## Case B — current-feature.md is already blank / already holds the new task
(No archive needed — just start.)

```
Read context/current-feature.md and begin the audit-first step: read the files
it names, show me the exact current state of what you'll change, list what you'd
change and why, and propose your plan. Do NOT write code until I confirm.
```

---

## Case C — mid-task follow-up (same session or resuming)
```
Continue the task in context/current-feature.md. Here's where we are: [WHAT'S DONE].
Next concern is [ONE THING]. Audit first if it's more than a trivial edit, then
propose before writing. One concern per commit.
```

---

## The rhythm after the opener (same every time)
1. Claude Code archives + swaps files (Case A only), then returns an **audit + plan**
   — including any decision points the task flagged.
2. You **confirm or tweak** the plan.
3. It writes the change (complete drop-in replacement when things are complex),
   **tests, commits**, and adds a dated line to the new task's History.
4. When fully verified, you say **"done — archive it."** That confirmation is now
   the only CHANGELOG "work" you do; the CLAUDE.md edit makes the copy-paste its job.

## Guardrails to hold the line on
- **One concern per commit.** If it proposes folding in an out-of-scope file or a
  flagged side-item, split it — CLAUDE.md backs you up.
- **Deploy commands come to you, not executed by Claude Code.**
- **Never archive unprompted** — the archive only fires after your explicit "done"
  confirmation. If it tries to archive before you've confirmed, stop it.
- **Both repos** carry the same workflow rules — behavior should match across backend
  and frontend sessions.
