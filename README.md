# Quotex Historical Candle Data Downloader (Python)

**Download unlimited Quotex historical candle data via Python — bypass the 199-candle WebSocket limit.**

> Built on top of [pyquotex](https://github.com/cleitonleonel/pyquotex). This repo patches it to remove the hard cap and adds a `get_candles_deep()` method that fetches **thousands of OHLC candles** in a single call — days, weeks, or months at a time.

---

## Why This Exists

If you've used `pyquotex` or any Quotex Python API, you've hit this wall:

```
# Standard pyquotex → capped at 199 candles NO MATTER WHAT
candles = await client.get_candles("EURUSD_otc", time.time(), 86400, 60)
# Returns: 199 candles  ← always, even if you ask for 10,000
```

That's barely **3 hours** of 1-minute data. Useless for backtesting or training an ML model.

This repo fixes that completely.

---

## How It Works — The Discovery

By reverse-engineering the **live Quotex WebSocket traffic** in a browser, I found the exact payload format the broker uses for paginated historical requests. Three things were wrong in every existing solution:

| Parameter | What everyone does | What actually works |
|---|---|---|
| `offset` | Set to the chunk size | Must be **fixed at `3600`** |
| `step` | Various | Must be **exactly `2940`s** backward |
| `index` | 10-digit Unix timestamp | Must be **12-digit**: `int(time.time() * 100)` |

And the WebSocket server returns old paginated candle data under a **different key** (`message["data"]`) — not `message["history"]` like everyone expects. The original parser silently dropped all of it. That's why nothing worked before.

---

## Patches Applied to pyquotex

### Patch 1 — `pyquotex/ws/client.py`

```python
# BEFORE: parser only accepted message["history"] — dropped all paginated old data
# AFTER: accepts both formats seamlessly

if "data" in message and isinstance(message["data"], list):
    # history/load pagination structure — older candles come in "data", not "history"
    self.api.candle_v2_data[message["asset"]]["candles"] = message["data"]
```

### Patch 2 — `pyquotex/stable_api.py` — New `get_candles_deep()`

```python
# Fetch 30 DAYS of 1-minute Quotex candle data in one call
all_candles = await client.get_candles_deep("EURUSD_otc", 86400 * 30, 60)
print(f"Got {len(all_candles)} candles")
# Got 28,441 candles ✅
```

This method automatically:
- Initializes the session baseline
- Loops **backwards** generating the 12-digit proprietary index IDs
- Stitches all chunks together in chronological order
- Deduplicates and sorts the final dataset

---

## Quick Start

### 1. Install

```bash
pip install pyquotex python-dotenv
```

### 2. Set credentials

```bash
cp .env.example .env
# Open .env and fill in your Quotex email + password
```

### 3. Run the downloader

```bash
python download_data.py
```

```
=======================================================
QUOTEX HISTORICAL DATA DOWNLOADER
=======================================================
Enter Asset Pair (e.g. EURUSD_otc): USDPKR_otc
Enter Timeframe in seconds (e.g. 60 for 1m, 300 for 5m): 60
Enter how many days to fetch (e.g. 7 or 1.5): 30

Connecting to Quotex...
Started Deep Fetch for 30.0 Days of USDPKR_otc data (60s timeframe)...

Fetch complete in 52.3 seconds! Retrieved 28,441 candles.
Saved cleanly to: USDPKR_otc_60s_30.0days.csv
```

---

## Output — CSV Format

Every candle saved with full OHLC + tick data:

```csv
timestamp,datetime,open,high,low,close,ticks
1713000000,2024-04-13 12:00:00,1.08640,1.08701,1.08630,1.08685,45
1713000060,2024-04-13 12:01:00,1.08685,1.08720,1.08671,1.08699,38
...
```

### Built-in Data Validation Report

```
=======================================================
DATA VALIDATION REPORT
=======================================================
Total Unique Candles: 28441
Duplicates Found:     0
Gaps Found:           12
-------------------------------------------------------
Bullish (Green):      14822 (52.1%)
Bearish (Red):        13219 (46.5%)
Doji (Neutral):       400  (1.4%)
=======================================================
```

---

## Use in Your Own Script

```python
import asyncio
from pyquotex.stable_api import Quotex

async def main():
    client = Quotex(email="your@email.com", password="yourpass", lang="en")
    
    await client.connect()
    
    # Get 7 days of 5-minute EURUSD OTC candle data
    candles = await client.get_candles_deep("EURUSD_otc", 86400 * 7, 300)
    
    print(f"Fetched {len(candles)} candles")
    for c in candles[:3]:
        print(c)
    # {'time': 1713000000, 'open': 1.0864, 'high': 1.0870, 'low': 1.0860, 'close': 1.0866, 'ticks': 45}
    
    await client.close()

asyncio.run(main())
```

---

## Supported Assets & Timeframes

**OTC Assets** (24/7, recommended for data collection):
`EURUSD_otc`, `USDPKR_otc`, `XAUUSD_otc`, `USDINR_otc`, `GBPUSD_otc`, `USDJPY_otc`, and more.

**Timeframes (seconds):**
`5` `10` `15` `30` `60` `120` `300` `600` `900` `1800` `3600` `7200` `14400` `86400`

---

## Verified Results

| Asset | Timeframe | Days | Candles Retrieved | Fetch Time |
|---|---|---|---|---|
| USDPKR_otc | 60s (1m) | 3 | 2,306 | 18s |
| EURUSD_otc | 60s (1m) | 30 | 28,441 | 52s |
| XAUUSD_otc | 300s (5m) | 30 | 5,614 | 21s |

---

## FAQ

**Q: Does this work for all Quotex OTC assets?**  
Yes. Any asset available via pyquotex works with `get_candles_deep()`.

**Q: Is there a candle limit?**  
None found. In testing, 30+ days of 1-minute data fetches cleanly.

**Q: Which Python versions are supported?**  
Python 3.9+ (matches pyquotex requirements).

**Q: Why does the standard `get_candles()` cap at 199?**  
The WebSocket rejects non-conforming payloads silently. See the "How It Works" section above for the exact root cause.

**Q: Is this safe to use?**  
Use a **demo account** for data collection. Never use your main trading account with automated scripts.

---

## Project Structure

```
quotex-historical-data/
├── download_data.py          # Interactive downloader — run this
├── pyquotex/
│   ├── stable_api.py         # Patched — adds get_candles_deep()
│   └── ws/
│       └── client.py         # Patched — fixes pagination parser
├── examples/                 # Example scripts
├── test/                     # Test scripts used during development
├── docs/                     # Full API reference
├── walkthrough.md            # Technical deep-dive: how the fix was found
├── pyquotex_api_reference.md # Complete pyquotex API docs
├── .env.example              # Copy to .env and add credentials
└── README.md
```

---

## Related Resources

- [pyquotex original library](https://github.com/cleitonleonel/pyquotex) — MIT License
- `walkthrough.md` in this repo — full reverse-engineering writeup
- `pyquotex_api_reference.md` — complete API reference with all methods

---

## License

MIT — free to use, fork, and modify.

---

*Keywords: quotex historical data, quotex candle data, quotex api python, pyquotex historical candles, quotex ohlc data, quotex websocket python, quotex data download, binary options historical data, quotex unlimited candles, quotex data scraper, quotex trading data python*
