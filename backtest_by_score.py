"""
backtest_by_score.py — รัน backtest แยกตามช่วง Bounce Score
เพื่อตอบคำถาม: "Bounce Score >= 75 แล้ว bounce จริงในอดีตมั้ย"

ใช้ logic เดียวกับ build_web_datasets.py ของทีม data sci
(load_base_data, build_features, run_rule_backtest)
"""

from __future__ import annotations

import gc
from pathlib import Path

import numpy as np
import pandas as pd


INPUT_CSV = Path("training_data_tv_FULL_FETCH_Week.csv")

BASE_COLUMNS = [
    "symbol", "date", "open", "high", "low", "close", "volume",
    "rsi", "atr", "ema50", "trend", "rvol", "macd_hist", "stoch_k", "roc",
]
FLOAT_COLUMNS = [
    "open", "high", "low", "close", "volume", "rsi", "atr", "ema50",
    "trend", "rvol", "macd_hist", "stoch_k", "roc",
]

TP_PCT = 0.08
SL_PCT = 0.06
MAX_HOLD_DAYS = 10  # หมายถึง 10 "bars" — สำหรับ weekly data คือ ~10 สัปดาห์
MAX_POSITIONS = 1


def load_base_data(csv_path: Path) -> pd.DataFrame:
    print(f"📂 โหลด {csv_path.name} …")
    dtypes = {col: "float32" for col in FLOAT_COLUMNS}
    dtypes["symbol"] = "category"
    df = pd.read_csv(
        csv_path,
        usecols=BASE_COLUMNS,
        dtype=dtypes,
        parse_dates=["date"],
    )
    df = df.dropna(subset=["symbol", "date", "open", "high", "low", "close", "volume"])
    df["symbol"] = df["symbol"].astype(str).str.strip().str.upper()
    df["source_timestamp"] = df["date"]
    df["trade_date"] = df["date"].dt.normalize()
    df = (
        df.sort_values(["symbol", "source_timestamp"])
        .groupby(["symbol", "trade_date"], sort=False, as_index=False)
        .tail(1)
        .reset_index(drop=True)
    )
    df["date"] = df["trade_date"]
    df = df.drop(columns=["trade_date"])
    df = df.sort_values(["symbol", "date"]).reset_index(drop=True)
    print(f"   {len(df):,} rows, {df['symbol'].nunique():,} symbols")
    return df


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    print("🔧 คำนวณ features …")
    by_symbol = df.groupby("symbol", sort=False, observed=True)

    df["hl_range"] = (df["high"] - df["low"] + 1e-9).astype("float32")
    df["atr_baseline"] = (
        by_symbol["atr"].transform(lambda x: x.rolling(50, min_periods=10).mean()).astype("float32")
    )
    df["past_5d_min"] = (
        by_symbol["close"].transform(lambda x: x.rolling(window=5, min_periods=1).min()).astype("float32")
    )
    df["sma20"] = by_symbol["close"].transform(lambda x: x.rolling(20).mean()).astype("float32")
    df["std20"] = by_symbol["close"].transform(lambda x: x.rolling(20).std()).astype("float32")
    df["bb_lower"] = (df["sma20"] - (2 * df["std20"])).astype("float32")
    df["bb_upper"] = (df["sma20"] + (2 * df["std20"])).astype("float32")
    df["vol_sma_20"] = by_symbol["volume"].transform(lambda x: x.rolling(window=20).mean()).astype("float32")

    vol_sma_5 = by_symbol["volume"].transform(lambda x: x.rolling(5).mean()).astype("float32")
    df["dist_ema50"] = ((df["close"] - df["ema50"]) / df["ema50"]).astype("float32")
    df["atr_pct"] = ((df["atr"] / df["close"]) * 100).astype("float32")
    df["roc_10"] = (by_symbol["close"].pct_change(periods=10) * 100).astype("float32")
    df["price_change_pct"] = ((df["close"] - df["open"]) / df["open"] * 100).astype("float32")
    df["run_up_from_bottom"] = (
        (df["close"] - df["past_5d_min"]) / (df["atr_baseline"] + 1e-9)
    ).astype("float32")
    df["vol_surge_int"] = (df["volume"] > vol_sma_5).astype("int8")
    df["vol_ratio"] = (df["volume"] / (df["vol_sma_20"] + 1e-8)).astype("float32")
    df["bb_width"] = ((df["bb_upper"] - df["bb_lower"]) / (df["sma20"] + 1e-9)).astype("float32")
    df["roc_3"] = (by_symbol["close"].pct_change(periods=3) * 100).astype("float32")
    df["accel_momentum"] = (df["roc_3"] - (df["roc_10"] / 3.33)).astype("float32")
    df["prev_close"] = by_symbol["close"].shift(1).astype("float32")

    features_to_shift = [
        "rsi", "atr", "ema50", "trend", "rvol", "macd_hist", "stoch_k", "roc",
        "hl_range", "atr_baseline", "past_5d_min", "sma20", "std20",
        "bb_lower", "bb_upper", "vol_sma_20", "dist_ema50", "atr_pct",
        "roc_10", "price_change_pct", "run_up_from_bottom", "vol_surge_int",
        "bb_width", "roc_3", "accel_momentum", "vol_ratio",
    ]
    for col in features_to_shift:
        df[col] = by_symbol[col].shift(1)

    df["gap_pct"] = ((df["open"] - df["prev_close"]) / (df["prev_close"] + 1e-9) * 100).astype("float32")
    df["close_to_bb_lower_pct"] = (
        (df["close"] - df["bb_lower"]) / ((df["bb_upper"] - df["bb_lower"]) + 1e-9)
    ).astype("float32")

    valid_mask = df[features_to_shift + ["prev_close"]].notna().all(axis=1)
    out = df.loc[valid_mask].reset_index(drop=True)
    print(f"   {len(out):,} rows พร้อมใช้ (หลัง drop NaN จาก shift)")
    return out


def score_candidates(df: pd.DataFrame) -> pd.DataFrame:
    print("🎯 คำนวณ Bounce Score …")
    out = df.copy()

    out["liquidity_score"] = (
        (out["vol_ratio"] >= 1.0).astype(int) + (out["rvol"] >= 1.0).astype(int)
    ).astype("int8")
    out["momentum_score"] = (
        (out["roc"] >= 0).astype(int)
        + (out["macd_hist"] >= 0).astype(int)
        + (out["accel_momentum"] >= 0).astype(int)
    ).astype("int8")
    out["trend_score"] = (
        (out["trend"] >= 1).astype(int) + (out["close"] >= out["ema50"]).astype(int)
    ).astype("int8")
    out["bounce_zone_score"] = (
        out["dist_ema50"].between(-0.08, 0.05, inclusive="both").astype(int)
        + out["rsi"].between(40, 70, inclusive="both").astype(int)
        + out["close_to_bb_lower_pct"].between(0.15, 0.70, inclusive="both").astype(int)
    ).astype("int8")
    out["risk_control_score"] = (
        (out["open"] >= 1.0).astype(int) + (out["stoch_k"] <= 85).astype(int)
    ).astype("int8")

    out["bounce_score_raw"] = (
        out["liquidity_score"] + out["momentum_score"] + out["trend_score"]
        + out["bounce_zone_score"] + out["risk_control_score"]
    )
    out["bounce_score"] = ((out["bounce_score_raw"] / 12.0) * 100).round(1)

    out["passes_base_filter"] = (
        (out["open"] >= 1.0) & (out["rsi"] <= 75) & (out["roc"] >= 0) & (out["vol_ratio"] >= 1.0)
    )
    return out


def run_rule_backtest(df_source: pd.DataFrame, min_bounce_score: float = 70.0,
                       start_date: pd.Timestamp | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    backtest_cols = [
        "symbol", "date", "open", "high", "low", "close",
        "rsi", "roc", "vol_ratio", "bounce_score", "rvol", "macd_hist", "ema50", "trend",
    ]
    df_bt = df_source[backtest_cols].copy()
    if start_date is not None:
        df_bt = df_bt[df_bt["date"] >= start_date].copy()

    df_bt["passes_entry"] = (
        (df_bt["open"] >= 1.0) & (df_bt["rsi"] <= 75) & (df_bt["roc"] >= 0)
        & (df_bt["vol_ratio"] >= 1.0) & (df_bt["bounce_score"] >= min_bounce_score)
    )

    available_cash = 100_000.0
    active_positions: list[dict] = []
    trade_log: list[dict] = []
    equity_curve: list[dict] = []

    for current_date, today_data in df_bt.groupby("date", sort=True, observed=True):
        has_sold_today = False
        keep: list[dict] = []
        today_rows = {str(row.symbol): row for row in today_data.itertuples(index=False)}

        for pos in active_positions:
            sym = str(pos["symbol"])
            row = today_rows.get(sym)

            if row is None:
                pos["hold_days"] = int(pos["hold_days"]) + 1
                if int(pos["hold_days"]) >= MAX_HOLD_DAYS:
                    sell_price = float(pos["current_value"]) / float(pos["shares"])
                    proceeds = float(pos["current_value"])
                    profit = proceeds - float(pos["invested"])
                    available_cash += proceeds
                    trade_log.append({**pos, "exit_date": current_date, "sell_price": sell_price,
                                       "result": "TIME", "profit": profit,
                                       "pct_change": (sell_price - float(pos["buy_price"])) / float(pos["buy_price"]) * 100})
                    has_sold_today = True
                else:
                    keep.append(pos)
                continue

            high = float(row.high); low = float(row.low); close = float(row.close)
            tp_price = float(pos["buy_price"]) * (1 + TP_PCT)
            sl_price = float(pos["buy_price"]) * (1 - SL_PCT)

            sold = False; reason = ""; sell_price = 0.0
            if low <= sl_price:
                sold, reason, sell_price = True, "LOSS", sl_price
            elif high >= tp_price:
                sold, reason, sell_price = True, "WIN", tp_price
            elif int(pos["hold_days"]) >= MAX_HOLD_DAYS:
                sold, reason, sell_price = True, "TIME", close

            if sold:
                proceeds = float(pos["shares"]) * sell_price
                profit = proceeds - float(pos["invested"])
                available_cash += proceeds
                trade_log.append({**pos, "exit_date": current_date, "sell_price": sell_price,
                                   "result": reason, "profit": profit,
                                   "pct_change": (sell_price - float(pos["buy_price"])) / float(pos["buy_price"]) * 100})
                has_sold_today = True
            else:
                pos["hold_days"] = int(pos["hold_days"]) + 1
                pos["current_value"] = float(pos["shares"]) * close
                keep.append(pos)

        active_positions = keep

        free_slots = MAX_POSITIONS - len(active_positions)
        if free_slots > 0 and available_cash > 100 and not has_sold_today:
            signals = today_data.loc[today_data["passes_entry"]]
            held = {str(p["symbol"]) for p in active_positions}
            signals = signals[~signals["symbol"].isin(held)]

            if not signals.empty:
                top_picks = signals.sort_values(
                    ["bounce_score", "vol_ratio", "rvol", "roc"], ascending=False
                ).head(free_slots)
                budget_per_slot = available_cash / free_slots

                for row in top_picks.itertuples(index=False):
                    buy_price = float(row.open)
                    shares = budget_per_slot / buy_price
                    available_cash -= budget_per_slot
                    sl_price = buy_price * (1 - SL_PCT)
                    day0_sl = float(row.low) <= sl_price

                    if day0_sl:
                        proceeds = shares * sl_price
                        profit = proceeds - budget_per_slot
                        available_cash += proceeds
                        trade_log.append({"symbol": row.symbol, "buy_date": current_date, "buy_price": buy_price,
                                           "shares": shares, "invested": budget_per_slot, "current_value": proceeds,
                                           "hold_days": 0, "bounce_score": float(row.bounce_score),
                                           "exit_date": current_date, "sell_price": sl_price, "result": "LOSS",
                                           "profit": profit, "pct_change": (sl_price - buy_price) / buy_price * 100})
                    else:
                        active_positions.append({"symbol": row.symbol, "buy_date": current_date, "buy_price": buy_price,
                                                  "shares": shares, "invested": budget_per_slot,
                                                  "current_value": shares * float(row.close), "hold_days": 0,
                                                  "bounce_score": float(row.bounce_score)})

        portfolio_value = available_cash + sum(float(p["current_value"]) for p in active_positions)
        equity_curve.append({"date": current_date, "capital": portfolio_value})

    equity_df = pd.DataFrame(equity_curve)
    trades_df = pd.DataFrame(trade_log)

    if equity_df.empty or trades_df.empty:
        return pd.DataFrame([{"min_bounce_score": min_bounce_score, "total_trades": 0,
                               "win_rate_pct": 0.0, "roi_pct": 0.0, "profit_factor": 0.0,
                               "max_drawdown_pct": 0.0, "avg_pct_change": 0.0}]), trades_df, equity_df

    final_capital = float(equity_df["capital"].iloc[-1])
    roi_pct = (final_capital / 100_000.0 - 1) * 100
    rolling_max = equity_df["capital"].cummax()
    drawdown = (equity_df["capital"] - rolling_max) / rolling_max * 100
    wins = trades_df[trades_df["profit"] > 0]
    losses = trades_df[trades_df["profit"] <= 0]
    gross_profit = float(wins["profit"].sum()) if not wins.empty else 0.0
    gross_loss = abs(float(losses["profit"].sum())) if not losses.empty else 0.0
    win_rate_pct = (len(wins) / len(trades_df) * 100) if not trades_df.empty else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0

    summary_df = pd.DataFrame([{
        "min_bounce_score": min_bounce_score,
        "total_trades": int(len(trades_df)),
        "win_rate_pct": round(win_rate_pct, 2),
        "final_capital": round(final_capital, 2),
        "roi_pct": round(roi_pct, 2),
        "profit_factor": round(profit_factor, 3),
        "max_drawdown_pct": round(float(drawdown.min()), 2),
        "avg_pct_change": round(float(trades_df["pct_change"].mean()), 2),
    }])
    return summary_df, trades_df, equity_df


def analyze_forward_returns_by_score(df: pd.DataFrame) -> pd.DataFrame:
    """
    วิธีที่ 2 — ไม่จำกัด MAX_POSITIONS=1 แบบ portfolio backtest
    แต่ดู "ทุกสัญญาณที่เกิดขึ้น" (ทุกแถวที่ passes_base_filter=True)
    แล้วเทียบ forward return ไปข้างหน้า N สัปดาห์ แยกตาม score bucket
    เพื่อตอบคำถาม "score >= 75 แล้ว bounce จริงในอดีตมั้ย" แบบไม่ติด constraint single position
    """
    print("\n📈 วิเคราะห์ Forward Return แยกตาม Score bucket (ไม่จำกัด 1 position) …")

    sig = df[df["passes_base_filter"]].copy()
    sig = sig.sort_values(["symbol", "date"]).reset_index(drop=True)

    # หา close ของ N สัปดาห์ข้างหน้า ต่อ symbol
    by_symbol = sig.groupby("symbol", sort=False, observed=True)
    HORIZON = 4  # 4 สัปดาห์ข้างหน้า (~1 เดือน)

    # ต้อง join กับ full df (ไม่ใช่แค่ sig) เพื่อหาราคาอนาคตจริง ไม่ใช่อนาคตของ "สัญญาณ" ครั้งต่อไป
    full_by_symbol = df.sort_values(["symbol", "date"])
    full_indexed = full_by_symbol.set_index(["symbol", "date"])["close"]

    def get_forward_return(row):
        future_date = row["date"] + pd.Timedelta(weeks=HORIZON)
        try:
            sym_data = full_by_symbol[full_by_symbol["symbol"] == row["symbol"]]
            future_rows = sym_data[sym_data["date"] >= future_date]
            if future_rows.empty:
                return np.nan
            future_close = future_rows.iloc[0]["close"]
            return (future_close / row["close"] - 1) * 100
        except Exception:
            return np.nan

    # เร็วกว่า: ใช้ shift กลับทาง (มองไปข้างหน้า N แถวของ symbol เดียวกัน)
    sig["fwd_close"] = by_symbol["close"].shift(-HORIZON)
    sig["fwd_return_pct"] = (sig["fwd_close"] / sig["close"] - 1) * 100
    sig = sig.dropna(subset=["fwd_return_pct"])

    # แบ่ง bucket
    bins = [0, 60, 65, 70, 75, 80, 85, 90, 101]
    labels = ["<60", "60-64", "65-69", "70-74", "75-79", "80-84", "85-89", "90+"]
    sig["score_bucket"] = pd.cut(sig["bounce_score"], bins=bins, labels=labels, right=False)

    result = sig.groupby("score_bucket", observed=True).agg(
        n_signals=("fwd_return_pct", "count"),
        win_rate_pct=("fwd_return_pct", lambda x: (x > 0).mean() * 100),
        loss_rate_pct=("fwd_return_pct", lambda x: (x < 0).mean() * 100),
        avg_fwd_return_pct=("fwd_return_pct", "mean"),
        median_fwd_return_pct=("fwd_return_pct", "median"),
        std_fwd_return_pct=("fwd_return_pct", "std"),
        max_drawdown_pct=("fwd_return_pct", "min"),       # การตกหนักสุดที่เคยเจอใน bucket นี้
        worst_5pct_avg_pct=("fwd_return_pct", lambda x: x.nsmallest(max(1, int(len(x)*0.05))).mean()),  # เฉลี่ย 5% ที่แย่ที่สุด
    ).round(2).reset_index()

    print(f"\n   Forward return หลังสัญญาณ {HORIZON} สัปดาห์ แยกตาม Bounce Score bucket:")
    print(result.to_string(index=False))

    result.to_csv("forward_return_by_score_bucket.csv", index=False)
    print(f"\n✅ บันทึก → forward_return_by_score_bucket.csv")
    return result


def main():
    df = load_base_data(INPUT_CSV)
    df = build_features(df)
    df = score_candidates(df)
    gc.collect()

    print(f"\n📊 Bounce Score distribution:")
    print(df["bounce_score"].describe())

    # ── รัน backtest แยกตาม score threshold ──
    score_buckets = [60, 65, 70, 75, 80, 85, 90]
    results = []

    print(f"\n🔄 รัน backtest แยกตาม min_bounce_score …\n")
    for score in score_buckets:
        summary, trades, equity = run_rule_backtest(df, min_bounce_score=score)
        row = summary.iloc[0].to_dict()
        results.append(row)
        print(f"  Score >= {score:>3}:  trades={row['total_trades']:>4}  "
              f"win_rate={row['win_rate_pct']:>6.2f}%  roi={row['roi_pct']:>7.2f}%  "
              f"profit_factor={row['profit_factor']:>5.3f}  avg_pct={row['avg_pct_change']:>6.2f}%")

    results_df = pd.DataFrame(results)
    results_df.to_csv("backtest_by_score_bucket.csv", index=False)
    print(f"\n✅ บันทึกผลเปรียบเทียบ → backtest_by_score_bucket.csv")

    # ── เก็บ trade log ของ score >= 75 ไว้ดูรายละเอียด ──
    summary75, trades75, equity75 = run_rule_backtest(df, min_bounce_score=75)
    summary75.to_csv("backtest_summary_score75.csv", index=False)
    trades75.to_csv("trades_score75.csv", index=False)
    equity75.to_csv("equity_score75.csv", index=False)
    print(f"✅ บันทึก trade log ของ score>=75 → trades_score75.csv ({len(trades75)} trades)")

    # ── วิธีที่ 2: forward return analysis (ตอบคำถามได้ตรงกว่า) ──
    analyze_forward_returns_by_score(df)


if __name__ == "__main__":
    main()