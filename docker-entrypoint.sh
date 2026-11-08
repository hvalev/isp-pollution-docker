#!/bin/sh
# Container entrypoint: validate the environment, then hand the knobs to the
# upstream script's own command-line options.
set -eu

PROGRAM="$(basename "$0")"

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

if [ "${BLACKLIST}" = "local" ] && [ ! -r "${BLACKLIST_FILE}" ]; then
    echo "${PROGRAM}: warning: BLACKLIST_FILE ${BLACKLIST_FILE} is unreadable, running without a filter" >&2
fi

# -u keeps the log readable in `docker logs`.
exec python3 -u /isp-data-pollution.py --gb_per_month "${GBPM}" --maxmemory "${MEM}" "$@"
