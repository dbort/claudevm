---
id: cv-007
title: "Disable IPv6 for Docker containers"
---

# cv-007: Disable IPv6 for Docker containers

## Summary

Opened briefly to stop Docker handing containers an IPv6 address that can
never route under the default gvisor-tap-vsock networking backend.

## Why abandoned

The problem turned out to be scoped entirely to the Docker daemon, so the
fix became decision #10 of `cv-005` (commit 9dd43b4). The task file was
never committed; this tombstone keeps the id from being reused.
