# isp-pollution

[![ci](https://github.com/hvalev/isp-pollution-docker/actions/workflows/ci.yml/badge.svg)](https://github.com/hvalev/isp-pollution-docker/actions/workflows/ci.yml)
![Docker Pulls](https://img.shields.io/docker/pulls/hvalev/isp-pollution)
![Docker Image Size (latest by date)](https://img.shields.io/docker/image-size/hvalev/isp-pollution)

Container that continuously generates fake browsing traffic to your ISP from a
headless Chromium, so your real history is harder to profile. The polluter is
vendored from [essandess/isp-data-pollution](https://github.com/essandess/isp-data-pollution)
and maintained here, since upstream stopped changing in 2018. Faux traffic is not
anonymity: a determined observer can still separate real from fake requests.

## Run it

```sh
docker run -d --network host -e GBPM=300 --name isp-pollution hvalev/isp-pollution:latest
```

The traffic is generated from the domains in the script's seed list, so
`--network host` matters only for matching your real connection's shape.
Give the container more memory than `MEM`: the limit applies to the chromedriver
process, and the Python interpreter sits on top of it.

```yaml
services:
  isp-pollution:
    image: hvalev/isp-pollution:latest
    container_name: isp-pollution
    network_mode: host
    environment:
      GBPM: "300"
      MEM: "2048"
      TZ: Europe/Amsterdam
    mem_limit: 3g
    restart: always
```

## Configuration

| Variable | Default | Controls |
|---|---|---|
| `GBPM` | `300` | Target traffic in GB/month, clamped to 1–2048. 1024 = 1 TB/month. |
| `MEM` | `2048` | chromedriver memory limit in MB, clamped to 256–4096. The driver is restarted when it exceeds it; `0` restarts it after every link. |
| `BLACKLIST` | `local` | Link filter source: `off`, `local`, or `remote` (see below). |
| `BLACKLIST_FILE` | `/etc/isp-data-pollution/blocklist-domains.txt` | Domain list used by `BLACKLIST=local`, one domain per line, `#` comments. |
| `SEED_WORDS_FILE` | `/etc/isp-data-pollution/seed-words.txt` | Words the seeder turns into search queries, one per line. Falls back to the remote dictionary if unreadable. |
| `SEED_SEARCH_BUDGET` | `20` | Seconds a seeding search may take before further searching is paused. |
| `SEED_SEARCH_COOLDOWN` | `300` | Seconds of no searching after a seeding search overruns its budget. |
| `SHALLA_URL` | Internet Archive copy | Tarball fetched by `BLACKLIST=remote`. |
| `CHROMEDRIVER_PATH` | `/usr/bin/chromedriver` | Driver binary. Empty lets Selenium Manager resolve it. |
| `HEALTH_FILE` | `/tmp/isp-data-pollution.health` | Touched once per pollute loop; the healthcheck reads its mtime. |
| `TZ` | `UTC` | Timezone. The upstream script keeps a diurnal rhythm, so this shapes when traffic is generated. |

Arguments passed to the container are appended after the built-in options, so
`docker run --rm hvalev/isp-pollution -g` enables the upstream debug output.

## Link filter

The filter keeps junk domains (ads, trackers, malware) out of the harvested
links. It is not a blocker for your own traffic.

| `BLACKLIST` | Source | Behaviour when the source fails |
|---|---|---|
| `off` | nothing | no filter, and no startup download |
| `local` | the list baked into the image | warns and runs unfiltered |
| `remote` | Shalla tarball plus two EasyList-format lists | exits, as upstream does |

The Shalla lists this project originally downloaded are dead: Shalla Secure
Services shut down, and `shallalist.de` returns 404. `remote` therefore points at
the Internet Archive copy by default. `local` is the default mode and uses a
vendored MIT list of about 78 000 ad, tracker, and malware domains:

```sh
tools/refresh_blocklist.sh   # refetch and rewrite blocklist/blocklist-domains.txt
```

`BLACKLIST=off` is the smallest-dependency option: the container needs no
third-party list at all and still pollutes.

## Health

`HEALTHCHECK` compares `HEALTH_FILE`'s mtime against a 900 s window, polled
every 5 minutes with a 15 minute start period. A stalled pollute loop — usually
a hung chromedriver that the restart logic cannot clear — turns the container
`unhealthy` instead of leaving it quietly idle.

```sh
docker inspect --format '{{.State.Health.Status}}' isp-pollution
```

## Build

```sh
docker build -t isp-pollution .
```

Build arguments:

| Argument | Default |
|---|---|
| `BASE_IMAGE` | `alpine:3.24` |
| `UV_VERSION` | `0.13.7` |

## Development

[`uv`](https://docs.astral.sh/uv/) manages the environment; `pyproject.toml` and
`uv.lock` are the single source of truth for dependencies, and the image installs
from the same lock.

```sh
uv sync --frozen        # .venv from the lock file
uv run pytest -q        # unit tests (no browser, no network)
uv run ruff check .     # lint
uv run pyright isp_data_pollution.py tests/
uv add --dev <tool>     # dev-only tools; runtime deps go in pyproject.toml
./tools/smoke_test.sh   # build, run, and prove the container generates traffic
```

Adding a runtime dependency means `uv add <pkg>`, a rebuild, and a commit of both
`pyproject.toml` and `uv.lock` — the lock is checked in so builds are repeatable.

## The vendored script

`isp_data_pollution.py` is the upstream polluter, vendored from
[`essandess/isp-data-pollution`](https://github.com/essandess/isp-data-pollution)
at commit `99862ab` (upstream's last commit; the project is unmaintained). Earlier
releases cloned it during the build and applied a `patches/` series on top; the
series is now folded into the file, so the fixes are reviewed as ordinary code and
a rebuild cannot drift away from an upstream branch.

What this repository changed in it:

| Change | Effect |
|---|---|
| Chromium flags | `no-sandbox`, `disable-dev-shm-usage` for root, small `/dev/shm` |
| Blacklist modes | `BLACKLIST=off\|local\|remote`, vendored list by default, per-source error tolerance |
| Liveness heartbeat | `HEALTH_FILE` tick at the top of the pollute loop |
| Selenium 4 API | `find_elements(By.*)`, driver `Service`, `browserVersion` capability |
| Modern Python and numpy | `random.sample()` on sets, numpy 2 scalar conversions, `importlib.util` |
| http(s)-only links | `data:`/`blob:` targets never reach the driver |
| Seed word list | words from the vendored frequency list; a fetched list is rejected unless it is word-shaped |
| Seeding search budget | pause searching after a search overruns `SEED_SEARCH_BUDGET`, so a bot-walled query does not eat the pollute loop |
| Scheme-checked fetches | every `urlopen()` goes through `open_http()`, which refuses anything but http(s) |

## Move the base image

`BASE_IMAGE`, `pyproject.toml`/`uv.lock` and the packaged Chromium move together:

1. Pick the base and read its `python3` and `chromium` versions — numpy needs
   CPython ≥ 3.12, and selenium must be current enough for that Chromium.
2. `uv lock --upgrade` and check each dependency still ships a `musllinux`
   wheel, otherwise the wheels stage needs a compiler.
3. `uv run pytest -q`, then build and run with `-g` and look for `exception`
   lines: the script swallows errors without it.
4. `./tools/smoke_test.sh` before releasing.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `Looks like chromedriver has hung`, `chromedriver .quit method is taking too long` | Search engines bot-wall headless traffic and the navigation times out. The driver is restarted and the run continues; it costs throughput, not correctness. |
| `data:,` in the log | The blank tab chromedriver sits on after a blocked navigation, not a link that was fetched. |
| `Failed to read the 'localStorage' property from 'Window': Storage is disabled inside 'data:' URLs` | Same blank tab: clearing storage there is a no-op and the error is caught. |
| `Local blacklist ... is unreadable; running without a filter` | `BLACKLIST_FILE` is missing or unreadable. Filter is off, pollution continues. |
| `Empty blacklists! Exiting.` | `BLACKLIST=remote` and every remote source failed. Use `BLACKLIST=local`. |
| Container `unhealthy` | Restart it: `docker restart isp-pollution`. |
| Everything looks silent but suspicious | Run with `-g`; the script only prints swallowed exceptions in debug mode. |

## Licensing

GPL-3.0-or-later. The polluter script this repository builds around is GPL from
upstream, so the whole repository follows it; see [NOTICE](NOTICE) for attribution
and for the MIT-licensed vendored data files.

## Releases

Tags `v*` build and push the multi-arch image (`linux/amd64`, `linux/arm64`)
and update the Docker Hub description. See [CHANGELOG.md](CHANGELOG.md).

32-bit ARM (`linux/arm/v7`) is not built: the image needs Chromium and Alpine
has shipped no Chromium for armv7 since 3.11, whose Chromium 80 no longer
renders the current web. A Raspberry Pi 2 on a 32-bit system is the only
common host left behind — the same machine in 64-bit mode is supported.
