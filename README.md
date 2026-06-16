# StockSurge — US Equity Screener

เว็บแอปสำหรับ screen หุ้น US ดูข้อมูล technical, EPS และผล backtest ทั้งหมดอยู่ในไฟล์ HTML ไฟล์เดียว ไม่มี build step ไม่มี framework ไม่ต้อง install อะไรเพิ่ม

---

## Changelog

| Version | วันที่ | สิ่งที่เปลี่ยน |
|---|---|---|
| v1.2 | 2026-06-05 | เพิ่ม `fetch_universe.py` ดึงราคาจริงจาก TradingView ผ่าน tvdatafeed — กราฟ EPS tab ใช้ `price_history` array จริงแทนการคำนวณจาก % return |
| v1.1 | 2026-06-04 | ลบคอลัมน์ Prev Year และ YoY Chg $ ออกจาก EPS table เหลือแค่ YoY Chg % / เพิ่มวันที่จริงใน x-axis กราฟ EPS / EPS Latest แสดง +/- เทียบปีก่อนในวงเล็บ |
| v1.0 | 2026-06-02 | Initial release — Screener, Stats, EPS, Backtest tabs |

---

## รันโปรเจคนี้ยังไง

### ขั้นที่ 1 — ดึงข้อมูลล่าสุด (ต้องทำก่อนครั้งแรก)

```bash
# ติดตั้ง dependencies
pip install tvdatafeed-enhanced websocket-client pandas ta

# รัน script ดึงข้อมูล (จะ save ทับ filter_universe.json อัตโนมัติ)
python fetch_universe.py

# ถ้ามี TradingView account จะได้ข้อมูลครบกว่า
python fetch_universe.py --user อีเมล --pass รหัสผ่าน
```

### ขั้นที่ 2 — เปิดเว็บ

ต้องเสิร์ฟผ่าน HTTP เท่านั้น (เปิดไฟล์ตรงๆ ใน browser จะ fetch ไม่ได้เพราะ CORS)

```bash
# Python
python -m http.server 8080

# Node
npx serve .
```

จากนั้นเปิด `http://localhost:8080/Us_Surge_Webpage.html`

---

## โครงสร้างไฟล์

```
📁 project/
  ├── Us_Surge_Webpage.html         ← ตัวแอปทั้งหมด (HTML + CSS + JS ไฟล์เดียว)
  ├── fetch_universe.py             ← script ดึงข้อมูลจาก TradingView → save filter_universe.json
  ├── filter_universe.json          ← ข้อมูลหุ้น (generate จาก fetch_universe.py)
  ├── eps_latest.json               ← ข้อมูล EPS แยก (ถ้าไม่ embed ไว้ใน universe)
  ├── backtest_summary.csv          ← สรุปผล backtest 1 แถว
  ├── backtest_trades.csv           ← log การซื้อขายแต่ละ trade
  └── backtest_equity_curve.csv     ← equity curve รายวัน
```

> **หมายเหตุ:** `stock_stats.csv` และ `top_highlights.csv` ไม่ได้ถูกโหลดโดย HTML ลบออกได้

---

## fetch_universe.py — วิธีใช้งาน

script นี้ดึง OHLCV รายวันจาก TradingView คำนวณ indicator ทุกตัว แล้ว save เป็น `filter_universe.json` ให้เว็บโหลดต่อได้เลย

### 1. ติดตั้ง dependencies

```bash
pip install tvdatafeed-enhanced websocket-client pandas ta
```

### 2. เตรียมรายชื่อหุ้น

**แบบ A — ใช้ default list** (50 symbols ที่กำหนดไว้ใน script แล้ว)
ไม่ต้องทำอะไรเพิ่ม รันได้เลย

**แบบ B — ระบุ symbols เองใน command line**
```bash
python fetch_universe.py --symbols AAPL MSFT TSLA NVDA
```

**แบบ C — โหลดจากไฟล์ CSV**
สร้างไฟล์ `symbols.csv` ฟอร์แมต `symbol,exchange` แถวละตัว:
```
AAPL,NASDAQ
JPM,NYSE
SPY,AMEX
```
แล้วรัน:
```bash
python fetch_universe.py --symbols-file symbols.csv
```

### 3. รัน script

```bash
# no-login (ฟรี แต่ข้อมูลอาจจำกัด)
python fetch_universe.py

# login TradingView (ข้อมูลครบกว่า)
python fetch_universe.py -u อีเมล -p รหัสผ่าน

# ทดสอบแค่ 5 ตัวก่อน
python fetch_universe.py --limit 5
```

ระหว่างรันจะเห็น progress ทีละ symbol:
```
[   1/50] AAPL         (NASDAQ)  ✓  bounce=72.3  rsi=58.4
[   2/50] MSFT         (NASDAQ)  ✓  bounce=68.1  rsi=54.2
...
💾 บันทึกแล้ว → filter_universe.json  (50 rows)
🌐 เปิดเว็บ:  python -m http.server 8080
```

### 4. เปิดเว็บ

```bash
python -m http.server 8080
```
แล้วไปที่ `http://localhost:8080/Us_Surge_Webpage.html`

> **หมายเหตุ:**
> - Bounce Score เป็น simplified version — Data Sci team ควรแทนที่ด้วย model จริง
> - tvdatafeed ไม่มีข้อมูล EPS ต้องใช้ `eps_latest.json` แยกต่างหากเหมือนเดิม
> - ถ้าจะอัปเดตข้อมูลใหม่ รัน script ซ้ำได้เลย จะ save ทับไฟล์เดิมอัตโนมัติ

---

## โครงสร้างโค้ดใน `Us_Surge_Webpage.html`

ไฟล์แบ่งออกเป็น 3 ส่วนหลักตามลำดับ:

### 1. CSS (~450 บรรทัด)
อยู่ใน `<style>` tag ส่วนบน ใช้ CSS custom properties (variables) ทั้งหมด เช่น `--bg`, `--accent`, `--green` ฯลฯ ทำให้แก้ theme ได้ที่จุดเดียว ไม่มี external CSS framework

สิ่งที่ style ไว้แยกเป็น block ชัดเจน:
- **NAV** — navbar ด้านบน (fixed)
- **FILTER BAR** — แถบ filter ใต้ nav (sticky) + dropdown
- **TABLE** — ตารางหุ้นทุก tab
- **EPS** — summary cards + expand panel
- **BACKTEST** — KPI cards + equity chart + trade log
- **PAGINATION, TOAST, LOADING** — UI components เล็กๆ

### 2. HTML (~300 บรรทัด)
อยู่ใน `<body>` แบ่งเป็น:

- **Loading overlay** (`#loadingEl`) — spinner ที่แสดงระหว่างโหลดข้อมูล
- **Nav** — โลโก้ + links (Screener / Backtest) + ปุ่ม
- **Filter bar** — 6 dropdown pills: Price, Exchange, Type, Signal, Bounce Score, Technicals
- **Main content** — market strip + tab switcher + 4 tab views:
  - `#vS` — Screener tab
  - `#vSt` — Stats tab
  - `#vEps` — EPS tab
  - `#vBt` — Backtest tab

### 3. JavaScript (~1,300 บรรทัด)
อยู่ใน `<script>` tag ท้ายไฟล์ ไม่มี external library ทั้งหมดเขียน vanilla JS

---

## Flow การทำงานของ JavaScript

```
loadData()
  │
  ├─ fetch filter_universe.json
  │     └─ normalizeRow()  ← แปลง field ให้ตรง schema ภายใน
  │
  ├─ สร้าง EPS_LIVE object จาก embedded EPS fields (ถ้ามี)
  │     └─ fallback: fetch eps_latest.json
  │
  ├─ fetch backtest_summary / trades / equity_curve (parallel)
  │
  ├─ updateFeatureVisibility()  ← ซ่อน EPS tab / Backtest nav ถ้าข้อมูลไม่ครบ
  │
  └─ renderScreener()  ← แสดงผลครั้งแรก
```

เมื่อ user กดปุ่ม Apply Filters:
```
applyAll()
  ├─ อ่านค่าจาก dropdown ทุกตัว
  ├─ filter ALL_DATA → FILTERED
  ├─ sort ตาม sortKey / sortDir
  └─ render tab ที่ active อยู่
```

---

## แต่ละ Tab ทำอะไร

### Screener (`renderScreener`)
ตารางหลัก แสดงหุ้นทั้งหมดใน `FILTERED` แบบ paginate (20 แถวต่อหน้า) คอลัมน์: Symbol, Price, %Chg, Volume, RVOL, RSI, Bounce Score, Signal, 30D Trend

**กดที่แถว** → `toggleExpand()` แสดง panel ใต้แถวนั้น มี 5 section: Momentum, Volatility, Volume, Returns, Highlight Reasons

**Bounce Score** คือคะแนนรวม 0–100 ที่ data pipeline คำนวณมา Signal มาจากคะแนนนี้:
- ≥ 90 = Strong Buy
- ≥ 75 = Buy
- ≥ 58 = Neutral
- < 58 = Sell

### Stats (`renderStats`)
ตารางเดียวกันแต่แสดง column technical เพิ่มเติม เช่น MACD Hist, Stoch %K, ATR, Vol Ratio, Return 20D/60D ฯลฯ แสดงแค่ 100 แถวแรกเพื่อ performance

### EPS (`renderEps`)
แสดงเฉพาะหุ้นที่มีข้อมูล EPS ใน `EPS_LIVE` ด้านบนมี summary cards 4 ใบ (YoY Improved Rate, Avg YoY Growth, Positive EPS count, Negative EPS count) ตารางมี 7 คอลัมน์: Symbol, Company, EPS Latest, YoY Chg%, Trend, Period, Report Date

**กดที่แถว** → `toggleEpsExpand()` แสดง dual-axis chart — เส้น EPS (left axis) เทียบกับราคาหุ้นจริงจาก `price_history` (right axis) พร้อม metrics breakdown

Tab นี้ซ่อนอัตโนมัติถ้าไม่มีข้อมูล EPS เลย

### Backtest (`renderBacktest`)
แสดงผลการทดสอบ strategy จากไฟล์ backtest ประกอบด้วย KPI cards (Total Return, Win Rate, Profit Factor, Max Drawdown, ROI), equity curve SVG chart เทียบกับ S&P 500 และ trade log ทุก trade

Tab และ nav link ซ่อนอัตโนมัติถ้าไฟล์ backtest ไม่โหลด

---

## Filter Bar ทำงานยังไง

Filter bar มี dropdown 6 ตัว แต่ละตัวเป็น `position:fixed` (ไม่ใช่ absolute) เพราะ parent มี `overflow-x:auto` ทำให้ dropdown ปกติโดน clip — ใช้ `positionDD()` คำนวณ position จาก `getBoundingClientRect()` แทน

เมื่อกด Apply → `applyAll()` รวม filter ทุกตัวในครั้งเดียวแล้ว set `FILTERED` ใหม่ ไม่มี state filter แยกรายตัว ทุกอย่างอ่านจาก DOM ตรงๆ ทุกครั้ง

---

## Schema ของข้อมูล

### filter_universe (ไฟล์หลัก)
รองรับทั้ง JSON array และ CSV — `loadData()` detect อัตโนมัติจาก character แรก

`normalizeRow()` ทำหน้าที่แปลง field ใหม่ให้ตรง schema ที่ UI ใช้ เช่น:
- `latest_close` → `close`
- `return_5d_pct` → `price_change_pct`
- `last_date` → `date`

Field สำคัญที่ UI ใช้: `symbol`, `close`, `price_change_pct`, `volume`, `rvol`, `rsi`, `bounce_score`, `passes_base_filter`, `highlight_rank`, `highlight_reason`, `Security Name`, `Listing Exchange`, `ETF`

Field ใหม่ที่เพิ่มโดย `fetch_universe.py`:
- `price_history` — array ราคาจริงรายวัน 60 วัน `[{date, close}, ...]` ใช้วาดกราฟใน EPS tab

EPS อาจ embed ตรงในไฟล์นี้ก็ได้ (ถ้ามี field `eps_data_available`) จะไม่โหลด `eps_latest.json` แยก

### eps_latest (ไฟล์เสริม)
โหลดเฉพาะเมื่อ universe ไม่มี EPS embed เก็บเป็น object keyed by symbol ใน `EPS_LIVE`

Field ที่ใช้: `eps_latest`, `eps_prev_year`, `eps_yoy_change_pct`, `eps_qoq_change_pct`, `eps_report_date`, `fiscal_period`, `eps_positive`, `eps_yoy_improved`, `eps_qoq_improved`, `eps_history` (optional array)

### backtest files
- **summary**: `strategy_name`, `start_date`, `end_date`, `tp_pct`, `sl_pct`, `max_hold_days`, `max_positions`, `total_trades`, `win_rate_pct`, `final_capital`, `roi_pct`, `profit_factor`, `max_drawdown_pct`
- **trades**: `symbol`, `buy_date`, `buy_price`, `exit_date`, `sell_price`, `shares`, `profit`, `pct_change`, `result`
- **equity_curve**: `date`, `capital`

Loader ลอง `.json` ก่อน ถ้าไม่มีค่อยลอง `.csv` อัตโนมัติ

---

## เชื่อม Backend (เมื่อพร้อม)

ตอนนี้ทุกอย่าง fetch จากไฟล์ local ใน `loadData()` พอมี API จริงแค่เปลี่ยน URL ใน function เดียวกัน:

```javascript
// ปัจจุบัน
const res = await fetch('filter_universe.json');

// เปลี่ยนเป็น
const res = await fetch('https://api.example.com/universe');
```

Field names ต้องตรงกับที่ `normalizeRow()` expect หรือแก้ normalizer ให้รับ schema ใหม่

---

## สิ่งที่ยังไม่เสร็จ / TODO

| Feature | สถานะ |
|---|---|
| กราฟ 30D จริงใน Screener | ❌ ยังเป็น random sparkline — `price_history` มีอยู่แล้วใน JSON แต่ยังไม่ได้ wire เข้า Screener |
| `eps_history` รายไตรมาส | ❌ ยังไม่มีจาก pipeline — chart ใช้ 2 จุด prev/curr แทน |
| Market strip (S&P, Nasdaq) | ❌ ยัง hardcode ใน HTML — ยังไม่ wired กับข้อมูลจริง |
| Market Cap, P/E, EPS Estimate | ❌ ไม่มีใน data ปัจจุบัน |
| Watchlist tab | ❌ ยังไม่มี feature นี้ |

---

## สิ่งที่ต้องรู้ก่อนแก้โค้ด

- **เพิ่ม column ใน EPS table** → ต้องแก้ `<th>` ใน HTML + row builder ใน `renderEps()` + `colspan` ใน expand row (ปัจจุบัน = 7)
- **แก้ filter** → แก้ใน `applyAll()` function เดียว แล้ว update `getChecked()` ถ้าเพิ่ม dropdown ใหม่
- **แก้ schema** → แก้ `normalizeRow()` ให้รับ field ใหม่ แล้วตรวจว่า render functions ใช้ field ชื่อถูกต้อง
- **ระวัง EPS event delegation** → `tbody.onclick` ถูก re-assign ทุกครั้งที่ `renderEps()` รัน เพราะ `innerHTML =` ล้าง listener เก่า
- **ไม่ต้อง npm install** — ไม่มี dependency ใดๆ แก้ไฟล์ HTML แล้ว refresh browser ได้เลย