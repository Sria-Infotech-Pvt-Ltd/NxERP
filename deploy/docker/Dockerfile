# syntax=docker/dockerfile:1
#
# NXERP production-style image: Frappe + the apps in deploy/apps.json, each at its pinned commit, with built assets.
# Build context is the REPOSITORY ROOT (the nxerp app is taken from the context, i.e. exactly the commit being released):
#
#   deploy/docker/build.sh            # tags <version>-<git sha>, writes an SBOM
#
# The base is the digest-pinned frappe/bench image from deploy/versions.env (BENCH_IMAGE). The default below must equal it:
# `python3 -I deploy/check_pins.py` fails when they drift. build.sh always passes the values from versions.env.
#
# STATUS: built and run locally (deploy/docker/compose/develop/, 2026-11-04); never built in CI or pushed (see docs/runbooks/release.md).

ARG BENCH_IMAGE=frappe/bench@sha256:cb24e8a76f93e39d6e9fe0efdf13cbe2bfb60312befa39a01a7b1804088c9f4a

# ---------------------------------------------------------------- stage 1: bench + pinned third-party apps
FROM ${BENCH_IMAGE} AS apps
ARG FRAPPE_REPO=https://github.com/frappe/frappe
ARG FRAPPE_REF=v16.53.0
ARG FRAPPE_COMMIT=e8d41dd0061a32ee781caefe5d0b0d2bb7c15362
ENV FRAPPE_REPO=${FRAPPE_REPO} FRAPPE_REF=${FRAPPE_REF} FRAPPE_COMMIT=${FRAPPE_COMMIT}

COPY --chown=frappe:frappe deploy/apps.json /tmp/build/apps.json
COPY --chown=frappe:frappe deploy/docker/install_apps.sh /tmp/build/install_apps.sh

# Optional BuildKit secret `git_token` for private app repositories (never written to a layer):
#   docker buildx build --secret id=git_token,env=GIT_TOKEN ...
RUN --mount=type=secret,id=git_token,uid=1000,required=false \
    bash /tmp/build/install_apps.sh pinned

# ---------------------------------------------------------------- stage 2: the platform app from this checkout + assets
FROM apps AS build
ARG NXERP_REVISION=unknown
# the apps of this repository (deploy/apps.json entries with a path), one folder each
COPY --chown=frappe:frappe apps/helpdesk /tmp/build/src/helpdesk
COPY --chown=frappe:frappe apps/nxerp_platform /tmp/build/src/nxerp
RUN NXERP_REVISION="${NXERP_REVISION}" bash /tmp/build/install_apps.sh platform \
    && rm -rf /tmp/build /home/frappe/.cache /home/frappe/.npm

# ---------------------------------------------------------------- stage 3: runtime image
FROM ${BENCH_IMAGE} AS runtime
ARG NXERP_VERSION=0.0.0
ARG NXERP_REVISION=unknown
LABEL org.opencontainers.image.title="nxerp" \
      org.opencontainers.image.description="NXERP platform: Frappe + ERPNext + Helpdesk + nxerp at pinned versions" \
      org.opencontainers.image.version="${NXERP_VERSION}" \
      org.opencontainers.image.revision="${NXERP_REVISION}" \
      org.opencontainers.image.source="https://github.com/Sria-Infotech-Pvt-Ltd/NxERP"

COPY --from=build --chown=frappe:frappe /home/frappe/frappe-bench /home/frappe/frappe-bench
COPY deploy/docker/entrypoint.sh /usr/local/bin/nxerp-entrypoint
USER root
RUN chmod 0755 /usr/local/bin/nxerp-entrypoint
USER frappe
# The sites volume hides sites/ of a newer image: keep a copy of its generated files (assets, apps.txt, apps.json),
# which the entrypoint refreshes into the volume when it configures the bench.
RUN cp -a /home/frappe/frappe-bench/sites /home/frappe/image-sites
WORKDIR /home/frappe/frappe-bench
# No secrets are baked in: database host, redis URLs and credentials arrive at run time (see deploy/env/).
ENV NXERP_VERSION=${NXERP_VERSION} \
    NXERP_REVISION=${NXERP_REVISION}
EXPOSE 8000 9000
# gunicorn picks the site from the request, not from default_site: name it, or every probe answers 404
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=5 \
    CMD curl -fsS -H "X-Frappe-Site-Name: $(python3 -I -c 'import json; print(json.load(open("sites/common_site_config.json")).get("default_site", ""))')" \
        http://localhost:8000/api/method/ping || exit 1
ENTRYPOINT ["/usr/local/bin/nxerp-entrypoint"]
# application_with_statics: the plain frappe.app:application serves neither /assets nor /files, and the nginx in front
# cannot serve /assets itself (sites/assets links into apps/, which only this image has)
CMD ["/home/frappe/frappe-bench/env/bin/gunicorn", "--chdir=/home/frappe/frappe-bench/sites", "--bind=0.0.0.0:8000", \
     "--threads=4", "--workers=2", "--worker-class=gthread", "--worker-tmp-dir=/dev/shm", "--timeout=120", \
     "--preload", "frappe.app:application_with_statics()"]
