---
id: cv-001
title: "Move firewall enforcement from guest to host"
---

# cv-001: Move firewall enforcement from guest to host

## Summary

Planned to enforce the VMs' default-deny egress firewall from the macOS
host, outside the guest kernel, so a process with root in the guest could
not disable it.

## Why abandoned

cv-009 removes outbound network restrictions from VMs entirely, so there
is no firewall left to enforce. The full plan, including its research on
Lima networking, is in git history before cv-009's planning commit.
