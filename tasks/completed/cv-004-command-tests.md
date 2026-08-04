# cv-004: Add tests for all existing claudevm commands

## Status

Not started. Written up as a plan doc after a design interview (`/grill-me`);
nothing in this repo has been changed yet for this task.

## Background

`claudevm` has 10 commands (`new`, `allow`, `secrets`, `up`, `down`, `rm`,
`ssh`, `code`, `refresh`, `ls`) and zero test coverage today -- no test
files, no CI, nothing under `.github/`.

### Why this needs careful design, not just "add pytest and mock things"

Evidence from this project's own history (this repo's git log, and this
session's own conversation): essentially every significant bug found and
fixed in `claudevm`/`claude-sandbox.yaml` was a case of *real* Lima/`limactl`
behavior diverging from what the code assumed -- not a bug in claudevm's own
bash logic in isolation. Examples: the `--mount` CLI flag's actual accepted
syntax, Lima's `base:` template composition merging `mounts:` additively
instead of replacing (which silently exposed the host home directory), SSH
`ControlPersist` silently serving a stale environment across boots, git
config `insteadOf`'s multi-value semantics silently clobbering, mount
ordering for the secrets directory, `claudevm new` defaulting to `$PWD`.
**None of these would have been caught by a test that mocks `limactl` and
asserts claudevm constructs the "expected" command string** -- the bugs were
precisely about `limactl`'s real behavior differing from that expectation.

Also confirmed during this session (see `cv-003`'s research): GitHub-hosted
Apple Silicon macOS runners do not support nested virtualization (Apple
lifted the OS-level restriction in macOS 15+, but GitHub's hosted runner
infrastructure doesn't currently expose it) -- so real VM-boot tests cannot
run in standard hosted CI at all today, only locally on a real Mac.

### Scope addition: `claudevm ls`'s scope change moved here from `cv-003`

`cv-003` (the menubar tool) originally planned to change `cmd_ls` to list
only claudevm-managed instances (filtering by `$INSTANCES_DIR`, synthesizing
a `new` status for never-booted ones) and add a `claudevm ls --json` mode,
since its plugin script needs that interface. During `cv-003`'s design
interview, that work was moved here instead: this task needs the same
interface for its own `cmd_ls` test coverage, and implementing it once here
-- with tests -- avoids either task being written around guessing which
lands first, or `cv-003` shipping a real behavior change with no test
coverage of its own. `cv-003` now depends on this task rather than owning
that change itself.

## Goal

1. Change `cmd_ls` to list only claudevm-managed instances (filtered by
   `$INSTANCES_DIR`), with a synthetic `new` status for instances that have
   been `claudevm new`'d but never booted, plus a `claudevm ls --json` mode
   -- the scope addition above, moved here from `cv-003`.
2. A two-tier pytest suite covering all 10 `claudevm` commands (including
   the new `cmd_ls` behavior from #1):
   - A fast, logic-only ("unit") tier that mocks `limactl`/`code` --
     runnable anywhere, including (eventually) CI.
   - A slower, local-only integration tier that boots real VMs -- the tier
     that would actually have caught this session's real bugs.
3. A top-level `test.sh` as the one and only documented way to run any of
   it -- see decision #12 -- so neither a human nor a Claude agent working
   in this repo ever needs to know `pytest` is involved at all.

## Decisions from the design interview

1. **Test strategy**: two tiers (logic + integration), not just one.
2. **Framework**: pytest, not bats-core -- a deliberate choice despite this
   being an otherwise bash-only repo, for pytest's stronger fixture/teardown
   support (real VM lifecycle cleanup matters a lot here).
3. **Logic-tier mocking**: a fake `limactl` (and `code`) script placed on
   `PATH` via a pytest fixture, returning canned/fixture output. No changes
   to claudevm's own production code purely for mocking purposes -- avoids
   the risk of testability-driven refactors introducing new bugs into logic
   that took this whole session to get right. (Exception: #9 below.)
4. **Test organization**: pytest markers (`@pytest.mark.integration`) in a
   single `tests/` tree, not separate `unit/`/`integration/` directories --
   avoids duplicating config/fixtures across two trees.
5. **CI wiring is explicitly OUT OF SCOPE for this task.** This task only
   produces the tests themselves; wiring a GitHub Actions workflow to run
   the logic tier automatically will be a separate, later task.
6. **Integration-tier VM strategy**: shared, session-scoped fixture VM(s)
   reused across most integration tests (`ssh`, `refresh`, `secrets`
   behavior, etc.), with fresh VMs specifically for tests of the creation
   path itself (`claudevm new` + first `up` -- mounts, project-dir
   handling), since that's exactly what those tests verify. Mirrors how
   this session actually worked in practice (a single `test-cv-002`
   instance reused across several checks earlier in this conversation).
7. **A bare `./test.sh` (no args) runs everything**, including the
   VM-booting integration tier -- see decision #12 for `test.sh` itself.
   I'd recommended gating integration behind an explicit opt-in; the user
   chose otherwise. Accepted tradeoff: running `./test.sh` casually costs
   real time and boots real VMs. `./test.sh unit` is the documented way to
   limit a run to the fast, non-integration tier.
8. **Test instance naming**: test-created VM instances use a clearly-
   namespaced prefix (e.g. `claudevm-test-<random>`), as a second line of
   defense beyond `CLAUDEVM_HOME`/`CLAUDEVM_INSTANCES` redirection to a temp
   dir -- makes accidental collision with a real instance name (like
   `partybot`) effectively impossible, and makes stray test instances easy
   to identify/clean up if isolation ever fails for some reason.
9. **`cmd_ssh` gets extended** to accept and forward a trailing command
   (e.g. `claudevm ssh <name> -- echo hello`), falling back to today's
   fully-interactive behavior when none is given. A deliberate, small,
   backward-compatible feature addition (not just a test shim) that lets
   integration tests verify ssh's *real* effect -- actual mounted volumes,
   actual environment -- through the real `cmd_ssh` code path, rather than
   faking the interaction away or testing an equivalent command that
   bypasses `cmd_ssh`'s actual interface.
10. **Integration tests get explicit, generous timeouts** (e.g. via
    `pytest-timeout`) -- a genuine hang fails the test fast rather than
    blocking the suite indefinitely. Thematically consistent with `cv-002`:
    silent hangs are exactly the failure mode this project has spent real
    effort eliminating elsewhere.
11. **Interactive/side-effecting commands, tested without triggering real
    side effects**:
    - `rm`: scripted stdin (`y`/`n`) covering both confirm and abort paths.
    - `secrets`: scripted stdin with fake token values -- the actual secret
      content doesn't matter for testing claudevm's own file-writing/
      permission logic.
    - `code`: a fake `code` binary on `PATH` records its invocation rather
      than launching real VS Code; the "code CLI missing" error path is
      tested separately by ensuring no `code` binary is on `PATH` at all.
    - `ssh`: real non-interactive commands run through the real (now
      trailing-arg-extended) `cmd_ssh` against a real integration-tier VM,
      verifying actual internals (mounted volumes, environment) rather than
      mocking the interaction away.
    - `allow`: a scripted `$EDITOR` stand-in actually given the correct path
      to the real allowlist file, confirmed to have write access to it.
      Exact mechanism (stat + permission check, or a real rewrite of
      unmodified content) left to implementation -- the goal is verifying
      the file is genuinely writable by whatever runs as `$EDITOR`, not
      just that some editor got invoked with the right path.
12. **`test.sh` is the one and only documented way to run tests** -- all
    guidance (README, `tests/README.md`, and any future `CLAUDE.md` for
    this repo) tells users and Claude agents alike to use it, never to
    invoke `pytest` directly:
    - Lives at the repo root: `./test.sh`.
    - Positional mode argument, matching this repo's own established
      positional-subcommand CLI convention (`claudevm up <name>`, not
      flag-based) rather than introducing a new getopts-style pattern:
      `./test.sh [all|integration|unit]`, defaulting to `all` when omitted.
      "unit" is this doc's "logic tier" under a different name -- same
      thing, named to match the CLI surface.
    - Auto-creates and uses its own gitignored virtualenv (e.g.
      `.venv/`) and auto-installs `tests/requirements.txt` into it on first
      run. Modern macOS typically ships an externally-managed system/
      Homebrew Python (PEP 668) where a bare `pip install` can fail
      outright -- since `test.sh` is meant to be the single thing anyone
      needs to know about, it must not push venv setup onto the caller as
      a prerequisite.
    - Checks that `python3` is actually available first, with a clear,
      actionable error if not -- mirrors `install.sh`'s existing pattern of
      checking for `limactl`/Homebrew rather than failing with a cryptic
      "command not found" partway through.
    - Forwards trailing arguments after `--` straight to `pytest` (e.g.
      `./test.sh unit -- -k test_foo` to run one specific test during
      development), so `test.sh` stays the canonical entry point without
      making iterative single-test development painful. Mirrors `cmd_ssh`'s
      own just-added trailing-arg-forwarding pattern (decision #9).

## Proposed plan

1. **Change `cmd_ls` in `claudevm`** (moved here from `cv-003`) to enumerate
   instance names from `$INSTANCES_DIR/*`, diff against `limactl list
   --format json`'s output, and synthesize a `new` status for any
   claudevm-managed name absent from that output. Keep the default (no
   flag) output human-readable, matching today's `claudevm ls` habits --
   this can no longer be a raw passthrough to `limactl list`, since
   synthetic `new` rows have no `limactl`-native formatting to borrow.
2. **Add `claudevm ls --json`** emitting the same diffed/merged data as
   structured JSON -- one object per claudevm-managed instance, at minimum
   `name` and `status` (`new`, `Running`, `Stopped`, etc.). This is the
   interface `cv-003`'s plugin script will consume.
3. **Update `README.md`**'s description of `claudevm ls` (currently "List
   all Lima VMs (claudevm-managed and otherwise)") to reflect the new,
   narrower scope and the `--json` mode.
4. Set up the pytest project skeleton: `tests/` directory,
   `tests/requirements.txt` (pytest, pytest-timeout), and a `pytest.ini` (or
   `pyproject.toml`) registering the `integration` marker.
5. **Write `test.sh`** (decision #12): repo-root entry point, checks for
   `python3`, creates/reuses a local gitignored venv and installs
   `tests/requirements.txt` into it on first run, parses the
   `[all|integration|unit]` positional mode argument (default `all`), maps
   it to the right `pytest -m ...` marker selection, and forwards anything
   after `--` straight to `pytest`. This is what steps 6-11 below get
   invoked through from here on -- no bare `pytest` in any documentation or
   example produced by the rest of this plan.
6. Build the logic-tier ("unit", per `test.sh`'s vocabulary) fixture
   infrastructure: a fake `limactl` script
   (parameterizable canned JSON for `list --format json`, recording
   invocations for `start`/`stop`/`shell`/`delete`), a fake `code` script,
   `PATH` manipulation via `monkeypatch`, and `CLAUDEVM_HOME`/
   `CLAUDEVM_INSTANCES` redirected to a per-test temp dir.
7. Write logic-tier ("unit") tests per command, covering argument
   validation, path/file construction, and branching logic against the
   faked `limactl`/`code` -- at minimum: `cmd_new`'s mandatory project-dir
   argument (and the `$PWD`-default bug this project already fixed once),
   `cmd_ls`'s new filtering/`new`-status/`--json` behavior from steps 1-2
   above, `cmd_up`'s create-vs-resume branching, `require_instance`'s
   guard, `close_ssh_control`'s file-existence check.
8. Extend `cmd_ssh` to forward a trailing command (decision #9), with its
   own unit-tier test (fake limactl, assert the right
   `limactl shell --workdir /workspace <name> -- <command>` invocation for
   both the interactive and non-interactive cases).
9. Build the integration-tier fixture infrastructure: session-scoped
   fixture(s) that create+boot a real, namespaced (`claudevm-test-*`) VM
   once and reuse it across most integration tests, plus a per-test fixture
   for tests that specifically need a fresh instance (the creation path).
   Guaranteed cleanup (`claudevm rm` or equivalent, via fixture teardown)
   even on test failure.
10. Write integration-tier tests per command against real VMs: `new`+`up`
    (mounts are correct: `/workspace`, `/mnt/claudevm-config`,
    `/mnt/claudevm-secrets`; project-dir handling), `down`/`up` resume
    cycle, `rm` (both confirm and abort, verifying the instance survives an
    aborted `rm`), `ssh` (via the extended trailing-command support --
    verify real mounts/environment), `refresh` (allowlist changes take
    effect), `secrets` (token files written with correct permissions,
    wired into `/etc/environment` and git config on next boot), `code`
    (invocation only, via the faked `code` binary -- no real VS Code
    launch even here), `ls` (real claudevm-managed-only filtering and
    `new`-status behavior against real instances, complementing step 7's
    mocked-limactl version).
11. Apply explicit timeouts to all integration tests (decision #10).
12. Document `test.sh` usage (`./test.sh`, `./test.sh unit`,
    `./test.sh integration`, `./test.sh unit -- -k test_foo`) in a
    `tests/README.md` or a section of the main `README.md` -- no raw
    `pytest` invocations in any of it.

## Open questions / risks to resolve during implementation

- **Resolved**: fake-`limactl` fidelity should be minimal, purpose-built for
  exactly the invocations `claudevm` actually makes (`list -q`,
  `list --format json`, `start`, `stop`, `delete`, `shell`) -- not a
  general-purpose Lima simulator.
- **Resolved**: `cmd_secrets`'s interactive flow can be driven with a single
  piped multi-line stdin stream, one line per prompt in sequence -- `-s`
  (hidden input) only suppresses terminal echo, it doesn't change how
  `read` consumes input, so standard bash `read` semantics apply with no
  special driver needed.
- **Resolved**: the integration tier has an explicit target of well under
  ~5 minutes total with a cached VM image, to keep the shared-VM-reuse
  strategy honest during implementation rather than discovering after the
  fact that the suite has become impractical to run.
- **Resolved**: the `cv-003` ordering question no longer applies -- the
  `cmd_ls` scope change moved into this task (see Background), so `cv-003`
  now depends on this task rather than the two tasks racing to define
  `cmd_ls`'s behavior independently.

## Non-goals

- Not wiring CI (decision #5) -- a separate task.
- Not testing `claude-sandbox.yaml`'s own provisioning logic directly (DNS
  pinning, firewall rules, etc.) -- this task is specifically about the
  `claudevm` CLI wrapper's 10 commands, not the guest-side provisioning
  this repo already verifies manually (as `cv-002` did).
- Not building `cv-003`'s actual SwiftBar plugin/menubar tooling, or
  `cv-001`'s host-side firewall enforcement -- those are separate,
  not-yet-implemented features with their own task docs. This task tests
  `cmd_ls` (which `cv-003` will depend on), not `cv-003` itself.
