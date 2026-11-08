# TODO

Dated decisions and deliberately deferred work.

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
