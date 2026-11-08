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

## 2026-11-08 — search-engine seeding can starve traffic, not just slow it

`pollute()` re-runs the whole seeding pass whenever the link library holds
fewer than 2000 links, and a pass is roughly 15 searches with 20 s timeouts.
Google, Bing, Yahoo and DuckDuckGo all bot-wall headless traffic now, so on an
unlucky draw a pass costs minutes instead of seconds. Measured on `0.4.0`
over 7 minutes at `GBPM=500`: 19 seeding searches, 15 chromedriver hangs, one
page fetched, zero `POLLUTING` lines — the container stayed `healthy` because
the heartbeat grace is 15 minutes and the first tick happened on entry to the
loop. A run that pulls a good seed (for example a real word rather than an
inline script fragment) escapes into steady pollution in about 5 minutes, so
the behaviour is bimodal, not uniformly slow.

Three fixes, in increasing order of reach: give `seed_links()` a wall-clock
budget so the pollute loop always proceeds; reject harvested "words" that are
not word-shaped, since modern pages feed the seeder minified JavaScript and
CSS as search terms; and replace the dead FreeBSD dictionary URL
(`wordsite_url`) with a vendored word list, which is also what makes the
first seeding pass predictable. `patches/` is the place; the vendored list
would ride in next to `blocklist/` with the same provenance header.

## 2026-11-08 — pinned upstream is unmaintained

`UPSTREAM_COMMIT` points at the last upstream commit (2018). Upstream has open
issues for the dead Shalla list and no release since, so expect fixes to land
here first. Closes if upstream revives or the script is vendored outright —
vendoring needs a decision on the GPL/MIT conflict named in `NOTICE`.

## 2026-11-08 — GitHub Actions stay on mutable version tags

Actions are referenced as `@vN` rather than commit SHAs so Dependabot keeps them
current with a single-line PR. Pinning to SHAs is the harder supply-chain stance
and would need a separate automation. Closes if SHA pinning is adopted.
