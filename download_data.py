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
from datetime import datetime

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

    print(f"\nStarted Deep Fetch for {days} Days of {asset_name} data ({period}s timeframe)...")
    print("Please wait, this might take a few minutes depending on the duration...")
    start_time = time.time()
    
    all_candles = await client.get_candles_deep(asset_name, duration_seconds, period)
    
    fetch_time = time.time() - start_time
    print(f"\nFetch complete in {fetch_time:.1f} seconds! Retrieved {len(all_candles)} candles.")
    
    if all_candles:
        # Generate safe filename
        safe_asset_name = asset_name.replace("/", "_")
        csv_filename = f"{safe_asset_name}_{period}s_{days}days.csv"
        
        with open(csv_filename, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['timestamp', 'datetime', 'open', 'high', 'low', 'close', 'ticks'])
            
            for c in all_candles:
                dt_str = datetime.fromtimestamp(c['time']).strftime('%Y-%m-%d %H:%M:%S')
                writer.writerow([
                    c['time'],
                    dt_str,
                    c['open'],
                    c['high'],
                    c['low'],
                    c['close'],
                    c.get('ticks', 0)
                ])
                
        print(f"Saved cleanly to: {csv_filename}")
        
        # Analyze
        analyze_data(all_candles, period)
    else:
        print("FAILED to retrieve any candles.")
        
    await client.close()

if __name__ == "__main__":
    asyncio.run(main())
