# syntax=docker/dockerfile:1

# The polluter script is vendored in this repository (see NOTICE): nothing is
# cloned at build time, so a build cannot be surprised by an upstream change and
# no patch series has to be re-applied on every rebuild.
#
# The base image and the dependency lock are a matched set: alpine 3.24 ships
# CPython 3.14 and Chromium/chromedriver 156, numpy 2.5 needs CPython >= 3.12,
# and selenium 4 is what talks to Chromium 156. To move the base, refresh
# pyproject.toml/uv.lock together (see "Upgrading" in README.md).
ARG BASE_IMAGE=alpine:3.24
ARG UV_VERSION=0.13.7

# --- stage 0: uv itself -------------------------------------------------------
# A stage, because COPY --from cannot expand a variable on its own.
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uvbin

# --- stage 1: python dependencies, installed from the lock file ---------------
# A venv because system Python on modern Alpine is marked externally managed
# (PEP 668): pip refuses to install into it. Every dependency has a musllinux
# wheel, so no compiler toolchain is needed.
ARG BASE_IMAGE
FROM ${BASE_IMAGE} AS wheels
COPY --from=uvbin /uv /usr/local/bin/uv

# uv builds the venv against an existing interpreter rather than downloading
# one, so the image Python is the same 3.14 the runtime stage will ship.
RUN apk add --no-cache python3

ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /lock
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
        uv sync --frozen --no-dev

# --- stage 2: runtime ---------------------------------------------------------
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

LABEL org.opencontainers.image.title="isp-pollution" \
      org.opencontainers.image.description="Continuously pollute your ISP with random browsing data from safe domains" \
      org.opencontainers.image.licenses="GPL-3.0-or-later" \
      org.opencontainers.image.source="https://github.com/hvalev/isp-pollution-docker" \
      org.opencontainers.image.upstream="https://github.com/essandess/isp-data-pollution"

RUN apk add --no-cache \
        xvfb \
        tzdata \
        python3 \
        chromium \
        chromium-chromedriver

COPY --from=wheels /opt/venv /opt/venv
COPY isp_data_pollution.py /isp-data-pollution.py
# The vendored script is GPL-3.0-or-later; ship the license text and the
# attribution notice with the code they cover.
COPY LICENSE /usr/share/licenses/isp-data-pollution/LICENSE
COPY NOTICE /usr/share/licenses/isp-data-pollution/NOTICE
COPY LICENSES/ /usr/share/licenses/isp-data-pollution/LICENSES/
COPY blocklist/blocklist-domains.txt /etc/isp-data-pollution/blocklist-domains.txt
# Seed words for the search queries. Baked in because the dictionary URL the
# script used to fetch is no longer reliable (404 to a plain client, bot
# challenge to a browser user agent) and whatever it returned became the word
# list. See the header of seedwords/seed-words.txt.
COPY seedwords/seed-words.txt /etc/isp-data-pollution/seed-words.txt
COPY docker-entrypoint.sh /usr/local/bin/isp-pollution
RUN chmod +x /usr/local/bin/isp-pollution

# Fail the build rather than ship an image that cannot start.
RUN /opt/venv/bin/python3 -c "import numpy, psutil, requests, selenium, fake_useragent, user_agents; import selenium.webdriver.common.by, selenium.webdriver.chrome.service" \
    && /opt/venv/bin/python3 -c "import ast; ast.parse(open('/isp-data-pollution.py').read())" \
    && /opt/venv/bin/python3 /isp-data-pollution.py --help >/dev/null

# GBPM / MEM / CHROMEDRIVER_PATH are handed to the script's own command-line
# options, so configuration needs no source patching.
ENV GBPM=300 \
    MEM=2048 \
    BLACKLIST=local \
    BLACKLIST_FILE=/etc/isp-data-pollution/blocklist-domains.txt \
    SEED_WORDS_FILE=/etc/isp-data-pollution/seed-words.txt \
    SEED_SEARCH_BUDGET=20 \
    SEED_SEARCH_COOLDOWN=300 \
    HEALTH_FILE=/tmp/isp-data-pollution.health \
    CHROMEDRIVER_PATH=/usr/bin/chromedriver \
    TZ=UTC
ENV PATH=/opt/venv/bin:$PATH

# The script refreshes HEALTH_FILE on every pollute loop; if it stops moving the
# loop is stuck (usually chromedriver hanging) and we want to show unhealthy
# instead of looking silently idle.
HEALTHCHECK --interval=5m --timeout=15s --start-period=15m --retries=3 \
    CMD ["/opt/venv/bin/python3", "-c", "import os,sys,time; p=os.environ.get('HEALTH_FILE','/tmp/isp-data-pollution.health'); sys.exit(0 if os.path.exists(p) and time.time()-os.path.getmtime(p) < 900 else 1)"]

ENTRYPOINT ["/usr/local/bin/isp-pollution"]
