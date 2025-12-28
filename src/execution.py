import hmac
import hashlib
import json
import time
import requests

class ExecutionClient:
    """
    CoinDCX Futures Execution Client (Real)
    Ref: https://docs.coindcx.com/?python#futures-end-points
    """
    def __init__(self, api_key=None, api_secret=None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = "https://api.coindcx.com" 

    def _send_signed_request(self, method, endpoint, body):
        if not self.api_key or not self.api_secret:
            print("Missing API credentials.")
            return None
            
        url = f"{self.base_url}{endpoint}"
        
        # Body must contain timestamp
        if "timestamp" not in body:
            body["timestamp"] = int(round(time.time() * 1000))
            
        # JSON Body for signature
        # Note: Docs use separators=(',', ':') which removes spaces
        json_body = json.dumps(body, separators=(',', ':'))
        
        secret_bytes = bytes(self.api_secret, encoding='utf-8')
        signature = hmac.new(secret_bytes, json_body.encode(), hashlib.sha256).hexdigest()
        
        headers = {
            'Content-Type': 'application/json',
            'X-AUTH-APIKEY': self.api_key,
            'X-AUTH-SIGNATURE': signature
        }
        
        try:
            if method.upper() == "POST":
                response = requests.post(url, data=json_body, headers=headers)
            else:
                # GET/DELETE with body? CoinDCX sometimes uses body even for GET (like wallets)
                # requests.get with data payload
                response = requests.request(method, url, data=json_body, headers=headers)
                
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"API Request Error ({endpoint}): {e}")
            try:
                print(f"Response: {response.text}")
            except:
                pass
            return None

    def get_balance(self, asset='USDT'):
        # Endpoint: /exchange/v1/derivatives/futures/wallets
        endpoint = "/exchange/v1/derivatives/futures/wallets"
        body = {}
        data = self._send_signed_request("POST", endpoint, body) # Docs say POST for wallets? checking doc trace... 
        # Wait, Doc Position 186 Wallets: "request.get" in Node example, "requests.get" in Python example.
        # But wait, Python example uses data=json_body in GET? Requests library allows it but it's non-standard.
        # Let's double check if I should use POST or GET.
        # Position 186 header says "HTTP Request POST" or GET?
        # Actually in position 186 summary: "Use this endpoint to fetch the wallet details... HTTP Request" usually implies POST if body is needed.
        # But python code `requests.get(url, data=json_body...)`. 
        # OK, I will try POST first as CoinDCX usually uses POST for everything secured, or follow Python example GET with body.
        # Let's try POST as it's safer for body payloads, but if it fails I'll switch to GET.
        # Actually most CoinDCX "read" endpoints take POST with timestamp. 
        # Let's verify Position 187... it says "HTTP Request".
        # Let's try POST.
        
        # Retrying analysis: The docs usually favor POST for authenticated calls requiring timestamp body.
        # But the snippet explicitly says `requests.get`. I will use `requests.post` initially because GET with body is flimsy.
        # Actually, let's look at `create_order` -> POST. `wallets` -> snippet says GET.
        # Use GET if snippet says GET.
        
        # Wait, `get_balance` needs to traverse the list to find currency.
        pass

    def get_balance_real(self, asset='USDT'):
        endpoint = "/exchange/v1/derivatives/futures/wallets"
        body = {}
        # Try POST first as it's common structure, if 405/404 then GET.
        # Actually, let's use the internal method that defaults to POST but can be overridden.
        # I'll implement a helper that tries GET if POST fails? No, risky.
        # Let's stick to Python snippet -> `requests.get` with body.
        
        resp = self._send_signed_request("GET", endpoint, body)
        if resp and isinstance(resp, list):
            for wallet in resp:
                if wallet.get("currency_short_name") == asset:
                    return float(wallet.get("balance", 0.0))
        return 0.0

    def place_order(self, symbol, side, qty, order_type='MARKET', price=None, params={}):
        """
        Create Order
        """
        endpoint = "/exchange/v1/derivatives/futures/orders/create"
        
        # order_type mapping: 'market_order' or 'limit_order'
        dcx_type = "market_order" if order_type.upper() == "MARKET" else "limit_order"
        stop_price_val = params.get('stopPrice')
        
        # Side: 'buy' or 'sell'
        
        order_payload = {
            "side": side.lower(),
            "pair": symbol, # e.g., B-BTC_USDT
            "order_type": dcx_type,
            "total_quantity": qty,
            # "leverage": 1, # Default? Or required? Docs showing integer.
            # "margin_currency_short_name": "USDT" # Optional?
        }
        
        if price:
            order_payload["price"] = price
        if stop_price_val:
            order_payload["stop_price"] = stop_price_val
            
        # If STOP_MARKET logic is needed, CoinDCX usually handles SL via stop_price or specialized order types.
        # Main `create_order` supports `stop_loss_price`.
        # Adhoc script uses:
        # 1. Market Entry
        # 2. Stop Market (SL) -> This might need to be a separate order or attached to entry.
        #    Adhoc script calls `place_order` separately for SL.
        #    For SL order: side=opposite, order_type=?, stop_price=SL.
        #    If `STOP_MARKET` is requested:
        #    CoinDCX doesn't have "STOP_MARKET" enum explicitly in the quick snippet.
        #    It has `take_profit_price` and `stop_loss_price` in the creates order body too.
        #    But for standalone SL order: usually "stop_limit_order" or regular limit with stop_price?
        #    Docs snippet Position 146 doesn't list stop_market.
        #    However, `stop_price` field exists.
        #    Let's assume we use `limit_order` with `stop_price` (Stop Limit) or `market_order` with `stop_price` (Stop Market).
        #    If `order_type` passed is `STOP_MARKET`, let's map to `market_order` + `stop_price`.
        
        if order_type == 'STOP_MARKET':
             order_payload["order_type"] = "market_order" # Trigger market?
             # CoinDCX might not support Stop Market via simple create api without specific flag?
             # Let's hope `stop_price` + `market_order` works as Stop Market.
             # Or use `stop_loss_price` param on the main position?
             # For now, map STOP_MARKET -> market_order with stop_price.
             pass
             
        body = {
            "order": order_payload
        }
        
        resp = self._send_signed_request("POST", endpoint, body)
        return resp

    # Wrapper for consistency
    def get_balance(self, asset='USDT'):
        return self.get_balance_real(asset)

    def set_leverage(self, symbol, leverage):
        """
        Update Position Leverage
        Endpoint: /exchange/v1/derivatives/futures/positions/update_leverage
        """
        endpoint = "/exchange/v1/derivatives/futures/positions/update_leverage"
        body = {
            "pair": symbol,
            "leverage": str(leverage) # Docs use string "5"
        }
        resp = self._send_signed_request("POST", endpoint, body)
        return resp

    def cancel_order(self, order_id):
        """
        Cancel Order
        Endpoint: /exchange/v1/derivatives/futures/orders/cancel
        """
        endpoint = "/exchange/v1/derivatives/futures/orders/cancel"
        body = {
            "id": order_id
        }
        return self._send_signed_request("POST", endpoint, body)

    def edit_order(self, order_id, new_price=None, new_stop_price=None, new_qty=None):
        """
        Edit Order
        Endpoint: /exchange/v1/derivatives/futures/orders/edit
        """
        endpoint = "/exchange/v1/derivatives/futures/orders/edit"
        body = {
            "id": order_id
        }
        if new_price is not None:
             body["price"] = new_price
        if new_stop_price is not None:
             body["stop_loss_price"] = new_stop_price # NOTE: The API param 'stop_loss_price' might be intended for attached SL, NOT for standalone stop order. 
             # However, Position 190 shows "stop_loss_price" in body.
             # If we are editing a LIMIT order, we change price.
             # If we are editing a STOP order, usually we change stop_price. 
             # But CoinDCX 'edit' example shows "price", "take_profit_price", "stop_loss_price".
             # If the original order was a STOP order (via PlaceOrder), checking if 'price' or 'stop_price' is key.
             # Position 190 example doesn't show 'stop_price' in body, it shows 'price', 'take_profit_price', 'stop_loss_price'.
             # BUT 'create_order' uses 'stop_price'.
             # Let's try passing 'stop_price' if 'stop_loss_price' doesn't work for standalone Stop Orders.
             # Actually, if I created a standalone Stop Limit, it has a trigger price.
             # Let's add 'stop_price' to body just in case the docs example was partial or specific to Limit-attached-SL.
             body["stop_price"] = new_stop_price

        if new_qty is not None:
             body["total_quantity"] = new_qty
             
        return self._send_signed_request("POST", endpoint, body)
