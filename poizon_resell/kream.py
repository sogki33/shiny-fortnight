"""크림(KREAM) 공개 페이지에서 시세를 읽는 파서.

포이즌 시세는 공개 웹에서 볼 수 없어서, 국내 리셀 체결가(크림)를 판매가 추정치로 쓴다.
페이지는 TinyFish fetch_content(markdown) 결과를 그대로 받아 파싱한다.
"""
import re
from urllib.parse import quote

TRADE_RE = re.compile(r'\n([A-Z]{0,3}\d{2,3}(?:\.\d)?|ONE SIZE|XS|S|M|L|XL|XXL)\n\n([\d,]+)원\n\n([^\n]*전|\d{2}/\d{2}/\d{2})')


def search_url(style_code):
    return 'https://kream.co.kr/search?keyword=' + quote(style_code)


def product_from_search(result):
    """검색 결과(fetch_content의 result 하나)에서 품번과 정확히 맞는 상품 URL. 없으면 None."""
    text = result.get('text') or ''
    if '검색 결과가 없습니다' in text:
        return None
    for link in result.get('links') or []:
        if re.fullmatch(r'https://kream\.co\.kr/products/\d+', link):
            return link
    return None


def parse_product(text):
    """상품 페이지 markdown → 모델번호, 발매가, 즉시구매가, 누적 거래, 최근 체결(사이즈, 가격) 목록."""
    def num(s):
        return int(s.replace(',', '')) if s else None
    model = re.search(r'모델번호\s+([^\n]+)', text)
    release = re.search(r'발매가\s+([\d,]+)원', text)
    now = re.search(r'\n([\d,]+)원\n\n\(?W?\)? ?[^\n]*\n\n[A-Za-z(]', text)
    total = re.search(r'거래 ([\d.]+만|[\d,]+)', text)
    trades, seen = [], set()
    for size, price, when in TRADE_RE.findall(text):
        key = (size, price, when)
        if key in seen:  # 페이지에 같은 블록이 두 번 나온다
            continue
        seen.add(key)
        trades.append({'size': size, 'price': num(price), 'when': when})
    t = total.group(1) if total else None
    return {
        'model': model.group(1).strip() if model else None,
        'release': num(release.group(1)) if release else None,
        'ask': num(now.group(1)) if now else None,
        'total_trades': int(float(t[:-1]) * 10000) if t and t.endswith('만') else num(t),
        'trades': trades,
    }


def profitable_sizes(trades, break_even):
    """최근 체결가가 손익분기 이상인 사이즈 → {사이즈: 최고 체결가}."""
    out = {}
    for t in trades:
        if t['price'] >= break_even:
            out[t['size']] = max(out.get(t['size'], 0), t['price'])
    return out
