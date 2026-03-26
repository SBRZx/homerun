# Deep Viability Analysis: Prediction Market Arbitrage vs Options Strategies

## Use This Prompt With Claude or Any LLM

Copy everything below the line and paste it into a new conversation. Fill in the bracketed `[YOUR_...]` fields with your actual numbers first.

---

## PROMPT START

I need a rigorous, quantitative analysis of two competing paths for generating semi-passive income from trading automation. I want you to be brutally honest — tell me where each path fails, not just where it succeeds. Challenge my assumptions.

### My Situation

- **Available capital:** $[YOUR_AMOUNT] (e.g., $5,000 / $10,000 / $50,000)
- **Monthly income I need this to generate to be "worth it":** $[YOUR_TARGET] (e.g., $500)
- **Hours per week I can dedicate to setup/maintenance:** [YOUR_HOURS] (e.g., 5-10)
- **Technical skill level:** [YOUR_LEVEL] (e.g., "can run Docker and edit Python" / "professional developer" / "basic terminal")
- **Risk tolerance:** [YOUR_TOLERANCE] (e.g., "can't afford to lose more than 10% of capital" / "willing to lose it all for learning")
- **Hardware available:** [YOUR_HARDWARE] (e.g., "ThinkCentre M710q running 24/7" / "personal laptop only" / "willing to rent a VPS")
- **Location:** [YOUR_LOCATION] (relevant for regulatory — US/EU/other)
- **Existing brokerage accounts:** [YOUR_ACCOUNTS] (e.g., "none" / "Robinhood" / "IBKR" / "Schwab")
- **Crypto wallet experience:** [YOUR_CRYPTO] (e.g., "none" / "have used MetaMask" / "experienced DeFi user")

---

### PATH A: Prediction Market Arbitrage Bot

I have access to an open-source platform called "Homerun" — a full-stack Python/React prediction market arbitrage system with:
- 35+ pre-built strategies (crypto arb, market making, flash crash reversion, news edge, probability surface arb, cross-platform arb, etc.)
- Polymarket and Kalshi integration
- Paper trading mode for zero-risk testing
- Custom data source framework (Python/RSS/REST APIs)
- Custom strategy framework (full Python, hot-reloadable)
- Risk-gated execution orchestrator
- Real-time price feeds via WebSocket (Polymarket Chainlink oracle)
- PostgreSQL backend, FastAPI, React frontend

**Analyze the following for Path A:**

1. **Market Opportunity Sizing**
   - What is the realistic daily volume on Polymarket and Kalshi as of early 2026?
   - What percentage of that volume represents exploitable inefficiency vs. informed pricing?
   - How does liquidity depth affect achievable position sizes? (i.e., can I actually deploy $X without moving the market?)
   - What is the realistic spread/edge available on cross-market arbs (Polymarket vs. Kalshi) after accounting for gas fees, USDC conversion, and execution slippage?
   - How quickly do arb opportunities close? (seconds? minutes?) What latency do I need to capture them?

2. **Cost Structure & Break-Even**
   - Polymarket fees (maker/taker)
   - Kalshi fees (per-contract)
   - Ethereum/Polygon gas costs per transaction
   - USDC on-ramp/off-ramp costs and time delays
   - Server/infrastructure costs (electricity, internet, VPS if needed)
   - What is my all-in cost per round-trip trade?
   - At what monthly volume do I break even on infrastructure costs alone?

3. **Risk Taxonomy (Be Specific)**
   - **Platform risk:** What happens if Polymarket goes down, gets hacked, or exit scams? Historical precedents?
   - **Smart contract risk:** What are the actual risks of funds locked in Polymarket's contracts?
   - **Regulatory risk:** Current CFTC stance on Polymarket for US users. Kalshi's regulated status. What changes in 2025-2026 could affect this?
   - **Market manipulation risk:** How thin are these markets? Can a whale move prices to trigger my strategies adversely?
   - **Settlement risk:** What happens in disputed event outcomes? Who arbitrates?
   - **Strategy risk:** Of the 35 built-in strategies, which ones have the highest theoretical Sharpe ratio and which are essentially gambling?
   - **Execution risk:** What happens during chain congestion? Failed transactions that cost gas but don't execute?
   - **Correlation risk:** In a market crash or "black swan" event, do prediction market arbs all blow up simultaneously?

4. **Realistic Returns Modeling**
   Run three scenarios at my capital level:
   - **Bear case** (things go wrong but not catastrophically)
   - **Base case** (median outcome given market conditions)
   - **Bull case** (strategies find consistent edge)

   For each: monthly gross return, monthly net return (after all fees), max drawdown, Sharpe ratio estimate, and time-to-first-dollar.

5. **Automation Reality Check**
   - Can this truly run unattended, or does it need daily monitoring?
   - What failure modes require human intervention?
   - What's the 3am scenario — the thing that goes wrong at night that costs real money?

---

### PATH B: Conservative Options Strategies

I'm considering automating one or more of these strategies via broker API (e.g., IBKR):

- **The Wheel** (cash-secured puts → covered calls)
- **Iron Condors** on SPY/QQQ (defined risk)
- **0DTE Credit Spreads** on SPX (high frequency, small edge)
- **PMCC (Poor Man's Covered Calls)** on LEAPS
- **Box Spreads** on SPX (synthetic risk-free rate)
- **Dividend Capture** with protective puts

**Analyze the following for Path B:**

1. **Strategy-by-Strategy Breakdown**
   For each strategy above, provide:
   - Capital required to run it meaningfully
   - Realistic monthly return (%) on capital at risk
   - Max drawdown in the last 5 years (backtest or known data)
   - Win rate vs. average win/loss ratio
   - Greeks exposure (delta, theta, vega, gamma) and what that means in plain English
   - How well it automates (fully hands-off vs. needs judgment calls)
   - Which broker APIs support it best
   - Tax treatment (Section 1256 if applicable, wash sale implications)

2. **Automation Feasibility**
   - Which of these strategies can genuinely be automated end-to-end?
   - What's the state of open-source options trading bots? (thetagang bot, etc.)
   - IBKR API reliability — what are known failure modes?
   - How do you handle assignment risk in an automated system?
   - Pattern Day Trader rule implications at my capital level

3. **Risk Analysis**
   - What's the worst single-day loss for each strategy? (cite: Feb 2018 Volmageddon, March 2020 COVID crash, 2022 bear market)
   - Tail risk: how do iron condors and credit spreads behave in a flash crash?
   - Liquidity risk: during high-vol events, do spreads widen enough to make exit impossible?
   - Broker risk: is my capital protected (SIPC) and how does that compare to prediction market platform risk?

4. **Realistic Returns Modeling**
   Same three scenarios (bear/base/bull) at my capital level for the top 2-3 strategies you'd recommend, including:
   - Monthly/annual net return after commissions and taxes
   - Sharpe ratio
   - Maximum drawdown
   - Capital efficiency (how much capital is locked as collateral vs. working)

---

### HEAD-TO-HEAD COMPARISON

After analyzing both paths independently, give me:

1. **Risk-Adjusted Return Comparison**
   - At my capital level, which path has the higher expected risk-adjusted return?
   - Which has the higher ceiling? Which has the higher floor?
   - If I split capital 50/50, does diversification help or just halve both edges?

2. **Time Investment Comparison**
   - Hours to get to first live trade (setup, learning, testing)
   - Hours per week for ongoing maintenance
   - Which has a steeper learning curve?
   - Which compounds skill/knowledge better over time?

3. **Scalability**
   - At what capital level does each strategy max out? (Where does the edge disappear?)
   - Which path scales more gracefully from $10k to $100k to $1M?

4. **Regulatory & Longevity**
   - Which is more likely to still work in 3 years?
   - Which faces existential regulatory risk?
   - Which has more established infrastructure and community?

5. **The "What Would You Actually Do" Test**
   - If you had to put your own money into one path, which would you choose and why?
   - What's the minimum capital where each path becomes "worth the effort"?
   - Is there a hybrid approach (e.g., options income funding prediction market experiments)?

6. **Decision Matrix**
   Create a weighted scoring matrix with these factors:
   | Factor | Weight | Path A Score (1-10) | Path B Score (1-10) | Reasoning |
   |--------|--------|---------------------|---------------------|-----------|
   | Risk-adjusted return | 25% | | | |
   | Capital efficiency | 15% | | | |
   | Automation reliability | 15% | | | |
   | Regulatory safety | 15% | | | |
   | Setup effort | 10% | | | |
   | Ongoing maintenance | 10% | | | |
   | Learning value | 5% | | | |
   | Scalability | 5% | | | |

---

### FINAL OUTPUT

End with:
1. A clear **recommendation** for my specific situation (given the numbers I provided above)
2. A **90-day action plan** — what should I do in month 1, 2, and 3?
3. **Kill criteria** — specific, measurable signals that tell me "stop, this isn't working" for each path
4. **The one thing I'm probably not thinking about** that could derail either path

Be quantitative wherever possible. Use real numbers, real fee structures, real historical data. If you don't have exact numbers, give ranges and cite your confidence level. Do not be encouraging for the sake of being encouraging — I want the truth even if it's "neither path is viable at your capital level."

## PROMPT END
