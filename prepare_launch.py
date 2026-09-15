"""Prepare the four user-authorized launch posts; never publish from this script."""
import json
from pathlib import Path
from automation import validate, DISCLOSURE

root = Path(__file__).parent
queue = json.loads((root / 'data/queue.json').read_text(encoding='utf-8'))
base = 'https://raw.githubusercontent.com/sogki33/shiny-fortnight/main/assets/'
posts = [
    ('intro-v1', '2026-09-16T08:30:00+09:00', 'intro-phone-v2.png',
     '여긴 대놓고 쿠팡파트너스 하는 계정이야.\n근데 장바구니까지 따라가서 등 떠밀진 않을게 ㅋㅋ\n\n“이걸 왜 사?”에 답이 있는 물건,\n안 사도 써먹는 생활 팁,\n그냥 웃겨서 보여주고 싶은 것도 올릴 거야.\n\n직접 써본 것과 찾아본 건 구분하고\n아쉬운 점도 같이 적을게.\n\n살림에서 제일 귀찮은 일 하나만 꼽으면 뭐야?\n\n사진은 AI 연출 이미지.'),
    ('chair-humor-v1', '2026-09-16T12:30:00+09:00', 'chair-phone-v2.png',
     '의자 샀는데\n옷이 더 오래 앉아 있음 ㅋㅋ\n\n빨기엔 애매하고\n옷장에 넣기엔 찝찝한\n“한 번 입은 옷” 전용 좌석.\n\n너희 집도 의자 하나쯤은\n본업 잃고 일하는 중이야?\n\n사진은 AI 연출 이미지.'),
    ('drawer-tip-v1', '2026-09-16T20:30:00+09:00', 'drawer-phone-v2.png',
     '정리하려고 수납함 샀는데\n그 수납함 둘 자리가 없는 상황 ㅋㅋ\n\n새로 사기 전에 이렇게 해보자.\n서랍 한 칸만 비우고 → 버릴 것 빼고 → 남은 걸 종류별로.\n\n집에 있는 작은 빈 상자로 며칠 나눠 써보면\n어떤 칸이 필요한지 감이 와.\n그다음 서랍 안쪽 치수 재고 골라도 늦지 않지.\n\n오늘은 물건 말고 자리부터 만들자.\n\n사진은 AI 연출 이미지.'),
    ('atojet-kitchen-v1', '2026-09-17T08:30:00+09:00', 'faucet-phone-v2.png',
     '주방 필터 살 때\n후기보다 먼저 볼 것: 우리 집에 맞나? ㅋㅋ\n\n오늘 후보는 아토젯 클렌징 주방 핸디형 세트.\n헤드필터 3개·바디필터 6개 구성이라 눈에 들어왔어.\n\n장바구니 넣기 전에 수전 연결부랑\n상세페이지 호환 안내부터 비교해봐.\n\n사진은 AI 연출 이미지.\n' + DISCLOSURE + '\nhttps://link.coupang.com/a/g4ntewoJ40'),
]
for pid, due, asset, caption in posts:
    item = dict(id=pid, status='approved', reviewed_by='Codex editorial review; user authorized five-post plan',
                not_before=due, media_type='IMAGE', media_url=base+asset,
                media_rights='Original AI-generated illustrative image', text=caption)
    if pid == 'atojet-kitchen-v1':
        item.update(product_id=6258651182, affiliate_url='https://link.coupang.com/a/g4ntewoJ40')
    validate(item)
    queue = [p for p in queue if p['id'] != pid] + [item]
(root/'data/queue.json').write_text(json.dumps(queue,ensure_ascii=False,indent=2),encoding='utf-8')
sections = ['# 첫 5개 게시물 구성', '기존 스팀다리미 글 1개 게시 완료. 아래 4개는 한국시간 기준 예약이며 GitHub 실행 지연이 있을 수 있습니다.']
for pid, due, asset, caption in posts:
    sections.append(f'## {due}\n\n![{pid}](assets/{asset})\n\n{caption}')
sections.append('## 이미지 제작\n\n내장 imagegen 사용. 네일아트한 손이 등장하는 평범한 집의 실내등·비스듬한 휴대폰 시점. 의자 위 한 번 입은 옷, 빈 상자로 칸을 나눈 서랍, 실제 상품 외형을 참조한 미설치 주방 필터. 모든 사진은 연출 이미지이며 실제 사용 경험으로 표현하지 않았습니다.')
(root/'LAUNCH_PLAN.md').write_text('\n\n'.join(sections),encoding='utf-8')
print('Prepared',len(posts),'posts; total queue',len(queue))
