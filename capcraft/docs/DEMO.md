# CapCraft: 3-minute demo script

Say the pitch in one breath: "Most calculators give you one number. CapCraft shows how wrong that number can be."
Start the app first (see README) and keep the Plan tab open.

## 1. Plan vs. reality (about 80 seconds)
1. Read the headline aloud: the straight-line plan says one thing, and only about 2 of 10 futures reach the goal.
2. Click **Live one future**. Talk while it plays: "This is one random future with the same assumptions. Watch it fall under the money I put in, then recover."
3. Click **Zoom out to all futures**. "Here are 5,000 of them. The middle 90% is the shaded band. The dashed line is what a normal calculator shows."
4. Point at the table: "To reach the goal in 8 of 10 futures, I would need about $1,200 a month, not $500."
5. Drag the volatility slider. "Same draw number, so only my assumption changed, not the luck."

## 2. Portfolio X-ray (about 50 seconds)
1. Open the tab. The sample portfolio loads (made-up data, labelled as such).
2. "One holding is 35% of my money but 58% of my risk." Point at the table.
3. Show the plot of random mixes. "My mix is the diamond. The best-Sharpe mix looks great, but it is tuned to the past, so I treat it as a question."

## 3. Priced for perfection? (about 50 seconds)
1. Read the headline: "At $20 the market is assuming 6.2% yearly growth. I assumed 8%."
2. Show the tornado: "Operating margin and the discount rate matter most, and growth matters least."
3. Show the share after the forecast: "76% of the value is the guess about the far future."

## Close (10 seconds)
"Every model states its assumptions, every result shows its random draw number, and 303 tests (including bugs I planted on purpose to check the tests catch them) back the math."

## Likely questions
- **Is the data real?** No. The sample assets and Cedar Co are made up. You can paste your own prices.
- **Why is the median below the average?** Volatility drag: losses hurt more than equal gains help.
- **Is this advice?** No. It says so on every screen. It is a way to see risk.
- **What would you add?** Fat-tailed returns, taxes and inflation, and saving scenarios.

## Before you present (checklist)
1. Run `python scripts/check_live.py MSFT` with your keys and compare the numbers with the 10-K.
2. Run `python scripts/make_snapshot.py MSFT AAPL KO` and commit `data/snapshots/`, so the demo works with no internet.
3. Open the app once and click through all three tabs on the machine you will present from.
