# TODO

Dated decisions and deliberately deferred work.

## 2026-11-08 — arm/v7 is dropped, as a decision

Closed, not deferred. Alpine has had no `chromium` for armv7 since 3.12, so the
3.24 base cannot build that platform, and a Debian variant would have to run
non-root (Debian Chromium refuses to run as root) and be verified on real armv7
hardware for a browser whose last 32-bit ARM build is from 2020. The image
ships `linux/amd64` and `linux/arm64`; a Raspberry Pi in 64-bit mode is covered,
and 32-bit-only hosts are not coming back. Do not reopen this from the old `arm`
manifest list on Docker Hub — that belongs to the 2021 images.

## 2026-11-08 — pinned upstream is unmaintained

`UPSTREAM_COMMIT` points at the last upstream commit (2018). Upstream has open
issues for the dead Shalla list and no release since, so expect fixes to land
here first. Closes if upstream revives or the script is vendored outright —
vendoring needs a decision on the GPL/MIT conflict named in `NOTICE`.

## 2026-11-08 — GitHub Actions stay on mutable version tags

Actions are referenced as `@vN` rather than commit SHAs so Dependabot keeps them
current with a single-line PR. Pinning to SHAs is the harder supply-chain stance
and would need a separate automation. Closes if SHA pinning is adopted.
