---
id: cv-008
title: "Adopt the claude-pipeline-kit task pipeline"
---

# cv-008: Adopt the claude-pipeline-kit task pipeline

## Summary
Retrofits this existing repo with the plan, implement, review pipeline from
claude-pipeline-kit (`/new-task`, `/work`, `/ship`, a `reviewer` agent, and
`tools/check` as the merge gate). The kit's installer accepts only empty
targets, so the template was ported by hand and adapted to this repo's `cv-`
task ids, its existing task docs, and VM-free development inside a claudevm
guest.

## Must Have
- [x] `.claude/` holds the kit's agents, docs and skills (minus the one-shot
  `init-pipeline`), with every task id written `cv-XXX`.
- [x] `.claude/pipeline-kit-version` holds the kit commit the port started
  from, so `git diff "$(cat .claude/pipeline-kit-version)" HEAD -- template/`
  in the kit shows later changes to port.
- [x] `python3 tools/task_status.py` lists cv-001, cv-003, cv-005 and cv-006
  with no unreadable files, and `--next-id` prints `cv-009`.
- [x] `tools/check --no-vm` exits 0 in a claudevm guest, from any working
  directory; `tools/check` without `--no-vm` and without `limactl` exits
  nonzero naming Lima; an unknown flag exits nonzero.
- [x] `CLAUDE.md` is the kit template with this project's brief and
  conventions filled in.

## Decisions
- Port by hand into this repo; leave the kit unchanged. The adaptations
  (CLAUDE.md merge, legacy task docs, CC0 license, id prefix) need judgment
  a generic installer cannot make.
- Task ids keep the `cv-` prefix. `ID_PREFIX` in `tools/task_status.py` owns
  it; branches are named `cv-XXX`.
- Keep the repo's CC0 `LICENSE`; do not copy the kit's MIT template.
- Legacy active task docs get frontmatter (`id`, `title`, `blocked_by`,
  `legacy_format: true`) plus empty `## Checklist` and `## Review log`;
  their bodies stay. `pipeline.md` § Task files maps their sections onto
  the template's. Completed docs are untouched: `task_status.py` reads
  their ids from file names.
- cv-007 was opened briefly and folded into cv-005 (commit 9dd43b4) without
  a committed file; `tasks/abandoned/cv-007-docker-ipv6.md` keeps the id
  from being reused.
- `tools/check` runs shellcheck, the full test suite (unit and integration)
  and `mypy --strict`. `--smoke` and `--no-vm` both drop the integration
  tier. `--no-vm` exists because claudevm is developed inside a claudevm
  guest, which has no Lima.
- `--no-vm` is allowed only when `limactl` is absent. A `/ship` under
  `--no-vm` of a branch touching what the integration tier exercises waits
  for the user to run the full gate on the Mac (`pipeline.md` § Checks).
- Static checks cover the shell files `tools/check` lists and `tools/*.py`.
  `tests/` (unannotated) and the scripts embedded in `claude-sandbox.yaml`
  stay outside a static checker for now; bringing them under one is a
  separate task.
- The Scripts stay simple obligation exempts the `claudevm` CLI and
  `claude-sandbox.yaml`'s provisioning scripts, which must run on stock
  macOS and in cloud-init.
- This task predates the pipeline, so it did not go through `/work` or a
  reviewer round; the user reviews the `cv-008` branch and merges it.

## Notes
- The kit's `tests/test_task_status.py` is not copied: the Test where the
  risk is obligation keeps `tools/task_status.py` untested.
- mypy's SQLite cache fails on the guest's 9p mount of the repo, hence
  `--no-sqlite-cache` in `tools/check`.
- shellcheck's only existing finding was SC2034 in
  `pre-push-branch-guard.sh` (unused `read` fields), fixed by reading them
  into `_`.

## Checklist
- [x] Copy kit `.claude/` and `tools/task_status.py`; rename ids to `cv-`.
- [x] Frontmatter for legacy active docs; cv-007 tombstone.
- [x] `tools/check`, mypy in `tests/requirements.txt`, shellcheck fix.
- [x] `pipeline.md` § Checks `--no-vm` and § Task files legacy format;
  pointers from `work`, `ship`, `doc-hygiene` and `reviewer`.
- [x] `CLAUDE.md`, README layout and Testing, friction-001.

## Review log
