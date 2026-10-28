#!/usr/bin/env bash
# Build the NXERP image and (when a tool is available) write its SBOM. Run from anywhere inside the repository.
#
#   deploy/docker/build.sh                 build, tag  <image>:<version>-<git sha>, load into the local Docker
#   deploy/docker/build.sh --push          also push (needs `docker login`; never done by default)
#   deploy/docker/build.sh --dry-run       print the commands only
#
# Environment (all optional):
#   NXERP_IMAGE     image name, default ghcr.io/sria-infotech-pvt-ltd/nxerp   (placeholder registry: see docs/runbooks/release.md)
#   NXERP_VERSION   default: __version__ from nxerp/__init__.py (the release workflow sets it from the tag)
#   GIT_TOKEN       read token for private app repositories, passed as a BuildKit secret (never baked into a layer)
#   SBOM_DIR        where the SBOM is written, default dist/
#
# Tag format: <version>-<12-char git sha>, plus "-dirty" when the working tree has uncommitted changes.
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$root"
push=0 dry=0
for arg in "$@"; do
	case "$arg" in
		--push) push=1 ;;
		--dry-run) dry=1 ;;
		*) echo "usage: $0 [--push] [--dry-run]" >&2; exit 2 ;;
	esac
done

run() {
	if [ "$dry" = 1 ]; then printf '+'; printf ' %q' "$@"; printf '\n'; else "$@"; fi
}

set -a
# shellcheck disable=SC1091
. deploy/versions.env
set +a
py=python3
"$py" -c "" >/dev/null 2>&1 || py=python   # Windows: python3 may be the Store shortcut
"$py" -I deploy/check_pins.py

version=${NXERP_VERSION:-$("$py" -I -c 'import re; print(re.search(r"__version__ = \"([^\"]+)\"", open("nxerp/__init__.py").read()).group(1))')}
sha=$(git rev-parse --short=12 HEAD)
[ -z "$(git status --porcelain)" ] || sha="$sha-dirty"
image=${NXERP_IMAGE:-ghcr.io/sria-infotech-pvt-ltd/nxerp}
tag="$version-$sha"
sbom_dir=${SBOM_DIR:-dist}

args=(buildx build -f deploy/docker/Dockerfile
	--build-arg "BENCH_IMAGE=$BENCH_IMAGE" --build-arg "FRAPPE_REPO=$FRAPPE_REPO"
	--build-arg "FRAPPE_REF=$FRAPPE_REF" --build-arg "FRAPPE_COMMIT=$FRAPPE_COMMIT"
	--build-arg "NXERP_VERSION=$version" --build-arg "NXERP_REVISION=$sha"
	-t "$image:$tag")
[ -z "${GIT_TOKEN:-}" ] || args+=(--secret "id=git_token,env=GIT_TOKEN")
if [ "$push" = 1 ]; then args+=(--push --provenance=mode=max --sbom=true); else args+=(--load); fi
args+=(.)

echo "image: $image:$tag"
run docker "${args[@]}"

# SBOM: syft first, then `docker sbom` (Docker Desktop's syft plugin). In CI the release workflow uses anchore/sbom-action.
[ "$dry" = 1 ] || mkdir -p "$sbom_dir"
out="$sbom_dir/sbom-$version-$sha.spdx.json"
if [ "$push" = 1 ] && [ "$dry" = 0 ]; then
	echo "SBOM and provenance were attached to the pushed image by buildx (--sbom=true); no local file written."
elif command -v syft >/dev/null 2>&1; then
	run syft "$image:$tag" -o "spdx-json=$out"
elif docker info --format '{{range .ClientInfo.Plugins}}{{.Name}} {{end}}' 2>/dev/null | grep -qw sbom; then
	run docker sbom --format spdx-json --output "$out" "$image:$tag"
else
	echo "NOTE: neither syft nor 'docker sbom' is installed; no SBOM written. The release workflow generates it with anchore/sbom-action." >&2
fi
