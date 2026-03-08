"""
Weather ColdMath Carry Strategy

Inspired by Polymarket trader ColdMath (@ColdMath), who turned ~$3.8M in volume
into +$58,869 P&L trading almost exclusively weather temperature markets. His bio
"Edge Compounds" captures the core thesis: harvest tiny, high-probability edges
at massive volume and let compounding do the work.

=== ColdMath Strategy Analysis ===

Profile:
  - Wallet: 0x594edb9112f526fa6a80b8f858a6379c8a2c1c11
  - Active since: November 2025
  - 3,083 predictions, $3.8M total volume, +$58,869 overall P&L
  - 99%+ of trades are weather temperature markets

Strategy operates in TWO modes:

MODE 1 — High-Probability NO Harvesting (Primary, ~85% of capital):
  Buy NO on temperature thresholds very unlikely to be reached.
  Entry prices: $0.96–$0.99 (implied 96–99% probability of NO).
  Per-share yield: 1–4% upon resolution (pennies per share, but at scale).
  Position sizes: 1,000–2,400 shares ($1,000–$2,400 per position).
  Example: "Will Chicago reach 63F?" → Buy NO at $0.989 → collect $0.011/share.
  Win rate: ~95%+ on these positions.

MODE 2 — Micro-Price Lottery Tickets (Secondary, ~15% of capital):
  Buy YES on specific temperature buckets priced at $0.001–$0.05.
  Tiny position sizes: $1–$70 per trade.
  Very low win rate (~5–10%) but 20–50x ROI when correct.
  Acts as tail-risk offset and high-upside optionality.

Key Behavioral Patterns:
  - Geographic diversification: 10+ cities (Chicago, NYC, Miami, Dallas,
    Buenos Aires, Toronto, Wellington, London, Paris, Munich, Lucknow, etc.)
  - Rapid, systematic execution (multiple trades per second → likely automated)
  - Hold to resolution (no early exits — weather markets expire at fixed time)
  - Both-sides hedging: sometimes buys YES and NO on related buckets
  - Started with small crypto bets (Ethereum, Bitcoin), pivoted fully to weather
  - Bio "Edge Compounds" → Bayesian Kelly-like compounding on positive EV bets

Why It Works:
  - Weather forecasts are highly accurate 24–48h out (0.5–1°C error)
  - Polymarket temperature buckets are often 1–2°C wide
  - When forecast confidence is high, extreme tail buckets are nearly guaranteed
    to resolve NO, but the market prices them at 96–99% instead of 99.5%+
  - The 0.5–3.5% edge per resolution, compounded across 3,000+ bets, yields
    consistent profit despite occasional losses on tail events

Implementation:
  This strategy evaluates weather intents and operates in two modes:
  1. Carry Mode: Buy NO on tail buckets where model probability < market NO price
     (i.e., the event is even less likely than the market thinks)
  2. Lottery Mode: Buy YES on specific buckets where model probability > YES price
     AND the YES price is very cheap (< $0.05), providing asymmetric upside

Pipeline:
  1. Weather workflow provides enriched intents with ensemble/consensus data
  2. Strategy computes model probability for each bucket
  3. For Carry Mode: filter buckets where YES price < carry_max_yes_price
     and model_prob < yes_price (NO is underpriced)
  4. For Lottery Mode: filter buckets where YES price < lottery_max_yes_price
     and model_prob > yes_price (YES is underpriced at micro-prices)
  5. Position sizing: Carry uses large, fixed sizes; Lottery uses small sizes
  6. Hold to resolution — no exit management needed
"""

from __future__ import annotations

import logging
import math
from typing import Any, Optional

from config import settings
from models import Opportunity, Event, Market
from models.opportunity import MispricingType
from services.strategies.base import (
    BaseStrategy,
    DecisionCheck,
    ScoringWeights,
    SizingConfig,
    ExitDecision,
)
from services.data_events import DataEvent
from services.quality_filter import QualityFilterOverrides
from services.strategy_sdk import StrategySDK
from utils.converters import to_float, to_confidence
from utils.signal_helpers import weather_signal_context, hours_to_target
from services.weather.signal_engine import (
    ensemble_bucket_probability,
    compute_confidence,
    compute_model_agreement,
)

logger = logging.getLogger(__name__)


def _norm_cdf(x: float, mu: float, sigma: float) -> float:
    """Normal distribution CDF using the error function."""
    return 0.5 * (1.0 + math.erf((x - mu) / (sigma * math.sqrt(2.0))))


class WeatherColdmathCarryStrategy(BaseStrategy):
    """
    ColdMath-inspired dual-mode weather carry strategy.

    Mode 1 (Carry): Buy NO on tail-end temperature buckets at 0.96–0.99,
    harvesting 1–4% yield per resolution with high probability of success.

    Mode 2 (Lottery): Buy YES on micro-priced buckets at 0.001–0.05,
    capturing 20–50x asymmetric upside on rare events.

    Both modes hold to resolution — weather markets expire at a fixed time.
    Geographic diversification across 10+ cities reduces correlation risk.
    """

    strategy_type = "weather_coldmath_carry"
    name = "Weather ColdMath Carry"
    description = (
        "Dual-mode weather carry: harvest high-probability NO at 96-99c "
        "and micro-price YES lottery tickets. Inspired by ColdMath's "
        "$58K profit on $3.8M volume across 3,000+ weather predictions."
    )
    mispricing_type = "news_information"
    source_key = "weather"
    worker_affinity = "weather"
    subscriptions = ["weather_update"]

    quality_filter_overrides = QualityFilterOverrides(
        min_roi=0.5,  # Carry mode has thin ROI per trade — lower floor
        max_resolution_months=0.5,
    )

    DEFAULT_CONFIG = {
        # -- Carry Mode (high-probability NO) --
        "carry_enabled": True,
        "carry_max_yes_price": 0.04,  # Only buy NO when YES is priced < 4c
        "carry_min_no_edge_percent": 0.5,  # Minimum edge on NO side
        "carry_min_model_confidence": 0.50,
        "carry_min_ensemble_agreement": 0.0,  # How many ensemble members agree
        "carry_base_size_usd": 200.0,  # ColdMath uses $1,000–$2,400; start conservative
        "carry_max_size_usd": 500.0,
        "carry_risk_base_score": 0.15,  # Low risk — high probability bets

        # -- Lottery Mode (micro-price YES) --
        "lottery_enabled": True,
        "lottery_max_yes_price": 0.05,  # Only buy YES priced < 5c
        "lottery_min_yes_edge_percent": 2.0,  # Model must show >= 2% edge on YES
        "lottery_min_model_confidence": 0.30,  # Lower bar — these are speculative
        "lottery_base_size_usd": 10.0,  # Small lottery tickets
        "lottery_max_size_usd": 50.0,
        "lottery_risk_base_score": 0.55,  # Higher risk — low probability bets

        # -- Shared --
        "sigma_c": 1.8,  # Std dev for normal CDF fallback
        "max_hours_to_resolution": 72.0,  # ColdMath focuses on near-term (24–72h)
        "min_source_count": 1,
        "max_source_spread_c": 6.0,
        "max_buckets_per_event": 3,  # Max positions in one event
        "geographic_diversification": True,  # Prefer spreading across cities
    }

    # ------------------------------------------------------------------
    # Init / configure
    # ------------------------------------------------------------------

    def __init__(self) -> None:
        super().__init__()
        self._config: dict = dict(self.DEFAULT_CONFIG)

    def configure(self, config: dict) -> None:
        if config:
            for key in self.DEFAULT_CONFIG:
                if key in config:
                    self._config[key] = config[key]

    @staticmethod
    def _normalize_intent(intent: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(intent)

        weather_payload = normalized.get("weather")
        if isinstance(weather_payload, dict):
            for key in (
                "source_count",
                "source_spread_c",
                "consensus_probability",
                "consensus_value_c",
                "model_agreement",
                "target_time",
                "location",
                "metric",
                "operator",
                "ensemble_members",
            ):
                if normalized.get(key) is None and weather_payload.get(key) is not None:
                    normalized[key] = weather_payload.get(key)
            if normalized.get("bucket_low_c") is None and weather_payload.get("threshold_c_low") is not None:
                normalized["bucket_low_c"] = weather_payload.get("threshold_c_low")
            if normalized.get("bucket_high_c") is None and weather_payload.get("threshold_c_high") is not None:
                normalized["bucket_high_c"] = weather_payload.get("threshold_c_high")
            threshold_raw = (
                normalized.get("threshold_c")
                if normalized.get("threshold_c") is not None
                else weather_payload.get("threshold_c")
            )
            try:
                threshold_c = float(threshold_raw) if threshold_raw is not None else None
            except Exception:
                threshold_c = None
            if threshold_c is not None and (
                normalized.get("bucket_low_c") is None or normalized.get("bucket_high_c") is None
            ):
                operator = (
                    str(
                        normalized.get("operator")
                        if normalized.get("operator") is not None
                        else weather_payload.get("operator") or ""
                    )
                    .strip()
                    .lower()
                )
                span_c = 25.0
                if normalized.get("bucket_low_c") is None and normalized.get("bucket_high_c") is None:
                    if operator in {"gt", "gte", ">", ">="}:
                        normalized["bucket_low_c"] = threshold_c
                        normalized["bucket_high_c"] = threshold_c + span_c
                    else:
                        normalized["bucket_low_c"] = threshold_c - span_c
                        normalized["bucket_high_c"] = threshold_c
                elif normalized.get("bucket_low_c") is None:
                    normalized["bucket_low_c"] = threshold_c - span_c
                elif normalized.get("bucket_high_c") is None:
                    normalized["bucket_high_c"] = threshold_c + span_c

        market_payload = normalized.get("market")
        if isinstance(market_payload, dict):
            if not str(normalized.get("market_id") or "").strip():
                normalized["market_id"] = market_payload.get("condition_id") or market_payload.get("id")
            if not str(normalized.get("market_slug") or "").strip() and market_payload.get("slug") is not None:
                normalized["market_slug"] = market_payload.get("slug")
            if not str(normalized.get("event_slug") or "").strip() and market_payload.get("event_slug") is not None:
                normalized["event_slug"] = market_payload.get("event_slug")
            if normalized.get("liquidity") is None and market_payload.get("liquidity") is not None:
                normalized["liquidity"] = market_payload.get("liquidity")
            if normalized.get("volume") is None and market_payload.get("volume") is not None:
                normalized["volume"] = market_payload.get("volume")
            if not normalized.get("clob_token_ids") and isinstance(market_payload.get("clob_token_ids"), list):
                normalized["clob_token_ids"] = list(market_payload.get("clob_token_ids") or [])

        direction = str(normalized.get("direction") or "").strip().lower()
        entry_price = normalized.get("entry_price")
        try:
            entry = float(entry_price) if entry_price is not None else None
        except Exception:
            entry = None

        yes_raw = normalized.get("yes_price")
        no_raw = normalized.get("no_price")
        try:
            yes_price = float(yes_raw) if yes_raw is not None else None
        except Exception:
            yes_price = None
        try:
            no_price = float(no_raw) if no_raw is not None else None
        except Exception:
            no_price = None

        if entry is not None:
            if direction == "buy_yes" and yes_price is None:
                yes_price = entry
            if direction == "buy_no" and no_price is None:
                no_price = entry

        if yes_price is None and no_price is not None:
            yes_price = 1.0 - no_price
        if no_price is None and yes_price is not None:
            no_price = 1.0 - yes_price

        if yes_price is None:
            yes_price = 0.5
        if no_price is None:
            no_price = 0.5

        normalized["yes_price"] = max(0.0, min(1.0, float(yes_price)))
        normalized["no_price"] = max(0.0, min(1.0, float(no_price)))
        return normalized

    @staticmethod
    def _market_from_intent(intent: dict[str, Any]) -> Optional[Market]:
        market_payload = intent.get("market")
        if not isinstance(market_payload, dict):
            market_payload = {}

        condition_id = str(
            intent.get("market_id") or market_payload.get("condition_id") or market_payload.get("id") or ""
        ).strip()
        if not condition_id:
            return None

        question = str(intent.get("market_question") or market_payload.get("question") or condition_id).strip()
        slug = str(market_payload.get("slug") or intent.get("market_slug") or condition_id).strip()
        event_slug = str(market_payload.get("event_slug") or intent.get("event_slug") or "").strip()
        platform = str(market_payload.get("platform") or intent.get("platform") or "polymarket").strip() or "polymarket"

        raw_token_ids = market_payload.get("clob_token_ids")
        if not isinstance(raw_token_ids, list):
            raw_token_ids = []
        clob_token_ids = [str(token_id).strip() for token_id in raw_token_ids if str(token_id).strip()]

        try:
            liquidity = float(market_payload.get("liquidity") or intent.get("liquidity") or 0.0)
        except Exception:
            liquidity = 0.0
        try:
            volume = float(market_payload.get("volume") or intent.get("volume") or 0.0)
        except Exception:
            volume = 0.0

        yes_price = float(intent.get("yes_price", 0.5))
        no_price = float(intent.get("no_price", 0.5))
        return Market(
            id=condition_id,
            condition_id=condition_id,
            question=question or condition_id,
            slug=slug or condition_id,
            event_slug=event_slug,
            clob_token_ids=clob_token_ids,
            outcome_prices=[yes_price, no_price],
            liquidity=max(0.0, liquidity),
            volume=max(0.0, volume),
            platform=platform,
        )

    # ------------------------------------------------------------------
    # detect (sync — always returns []; weather uses detect_from_intents)
    # ------------------------------------------------------------------

    def detect(
        self,
        events: list[Event],
        markets: list[Market],
        prices: dict[str, dict],
    ) -> list[Opportunity]:
        return []

    # ------------------------------------------------------------------
    # detect_from_intents (main entry-point for weather pipeline)
    # ------------------------------------------------------------------

    def detect_from_intents(
        self,
        intents: list[dict],
        markets: list[Market],
        events: list[Event],
    ) -> list[Opportunity]:
        """Evaluate weather intents through dual-mode ColdMath pipeline."""
        if not intents:
            return []

        cfg = self._config
        opportunities: list[Opportunity] = []
        market_map = {m.id: m for m in markets}
        event_map: dict[str, Event] = {}
        for event in events:
            for m in event.markets:
                event_map[m.id] = event

        for intent in intents:
            try:
                # Try Carry Mode first (primary mode — high volume)
                if cfg.get("carry_enabled", True):
                    opp = self._evaluate_carry(intent, market_map, event_map, cfg)
                    if opp:
                        opportunities.append(opp)
                        continue

                # Try Lottery Mode (secondary — micro-price tickets)
                if cfg.get("lottery_enabled", True):
                    opp = self._evaluate_lottery(intent, market_map, event_map, cfg)
                    if opp:
                        opportunities.append(opp)
            except Exception as e:
                logger.debug("%s: skipped intent: %s", self.name, e)

        if opportunities:
            carry_count = sum(1 for o in opportunities if "Carry" in (o.title or ""))
            lottery_count = sum(1 for o in opportunities if "Lottery" in (o.title or ""))
            logger.info(
                "%s: %d opportunities (%d carry, %d lottery) from %d intents",
                self.name,
                len(opportunities),
                carry_count,
                lottery_count,
                len(intents),
            )
        return opportunities

    # ------------------------------------------------------------------
    # _compute_model_prob — shared probability computation
    # ------------------------------------------------------------------

    def _compute_model_prob(
        self,
        intent: dict,
        bucket_low: float,
        bucket_high: float,
        consensus_f: float,
        sigma: float,
    ) -> Optional[float]:
        """Compute model probability for a temperature bucket."""
        ensemble_members = intent.get("ensemble_members")
        if ensemble_members and len(ensemble_members) > 0:
            return ensemble_bucket_probability(ensemble_members, bucket_low, bucket_high)
        prob = _norm_cdf(bucket_high, consensus_f, sigma) - _norm_cdf(bucket_low, consensus_f, sigma)
        return max(0.0, prob)

    # ------------------------------------------------------------------
    # MODE 1: Carry — Buy NO on high-probability outcomes
    # ------------------------------------------------------------------

    def _evaluate_carry(
        self,
        intent: dict,
        market_map: dict[str, Market],
        event_map: dict[str, Event],
        cfg: dict,
    ) -> Optional[Opportunity]:
        """
        Carry Mode: Buy NO when the YES price is very low (< 4c),
        meaning the NO side is priced at 96–99c. If our model says the
        event is even less likely than the market implies, there's a
        small but reliable edge that compounds over many resolutions.
        """
        yes_price = float(intent.get("yes_price", 0.5))
        no_price = float(intent.get("no_price", 0.5))

        # Gate: Only enter carry when YES is very cheap (bucket is unlikely)
        carry_max_yes = float(cfg.get("carry_max_yes_price", 0.04))
        if yes_price > carry_max_yes:
            return None

        bucket_low = intent.get("bucket_low_c")
        bucket_high = intent.get("bucket_high_c")
        consensus_value_c = intent.get("consensus_value_c")
        if bucket_low is None or bucket_high is None or consensus_value_c is None:
            return None

        bucket_low_f = float(bucket_low)
        bucket_high_f = float(bucket_high)
        consensus_f = float(consensus_value_c)
        sigma = float(cfg.get("sigma_c", 1.8))

        model_prob = self._compute_model_prob(intent, bucket_low_f, bucket_high_f, consensus_f, sigma)
        if model_prob is None:
            return None

        # Carry logic: model says YES is even less likely than market price
        # Edge on NO side = (1 - model_prob) - no_price
        model_no_prob = 1.0 - model_prob
        no_edge = model_no_prob - no_price
        no_edge_percent = no_edge * 100.0

        min_no_edge = float(cfg.get("carry_min_no_edge_percent", 0.5))
        if no_edge_percent < min_no_edge:
            return None

        # Direction is always buy_no in carry mode
        direction = "buy_no"
        entry_price = no_price
        target_price = model_no_prob

        # Confidence check
        source_count = max(0, int(to_float(intent.get("source_count"), 0)))
        source_spread_c = float(intent.get("source_spread_c") or 0)
        ensemble_members = intent.get("ensemble_members")
        agreement = float(intent.get("model_agreement", 0))
        if agreement == 0 and ensemble_members:
            agreement = compute_model_agreement({"ensemble": model_prob})

        confidence = compute_confidence(agreement, model_no_prob, source_count, source_spread_c)
        min_confidence = float(cfg.get("carry_min_model_confidence", 0.50))
        if confidence < min_confidence:
            return None

        # Market lookup
        market_id = intent.get("market_id")
        market = market_map.get(market_id) if market_id else None
        event = event_map.get(market_id) if market_id else None
        if not market:
            return None

        city = intent.get("location", "Unknown")
        question = market.question or ""

        # Token selection (NO side)
        token_id = None
        if market.clob_token_ids:
            idx = 1 if len(market.clob_token_ids) > 1 else 0
            token_id = market.clob_token_ids[idx]

        # Profit calculation
        expected_payout = target_price
        total_cost = entry_price
        gross_profit = expected_payout - total_cost
        fee_amount = expected_payout * self.fee
        net_profit = gross_profit - fee_amount
        roi = (net_profit / total_cost) * 100 if total_cost > 0 else 0

        if roi < 0.25:  # Even small carry should be positive
            return None

        # Position sizing — carry uses larger sizes (ColdMath style)
        sizing = StrategySDK.resolve_position_sizing(
            liquidity_usd=market.liquidity,
            liquidity_fraction=0.08,  # More aggressive liquidity fraction for carry
            hard_cap_usd=float(cfg.get("carry_max_size_usd", 500.0)),
            signal=intent,
            default_min_size=float(settings.MIN_POSITION_SIZE),
        )
        min_liquidity = float(sizing.get("liquidity_usd", 0.0) or 0.0)
        max_position = float(sizing.get("max_position_size", 0.0) or 0.0)
        if not bool(sizing.get("is_tradeable", False)):
            return None

        # Risk scoring — carry is inherently lower risk
        risk_score = float(cfg.get("carry_risk_base_score", 0.15))
        risk_factors = [
            "ColdMath carry: high-probability NO harvest",
            f"YES price: ${yes_price:.3f} (< ${carry_max_yes:.2f} threshold)",
            f"Model NO prob: {model_no_prob:.1%} vs market: {no_price:.1%}",
            f"NO edge: {no_edge_percent:.2f}%",
        ]
        if source_spread_c > 3.0:
            risk_score += 0.10
            risk_factors.append("High source disagreement")
        if no_edge_percent < 1.0:
            risk_score += 0.05
            risk_factors.append("Very thin carry edge")
        risk_score = min(risk_score, 1.0)

        # Build opportunity
        positions = [
            {
                "action": "BUY",
                "outcome": "NO",
                "price": entry_price,
                "token_id": token_id,
                "_coldmath_carry": {
                    "mode": "carry",
                    "city": city,
                    "model_yes_prob": model_prob,
                    "model_no_prob": model_no_prob,
                    "no_edge_percent": no_edge_percent,
                    "yes_price": yes_price,
                    "confidence": confidence,
                    "source_count": source_count,
                    "source_spread_c": source_spread_c,
                    "bucket_low_c": bucket_low_f,
                    "bucket_high_c": bucket_high_f,
                    "consensus_value_c": consensus_f,
                    "used_ensemble": bool(intent.get("ensemble_members")),
                },
            }
        ]

        title = f"Carry: {city} - NO on {question[:35]}"
        description = (
            f"ColdMath carry | NO at ${entry_price:.3f} "
            f"(YES=${yes_price:.3f}, edge={no_edge_percent:.2f}%) | "
            f"Model: {model_no_prob:.1%} NO prob"
        )

        opp = self.create_opportunity(
            title=title,
            description=description,
            total_cost=total_cost,
            expected_payout=expected_payout,
            markets=[market],
            positions=positions,
            event=event,
            is_guaranteed=False,
            custom_roi_percent=roi,
            custom_risk_score=risk_score,
            confidence=confidence,
        )
        if opp is not None:
            opp.strategy_context = {
                "source_key": "weather",
                "strategy_slug": self.strategy_type,
                "coldmath_mode": "carry",
                "weather": {
                    "agreement": agreement,
                    "model_agreement": agreement,
                    "source_count": source_count,
                    "source_spread_c": source_spread_c,
                    "consensus_temp_c": consensus_f,
                    "model_probability": model_prob,
                    "no_edge_percent": no_edge_percent,
                    "target_time": intent.get("target_time"),
                    "used_ensemble": bool(intent.get("ensemble_members")),
                },
            }
            opp.risk_factors = risk_factors
            opp.min_liquidity = min_liquidity
            opp.max_position_size = max_position
            opp.mispricing_type = MispricingType.NEWS_INFORMATION
        return opp

    # ------------------------------------------------------------------
    # MODE 2: Lottery — Buy YES on micro-priced buckets
    # ------------------------------------------------------------------

    def _evaluate_lottery(
        self,
        intent: dict,
        market_map: dict[str, Market],
        event_map: dict[str, Event],
        cfg: dict,
    ) -> Optional[Opportunity]:
        """
        Lottery Mode: Buy YES when the price is extremely cheap (< 5c)
        AND the model suggests the true probability is meaningfully higher
        than the market price. These are low-probability, high-payout bets
        that provide asymmetric upside and hedge against carry losses.
        """
        yes_price = float(intent.get("yes_price", 0.5))
        no_price = float(intent.get("no_price", 0.5))

        # Gate: Only enter lottery when YES is very cheap
        lottery_max_yes = float(cfg.get("lottery_max_yes_price", 0.05))
        if yes_price > lottery_max_yes:
            return None
        if yes_price <= 0.001:  # Too cheap — likely stale or zero liquidity
            return None

        bucket_low = intent.get("bucket_low_c")
        bucket_high = intent.get("bucket_high_c")
        consensus_value_c = intent.get("consensus_value_c")
        if bucket_low is None or bucket_high is None or consensus_value_c is None:
            return None

        bucket_low_f = float(bucket_low)
        bucket_high_f = float(bucket_high)
        consensus_f = float(consensus_value_c)
        sigma = float(cfg.get("sigma_c", 1.8))

        model_prob = self._compute_model_prob(intent, bucket_low_f, bucket_high_f, consensus_f, sigma)
        if model_prob is None:
            return None

        # Lottery logic: model says YES is more likely than market price
        yes_edge = model_prob - yes_price
        yes_edge_percent = yes_edge * 100.0

        min_yes_edge = float(cfg.get("lottery_min_yes_edge_percent", 2.0))
        if yes_edge_percent < min_yes_edge:
            return None

        direction = "buy_yes"
        entry_price = yes_price
        target_price = model_prob

        # Confidence check (lower bar for lottery)
        source_count = max(0, int(to_float(intent.get("source_count"), 0)))
        source_spread_c = float(intent.get("source_spread_c") or 0)
        ensemble_members = intent.get("ensemble_members")
        agreement = float(intent.get("model_agreement", 0))
        if agreement == 0 and ensemble_members:
            agreement = compute_model_agreement({"ensemble": model_prob})

        confidence = compute_confidence(agreement, model_prob, source_count, source_spread_c)
        min_confidence = float(cfg.get("lottery_min_model_confidence", 0.30))
        if confidence < min_confidence:
            return None

        # Market lookup
        market_id = intent.get("market_id")
        market = market_map.get(market_id) if market_id else None
        event = event_map.get(market_id) if market_id else None
        if not market:
            return None

        city = intent.get("location", "Unknown")
        question = market.question or ""

        # Token selection (YES side)
        token_id = None
        if market.clob_token_ids:
            token_id = market.clob_token_ids[0]

        # Profit calculation — lottery has high ROI when it hits
        expected_payout = target_price
        total_cost = entry_price
        gross_profit = expected_payout - total_cost
        fee_amount = expected_payout * self.fee
        net_profit = gross_profit - fee_amount
        roi = (net_profit / total_cost) * 100 if total_cost > 0 else 0

        if roi < 10.0:  # Lottery should offer substantial upside
            return None

        # Position sizing — lottery uses small sizes
        sizing = StrategySDK.resolve_position_sizing(
            liquidity_usd=market.liquidity,
            liquidity_fraction=0.02,  # Conservative for lottery
            hard_cap_usd=float(cfg.get("lottery_max_size_usd", 50.0)),
            signal=intent,
            default_min_size=float(settings.MIN_POSITION_SIZE),
        )
        min_liquidity = float(sizing.get("liquidity_usd", 0.0) or 0.0)
        max_position = float(sizing.get("max_position_size", 0.0) or 0.0)
        if not bool(sizing.get("is_tradeable", False)):
            return None

        # Risk scoring — lottery is inherently higher risk
        risk_score = float(cfg.get("lottery_risk_base_score", 0.55))
        risk_factors = [
            "ColdMath lottery: micro-price YES ticket",
            f"YES price: ${yes_price:.3f} (asymmetric upside)",
            f"Model YES prob: {model_prob:.1%} vs market: {yes_price:.1%}",
            f"YES edge: {yes_edge_percent:.1f}%",
            f"Potential ROI: {roi:.0f}%",
        ]
        if source_spread_c > 4.0:
            risk_score += 0.10
            risk_factors.append("Wide source disagreement")
        if model_prob < 0.10:
            risk_score += 0.10
            risk_factors.append("Sub-10% model probability")
        risk_score = min(risk_score, 1.0)

        # Build opportunity
        positions = [
            {
                "action": "BUY",
                "outcome": "YES",
                "price": entry_price,
                "token_id": token_id,
                "_coldmath_lottery": {
                    "mode": "lottery",
                    "city": city,
                    "model_yes_prob": model_prob,
                    "yes_edge_percent": yes_edge_percent,
                    "yes_price": yes_price,
                    "potential_roi_pct": roi,
                    "confidence": confidence,
                    "source_count": source_count,
                    "source_spread_c": source_spread_c,
                    "bucket_low_c": bucket_low_f,
                    "bucket_high_c": bucket_high_f,
                    "consensus_value_c": consensus_f,
                    "used_ensemble": bool(intent.get("ensemble_members")),
                },
            }
        ]

        title = f"Lottery: {city} - YES on {question[:35]}"
        description = (
            f"ColdMath lottery | YES at ${entry_price:.3f} "
            f"(model={model_prob:.1%}, edge={yes_edge_percent:.1f}%, "
            f"ROI={roi:.0f}%)"
        )

        opp = self.create_opportunity(
            title=title,
            description=description,
            total_cost=total_cost,
            expected_payout=expected_payout,
            markets=[market],
            positions=positions,
            event=event,
            is_guaranteed=False,
            custom_roi_percent=roi,
            custom_risk_score=risk_score,
            confidence=confidence,
        )
        if opp is not None:
            opp.strategy_context = {
                "source_key": "weather",
                "strategy_slug": self.strategy_type,
                "coldmath_mode": "lottery",
                "weather": {
                    "agreement": agreement,
                    "model_agreement": agreement,
                    "source_count": source_count,
                    "source_spread_c": source_spread_c,
                    "consensus_temp_c": consensus_f,
                    "model_probability": model_prob,
                    "yes_edge_percent": yes_edge_percent,
                    "target_time": intent.get("target_time"),
                    "used_ensemble": bool(intent.get("ensemble_members")),
                },
            }
            opp.risk_factors = risk_factors
            opp.min_liquidity = min_liquidity
            opp.max_position_size = max_position
            opp.mispricing_type = MispricingType.NEWS_INFORMATION
        return opp

    # ------------------------------------------------------------------
    # on_event() (event-driven detection from weather worker)
    # ------------------------------------------------------------------

    async def on_event(self, event: DataEvent) -> list[Opportunity]:
        if event.event_type != "weather_update":
            return []
        raw_intents = event.payload.get("intents") or []
        if not raw_intents:
            return []
        intents: list[dict[str, Any]] = []
        markets: list[Market] = []
        for raw in raw_intents:
            if not isinstance(raw, dict):
                continue
            normalized = self._normalize_intent(raw)
            market = self._market_from_intent(normalized)
            if market is None:
                continue
            intents.append(normalized)
            markets.append(market)
        if not intents:
            return []
        return self.detect_from_intents(intents, markets, [])

    # ------------------------------------------------------------------
    # evaluate() (composable pipeline)
    # ------------------------------------------------------------------

    scoring_weights = ScoringWeights(
        edge_weight=0.45,  # Lower edge weight — carry edges are thin
        confidence_weight=25.0,
        risk_penalty=5.0,
    )
    sizing_config = SizingConfig()

    _coldmath_mode: str = "carry"
    _coldmath_edge: float = 0.0
    _coldmath_source_count: int = 0
    _coldmath_source_spread_c: float = 0.0

    def custom_checks(self, signal: Any, context: dict, params: dict, payload: dict) -> list[DecisionCheck]:
        weather = weather_signal_context(signal)

        source = str(getattr(signal, "source", "") or "").strip().lower()
        source_ok = source in {"weather"}
        min_source_count = max(1, int(to_float(params.get("min_source_count", 1), 1)))
        max_source_spread = max(0.0, to_float(params.get("max_source_spread_c", 6.0), 6.0))
        max_target_hours = max(1.0, to_float(params.get("max_hours_to_resolution", 72.0), 72.0))

        source_count = max(0, int(to_float(weather.get("source_count", 0), 0)))
        source_spread_c = max(0.0, to_float(weather.get("source_spread_c", 0.0), 0.0))
        htt = hours_to_target(weather.get("target_time"))
        target_window_ok = htt is None or (0.0 <= htt <= max_target_hours)

        self._coldmath_source_count = source_count
        self._coldmath_source_spread_c = source_spread_c

        # Determine mode from strategy context
        strategy_context = getattr(signal, "strategy_context", None) or {}
        self._coldmath_mode = str(strategy_context.get("coldmath_mode", "carry"))

        return [
            DecisionCheck("source", "Weather source", source_ok, detail="Requires source=weather."),
            DecisionCheck(
                "source_count",
                "Forecast source depth",
                source_count >= min_source_count,
                score=float(source_count),
                detail=f"min={min_source_count}",
            ),
            DecisionCheck(
                "source_spread",
                "Model spread ceiling (C)",
                source_spread_c <= max_source_spread,
                score=source_spread_c,
                detail=f"max={max_source_spread:.2f}",
            ),
            DecisionCheck(
                "target_window",
                "Resolution window",
                target_window_ok,
                score=htt,
                detail=f"max={max_target_hours:.0f}h",
            ),
        ]

    def compute_score(
        self, edge: float, confidence: float, risk_score: float, market_count: int, payload: dict
    ) -> float:
        # Carry mode: prioritize reliability over magnitude
        # Lottery mode: prioritize edge magnitude
        if self._coldmath_mode == "carry":
            return (
                (edge * 0.35)
                + (confidence * 35.0)
                + (min(3, self._coldmath_source_count) * 2.0)
                - (self._coldmath_source_spread_c * 0.8)
            )
        else:
            return (
                (edge * 0.70)
                + (confidence * 20.0)
                + (min(3, self._coldmath_source_count) * 1.0)
                - (self._coldmath_source_spread_c * 1.5)
            )

    def compute_size(
        self, base_size: float, max_size: float, edge: float, confidence: float, risk_score: float, market_count: int
    ) -> float:
        if self._coldmath_mode == "carry":
            # Carry: scale with confidence, keep size relatively stable
            size = base_size * (0.85 + confidence * 0.3) * (1.0 + min(0.15, edge / 200.0))
        else:
            # Lottery: smaller base, scale more with edge
            size = base_size * (0.5 + confidence) * (1.0 + min(0.5, edge / 50.0))
        return max(1.0, min(max_size, size))

    # ------------------------------------------------------------------
    # should_exit() — hold to resolution (ColdMath never exits early)
    # ------------------------------------------------------------------

    def should_exit(self, position: Any, market_state: dict) -> ExitDecision:
        """Weather markets resolve at fixed time — always hold to resolution.

        ColdMath's strategy is explicitly hold-to-expiry. Weather markets
        resolve at a known time and the edge is in the resolution, not in
        price movement before resolution.
        """
        if market_state.get("is_resolved"):
            return self.default_exit_check(position, market_state)
        return ExitDecision("hold", "ColdMath carry — holding to forecast resolution")

    # ------------------------------------------------------------------
    # Platform gate hooks
    # ------------------------------------------------------------------

    def on_blocked(self, signal, reason: str, context: dict) -> None:
        logger.info("%s: signal blocked — %s (market=%s)", self.name, reason, getattr(signal, "market_id", "?"))

    def on_size_capped(self, original_size: float, capped_size: float, reason: str) -> None:
        logger.info("%s: size capped $%.0f → $%.0f — %s", self.name, original_size, capped_size, reason)
