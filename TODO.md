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

## 2026-11-08 — upstream is vendored, not pinned

Closed. `isp_data_pollution.py` is in this repository as of 0.5.0, so there is no
`UPSTREAM_COMMIT` to chase and no patch series to re-apply. Upstream is unmaintained
(last commit 2018, open issues about the dead Shalla list), so fixes land here.
The license question that blocked vendoring — an MIT `LICENSE` in upstream's
repository against a GPL-3.0-or-later header in the file — was resolved by taking
the more restrictive reading; see `NOTICE`.

## 2026-11-08 — re-vendor if upstream ever revives

Deferred, low priority. If `essandess/isp-data-pollution` ever ships a release
again, diffing it against the vendored file is a manual job: the patch series
that used to make that comparison mechanical is gone, and the file has diverged
(lint, types, scheme-checked fetches). Worth a afternoon only if upstream grows
something this copy lacks.

## 2026-11-08 — GitHub Actions stay on mutable version tags

Actions are referenced as `@vN` rather than commit SHAs so Dependabot keeps them
current with a single-line PR. Pinning to SHAs is the harder supply-chain stance
and would need a separate automation. Closes if SHA pinning is adopted.
