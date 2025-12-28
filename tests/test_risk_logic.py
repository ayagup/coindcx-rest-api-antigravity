import unittest
from src.risk_manager import RiskManager

class TestRiskManager(unittest.TestCase):
    def setUp(self):
        self.rm_fixed = RiskManager(risk_type='FIXED_SIZE', risk_value=0.5)
        self.rm_pct = RiskManager(risk_type='PERCENTAGE', risk_value=10.0)
    
    def test_calculate_qty_fixed(self):
        qty = self.rm_fixed.calculate_qty(balance=10000, entry_price=50000)
        self.assertEqual(qty, 0.5)

    def test_calculate_qty_percentage(self):
        qty = self.rm_pct.calculate_qty(balance=10000, entry_price=50000)
        self.assertAlmostEqual(qty, 0.02)

    def test_get_stop_loss_long(self):
        sl = self.rm_fixed.get_stop_loss_price(50000, "LONG", 100)
        self.assertEqual(sl, 49800)

    def test_get_stop_loss_short(self):
        sl = self.rm_fixed.get_stop_loss_price(50000, "SHORT", 100)
        self.assertEqual(sl, 50200)

    def test_calculate_targets_long(self):
        targets = self.rm_fixed.calculate_targets(50000, "LONG", 49800)
        self.assertEqual(len(targets), 4)
        self.assertEqual(targets, [50200, 50400, 50600, 50800])
        
    # --- New Tests ---
    
    def test_get_candle_based_stop_loss_long(self):
        # Entry 50000. Candle High 5100, Low 5000 (Size 100). Multi usage default 2.0 = 200.
        # Long SL = 50000 - 200 = 49800
        # Wait, Inputs are prices. High=50100, Low=50000 -> Size 100.
        sl = self.rm_fixed.get_candle_based_stop_loss(50000, "LONG", 50100, 50000, multiplier=2.0)
        self.assertEqual(sl, 49800)

    def test_get_candle_based_stop_loss_short(self):
        # Price 50000. Candle Size 100. SL = 50000 + 200 = 50200
        sl = self.rm_fixed.get_candle_based_stop_loss(50000, "SHORT", 50100, 50000, multiplier=2.0)
        self.assertEqual(sl, 50200)

    def test_calculate_fixed_point_targets_long(self):
        entry = 50000
        points = [300, 500, 800, 1000]
        expected = [50300, 50500, 50800, 51000]
        result = self.rm_fixed.calculate_fixed_point_targets(entry, "LONG", points)
        self.assertEqual(result, expected)

    def test_calculate_fixed_point_targets_short(self):
        entry = 50000
        points = [300, 500, 800, 1000]
        expected = [49700, 49500, 49200, 49000]
        result = self.rm_fixed.calculate_fixed_point_targets(entry, "SHORT", points)
        self.assertEqual(result, expected)

if __name__ == '__main__':
    unittest.main()
