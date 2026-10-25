"""크림(KREAM) 공개 페이지에서 시세를 읽는 파서.

포이즌 시세는 공개 웹에서 볼 수 없어서, 국내 리셀 체결가(크림)를 판매가 추정치로 쓴다.
페이지는 TinyFish fetch_content(markdown) 결과를 그대로 받아 파싱한다.
"""
import re
from urllib.parse import quote

TRADE_RE = re.compile(r'\n((?:[A-Z]{1,3} ?)?\d{1,3}(?:\.\d)?[A-Z]{0,2}|ONE SIZE|XXS|XS|S|M|L|XL|XXL|XXXL)\n\n([\d,]+)원\n\n([^\n]*전|\d{2}/\d{2}/\d{2})')


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


def profitable_sizes(trades, break_even, today=None, days=30):
    """최근 days일 체결가가 손익분기 이상인 사이즈 → {사이즈: 최고 체결가}. 오래된 거래는 제외."""
    out = {}
    for t in trades:
        if t['price'] >= break_even and is_recent(t['when'], today, days):
            out[t['size']] = max(out.get(t['size'], 0), t['price'])
    return out


# 크림 판매 수수료 (레벨1 최고 요율, 부가세 별도). 프리미엄 요율은 샤넬·에르메스 가방, 롤렉스 시계 같은
# 지정 카테고리에만 붙고 신발·의류는 일반 요율이다. 상한 30만 원.
KREAM_FEE = {'rate': 0.06, 'base': 2500, 'premium_rate': 0.03, 'premium_base': 20000,
             'cap': 300000, 'vat': 0.10, 'shipping': 3500}


def kream_fee(sell, fee=KREAM_FEE, premium=False):
    raw = sell * fee['premium_rate'] + fee['premium_base'] if premium else sell * fee['rate'] + fee['base']
    return round(min(raw, fee['cap']) * (1 + fee['vat']))


def kream_profit(buy, sell, fee=KREAM_FEE, premium=False):
    """크림에 팔았을 때 순이익 (개인 판매 기준, 부가세 환급 없음)."""
    return round(sell - kream_fee(sell, fee, premium) - fee['shipping'] - buy)


def is_recent(when, today=None, days=30):
    """'3시간 전', '2일 전' 같은 표기나 'YY/MM/DD' 날짜가 최근 days일 이내인지."""
    from datetime import date
    if when.endswith('전'):
        return True
    try:
        y, m, d = (int(x) for x in when.split('/'))
        return ((today or date.today()) - date(2000 + y, m, d)).days <= days
    except ValueError:
        return False


def instant_sell_estimate(trades, today=None, days=30, min_trades=2):
    """사이즈별 즉시판매 추정가 = 최근 days일 체결가 중 가장 낮은 값.

    실제 즉시판매가(구매 입찰 최고가)는 로그인해야 보여서 체결가로 추정한다.
    한 번 튄 거래에 속지 않도록 그 사이즈 체결이 min_trades건 이상일 때만 쓴다.
    """
    prices = {}
    for t in trades:
        if is_recent(t['when'], today, days):
            prices.setdefault(t['size'], []).append(t['price'])
    est = {sz: min(ps) for sz, ps in prices.items() if len(ps) >= min_trades}
    # 다른 사이즈보다 20% 넘게 비싸게 체결된 사이즈는 구매 입찰이 그 가격까지 받쳐주지 않는 경우가 많아 제외
    allp = sorted(p for ps in prices.values() for p in ps)
    if len(allp) >= 3:
        median = allp[len(allp) // 2]
        est = {sz: p for sz, p in est.items() if p <= median * 1.2}
    return est
