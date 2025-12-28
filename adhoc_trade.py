import sys
import os
import argparse
import time
import json
from dotenv import load_dotenv

sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.data_client import DataClient
from src.execution import ExecutionClient
from src.risk_manager import RiskManager

CONFIG_FILE = 'config.json'
TRADES_FILE = 'trades.json'

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

# --- Persistence ---
def load_trades():
    if not os.path.exists(TRADES_FILE):
        return []
    try:
        with open(TRADES_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return []

def save_trades(trades):
    with open(TRADES_FILE, 'w') as f:
        json.dump(trades, f, indent=4)

def add_trade(trade_data):
    trades = load_trades()
    trades.append(trade_data)
    save_trades(trades)

def update_trade(trade_id, key, value):
    trades = load_trades()
    for t in trades:
        if t.get('id') == trade_id:
            t[key] = value
            save_trades(trades)
            return

def delete_trade(trade_id):
    trades = load_trades()
    trades = [t for t in trades if t.get('id') != trade_id]
    save_trades(trades)

# --- Monitor ---
def monitor_trade(trade, exec_client, data_client):
    symbol = trade['symbol']
    sl_order_id = trade.get('sl_order_id')
    monitor_trigger_level = trade.get('monitor_trigger_level', 0)
    sl_moved = trade.get('sl_moved', False)
    targets = trade.get('targets', [])
    entry_price = trade.get('entry_price')
    side = trade.get('side')
    qty = trade.get('qty')
    trade_id = trade.get('id')
    
    print(f"Resuming Monitor for Trade {trade_id} ({side} {symbol})...")
    
    if not sl_order_id:
        print("No SL Order ID found. Cannot manage SL.")
        return

    try:
        while True:
            time.sleep(15)
            
            # Fetch Price
            df_mon = data_client.get_klines(symbol, '1m', limit=1)
            if df_mon.empty:
                continue
                
            curr_price = df_mon['close'].iloc[-1]
            print(f"[Mon {trade_id}] Price: {curr_price}...", end='\r')
            
            # 1. Check if SL Hit? (Requires calling Order Status API or inferring from Price)
            # Inferring from price for simplicity in adhoc
            sl_hit = False
            # Check Open Orders to see if SL is gone? 
            # Or simplified price check:
            # If SL is valid, and price crosses it, we assume SL hit.
            # But we don't know the CURRENT SL price easily without tracking or fetching.
            # Let's rely on TP Trigger Logic primarily as requested.
            
            # 2. Monitor TP Trigger
            if monitor_trigger_level > 0 and not sl_moved:
                target_idx = monitor_trigger_level - 1
                if 0 <= target_idx < len(targets):
                    trigger_pr = targets[target_idx]
                    
                    hit = False
                    if side == "LONG" and curr_price >= trigger_pr:
                        hit = True
                    elif side == "SHORT" and curr_price <= trigger_pr:
                        hit = True
                        
                    if hit:
                        print(f"\n[Mon {trade_id}] TP {monitor_trigger_level} Hit ({trigger_pr})! Moving SL to Entry {entry_price}...")
                        
                        # Move SL
                        edit_resp = exec_client.edit_order(sl_order_id, new_stop_price=entry_price)
                        if edit_resp and edit_resp.get('code') == 200:
                            print(f"SL Updated to Breakeven: {edit_resp}")
                            sl_moved = True
                            update_trade(trade_id, 'sl_moved', True)
                        else:
                            print(f"Edit Order Failed: {edit_resp}. Trying Cancel/Replace...")
                            exec_client.cancel_order(sl_order_id)
                            time.sleep(1)
                            sl_side = 'sell' if side == "LONG" else 'buy'
                            new_sl_resp = exec_client.place_order(symbol, sl_side, qty, 'STOP_MARKET', params={'stopPrice': entry_price})
                            print(f"New SL Placed: {new_sl_resp}")
                            if new_sl_resp and new_sl_resp.get('id'):
                                sl_order_id = new_sl_resp.get('id')
                                update_trade(trade_id, 'sl_order_id', sl_order_id)
                                sl_moved = True
                                update_trade(trade_id, 'sl_moved', True)
            
            # TODO: Detect Trade Close to remove from JSON
            # For now, user manual stop
            
    except KeyboardInterrupt:
        print(f"\nMonitor for {trade_id} Stopped.")

def main():
    load_dotenv()
    config = load_config()
    
    parser = argparse.ArgumentParser(description="Adhoc Trading Mode")
    parser.add_argument("side", type=str, choices=["LONG", "SHORT", "long", "short", "RESUME"], help="Action: LONG, SHORT, or RESUME")
    parser.add_argument("--size", type=float, default=None, help="Override config position size (Fixed amount)")
    
    args = parser.parse_args()
    action = args.side.upper()

    api_key = os.getenv("COINDCX_API_KEY")
    api_secret = os.getenv("COINDCX_API_SECRET")
    
    if not api_key or not api_secret:
        print("ERROR: API Keys missing.")
        return

    data_client = DataClient()
    exec_client = ExecutionClient(api_key, api_secret)

    # --- RESUME MODE ---
    if action == "RESUME":
        trades = load_trades()
        if not trades:
            print("No open trades found in trades.json.")
            return
        
        print(f"Resuming {len(trades)} trades...")
        # For simplicity, if multiple, we monitor the first one or loop? 
        # Since while loop is blocking, we can only monitor one in this script structure implies threading.
        # But 'adhoc' usually implies one. Let's just monitor the last one added.
        monitor_trade(trades[-1], exec_client, data_client)
        return

    # --- NEW TRADE ---
    side = action
    
    # Config Values
    leverage = config.get('leverage', 10)
    risk_config = config.get('risk', {})
    sl_multiplier = risk_config.get('sl_candle_multiplier', 2.0)
    tp_points = risk_config.get('tp_fixed_points', [300, 500, 800, 1000])
    monitor_trigger = risk_config.get('move_sl_to_entry_when_tp_hit', 0)
    
    pos_config = config.get('position_size', {'type': 'FIXED', 'value': 0.001})
    pos_type = pos_config.get('type', 'FIXED').upper()
    pos_value = pos_config.get('value', 0.001)

    # CLI Overrides
    if args.size is not None:
        pos_type = 'FIXED'
        pos_value = args.size
        print(f"Using CLI Size Override: {pos_value}")
    
    # Map Check
    rm_type = 'FIXED_SIZE' 
    if pos_type == 'PERCENTAGE': rm_type = 'PERCENTAGE'
    elif pos_type == 'MARGIN': rm_type = 'MARGIN'
    elif pos_type == 'MARGIN_PERCENTAGE': rm_type = 'MARGIN_PERCENTAGE'
    
    print(f"Starting Adhoc Trade: {side}")
    
    symbol = "B-BTC_USDT" 
    interval = "15m"
    risk_manager = RiskManager(risk_type=rm_type, risk_value=pos_value, stop_loss_atr_multiplier=sl_multiplier)
    
    # 0. Set Leverage
    print(f"Setting Leverage to {leverage}x...")
    exec_client.set_leverage(symbol, leverage)

    # 1. Fetch Data
    print(f"Fetching recent data for {symbol}...")
    df = data_client.get_klines(symbol, interval, limit=5)
    current_price = df['close'].iloc[-1]
    prev_candle = df.iloc[-2]
    
    print(f"Current Price: {current_price}")
    
    # 2. Calculate Size
    qty = 0.0
    balance = exec_client.get_balance('USDT') 
    
    if rm_type == 'PERCENTAGE':
        qty = risk_manager.calculate_qty(balance, current_price, leverage=leverage)
    elif rm_type == 'MARGIN':
        qty = risk_manager.calculate_qty(0, current_price, leverage=leverage) 
    elif rm_type == 'MARGIN_PERCENTAGE':
        qty = risk_manager.calculate_qty(balance, current_price, leverage=leverage)
    else:
        qty = pos_value
        
    # Rounding (0.001 step)
    step_size = 0.001
    import math
    steps = qty / step_size
    qty = round(steps) * step_size
    qty = float(f"{qty:.3f}")
    
    if qty <= 0:
        print("Error: Quantity too small.")
        return

    # 3. Plan
    sl_price = risk_manager.get_candle_based_stop_loss(current_price, side, prev_candle['high'], prev_candle['low'], multiplier=sl_multiplier)
    targets = risk_manager.calculate_fixed_point_targets(current_price, side, points=tp_points)
    
    print(f"Side: {side} | Size: {qty} | Entry: {current_price}")
    print(f"SL: {sl_price:.2f} | Targets: {targets}")
    
    confirm = input("Execute? (yes/no): ").strip().lower()
    if confirm not in ["yes", "y"]:
        return

    # 4. Execute
    order_side = 'buy' if side == "LONG" else 'sell'
    order = exec_client.place_order(symbol, order_side, qty, 'MARKET')
    
    if not order or not order.get('id'):
        print("Market Order Failed.")
        return

    entry_price_executed = current_price # Fallback
    
    # Recalculate SL
    sl_price = risk_manager.get_candle_based_stop_loss(entry_price_executed, side, prev_candle['high'], prev_candle['low'], multiplier=sl_multiplier)
    targets = risk_manager.calculate_fixed_point_targets(entry_price_executed, side, points=tp_points)
    
    # Stop Loss
    sl_side = 'sell' if order_side == 'buy' else 'buy'
    sl_resp = exec_client.place_order(symbol, sl_side, qty, 'STOP_MARKET', params={'stopPrice': sl_price})
    sl_order_id = sl_resp.get('id') if sl_resp else None
    
    # Take Profits
    chunk_qty = float(f"{qty / 4:.3f}") # 3 decimals
    tp_ids = []
    for t in targets:
        tp_resp = exec_client.place_order(symbol, sl_side, chunk_qty, 'LIMIT', price=t)
        if tp_resp and tp_resp.get('id'):
            tp_ids.append(tp_resp.get('id'))

    # SAVE STATE
    trade_data = {
        'id': str(int(time.time())),
        'symbol': symbol,
        'side': side,
        'qty': qty,
        'entry_price': entry_price_executed,
        'sl_order_id': sl_order_id,
        'tp_order_ids': tp_ids,
        'targets': targets,
        'monitor_trigger_level': monitor_trigger,
        'sl_moved': False
    }
    add_trade(trade_data)
    print("Trade Saved to trades.json")

    # Start Monitor
    monitor_trade(trade_data, exec_client, data_client)

if __name__ == "__main__":
    main()

if __name__ == "__main__":
    main()
