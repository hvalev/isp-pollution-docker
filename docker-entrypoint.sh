#!/bin/sh
# Container entrypoint: validate the environment, then hand the knobs to the
# upstream script's own command-line options.
set -eu

PROGRAM="$(basename "$0")"
EXTRA_ARGS="$*"

die() {
    echo "${PROGRAM}: $1" >&2
    exit 2
}

case "${BLACKLIST}" in
    off | local | remote) ;;
    *) die "BLACKLIST must be off, local or remote (got '${BLACKLIST}')" ;;
esac

[ -n "${GBPM}" ] || die "GBPM is empty"
[ -n "${MEM}" ] || die "MEM is empty"
[ "${GBPM}" -ge 1 ] 2>/dev/null || die "GBPM must be a positive integer (got '${GBPM}')"
[ "${MEM}" -ge 0 ] 2>/dev/null || die "MEM must be a non-negative integer (got '${MEM}')"

# The seeding budget and cooldown are read by the script itself; catching a typo
# here turns it into a startup message instead of a silently ignored setting.
positive_seconds() {
    case "$2" in
        '' | *[!0-9.]*) die "$1 must be a positive number of seconds (got '$2')" ;;
    esac
    awk -v v="$2" 'BEGIN { exit !(v + 0 > 0) }' || die "$1 must be greater than zero (got '$2')"
}

positive_seconds SEED_SEARCH_BUDGET "${SEED_SEARCH_BUDGET}"
positive_seconds SEED_SEARCH_COOLDOWN "${SEED_SEARCH_COOLDOWN}"

if [ "${BLACKLIST}" = "local" ] && [ ! -r "${BLACKLIST_FILE}" ]; then
    echo "${PROGRAM}: warning: BLACKLIST_FILE ${BLACKLIST_FILE} is unreadable, running without a filter" >&2
fi

if [ -n "${CHROMEDRIVER_PATH}" ] && [ ! -x "${CHROMEDRIVER_PATH}" ]; then
    die "CHROMEDRIVER_PATH ${CHROMEDRIVER_PATH} is not an executable"
fi

# The upstream script's own options carry the configuration, and -P pins the
# driver so Selenium Manager does not go looking for one to download.
set -- --gb_per_month "${GBPM}" --maxmemory "${MEM}"
if [ -n "${CHROMEDRIVER_PATH}" ]; then
    set -- "$@" -P "${CHROMEDRIVER_PATH}"
fi

# -u keeps the log readable in `docker logs`. Caller arguments are appended so
# they win, e.g. `docker run image -g` for the upstream debug output.
# shellcheck disable=SC2086
exec python3 -u /isp-data-pollution.py "$@" ${EXTRA_ARGS}
