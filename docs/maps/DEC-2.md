# DEC-2 — 결정 2 (영향 지도 5문)

사용자 결정 2026-09-21: "open-meteo → `access_basis=api_terms`(근거 URL) 로
런타임 이관 · daum 검색 → **끈다**(Bing RSS 가 대체, 요청 0 확인) ·
tor_search → **이관·수정하지 않는다.** 호출부·7일 호출 수만 보고."

## ① `access_basis` 가 무엇인가 — 새 개념이라 적어 둔다

robots 가 거부해도 **그 API 자신의 약관**이 프로그램 접근을 정하고 있으면
그 약관이 governing 이다. open-meteo 가 그 경우다:

```
robots.txt        Disallow: /            ← 사이트 전체 기준
약관(근거 URL)     10,000/일 · 5,000/시간 · 600/분 · CC-BY 4.0
                  https://open-meteo.com/en/terms
```

🔴 **근거 URL 없이 `api_terms` 라고 적으면 그게 거짓이다.** 계약이 잠근다.
🔴 **덮는 범위는 그 호스트 하나뿐이다.** `daum`·`google` 은 그대로 막힌다.

⚠️ **상업성 판단은 사용자 몫이다.** 무료 티어는 "private websites without
   ads/subscriptions · personal · research · education" 이다. 이 봇이 거기
   해당하는지는 내가 정할 일이 아니라 **설정에 그대로 적었다**.
⚠️ CC-BY 4.0 이라 **출처 표시가 필요하다** — 카드에 날씨를 쓰면 그렇다.
   그 자리는 이 단위 밖이라 등록만 한다.

## ② daum — 끈다

`search.daum.net` 은 `Disallow: /` 다. DS-3 이 `rss_hits` 를 Bing 으로
갈았으므로 ~~**대체가 이미 있다.**~~

> 🔴 **[D52 정정 2026-09-22] 이 문장이 틀렸다.** `rss_hits` 는 있었지만 부르는
> 곳이 축구뿐이었고 `gather_kbo` 는 **미연결**이었다. 끈 순간 KBO 기사가 0 이
> 됐다(실측 2026-09-22 10:29 KST · KT Wiz@SSG Landers · 8회 전건 차단).
> 정정: **"대체 함수는 있었으나 KBO 에 미연결이었다. 2026-09-22 연결."**
> → `docs/maps/D52F.md` · DEFECTS D52

남은 호출부 둘을 게이트로 막는다:
```
satellite.py:463         KBO 기사 검색
satellite_soccer.py:538  축구 기사 검색
```
🔴 **코드를 지우지 않는다** — `source_gate` 한 줄로 되돌린다(SRC-OFF 방식).

## ③ tor — 🔴 **손대지 않는다.** 보고만.

```
호출부 5곳
  satellite.py:138 · satellite.py:551 · satellite_soccer.py:620
  (+ config.py:505 스위치 · satellite_soccer.py:110 주석)

스위치  satellite_tor_enabled  **기본값 True** (환경변수 비어 있어도 켜짐)
        운영 실측: True

7일 호출 수(계산값)  ≈ **91,392회**
  근거: DS-0 직접 계측 1사이클(NPB 3경기) = torproject 6 + ddg 6 = 경기당 4회
        96사이클/일 × 경기 약 34개 × 4 × 7일
```
⚠️ **계산값이다.** 실측은 DS-0 의 1사이클(12회)뿐이다.
⚠️ `lite.duckduckgo.com` 은 robots **허용**이다. 문제는 **Tor 경유**라는 것이고,
   그것은 "차단 우회 인프라"에 해당하는지가 **사용자 판단**이다.

## ④ 어디를 건드리나

| 파일 | 무엇 |
|---|---|
| `config/deepsearch.yaml` | `access_basis:` 블록(근거 URL·한도·비상업 주석) |
| `app/deepsearch/runtime.py` | `access_basis()` · robots 검사에서 그 호스트만 통과 |
| `app/collectors/weather.py` | `httpx` → 런타임 |
| `config/rules.yaml` | `sources.daum_search.enabled: false` |
| `app/collectors/satellite.py` | `_daum_fetch` 에 `require("daum_search")` |

**tor_search.py 는 한 줄도 안 건드린다.** 계약이 그것을 확인한다.

## ⑤ 되돌릴 수 있나

- daum: `config/rules.yaml` 한 줄.
- open-meteo: `access_basis` 항목을 빼면 다시 막힌다.
- ⚠️ robots 검사를 끄는 스위치는 없다 — `access_basis` 는 **호스트별 근거**이지
  전역 스위치가 아니다.

## ⑥ 틀렸을 때 누가 알려주나

계약 8건: 설정에 근거 URL 이 있나 · 비상업 조건이 적혀 있나 ·
`api_terms` 가 robots 를 덮나 · **덮지 않는 곳은 그대로 막히나** ·
weather 가 런타임을 지나나 · daum 이 꺼졌나 · 부르면 요청 0 인가 ·
**tor 를 안 건드렸나**.
