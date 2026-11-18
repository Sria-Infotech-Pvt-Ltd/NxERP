# Phase 1 baseline: tests before any change

Run on 2026-11-11 on branch `feat/nxdesk-public-site` (no code changed yet), dev site `nxerp.localhost`, inside the bench container:

```
bench --site nxerp.localhost run-tests --app nxerp
```

The runner printed two blocks (the second one is the architecture module, which it runs separately).

| Block | Result |
| --- | --- |
| 1 | `Ran 174 tests in 298.710s`, `FAILED (failures=1, errors=3)` ("Running 200 integration tests" was announced; the two `setUpClass` errors skip the tests of those classes) |
| 2 | `Ran 17 tests in 27.150s`, `OK` |

## The four failures (FACT: from the runner's output)

| Test | Cause shown in the output |
| --- | --- |
| `setUpClass` of `test_access_matrix.TestAccessMatrix` | `Client("Administrator", <env password>)` got `HTTP 401` from `/api/method/login` |
| `setUpClass` of `test_customer_leaks.TestCustomerLeaks` | same `HTTP 401` |
| `test_unified_experience...test_administrator_goes_to_the_setup_wizard_until_setup_is_done_then_the_launcher` | same `HTTP 401` |
| `test_enforcement_unit...test_resolver_error_never_locks_out_administrator` | `enforcement.auth_hook()` raised: `routing.desk_root_redirect` (added by the "retire the bare /desk gateway" commit) calls `access.can_access_app`, which the test replaces with a mock that raises, so the "must not raise" assertion fails before it is reached |

ASSUMPTION (not verified): the `NXERP_ADMIN_PASSWORD` in the container environment no longer matches the dev site's
Administrator password, which explains the three HTTP 401 failures. The fourth failure is a test that was not updated when
`desk_root_redirect` was added. None of the four involves code this phase touches.

The Administrator password appeared in the runner's traceback; it is not copied here and nothing in this repository stores it.

Browser tests (`apps/nxerp_platform/browser-tests`) were not run for the baseline: they need the separate `nxerp-e2e.localhost`
site restored to its pristine snapshot and take about 25 minutes. See the final report for what was run later.
