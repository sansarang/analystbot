# SCT-8 — 검색어를 두 벌로 (대진 질의 + 팀 질의). 사용자 지시

## 왜

`SCT-7` 로 RSS 통로를 붙였는데 **4팀 전부 0건**이었다. 원인은 통로가 아니라
**질의 모양**이었다(실측 2026-09-14, 운영 컨테이너):
```
q="Torino probabili formazioni infortunati"   <item> 80건 · 48h 안 0건
   434.9h / 3386.9h / 2954.9h / 5881.9h …     ← 구글이 과거 전체를 매칭한다
q="Torino Roma probabili formazioni"          12건 중 10건이 24h 안
   1.6h / 3.3h / 3.8h / 4.2h / 4.6h / 5.1h …  ← 오늘 경기 기사
```
사용자 지시: 대진 질의(기사 매칭용) + 팀 질의(결장 뉴스용) **두 벌**을 두고,
팀 질의에는 **신선도 토큰**을 반드시 붙인다. 대진이 10건 이상이면 팀 질의 생략.

재현:
```
PYTHONPATH=. .venv/bin/python <scratchpad>/repro_sct8.py
  → TypeError: queries() got an unexpected keyword argument 'home'
```

## ① 이 함수/상태를 읽는 곳 **전부**

```
$ grep -rn "SC.queries\|scout_config.queries" app/ tests/
app/engine/scout_config.py     queries 정의 · tor_safe 가 내부에서 부른다
app/collectors/satellite_soccer.py  gather_soccer (대진·팀 두 벌을 만든다)
tests/collectors/test_satellite_search.py · tests/test_rss_channel.py
```
`queries()` 의 인자가 늘었지만 **위치 인자 순서는 그대로**다(`league, team,
stage`). `tor_safe()` 가 `queries(league,"X","pre")` 로 부르는 것도 그대로 돈다.

## ② 만드는/바꾸는 상태

**없다.** 바뀌는 것은 설정 파일의 문자열과 질의 순서뿐이다.
| 무엇 | 전 | 후 |
|---|---|---|
| `search_terms.yaml` 유럽 6리그 | 팀 질의 1줄 | 대진 1줄 + 팀 1줄(신선도 토큰 포함) |
| 질의 순서 | 팀 질의만 | **대진 먼저**, 부족하면 팀 질의 |
| 대진 기사 귀속 | — | **양 팀 모두**(본문은 한 번만 연다) |

야구·J1·K리그1 은 **팀 질의 그대로**다(사용자 지시 — 현지 매체가 팀 단위로 쓴다).
리그1·에레디비시는 우리 시스템에 리그가 없어 표에만 적어 두었다.

## ③ 리그·종목·경로 분기가 생기는가

리그별 질의 구성이 갈린다(대진형 vs 팀형). 그 갈림은 **yaml 이 정한다** —
코드에 `if league ==` 를 넣지 않았다. 자리표시자를 채울 수 없는 줄은
`queries()` 가 **뺀다**(빈 문자열로 채우면 반쪽 질의가 나가고, 그게 다시
과거 전체를 긁는다).

## ④ 실패하면 "시끄럽게" 실패하는가

- `[rss] {away}@{home} 검색결과 N건 → 기사 M건 · 폐기 K건` — 검색 결과 수를
  기사 수와 **따로** 남긴다. 0건이 "안 나왔다"인지 "다 걸렀다"인지 갈린다.
- 팀 질의를 건너뛰면 `대진 질의 N건이라 팀 질의 생략` 을 남긴다.

## ⑤ 시스템에 이미 있는 사실을 다시 적고 있지 않은가

- 상한 10 을 코드에 적지 않는다 — `scout_config.PAIR_HITS_ENOUGH` 가 원본이고
  계약이 `"< 10"` 이 코드에 없음을 단언한다.
- 신선도 토큰 목록도 `today_words` 를 쓴다(계약이 그 목록으로 검사한다).
- 선별·등급·본문 재검사는 SCT-4/6/7 의 같은 함수를 그대로 탄다.
