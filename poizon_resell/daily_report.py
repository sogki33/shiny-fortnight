"""매일 아침 마진 후보 리포트 (휴대폰용 HTML).

무신사 검색 API 응답(JSON 파일들)을 받아 할인 신발 후보를 고르고,
포이즌에서 최소 얼마에 팔려야 목표 순이익이 남는지(손익분기 판매가)를 붙여 HTML로 만든다.

  python daily_report.py raw1.json raw2.json ... -o report.html
"""
import argparse
import html
import json
from datetime import datetime, timedelta, timezone

import resell as r

KST = timezone(timedelta(hours=9))
# 매일 조회할 무신사 검색어 (할인율순)
KEYWORDS = ['나이키 스니커즈', '아디다스 스니커즈', '뉴발란스 스니커즈', '아식스 스니커즈', '살로몬 스니커즈']


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


def render(cands, cfg, now):
    rows = []
    for i, c in enumerate(cands, 1):
        e = html.escape
        rows.append(f'''<li class="card">
  <div class="top"><span class="rank">{i}</span><span class="nm">{e(c['brand'])} · {e(c['name'])}</span></div>
  <div class="code">{e(c['style_code'])}</div>
  <dl>
    <dt>무신사 가격</dt><dd>{won(c['buy'])} <s>{won(c['normal'])}</s> <b class="disc">{c['discount']}%</b></dd>
    <dt>포이즌 손익분기</dt><dd class="be">{won(c['break_even'])} 이상</dd>
    <dt>리뷰</dt><dd>{c['reviews']:,}개</dd>
  </dl>
  <div class="acts"><a href="{e(c['url'])}" target="_blank" rel="noopener">무신사에서 보기</a>
  <button type="button" data-copy="{e(c['style_code'])}">품번 복사</button></div>
</li>''')
    body = '\n'.join(rows) or '<li class="card">오늘은 조건에 맞는 할인 상품이 없습니다.</li>'
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
s {{ color:var(--muted); font-size:12px }} .disc {{ color:var(--hot) }} .be {{ font-weight:700; color:var(--accent) }}
.acts {{ display:flex; gap:8px; flex-wrap:wrap }}
.acts a, .acts button {{ font:600 14px var(--font); border:1px solid var(--line); border-radius:8px; padding:8px 12px;
  background:var(--bg); color:var(--fg); text-decoration:none; cursor:pointer }}
a:focus-visible, button:focus-visible {{ outline:2px solid var(--accent); outline-offset:2px }}
.foot {{ color:var(--muted); font-size:12px; margin:0 }}
</style>
<main>
  <header><h1>오늘의 포이즌 후보</h1>
  <p class="sub">{now:%Y년 %m월 %d일 %H:%M} 기준 · 무신사 할인 신발 {len(cands)}개</p></header>
  <div class="how"><b>쓰는 법</b><ol>
    <li>품번을 복사해 포이즌 앱에서 검색합니다.</li>
    <li>사이즈별 판매가가 <b>손익분기 가격 이상</b>이면 순이익 {won(cfg['min_profit'])} 이상 남습니다.</li>
    <li>최근 거래량도 꼭 확인하세요. 안 팔리면 재고가 됩니다.</li></ol></div>
  <ul>{body}</ul>
  <p class="foot">계산 기준: 수수료 {cfg['fee_rate']:.0%}(최소 {won(cfg['min_fee'])}), 배송비 {won(cfg['shipping'])},
  부가세 환급 {'반영' if cfg['vat_refund'] else '미반영'}. 무신사 가격은 쿠폰·적립 전 가격입니다. 포이즌 시세는 자동으로 확인하지 않았습니다.</p>
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
    ap = argparse.ArgumentParser()
    ap.add_argument('json_files', nargs='*')
    ap.add_argument('-o', '--out', default='report.html')
    ap.add_argument('-n', type=int, default=10)
    ap.add_argument('--urls', action='store_true', help='조회할 무신사 URL만 출력')
    a = ap.parse_args(argv)
    if a.urls:
        print('\n'.join(musinsa_url(k) for k in KEYWORDS))
        return
    cfg = r.load_config()
    cands = r.musinsa_candidates(load_items(a.json_files), cfg, n=a.n)
    open(a.out, 'w', encoding='utf-8').write(render(cands, cfg, datetime.now(KST)))
    print(f'{len(cands)}개 후보 → {a.out}')
    for c in cands:
        print(f"{c['style_code']:14} {c['discount']:>3}%  매입 {c['buy']:>9,}  손익분기 {c['break_even']:>9,}  {c['name']}")


if __name__ == '__main__':
    main()
