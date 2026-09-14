# SCT-6 — 날짜를 모르는 결과를 폐기했다. 소스별로 가른다 (사용자 지시)

## 왜

`SCT-4` 가 지시문 4-3 ② 날짜 문을 그대로 구현했더니 **DDG/토르 보강이
0건이 됐다.** 실측(2026-09-14 15:5x, 세리에A 3경기):
```
전  기사 47건 · 토르 보강 +6건
후  기사 41건 · 토르 보강 +0건 · 폐기 사유 최다 = '날짜'
```
원인은 소스 차이다 — **RSS 는 `pubDate` 를 싣고 DDG 스니펫은 안 싣는다.**
날짜를 "모르는" 것을 "지난 글"과 같게 처리한 것이 결함이었다.

사용자 지시(2026-09-14): RSS 는 지금 규칙 그대로, DDG/토르는 날짜 토큰이
없으면 폐기가 아니라 `undated=true` 로 통과시키되 tier 를 한 단계 내리고,
fetch 후 본문(`article:published_time` 또는 첫 날짜)으로 재검사해 경기일
±2일 밖이거나 지난 연도가 명시되면 그때 폐기.

재현:
```
PYTHONPATH=. .venv/bin/python <scratchpad>/repro_sct6.py
  → AttributeError: 'Screen' object has no attribute 'undated'
```

## ① 이 함수/상태를 읽는 곳 **전부**

```
$ grep -rn "screen(\|rank_and_pick\|Screen(" app/ tests/
app/engine/scout_config.py      screen · rank_and_pick · Screen
app/collectors/satellite.py     _tor_supplement (SCT-4 가 붙인 유일한 호출부)
tests/collectors/test_satellite_search.py · tests/test_satellite_search_wiring.py
```
`screen` 의 호출부는 `rank_and_pick` 하나, 그 호출부는 `_tor_supplement`
하나다. 야구 경로는 `league` 를 넘기지 않아 이 문을 아예 지나지 않는다.

## ② 만드는/바꾸는 상태

**없다.** DB·Redis·env 를 만들지 않는다. 바뀌는 것은:
| 무엇 | 전 | 후 |
|---|---|---|
| `Screen` | `(keep, reason)` | `(keep, reason, undated=False)` — 칸 하나 추가 |
| 날짜 미상 결과 | 폐기 | 통과 + `hit["undated"]=True` + tier +1 |
| fetch 후 | 없음 | `body_date_ok(body, kickoff)` 재검사 |

`Screen` 의 새 칸은 기본값이 있어 기존 호출부가 그대로 돈다.

## ③ 리그·종목·경로 분기가 생기는가

**소스 분기**가 생긴다(그것이 지시의 핵심이다):
- `hit["published"]` 가 `datetime` 이면 RSS 로 본다 → 신선도 + 날짜 문 종전 그대로.
- 아니면 DDG/토르로 본다 → 날짜 토큰 있으면 통과, 없으면 `undated`.
- **연도가 명시됐는데 올해가 아니면** 두 경우 모두 즉시 폐기(지난 시즌 글).
종목·리그 분기는 늘지 않는다.

## ④ 실패하면 "시끄럽게" 실패하는가

- 본문 재검사 폐기는 URL 과 사유를 로그에 남긴다(`[scout] 본문 재검사 폐기 …`).
- 폐기 건수는 종전처럼 `_tor_supplement` 의 `dropped` 에 합산돼 기존 한 줄에 뜬다.
- 🔴 **반대 위험은 이번엔 반대 방향이다** — 문을 넓혔으므로 지난 시즌 글이
  섞일 수 있다. 그래서 본문 재검사를 함께 넣었고, 배포 후 첫 사이클에서
  보강 건수와 폐기 사유를 다시 잰다(기준선: 보강 0건).

## ⑤ 시스템에 이미 있는 사실을 다시 적고 있지 않은가

- 신선도 상한·tier 표·확정 키워드·상위 개수는 그대로 `scout_config` 상수·
  yaml 이 원본이다. 새 상수는 `BODY_DATE_TOLERANCE_D` 하나이고 지시문이 준 값(±2일)이다.
- 본문 날짜는 `article:published_time` **표준 메타**를 먼저 본다 — 사이트별
  규칙을 손으로 적지 않는다.
