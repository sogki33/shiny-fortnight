"""매일 아침 마진 후보 리포트 (휴대폰용 HTML).

무신사 검색 API 응답(JSON 파일들)을 받아 할인 신발 후보를 고르고,
포이즌에서 최소 얼마에 팔려야 목표 순이익이 남는지(손익분기 판매가)를 붙여 HTML로 만든다.

  python daily_report.py urls                       # 무신사 검색 URL
  python daily_report.py pool raw*.json -o pool.json  # 후보군 + 크림 검색 URL
  python daily_report.py products pool.json search_results*.json   # 크림 상품 URL
  python daily_report.py final pool.json product_results*.json -o report.html
"""
import argparse
import html
import json
from datetime import datetime, timedelta, timezone

import kream
import resell as r

KST = timezone(timedelta(hours=9))
# 매일 조회할 무신사 검색어 (할인율순)
KEYWORDS = ['나이키 스니커즈', '아디다스 스니커즈', '뉴발란스 스니커즈', '아식스 스니커즈', '살로몬 스니커즈',
            '오니츠카타이거 스니커즈', '호카 운동화', '온러닝 운동화', '푸마 스니커즈', '컨버스 스니커즈',
            '반스 스니커즈', '미즈노 스니커즈']


def musinsa_url(keyword, size=60):
    from urllib.parse import quote
    return ('https://api.musinsa.com/api2/dp/v1/plp/goods?keyword=' + quote(keyword) +
            f'&gf=A&sortCode=DISCOUNT_RATE&page=1&size={size}&caller=SEARCH')


def load_items(paths):
    items = []
    for p in paths:
        data = json.loads(open(p, encoding='utf-8').read())
        items += (data.get('data') or {}).get('list') or []
    return items


def won(n):
    return f'{int(n):,}원'


def read_results(paths):
    """fetch_content 결과 파일들 → {url: result}. 파일은 {"results": [...]} 또는 [...] 형식."""
    out = {}
    for p in paths:
        data = json.loads(open(p, encoding='utf-8').read())
        for res in (data.get('results') if isinstance(data, dict) else data) or []:
            out[res.get('url')] = res
            if res.get('final_url'):
                out[res['final_url']] = res
    return out


def build_pool(raw_paths, cfg, n=40):
    """무신사 목록에서 크림 시세를 확인할 후보군 (할인 10% 이상, 브랜드당 5개)."""
    return r.musinsa_candidates(load_items(raw_paths), cfg, n=n, min_discount=10, per_brand=5)


def attach_products(pool, search_results):
    for c in pool:
        res = search_results.get(kream.search_url(c['style_code']))
        c['kream_url'] = kream.product_from_search(res) if res else None
    return pool


def size_key(size):
    """'W235' / '235' / '235mm' → '235' (무신사·크림 사이즈 표기 맞추기)."""
    import re as _re
    m = _re.search(r'\d{2,3}(?:\.\d)?', str(size))
    return m.group(0) if m else str(size).strip().upper()


def apply_stock(winners, stock):
    """stock: {무신사 상품 URL: {"in_stock": [...], "sold_out": [...]}}. 재고 없는 사이즈 제거, 정보 없으면 '재고 미확인' 표시."""
    out = []
    for c in winners:
        info = stock.get(c['url'])
        if info is None:
            out.append(dict(c, stock_checked=False))
            continue
        avail = {size_key(s) for s in info.get('in_stock') or []}
        sizes = {sz: v for sz, v in c['sizes'].items() if size_key(sz) in avail}
        if sizes:
            out.append(dict(c, sizes=sizes, stock_checked=True,
                            best_profit=max(v['profit'] for v in sizes.values())))
    out.sort(key=lambda c: c['best_profit'], reverse=True)
    return out


def finalize(pool, product_results, cfg, n=10):
    """사이즈별 최근 체결가가 손익분기 이상인 상품만, 예상 순이익 큰 순으로."""
    vat_ok = r.SOURCE_VAT.get('musinsa', False)
    winners = []
    for c in pool:
        res = product_results.get(c.get('kream_url') or '')
        if not res:
            continue
        info = kream.parse_product(res.get('text') or '')
        if not info['model'] or r.normalize_code(c['style_code']) not in r.normalize_code(info['model']):
            continue  # 모델번호가 없거나 다르면 다른 상품일 수 있어 제외  # 다른 상품으로 연결된 경우 제외
        est = kream.instant_sell_estimate(info['trades'])
        # 크림 체결가로 크림에 되파는 순이익과, 같은 가격을 포이즌 판매가로 본 순이익 중 큰 쪽
        sizes = {}
        for sz, pr in est.items():
            kp, pp = kream.kream_profit(c['buy'], pr), r.profit(c['buy'], pr, cfg, vat_ok)
            best, ch = (kp, '크림') if kp >= pp else (pp, '포이즌')
            if best >= cfg['min_profit']:
                sizes[sz] = {'price': pr, 'profit': best, 'channel': ch}
        if not sizes:
            continue
        c = dict(c, kream=info, sizes=sizes)
        c['best_profit'] = max(v['profit'] for v in c['sizes'].values())
        winners.append(c)
    winners.sort(key=lambda c: c['best_profit'], reverse=True)
    return winners[:n]


def won(n):
    return f'{int(n):,}원'


def render(cands, cfg, now, checked=0):
    e = html.escape
    rows = []
    for i, c in enumerate(cands, 1):
        sizes = ''.join(f'<li><b>{e(sz)}</b> 체결 {won(v["price"])} → {v.get("channel", "")} 순이익 <b class="pf">{won(v["profit"])}</b></li>'
                        for sz, v in sorted(c['sizes'].items(), key=lambda kv: -kv[1]['profit']))
        k = c['kream']
        rows.append(f'''<li class="card">
  <div class="top"><span class="rank">{i}</span><span class="nm">{e(c['brand'])} · {e(c['name'])}</span></div>
  <div class="code">{e(c['style_code'])}</div>
  <dl>
    <dt>무신사 매입가</dt><dd>{won(c['buy'])} <b class="disc">{c['discount']}%</b></dd>
    <dt>손익분기 판매가</dt><dd>{won(c['break_even'])}</dd>
    <dt>크림 누적 거래</dt><dd>{(k['total_trades'] or 0):,}건</dd>
  </dl>
  <div class="szh">수익 나는 사이즈 (최근 30일 체결가 중 최저, 2건 이상) · {'무신사 재고 확인됨' if c.get('stock_checked') else '무신사 재고 미확인'}</div>
  <ul class="sizes">{sizes}</ul>
  <div class="acts"><a href="{e(c['url'])}" target="_blank" rel="noopener">무신사에서 사이즈 확인</a>
  <a href="{e(c['kream_url'])}" target="_blank" rel="noopener">크림 시세</a>
  <button type="button" data-copy="{e(c['style_code'])}">품번 복사</button></div>
</li>''')
    body = '\n'.join(rows) or '<li class="card">오늘은 실제 체결가 기준으로 수익이 나는 상품이 없습니다. 사지 마세요.</li>'
    return f'''<title>오늘의 포이즌 후보</title>
<meta name="claude:viewport-fit-sides" content="cover">
<style>
/* Layout: 한 손으로 넘겨 보는 카드 목록 */
:root {{ --bg:#f3f4f1; --surface:#fff; --fg:#1b1f1c; --muted:#616a63; --line:#d9ddd6; --accent:#0f7a55; --hot:#c0392b;
  --font:"Apple SD Gothic Neo","Malgun Gothic","Noto Sans KR",sans-serif; --num:ui-monospace,"SFMono-Regular",Menlo,monospace }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#121614; --surface:#1b211e; --fg:#e8ece9;
  --muted:#9aa49d; --line:#2c3430; --accent:#3ccf95; --hot:#ff7b6b; color-scheme:dark }} }}
:root[data-theme="dark"] {{ --bg:#121614; --surface:#1b211e; --fg:#e8ece9; --muted:#9aa49d; --line:#2c3430;
  --accent:#3ccf95; --hot:#ff7b6b; color-scheme:dark }}
* {{ box-sizing:border-box }}
body {{ background:var(--bg); color:var(--fg); font-family:var(--font); font-size:15px; line-height:1.5;
  padding-left:max(16px, env(safe-area-inset-left, 0px)); padding-right:max(16px, env(safe-area-inset-right, 0px)); padding-block:16px 40px }}
main {{ max-width:520px; margin:0 auto; display:grid; gap:14px }}
h1 {{ font-size:22px; margin:0 }} .sub {{ color:var(--muted); margin:0; font-size:13px }}
.how {{ background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:12px 14px; font-size:14px }}
.how ol {{ margin:6px 0 0; padding-left:20px }}
ul {{ list-style:none; margin:0; padding:0; display:grid; gap:10px }}
.card {{ background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:14px; display:grid; gap:6px; min-width:0 }}
.top {{ display:flex; gap:10px; align-items:baseline; min-width:0 }}
.rank {{ font:700 13px var(--num); color:var(--accent) }} .nm {{ font-weight:600; overflow-wrap:anywhere; min-width:0 }}
.code {{ font:600 14px var(--num); color:var(--muted) }}
dl {{ display:grid; grid-template-columns:auto 1fr; gap:4px 12px; margin:0 }} dt {{ color:var(--muted); font-size:13px }}
dd {{ margin:0; text-align:right; font-family:var(--num); font-variant-numeric:tabular-nums }}
.disc {{ color:var(--hot) }} .pf {{ color:var(--accent) }}
.szh {{ font-size:13px; color:var(--muted); margin-top:4px }}
.sizes {{ gap:2px; font-family:var(--num); font-size:14px; font-variant-numeric:tabular-nums }}
.acts {{ display:flex; gap:8px; flex-wrap:wrap; margin-top:4px }}
.acts a, .acts button {{ font:600 14px var(--font); border:1px solid var(--line); border-radius:8px; padding:8px 12px;
  background:var(--bg); color:var(--fg); text-decoration:none; cursor:pointer }}
a:focus-visible, button:focus-visible {{ outline:2px solid var(--accent); outline-offset:2px }}
.foot {{ color:var(--muted); font-size:12px; margin:0 }}
</style>
<main>
  <header><h1>오늘의 포이즌 후보</h1>
  <p class="sub">{now:%Y년 %m월 %d일 %H:%M} 기준 · {checked}개 상품의 실제 체결가를 확인해 수익 나는 {len(cands)}개만 남김</p></header>
  <div class="how"><b>기준</b><ol>
    <li>무신사에서 지금 살 수 있는 가격으로 매입.</li>
    <li>사이즈별 최근 30일 체결이 2건 이상이고, 그중 <b>가장 낮은</b> 체결가도 손익분기(순이익 {won(cfg['min_profit'])}) 이상인 사이즈만 표시.</li>\n    <li><b>실제 즉시판매가(구매 입찰 최고가)는 크림 로그인 후에만 보여 확인하지 못했습니다. 사기 전에 크림 앱에서 그 사이즈 구매 입찰가를 꼭 확인하세요.</b></li>
    <li>무신사에 그 사이즈 재고가 있는지, 포이즌 앱 시세도 같은지 확인한 뒤 사세요.</li></ol></div>
  <ul>{body}</ul>
  <p class="foot">계산: 수수료 {cfg['fee_rate']:.0%}(최소 {won(cfg['min_fee'])}), 배송비 {won(cfg['shipping'])},
  부가세 환급 {'반영' if cfg['vat_refund'] else '미반영'}. 판매가는 크림(국내) 최근 체결가이며 포이즌 시세와 다를 수 있습니다.</p>
</main>
<script>
document.querySelectorAll('[data-copy]').forEach(b => b.addEventListener('click', () => {{
  const t = b.dataset.copy, done = () => {{ b.textContent = '복사됨'; setTimeout(() => b.textContent = '품번 복사', 1200); }};
  (navigator.clipboard ? navigator.clipboard.writeText(t) : Promise.reject()).then(done).catch(() => {{
    const r = document.createRange(); r.selectNodeContents(b.closest('.card').querySelector('.code'));
    const s = getSelection(); s.removeAllRanges(); s.addRange(r); }});
}}));
</script>
'''


def main(argv=None):
    ap = argparse.ArgumentParser(description='1) urls → 2) pool → 3) products → 4) final')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('urls', help='무신사 검색 URL 출력')
    p = sub.add_parser('pool', help='무신사 raw JSON → 후보군 + 크림 검색 URL 출력')
    p.add_argument('raw', nargs='+'); p.add_argument('-o', default='pool.json')
    p = sub.add_parser('products', help='크림 검색 결과 → 상품 URL 출력')
    p.add_argument('pool'); p.add_argument('results', nargs='+')
    p = sub.add_parser('final', help='크림 상품 페이지 → 수익 상품 리포트')
    p.add_argument('pool'); p.add_argument('results', nargs='+'); p.add_argument('-o', default='report.html')
    p.add_argument('--stock', help='무신사 사이즈 재고 JSON {상품URL: {"in_stock": [...]}}')
    p = sub.add_parser('winners', help='수익 상품의 무신사 URL과 수익 사이즈 출력 (재고 확인용)')
    p.add_argument('pool'); p.add_argument('results', nargs='+')
    a = ap.parse_args(argv)
    cfg = r.load_config()
    if a.cmd == 'urls':
        print('\n'.join(musinsa_url(k) for k in KEYWORDS))
    elif a.cmd == 'pool':
        pool = build_pool(a.raw, cfg)
        open(a.o, 'w', encoding='utf-8').write(json.dumps(pool, ensure_ascii=False))
        print('\n'.join(kream.search_url(c['style_code']) for c in pool))
    elif a.cmd == 'products':
        pool = attach_products(json.load(open(a.pool, encoding='utf-8')), read_results(a.results))
        open(a.pool, 'w', encoding='utf-8').write(json.dumps(pool, ensure_ascii=False))
        print('\n'.join(c['kream_url'] for c in pool if c.get('kream_url')))
    elif a.cmd == 'winners':
        pool = json.load(open(a.pool, encoding='utf-8'))
        for c in finalize(pool, read_results(a.results), cfg, n=30):
            print(c['url'], ','.join(c['sizes']))
    else:
        pool = json.load(open(a.pool, encoding='utf-8'))
        win = finalize(pool, read_results(a.results), cfg, n=30)
        if a.stock:
            win = apply_stock(win, json.load(open(a.stock, encoding='utf-8')))
        win = win[:10]
        checked = sum(1 for c in pool if c.get('kream_url'))
        open(a.o, 'w', encoding='utf-8').write(render(win, cfg, datetime.now(KST), checked))
        print(f'{checked}개 확인 → 수익 상품 {len(win)}개 → {a.o}')
        for c in win:
            szs = ', '.join(f"{sz} {v['price']:,}(+{v['profit']:,})" for sz, v in c['sizes'].items())
            print(f"{c['style_code']:14} 매입 {c['buy']:>9,}  손익분기 {c['break_even']:>9,}  {c['name']} | {szs}")


if __name__ == '__main__':
    main()
