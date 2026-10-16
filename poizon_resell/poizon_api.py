"""POIZON 오픈플랫폼(open.poizon.com) 판매자 API 클라이언트.

필요한 것: 포이즌 판매자 계정 → open.poizon.com 콘솔에서 앱 생성 → API 권한 패키지 신청
→ 앱 정보 탭의 App Key / App Secret. poizon_keys.json(깃에 안 올라감)에 저장한다.

서명(sign) 규칙 (공식 문서 'Sign'):
  요청 JSON에 app_key, timestamp(ms)를 넣고 값이 빈 키는 제외, 키를 ASCII 오름차순 정렬,
  key=URL인코딩(value)를 &로 연결 → 끝에 app_secret 붙임 → MD5 → 대문자.
  값이 배열이면 원소를 쉼표로 이어 붙이고, 객체는 키 정렬 JSON 문자열로 만든다.
"""
import hashlib
import json
import time
import uuid
from pathlib import Path
from urllib.parse import quote_plus

import requests

ROOT = Path(__file__).resolve().parent
KEYS_FILE = ROOT / 'poizon_keys.json'
DEFAULT_BASE_URL = 'https://open.poizon.com'

# 공식 문서에 나온 경로
PATHS = {
    'sku_by_article': '/dop/api/v1/pop/api/v1/intl-commodity',      # 브랜드 공식 품번으로 SKU 조회
    'recommend_bid': '/dop/api/v1/pop/api/v1/recommend-bid',          # 리스팅 추천가(최저가 등)
    'recommend_bid_batch': '/dop/api/v1/pop/api/v1/recommend-bid/batch',
    'submit_bid': '/dop/api/v1/pop/api/v1/submit-bid/normal-autonomous-bidding',  # 입찰(검수 후 발송형)
    'update_bid': '/dop/api/v1/pop/api/v1/submit-bid/update',
    'cancel_bid': '/dop/api/v1/pop/api/v1/submit-bid/cancel',
    'list_bids': '/dop/api/v1/pop/api/v1/submit-bid/list',
    'orders': '/dop/api/v1/pop/api/v1/order/query-v2',
}


def _value_str(obj, sub=False):
    """공식 Python 예제(getStr)와 같은 방식으로 값을 문자열화."""
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], str):
            return ','.join(obj)
        s = ','.join(_value_str(x, True) for x in obj)
        return f'[{s}]' if sub else s
    if isinstance(obj, dict):
        inner = ','.join(f'"{k}":{_value_str(obj[k], True)}' for k in sorted(obj))
        return '{' + inner + '}'
    if isinstance(obj, bool):
        return 'true' if obj else 'false'
    if isinstance(obj, str) and sub:
        return f'"{obj}"'
    return str(obj)


def sign_string(params):
    """서명 대상 문자열 (app_secret 붙이기 전)."""
    keys = sorted(k for k, v in params.items() if v not in (None, '') and k != 'sign')
    return '&'.join(f'{k}={quote_plus(_value_str(params[k]), encoding="utf-8")}' for k in keys)


def make_sign(params, app_secret):
    return hashlib.md5((sign_string(params) + app_secret).encode('utf-8')).hexdigest().upper()


class PoizonError(RuntimeError):
    pass


class PoizonClient:
    def __init__(self, app_key, app_secret, access_token=None, base_url=DEFAULT_BASE_URL,
                 language='ko', time_zone='Asia/Seoul', session=None):
        self.app_key, self.app_secret, self.access_token = app_key, app_secret, access_token
        self.base_url = base_url.rstrip('/')
        self.language, self.time_zone = language, time_zone
        self.session = session or requests.Session()

    @classmethod
    def from_file(cls, path=KEYS_FILE, **kw):
        path = Path(path)
        if not path.exists():
            raise PoizonError(f'{path.name} 파일이 없습니다. poizon_keys.json에 app_key, app_secret을 입력하세요 (README 참고).')
        d = json.loads(path.read_text(encoding='utf-8'))
        if not d.get('app_key') or not d.get('app_secret'):
            raise PoizonError('App Key 또는 App Secret이 비어 있습니다.')
        return cls(d['app_key'], d['app_secret'], d.get('access_token'),
                   d.get('base_url') or DEFAULT_BASE_URL, **kw)

    def call(self, name, body):
        params = dict(body)
        params.update(app_key=self.app_key, timestamp=int(time.time() * 1000),
                      language=self.language, timeZone=self.time_zone)
        if self.access_token:
            params['access_token'] = self.access_token
        params['sign'] = make_sign(params, self.app_secret)
        r = self.session.post(self.base_url + PATHS[name], json=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        if data.get('code') not in (200, 0, '200'):
            raise PoizonError(f"{name} 실패: code={data.get('code')} msg={data.get('msg') or data.get('message')} "
                              f"trace={data.get('trace_id')}")
        return data.get('data')

    # ---- 조회 ----
    def sku_by_article(self, article_number):
        """브랜드 공식 품번(예: DD1503-101)으로 포이즌 SPU/SKU 정보 조회."""
        return self.call('sku_by_article', {'articleNumber': article_number})

    def recommend_bid(self, sku_id=None, global_sku_id=None, country_code='KR', currency='KRW'):
        """리스팅 추천가: 현재 최저 입찰가 등 판매가 결정에 쓰는 시세."""
        body = {'countryCode': country_code, 'currency': currency}
        if global_sku_id:
            body['globalSkuId'] = global_sku_id
        if sku_id:
            body['skuId'] = sku_id
        return self.call('recommend_bid', body)

    def list_bids(self, page=1, size=50):
        return self.call('list_bids', {'pageNum': page, 'pageSize': size})

    # ---- 판매(입찰) ----
    def submit_bid(self, price, quantity=1, sku_id=None, global_sku_id=None, size_type=None,
                   country_code='KR', currency='KRW'):
        """검수 후 발송(Ship-to-verify) 방식 입찰. 성공하면 sellerBiddingNo 반환."""
        body = {'requestId': str(uuid.uuid4()), 'price': int(price), 'quantity': int(quantity),
                'countryCode': country_code, 'deliveryCountryCode': country_code, 'currency': currency}
        if global_sku_id:
            body['globalSkuId'] = global_sku_id
        if sku_id:
            body['skuId'] = sku_id
        if size_type:
            body['sizeType'] = size_type
        return self.call('submit_bid', body)

    def update_bid(self, seller_bidding_no, price, quantity=1):
        return self.call('update_bid', {'requestId': str(uuid.uuid4()), 'sellerBiddingNo': seller_bidding_no,
                                        'price': int(price), 'quantity': int(quantity)})

    def cancel_bid(self, seller_bidding_no):
        return self.call('cancel_bid', {'sellerBiddingNo': seller_bidding_no})


if __name__ == '__main__':
    # 키 연결 확인용 조회 명령. 예: python poizon_api.py lookup DD1503-101
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == 'lookup':
        print(json.dumps(PoizonClient.from_file().sku_by_article(sys.argv[2]), ensure_ascii=False, indent=2))
    else:
        print('사용법: python poizon_api.py lookup <품번>')
