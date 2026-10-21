"""무신사 부티크(명품) 상품 → 크림 즉시판매 시 수익 나는 사이즈 찾기.

  python boutique.py urls                                 # 브랜드별 무신사 검색 URL
  python boutique.py pool raw*.json -o pool.json          # 후보군 + 크림 검색 URL
  python daily_report.py products pool.json search*.json  # 크림 상품 URL (공용)
  python boutique.py final pool.json product*.json -o boutique.html
"""
import argparse
import html
import json
from datetime import datetime
from urllib.parse import quote

import daily_report as d
import kream
import resell as r

BRANDS = ['구찌', '프라다', '미우미우', '발렌시아가', '생로랑', '보테가베네타', '메종마르지엘라', '셀린느', '로에베',
          '버버리', '몽클레르', '골든구스', '알렉산더맥퀸', '지방시', '발렌티노', '톰브라운', '스톤아일랜드',
          '아크네스튜디오', '메종키츠네', '르메르', '질샌더', '마르니', '펜디', '아미']


def musinsa_url(keyword, size=100):
    return ('https://api.musinsa.com/api2/dp/v1/plp/goods?keyword=' + quote(keyword) +
            f'&gf=A&sortCode=DISCOUNT_RATE&page=1&size={size}&caller=SEARCH&storeCode=boutique')


def build_pool(raw_paths, per_brand=15):
    """품번 있는 상품 중 브랜드별 할인율 상위. 매입가 대비 수익은 크림 시세로 판단하므로 손익분기는 크림 기준으로 계산."""
    cands = r.musinsa_candidates(d.load_items(raw_paths), r.load_config(), n=10_000, min_discount=0,
                                 min_reviews=0, per_brand=per_brand)
    for c in cands:
        c['break_even'] = kream_break_even(c['buy'])
    return cands


RANKING_URL = ('https://api.musinsa.com/api2/hm/web/v5/pans/ranking?storeCode=boutique&sectionId=200'
               '&categoryCode=000&gf=A&ageBand=AGE_BAND_ALL&period=DAILY')


def parse_ranking(text):
    """부티크 랭킹 API 응답 → 순위대로 상품 목록."""
    j = json.loads(text)
    items = [it for m in j['data']['modules'] if m.get('type') == 'MULTICOLUMN'
             for it in m.get('items', []) if it.get('type') == 'PRODUCT_COLUMN']
    out, seen = [], set()
    for it in items:
        if it['id'] in seen:
            continue
        seen.add(it['id'])
        info = it['info']
        out.append({'rank': len(out) + 1, 'goods_no': it['id'], 'brand': info.get('brandName', ''),
                    'name': info.get('productName', ''), 'buy': int(info.get('finalPrice') or 0),
                    'discount': info.get('discountRatio') or 0,
                    'url': f"https://www.musinsa.com/products/{it['id']}"})
    return out


def style_code_from_page(result):
    """무신사 상품 페이지(fetch 결과)의 설명/제목에서 제품번호."""
    import re
    for field in (result.get('description') or '', result.get('title') or '', result.get('text') or ''):
        m = re.search(r'제품번호\s*:?\s*([A-Za-z0-9][A-Za-z0-9\- ]{3,30}?)(?:\s+제품|\s*$|\s*-\s|\n)', field)
        if m:
            return m.group(1).strip()
    return None


def kream_break_even(buy, target=10000):
    s = buy + target
    while kream.kream_profit(buy, s) < target:  # 수수료가 구간식이라 단순 반복으로 찾는다
        s += 1000
    return s


def finalize(pool, product_results, target=10000):
    winners = []
    for c in pool:
        res = product_results.get(c.get('kream_url') or '')
        if not res:
            continue
        info = kream.parse_product(res.get('text') or '')
        if info['model'] and r.normalize_code(c['style_code']) not in r.normalize_code(info['model']):
            continue
        sizes = {sz: {'price': p, 'profit': kream.kream_profit(c['buy'], p)}
                 for sz, p in kream.instant_sell_estimate(info['trades']).items()}
        sizes = {sz: v for sz, v in sizes.items() if v['profit'] >= target}
        if sizes:
            winners.append(dict(c, kream=info, sizes=sizes, best_profit=max(v['profit'] for v in sizes.values())))
    winners.sort(key=lambda c: c['best_profit'], reverse=True)
    return winners


def render(win, checked, now):
    e = html.escape
    cards = []
    for i, c in enumerate(win, 1):
        sizes = ''.join(f'<li><b>{e(sz)}</b> 즉판 추정 {d.won(v["price"])} → 순이익 <b class="pf">{d.won(v["profit"])}</b></li>'
                        for sz, v in sorted(c['sizes'].items(), key=lambda kv: -kv[1]['profit']))
        cards.append(f'''<li class="card"><div class="top"><span class="rank">{i}</span><span class="nm">{e(c['brand'])} · {e(c['name'])}</span></div>
  <div class="code">{e(c['style_code'])}</div>
  <dl><dt>무신사 매입가</dt><dd>{d.won(c['buy'])} <b class="disc">{c['discount']}%</b></dd>
  <dt>크림 누적 거래</dt><dd>{(c['kream']['total_trades'] or 0):,}건</dd></dl>
  <ul class="sizes">{sizes}</ul>
  <div class="acts"><a href="{e(c['url'])}" target="_blank" rel="noopener">무신사</a>
  <a href="{e(c['kream_url'])}" target="_blank" rel="noopener">크림</a></div></li>''')
    page = d.render([], r.load_config(), now, checked)
    head = page[:page.index('<main>')].replace('오늘의 포이즌 후보', '부티크 → 크림 즉판')
    body = '\n'.join(cards) or '<li class="card">수익 나는 상품이 없습니다.</li>'
    return head + f'''<main><header><h1>부티크 → 크림 즉판</h1>
<p class="sub">{now:%Y년 %m월 %d일 %H:%M} 기준 · 크림에서 {checked}개 확인 → 수익 {len(win)}개</p></header>
<div class="how"><b>기준</b><ol><li>무신사 부티크 현재 판매가로 매입.</li>
<li>즉시판매가는 크림 최근 체결가 중 사이즈별 <b>가장 낮은 값</b>으로 보수적으로 추정.</li>
<li>크림 수수료 2026.3 기준(일반 6%+2,500원 / 프리미엄 3%+20,000원 중 큰 쪽, 부가세 포함), 발송비 3,500원, 개인 판매 기준.</li>
<li>순이익 10,000원 이상 사이즈만. 무신사 사이즈 재고와 크림 실제 구매입찰가는 사기 전에 확인하세요.</li></ol></div>
<ul>{body}</ul></main>'''


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('urls')
    sub.add_parser('ranking-url')
    p = sub.add_parser('rank', help='랭킹 응답(fetch 결과 파일) → 순위 목록, 무신사 상품 URL 출력')
    p.add_argument('results'); p.add_argument('-o', default='pool.json')
    p = sub.add_parser('codes', help='무신사 상품 페이지 → 제품번호 붙이고 크림 검색 URL 출력')
    p.add_argument('pool'); p.add_argument('results', nargs='+')
    p = sub.add_parser('pool'); p.add_argument('raw', nargs='+'); p.add_argument('-o', default='pool.json')
    p = sub.add_parser('final'); p.add_argument('pool'); p.add_argument('results', nargs='+'); p.add_argument('-o', default='boutique.html')
    a = ap.parse_args(argv)
    if a.cmd == 'urls':
        print('\n'.join(musinsa_url(b) for b in BRANDS))
    elif a.cmd == 'ranking-url':
        print(RANKING_URL)
    elif a.cmd == 'rank':
        res = d.read_results([a.results])
        text = next(v['text'] for k, v in res.items() if 'ranking' in (k or ''))
        pool = parse_ranking(text)
        open(a.o, 'w', encoding='utf-8').write(json.dumps(pool, ensure_ascii=False))
        print('\n'.join(c['url'] for c in pool))
    elif a.cmd == 'codes':
        pool = json.load(open(a.pool, encoding='utf-8'))
        pages = d.read_results(a.results)
        for c in pool:
            res = pages.get(c['url'])
            c['style_code'] = style_code_from_page(res) if res else None
            if c['style_code']:
                c['break_even'] = kream_break_even(c['buy'])
        pool = [c for c in pool if c.get('style_code')]
        open(a.pool, 'w', encoding='utf-8').write(json.dumps(pool, ensure_ascii=False))
        print('\n'.join(kream.search_url(c['style_code']) for c in pool))
    elif a.cmd == 'pool':
        pool = build_pool(a.raw)
        open(a.o, 'w', encoding='utf-8').write(json.dumps(pool, ensure_ascii=False))
        print('\n'.join(kream.search_url(c['style_code']) for c in pool))
    else:
        pool = json.load(open(a.pool, encoding='utf-8'))
        win = finalize(pool, d.read_results(a.results))
        checked = sum(1 for c in pool if c.get('kream_url'))
        open(a.o, 'w', encoding='utf-8').write(render(win, checked, datetime.now(d.KST)))
        print(f'{checked}개 확인 → 수익 {len(win)}개 → {a.o}')
        for c in win:
            szs = ', '.join(f"{sz} {v['price']:,}(+{v['profit']:,})" for sz, v in c['sizes'].items())
            print(f"{c['style_code']:18} 매입 {c['buy']:>10,}  {c['brand']} {c['name']} | {szs}")


if __name__ == '__main__':
    main()
