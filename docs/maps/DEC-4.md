# DEC-4 — 매체 유형 분류 (영향 지도 5문)

사용자 결정 2026-09-21: "`config/source_types.yaml` — 매체를 유형(official ·
wire · beat · general · aggregator)으로만 분류(**사실 기준, 근거 URL**).
등급은 **official 만 상위**, 나머지 unrated(soft). 승격은 `source_scorecard` 의
'공식·라인업과 일치율' **n≥20** 후보만, **사용자 승인**."

## ① 왜 등급이 아니라 유형인가

종전 `config/sources.yaml` 은 tier0/1/2/3 으로 **믿음의 등급**을 매긴다.
그런데 실측(D41): `tier1_club_local.kbo` 는 `gukjenews.com` **하나**,
`tier2_aggregator.kbo` 는 **빈 목록**이다. 그래서 `osen`·`yna`·`mt` 가 전부
`RANK_UNKNOWN` 이고, 오디션 표의 "화이트리스트 0%" 가 그것이었다.

🔴 **등급을 내가 채우면 그건 취향이다.** 유형은 다르다 — "구단 공식인가"는
   **사실**이고 근거 URL 로 확인된다.

## ② 분류 대상은 **실측한 것만**

운영 Redis 캐시에서 실제로 본 기사 도메인 **13종**(합계 175건):
```
72 v.daum.net · 39 news.yahoo.co.jp · 36 news.google.com · 11 www.sanspo.com
 5 www.transfermarkt.com · 2 sp.baystars.co.jp · 2 news.mynavi.jp
 2 www.goal.com · 2 www.baseballchannel.jp · 1 niwaka-yakyu.net
 1 www.nikkansports.com · 1 www.sponichi.co.jp · 1 www.sportingnews.com
```
여기에 오늘 실측에서 본 것을 더한다 — Bing 검색 결과 도메인(osen·yna·mt·
fnnews·newspim·ajunews·msn), 본문 열기 실측 15종, `kbo_news.py` 가 설정으로
가진 피드 4곳, `source_map` 의 구단 공식 2곳.

🔴 **지어낸 도메인은 넣지 않는다.** 계약이 운영에서 본 12종이 들어 있는지 확인한다.

## ③ 🔴 근거 URL 을 **실제로 열어 봤다**

24건 중 **2건이 실패**했다:
```
www.yna.co.kr/about/index    → 400
news.yahoo.co.jp/info/       → 404
```
→ **루트로 대체하고 "소개 페이지를 못 찾았다"를 `note` 에 적는다.**
   없는 URL 을 근거로 적으면 그게 거짓이다. 계약이 이 문구를 확인한다.

## ④ 어디를 건드리나

| 파일 | 무엇 |
|---|---|
| `config/source_types.yaml` | **신규** — 도메인 → 유형 · 근거 URL · note |
| `app/engine/source_types.py` | **신규** — `tier_of` · `promotion_candidate` |

🔴 **`config/sources.yaml`(tier0~3)은 한 줄도 안 건드린다.** 별개 축이다 —
   그쪽은 리그별 등급, 이쪽은 매체 유형. 계약이 확인한다.
⚠️ **아무도 아직 부르지 않는다.** 판정·수집 경로에 닿지 않는다. 이을 자리는
   `scout_config.rank` 인데, 그것은 **승격 규칙이 정해진 뒤**다.

## ⑤ 승격 — 코드가 스스로 하지 않는다

```
official                     → primary (상위)
그 외 전부                    → unrated (soft)
모르는 도메인                  → unrated  ← 조용히 낮추지도 올리지도 않는다
```
승격 후보 조건: **공식·라인업과의 일치율** 실측이 **n≥20** 일 때만.
그마저도 **후보**일 뿐이고 올리는 것은 사용자다.
계약이 `promote(`·`auto_promote`·`upgrade(` 가 코드에 없음을 확인한다.

## ⑥ 틀렸을 때 누가 알려주나

계약 8건: 유형이 다섯 가지뿐인가 · 근거 URL 이 전건 있나 ·
**못 찾은 근거가 그렇게 적혀 있나** · official 만 상위인가 ·
**자동 승격 경로가 없나** · 표본 n≥20 인가 · 종전 등급표를 안 건드렸나 ·
**분류가 실측 도메인에서 왔나**.
