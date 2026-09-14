# FOT-1 — 라인업·결장을 구조 JSON 으로 받는다 (사용자 지시)

## 왜

추출 1순위를 LLM 에서 **구조 JSON** 으로 바꾼다. 기사 추출은 groq 무료 한도에
막혔고(실측 2026-09-14: 429 백오프 340~527초), 뚫려도 로마 `out` 이 비었다.
같은 사실이 FotMob JSON 에는 칸으로 들어 있다(실측):
```
content.lineup.lineupType = "predicted"
content.lineup.homeTeam   = formation 3-5-2 · starters 11(id 포함) · coach ·
                            unavailable[{name, unavailability{type, expectedReturn}}]
content.lineup.awayTeam   = **unavailable 키 자체가 없음**(로마)
```

🔴 **경로가 지시문과 다르다 — 실측한 것을 쓴다.** `/api/matches` 는 404(HTML),
`/api/data/matches` 가 200 이다. `matchDetails` 도 `/api/data/` 아래다.

재현:
```
PYTHONPATH=. .venv/bin/python <scratchpad>/repro_fot1.py
  → cannot import name 'fotmob' from 'app.collectors'
```

## ① 이 함수/상태를 읽는 곳 **전부**

새 모듈이라 지금은 없다. 앞으로 붙일 자리(각각 **별도 단위**):
```
위성/파이프라인  attach(jg, redis)  → jg["fotmob"]
T-60 트리거      attach 재호출 → lineup_type 이 confirmed 로 바뀌면 diff_xi
교차검증         unavailable is None → API-Football /injuries (2순위, 다음 단위)
```
이 단위는 **수집·파싱까지**다. 호출부를 이번에 만들지 않는다.

## ② 만드는/바꾸는 상태

| 상태 | 성격 |
|---|---|
| `jg["fotmob"]` | 메모리 — lineup_type·formation·starters(id)·bench·unavailable·missing·diff |
| Redis `fotmob:xi:{game_id}` | **새 키.** 예상 XI 보관(12h) — T-60 에서 공식과 대조하려고 |

DB 컬럼은 만들지 않는다.

🔴 **`unavailable` 이 없으면 `None`** 으로 돌려준다. 빈 목록(0명)과 구분해야
   "결장 없음"과 "모른다"가 갈린다. `missing` 에 그 사실을 남긴다.
🔴 **선수 id 를 반드시 싣는다.** 주전 판정(최근 10경기 선발 수)은 이름이
   아니라 id 로 센다(사용자 지시 3). `diff_xi` 도 id 로만 비교한다.

## ③ 리그·종목·경로 분기가 생기는가

**생기지 않는다.** FotMob 응답에서 리그를 가르지 않고 경기 단위로 붙인다.
야구는 이 모듈을 부르지 않는다(호출부가 축구 경로에만 생긴다 — 다음 단위).

## ④ 실패하면 "시끄럽게" 실패하는가

- 404·타임아웃·JSON 불량은 **결측**이다(None). 예외를 올리지 않는다 — 수집이
  판정을 막으면 안 된다. 실패는 `[fotmob] … 실패` 로 남는다.
- 경기를 못 찾으면 `그 날짜 표에 없다` 를 남긴다("조용한 0" 금지).
- 성공 로그 한 줄에 `lineup_type · 선발 수 · 결장 수(모름이면 '모름')` 가 든다.

⚠️ **매칭은 양쪽 이름이 다 맞아야** 붙인다. 퍼지 유사도를 쓰지 않는다
   (AC밀란→인테르 오매칭 전례). 정규화 후 포함 관계만 본다
   (`Torino` ⊂ `Torino FC`).

## ⑤ 시스템에 이미 있는 사실을 다시 적고 있지 않은가

- 팀 별칭은 이 모듈에 적지 않는다 — 매칭은 정규화로 하고, 리그별 현지 표기는
  `aliases_local.yaml`(ALI-1)이 원본이다.
- 요청 간격·UA 는 이 모듈 상수 하나씩이고 사용자 지시값(2초)이다.
