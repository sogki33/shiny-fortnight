import hashlib
import unittest
from unittest.mock import MagicMock

import poizon_api as p


class SignTests(unittest.TestCase):
    def test_sorted_encoded_and_empty_skipped(self):
        s = p.sign_string({'b': 'x y', 'a': 1, 'empty': '', 'none': None, 'sign': 'old'})
        self.assertEqual(s, 'a=1&b=x+y')

    def test_array_of_objects_joined_with_comma(self):
        s = p.sign_string({'sku_list': [{'b': 2, 'a': 'z'}, {'a': 'y'}]})
        # 객체는 키 정렬 JSON, 배열 원소는 쉼표로 연결 (공식 Python 예제 방식)
        self.assertEqual(s, 'sku_list=' + p.quote_plus('{"a":"z","b":2},{"a":"y"}'))

    def test_sign_is_upper_md5_of_string_plus_secret(self):
        params = {'app_key': 'k', 'timestamp': 1}
        want = hashlib.md5(b'app_key=k&timestamp=1secret').hexdigest().upper()
        self.assertEqual(p.make_sign(params, 'secret'), want)


class ClientTests(unittest.TestCase):
    def client(self, payload):
        s = MagicMock()
        s.post.return_value.json.return_value = payload
        return p.PoizonClient('key', 'secret', session=s), s

    def test_call_adds_auth_and_sign(self):
        c, s = self.client({'code': 200, 'data': {'ok': 1}})
        self.assertEqual(c.sku_by_article('DD1503-101'), {'ok': 1})
        body = s.post.call_args.kwargs['json']
        self.assertEqual(body['articleNumber'], 'DD1503-101')
        self.assertEqual(body['app_key'], 'key')
        signed = {k: v for k, v in body.items() if k != 'sign'}
        self.assertEqual(body['sign'], p.make_sign(signed, 'secret'))

    def test_error_code_raises(self):
        c, _ = self.client({'code': 401, 'msg': 'bad sign'})
        with self.assertRaises(p.PoizonError):
            c.list_bids()

    def test_missing_keys_file(self):
        with self.assertRaises(p.PoizonError):
            p.PoizonClient.from_file('/nonexistent/keys.json')


if __name__ == '__main__':
    unittest.main()
