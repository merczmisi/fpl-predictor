# Dashboard

Streamlit MVP for exploring expected points computed by the `fpl_draft` package.

Run locally:

```bash
pip install streamlit
streamlit run dashboard/app.py
```

The app uses the same `fpl_draft` functions and authenticates via `FPLSession` (Playwright-backed browser auth), which injects the `X-Api-Authorization` header required by the Draft API.
