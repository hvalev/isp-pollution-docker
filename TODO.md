# TODO

Dated decisions and deliberately deferred work.

## 2026-11-08 — arm/v7 returns through a Debian variant, not Alpine

Alpine has no `chromium` for armv7 since 3.12, so the image ships amd64 and
arm64 only. Debian trixie packages `chromium` and `chromium-driver` for armhf,
so a separate `Dockerfile.debian` built for `linux/arm/v7` and merged into the
same tag with `docker manifest create` would restore 32-bit ARM. Two conditions:
Debian Chromium refuses to run as root, so the variant runs as a non-root user
with the setuid sandbox (or asks the operator for `--cap-add=SYS_ADMIN`), and an
armv7 host is needed to prove the browser starts — the manifest can be built
blind but nothing less is a verification. Closes when such a variant builds and
pollutes on real armv7 hardware.

## 2026-11-08 — seeding still pays for a search on every thin-library iteration

An earlier version of this entry claimed `0.4.0` starved traffic and that the
dictionary URL was dead. Both were measurement errors: the counter I used was a
log string this script version does not print, and the URL does answer — with a
404 to a plain HTTP client and a bot-challenge page to a browser user agent,
both of which the seeder then turned into search terms. Vendoring the word list
(patch 0007, `seedwords/`) is the real fix, worth about 2.5x the data polluted;
see the `0.4.1` entry in `CHANGELOG.md`.

Still open: `pollute()` runs a seeding search on every iteration while the link
library holds fewer than 2000 links, and all four engines bot-wall headless
traffic, so those iterations spend seconds on a search — around half of them end
in the hang handler and a driver restart (25 hangs in 48 searches) — before
polluting the page they already had. A wall-clock budget on `seed_links()`, or a
backoff after a hung search, would recover the rest. It stays unwritten because
the remaining gain looks incremental rather than the several-fold it appeared to
be.

## 2026-11-08 — pinned upstream is unmaintained

`UPSTREAM_COMMIT` points at the last upstream commit (2018). Upstream has open
issues for the dead Shalla list and no release since, so expect fixes to land
here first. Closes if upstream revives or the script is vendored outright —
vendoring needs a decision on the GPL/MIT conflict named in `NOTICE`.

## 2026-11-08 — GitHub Actions stay on mutable version tags

Actions are referenced as `@vN` rather than commit SHAs so Dependabot keeps them
current with a single-line PR. Pinning to SHAs is the harder supply-chain stance
and would need a separate automation. Closes if SHA pinning is adopted.
