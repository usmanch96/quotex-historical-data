"""
Universal Quotex Historical Data Downloader
===========================================
Bypass the 199-candle WebSocket limit and download unlimited historical
candlestick data from the Quotex broker.

Usage:
    1. Copy .env.example to .env and fill in your credentials
    2. python download_data.py

It will interactively ask for the asset, timeframe, and days of history,
then compile everything into a validated CSV file.
"""

import os
import sys
import time
import asyncio
import csv
import logging
from datetime import datetime, timedelta

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv optional — can also set vars in shell

sys.path.insert(0, ".")

from pyquotex.stable_api import Quotex

# Suppress debug logs for cleaner user output
logging.basicConfig(level=logging.WARNING)

# Load credentials from .env file (copy .env.example → .env and fill in your details)
EMAIL = os.getenv("QUOTEX_EMAIL", "")
PASSWORD = os.getenv("QUOTEX_PASSWORD", "")

if not EMAIL or not PASSWORD:
    print("ERROR: Credentials not set.")
    print("  Copy .env.example to .env and fill in your QUOTEX_EMAIL and QUOTEX_PASSWORD.")
    sys.exit(1)

def print_progress(fetched_seconds, total_seconds, candle_count, start_ts):
    """Prints a live updating progress bar to the terminal."""
    pct = min(fetched_seconds / total_seconds, 1.0) if total_seconds > 0 else 0
    bar_len = 35
    filled = int(bar_len * pct)
    bar = "█" * filled + "░" * (bar_len - filled)

    elapsed = time.time() - start_ts
    if pct > 0.01:
        eta_secs = (elapsed / pct) * (1 - pct)
        eta_str = str(timedelta(seconds=int(eta_secs)))
    else:
        eta_str = "calculating..."

    days_fetched = fetched_seconds / 86400

    # \r goes back to start of line — overwrites without scrolling
    print(
        f"\r  [{bar}] {pct*100:5.1f}%  "
        f"{days_fetched:.2f} days  "
        f"{candle_count:,} candles  "
        f"⏱ {elapsed:.0f}s  ETA {eta_str}   ",
        end="", flush=True
    )


def analyze_data(candles, period):
    """Performs validation checks on the retrieved candles."""
    if not candles:
        print("❌ No data to analyze.")
        return

    duplicates = 0
    gaps = 0
    green_count = 0
    red_count = 0
    doji_count = 0
    
    seen_times = set()
    gap_details = []

    for i, c in enumerate(candles):
        c_time = c['time']
        
        # 1. Duplicates check
        if c_time in seen_times:
            duplicates += 1
        seen_times.add(c_time)
        
        # 2. Gaps check (comparing with previous candle)
        if i > 0:
            prev_time = candles[i-1]['time']
            time_diff = c_time - prev_time
            if time_diff != period:
                gaps += 1
                gap_details.append(f"Gap between {datetime.fromtimestamp(prev_time).strftime('%Y-%m-%d %H:%M:%S')} and {datetime.fromtimestamp(c_time).strftime('%Y-%m-%d %H:%M:%S')} ({time_diff}s diff)")

        # 3. Candle type count
        if c['close'] > c['open']:
            green_count += 1
        elif c['close'] < c['open']:
            red_count += 1
        else:
            doji_count += 1

    total = len(candles)
    
    print("\n=======================================================")
    print("DATA VALIDATION REPORT")
    print("=======================================================")
    print(f"Total Unique Candles: {total - duplicates}")
    print(f"Duplicates Found:     {duplicates}")
    print(f"Gaps Found:           {gaps}")
    print("-------------------------------------------------------")
    print(f"Bullish (Green):      {green_count} ({(green_count/total)*100:.1f}%)")
    print(f"Bearish (Red):        {red_count} ({(red_count/total)*100:.1f}%)")
    print(f"Doji (Neutral):       {doji_count} ({(doji_count/total)*100:.1f}%)")
    print("=======================================================\n")
    
    if gaps > 0 and len(gap_details) <= 10:
        print("Detailed Gaps:")
        for g in gap_details:
            print(f" - {g}")
    elif gaps > 0:
        print(f"High gap count ({gaps}). This is typical for zero-volume market minutes or connection resets.")


async def main():
    print("\n=======================================================")
    print("QUOTEX HISTORICAL DATA DOWNLOADER")
    print("=======================================================")
    
    asset = input("Enter Asset Pair (e.g. USDPKR_otc): ").strip()
    if not asset:
        print("Invalid asset.")
        return
        
    try:
        period = int(input("Enter Timeframe in seconds (e.g. 60 for 1m, 300 for 5m): ").strip())
        days = float(input("Enter how many days to fetch (e.g. 7 or 1.5): ").strip())
    except ValueError:
        print("Invalid number entered. Exiting.")
        return

    duration_seconds = int(86400 * days)

    print("\nConnecting to Quotex...")
    client = Quotex(email=EMAIL, password=PASSWORD, lang="en")
    client.debug_ws_enable = False

    check, msg = await client.connect()
    if not check:
        print(f"Connection FAILED: {msg}")
        return

    asset_name, asset_data = await client.get_available_asset(asset, force_open=True)
    if not asset_data[2]:
        print(f"WARNING: Asset {asset} is currently CLOSED on the broker.")
        # We can still attempt fetch, some brokers allow fetching history of closed assets.

    print(f"\n🚀 Starting deep fetch: {days} days of {asset_name} ({period}s candles)")
    print(f"   Estimated candles: ~{int(duration_seconds / period):,}")
    print()

    start_time = time.time()

    def on_progress(fetched_secs, total_secs, count):
        print_progress(fetched_secs, total_secs, count, start_time)

    all_candles = await client.get_candles_deep(
        asset_name, duration_seconds, period,
        progress_callback=on_progress
    )

    # Move to next line after progress bar
    print()

    fetch_time = time.time() - start_time
    print(f"✅ Fetch complete in {fetch_time:.1f}s — Retrieved {len(all_candles):,} candles.")
    
    if all_candles:
        # Generate safe filename
        safe_asset_name = asset_name.replace("/", "_")
        csv_filename = f"{safe_asset_name}_{period}s_{days}days.csv"

        skipped = 0
        written = 0
        with open(csv_filename, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['timestamp', 'datetime', 'open', 'high', 'low', 'close', 'ticks'])

            for c in all_candles:
                # Some tick-based candles may be missing OHLC — skip them gracefully
                op   = c.get('open')
                hi   = c.get('high')
                lo   = c.get('low')
                cl   = c.get('close')
                if None in (op, hi, lo, cl):
                    skipped += 1
                    continue
                dt_str = datetime.fromtimestamp(c['time']).strftime('%Y-%m-%d %H:%M:%S')
                writer.writerow([
                    c['time'],
                    dt_str,
                    op, hi, lo, cl,
                    c.get('ticks', 0)
                ])
                written += 1

        if skipped:
            print(f"⚠️  Skipped {skipped:,} incomplete candles (missing OHLC — normal for 1s timeframe).")
        print(f"💾 Saved {written:,} candles to: {csv_filename}")

        # Analyze only complete candles
        complete = [c for c in all_candles if c.get('open') is not None]
        analyze_data(complete, period)
    else:
        print("❌ FAILED to retrieve any candles.")

    await client.close()

if __name__ == "__main__":
    asyncio.run(main())
