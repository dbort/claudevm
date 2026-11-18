---
next_id: friction-003
---

# Friction log

Moments where developing or testing this repo forced a workaround: a
missing tool, data in the wrong shape, a doc that had to be
reverse-engineered. Log it in the same session, even when the workaround
succeeded. Defects in the project itself go in `bug-log.md` instead.

An entry qualifies only if its fix is something this repo could build or
write. An upstream tool's permanent behavior belongs in a comment at the
call site, a doc under `.claude/docs/`, or a Claude memory.

Format, oldest first:

- `friction-NNN` - **<what was needed>**: what happened; the workaround
  used. Simpler if: <the missing tool/data/doc>.

The id is `next_id` from the front matter; increment it in the same
commit. It only moves forward, even when entries are deleted. An entry
commits with the work on the branch where the issue was found and
reaches `main` in that work's merge, never on a branch of its own. An
issue already present on `main` commits on `main`. When `/ship`'s merge
gate finds an issue the shipping branch causes, the ship fails and the
entry commits on that branch. A commit that fixes the entry, or removes
the code it concerns, deletes it and records the papercut and its fix in
its message.

## Entries

- `friction-001` - **`tools/check` prerequisites inside a claudevm
  guest**: developing this repo in a claudevm VM, `./test.sh` failed
  because the stock Ubuntu image lacks `python3-venv`, and `shellcheck`
  was absent; the user installed both with apt by hand (cv-008). Simpler
  if: an opt-in way to provision extra packages per VM, or a documented
  setup step for VMs that develop claudevm itself.
- `friction-002` - **Editing files on the project mount from a
  subagent**: during cv-009's `/ship`, two of the `hygiene` subagent's
  Edit calls left `README.md` and `claude-sandbox.yaml` at 0 bytes on
  the `/workspace` host mount ("Write verification failed ... is 0 bytes
  on disk"), while a third Edit in the same run wrote correctly. The
  files were committed, so `git checkout --` restored them and the main
  session reapplied the edits with a Python write. During cv-010's
  `/work` the main session's own Edit did the same to `CLAUDE.md`, on a
  9p project mount from a Linux host, so it is not specific to
  subagents or to the macOS host. Cause not found.
  Simpler if: the rendered Lima config's project mount (`cmd_up` in
  `claudevm`) used a mount type that handles the Edit tool's write
  pattern, once the cause is known.
