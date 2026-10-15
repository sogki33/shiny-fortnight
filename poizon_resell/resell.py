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


def vat_share(cfg):
    return 1 / 11 if cfg['vat_refund'] else 0.0


def profit(buy, sell, cfg):
    """순이익 = 판매가 - 수수료 - 배송비 - 매입가 + 매입 부가세 환급."""
    return round(sell - poizon_fee(sell, cfg) - cfg['shipping'] - buy + buy * vat_share(cfg))


def max_buy_price(sell, cfg, target_profit=None):
    """목표 순이익을 남길 수 있는 최대 매입가."""
    target = cfg['min_profit'] if target_profit is None else target_profit
    return int((sell - poizon_fee(sell, cfg) - cfg['shipping'] - target) / (1 - vat_share(cfg)))


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
    best = min(live, key=lambda o: o.price)
    sell = row['poizon_price']
    p = profit(best.price, sell, cfg)
    return {
        'style_code': row['style_code'], 'name': row.get('name') or best.name, 'size': row.get('size', ''),
        'source': best.source, 'buy': best.price, 'sell': sell, 'fee': poizon_fee(sell, cfg),
        'profit': p, 'roi': round(p / best.price, 4), 'max_buy': max_buy_price(sell, cfg), 'url': best.url,
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
