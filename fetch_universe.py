"""
fetch_universe.py — ดึงข้อมูลหุ้น US จาก TradingView แล้ว save เป็น filter_universe.json

ติดตั้ง:
    pip install tvdatafeed-enhanced websocket-client pandas ta

รัน:
    python fetch_universe.py                              # no-login, ดึง default symbols
    python fetch_universe.py -u EMAIL -p PASSWORD         # login TradingView (ข้อมูลครบกว่า)
    python fetch_universe.py --symbols AAPL MSFT TSLA     # ระบุ symbols เอง
    python fetch_universe.py --symbols-file symbols.csv   # โหลดรายชื่อจากไฟล์ (symbol,exchange)
    python fetch_universe.py --limit 10                   # ทดสอบแค่ 10 ตัวก่อน
    python fetch_universe.py --retries 5 --delay 2.0      # ปรับ retry และ delay เอง
"""

import argparse
import json
import math
import os
import time

import pandas as pd

try:
    import ta
    HAS_TA = True
except ImportError:
    HAS_TA = False
    print("⚠  ไม่พบ 'ta' — indicator บางตัวใช้ fallback (ติดตั้ง: pip install ta)")

try:
    from tvDatafeed import TvDatafeed, Interval
except ImportError:
    try:
        from tvdatafeed_enhanced import TvDatafeed, Interval
    except ImportError:
        raise SystemExit(
            "❌ ไม่พบ tvdatafeed\n"
            "   ติดตั้งด้วย: pip install tvdatafeed-enhanced websocket-client"
        )


# ── Symbol list เริ่มต้น ─────────────────────────────────
# แก้รายชื่อตรงนี้ได้เลย หรือใช้ --symbols / --symbols-file แทน
DEFAULT_SYMBOLS = [
    # Mega cap
    ("AAPL",  "NASDAQ"), ("MSFT",  "NASDAQ"), ("NVDA",  "NASDAQ"),
    ("GOOGL", "NASDAQ"), ("AMZN",  "NASDAQ"), ("META",  "NASDAQ"),
    ("TSLA",  "NASDAQ"), ("BRK.B", "NYSE"),   ("JPM",   "NYSE"),
    ("V",     "NYSE"),
    # Large cap tech
    ("AMD",   "NASDAQ"), ("INTC",  "NASDAQ"), ("AVGO",  "NASDAQ"),
    ("QCOM",  "NASDAQ"), ("MU",    "NASDAQ"), ("AMAT",  "NASDAQ"),
    ("LRCX",  "NASDAQ"), ("KLAC",  "NASDAQ"), ("MRVL",  "NASDAQ"),
    ("NFLX",  "NASDAQ"),
    # Finance
    ("GS",    "NYSE"),   ("MS",    "NYSE"),   ("BAC",   "NYSE"),
    ("WFC",   "NYSE"),   ("C",     "NYSE"),   ("AXP",   "NYSE"),
    # Healthcare
    ("JNJ",   "NYSE"),   ("UNH",   "NYSE"),   ("LLY",   "NYSE"),
    ("PFE",   "NYSE"),   ("ABBV",  "NYSE"),   ("MRK",   "NYSE"),
    # Consumer
    ("WMT",   "NASDAQ"),   ("COST",  "NASDAQ"), ("HD",    "NYSE"),
    ("MCD",   "NYSE"),   ("SBUX",  "NASDAQ"), ("NKE",   "NYSE"),
    # Energy
    ("XOM",   "NYSE"),   ("CVX",   "NYSE"),   ("COP",   "NYSE"),
    # ETFs
    ("SPY",   "AMEX"),   ("QQQ",   "NASDAQ"), ("IWM",   "AMEX"),
]

EXCHANGE_MAP = {"NASDAQ": "Q", "NYSE": "N", "AMEX": "A", "CBOE": "Z"}

ETF_SYMBOLS = {"SPY", "QQQ", "IWM", "GLD", "SLV", "TLT", "HYG", "EEM",
               "VTI", "VOO", "ARKK", "XLF", "XLE", "XLK", "XLV"}

# ── Retry / timing config ────────────────────────────────
# แก้ได้ที่นี่ หรือใช้ --retries / --delay / --batch-delay ใน command line
DEFAULT_RETRIES     = 3    # จำนวนครั้งที่ retry ต่อ symbol
DEFAULT_DELAY       = 0.3  # วิ หน่วงระหว่างแต่ละ symbol (ลดจาก 1.0 → 0.3)
DEFAULT_RETRY_DELAY = 3.0  # วิ หน่วงก่อน retry ครั้งแรก (x2 ทุกครั้ง = exponential backoff)
DEFAULT_BATCH_DELAY = 1.5  # วิ หน่วงเพิ่มทุก 10 symbols (ลดจาก 3.0 → 1.5)

# --fast mode: ไม่มี per-symbol delay เลย พัก batch สั้นลง
# ใช้เมื่อ connection ดี หรืออยากรันเร็ว
FAST_DELAY       = 0.0
FAST_BATCH_DELAY = 0.5


# ── คำนวณ indicators จาก OHLCV DataFrame ────────────────
def calc_indicators(df: pd.DataFrame) -> dict:
    close = df["close"]
    high  = df["high"]
    low   = df["low"]
    vol   = df["volume"]
    n     = len(df)

    def safe(val):
        if val is None:
            return None
        try:
            return None if (math.isnan(val) or math.isinf(val)) else round(float(val), 6)
        except Exception:
            return None

    r = {}

    # Price
    r["close"]  = safe(close.iloc[-1])
    r["open"]   = safe(df["open"].iloc[-1])
    r["high"]   = safe(high.iloc[-1])
    r["low"]    = safe(low.iloc[-1])
    r["volume"] = safe(vol.iloc[-1])
    r["date"]   = df.index[-1].strftime("%Y-%m-%d") if hasattr(df.index[-1], "strftime") else str(df.index[-1])

    # Returns
    def pct_ret(bars):
        if n <= bars:
            return None
        old = close.iloc[-(bars + 1)]
        return safe((close.iloc[-1] / old - 1) * 100) if old else None

    r["return_5d_pct"]    = pct_ret(5)
    r["return_20d_pct"]   = pct_ret(20)
    r["return_60d_pct"]   = pct_ret(60)
    r["price_change_pct"] = r["return_5d_pct"]

    # Volume
    avg_20 = vol.iloc[-20:].mean() if n >= 20 else vol.mean()
    avg_60 = vol.iloc[-60:].mean() if n >= 60 else vol.mean()
    r["avg_volume_20d"] = safe(avg_20)
    r["avg_volume_60d"] = safe(avg_60)
    r["vol_sma_20"]     = safe(avg_20)
    r["rvol"]           = safe(vol.iloc[-1] / avg_20) if avg_20 else None
    r["vol_ratio"]      = r["rvol"]
    r["vol_surge_int"]  = bool(r["rvol"] and r["rvol"] >= 2)

    # RSI
    if HAS_TA and n >= 15:
        r["rsi"] = safe(ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-1])
    else:
        delta = close.diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        rs    = gain / loss.replace(0, float("nan"))
        r["rsi"] = safe((100 - (100 / (1 + rs))).iloc[-1])

    # EMA 50
    if n >= 50:
        ema50 = close.ewm(span=50, adjust=False).mean()
        r["ema50"]      = safe(ema50.iloc[-1])
        r["dist_ema50"] = safe((close.iloc[-1] - ema50.iloc[-1]) / ema50.iloc[-1]) if ema50.iloc[-1] else None
        r["trend"]      = 1 if close.iloc[-1] > ema50.iloc[-1] else 0
    else:
        r["ema50"] = r["dist_ema50"] = r["trend"] = None

    # MACD
    if HAS_TA and n >= 26:
        r["macd_hist"] = safe(ta.trend.MACD(close).macd_diff().iloc[-1])
    elif n >= 26:
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        r["macd_hist"] = safe((macd_line - macd_line.ewm(span=9, adjust=False).mean()).iloc[-1])
    else:
        r["macd_hist"] = None

    # Stochastic %K
    if HAS_TA and n >= 14:
        r["stoch_k"] = safe(ta.momentum.StochasticOscillator(high, low, close).stoch().iloc[-1])
    elif n >= 14:
        low14  = low.rolling(14).min()
        high14 = high.rolling(14).max()
        r["stoch_k"] = safe(((close - low14) / (high14 - low14).replace(0, float("nan")) * 100).iloc[-1])
    else:
        r["stoch_k"] = None

    # ATR
    if HAS_TA and n >= 14:
        r["atr"] = safe(ta.volatility.AverageTrueRange(high, low, close).average_true_range().iloc[-1])
    elif n >= 2:
        prev = close.shift(1)
        tr   = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
        r["atr"] = safe(tr.rolling(14).mean().iloc[-1])
    else:
        r["atr"] = None
    r["atr_pct"] = safe(r["atr"] / close.iloc[-1] * 100) if r["atr"] and close.iloc[-1] else None

    # Bollinger Bands
    if HAS_TA and n >= 20:
        bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
        r["bb_upper"] = safe(bb.bollinger_hband().iloc[-1])
        r["bb_lower"] = safe(bb.bollinger_lband().iloc[-1])
        r["bb_width"] = safe(bb.bollinger_wband().iloc[-1])
    elif n >= 20:
        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        r["bb_upper"] = safe((sma20 + 2 * std20).iloc[-1])
        r["bb_lower"] = safe((sma20 - 2 * std20).iloc[-1])
        r["bb_width"] = safe(((4 * std20) / sma20).iloc[-1] * 100) if sma20.iloc[-1] else None
    else:
        r["bb_upper"] = r["bb_lower"] = r["bb_width"] = None

    r["close_to_bb_lower_pct"] = safe(
        (close.iloc[-1] - r["bb_lower"]) / r["bb_lower"] * 100
    ) if r["bb_lower"] else None

    # ROC
    def roc(p):
        if n <= p:
            return None
        old = close.iloc[-(p + 1)]
        return safe((close.iloc[-1] / old - 1) * 100) if old else None

    r["roc_10"] = roc(10)
    r["roc_3"]  = roc(3)

    # Volatility 20D annualised
    r["volatility_20d_ann_pct"] = safe(
        close.pct_change().iloc[-20:].std() * (252 ** 0.5) * 100
    ) if n >= 21 else None

    # Range 20D
    if n >= 20:
        h20 = high.iloc[-20:].max()
        l20 = low.iloc[-20:].min()
        r["range_20d_pct"]      = safe((h20 - l20) / l20 * 100) if l20 else None
        r["close_rank_pct_20d"] = safe((close.iloc[-1] - l20) / (h20 - l20)) if (h20 - l20) else None
    else:
        r["range_20d_pct"] = r["close_rank_pct_20d"] = None

    # Gap %
    r["gap_pct"] = safe(
        (df["open"].iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100
    ) if n >= 2 and close.iloc[-2] else None

    # Accel Momentum
    if n >= 7 and close.iloc[-4] and close.iloc[-7]:
        r["accel_momentum"] = safe(
            (close.iloc[-1] / close.iloc[-4] - 1) - (close.iloc[-4] / close.iloc[-7] - 1)
        )
    else:
        r["accel_momentum"] = None

    # Bounce Score — สูตรใหม่ (เหมือน build_web_datasets.py ของ wisarut)
    # คำนวณเป็น rule-based 0/1 แล้วรวมคะแนน max = 12
    rsi_v       = r["rsi"]            or 50
    rvol_v      = r["rvol"]           or 1
    trend_v     = r["trend"]          or 0
    macd_v      = r["macd_hist"]      or 0
    vol_ratio_v = r["vol_ratio"]      or 1
    roc_v       = r["return_5d_pct"]  or 0
    accel_v     = r["accel_momentum"] or 0
    dist_v      = r["dist_ema50"]     or 0
    bb_pos_v    = r["close_to_bb_lower_pct"] or 0
    stoch_v     = r["stoch_k"]        or 50
    close_v     = r["close"]          or 0
    ema50_v     = r["ema50"]          or 0

    liquidity_score  = int(vol_ratio_v >= 1.0) + int(rvol_v >= 1.0)               # max 2
    momentum_score   = int(roc_v >= 0) + int(macd_v >= 0) + int(accel_v >= 0)    # max 3
    trend_score_new  = int(trend_v >= 1) + int(close_v >= ema50_v)                # max 2
    bounce_zone      = (int(-0.08 <= dist_v <= 0.05)                              # max 3
                      + int(40 <= rsi_v <= 70)
                      + int(0.15 <= bb_pos_v <= 0.70))
    risk_control     = int(close_v >= 1.0) + int(stoch_v <= 85)                   # max 2

    bounce_raw = liquidity_score + momentum_score + trend_score_new + bounce_zone + risk_control
    bounce     = round((bounce_raw / 12.0) * 100, 1)

    r["bounce_score"]       = bounce
    r["momentum_score"]     = float(momentum_score)
    r["trend_score"]        = float(trend_score_new)
    r["liquidity_score"]    = float(liquidity_score)
    r["bounce_zone_score"]  = float(bounce_zone)
    r["risk_control_score"] = float(risk_control)

    # passes_base_filter — เงื่อนไขเหมือน wisarut
    r["passes_base_filter"] = bool(
        r["close"]    and r["close"]  >= 1.0 and
        r["rsi"]      and r["rsi"]    <= 75  and
        roc_v         >= 0                   and
        vol_ratio_v   >= 1.0
    )

    # highlight_rank & reason
    r["highlight_rank"]   = round(100 - bounce)
    reasons = []
    if rsi_v   < 35:       reasons.append("RSI_OVERSOLD")
    if rvol_v  >= 2:       reasons.append("VOL_SURGE")
    if trend_v == 1:       reasons.append("ABOVE_EMA50")
    if macd_v  > 0:        reasons.append("MACD_POSITIVE")
    r["highlight_reason"] = "|".join(reasons)

    # Metadata
    r["history_rows"] = n
    r["first_date"]   = df.index[0].strftime("%Y-%m-%d") if hasattr(df.index[0], "strftime") else str(df.index[0])
    r["last_date"]    = r["date"]

    # price_history: ราคาจริง 60 วันย้อนหลัง สำหรับกราฟใน EPS tab
    r["price_history"] = [
        {"date": idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx),
         "close": safe(row["close"])}
        for idx, row in df.iloc[-60:].iterrows()
        if safe(row["close"]) is not None
    ]

    return r


# ── ดึงข้อมูล 1 symbol พร้อม retry + exponential backoff ──
def fetch_symbol(
    tv: TvDatafeed,
    symbol: str,
    exchange: str,
    n_bars: int = 200,
    max_retries: int = DEFAULT_RETRIES,
    retry_delay: float = DEFAULT_RETRY_DELAY,
) -> dict | None:
    """
    ดึงข้อมูล 1 symbol จาก TradingView
    - retry สูงสุด max_retries ครั้งเมื่อเกิด WebSocket error
    - delay เพิ่มเป็น 2x ทุก attempt (exponential backoff)
      attempt 1 fail → รอ 3s
      attempt 2 fail → รอ 6s
      attempt 3 fail → skip
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            df = tv.get_hist(symbol, exchange, interval=Interval.in_daily, n_bars=n_bars)

            # tvdatafeed บางครั้ง return None แทนที่จะ raise exception
            # เมื่อ WebSocket หลุด — ต้อง retry เหมือนกัน
            if df is None or df.empty:
                raise ValueError("tvdatafeed returned None/empty (likely WebSocket drop)")

            df.columns = [c.lower() for c in df.columns]
            df = df.dropna(subset=["close"])

            row = calc_indicators(df)
            row["symbol"]           = symbol
            row["Listing Exchange"] = EXCHANGE_MAP.get(exchange.upper(), exchange.upper()[0])
            row["ETF"]              = "Y" if symbol.upper() in ETF_SYMBOLS else "N"
            row["Security Name"]    = symbol
            return row  # สำเร็จ

        except Exception as e:
            last_error = e
            is_last_attempt = attempt == max_retries - 1

            if is_last_attempt:
                print(f"  ✗ {symbol}: ล้มเหลวหลัง {max_retries} attempts ({type(e).__name__})")
            else:
                wait = retry_delay * (2 ** attempt)
                print(f"\n    ⚠ {symbol} attempt {attempt + 1}/{max_retries}: {type(e).__name__} — retry ใน {wait:.0f}s…", end="", flush=True)
                time.sleep(wait)

    return None


# ── Main ────────────────────────────────────────────────
def run(args):
    tv = TvDatafeed(username=args.username, password=args.password) \
        if (args.username and args.password) \
        else TvDatafeed()

    # ── โหลด symbol list ──
    if args.symbols:
        symbol_list = [(s.upper(), "NASDAQ") for s in args.symbols]
    elif args.symbols_file:
        symbol_list = []
        with open(args.symbols_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(",")
                symbol_list.append((
                    parts[0].strip().upper(),
                    parts[1].strip().upper() if len(parts) > 1 else "NASDAQ",
                ))
    else:
        symbol_list = DEFAULT_SYMBOLS

    if args.limit:
        symbol_list = symbol_list[:args.limit]

    # ── ใช้ fast mode ถ้า --fast ──
    delay       = FAST_DELAY       if args.fast else args.delay
    batch_delay = FAST_BATCH_DELAY if args.fast else args.batch_delay

    total = len(symbol_list)
    est_min = (total * delay + (total // 10) * batch_delay) / 60
    mode_label = "⚡ fast" if args.fast else "normal"
    print(f"\n📋 ดึงข้อมูล {total} symbols…  [{mode_label}]")
    print(f"   delay={delay}s/symbol  |  batch_delay={batch_delay}s/10  |  retry={args.retries}x (backoff {args.retry_delay}s)")
    print(f"   ⏱ ประมาณ {est_min:.1f} นาที (ไม่รวม retry)\n")

    results, errors = [], []

    for i, (sym, exch) in enumerate(symbol_list, 1):
        print(f"  [{i:>4}/{total}] {sym:<12} ({exch})", end="", flush=True)

        row = fetch_symbol(
            tv, sym, exch,
            n_bars=args.n_bars,
            max_retries=args.retries,
            retry_delay=args.retry_delay,
        )

        if row:
            results.append(row)
            flag = "✓" if row.get("passes_base_filter") else "·"
            print(f"  {flag}  bounce={row.get('bounce_score', 0):.1f}  rsi={row.get('rsi') or '—'}")
        else:
            errors.append(sym)
            # error message ถูก print ใน fetch_symbol แล้ว

        # delay ระหว่าง symbol — ป้องกัน rate limit
        if delay > 0:
            time.sleep(delay)

        # พักหนักขึ้นทุก 10 symbols
        if i % 10 == 0 and i < total:
            print(f"\n   ⏸ พัก {batch_delay}s หลังจาก {i} symbols…\n")
            time.sleep(batch_delay)

    # ── สรุปผล ──
    success_rate = len(results) / total * 100 if total else 0
    print(f"\n{'='*55}")
    print(f"✅ ได้ข้อมูล {len(results)}/{total} symbols ({success_rate:.0f}%)  |  error: {len(errors)}")
    if errors:
        print(f"   ไม่ได้ข้อมูล: {', '.join(errors)}")
    print(f"{'='*55}")

    results.sort(key=lambda r: r.get("highlight_rank", 9999))

    # ── save ──
    out_path = args.output
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n💾 บันทึกแล้ว → {out_path}  ({len(results)} rows)")
    if results:
        print(f"   วันที่ล่าสุด: {results[0].get('date', '?')}")
    print("\n🌐 เปิดเว็บ:  python -m http.server 8080")
    print("   แล้วไปที่:  http://localhost:8080/Us_Surge_Webpage.html")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="ดึงข้อมูลหุ้น US จาก TradingView แล้ว save เป็น filter_universe.json"
    )
    parser.add_argument("--username",    "-u",  default=os.environ.get("TV_USER"))
    parser.add_argument("--password",    "-p",  default=os.environ.get("TV_PASS"))
    parser.add_argument("--symbols",           nargs="+", metavar="SYM")
    parser.add_argument("--symbols-file",      metavar="FILE")
    parser.add_argument("--limit",       type=int,   default=0,                    help="จำกัดจำนวน symbols (0 = ไม่จำกัด)")
    parser.add_argument("--n-bars",      type=int,   default=200,                  help="จำนวน bars ต่อ symbol (default: 200)")
    parser.add_argument("--output",      "-o",       default="filter_universe.json")
    parser.add_argument("--retries",     type=int,   default=DEFAULT_RETRIES,      help=f"จำนวน retry ต่อ symbol (default: {DEFAULT_RETRIES})")
    parser.add_argument("--delay",       type=float, default=DEFAULT_DELAY,        help=f"วิ หน่วงระหว่างแต่ละ symbol (default: {DEFAULT_DELAY})")
    parser.add_argument("--retry-delay", type=float, default=DEFAULT_RETRY_DELAY,  help=f"วิ หน่วงก่อน retry ครั้งแรก (x2 ต่อ attempt) (default: {DEFAULT_RETRY_DELAY})")
    parser.add_argument("--batch-delay", type=float, default=DEFAULT_BATCH_DELAY,  help=f"วิ พักเพิ่มทุก 10 symbols (default: {DEFAULT_BATCH_DELAY})")
    parser.add_argument("--fast",        action="store_true",                       help="ไม่มี per-symbol delay เลย เร็วสุด แต่อาจ error มากขึ้น")
    args = parser.parse_args()
    run(args)