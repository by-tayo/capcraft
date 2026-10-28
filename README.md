# CapCraft

**Live site: https://capcraft-is1c.onrender.com**

A full-stack finance toolkit: test a savings plan against thousands of possible futures, check a portfolio's risk,
and see what a stock price assumes. Built with React, TypeScript, FastAPI and Python.

This is a personal portfolio project for learning, not a product. It is not financial advice.
The free host puts the site to sleep when idle, so the first visit can take about a minute to load.

## What it does

| Tab | The question | What it uses |
|---|---|---|
| Plan vs. reality | Will my plan work, and what would make it likely to? | Monte Carlo (geometric Brownian motion), exact solve for the monthly amount needed |
| Portfolio Risk | What is my mix really doing? | Price CSV, risk contributions, Sharpe/Sortino/beta, drawdowns, sampled efficient frontier |
| Valuation | What does this price assume? | DCF, reverse DCF, sensitivity grid, tornado |

The sample portfolio and "Cedar Co" are made up and labelled that way. On the Valuation tab you can also load a real
company by ticker, using numbers derived from its SEC filings (see Live data below).

## Layout

    capcraft/       tested Python library (numpy only): tvm, risk_return, risk_metrics, portfolio,
                    monte_carlo, dcf, sensitivity, data, sample_data
    capcraft_api/   FastAPI layer (schemas, service, main); limits, readable 422 errors, NaN-free JSON
    web/            React + TypeScript (Vite); API types generated from the API's OpenAPI file
    tests/          library and API tests (300+)
    examples/       worked examples, run as scripts

## Run it

    pip install -e ".[dev]"
    pytest                                   # library and API tests
    uvicorn capcraft_api.main:app --port 8000

    cd web
    npm install
    npm run dev                              # http://localhost:5173, proxies /api to port 8000

When the API changes, regenerate the types: export `app.openapi()` to `web/openapi.json`, then
`npx openapi-typescript openapi.json -o src/api/schema.d.ts`.

## Live data (optional)

Set any of these environment variables (see `.env.example`). Each feature switches on only when its setting exists,
and CapCraft works fully without any of them. Keys stay on the server and are never sent to the browser.

| Setting | Turns on | Source |
|---|---|---|
| `CAPCRAFT_SEC_USER_AGENT` | "Load a real company by ticker" on the Valuation tab | SEC EDGAR company facts (no key; the SEC asks for a contact string such as "Your Name you@example.com") |
| `ALPHAVANTAGE_API_KEY` | the latest share price for that company | Alpha Vantage (free tier is small; answers are cached 15 minutes) |
| `FRED_API_KEY` | `GET /api/rates`, the 10-year Treasury yield | FRED |

Loaded numbers are history, not forecasts: growth is the company's own past growth, margins are 3-year averages,
and every number lists how it was derived. Banks and insurers do not fit this model and are rejected with a message.
Everything loaded can be edited. If the share price is unavailable (the free service is rate limited), type it by hand.

To check that your keys work, run `python scripts/check_live.py MSFT` once and compare the printed numbers with the
company's latest 10-K.

## Deploy

One container serves both the API and the built frontend:

    docker build -t capcraft .
    docker run -p 8000:8000 capcraft          # http://localhost:8000

On Render: New > Blueprint, pick this repo (`render.yaml` is included). It runs with no keys; add
`CAPCRAFT_SEC_USER_AGENT`, `ALPHAVANTAGE_API_KEY` and `FRED_API_KEY` in the dashboard only if you want live lookups.
Any host that runs a Dockerfile works (Fly.io, Railway). Set `PORT` if the host requires it.
Set `CAPCRAFT_CORS` only if the frontend is served from a different address.
CI (`.github/workflows/ci.yml`) runs the tests, lint and a build.

## Assumptions and limits

Each tab has a "How this works, and what it leaves out" panel fed by `GET /api/meta`.
In short:

- Plan: monthly returns are lognormal and independent. Mean matches the straight-line math, so the median is lower (volatility drag). No taxes, fees or inflation. Results show their random draw number and are reproducible.
- Portfolio Risk: weights are held constant (rebalanced). Risk assumes independent periods. The frontier is sampled at random, so min-risk and best-Sharpe are approximations and describe the past only.
- Valuation: terminal value is often most of the value. Sensitivity changes one or two inputs at a time and misses interactions. A reverse DCF is a question, not a verdict.

## How it is tested

Hand-worked numbers and exact identities, statistical checks within standard errors, input-validation cases,
API results compared with direct library calls, and mutation checks (plant a bug, confirm a test fails).

## License

MIT. See [LICENSE](LICENSE).
