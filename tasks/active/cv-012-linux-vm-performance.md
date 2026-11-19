---
id: cv-012
title: "Faster /workspace and more memory headroom for VMs"
---

# cv-012: Faster /workspace and more memory headroom for VMs

## Summary
A real project moved from a Mac VM to a Fedora-host VM ran into two limits.
The 9p `/workspace` share is about 60x slower than guest disk for
small-file work (`pixi install` of a 3.8 GB env takes 4 minutes), and the
fixed 4 GiB, swapless default leaves FreeCAD runs close to the OOM killer.
This task benchmarks tuned 9p against virtiofs on Linux hosts and ships the
winner, scales CPU and memory defaults with the host, adds zram swap to
every VM, and gives the few existing VMs a one-off migration path.

## Must Have
- [ ] New instances default to memory = host RAM / 4, clamped to [4, 8] GiB, and CPUs = host threads / 2, clamped to [4, 8], on macOS and Linux. `CLAUDEVM_MEMORY` and `CLAUDEVM_CPUS` still override. Unit tests on the faked host cover a below-floor host, a mid-range host, and an above-cap host (62 GiB / 16 threads gives 8 GiB / 8 CPUs) on each platform.
- [ ] Every new VM has zram swap active after boot: `swapon --show` lists a `/dev/zram*` device. An integration test checks it, so it runs on both host platforms.
- [ ] The `## Decisions` section records the Fedora benchmark: 5,000 one-line file writes and a `find` over a tree of roughly 76k files, both on `/workspace`, for default 9p, tuned 9p, and virtiofs, with the guest-disk figure as the baseline.
- [ ] The shipped Linux-host mount configuration is the one the benchmark rule in `## Decisions` selects, and a new instance on a Linux host comes up with it (an integration test reads the mount type from inside the guest on Linux).
- [ ] On a Linux host, files created in `/workspace` from the guest are owned by the host user on the host, and `ausearch -m avc -ts recent` shows no denials during a boot plus write run (manual QA on Fedora, as in cv-010).
- [ ] macOS hosts see no mount change: the rendered per-instance config on Darwin has the same `mounts:` section as before this task (unit test), and the full `tools/check` passes on macOS.
- [ ] If virtiofs is selected, `install.sh` on Linux lists `virtiofsd` among missing dependencies with its dnf package when it is absent (unit test).
- [ ] An uncommitted migration script, run on a stopped pre-cv-012 VM on each host platform, leaves the VM with the current template's mounts, mount type and provisioning (zram, plus anything else the template now provisions) and the new sizing, while a marker file placed in the guest home before migration survives and the per-instance mounts the current `cmd_up` renders are present, with the project at `/workspace` (manual QA, once per host platform).
- [ ] `README.md` states that CPU and memory defaults scale with the host up to a cap and names where the formula lives in `claudevm`, instead of giving fixed numbers; if virtiofs is selected, its Linux requirements list `virtiofsd`.

## Decisions
- Choose the Linux mount by benchmark, with this rule: pick virtiofs only if it is at least 5x faster than tuned 9p on both benchmark operations and passes the ownership and no-AVC checks. Otherwise pick tuned 9p if it beats default 9p, else leave the default. 5x is the bar for taking on the extra `virtiofsd` host dependency and Lima's experimental virtiofs-on-QEMU support.
- 9p tuning uses coherent cache modes only. `loose` and `fscache` cache metadata with no expiry, so a host-side edit or `git checkout` can stay invisible in the guest for an unbounded time. The user accepts a staleness window of about 1 second for a big win, which virtiofs's default metadata timeout meets. Verify that timeout under Lima at /work.
- The benchmark script is throwaway and never committed; its numbers in `## Decisions` are the record. This session runs in a guest without `limactl`, so the user runs it on the Fedora host.
- Keep macOS mounts unchanged: vz already uses virtiofs there. Apply any mount type or 9p options only on Linux hosts.
- No mechanism for keeping heavy generated trees (`.pixi/`, `node_modules`, `.venv`) on guest disk. The user declined it.
- Memory: a quarter of host RAM, floor 4 GiB, cap 8 GiB. CPUs: half the host's threads, floor 4, cap 8. The floors keep a 16 GB Mac at today's 4 GiB / 4 CPUs; the user's 62 GiB / 16-thread host gets 8 / 8. Disk stays at its current default.
- zram swap in every VM, macOS included. It costs almost nothing while idle and turns an OOM kill into a slowdown under pressure. No disk swapfile: it grows the guest disk image for good and double-caches through the host.
- Existing VMs migrate with a one-off script that is never committed: /work writes it outside the repo and hands the user its path, and the user deletes it after use. This keeps the `claudevm` command's scope unchanged. The script re-renders the instance's Lima config from the current template, keeping the guest disk, so old VMs also pick up every other template change. That is safe because provisioning already reruns on every boot.
- The migration applies the new defaults with no never-shrink logic: every existing VM is smaller than the new caps.

## Notes
- Sizing defaults are `CPUS`/`MEMORY` near the top of `claudevm`, passed only on first `up` (`cmd_up`). Host detection needs new fakes alongside `tests/fakes/uname` (for example `sysctl` on Darwin, and `nproc` plus `/proc/meminfo` or an override on Linux).
- `cmd_up` renders the `mounts:` block by concatenation; Linux-only mount settings belong there or in a host-conditional append, since `claude-sandbox.yaml` is shared by both hosts. Lima's per-mount `9p:` keys (`msize`, `cache`, `securityModel`, `protocolVersion`) and top-level `mountType` are the knobs. The current guest mount shows `cache=0x5` (the kernel's `mmap` mode) and `msize=131072`.
- For the migration, check whether rewriting `$LIMA_HOME/<name>/lima.yaml` on a stopped instance (or `limactl edit`) applies a new `mountType`, sizing and `provision:` on the next start, and whether Lima rejects changing `mountType` on an existing instance.
- If virtiofs is in play on Fedora, check how Lima launches `virtiofsd` (path, user, sandbox mode) and the SELinux label on the shared dir before benchmarking.
- `README.md` states the fixed sizing defaults and the Linux requirement list; `install.sh` holds the Linux missing-dependency list and dnf packages. `tests/test_install.py` covers that list.
- `.claude/docs/friction-log.md` friction-002 (zero-byte files from Edit on the project mount, seen on 9p from Linux) may change with the mount type. Note the result there if it does.
- cv-010 decided to leave `mountType` unset and plan nothing about virtiofs; this task's benchmark decision supersedes that for Linux hosts.
- cv-013 removes the secrets mount and provisioning. If it lands first, the migration's re-render drops them from old VMs; values already in a VM's `/etc/environment` and git config stay behind.
- cv-011 also edits `claude-sandbox.yaml` provisioning; whichever lands second rebases its step around the other's. The migration script picks up cv-011's install if cv-011 has landed by then.

## Checklist

## Review log
