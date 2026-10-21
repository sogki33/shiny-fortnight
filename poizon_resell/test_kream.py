import unittest

import kream as k

PAGE = """유사 상품\n\n발매가 139,000원\n\n56%\n\n61,000원\n\n(W) 아디다스 삼바 OG 크림 화이트 코어 블랙\n\n(W) Adidas Samba OG Cream White Core Black\n\n4.8
모델번호 ID0478\n\n발매일 24/02/16\n\n발매가 139,000원\n\n거래 2.4만\n\n옵션\n\n거래가\n\n거래일
W235\n\n106,000원\n\n1시간 전
W235\n\n106,000원\n\n3시간 전
W235\n\n88,000원\n\n6시간 전
W240\n\n88,000원\n\n8시간 전
W230\n\n67,000원\n\n10시간 전\n\n모든 시세는 로그인 후 확인 가능합니다.
W235\n\n106,000원\n\n1시간 전
"""


class KreamTests(unittest.TestCase):
    def test_parse_product(self):
        p = k.parse_product(PAGE)
        self.assertEqual(p['model'], 'ID0478')
        self.assertEqual(p['release'], 139000)
        self.assertEqual(p['ask'], 61000)
        self.assertEqual(p['total_trades'], 24000)
        self.assertEqual([(t['size'], t['price']) for t in p['trades']],
                         [('W235', 106000), ('W235', 106000), ('W235', 88000), ('W240', 88000), ('W230', 67000)])

    def test_profitable_sizes(self):
        p = k.parse_product(PAGE)
        self.assertEqual(k.profitable_sizes(p['trades'], 82200), {'W235': 106000, 'W240': 88000})

    def test_product_from_search(self):
        hit = {'text': '삼바', 'links': ['https://kream.co.kr/brands/adidas', 'https://kream.co.kr/products/196266']}
        miss = {'text': 'x에 대한 검색 결과가 없습니다.', 'links': ['https://kream.co.kr/products/1']}
        self.assertEqual(k.product_from_search(hit), 'https://kream.co.kr/products/196266')
        self.assertIsNone(k.product_from_search(miss))


if __name__ == '__main__':
    unittest.main()


class FinalizeTests(unittest.TestCase):
    def test_only_profitable_sizes_survive(self):
        import daily_report as d
        import resell as r
        cfg = dict(r.DEFAULT_CONFIG)
        pool = [{'style_code': 'ID0478', 'name': '삼바', 'brand': 'A', 'buy': 59600, 'discount': 60, 'reviews': 1,
                 'break_even': r.break_even_sell(59600, cfg), 'url': 'u', 'normal': 139000},
                {'style_code': 'IG0671', 'name': '가젤', 'brand': 'A', 'buy': 50990, 'discount': 60, 'reviews': 1,
                 'break_even': r.break_even_sell(50990, cfg), 'url': 'u', 'normal': 129000}]
        search = {k.search_url('ID0478'): {'text': '', 'links': ['https://kream.co.kr/products/196266']},
                  k.search_url('IG0671'): {'text': '', 'links': ['https://kream.co.kr/products/2']}}
        d.attach_products(pool, search)
        gazelle = '모델번호 IG0671\n\n거래 1,707\n260\n\n38,000원\n\n1일 전\n'
        win = d.finalize(pool, {'https://kream.co.kr/products/196266': {'text': PAGE},
                                'https://kream.co.kr/products/2': {'text': gazelle}}, cfg)
        self.assertEqual([c['style_code'] for c in win], ['ID0478'])
        self.assertEqual(set(win[0]['sizes']), {'W235', 'W240'})
        self.assertEqual(win[0]['sizes']['W235']['profit'], r.profit(59600, 106000, cfg))
        html = d.render(win, cfg, __import__('datetime').datetime(2026, 10, 20), checked=2)
        self.assertIn('W235', html)


class StockTests(unittest.TestCase):
    def test_apply_stock(self):
        import daily_report as d
        w = [{'url': 'a', 'sizes': {'W235': {'profit': 30}, 'W240': {'profit': 10}}, 'best_profit': 30},
             {'url': 'b', 'sizes': {'290': {'profit': 50}}, 'best_profit': 50},
             {'url': 'c', 'sizes': {'260': {'profit': 5}}, 'best_profit': 5}]
        out = d.apply_stock(w, {'a': {'in_stock': ['240', '250']}, 'b': {'in_stock': ['280']}})
        self.assertEqual([(c['url'], list(c['sizes'])) for c in out], [('a', ['W240']), ('c', ['260'])])
        self.assertTrue(out[0]['stock_checked']); self.assertFalse(out[1]['stock_checked'])


class KreamFeeTests(unittest.TestCase):
    def test_fee_uses_larger_of_general_and_premium(self):
        self.assertEqual(k.kream_fee(100000), round((20000 + 3000) * 1.1))     # 저가는 프리미엄 기본료가 큼
        self.assertEqual(k.kream_fee(1000000), round((60000 + 2500) * 1.1))   # 고가는 일반 6%가 큼

    def test_instant_sell_uses_lowest_trade(self):
        p = k.parse_product(PAGE)
        self.assertEqual(k.instant_sell_estimate(p['trades'])['W235'], 88000)

    def test_boutique_break_even(self):
        import boutique as b
        be = b.kream_break_even(500000)
        self.assertGreaterEqual(k.kream_profit(500000, be), 10000)
        self.assertLess(k.kream_profit(500000, be - 1000), 10000)
