---
name: ship
description: "Human sign-off for a reviewed task: doc-hygiene sweep, mark done, verified merge into main. Run only when the user invokes /ship cv-XXX."
disable-model-invocation: true
---

# Ship a task

Invoking `/ship cv-XXX` is the user's sign-off. Pipeline rules:
`.claude/docs/pipeline.md`.

1. **Preflight.** Require a task id, a clean tree, and no merge or rebase
   in progress. If `cv-XXX` is already merged into `main`, delete it with
   `git branch -d` and stop. If the task is already in `tasks/completed/`
   on the branch, skip to step 4 (a retry after a failed merge).
   Otherwise the task file's last `## Review log` round on `cv-XXX` must
   be APPROVED, and a VM-affecting branch must carry a `Host checks at
   <sha>` line with nothing but the task file changed since `<sha>`
   (`pipeline.md` § Host checks).
2. **Hygiene.** On `cv-XXX`, run the `doc-hygiene` skill with
   `--diff=main`. If it made edits and its checks passed, commit them
   (`doc-hygiene: pre-merge pass on cv-XXX`). If its checks failed, stop.
3. **Finalize.** Tick every Must Have the review confirmed (a legacy-format
   file differs: `pipeline.md` § Task files). If
   `docs/roadmap.md` references this id, tick its box there, and delete
   the milestone's section when it was the last box (`pipeline.md`
   § Roadmap). Stage the
   edits, then `git mv tasks/active/cv-XXX-<slug>.md tasks/completed/`,
   and commit (`cv-XXX: mark task done`). Staging before the move matters:
   `git mv` moves the index's blob, not the file on disk.
4. **Merge.** `git checkout main`, then `git merge --no-commit --no-ff
   cv-XXX`. On conflicts, stop and leave them for the user. Run
   `tools/check --no-vm` on the merged tree (`pipeline.md` § Checks).
   - Green: commit `Merge cv-XXX: <title>`, then `git branch -d cv-XXX`
     (never `-D`).
   - Red: `git merge --abort`, report the failing check, and stop. The
     branch keeps its commits; re-running `/ship` resumes at this step.

Report what merged, what `doc-hygiene` changed, and `python3
tools/task_status.py` for the remaining backlog.
