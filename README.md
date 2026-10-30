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

The project lives in the `capcraft/` folder of this repo. Everything below is inside it.

    capcraft/       tested Python library (numpy only): tvm, risk_return, risk_metrics, portfolio,
                    monte_carlo, dcf, sensitivity, data, sample_data
    capcraft_api/   FastAPI layer (schemas, service, providers, main); limits, readable 422 errors, NaN-free JSON
    web/            React + TypeScript (Vite); API types generated from the API's OpenAPI file
    tests/          library and API tests (300+)
    examples/       worked examples, run as scripts
    scripts/        check_live.py (try your keys), make_snapshot.py (optional saved copies of real data)

## Run it

    git clone https://github.com/by-tayo/capcraft
    cd capcraft/capcraft

    pip install -e ".[dev]"
    pytest                                   # library and API tests
    uvicorn capcraft_api.main:app --port 8000

    cd web
    npm install --legacy-peer-deps
    npm run dev                              # http://localhost:5173, proxies /api to port 8000

When the API changes, regenerate the types: export `app.openapi()` to `web/openapi.json`, then
`npx openapi-typescript openapi.json -o src/api/schema.d.ts`.

## Live data (optional)

Set any of these environment variables (see `capcraft/.env.example`). Each feature switches on only when its setting
exists, and CapCraft works fully without any of them. Keys stay on the server and are never sent to the browser.
The app reads real environment variables; it does not load a `.env` file by itself.

| Setting | Turns on | Source |
|---|---|---|
| `CAPCRAFT_SEC_USER_AGENT` | "Load a real company by ticker" on the Valuation tab | SEC EDGAR company facts (no key; the SEC asks for a contact string such as "Your Name you@example.com") |
| `ALPHAVANTAGE_API_KEY` | the latest share price for that company | Alpha Vantage (free tier is small; answers are cached 15 minutes) |
| `FRED_API_KEY` | `GET /api/rates`, the 10-year Treasury yield | FRED |

Loaded numbers are history, not forecasts: growth is the company's own past growth, margins are 3-year averages,
and every number lists how it was derived. Banks and insurers do not fit this model and are rejected with a message.
Everything loaded can be edited.

**Share price on the live site.** The free price service allows only 25 requests a day per key, and on the free host
it often answers "limit reached" even for a new key, most likely because the host's server address is shared with other
apps. When that happens the app says so and you type the price by hand; every other number still loads from the
company's SEC filings.

To check that your keys work, run `python scripts/check_live.py MSFT` once from the `capcraft/` folder and compare the
printed numbers with the company's latest 10-K.

## Deploy

The live site runs on [Render](https://render.com) (free plan). Render builds the `capcraft/Dockerfile`, which
compiles the React app and serves it together with the API from one container. It redeploys automatically on every
push to `main`.

Render settings: Root Directory `capcraft`, runtime Docker, health check path `/api/health`
(`capcraft/render.yaml` lists them). The API keys are set under Environment in the Render dashboard, never in this repo.

To run the same container on your own machine, from the `capcraft/` folder:

    docker build -t capcraft .
    docker run -p 8000:8000 capcraft          # http://localhost:8000

CI (`.github/workflows/ci.yml`) runs the Python tests, the web lint and the web build on every push.

## Assumptions and limits

Each tab has a "How this works, and what it leaves out" panel fed by `GET /api/meta`.
In short:

- Plan: monthly returns are lognormal and independent. Mean matches the straight-line math, so the median is lower (volatility drag). No taxes, fees or inflation. Results show their random draw number and are reproducible.
- Portfolio Risk: weights are held constant (rebalanced). Risk assumes independent periods. The frontier is sampled at random, so min-risk and best-Sharpe are approximations and describe the past only.
- Valuation: terminal value is often most of the value. Sensitivity changes one or two inputs at a time and misses interactions. A reverse DCF is a question, not a verdict.

## How it is tested

Hand-worked numbers and exact identities, statistical checks within standard errors, input-validation cases,
API results compared with direct library calls, and mutation checks (plant a bug, confirm a test fails).
The Python side has 300+ tests. The React side is checked by lint and a type-checked build, not by unit tests.

## License

MIT. See [LICENSE](LICENSE).
