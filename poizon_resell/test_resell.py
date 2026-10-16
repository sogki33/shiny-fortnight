import unittest
from unittest.mock import MagicMock

import resell as r

CFG = dict(r.DEFAULT_CONFIG)


def fake_session(items):
    s = MagicMock()
    s.get.return_value.json.return_value = {'data': {'list': items}}
    return s


def goods(name, price, sold_out=False, used=None):
    return {'goodsNo': 1, 'goodsName': name, 'goodsLinkUrl': 'https://www.musinsa.com/products/1',
            'finalPrice': price, 'price': price, 'isSoldOut': sold_out, 'usedConditionGrade': used}


class MarginTests(unittest.TestCase):
    def test_min_fee_applies_to_cheap_items(self):
        self.assertEqual(r.poizon_fee(100000, CFG), 15000)
        self.assertEqual(r.poizon_fee(300000, CFG), 30000)

    def test_profit_includes_vat_refund(self):
        # 120,000 - 15,000 - 3,000 - 100,000 + 9,091 = 11,091
        self.assertEqual(r.profit(100000, 120000, CFG), 11091)
        self.assertEqual(r.profit(100000, 120000, dict(CFG, vat_refund=False)), 2000)

    def test_max_buy_price_hits_target(self):
        mb = r.max_buy_price(200000, CFG)
        self.assertGreaterEqual(r.profit(mb, 200000, CFG), CFG['min_profit'])
        self.assertLess(r.profit(mb + 100, 200000, CFG), CFG['min_profit'])


class CostOptionTests(unittest.TestCase):
    def test_card_discount_and_risk(self):
        cfg = dict(CFG, card_discount=0.05, risk_rate=0.02)
        # 120,000 - 15,000 - 3,000 - 2,400 - 95,000 + 9,091 = 13,691
        self.assertEqual(r.profit(100000, 120000, cfg), 13691)
        mb = r.max_buy_price(200000, cfg)
        self.assertGreaterEqual(r.profit(mb, 200000, cfg), cfg['min_profit'])
        self.assertLess(r.profit(mb + 100, 200000, cfg), cfg['min_profit'])

    def test_no_vat_source_gets_no_refund(self):
        self.assertEqual(r.profit(100000, 120000, CFG, vat_ok=False), 2000)

    def test_min_fee_zone(self):
        self.assertTrue(r.min_fee_zone(149000, CFG))
        self.assertFalse(r.min_fee_zone(150000, CFG))


class MusinsaTests(unittest.TestCase):
    def test_exact_style_code_only_and_skips_used(self):
        s = fake_session([goods('덩크 로우 W / DD1503-101', 139000),
                          goods('덩크 로우 W / DD1503-1010', 99000),
                          goods('덩크 로우 W / DD1503-101', 80000, used='A')])
        offers = r.musinsa_search('dd1503 101', session=s)
        self.assertEqual([o.price for o in offers], [139000])

    def test_scan_picks_cheapest_in_stock_and_flags_ok(self):
        s = fake_session([goods('A / DD1503-101', 139000), goods('B / DD1503-101', 100000, sold_out=True)])
        results, errors = r.scan([{'style_code': 'DD1503-101', 'poizon_price': 200000}], CFG, session=s)
        self.assertEqual(errors, [])
        self.assertEqual(results[0]['buy'], 139000)
        self.assertTrue(results[0]['ok'])

    def test_source_error_is_reported_not_raised(self):
        s = MagicMock()
        s.get.side_effect = RuntimeError('blocked')
        results, errors = r.scan([{'style_code': 'X1', 'poizon_price': 1}], CFG, session=s)
        self.assertEqual(results, [])
        self.assertIn('blocked', errors[0])


class DiscordTests(unittest.TestCase):
    def test_only_ok_results_are_sent(self):
        s = MagicMock()
        rows = [{'ok': True, 'style_code': 'A', 'size': '', 'name': 'n', 'buy': 1, 'sell': 2, 'fee': 0,
                 'profit': 1, 'roi': 1.0, 'max_buy': 1, 'source': 'musinsa', 'url': 'https://x'},
                {'ok': False}]
        self.assertEqual(r.notify_discord(rows, 'https://discord.example/hook', session=s), 1)
        self.assertEqual(len(s.post.call_args.kwargs['json']['embeds']), 1)
        self.assertEqual(r.notify_discord(rows, None, session=s), 0)


if __name__ == '__main__':
    unittest.main()
