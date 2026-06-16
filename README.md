# StockSurge — US Equity Screener

เว็บแอปสำหรับ screen หุ้น US ดูข้อมูล technical, EPS, ผล backtest, ความสัมพันธ์ระหว่างหุ้น (Relations/Graph) และ Watchlist ส่วนตัว ตัวแอปอยู่ในไฟล์ HTML ไฟล์เดียว ไม่มี build step ไม่มี framework ไม่ต้อง install อะไรเพิ่ม

---

## Changelog

| Version | วันที่ | สิ่งที่เปลี่ยน |
|---|---|---|
| v2.0 | 2026-06 | เพิ่ม Relations tab (vis-network), Graph tab (d3 + Sentiment mode), Watchlist (localStorage), Symbol search, Market strip 4 modes, merge_universe.py |
| v1.2 | 2026-06-05 | เพิ่ม `fetch_universe.py` ดึงราคาจริงจาก TradingView ผ่าน tvdatafeed — กราฟ EPS tab ใช้ `price_history` array จริงแทนการคำนวณจาก % return |
| v1.1 | 2026-06-04 | ลบคอลัมน์ Prev Year และ YoY Chg $ ออกจาก EPS table เหลือแค่ YoY Chg % / เพิ่มวันที่จริงใน x-axis กราฟ EPS |
| v1.0 | 2026-06-02 | Initial release — Screener, Stats, EPS, Backtest tabs |

---

## รันโปรเจคนี้ยังไง

### ขั้นที่ 1 — ดึงข้อมูลล่าสุด (ทุกวันที่อยากอัปเดต)

```bash
# ติดตั้ง dependencies (ครั้งแรกเท่านั้น)
pip install tvdatafeed-enhanced websocket-client pandas ta

# รัน script ดึงข้อมูล 44 หุ้นหลักจาก TradingView
python fetch_universe.py

# merge เข้ากับ universe ทั้งตลาด (filter_universe_base.json)
python merge_universe.py
```

### ขั้นที่ 2 — เปิดเว็บ

ต้องเสิร์ฟผ่าน HTTP เท่านั้น (เปิดไฟล์ตรงๆ ใน browser จะ fetch ไม่ได้เพราะ CORS)

```bash
python -m http.server 8080
```

แล้วเปิด `http://localhost:8080/Us_Surge_Webpage.html`

---

## โครงสร้างไฟล์

```
📁 project/
  ├── Us_Surge_Webpage.html       ← ตัวแอปทั้งหมด (HTML + CSS + JS ไฟล์เดียว)
  ├── graph.html                  ← Obsidian-style stock relationship graph (d3 canvas)
  ├── fetch_universe.py           ← ดึงข้อมูล 44 หุ้นหลักจาก TradingView
  ├── merge_universe.py           ← รวม filter_universe.json (44 หุ้น) เข้ากับ base (ทั้งตลาด)
  ├── filter_universe.json        ← ข้อมูลหุ้นที่ใช้งานจริง (44 หุ้น + ทั้งตลาดหลัง merge)
  ├── filter_universe_base.json   ← ข้อมูลทั้งตลาด ~11,264 หุ้น จาก data sci pipeline
  ├── relations.json              ← Suppliers/Customers/Competitors ของ 36 หุ้น Nasdaq 100
  ├── eps_latest.json             ← ข้อมูล EPS แยก (fallback ถ้าไม่ embed ใน universe)
  ├── backtest_summary.csv        ← สรุปผล backtest 1 แถว
  ├── backtest_trades.csv         ← log การซื้อขายแต่ละ trade
  └── backtest_equity_curve.csv   ← equity curve รายวัน
```

> **หมายเหตุ:** `watchlist.json` ไม่ต้องมีในไฟล์ — ข้อมูล Watchlist เก็บใน browser `localStorage` ของแต่ละคน

---

## fetch_universe.py — วิธีใช้งาน

ดึง OHLCV รายวันจาก TradingView คำนวณ indicator + Bounce Score แล้ว save เป็น `filter_universe.json`

```bash
# no-login (ฟรี แต่ข้อมูลอาจจำกัด)
python fetch_universe.py

# login TradingView (ข้อมูลครบกว่า)
python fetch_universe.py -u อีเมล -p รหัสผ่าน

# ระบุ symbols เอง
python fetch_universe.py --symbols AAPL MSFT TSLA NVDA

# ทดสอบแค่ 5 ตัวก่อน
python fetch_universe.py --limit 5

# fast mode (ไม่มี delay ระหว่าง symbol)
python fetch_universe.py --fast
```

**Bounce Score** คำนวณแบบ rule-based 0/1 รวมคะแนนเต็ม 12 แบ่งเป็น 5 กลุ่ม: Liquidity (vol_ratio, rvol), Momentum (roc, macd, accel), Trend (above EMA50), Bounce Zone (RSI 40-70, dist EMA50, BB position), Risk Control (price, stoch_k) — สูตรเดียวกับ pipeline ของทีม data sci

---

## merge_universe.py — วิธีใช้งาน

รวมข้อมูล 44 หุ้นล่าสุดเข้ากับ universe ทั้งตลาด โดยใช้ข้อมูลที่ใหม่กว่าเสมอ

```bash
python merge_universe.py              # ใช้ default paths
python merge_universe.py --dry-run    # ดูผลโดยไม่ save จริง
```

ก่อนรันครั้งแรกต้องมี `filter_universe_base.json` (ข้อมูลทั้งตลาดจาก data sci pipeline) อยู่ในโฟลเดอร์เดียวกัน

---

## Tab ต่างๆ ในเว็บ

### Screener
ตารางหลัก มี search box ค้นหา symbol ได้ทันที (`startsWith`), filter bar 6 dropdown (Price, Exchange, Type, Signal, Bounce Score, Technicals), Market strip ด้านบนเลือกได้ 4 modes (ดัชนีตลาด / Top Picks / Volume Surge / RSI Oversold) กดที่หุ้นใน Market strip เพื่อ jump ไปดูในตารางได้เลย

กดที่แถวไหน → expand ดู Momentum, Volatility, Volume, Returns, Highlight Reasons แบบละเอียด

กดปุ่ม ⭐ ท้ายแถว → เพิ่ม/ลบจาก Watchlist

### Stats / EPS / Backtest
อยู่ในแถบเดียวกันกับ Screener — Stats แสดง technical indicators ครบ, EPS แสดงกำไรต่อหุ้นพร้อมกราฟเทียบราคา, Backtest แสดงผลทดสอบ strategy (KPI, equity curve, trade log)

### Relations (อยู่บน nav bar)
ค้นหาหุ้น → เห็น interactive graph (vis-network) พื้นหลังดำ แสดง Suppliers/Customers/Competitors พร้อมขอบสีเขียว/แดงตาม %Chg วันนั้น คลิกดู popup รายละเอียด ดับเบิลคลิกเพื่อ navigate ไปหุ้นอื่น

### Graph (อยู่บน nav bar)
Obsidian-style graph ทั้งตลาด Nasdaq 100 (62 หุ้น, 353 relationships) มี 2 mode หลัก (Direct/Cluster) และ Sentiment mode ที่ระบายสี node ตาม %Chg — เลือก filter "เขียวตาม"/"แดงตาม" เพื่อดูว่าหุ้นที่เชื่อมกับหุ้นที่สนใจไปทางเดียวกันมั้ย

### ⭐ Watchlist (อยู่บน nav bar)
เพิ่มหุ้นที่สนใจ ตั้ง note ส่วนตัว ดู alert เมื่อ Bounce Score ขึ้นถึงเกณฑ์ ข้อมูลเก็บใน `localStorage` ของ browser (ไม่ sync ข้ามเครื่อง/คน) — มีปุ่ม Export JSON สำรองข้อมูลได้

---

## Schema ของข้อมูล

### filter_universe.json
รองรับทั้ง JSON array และ CSV — `loadData()` detect อัตโนมัติ `normalizeRow()` แปลง field ใหม่ให้ตรง schema ที่ UI ใช้ (เช่น `latest_close` → `close`)

Field สำคัญ: `symbol`, `close`, `price_change_pct`, `volume`, `rvol`, `rsi`, `bounce_score`, `passes_base_filter`, `highlight_rank`, `price_history` (array ราคาจริง 60 วันสำหรับ sparkline/EPS chart)

### relations.json
```json
{
  "NVDA": {
    "suppliers":   [{"symbol": "ASML", "market": "EU"}, ...],
    "customers":   [{"symbol": "MSFT", "market": "US"}, ...],
    "competitors": [{"symbol": "AMD",  "market": "US"}, ...]
  }
}
```

### backtest files
- **summary**: `strategy_name`, `start_date`, `end_date`, `total_trades`, `win_rate_pct`, `final_capital`, `roi_pct`, `profit_factor`, `max_drawdown_pct`
- **trades**: `symbol`, `buy_date`, `buy_price`, `exit_date`, `sell_price`, `shares`, `profit`, `pct_change`, `result`
- **equity_curve**: `date`, `capital`

---

## สิ่งที่ยังไม่เสร็จ / TODO

| Feature | สถานะ |
|---|---|
| เส้น S&P 500 ใน Equity Curve | ❌ ยัง random — ต้องการ SPY price_history ย้อนหลังเต็มช่วง backtest |
| `eps_history` รายไตรมาส | ❌ ยังไม่มีจาก pipeline — chart ใช้ 2 จุด prev/curr แทน |
| Market Cap, P/E, EPS Estimate | ❌ ไม่มีใน data ปัจจุบัน |
| Relations/Graph ครอบคลุมหุ้นมากกว่า 36/62 ตัว | ❌ ต้องขยาย dataset เพิ่ม |
| filter_universe_base.json ล่าสุด | ⚠️ รอ data sci รัน pipeline ใหม่ (ปัจจุบันข้อมูล 2026-05-12) |

---

## สิ่งที่ต้องรู้ก่อนแก้โค้ด

- **เพิ่ม tab ใหม่** → เพิ่ม nav link + ctab (ถ้าต้องการ) + view div + แก้ `setTab()`/`navTo()` ให้ซ่อน/แสดง view ที่ถูกต้อง
- **แก้ filter** → แก้ใน `applyAll()` function เดียว แล้ว update `getChecked()` ถ้าเพิ่ม dropdown ใหม่
- **แก้ schema** → แก้ `normalizeRow()` ให้รับ field ใหม่ แล้วตรวจว่า render functions ใช้ field ชื่อถูกต้อง
- **Watchlist ใช้ localStorage** → ไม่มี backend, ไม่ sync ข้ามคน/เครื่อง ถ้าต้องการแชร์ทีมต้องเปลี่ยนเป็น Supabase หรือ backend อื่น
- **graph.html เป็น iframe แยก** — โหลดผ่าน `loadGraphTab()` ครั้งแรกที่กด tab Graph เท่านั้น ไม่ reload ซ้ำ
- **ไม่ต้อง npm install** — ไม่มี dependency ใดๆ แก้ไฟล์ HTML แล้ว refresh browser ได้เลย