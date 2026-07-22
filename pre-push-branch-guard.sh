#!/bin/bash
# pre-push-branch-guard.sh
#
# Install: copy into a repo as .git/hooks/pre-push and chmod +x
# (or symlink it there so updates here propagate).
#
# Refuses to push directly to protected branches, so a sandboxed Claude
# session can push feature branches but not push straight to main/prod.
# This is a *local* safety net -- the real enforcement should still be a
# GitHub branch protection rule requiring PRs. This just stops it earlier.

PROTECTED_BRANCHES="${CLAUDEVM_PROTECTED_BRANCHES:-main master prod production}"

while read -r local_ref local_sha remote_ref remote_sha; do
  branch="${remote_ref#refs/heads/}"
  for protected in $PROTECTED_BRANCHES; do
    if [ "$branch" = "$protected" ]; then
      echo "Refusing to push directly to protected branch '$branch'." >&2
      echo "Push a feature branch and open a PR instead." >&2
      echo "(Override: git push --no-verify, if you really mean it.)" >&2
      exit 1
    fi
  done
done

exit 0
