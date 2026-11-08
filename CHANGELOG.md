# Changelog

Dated entries, newest first. Each entry is a finished unit of work.

## 0.4.0 — 2026-11-08

- The container runs again. The Shalla blocklist this image downloaded is gone
  (Shalla Secure Services shut down; the URL returns 404) and one dead EasyList
  URL took the whole download loop with it, so every start exited with
  `Empty blacklists! Exiting.`
- `BLACKLIST=off|local|remote` selects the link filter: `local` is now the
  default and reads a vendored MIT list of ~78 000 ad, tracker, and malware
  domains baked into the image, so no third-party list is needed at runtime.
  `tools/refresh_blocklist.sh` regenerates it with its provenance header.
- Runtime modernised to alpine 3.24: CPython 3.14, Chromium/chromedriver 156,
  selenium 4.52, numpy 2.5, fake-useragent 2.2. Dependencies install into a
  virtualenv because modern Alpine Python is marked externally managed.
  Domain entropy per page improved from ~1.1 to ~2.0 bits against the previous
  base, because the old Chromium no longer renders current sites.
- Removed `linux/arm/v7`. Alpine stopped building Chromium for armv7 after
  3.11 (Chromium 80), so the 3.24 base has no `chromium` package there and the
  multi-arch build died at `apk add`. The platform was already unusable: no
  Chromium released for 32-bit ARM since 2020 renders current search pages.
- Compatibility fixes upstream never made, applied as a patch series that fails
  the build when a patch stops matching: Selenium 4 element lookup and driver
  service, `browserVersion` capability, numpy 2 scalar conversions,
  `random.sample()` on sets (removed in Python 3.11), explicit
  `importlib.util`, and keeping non-http targets out of the link library.
- `HEALTHCHECK` reports `unhealthy` when the pollute loop stops making progress
  instead of leaving a stuck container looking idle.
- Base image, upstream script, and patches are pinned and verified at build
  time: the upstream script is cloned at a commit and patched with `git apply`
  instead of `sed`, which used to succeed while matching nothing.
- Default `MEM` raised 512 → 2048 MB: the chromedriver memory watchdog was
  tuned for Chromium 80 and restarted the driver constantly on current pages.
- CI fixed: both workflows ran on the retired `ubuntu-20.04` runner, so nothing
  had run in years. They now build on `ubuntu-latest` with layer caching, on
  pull requests as well as pushes, and releases can be rebuilt manually.
- Invalid configuration (`BLACKLIST`, `GBPM`, `MEM`, `CHROMEDRIVER_PATH`) is
  rejected at startup with a message instead of surfacing deep inside the script.
- Added `LICENSE` (MIT), `NOTICE` with upstream and blocklist attribution, and
  the upstream license text inside the image. The Shalla lists are explicitly
  not redistributable and are not shipped.
