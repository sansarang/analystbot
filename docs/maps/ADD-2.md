# ADD-2 — MSN 래핑 버리기 · Bing 을 `feed` 로 등록 (영향 지도 5문)

사용자 지시 2026-09-21 (추가 2건). 둘 다 `search.py` 한 자리라 한 단위로 묶었다.

## ① 실측 근거 (D43)

```
기사 URL 24건 · 도메인 15종을 실제로 열어 본 결과
   www.msn.com    본문 **3자** × **6건**  ← 24건 중 25%
   www.mt.co.kr   본문 1,200자
   www.osen.co.kr 본문 295자
```
MSN 은 JS 렌더라 정적 HTML 에 값이 없다. **제목만 남는다.**
Bing 결과의 1/4 이 이 상태였다.

## ② 🔴 추가 검색을 하지 않는다

지시: "같은 제목의 원 매체 URL 이 **같은 검색 결과 안에** 있으면 그것만 쓴다.
**추가 검색 금지.**"

원 매체를 다시 찾으러 나가면 요청이 늘고, 그건 지시가 막은 것이다.
→ `drop_wrappers` 는 **순수 함수**다. 계약이 `await`·`fetch`·`httpx` 가
  본문에 없음을 확인한다.

⚠️ **제목이 같아야 바꾼다.** 아무 기사나 갖다 붙이면 안 된다. 제목이 다르면
   대체(`wrapper_replaced`)가 아니라 **폐기**(`wrapper_no_body`)다.

## ③ `feed` 는 `api_terms` 와 **다르다**

| basis | 뜻 | robots 를 덮나 |
|---|---|---|
| `api_terms` | 그 API 자신의 약관이 governing | 🔴 **덮는다** (open-meteo) |
| `feed` | 제공되는 피드 형식 · 간격·상한을 명시 | ❌ **안 덮는다** |

Bing 은 `/news/…` 가 **애초에 robots 허용**이라 덮을 이유가 없다.
등록하는 이유는 **간격·일일 상한·근거를 한 곳에 적기 위해서**다.
🔴 이 차이를 계약으로 잠근다(`overrides_robots`).

근거 URL (**실제로 열어 확인**):
```
https://www.bing.com/news/search?q=…&format=RSS   200   ← 피드 자체
https://www.bing.com/new/termsofuse               200
https://www.microsoft.com/en-us/servicesagreement 200
```
⚠️ **약관 본문은 아직 안 읽었다.** URL 만 확인했다 — 그렇게 적는다.

## ④ 어디를 건드리나

| 파일 | 무엇 |
|---|---|
| `config/deepsearch.yaml` | `search.wrappers` · `access_basis.www.bing.com` |
| `app/deepsearch/search.py` | `drop_wrappers()` (순수) |
| `app/deepsearch/runtime.py` | `overrides_robots()` — `api_terms` 만 True |

⚠️ 래핑 도메인 목록은 **config 가 원본**이다. 계약이 `msn.com` 이 코드에
   없음을 확인한다.

## ⑤ 틀렸을 때 누가 알려주나

계약 7건: 래핑을 버리나 · 같은 결과 안 원문으로 **바꾸나** ·
**추가 검색을 안 하나** · 제목이 다르면 안 바꾸나 · 도메인이 config 에 있나 ·
bing 이 `feed` 로 등록됐나 · **`feed` 가 robots 를 안 덮나**.
