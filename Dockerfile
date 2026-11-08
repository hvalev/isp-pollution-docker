# syntax=docker/dockerfile:1

# Upstream is pinned by commit: builds are reproducible, and a patch that no
# longer applies fails the build instead of silently doing nothing (the old
# build used `sed -i`, which succeeds even when nothing matched).
#
# The base image, requirements.txt and patches/0004-0005 are a matched set:
# alpine 3.24 ships CPython 3.14 and Chromium/chromedriver 156, numpy 2.5
# needs CPython >= 3.12, and selenium 4 is what talks to Chromium 156. To move
# the base, refresh all three together (see "Upgrading" in README.md).
ARG BASE_IMAGE=alpine:3.24
ARG UPSTREAM_REPOSITORY=https://github.com/essandess/isp-data-pollution.git
ARG UPSTREAM_COMMIT=99862aba74ee4704c5366ac197191ed6ab5f0f13

# --- stage 1: fetch the pinned upstream script and apply our patches ----------
FROM ${BASE_IMAGE} AS patcher
ARG UPSTREAM_REPOSITORY
ARG UPSTREAM_COMMIT

RUN apk add --no-cache git python3
WORKDIR /src
RUN git clone --quiet "${UPSTREAM_REPOSITORY}" . \
    && git checkout --quiet "${UPSTREAM_COMMIT}" \
    && git rev-parse HEAD

COPY patches/ /patches/
RUN for patch in /patches/*.patch; do \
        echo "applying $(basename "${patch}")"; \
        git apply "${patch}"; \
    done \
    && python3 -c "import ast; ast.parse(open('/src/isp_data_pollution.py').read())"

# --- stage 2: python dependencies in a virtualenv -----------------------------
# A venv because system Python on modern Alpine is marked externally managed
# (PEP 668): pip refuses to install into it. Everything here has a musllinux
# wheel, so no compiler toolchain is needed.
FROM ${BASE_IMAGE} AS wheels

RUN apk add --no-cache python3 py3-pip \
    && python3 -m venv /opt/venv
ENV VIRTUAL_ENV=/opt/venv
ENV PATH=/opt/venv/bin:$PATH

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --requirement /tmp/requirements.txt

# --- stage 3: runtime ---------------------------------------------------------
FROM ${BASE_IMAGE}

LABEL org.opencontainers.image.title="isp-pollution" \
      org.opencontainers.image.description="Continuously pollute your ISP with random browsing data from safe domains" \
      org.opencontainers.image.licenses="MIT (this packaging), GPL-3.0+ (upstream script)" \
      org.opencontainers.image.source="https://github.com/hvalev/isp-pollution-docker" \
      org.opencontainers.image.upstream="https://github.com/essandess/isp-data-pollution"

RUN apk add --no-cache \
        xvfb \
        tzdata \
        python3 \
        chromium \
        chromium-chromedriver

COPY --from=wheels /opt/venv /opt/venv
COPY --from=patcher /src/isp_data_pollution.py /isp-data-pollution.py
COPY blocklist/blocklist-domains.txt /etc/isp-data-pollution/blocklist-domains.txt
COPY docker-entrypoint.sh /usr/local/bin/isp-pollution
RUN chmod +x /usr/local/bin/isp-pollution

# Fail the build rather than ship an image that cannot start.
RUN /opt/venv/bin/python3 -c "import numpy, psutil, requests, selenium, fake_useragent, user_agents; import selenium.webdriver.common.by, selenium.webdriver.chrome.service"

# GBPM / MEM / CHROMEDRIVER_PATH are handed to the upstream script's own
# command-line options, so configuration needs no source patching.
ENV GBPM=300 \
    MEM=2048 \
    BLACKLIST=local \
    BLACKLIST_FILE=/etc/isp-data-pollution/blocklist-domains.txt \
    HEALTH_FILE=/tmp/isp-data-pollution.health \
    CHROMEDRIVER_PATH=/usr/bin/chromedriver \
    TZ=UTC
ENV PATH=/opt/venv/bin:$PATH

# The patched script refreshes HEALTH_FILE on every pollute loop; if it stops
# moving the loop is stuck (usually chromedriver hanging) and we want to show
# unhealthy instead of looking silently idle.
HEALTHCHECK --interval=5m --timeout=15s --start-period=15m --retries=3 \
    CMD ["/opt/venv/bin/python3", "-c", "import os,sys,time; p=os.environ.get('HEALTH_FILE','/tmp/isp-data-pollution.health'); sys.exit(0 if os.path.exists(p) and time.time()-os.path.getmtime(p) < 900 else 1)"]

ENTRYPOINT ["/usr/local/bin/isp-pollution"]
