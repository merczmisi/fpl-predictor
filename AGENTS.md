# Repository Agent Guide

Purpose
- Provide concise guidance for automated or human agents working on this repository: architecture overview, FPL domain assumptions, development and test commands, coding conventions, and explicit rules agents must follow.

**Architecture (high level)**
- **Auth layer**: Browser-backed authentication is handled by the Playwright-backed adapter; tokens are surfaced to Python via a token provider. Agents should not reimplement OAuth flows — call the existing adapter or mock it in tests.
- **HTTP client**: `FplHttpClient` wraps a `requests`-like session and injects `X-Api-Authorization` headers. It encapsulates retry-on-401 behavior. Use it for real HTTP calls; tests should use small test doubles instead.
- **API wrappers**: Thin functions live in `fpl_draft/api.py`. They accept any `client` object with a `.get(...)` method that returns a `Response`-like object. Prefer these wrappers for endpoint semantics.
- **Features**: Pure data-transform functions (in `fpl_draft/features.py`) operate on pandas DataFrames and are the primary place for feature-engineering logic.
- **Orchestrator**: `fpl_draft/predict.py` composes API wrappers + feature functions and is the recommended entrypoint for prediction logic. `FPLSession.get_expected_points` delegates to it.

**Important FPL domain assumptions & invariants**
- Player IDs returned by `get_player_ids` correspond to `elements.id` in `bootstrap-static`.
- `chance_of_playing_next_round` is treated as a percentage (0–100). Missing values are treated as 100 by the current pipeline.
- The next fixture is taken as the first element of the `fixtures` list returned by `element-summary`. If `fixtures` is empty, `next_match_difficulty` is `None` and fixture multipliers are skipped.
- Base points are computed as: 0.6 * `form` + 0.4 * `points_per_game`. This formula is intentionally explicit in `fpl_draft/features.py`.
- Default FDR multiplier mapping is: {1:1.15, 2:1.08, 3:1.00, 4:0.92, 5:0.85}. Any change to these values must be reflected in tests and documented.
- Network 401 responses are expected; the correct behavior is to trigger the browser auth refresh and retry once. Do not silence repeated 401s.

**Development commands**
- Create & activate venv (macOS/Linux):

  python -m venv .venv
  source .venv/bin/activate

- Install package editable and dev deps:

  pip install -e .
  pip install -r requirements-dev.txt

- Run full tests:

  pytest -q

- Run a single test file:

  pytest -q tests/test_predict.py


**Testing guidance**
- Tests must avoid launching Playwright. Mock or use the `BrowserAuth` delegation/mocking helpers already present (prefer small `DummyClient` classes that implement `.get(url)` and return `json()`/`raise_for_status`).
- Prefer small, deterministic unit tests for `fpl_draft/features.py` and API wrappers. Integration tests may run against mocked HTTP clients that emulate expected JSON shapes.
- When adding tests that involve network behavior, keep them fast by stubbing external calls and asserting request URLs and headers where relevant.

**Coding conventions & style**
- Keep pure logic in `fpl_draft/features.py` and orchestration in `fpl_draft/predict.py`.
- API surface functions in `fpl_draft/api.py` must remain thin and accept a `client` abstraction.
- Keep side-effecting browser/IO code isolated to `fpl_draft/auth.py` and `fpl_draft/http.py`.
- Use pandas idioms consistently: prefer `pd.to_numeric(..., errors='coerce')` for numeric conversions and avoid chained indexing. When selecting players, prefer `reindex`/`loc` patterns that handle missing IDs safely.
- Follow existing formatting and run `black`/`isort` before committing.

**Rules for automated coding agents**
- Preserve existing observable behavior unless the user explicitly asks for breaking changes.
- Do not attempt live OAuth or Playwright flows in CI — use mocks or delegation modes for tests.
- When adding or changing numeric FPL logic (base points, multipliers, chance handling), add or update tests that assert the numerical outputs.
- Avoid network calls in unit tests; if network tests are necessary, gate them behind an opt-in marker (e.g., `--run-network-tests`) and document how to run them.
- Keep changes small and focused. For any multi-file change, update or add tests that cover the behavior before marking the change done.
- When modifying data-shape expectations (JSON keys, indexes), add transformations that are defensive (use `.get(...)`, `errors='coerce'`, `.fillna(...)`) and document the rationale in the test or changelog.

If you modify these rules, edit this file and add a brief changelog entry at the top.
