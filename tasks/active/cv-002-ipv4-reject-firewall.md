# cv-002: Use REJECT instead of DROP for the IPv4 default-deny firewall

## Status

Not started. Written up as a plan doc before implementation; nothing in this
repo has been changed yet for this task.

## Background

`claude-sandbox.yaml`'s default-deny egress firewall (provisioning step 3)
sets `iptables -P OUTPUT DROP` as the IPv4 policy, with explicit ACCEPT rules
layered on top for loopback, established connections, DNS to the two pinned
resolvers, and (added separately, by a different script) traffic to
allowlisted domains' resolved IPs.

The IPv6 side of the same firewall (also step 3) does something different:
after the same `DROP` policy and loopback ACCEPT, it adds an explicit
catch-all `REJECT --reject-with icmp6-adm-prohibited` rule, so any blocked
IPv6 attempt fails immediately with an ICMPv6 error instead of hanging. This
was deliberate — added earlier in this project's history specifically so
IPv6-preferring clients (happy-eyeballs-style) fail fast and fall back to
IPv4 quickly, rather than waiting out a SYN timeout. The `DROP` policy stays
underneath as a backstop in case the `REJECT` rule is ever removed
independently.

### The problem this task addresses

IPv4 has no equivalent — it's still a bare `DROP` policy with no catch-all
`REJECT`. A real incident surfaced this directly: a Go toolchain inside a VM
tried to reach `proxy.golang.org`, and because the domain's IP wasn't yet in
the allowlist ipset (the underlying cause turned out to be a stale ipset that
just needed `claudevm refresh`), the connection attempt hung for the *full 2
minutes* of `go doc`'s internal timeout instead of failing in milliseconds.
`curl` without an explicit `--connect-timeout` would have hung far longer, or
indefinitely.

This makes every "is this domain actually blocked, or something else" question
slow to answer, for both real blocks and transient issues like the one above.
A `REJECT` gives an instant, unambiguous signal.

## Goal

Make blocked IPv4 egress fail fast (`REJECT`), matching the existing IPv6
behavior, without breaking the dynamic, cron-refreshed ipset allowlist
mechanism that's the whole point of the firewall.

## Why this isn't a one-line change

`update-firewall.sh` (installed and scheduled by provisioning step 4, re-run
every 5 minutes via cron) adds its ipset-matching ACCEPT rule like this:

```sh
iptables -C OUTPUT -m set --match-set "$SET_NAME" dst -j ACCEPT 2>/dev/null || \
  iptables -A OUTPUT -m set --match-set "$SET_NAME" dst -j ACCEPT
```

`-C` (check) then `-A` (append) *only if missing* — meaning this rule gets
added exactly once, at whatever position is next-available in the chain at
that moment, and is never touched again on subsequent cron runs (only the
ipset's *contents* get refreshed after that, not the iptables rule structure).

If a catch-all `REJECT` rule were simply added once in step 3 (mirroring the
IPv6 pattern exactly), it would already be in the chain *before*
`update-firewall.sh` ever runs (step 3 runs before step 4). When step 4 then
appends its ACCEPT rule, that rule lands *after* the REJECT rule in the
chain — so every packet matches REJECT first and the allowlist stops working
entirely, silently, for IPv4. This would break the tool far worse than the
problem it's meant to fix.

Fixing this correctly means changing how `update-firewall.sh` manages rule
*order*, not just adding a rule somewhere.

## Proposed plan

1. Move ownership of the catch-all REJECT rule into `update-firewall.sh`
   itself, so it's managed by the same script that owns the ACCEPT rule's
   position, on every run (not just once at boot):
   - Delete any existing catch-all REJECT rule for `OUTPUT` (if present).
   - Ensure the ipset ACCEPT rule is present (existing `-C`/`-A` logic,
     unchanged).
   - Re-append the catch-all REJECT rule at the end.
   This makes the relative order self-correcting on every cron cycle,
   regardless of how many times the script has already run or what state the
   chain was left in — rather than relying on a fixed rule-position number
   that could silently drift wrong if the static rule count ever changes.
2. Don't duplicate a REJECT rule in step 3. Step 4 already invokes
   `update-firewall.sh` once immediately after installing it (before boot is
   considered complete), so there's no meaningful window where a fresh VM has
   the ACCEPT rule but not the REJECT rule.
3. **Decided**: use `icmp-host-prohibited`. Verified empirically against a
   running instance (`partybot`) with a temporary, narrowly-scoped test rule
   (single test IP, added and removed within the same command): both
   `icmp-host-prohibited` and `icmp-admin-prohibited` produce the identical
   client-visible result -- curl reports `Failed to connect ... : No route to
   host` (curl error 7), *not* `Permission denied` as originally guessed.
   Linux apparently maps every ICMP "administratively prohibited" variant
   (host/net/generic) to the same `EHOSTUNREACH` errno. `tcp-reset` was also
   considered and would instead produce a plain `Connection refused` --
   distinguishable from the ICMP result, but reads more like "service down"
   than "blocked by policy." Neither option says "firewall policy blocked
   you" outright, but `icmp-host-prohibited` was chosen for consistency with
   the IPv6 rule's naming (`icmp6-adm-prohibited`), since there's no
   behavioral difference between the *-prohibited variants.
4. Keep `iptables -P OUTPUT DROP` as the policy underneath, same rationale as
   IPv6: if the REJECT rule is ever removed independently (e.g. mid-cron-run,
   between the delete and re-append steps above), traffic fails closed, not
   open.
5. Verify across *multiple* cron cycles, not just the first one — this is
   the part most likely to have a subtle bug: confirm the allowlist keeps
   working correctly after several consecutive 5-minute refreshes, not just
   immediately after `claudevm up`.
6. Once implemented, remind whoever's driving this to add the CLAUDE.md
   section below to the project(s) running inside claudevm sandboxes, so an
   agent working inside the VM knows how to interpret this failure mode
   correctly instead of chasing a phantom routing/DNS problem. This is a
   manual step (there's no mechanism in claudevm today that pushes content
   into a project's own `CLAUDE.md`), so it needs an explicit call-out at the
   end of implementation, not just a mention buried in this doc.

## VM agent instructions (add to the project's CLAUDE.md once implemented)

The section below is meant to be copied into the `CLAUDE.md` of whatever
project runs inside a claudevm sandbox -- not this repo's own docs -- so an
agent working inside the VM recognizes this failure mode instead of treating
it as a real network/DNS problem:

    ## Network access in this sandbox

    This VM's outbound network is default-deny: only domains explicitly
    added to the firewall allowlist are reachable. If a command fails to
    connect to a host with `No route to host` (e.g. curl exit code 7),
    that's very likely this firewall blocking an unlisted domain -- not a
    real routing or DNS problem, even if DNS resolution itself succeeded
    fine.

    If you hit this, don't try to work around it (retrying, switching
    resolvers, etc. won't help). Instead, tell the user which domain(s)
    need to be added, so they can run, on the host (not inside this VM):

        claudevm allow <name>      # add the domain(s) to the allowlist
        claudevm refresh <name>    # apply immediately, instead of waiting up to 5 min

## Open questions / risks to resolve during implementation

- Whether the brief delete-then-re-append window for the REJECT rule (every
  5 minutes) has any observable effect under concurrent traffic — almost
  certainly negligible given how fast iptables rule changes are, but worth
  a sanity check rather than assuming.
- Whether `ip6tables`' existing REJECT-management approach (added once,
  never touched again after boot) should eventually be reconciled with this
  new self-correcting pattern for consistency, or whether it's fine as-is
  since IPv6 has no dynamic/cron-driven rule to stay ordered against.

## Non-goals

- Not touching the IPv6 firewall rules — already REJECT, not affected by
  this task's ordering hazard since there's no dynamic IPv6 allowlist rule
  to stay ordered against.
- Not touching DNS-specific ACCEPT rules or the resolver-pinning logic.
- Not related to cv-001 (host-side enforcement) — this task is entirely
  about the existing guest-side firewall's failure mode, independent of
  where enforcement ultimately lives.
