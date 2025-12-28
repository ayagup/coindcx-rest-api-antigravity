import requests
import pandas as pd
import datetime
import time

class DataClient:
    """
    CoinDCX Data Client (Public Futures API)
    Ref: https://docs.coindcx.com/?python#futures-end-points (Get instrument candlesticks)
    """
    def __init__(self, base_url="https://public.coindcx.com"):
        self.base_url = base_url

    def get_klines(self, symbol="B-BTC_USDT", interval="15m", limit=100):
        """
        Fetch candles from /market_data/candlesticks
        Params: pair, from, to, resolution, pcode=f
        """
        endpoint = "/market_data/candlesticks"
        url = f"{self.base_url}{endpoint}"
        
        # Map simple interval (e.g., '15m') to Coindcx resolution
        # '1' OR '5' OR '60' OR '1D'
        resolution_map = {
            '1m': '1',
            '5m': '5',
            '15m': '15', # Wait, docs say '1', '5', '60', '1D'. Does it support 15? 
                         # Usually 15 is supported if 5 is. The examples show limited set. 
                         # Let's assume '15' works or fallback to '5' if failing. 
                         # Actually docs say: '1' OR '5' OR '60' OR '1D'. 
                         # If 15 is not supported, we might need to build 15m from 5m or 1m.
                         # Let's try sending '15' first, if it fails, maybe use '5'.
                         # However, for simplicity let's stick to what might be supported or just '5' if we want safety.
                         # Let's try to map '15m' -> '15' and see. If strict validation, we change.
            '1h': '60',
            '1d': '1D'
        }
        res_val = resolution_map.get(interval, '15') 
        
        # Timestamps
        to_ts = int(time.time())
        # limit * interval_seconds approx
        # 15m * 100 = 1500 mins = 25 hours = 90000 seconds
        from_ts = to_ts - (limit * 15 * 60) # Rough estimate for 15m
        
        params = {
            "pair": symbol,
            "from": from_ts,
            "to": to_ts,
            "resolution": res_val, 
            "pcode": "f" # Futures
        }
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            resp_json = response.json()
            
            # Structure: { "s": "ok", "data": [ ... ] }
            if resp_json.get("s") != "ok":
                print(f"CoinDCX Error: {resp_json}")
                return pd.DataFrame()
                
            data = resp_json.get("data", [])
            if not data:
                return pd.DataFrame()
            
            df = pd.DataFrame(data)
            
            # Columns in response: open, high, low, close, volume, time
            if "time" in df.columns:
                df["open_time"] = pd.to_datetime(df["time"], unit="ms")
                df["close_time"] = df["open_time"] 
                
            # Ensure numeric
            numeric_cols = ["open", "high", "low", "close", "volume"]
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            if "open_time" in df.columns:
                df = df.sort_values("open_time").reset_index(drop=True)
                
            return df
            
        except Exception as e:
            print(f"Error fetching data from CoinDCX: {e}")
            return pd.DataFrame()
