import unittest
from copy import deepcopy
from datetime import date
from origin_review import approved

class OriginTests(unittest.TestCase):
    def setUp(self):
        self.p = {"productId": 1, "productName": "국내산 쌀"}
        self.r = {"1": {"status": "approved", "product_name": "국내산 쌀",
            "checked_on": "2026-09-15", "reviewer": "reviewer", "complete_ingredient_list": True,
            "all_subingredients_checked": True, "same_options_and_origin": True,
            "source_url": "https://example.com/label", "label_evidence": "쌀 100%, 대한민국",
            "ingredients": [{"name": "쌀", "origin": "대한민국", "evidence": "쌀: 대한민국"}]}}
    def check(self, r):
        return approved(self.p, r, date(2026, 9, 15))
    def test_verified(self):
        self.assertTrue(self.check(self.r))
    def test_title_only(self):
        self.assertFalse(self.check({}))
    def test_imported_subingredient(self):
        self.r['1']['ingredients'].append({'name': '밀', 'origin': '미국', 'evidence': '미국산'})
        self.assertFalse(self.check(self.r))
    def test_incomplete_and_stale(self):
        for key, value in [('complete_ingredient_list', False), ('all_subingredients_checked', False),
                           ('same_options_and_origin', False), ('checked_on', '2026-01-01'),
                           ('checked_on', '2027-01-01'), ('ingredients', []), ('label_evidence', ''),
                           ('product_name', '다른 옵션'), ('reviewer', '')]:
            with self.subTest(key=key):
                r = deepcopy(self.r)
                r['1'][key] = value
                self.assertFalse(self.check(r))

if __name__ == '__main__':
    unittest.main()
