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

## 2026-11-08 — search-engine seeding is degraded, not fixed

The upstream script seeds its link library by searching Google, Bing, Yahoo and
DuckDuckGo for random words harvested from pages it has already visited. Those
engines now bot-wall headless traffic, so a share of those navigations time out
and chromedriver restarts. Traffic still flows from the bias list and from
harvested links, so this costs throughput rather than correctness. Closes when
the seeding path is replaced (for example friendlier endpoints, or dropping
search seeding in favour of the vendored domain list) — `patches/` is the place.

## 2026-11-08 — pinned upstream is unmaintained

`UPSTREAM_COMMIT` points at the last upstream commit (2018). Upstream has open
issues for the dead Shalla list and no release since, so expect fixes to land
here first. Closes if upstream revives or the script is vendored outright —
vendoring needs a decision on the GPL/MIT conflict named in `NOTICE`.

## 2026-11-08 — GitHub Actions stay on mutable version tags

Actions are referenced as `@vN` rather than commit SHAs so Dependabot keeps them
current with a single-line PR. Pinning to SHAs is the harder supply-chain stance
and would need a separate automation. Closes if SHA pinning is adopted.
