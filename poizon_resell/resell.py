"""국내 매입(무신사 등) → 포이즌 판매 마진 스캐너.

흐름: watchlist.csv(품번 + 포이즌 시세) → 국내 최저가 조회 → 수수료/배송/부가세 환급 반영 마진 계산
→ 기준 이상이면 리포트 + 디스코드 웹훅 알림.

포이즌은 공개 시세 API가 없어 포이즌 가격은 CSV로 받습니다(앱에서 확인하거나 사용 중인 도구에서 내보낸 값).
구매는 자동으로 하지 않습니다. 알림을 보고 사람이 직접(또는 기존 도구로) 결제합니다.
"""
import argparse
import csv
import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = {
    'fee_rate': 0.10,          # 포이즌 판매 수수료율 (카테고리별로 다름, 판매자센터 기준으로 수정)
    'min_fee': 15000,          # 최소 수수료
    'shipping': 3000,          # 인천 검수센터까지 배송비
    'vat_refund': True,        # 일반과세자 수출 영세율: 매입 부가세(매입가/11) 환급
                               # (영수증에 부가세가 찍히는 매입처만 해당, SOURCE_VAT 참고)
    'card_discount': 0.0,      # 카드 할인·적립·상품권 등 실결제 할인율 (0.03 = 3%)
    'risk_rate': 0.0,          # 검수 불합격·페널티 대비 적립률 (판매가 대비, 0.02 = 2%)
    'min_profit': 10000,       # 알림 기준 최소 순이익
    'min_roi': 0.05,           # 알림 기준 최소 수익률 (순이익 / 매입가)
}
UA = {'User-Agent': 'Mozilla/5.0 (resell-scanner)'}


def load_config(path=None):
    cfg = dict(DEFAULT_CONFIG)
    path = Path(path) if path else ROOT / 'config.json'
    if path.exists():
        cfg.update(json.loads(path.read_text(encoding='utf-8')))
    return cfg


def poizon_fee(sell, cfg):
    return max(round(sell * cfg['fee_rate']), cfg['min_fee'])


def vat_share(cfg, vat_ok=True):
    return 1 / 11 if cfg['vat_refund'] and vat_ok else 0.0


def costs(sell, cfg):
    """매입가와 무관한 판매 비용: 수수료 + 배송비 + 리스크 적립."""
    return poizon_fee(sell, cfg) + cfg['shipping'] + sell * cfg.get('risk_rate', 0)


def profit(buy, sell, cfg, vat_ok=True):
    """순이익 = 판매가 - 비용 - 실결제액(매입가 - 카드할인) + 매입 부가세 환급."""
    paid = buy * (1 - cfg.get('card_discount', 0))
    return round(sell - costs(sell, cfg) - paid + buy * vat_share(cfg, vat_ok))


def min_fee_zone(sell, cfg):
    """최소 수수료가 적용되는 가격대인지 (이 구간은 수수료 비율이 급격히 커짐)."""
    return sell * cfg['fee_rate'] < cfg['min_fee']


def max_buy_price(sell, cfg, target_profit=None, vat_ok=True):
    """목표 순이익을 남길 수 있는 최대 매입가 (판매처 표시가 기준)."""
    target = cfg['min_profit'] if target_profit is None else target_profit
    return int((sell - costs(sell, cfg) - target) / (1 - cfg.get('card_discount', 0) - vat_share(cfg, vat_ok)))


def break_even_sell(buy, cfg, target=None, vat_ok=True):
    """목표 순이익을 남기려면 포이즌에서 최소 얼마에 팔아야 하는지 (원 단위 올림)."""
    target = cfg['min_profit'] if target is None else target
    base = target + cfg['shipping'] + buy * (1 - cfg.get('card_discount', 0)) - buy * vat_share(cfg, vat_ok)
    risk = cfg.get('risk_rate', 0)
    s = (base + cfg['min_fee']) / (1 - risk)          # 최소 수수료 구간
    if s * cfg['fee_rate'] >= cfg['min_fee']:
        s = base / (1 - cfg['fee_rate'] - risk)       # 비율 수수료 구간
    return int(-(-s // 100) * 100)


STYLE_RE = re.compile(r'/\s*([A-Z0-9]{2,}[A-Z0-9-]*\d[A-Z0-9-]*)\s*$')


NON_SHOE = ('팬츠', '자켓', '재킷', '티셔츠', '셔츠', '후드', '스웨트', '양말', '삭스', '모자', '캡', '가방', '백팩', '저지',
            '쇼츠', '레깅스', '져지', '조거', '베스트', '파카', '패딩', '크루', '탑', '드레스', '스커트')


def musinsa_candidates(items, cfg, n=10, min_discount=20, min_reviews=1, per_brand=3):
    """무신사 목록(JSON list)에서 품번이 있는 할인 신발을 골라 손익분기 포이즌 판매가와 함께 반환."""
    out, seen = [], set()
    for g in items:
        m = STYLE_RE.search(g.get('goodsName') or '')
        if not m or g.get('isSoldOut') or g.get('usedConditionGrade'):
            continue
        code = m.group(1)
        if any(w in g['goodsName'] for w in NON_SHOE):
            continue
        disc = g.get('finalDiscount') or g.get('saleRate') or 0
        if code in seen or disc < min_discount or (g.get('reviewCount') or 0) < min_reviews:
            continue
        seen.add(code)
        buy = int(g.get('finalPrice') or g.get('price'))
        be = break_even_sell(buy, cfg, vat_ok=SOURCE_VAT.get('musinsa', False))
        out.append({'style_code': code, 'name': g['goodsName'].rsplit('/', 1)[0].strip(),
                    'brand': g.get('brandName', ''), 'normal': g.get('normalPrice'), 'buy': buy, 'discount': disc,
                    'reviews': g.get('reviewCount') or 0, 'break_even': be,
                    'url': g.get('goodsLinkUrl') or f"https://www.musinsa.com/products/{g.get('goodsNo')}"})
    # 할인율 높고 리뷰(판매) 많은 순
    out.sort(key=lambda c: (c['discount'], c['reviews']), reverse=True)
    picked, count = [], {}
    for c in out:  # 한 브랜드가 목록을 독차지하지 않게
        if count.get(c['brand'], 0) < per_brand:
            picked.append(c)
            count[c['brand']] = count.get(c['brand'], 0) + 1
    return picked[:n]


def normalize_code(code):
    return re.sub(r'[^A-Z0-9]', '', (code or '').upper())


@dataclass
class Offer:
    source: str
    style_code: str
    name: str
    price: int
    url: str
    sold_out: bool = False


def musinsa_search(style_code, session=requests):
    """무신사 검색에서 품번이 상품명에 정확히 들어간 상품만 반환 (예: '덩크 로우 ... / DD1503-101')."""
    r = session.get('https://api.musinsa.com/api2/dp/v1/plp/goods', headers=UA, timeout=20, params={
        'keyword': style_code, 'gf': 'A', 'sortCode': 'PRICE_LOW', 'page': 1, 'size': 30, 'caller': 'SEARCH'})
    r.raise_for_status()
    want = normalize_code(style_code)
    offers = []
    for g in (r.json().get('data') or {}).get('list') or []:
        name = g.get('goodsName') or ''
        codes = {normalize_code(c) for c in re.split(r'[/\s]+', name) if c}
        if want not in codes or g.get('usedConditionGrade'):  # 중고는 포이즌 검수 대상 아님
            continue
        offers.append(Offer('musinsa', style_code, name, int(g.get('finalPrice') or g.get('price')),
                            g.get('goodsLinkUrl') or f"https://www.musinsa.com/products/{g.get('goodsNo')}",
                            bool(g.get('isSoldOut'))))
    return offers


SOURCES = {'musinsa': musinsa_search}
# 매입처별로 영수증에 부가세가 포함되는지 (False면 환급 없이 계산). 해외배송·병행수입 위주 판매처는 False로.
SOURCE_VAT = {'musinsa': True}


def read_watchlist(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        rows = [r for r in csv.DictReader(f) if (r.get('style_code') or '').strip()]
    for r in rows:
        r['style_code'] = r['style_code'].strip()
        r['poizon_price'] = int(str(r['poizon_price']).replace(',', ''))
    return rows


def evaluate(row, offers, cfg):
    live = [o for o in offers if not o.sold_out]
    if not live:
        return None
    sell = row['poizon_price']
    vat = lambda o: SOURCE_VAT.get(o.source, False)
    best = max(live, key=lambda o: profit(o.price, sell, cfg, vat(o)))  # 부가세 여부가 달라 최저가 ≠ 최고이익
    p = profit(best.price, sell, cfg, vat(best))
    return {
        'style_code': row['style_code'], 'name': row.get('name') or best.name, 'size': row.get('size', ''),
        'source': best.source, 'buy': best.price, 'sell': sell, 'fee': poizon_fee(sell, cfg),
        'profit': p, 'roi': round(p / best.price, 4), 'max_buy': max_buy_price(sell, cfg, vat_ok=vat(best)),
        'url': best.url, 'min_fee_zone': min_fee_zone(sell, cfg),
        'ok': p >= cfg['min_profit'] and p / best.price >= cfg['min_roi'],
    }


def scan(watchlist, cfg, sources=None, session=requests):
    sources = sources or SOURCES
    results, errors = [], []
    for row in watchlist:
        offers = []
        for name, fn in sources.items():
            try:
                offers += fn(row['style_code'], session=session)
            except Exception as e:  # 한 소스 실패가 전체 스캔을 멈추지 않게
                errors.append(f"{row['style_code']} {name}: {e}")
        res = evaluate(row, offers, cfg)
        if res:
            results.append(res)
    results.sort(key=lambda r: r['profit'], reverse=True)
    return results, errors


def fmt(n):
    return f'{n:,}원'


def report(results):
    lines = []
    for r in results:
        mark = '✅' if r['ok'] else '  '
        if r.get('min_fee_zone'):
            mark += '⚠최소수수료'
        lines.append(f"{mark} {r['style_code']} {r['size']} | 매입 {fmt(r['buy'])}({r['source']}) → 포이즌 {fmt(r['sell'])}"
                     f" | 순이익 {fmt(r['profit'])} ({r['roi']:.1%}) | 최대매입가 {fmt(r['max_buy'])}\n   {r['url']}")
    return '\n'.join(lines) or '조회된 상품 없음'


def notify_discord(results, webhook, session=requests):
    hits = [r for r in results if r['ok']]
    if not hits or not webhook:
        return 0
    for i in range(0, len(hits), 10):  # 디스코드 embed 한도 10개
        embeds = [{
            'title': f"{r['style_code']} {r['size']} 순이익 {fmt(r['profit'])} ({r['roi']:.1%})",
            'url': r['url'],
            'description': f"{r['name']}\n매입 {fmt(r['buy'])} ({r['source']}) → 포이즌 {fmt(r['sell'])}\n"
                           f"수수료 {fmt(r['fee'])} · 최대매입가 {fmt(r['max_buy'])}",
        } for r in hits[i:i + 10]]
        session.post(webhook, json={'content': '포이즌 마진 상품 발견', 'embeds': embeds}, timeout=20).raise_for_status()
    return len(hits)


def main(argv=None):
    ap = argparse.ArgumentParser(description='국내 매입 → 포이즌 판매 마진 스캐너')
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('scan', help='watchlist 전체 조회')
    s.add_argument('--watchlist', default=str(ROOT / 'watchlist.csv'))
    s.add_argument('--config')
    s.add_argument('--json', help='결과를 JSON 파일로 저장')
    s.add_argument('--no-notify', action='store_true')
    c = sub.add_parser('calc', help='마진 계산기')
    c.add_argument('buy', type=int)
    c.add_argument('sell', type=int)
    c.add_argument('--config')
    args = ap.parse_args(argv)
    cfg = load_config(args.config)

    if args.cmd == 'calc':
        print(f"수수료 {fmt(poizon_fee(args.sell, cfg))} / 순이익 {fmt(profit(args.buy, args.sell, cfg))}"
              f" / 최대매입가(목표 {fmt(cfg['min_profit'])}) {fmt(max_buy_price(args.sell, cfg))}")
        return 0

    results, errors = scan(read_watchlist(args.watchlist), cfg)
    print(report(results))
    for e in errors:
        print('경고:', e, file=sys.stderr)
    if args.json:
        Path(args.json).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    if not args.no_notify:
        sent = notify_discord(results, os.environ.get('DISCORD_WEBHOOK_URL'))
        if sent:
            print(f'디스코드 알림 {sent}건 전송')
    return 0


if __name__ == '__main__':
    sys.exit(main())
