# Session Opener — reusable template

How to start a Claude Code session so the CHANGELOG archive + current-feature.md
swap happen cleanly (per the CLAUDE.md session-workflow rule). Fill in the
blanks, paste as the first message of the session.

**The one rule that matters:** never overwrite `current-feature.md` while a
*completed but un-archived* task is still in it — the old task's Goals + History
must reach `context/CHANGELOG.md` first, or they're gone. There are two safe ways
to swap tasks, and you can use whichever fits:

- **Atomic swap (Case A)** — hand the next task to Claude Code in the *same*
  message as the archive. It archives from the existing file first, then
  overwrites. One message, no gap. Best for small tasks.
- **Two-part swap (Case A-close → Case B)** — first archive-and-blank the file
  (Case A-close), then drop the next task's `current-feature.md` into the repo
  yourself and start it with Case B. Best for large specs, where pasting a long
  file into the chat box invites truncation/formatting errors — Claude Code just
  reads the file already sitting in `context/`.

What's forbidden is pre-saving the new file *over* an un-archived completed one.
Both flows above avoid that: Case A archives before overwriting; the two-part
flow blanks the file only *after* archiving, so there's nothing left to lose by
the time you drop the new task in.

---

## Case A — atomic swap (completed task still in the file, load the next one now)
(Archive the old, load the new, kick off audit-first — one message.)

```
The task currently in context/current-feature.md ([OLD TASK NAME]) is complete
and verified — I confirm it's done. Archive it per our workflow (final Goals +
full History to context/CHANGELOG.md, newest at top, matching existing format),
then reset current-feature.md to the content below. After archiving, paste back
the exact CHANGELOG entry you added so I can eyeball it.

Once that's done, begin the audit-first step from the new task: read the files
it names, show me the exact current state of what you'll change, confirm any
shared plumbing or conventions the spec calls out, and propose your plan — mapped to the spec's
numbered edit sites, and stating explicitly which of any flagged decision
options you're taking and why. Do NOT write code until I confirm.

--- new current-feature.md ---
[PASTE THE FULL NEW current-feature.md HERE]
```

Order matters: it archives *from* the existing file first (while the old text is
still there), then overwrites. Filling in [OLD TASK NAME] forces you to look at
what you're actually archiving before you assert it's done.

---

## Case A-close — Part 1 of the two-part swap (archive + blank only, no new task yet)
(Close out the finished task and leave the file blank. You'll hand over the next
task separately, via Case B.)

```
The task in context/current-feature.md ([OLD TASK NAME]) is complete and
verified — I confirm it's done. Archive it per our workflow (final Goals + full
History to context/CHANGELOG.md, newest at top, matching existing format), then
reset current-feature.md to the blank template. Paste back the exact CHANGELOG
entry you added so I can eyeball it. Do not start a new task — I'll hand you the
next one separately.
```

After this returns, save the next task's `current-feature.md` into `context/`
yourself, then run Case B.

---

## Case B — Part 2 of the two-part swap, or any fresh start
(current-feature.md already blank or already holds the next task. No archive —
just review the file in the repo and begin.)

```
I've placed the next task in context/current-feature.md. Read it and begin the
audit-first step: read the files it names, show me the exact current state of
what you'll change, confirm any shared plumbing or conventions the spec calls out, and propose
your plan — mapped to the spec's numbered edit sites, and stating explicitly
which of any flagged decision options you're taking and why. Do NOT write code
until I confirm.
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
1. Claude Code archives (Case A / A-close) and — for Case A and Case B — returns
   an **audit + plan**, including any decision points the task flagged, mapped to
   the spec's numbered edit sites.
2. You **confirm or tweak** the plan.
3. It writes the change (complete drop-in replacement when things are complex),
   **tests, commits**, and adds a dated line to the new task's History.
4. When fully verified, you say **"done — archive it"** (Case A-close), or hand
   over the next task in the same breath (Case A). That confirmation is the only
   CHANGELOG "work" you do; the CLAUDE.md rule makes the copy-paste its job.

## Guardrails to hold the line on
- **Archive before you blank or overwrite.** Whether atomic (Case A) or two-part
  (Case A-close → Case B), the old Goals + History reach CHANGELOG *first*. Never
  pre-save a new current-feature.md over an un-archived completed one.
- **Verify before you assert "done."** The completion claim lives in the opener
  text — so before pasting, make sure the task's Verification checklist has
  actually been run. Don't archive a task whose History still says a check is
  "not yet run."
- **Echo the archive back.** The opener asks Claude Code to paste the CHANGELOG
  entry it wrote — eyeball it. A dropped History or wrong summary is a one-line
  `git revert` if you catch it now, a mess three tasks later if you don't.
- **One concern per commit.** If it proposes folding in an out-of-scope file or a
  flagged side-item, split it — CLAUDE.md backs you up.
- **Scope the repo.** If a task is backend-only (or frontend-only), say so in the
  opener so Claude Code doesn't hunt for a phantom edit in the other repo.
- **Deploy commands come to you, not executed by Claude Code.**
- **Never archive unprompted** — the archive only fires after your explicit
  confirmation. If it tries to archive before you've confirmed, stop it.
- **Both repos** carry the same workflow rules — behavior should match across
  backend and frontend sessions.
