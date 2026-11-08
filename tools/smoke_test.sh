#!/usr/bin/env bash
# Behavioural smoke test: build the image, run it, and prove it is actually
# polluting rather than just starting.
#
# The per-page progress lines need a terminal, so a detached container prints
# almost nothing. The health file is the headless signal instead: the script
# rewrites it on every pollute loop with "<unix time> <bytes used>", so a
# growing byte count plus a fresh timestamp means the loop is alive and
# transferring.
#
#   ./tools/smoke_test.sh                 # build . and run 3 minutes
#   IMAGE=hvalev/isp-pollution:0.5.0 RUN_SECONDS=600 ./tools/smoke_test.sh
set -euo pipefail

IMAGE=${IMAGE:-isp-pollution:smoke}
RUN_SECONDS=${RUN_SECONDS:-180}
MEASURE_SECONDS=${MEASURE_SECONDS:-90}
GBPM=${GBPM:-500}
HEALTH_PATH=${HEALTH_FILE:-/tmp/isp-data-pollution.health}
NAME="isp-pollution-smoke-$$"
log=$(mktemp)

cleanup() {
    docker rm -f "${NAME}" >/dev/null 2>&1 || true
    rm -f "${log}"
}
trap cleanup EXIT

fail() {
    echo "FAIL: $*" >&2
    docker logs "${NAME}" >&2 2>&1 || true
    exit 1
}

health() { docker exec "${NAME}" cat "${HEALTH_PATH}" 2>/dev/null || true; }

if [ "${SKIP_BUILD:-0}" != 1 ]; then
    echo "building ${IMAGE}…"
    docker build -q -t "${IMAGE}" . >/dev/null
fi

# Configuration the script cannot work with has to be refused, not half-run.
if docker run --rm -e GBPM=0 "${IMAGE}" >"${log}" 2>&1; then
    fail "GBPM=0 was accepted"
fi
if docker run --rm -e BLACKLIST=banana "${IMAGE}" >"${log}" 2>&1; then
    fail "BLACKLIST=banana was accepted"
fi
echo "guards: bad GBPM and bad BLACKLIST refused"

docker run -d --name "${NAME}" -e "GBPM=${GBPM}" "${IMAGE}" >/dev/null
echo "running for ${RUN_SECONDS}s to let it seed links…"  # keep it long: see MEASURE_SECONDS
sleep "${RUN_SECONDS}"

docker inspect -f '{{.State.Running}}' "${NAME}" | grep -q true || fail "container is not running"
docker logs "${NAME}" 2>&1 | grep -q 'ISP Data Pollution' || fail "startup banner missing"
if docker logs "${NAME}" 2>&1 | grep -qi 'Traceback'; then
    fail "python traceback in the log"
fi

read -r _ bytes_before <<<"$(health)"
[ -n "${bytes_before}" ] || fail "no health file at ${HEALTH_PATH} after ${RUN_SECONDS}s"
sleep "${MEASURE_SECONDS}"
read -r stamp_after bytes_after <<<"$(health)"
[ -n "${bytes_after}" ] || fail "health file disappeared"

[ "${bytes_after}" -gt "${bytes_before}" ] ||
    fail "no data polluted in ${MEASURE_SECONDS}s (${bytes_before} -> ${bytes_after} bytes)"

age=$(( $(date +%s) - ${stamp_after%.*} ))
[ "${age}" -lt 900 ] || fail "health file is ${age}s old; the pollute loop is stuck"

python3 - "${bytes_before}" "${bytes_after}" "${MEASURE_SECONDS}" <<'PY'
import sys
before, after, seconds = (float(a) for a in sys.argv[1:4])
mb_per_min = (after - before) / 1024 / 1024 / (seconds / 60)
gb_per_month = mb_per_min * 43200 / 1024
print(f"PASS: polluted {(after - before) / 1024 / 1024:.1f} MB in {seconds:g}s "
      f"({mb_per_min:.2f} MB/min, about {gb_per_month:.0f} GB/month), "
      f"health file total {after / 1024 / 1024:.0f} MB")
PY
