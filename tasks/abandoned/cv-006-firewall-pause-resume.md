---
id: cv-006
title: "`claudevm firewall pause`/`resume`/`status`"
---

# cv-006: `claudevm firewall pause`/`resume`/`status`

## Summary

Planned host-side commands to open a VM's egress firewall temporarily,
restore it, and report its state, for debugging network failures.

## Why abandoned

cv-009 removes outbound network restrictions from VMs entirely, which
leaves every VM permanently in what this task called the paused state.
The full plan is in git history before cv-009's planning commit.
