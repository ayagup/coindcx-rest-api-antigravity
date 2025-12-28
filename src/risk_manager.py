
class RiskManager:
    def __init__(self, risk_type='PERCENTAGE', risk_value=1.0, stop_loss_atr_multiplier=2.0):
        """
        :param risk_type: 'PERCENTAGE' (of balance) or 'FIXED_SIZE' (amount of asset)
        :param risk_value: value for the risk type (e.g., 20.0 for 20% or 0.1 for 0.1 BTC)
        :param stop_loss_atr_multiplier: multiplier for ATR to calculate SL distance
        """
        self.risk_type = risk_type
        self.risk_value = risk_value
        self.sl_multiplier = stop_loss_atr_multiplier

    def calculate_qty(self, balance, entry_price, leverage=1.0):
        """
        Calculate entry quantity.
        """
        if self.risk_type == 'FIXED_SIZE':
            return self.risk_value
        elif self.risk_type == 'PERCENTAGE':
            # Example: risk_value = 10 means 10% of balance (Balance * % / Price) (Simplified cash equivalent)
            allocation = balance * (self.risk_value / 100.0)
            qty = allocation / entry_price
            return qty
        elif self.risk_type == 'MARGIN':
            # risk_value is the Margin Amount in USDT (e.g. 100 USDT)
            # Notional Value = Margin * Leverage
            notional = self.risk_value * leverage
            qty = notional / entry_price
            return qty
        elif self.risk_type == 'MARGIN_PERCENTAGE':
            # risk_value is % of Balance to use as Margin
            # Margin = Balance * (risk_value / 100)
            margin_amt = balance * (self.risk_value / 100.0)
            notional = margin_amt * leverage
            qty = notional / entry_price
            return qty
        return 0.0

    def get_stop_loss_price(self, entry_price, direction, atr):
        """
        Calculate Stop Loss Price based on ATR.
        """
        distance = atr * self.sl_multiplier
        if direction.upper() == "LONG":
            return entry_price - distance
        elif direction.upper() == "SHORT":
            return entry_price + distance
        return entry_price

    def calculate_targets(self, entry_price, direction, sl_price):
        """
        Calculate 4 pre-determined targets based on Risk:Reward from the SL distance.
        R:R ratios: 1:1, 1:2, 1:3, 1:4
        """
        targets = []
        risk_distance = abs(entry_price - sl_price)
        
        # Avoid division by zero or super small risk
        if risk_distance == 0:
            return [entry_price] * 4

        for r in range(1, 5): # 1, 2, 3, 4
            reward_distance = risk_distance * r
            if direction.upper() == "LONG":
                target = entry_price + reward_distance
            else: # SHORT
                target = entry_price - reward_distance
            targets.append(target)
            
        return targets

    def get_candle_based_stop_loss(self, entry_price, direction, candle_high, candle_low, multiplier=2.0):
        """
        Calculate Stop Loss based on the size of a specific reference candle (High - Low).
        Distance = Candle Size * multiplier
        """
        candle_size = abs(candle_high - candle_low)
        distance = candle_size * multiplier
        
        if direction.upper() == "LONG":
            return entry_price - distance
        elif direction.upper() == "SHORT":
            return entry_price + distance
        return entry_price

    def calculate_fixed_point_targets(self, entry_price, direction, points=[300, 500, 800, 1000]):
        """
        Calculate targets based on fixed points from entry price.
        """
        targets = []
        for p in points:
            if direction.upper() == "LONG":
                targets.append(entry_price + p)
            else: # SHORT
                targets.append(entry_price - p)
        return targets
