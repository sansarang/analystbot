# SCT-4 — 위성이 현지어 검색어·tier 선별을 쓰지 않는다 (SCT-3 배선)

## 왜

`SCT-3`(2026-09-13)이 검색어 표(`config/search_terms.yaml`)·소스 화이트리스트
(`config/sources.yaml`)·선별 규칙(`scout_config.rank_and_pick`)을 만들었는데
**위성이 그것을 부르지 않는다.** 축구 위성은 여전히 고정 꼬리말 영어 질의를
던지고, 검색 결과를 tier 정렬 없이 제목 문만 보고 연다.

재현:
```
PYTHONPATH=. .venv/bin/python <scratchpad>/repro_sct4.py
  → AttributeError: module 'app.collectors.satellite_soccer' has no attribute '_tor_stage'
```

## ① 이 함수/상태를 읽는 곳 **전부**

```
$ grep -rn "scout_config\|SEARCH_TERMS\|rank_and_pick" app/ tests/
app/engine/scout_config.py        queries · screen · rank · rank_and_pick · tor_safe · validate · merge
   → app/ 안 호출부 **0** (테스트만 부른다)
app/collectors/satellite.py       _tor_supplement — 제목 문(_title_hits)만 본다
app/collectors/satellite_soccer.py gather_soccer — `_SOCCER_TOR_TAIL` 고정 꼬리말
tests/collectors/test_satellite_search.py  순수 함수 단위 테스트
```
붙이는 자리는 **토르(DDG) 보강 경로 한 곳**이다. 이유는 실측이다:
```
rank('https://calciolecce.it/x', 'serie_a') = 1   ← tier1
rank('https://fantacalcio.it/x', 'serie_a') = 2   ← tier2
rank('https://v.daum.net/v/1',  'serie_a') = 9   ← 미상(=fetch 안 함)
```
🔴 주력 채널(다음·야후 뉴스)은 도메인이 전부 `v.daum.net`·`news.yahoo.co.jp`
   라 tier 표에 없다. 거기에 이 선별을 걸면 **기사가 통째로 0건이 된다.**
   tier 표는 현지 웹 검색 결과를 겨눈 것이고, 그 통로는 DDG 뿐이다.
   그래서 다음·야후 경로는 **건드리지 않았다.**

## ② 만드는/바꾸는 상태

**없다.** DB·캐시·env 를 만들지 않는다. 바뀌는 것은 두 가지 행동뿐이다:
| 무엇 | 전 | 후 |
|---|---|---|
| DDG 질의 | `{team} team news injury suspension predicted lineup` 고정 | `search_terms.yaml` 의 리그·단계별 현지어 |
| DDG 결과 선별 | 제목 문만 | 제목·날짜·신선도 문 → tier 정렬 → 상위 3 |

`_tor_supplement(league=None)` 이면 **종전 그대로**다 — 야구 호출부(MLB·NPB)는
`league` 를 넘기지 않으므로 동작이 바뀌지 않는다.

## ③ 리그·종목·경로 분기가 생기는가

생긴다. 그리고 **명시한다**:
- 축구만 `league` 를 넘긴다(야구 호출부는 그대로).
- 한국어 질의는 토르가 거부하므로(`tor_search.is_tor_safe_query`) K리그1 은
  `scout_config.tor_safe()` 가 False 를 주고 **종전 꼬리말로 돌아간다.**
  조용히 빈손이 되게 두지 않는다.
- 리그 키를 못 찾으면(`league_labels()` 에 없는 라벨) `league=None` 이라
  역시 종전 경로다.

## ④ 실패하면 "시끄럽게" 실패하는가

- `rank_and_pick(with_discard=True)` 이 사유별 폐기 건수를 돌려주고,
  `_tor_supplement` 이 그 합을 기존 로그 줄에 실어 남긴다
  (`토르 보강 … +N건 · 제목 불일치 폐기 M건`).
- `scout_config` 자신도 `[scout] 리그 단계 — 폐기 {사유: n}` 을 남긴다.

🔴 **반대 위험(정상 데이터 폐기)이 이 단위의 진짜 위험이다.** tier 표에 없는
   도메인은 전부 `미상` 으로 버려지므로, 표가 얇으면 보강이 0건이 된다.
   그래서 배포 후 **첫 사이클에서 전후 기사 수를 재고 보고한다**
   (오늘 실측 기준선: 세리에A 3경기 47건, 그중 토르 보강 +6건).

## ⑤ 시스템에 이미 있는 사실을 다시 적고 있지 않은가

- 검색어·도메인·신선도 상한·상위 개수를 **코드에 적지 않는다.**
  `search_terms.yaml`·`sources.yaml`·`scout_config` 상수가 원본이다.
- 남은 시간도 다시 계산하지 않는다 — `pregame_push.minutes_until_start` 를
  쓴다(트리거·발송이 쓰는 그 함수).
- 리그 라벨→키도 `app.leagues.league_labels()` 원본을 쓴다.
