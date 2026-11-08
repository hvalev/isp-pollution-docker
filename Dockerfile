# syntax=docker/dockerfile:1

# Upstream is pinned by commit: builds are reproducible, and a patch that no
# longer applies fails the build instead of silently doing nothing (the old
# build used `sed -i`, which succeeds even when nothing matched).
#
# BASE_IMAGE stays on alpine:3.11 on purpose. Newer alpine releases fail here:
# pip refuses to install into the system environment (PEP 668), and the shipped
# numpy drops the np.float aliases this script calls. See "Upgrading the base
# image" in README.md.
ARG BASE_IMAGE=alpine:3.11
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

# --- stage 2: runtime ---------------------------------------------------------
FROM ${BASE_IMAGE}

LABEL org.opencontainers.image.title="isp-pollution" \
      org.opencontainers.image.description="Continuously pollute your ISP with random browsing data from safe domains" \
      org.opencontainers.image.licenses="MIT (this packaging), GPL-3.0+ (upstream script)" \
      org.opencontainers.image.source="https://github.com/hvalev/isp-pollution-docker" \
      org.opencontainers.image.upstream="https://github.com/essandess/isp-data-pollution"

RUN apk add --no-cache \
        xvfb \
        tzdata \
        chromium \
        chromium-chromedriver \
        py3-numpy \
        py3-requests \
        py3-psutil \
        py3-openssl \
        py3-pip

COPY requirements.txt /tmp/requirements.txt
RUN python3 -m pip install --no-cache-dir --upgrade pip \
    && pip3 install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

COPY --from=patcher /src/isp_data_pollution.py /isp-data-pollution.py
COPY blocklist/blocklist-domains.txt /etc/isp-data-pollution/blocklist-domains.txt

# GBPM / MEM are passed as the upstream script's own --gb_per_month / --maxmemory
# options, so no source patching is needed for configuration.
ENV GBPM=300 \
    MEM=512 \
    BLACKLIST=local \
    BLACKLIST_FILE=/etc/isp-data-pollution/blocklist-domains.txt \
    HEALTH_FILE=/tmp/isp-data-pollution.health \
    TZ=UTC

# The patched script refreshes HEALTH_FILE on every pollute loop; if it stops
# moving, the loop is stuck (usually chromedriver hanging) and we want to show
# unhealthy rather than look silently idle.
HEALTHCHECK --interval=5m --timeout=15s --start-period=15m --retries=3 \
    CMD ["python3", "-c", "import os,sys,time; p=os.environ.get('HEALTH_FILE','/tmp/isp-data-pollution.health'); sys.exit(0 if os.path.exists(p) and time.time()-os.path.getmtime(p) < 900 else 1)"]

CMD ["sh", "-c", "exec python3 -u /isp-data-pollution.py --gb_per_month \"${GBPM}\" --maxmemory \"${MEM}\""]
