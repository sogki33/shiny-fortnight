"""
쓰레드 × 쿠팡 파트너스 자동 발행 봇 (국산 원재료 식품 전용)
흐름: 키워드 선택 → 쿠팡 파트너스 상품검색 API → 중복 제외 상품 선택
      → Claude로 글 생성 → 쓰레드에 이미지+본문 발행 → 댓글로 파트너스 링크+대가성 문구

환경변수
  COUPANG_ACCESS_KEY, COUPANG_SECRET_KEY   쿠팡 파트너스 API 키
  THREADS_USER_ID, THREADS_ACCESS_TOKEN    쓰레드 API (장기 토큰)
  ANTHROPIC_API_KEY                        글 생성 (없으면 템플릿 문구 사용)
  CLAUDE_MODEL                             기본 claude-sonnet-4-5
  DRY_RUN=1                                API 호출 없이 가짜 상품으로 글만 출력
"""
import hashlib
import hmac
import json
import os
import random
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import requests
from origin_review import approved

BASE = Path(__file__).parent
STATE_FILE = BASE / "data" / "posted.json"
KEYWORDS_FILE = BASE / "keywords.txt"

DISCLOSURE = "쿠팡파트너스 활동의 일환으로 수수료를 제공받습니다."
DRY_RUN = os.getenv("DRY_RUN") == "1"
THREADS_API = "https://graph.threads.net/v1.0"
THREADS_TEXT_LIMIT = 500


# ---------------- 쿠팡 파트너스 ----------------
COUPANG_DOMAIN = "https://api-gateway.coupang.com"
SEARCH_PATH = "/v2/providers/affiliate_open_api/apis/openapi/v1/products/search"


def coupang_auth(method: str, path: str, query: str) -> str:
    signed_date = datetime.now(timezone.utc).strftime("%y%m%dT%H%M%SZ")
    message = signed_date + method + path + query
    signature = hmac.new(
        os.environ["COUPANG_SECRET_KEY"].encode(), message.encode(), hashlib.sha256
    ).hexdigest()
    return (
        f"CEA algorithm=HmacSHA256, access-key={os.environ['COUPANG_ACCESS_KEY']}, "
        f"signed-date={signed_date}, signature={signature}"
    )


def search_products(keyword: str, limit: int = 10) -> list[dict]:
    if DRY_RUN:
        return [{
            "productId": random.randint(1, 10**9),
            "productName": f"[테스트] 국내산 {keyword} 1kg",
            "productPrice": 19900,
            "productImage": "https://example.com/sample.jpg",
            "productUrl": "https://link.coupang.com/a/TEST",
            "isRocket": True,
        }]
    query = f"keyword={urllib.parse.quote(keyword)}&limit={limit}"
    headers = {
        "Authorization": coupang_auth("GET", SEARCH_PATH, query),
        "Content-Type": "application/json;charset=UTF-8",
    }
    r = requests.get(f"{COUPANG_DOMAIN}{SEARCH_PATH}?{query}", headers=headers, timeout=20)
    r.raise_for_status()
    body = r.json()
    if body.get("rCode") not in (None, "0"):
        raise RuntimeError(f"쿠팡 API 오류: {body}")
    return body.get("data", {}).get("productData", []) or []


# ---------------- 상태(중복 방지) ----------------
def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"products": [], "keyword_idx": 0, "log": []}


def save_state(state: dict) -> None:
    state["products"] = state["products"][-2000:]
    state["log"] = state["log"][-300:]
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def load_keywords() -> list[str]:
    lines = KEYWORDS_FILE.read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in lines if l.strip() and not l.startswith("#")]


def pick_product(state: dict) -> tuple[str, dict]:
    reviews = json.loads((BASE / "data" / "origin_reviews.json").read_text(encoding="utf-8"))
    if not reviews:
        raise RuntimeError("전체 원재료 국산 검증 상품이 없습니다. 원재료 표시 검토 후 origin_reviews.json에 등록하세요. 게시하지 않습니다.")
    keywords = load_keywords()
    posted = set(map(str, state["products"]))
    # 쿠팡 검색 API는 시간당 호출 제한이 빡빡하므로 실행당 최대 3개 키워드만 시도
    for _ in range(3):
        kw = keywords[state["keyword_idx"] % len(keywords)]
        state["keyword_idx"] += 1
        items = [p for p in search_products(kw)
                 if str(p.get("productId")) not in posted and approved(p, reviews)]
        items.sort(key=lambda p: not p.get("isRocket"))  # 로켓배송 우선
        if items:
            return kw, random.choice(items[:3])
    raise RuntimeError("새로 올릴 국산 상품을 찾지 못함 (keywords.txt에 키워드 추가 필요)")


# ---------------- 글 생성 ----------------
HOOK_TYPES = [
    "원산지 표시 읽는 법 (예: '국산'과 '국내 제조'는 다른 말이라는 사실)",
    "국산이 비싼 이유를 납득시키기 (생산량·인건비·제철 등 일반적인 이유)",
    "장보기 공감 (뒷면 원산지부터 뒤집어보는 습관, 부모님 드릴 선물 고민)",
    "제철·산지 이야기 (지금이 제철인 산지 식재료)",
    "먹는 법 제안 (이 재료로 만드는 간단한 한 끼)",
]

PROMPT = """너는 쓰레드(Threads)에서 '원산지 확인하고 사는 국산 먹거리'를 소개하는 장보기 고수 계정이야.
아래 쿠팡 식품으로 쓰레드 본문을 써줘. 이번 글의 후킹 유형: {hook}

톤 원칙 (욕 안 먹고 신뢰 쌓기)
- 다른 나라·수입산을 깎아내리지 말고 "국산을 고르는 이유/방법"으로만 말할 것
- 특정 국가·국민을 조롱하거나 비하, 공포 조장("중국산 먹으면 큰일" 류) 절대 금지
- "원산지 따지는 사람" 입장에서 담백하게, 가르치려 들지 말고 공감형으로

형식 규칙
- 350자 이내, 반말 섞인 친근한 말투, 이모지 1~2개
- 첫 줄: 후킹 유형에 맞춘, 스크롤을 멈추게 하는 한 문장
- 원산지는 상품명에 적힌 표현(국산/국내산/지역명)만 그대로 언급. "100% 국산", "무첨가" 등 상품명에 없는 표현 금지
- 질병 예방·치료, 다이어트, 면역력 같은 건강 효능 표현 금지 (식품표시광고법)
- 확인되지 않은 수치·통계·뉴스·후기·"내가 먹어봤다" 경험담 지어내지 마
- 가격은 변동되니 구체 금액 쓰지 말 것
- 링크·URL·해시태그 넣지 말 것 (링크는 댓글에 따로 달림)
- 마지막 줄: "👇 제품 정보는 댓글에"
- 본문만 출력

키워드: {kw}
상품명: {name}
로켓배송: {rocket}"""


def generate_text(kw: str, p: dict) -> str:
    if os.getenv("ANTHROPIC_API_KEY") and not DRY_RUN:
        import anthropic
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5"),
            max_tokens=600,
            messages=[{"role": "user", "content": PROMPT.format(
                hook=random.choice(HOOK_TYPES), kw=kw, name=p["productName"], rocket="예" if p.get("isRocket") else "아니오")}],
        )
        text = msg.content[0].text.strip()
    else:
        text = (f"장볼 때 원산지 뒷면까지 보는 사람? 🙋\n\n"
                f"오늘의 국산 먹거리: {p['productName']}\n"
                f"{'로켓배송 표시 상품' if p.get('isRocket') else ''}\n\n"
                "👇 제품 정보는 댓글에")
    suffix = f"\n\n#광고\n{DISCLOSURE}"
    return text[:THREADS_TEXT_LIMIT - len(suffix)] + suffix


def reply_text(p: dict) -> str:
    return f"{p['productName'][:80]}\n{p['productUrl']}\n\n{DISCLOSURE}"


# ---------------- 쓰레드 발행 ----------------
def threads_post(params: dict) -> str:
    uid, token = os.environ["THREADS_USER_ID"], os.environ["THREADS_ACCESS_TOKEN"]
    r = requests.post(f"{THREADS_API}/{uid}/threads", data={**params, "access_token": token}, timeout=30)
    r.raise_for_status()
    creation_id = r.json()["id"]
    time.sleep(30)  # Meta 권장: 컨테이너 처리 대기
    r = requests.post(f"{THREADS_API}/{uid}/threads_publish",
                      data={"creation_id": creation_id, "access_token": token}, timeout=30)
    r.raise_for_status()
    return r.json()["id"]


def publish(text: str, image_url: str | None, reply: str) -> str:
    if DRY_RUN:
        print("=== 본문 ===\n" + text + "\n=== 댓글 ===\n" + reply)
        return "dry-run"
    try:
        main_id = threads_post({"media_type": "IMAGE", "image_url": image_url, "text": text})
    except requests.HTTPError as e:
        print("이미지 발행 실패 → 텍스트로 재시도:", e.response.text if e.response is not None else e)
        main_id = threads_post({"media_type": "TEXT", "text": text})
    threads_post({"media_type": "TEXT", "text": reply, "reply_to_id": main_id})
    return main_id


def refresh_token() -> None:
    """장기 토큰(60일) 연장. 결과 토큰을 출력 → 워크플로에서 시크릿 갱신."""
    r = requests.get("https://graph.threads.net/refresh_access_token", params={
        "grant_type": "th_refresh_token", "access_token": os.environ["THREADS_ACCESS_TOKEN"]}, timeout=30)
    r.raise_for_status()
    data = r.json()
    print(f"::add-mask::{data['access_token']}")
    Path(os.getenv("TOKEN_OUT", "new_token.txt")).write_text(data["access_token"])
    print(f"토큰 갱신 완료, 남은 기간 {int(data['expires_in']) // 86400}일")


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "refresh":
        return refresh_token()
    state = load_state()
    kw, product = pick_product(state)
    text = generate_text(kw, product)
    post_id = publish(text, product.get("productImage"), reply_text(product))
    if not DRY_RUN:
        state["products"].append(product["productId"])
        state["log"].append({"at": datetime.now(timezone.utc).isoformat(), "kw": kw,
                             "product": product["productName"], "post_id": post_id})
    save_state(state)
    print("발행 완료:", kw, product["productName"], post_id)


if __name__ == "__main__":
    main()
