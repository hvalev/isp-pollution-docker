# isp-pollution

Container that continuously generates fake browsing traffic to your ISP from a
headless Chromium, so your real history is harder to profile. It packages
[essandess/isp-data-pollution](https://github.com/essandess/isp-data-pollution)
with a pinned, patched build. Faux traffic is not anonymity: a determined
observer can still separate real from fake requests.

[![ci](https://github.com/hvalev/isp-pollution-docker/actions/workflows/ci.yml/badge.svg)](https://github.com/hvalev/isp-pollution-docker/actions/workflows/ci.yml)
![Docker Pulls](https://img.shields.io/docker/pulls/hvalev/isp-pollution)
![Docker Image Size (latest by date)](https://img.shields.io/docker/image-size/hvalev/isp-pollution)

## Run it

```sh
docker run -d --network host -e GBPM=300 --name isp-pollution hvalev/isp-pollution:latest
```

The traffic is generated from the domains in the upstream script's seed list,
so `--network host` matters only for matching your real connection's shape.
Give the container more memory than `MEM`: the limit applies to the chromedriver
process, and Python plus Xvfb sit on top of it.

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
| `UPSTREAM_REPOSITORY` | `https://github.com/essandess/isp-data-pollution.git` |
| `UPSTREAM_COMMIT` | `99862aba74ee4704c5366ac197191ed6ab5f0f13` |

## Patch series

`patches/*.patch` are applied to the pinned upstream checkout with `git apply`,
which fails the build when a patch no longer matches — the previous build used
`sed -i`, which succeeded silently on nothing. Check the series locally before
touching `UPSTREAM_COMMIT`:

```sh
tmp=$(mktemp -d) && git -C "$tmp" init -q
git clone -q https://github.com/essandess/isp-data-pollution.git "$tmp/src"
git -C "$tmp/src" checkout -q <new-commit>
for p in patches/*.patch; do git -C "$tmp/src" apply --check "$PWD/$p" || echo "FAILS: $p"; done
```

| Patch | Purpose |
|---|---|
| `0001-chromium-flags-for-containers` | `no-sandbox`, `disable-dev-shm-usage` for root, small `/dev/shm` |
| `0002-blacklist-modes` | `BLACKLIST=off\|local\|remote`, live Shalla default, per-source error tolerance |
| `0003-liveness-heartbeat` | `HEALTH_FILE` tick at the top of the pollute loop |
| `0004-selenium-4-api` | `find_elements(By.*)`, driver `Service`, `browserVersion` capability |
| `0005-modern-python-numpy` | `random.sample()` on sets (Python 3.11), numpy 2 scalar conversions, `importlib.util` |
| `0006-chromedriver-modern-browser` | keep only http(s) links, so `data:`/`blob:` targets never reach the driver |

## Move the base image

`BASE_IMAGE`, `requirements.txt`, and the compatibility patches move together:

1. Pick the base and read its `python3` and `chromium` versions — numpy needs
   CPython ≥ 3.12, and selenium must be current enough for that Chromium.
2. Update `requirements.txt` to the newest releases; check each has a
   `musllinux` wheel, otherwise the wheels stage needs a compiler.
3. Build, then run with `-g` and look for `exception` lines: the script swallows
   errors without it.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `Looks like chromedriver has hung`, `chromedriver .quit method is taking too long` | Search engines bot-wall headless traffic and the navigation times out. The driver is restarted and the run continues; it costs throughput, not correctness. |
| `data:,` in the log | The blank tab chromedriver sits on after a blocked navigation, not a link that was fetched. |
| `Failed to read the 'localStorage' property from 'Window': Storage is disabled inside 'data:' URLs` | Same blank tab: clearing storage there is a no-op and the error is caught. |
| `Local blacklist ... is unreadable; running without a filter` | `BLACKLIST_FILE` is missing or unreadable. Filter is off, pollution continues. |
| `Empty blacklists! Exiting.` | `BLACKLIST=remote` and every remote source failed. Use `BLACKLIST=local`. |
| Container `unhealthy` | Restart it: `docker restart isp-pollution`. |
| Everything looks silent but suspicious | Run with `-g`; the upstream script only prints swallowed exceptions in debug mode. |

## Licensing

MIT for the packaging in this repository. The image contains GPL-3.0-or-later
upstream code and an MIT vendored blocklist; see [NOTICE](NOTICE).

## Releases

Tags `v*` build and push the multi-arch image (`linux/amd64`, `linux/arm64`,
`linux/arm/v7`) and update the Docker Hub description. See
[CHANGELOG.md](CHANGELOG.md).
