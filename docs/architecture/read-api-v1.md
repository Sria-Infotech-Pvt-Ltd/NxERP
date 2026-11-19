# Read API v1

The only way an app reads the shared read layer (ADR-009). This page is completed with the API itself in work package 4D; this
first version records what the service is built on.

## Libraries available in the image (recorded 2026-11-19; no dependency is added)

The projector, the reconciler and the Read API run in the same application image as the apps, with its Python environment. They are
written to use only what that image already carries:

| Library | Version in the image | Used for |
| --- | --- | --- |
| Python | 3.14.8 | everything |
| PyMySQL | 1.1.2 (package metadata) | the shared database driver |
| Werkzeug | 3.1.9 | the Read API's request and response handling (WSGI) |
| gunicorn | 23.0.0 | serving the Read API |
| `hashlib.scrypt` (standard library) | built in | hashing app tokens |
| `urllib.request` (standard library) | built in | the projector's HTTP client for the owners' feeds |
| mysqlclient 2.2.7, requests 2.33.1 | present, not used by the shared service | |
| jsonschema | **not installed** | not used: envelopes and contracts are checked by the standard-library code in `nxerp/shared/registry.py` |

The shared service imports neither `frappe` nor any other app (ADR-005); it shares only the pure modules `nxerp/shared/registry.py`
and `nxerp/shared/payload.py` with the owners' side.
