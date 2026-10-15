# 포이즌 리셀 마진 스캐너

국내 플랫폼(현재 무신사)에서 싸게 살 수 있는 상품 중, 포이즌에서 팔면 마진이 남는 상품을 찾아 알려주는 도구입니다.

```
watchlist.csv (품번, 사이즈, 포이즌 시세)
   → 무신사 품번 검색 (정확한 품번 일치, 품절·중고 제외, 최저가 선택)
   → 마진 계산 (수수료 · 최소수수료 · 배송비 · 매입 부가세 환급)
   → 리포트 출력 + 기준 이상이면 디스코드 웹훅 알림
```

## 데스크톱 앱 (Windows)

1. [파이썬](https://www.python.org/downloads/)을 설치합니다. 설치 화면에서 **Add python.exe to PATH**를 체크하세요.
2. 이 `poizon_resell` 폴더를 PC에 내려받고 **`설치_바탕화면바로가기.bat`**를 더블클릭합니다.
3. 바탕화면에 생긴 **"포이즌 리셀 스캐너"** 아이콘으로 실행합니다.

앱에는 스캔, 관심 상품 편집, 마진 계산기, 설정(수수료와 디스코드 웹훅) 탭이 있습니다. 스캔 결과 행을 더블클릭하면 구매 페이지가 열립니다.
웹훅 주소는 `discord_webhook.txt`에 저장되며 git에는 올라가지 않습니다.

## 사용법 (명령줄)

```bash
pip install requests
python resell.py calc 100000 120000      # 매입가 10만 → 포이즌 12만 원일 때 순이익
python resell.py scan                    # watchlist.csv 전체 조회
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/... python resell.py scan
python -m unittest -v test_resell        # 테스트
```

- `watchlist.csv`: `style_code,name,size,poizon_price`. 들어 있는 가격은 **예시**입니다. 포이즌 앱이나 지금 쓰는 디스코드 도구에서 확인한 실제 판매 가능가(원화)로 바꾸세요.
- `config.json`(선택): 기본값을 덮어씁니다.
  ```json
  {"fee_rate": 0.10, "min_fee": 15000, "shipping": 3000, "vat_refund": true, "min_profit": 10000, "min_roi": 0.05}
  ```
  수수료율과 최소수수료는 카테고리와 시기에 따라 다릅니다. **포이즌 판매자센터 기준으로 꼭 맞추세요.**
  `vat_refund`는 일반과세자로 수출 영세율 환급을 받는 경우에만 `true`로 둡니다.

## 순이익 공식

```
수수료 = max(판매가 × fee_rate, min_fee)
순이익 = 판매가 − 수수료 − 배송비 − 매입가 + 매입가/11 (부가세 환급, 일반과세자)
최대매입가 = (판매가 − 수수료 − 배송비 − 목표이익) ÷ (1 − 1/11)
```

## 범위와 한계

- **포이즌 시세는 자동 수집하지 않습니다.** 공식 공개 API가 없고, 앱 스크래핑은 약관 위반과 차단 위험이 있습니다. CSV로 넣거나, 시세를 주는 도구가 있으면 그 출력을 CSV로 변환해 넣으세요.
- **자동 결제는 하지 않습니다.** 알림을 보고 직접 사거나 기존 도구로 구매하세요. 플랫폼 약관상 매크로 구매는 계정 제재 대상이 될 수 있습니다.
- 매입처를 추가하려면 `SOURCES`에 `함수(style_code, session) -> [Offer]`를 등록하면 됩니다 (예: 29CM, 나이키 공홈, SSF).
- 무신사 가격은 쿠폰과 회원 등급 할인 전 `finalPrice` 기준입니다. 실제 결제가는 더 낮을 수 있습니다.
