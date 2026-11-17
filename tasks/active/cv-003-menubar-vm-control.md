---
id: cv-003
title: "Menubar app for starting/stopping VMs without a terminal"
blocked_by: [cv-004]
legacy_format: true
---

# cv-003: Menubar app for starting/stopping VMs without a terminal

## Status

Not started. Written up as a plan doc before implementation, then walked
through a design interview (`/grill-me`) that changed several foundational
decisions from the first draft -- see history in this repo's commits for the
earlier SwiftUI-native-app version of this doc, superseded by the SwiftBar
plugin approach below. Nothing in this repo has been changed yet for this
task.

**Depends on `cv-004`**: during `cv-004`'s own design interview, the
`claudevm ls` scope change (claudevm-managed-only filtering, synthetic `new`
status, `--json` mode) originally planned as part of *this* task was moved
into `cv-004` instead, since `cv-004` needs that same interface for its own
test coverage and this avoids either task being written/rewritten around
guessing which lands first. This task now assumes `claudevm ls --json`
already exists and behaves as described below -- see `cv-004` for its actual
implementation.

## Background

Today, starting or stopping a claudevm-managed VM requires a terminal:
`claudevm up <name>` / `claudevm down <name>`. There's no GUI path at all.

### The ask

A macOS menubar item that:
- Shows all known VMs — see the scope change below (claudevm-managed only,
  not literally "every Lima VM").
- Shows each VM's up/down status, including instances that have been
  `claudevm new`'d but never booted (shown distinctly, not hidden).
- Lets the user click a VM in the list to toggle it (start if stopped, stop
  if running) — no terminal needed. Never-booted ("new") instances are
  shown grayed out and are *not* clickable from here.

### Scope change: `claudevm ls` becomes claudevm-managed-only (implemented by `cv-004`)

`claudevm ls` today is just `limactl list` — **every** Lima instance on the
machine, claudevm-managed or not (`cmd_ls()` in `claudevm`). Both `claudevm
ls` and this menubar tool need it changed to show **only claudevm-managed
instances** instead — i.e. only names that exist under `$INSTANCES_DIR`
(`${CLAUDEVM_INSTANCES:-$HOME/.local/var/claudevm/instances}`, same default
`claudevm` itself already uses). **`cv-004` is the task that actually makes
this change** (see its Status note above for why); this doc keeps the
rationale here since it's why the menubar tool needs the interface it needs.

This is a deliberate simplification, not just a menubar-specific filter:
`claudevm up` and `claudevm down` are not symmetric today. `cmd_down()`
calls `limactl stop "$name"` directly with no ownership check, so it works
on *any* Lima instance -- but `cmd_up()` calls `require_instance "$name"`
first, which fails for anything without a claudevm-created config
directory. Restricting `claudevm ls` itself to claudevm-managed instances
means every listed instance can always be toggled the same way, with no
fallback case for non-claudevm instances to worry about.

### Implementation approach: SwiftBar plugin script, not a native app

The original draft of this doc planned a native SwiftUI `MenuBarExtra` app.
That was reconsidered during the design interview: **no new Xcode/Swift
build dependency is acceptable** for this feature. The chosen alternative is
a **SwiftBar plugin script** -- a shell script following SwiftBar's plugin
output conventions, run by the separately-installed SwiftBar host app. No
compiling, no Xcode, just a script.

## Goal

1. Ship a SwiftBar plugin script that lists every claudevm-managed instance
   (via `claudevm ls --json`, provided by `cv-004`) with its status, toggles
   non-`new` instances on click via `claudevm up`/`claudevm down`, and
   renders `new` instances grayed out and inert.
2. A setup helper (separate from the main `install.sh`) that installs
   SwiftBar via Homebrew cask if missing, and **copies** (not symlinks) the
   plugin script into SwiftBar's plugins directory, so the plugin keeps
   working even if this repo's clone is later moved or deleted -- matching
   how the main `install.sh` already copies `claude-sandbox.yaml` and
   `claudevm` itself into stable locations rather than referencing the repo
   in place.

(`claudevm ls` gaining claudevm-managed-only filtering, the synthetic `new`
status, and `--json` output is `cv-004`'s goal, not this task's -- see the
Status note above.)

## Research findings

- **`limactl list --format json`** (short flag: `--json`) gives fully
  structured, parseable output — confirmed by running it directly against
  this machine's real instances. Includes `name`, `status` (`"Running"` /
  `"Stopped"` etc.), `dir`, `sshLocalPort`, and more. Measured latency:
  ~15ms across 3 runs -- fast enough that there's no real reason to cache
  or avoid a live re-fetch on every plugin refresh.
- **How to represent never-booted instances** (this finding now lives in,
  and is implemented by, `cv-004` -- kept here as context for why the
  `--json` contract this task consumes looks the way it does): rather than
  passing claudevm-managed names to `limactl list <name>` and finding out
  what it does for an unbooted name, `cmd_ls` diffs two independently-
  known-good lists: the claudevm-managed names from `$INSTANCES_DIR/*`, and
  the full instance list from `limactl list --format json` (no name
  arguments, so always well-defined). Any claudevm-managed name *not*
  present in `limactl`'s output gets a synthetic `new` status; anything
  present gets `limactl`'s real status passed through.
- **Why toggling should go through `claudevm up`/`down`, not raw
  `limactl`**: `claudevm up` does more than `limactl start` -- notably
  `close_ssh_control` (see this project's git log / `cv-002`'s background
  for the full story), which force-closes Lima's SSH control-master
  connection after provisioning finishes so the next session doesn't
  silently inherit a stale environment. Bypassing `claudevm up` would
  reintroduce that bug for anyone starting their VM from the menubar.
- **SwiftBar plugin click-action mechanism** (verified against SwiftBar's
  own README, not assumed from memory): a menu item can specify `bash=` (a
  script to run), `param0=`/`param1=`/... (arguments to that script),
  `terminal=false` (run in the background instead of opening Terminal.app),
  and `refresh=true` (re-run the whole plugin immediately after the action
  script exits). This is exactly the mechanism needed for click-to-toggle
  plus an immediate status update afterward. Exact delimiter/quoting
  details should be double-checked against a working example plugin during
  implementation -- the docs fetch that confirmed the parameter names
  wasn't fully precise about separator syntax.
- **Disabled/grayed-out rows for `new` instances**: SwiftBar has no
  dedicated "disabled" attribute. A menu item with no `bash=`/`params=`
  action is simply inert (not clickable) by omission -- that alone gives
  the "not clickable" half. `color=<name-or-hex>` (with optional
  `color=light,dark` light/dark-mode variants) gives the "grayed out" visual
  half. Both are directly achievable with verified syntax.
- **Refresh interval is static, not runtime-adjustable.** It's set either
  by encoding it in the plugin's filename (`name.<interval>.sh`, e.g.
  `claudevm-status.60s.sh`) or via a `<swiftbar.schedule>` cron-syntax tag
  in the script's own output -- both fixed at plugin-load time, not
  something the script can dynamically change per-run (confirmed via
  SwiftBar's GitHub issues/README; no built-in variable-backoff mechanism
  exists). Decision: flat 60s baseline refresh, relying on the click
  action's `refresh=true` (above) to catch the specific, known-pending
  status change immediately after a toggle -- covering the actual need
  (see the change quickly after toggling) without requiring a genuine ramp
  the platform doesn't support.
- **In-progress state while a toggle action runs (e.g. a 30+ second VM
  boot)**: SwiftBar has no built-in per-row loading indicator. A DIY
  workaround exists (the action script writes a transient status to a state
  file the plugin's render logic checks, forcing a refresh to show it) but
  adds real complexity -- a new state file, cleanup logic, and a new
  failure mode if the action script dies mid-run without cleaning up.
  **Decided**: skip it. Given how infrequently VMs get toggled, the row
  simply keeps showing its prior status until the action's `refresh=true`
  fires on completion -- no interim state.

## Proposed plan

0. **Prerequisite: `cv-004` lands first**, providing `claudevm ls --json`
   (claudevm-managed-only filtering, synthetic `new` status). Nothing below
   can be meaningfully implemented before that exists.
1. **Write the SwiftBar plugin script** (e.g.
   `menubar/claudevm-status.60s.sh` in this repo): parses `claudevm ls
   --json`, renders one menu line per instance (name plus project dir as a
   subtitle, for disambiguating similarly-named instances across setups),
   `color=`-dims and omits click-action parameters for `new` rows, and wires
   `bash=claudevm param0=up|down param1=<name> terminal=false refresh=true`
   for the rest. No interim "in-progress" state (decided above) -- a row
   just shows its prior status until the action's own `refresh=true` fires.
   Menubar title/glyph: plain text or an emoji (SwiftBar plugins set this
   via their own stdout, no compiled icon asset needed) -- exact glyph is a
   cosmetic detail to pick during implementation, not a design decision.
2. **Write a menubar setup helper** (e.g. `menubar/install.sh`, separate
   from the main `install.sh`): offers to `brew install --cask swiftbar` if
   missing, then **copies** (not symlinks) the plugin script into SwiftBar's
   plugins directory. Note the same tradeoff this creates as the main
   installer already has: future edits to the plugin script in this repo
   require re-running this helper to take effect, they don't propagate
   automatically.
3. **Surface failures inline** on the row itself (e.g. an "Error" state) on
   the plugin's next render -- decided against a native macOS notification,
   which would need extra permission prompts and more implementation effort
   for a lightweight utility.

## Open questions / risks to resolve during implementation

- Exact SwiftBar menu-item attribute delimiter syntax (space vs. pipe
  separated) should be confirmed against a real working plugin example,
  not just the README summary gathered during this planning pass.
- Confirm `limactl start`/`stop` (via `claudevm up`/`down`) exit codes and
  stderr are sufficient to distinguish "genuinely failed" from "already in
  the desired state" -- verify empirically rather than assume.
- Auto-launch SwiftBar (and this plugin) at login -- not requested, not
  assumed; flag as a possible follow-up rather than building it into v1.

## Non-goals

- Not a GUI replacement for the rest of the `claudevm` CLI -- no `new`,
  `secrets`, `allow`, `ssh`, or `code` equivalents. Start/stop and status
  only, per the explicit ask.
- Not managing or creating claudevm instance config -- this only toggles
  instances that already exist.
- Not related to `cv-001` (host-side firewall enforcement) or `cv-002`
  (IPv4 REJECT) -- purely a new, independent control-surface convenience
  layered on top of the existing `claudevm`/`limactl` commands, not a
  change to how any VM's networking or provisioning behaves.
- Not implementing `claudevm ls`'s scope change or `--json` mode -- that's
  `cv-004`'s job (moved there during `cv-004`'s design interview); this task
  only consumes that interface once it exists.

## Checklist

## Review log
