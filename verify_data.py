import os
sys = __import__("sys")
try:
    import pandas as pd
except ImportError:
    print("Please install pandas first: pip install pandas")
    sys.exit(1)

def verify_csv(filename):
    if not os.path.exists(filename):
        print(f"❌ File not found: {filename}")
        return

    print(f"\n=======================================================")
    print(f"🔍 ANALYZING: {filename}")
    print(f"=======================================================")
    
    df = pd.read_csv(filename)
    total_candles = len(df)
    
    print(f"Total Candles: {total_candles:,}")
    
    # Check for Gaps (assuming continuous timeframe, detect where difference is not uniform)
    # We first need to guess the period (timeframe)
    if total_candles > 1:
        periods = df['timestamp'].diff().value_counts()
        period = int(periods.idxmax())
        
        gaps = df['timestamp'].diff() > period
        gap_count = gaps.sum()
        print(f"Detected Timeframe: {period}s")
        print(f"Missing Blocks / Gaps: {gap_count}")
    
    # DOJIs analysis
    # A real DOJI has open == close, but high and low can be different.
    doji_condition = (df['open'] == df['close'])
    real_dojis = df[doji_condition]
    
    # A SYNTHETIC DOJI (fake gap fill) has open == close == high == low
    fake_doji_condition = doji_condition & (df['high'] == df['open']) & (df['low'] == df['open'])
    fake_dojis = df[fake_doji_condition]
    
    print("-------------------------------------------------------")
    print(f"Total Neutral/Doji Candles: {len(real_dojis):,} ({(len(real_dojis)/total_candles)*100:.1f}%)")
    print(f"Fake 'Flat' Candles (O=H=L=C): {len(fake_dojis):,} ({(len(fake_dojis)/total_candles)*100:.1f}%)")
    print("-------------------------------------------------------")
    
    if len(fake_dojis) > 0:
        print("⚠️ Found FAKE gap-fill candles! Example:")
        print(fake_dojis[['datetime', 'open', 'high', 'low', 'close', 'ticks']].head(3).to_string(index=False))
    else:
        print("✅ No fake 'flat' gap-fill candles found. All data is authentic.")

    if len(real_dojis) > 0 and len(fake_dojis) == 0:
        print("\n📈 Sample of REAL Dojis (Notice how high/low move, and ticks > 1):")
        print(real_dojis[['datetime', 'open', 'high', 'low', 'close', 'ticks']].head(5).to_string(index=False))
        
    print("=======================================================\n")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        verify_csv(sys.argv[1])
    else:
        # Prompt user if no argument passed
        files = [f for f in os.listdir() if f.endswith('.csv')]
        if not files:
            print("No CSV files found in directory.")
        else:
            print("Available CSV files:")
            for i, f in enumerate(files):
                print(f" {i+1}. {f}")
            choice = input(f"\nEnter the number to test (1-{len(files)}): ").strip()
            try:
                idx = int(choice) - 1
                verify_csv(files[idx])
            except (ValueError, IndexError):
                print("Invalid choice.")
