# claudevm

Per-project, isolated Lima VMs for running Claude Code sessions with a
default-deny network firewall. See `README.md` for what the tool does and
how to use it.

## Planning workflow: tasks/

Non-trivial changes get a plan doc before implementation, not just a chat
message. This applies regardless of which session is doing the work --
multiple sessions have independently created task docs in this repo, so
don't assume conversation history alone gives you the full picture.

- **`tasks/active/cv-NNN-<slug>.md`**: an in-progress or not-yet-started
  plan.
- **`tasks/completed/cv-NNN-<slug>.md`**: the same file, moved here (via
  `git mv`) once fully implemented and verified, with its `## Status`
  section updated to reflect that before the move.
- `cv-NNN` is a single sequential ID shared across every task in this repo
  -- not per-branch, not per-session.
- **Before creating a new task doc, check both `tasks/active/` and
  `tasks/completed/`** for the highest existing `cv-NNN` and use the next
  number. Don't guess from what's visible in the current conversation --
  other sessions may have created docs this one has no memory of.

### Expected doc structure

Not every section is mandatory for every task, but this is the default
shape (see any file under `tasks/` for real examples):

- `## Status` -- one line: not started / in progress / done, plus enough
  context for a cold read to resume it.
- `## Background` -- what exists today and why this task is needed. Add a
  `### Scope change` or `### Implementation approach` subsection if the
  task changes something's existing behavior, or reconsiders its own
  approach mid-design.
- `## Goal` -- the concrete deliverable(s), numbered.
- `## Research findings` -- facts verified against the actual codebase,
  live system state, or external docs -- not assumed. Mark anything not
  yet verified explicitly rather than presenting it as settled.
- `## Decisions from the design interview` -- present when the task was
  refined via the `grill-me` skill; one numbered item per resolved
  question, including *why*, not just the answer.
- `## Proposed plan` -- numbered, concrete steps.
- `## Open questions / risks` -- mark each resolved once it's settled
  (`**Resolved**: ...`) rather than deleting it, so the doc keeps a record
  of what was decided and why.
- `## Non-goals` -- explicit exclusions, including references to other
  `cv-NNN` tasks this one deliberately doesn't overlap with or depend on.

### Cross-task dependencies

Tasks can depend on each other -- e.g. work planned in one task's scope can
get moved into another task's scope mid-design (this has already happened
once: `cv-003` originally planned a `claudevm ls` change that moved into
`cv-004` instead). When that happens, update BOTH docs to state the
dependency explicitly in both directions, not just the one being edited.
