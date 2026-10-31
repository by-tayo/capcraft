# CapCraft

**Live site: https://capcraft-is1c.onrender.com**

A full-stack finance toolkit: test a savings plan against thousands of possible futures, check a portfolio's risk,
and see what a stock price assumes. Built with React, TypeScript, FastAPI and Python.

This is a personal portfolio project for learning, not a product. It is not financial advice.
The free host puts the site to sleep when idle, so the first visit can take about a minute to load.

## At a glance

- Three tools in one app: Monte Carlo planning, portfolio risk, and DCF valuation.
- A tested Python library (numpy only) behind a FastAPI layer and a React + TypeScript front end.
- 307 Python tests, plus CI on every push.
- Deployed as one Docker container on Render.

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
    tests/          library and API tests (307)
    examples/       worked examples, run as scripts
    scripts/        check_live.py (try your keys), make_snapshot.py (optional saved copies of real data)

## Run it

**Quickest: Docker** (one container serves the website and the API):

    git clone https://github.com/by-tayo/capcraft
    cd capcraft/capcraft
    docker build -t capcraft .
    docker run -p 8000:8000 capcraft          # http://localhost:8000

**For development** (Python 3.9+ and Node 22):

1. Install the Python packages and run the tests.

       git clone https://github.com/by-tayo/capcraft
       cd capcraft/capcraft
       pip install -r requirements.txt
       pytest

2. Start the API (leave this terminal open).

       uvicorn capcraft_api.main:app --port 8000

3. In a second terminal, start the website.

       cd capcraft/capcraft/web
       npm install --legacy-peer-deps
       npm run dev                            # http://localhost:5173, proxies /api to port 8000

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

CI (`.github/workflows/ci.yml`) runs the Python tests, the web lint and the web build on every push.

## Methods and assumptions

Each tab also has a "How this works, and what it leaves out" panel in the app. Here is the written version.

### Plan vs. reality (Monte Carlo)

- **Model:** each month's value moves as geometric Brownian motion: `V(t+dt) = V(t) * exp((mu - sigma^2/2) dt + sigma * sqrt(dt) * Z)`, where `Z` is a standard normal draw and `mu = ln(1 + r)`.
- **Built to match the simple math:** the average outcome equals the straight-line future value, `V0 * (1 + r)^T`. Because of volatility drag (the `sigma^2/2` term), the median outcome is lower. More than half of the simulated paths finish below the straight-line answer, and the gap grows with volatility and horizon.
- **What it assumes:** returns are lognormal, volatility and correlation stay constant (they rise in crises), and each step is independent of the last (no momentum or mean reversion). Real returns have fatter tails than this model.
- **What it leaves out:** taxes, fees and inflation.
- **Reproducible:** every result shows its random draw number, and the same seed gives the same paths.
- **In the library:** `bootstrap_returns()` also resamples real return history instead of assuming a normal distribution, at the cost of assuming the future looks like that history.

### Portfolio Risk

- Weights are held constant (rebalanced), and risk assumes independent periods.
- The efficient frontier is sampled at random, so the minimum-risk and best-Sharpe portfolios are approximations. They describe the past only.
- Annualized return is shown the geometric way (CAGR, what an investor actually earned), not the average-times-periods way, which ignores compounding.

### Valuation (DCF)

- **Method:** free cash flow is discounted at WACC, plus a terminal value by Gordon growth or an exit multiple. Terminal growth must be below the discount rate.
- **Conventions:** end-of-year cash flows by default, with an optional mid-year convention. Tax is a flat rate on EBIT. Depreciation, capex and working capital are fixed percentages of revenue. WACC stays constant, so the capital structure is assumed stable.
- **Not modeled:** loss carryforwards, deferred taxes, and preferred stock, minority interest, leases or pension deficits in the equity bridge (only net debt is subtracted).
- **Read with care:** terminal value is often most of the value. Sensitivity changes one or two inputs at a time and misses interactions. A reverse DCF is a question, not a verdict.

## Sources

- Company financials: SEC EDGAR company facts.
- Share prices: Alpha Vantage.
- Treasury yield: FRED (Federal Reserve Bank of St. Louis).
- Sample portfolio and "Cedar Co": made-up data, labelled as such in the app.

## How it is tested

Hand-worked numbers and exact identities, statistical checks within standard errors, input-validation cases,
API results compared with direct library calls, and mutation checks (plant a bug, confirm a test fails).
For example, the Monte Carlo tests confirm that the simulated mean matches the future-value formula, that percentiles
and the probability of loss match the lognormal and normal formulas, and that with zero volatility the simulation
reproduces the annuity math exactly. The DCF tests check hand-worked valuations and that Gordon growth and the exit
multiple round-trip.
The Python side has 307 tests. The React side is checked by lint and a type-checked build, not by unit tests.

## License

MIT. See [LICENSE](LICENSE).
