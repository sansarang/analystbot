# SRCH-8 — 크롤러가 가져온 것을 DB 페이로드도 보게 한다

사용자 지시 2026-09-12: "재요청, 오늘 타순 불펜 폼까지 수정해라"

## 왜 — 같은 사실이 두 갈래로 갈라져 있다

실측 2026-09-12, 운영 파이프라인(ORDER_V3=1):

```
[dbref] 있음 3 · 본것 ['오늘 타순']
없음: 최근 3경기 박스스코어 · 불펜 최근 폼과 가용성 · 실력 레이팅 · …
조사 결과: 원정/홈 선발 예고 · 16:08 라인업 변경     ← 타순 줄이 없다
```

그런데 크롤러는 **10분마다 타순과 불펜을 긁고 있다.**

| 사실 | 수집 경로(v3) | DB 페이로드 |
|---|---|---|
| 오늘 타순 | 크롤러 스냅샷 `lineup_home`/`lineup_away` | **비었음** |
| 불펜 연투 | `pitcher_appearances` → 문장 | **없음** |

원인 셋:

1. **타순** — `lineups_payload` 에 폴백이 **이미 있다**(`jg["lineup_{side}"]`).
   그런데 `gather.enrich` 가 **선발 이름만** 채우고 타순은 안 채워서
   그 폴백이 영영 안 걸렸다.
2. **불펜** — `gather._bullpen` 이 연투까지 읽어 **문장으로만 쓰고 버린다.**
   `bullpen_payload` 는 `research` 를 보므로 계속 `없음`.
3. **재요청** — 2단계가 `DB요청: 불펜 최근 폼과 가용성` 을 냈는데 DB에
   없으면 **조용히 버려졌다.** 검색으로 넘길 길이 없었다(SRCH-7 은 판정의
   `추가요청` 만 검색으로 보냈다).

## ① 이 함수/상태를 읽는 곳 **전부**

```
$ grep -rn "lineups_payload\|bullpen_payload" app/
app/engine/dbref.py      ITEMS → bundle 이 부른다
app/engine/gather.py     _lineup 이 lineups_payload 를 부른다
app/engine/matchup.py    정의 · MATCHUP 프롬프트 조립(구 경로)

$ grep -rn 'jg\["lineup_' app/ | head
app/engine/matchup.py:108   lineups_payload 의 폴백 — **읽는 유일한 곳**

$ grep -rn "enrich(" app/
app/engine/gather.py     collect 가 맨 먼저 부른다 — 유일한 호출부
```

🔴 `lineups_payload` 는 **구 경로 프롬프트(자료3)도 쓴다.** 타순이 채워지면
   구 경로 카드에도 자료3 이 늘어난다 — 그건 개선이지만 **동작 변화**다.
   ⚠️ 운영은 지금 구 경로로 돈다. 다만 채우는 값은 크롤러가 이미 긁던 것이고,
     **비어 있을 때만** 넣으므로 기존 값을 덮지 않는다.

## ② 만드는/바꾸는 상태

| 상태 | 성격 | 다른 곳이 다른 규칙으로 갱신하나 |
|---|---|---|
| `jg["lineup_home"]`·`jg["lineup_away"]` | 기존 칸을 채운다 | 🔴 `lineup_diff` 가 `today_nine` 을 따로 채운다 — 그쪽이 있으면 `lineups_payload` 가 **그것을 먼저 쓴다**(폴백은 그 다음) |
| `research[f"{side}_bullpen"]["최근"]` | 하위 키 추가 | 🔴 `era` 는 `kbo_stats`·`naver_kbo`·`npb_stats` 가 채운다 — **덮지 않는다**(`setdefault`) |
| `order_v3["DB못채움"]` | 원장 키 추가 | 아니다 |

🔴 **상태 이원화 위험이 정확히 여기 있다.** 같은 "오늘 타순"을
   `today_nine`(구조)과 `lineup_{side}`(문자열) 두 곳이 갖는다.
   → 새로 만드는 것이 아니다. **둘 다 이미 있었고**, `lineups_payload` 가
     이미 우선순위를 정해 두었다(구조 우선, 문자열 폴백). 우리는 **비어 있던
     쪽만** 채운다.

## ③ 리그·종목·경로 분기

**생기지 않는다.** `enrich`·`_bullpen` 은 종목 공통이고, 크롤러 스냅샷도
kbo·npb·mlb 공통 키다.

⚠️ MLB 는 `games.home_pitcher` 가 statsapi 로 이미 차 있어 `enrich` 가
   선발을 덮지 않는다(기존 규약). 타순도 **같은 규약**을 따른다 —
   비어 있을 때만.

## ④ 조용히 실패하는가

| 위험 | 대응 |
|---|---|
| 🔴 **크롤러 값이 멀쩡한 값을 덮는다** ← 가장 큰 반대 위험 | 비어 있을 때만 채운다. 계약이 "이미 있으면 안 덮는다"를 단언 |
| 빈 불펜 기록으로 빈 칸을 만들어 `bundle` 이 "있음"으로 센다 | 기록이 없으면 칸 자체를 안 만든다(계약) |
| `era` 를 지운다 | `setdefault` 로 하위 키만 더한다(계약) |
| 못 채운 DB 요청이 또 조용히 버려진다 | `with_miss=True` 로 받아 **검색으로 넘긴다**. `DB못채움` 을 원장에 남긴다 |
| 검색 라운드가 늘어 비용이 2배 | `gather.search` 호출이 2회를 넘지 않는지 계약으로 단언 |
| 타순 파싱이 깨져 9명이 35명으로 세진다 | 파싱은 `lineup_diff.parse_order` 가 원본이다 — 새로 쓰지 않는다(2026-09-07 전례) |

⚠️ **아직 못 재는 것**: 오늘 슬레이트가 끝나 실제 경로 재측정이 불가능하다.
   내일 슬레이트에서 `DB있음` 이 3 → 5 로 느는지 확인해야 한다.

## ⑤ 이미 있는 사실을 다시 적는가

- 타순 문자열 파싱을 새로 쓰지 않는다 — `lineup_diff.parse_order` 가 원본이고
  `lineups_payload` 가 이미 그것을 부른다.
- 불펜 집계를 새로 만들지 않는다 — `bullpen_usage.recent` 의 반환을 **그대로** 넣는다.
- 크롤러 스냅샷 키(`lineup_home`·`lineup_away`)를 손으로 정의하지 않는다 —
  `crawler_feed` 가 원본이다.
- 검색 경로·질문 상한은 `gather.search`·`websearch.MAX_ASKS` 그대로.
