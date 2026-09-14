# ALI-1 — 검색 질의에 쓸 현지 표기 별칭표 (사용자 지시)

## 왜

팀 질의가 0건이었다(실측 2026-09-14 운영):
```
q="Como 1907 infortunati oggi"         → 0건
q="Parma Calcio 1913 infortunati oggi" → 0건
```
현지 매체는 `Como`·`Parma` 로 쓴다. 법인격(FC·AC·US·SSC)과 창단연도
(1907·1913)는 이름이 아니라 **형식**이다.

기존 별칭표(`satellite_soccer.SOCCER_ALIAS`, 98건)는 **한국어 전용**
(코모·파르마)이라 이탈리아어 질의에 쓸 수 없다.

재현:
```
PYTHONPATH=. .venv/bin/python <scratchpad>/repro_ali1.py
  → module 'app.engine.scout_config' has no attribute 'local_name'
```

## ① 이 함수/상태를 읽는 곳 **전부**

```
$ grep -rn "SOCCER_ALIAS\|soccer_query\|local_name" app/ tests/
app/collectors/satellite_soccer.py  SOCCER_ALIAS · soccer_query  → 다음(한국어) 검색 경로
app/engine/scout_config.py          local_name  ← 신규, 현지어 질의 전용
app/collectors/satellite_soccer.py  gather_soccer 가 질의 조립에서만 부른다
```
🔴 **두 표는 섞이지 않는다.** 계약이 `soccer_query("Como 1907") == "코모"` 와
`local_name("serie_a","Como 1907") == "Como"` 를 **함께** 단언한다.

## ② 만드는/바꾸는 상태

| 무엇 | 성격 |
|---|---|
| `config/aliases_local.yaml` | **새 설정 파일**(사용자 편집). 리그별 `{DB 표기: [현지 표기…]}` |

DB·Redis·env 는 만들지 않는다. 세리에A 12건은 **사용자가 준 값 그대로**이고,
나머지는 같은 규칙(법인격·숫자 토큰 제거)으로 자동 생성했다.
⚠️ 구두점만 다른 것은 별칭이 아니다("St. Louis Cardinals") — 표에 넣지 않았다.
⚠️ 이름이 그대로면 적지 않는다(사본 금지).

## ③ 리그·종목·경로 분기가 생기는가

리그별 표가 갈리지만 **코드 분기는 없다** — 표에 없으면 원래 이름을 쓴다.
야구(kbo·npb·mlb)는 생성 결과가 0건이라 표가 비어 있고, 그래서 종전과
동작이 같다.

## ④ 실패하면 "시끄럽게" 실패하는가

- 표에 없으면 **원래 이름**으로 검색한다(지어내지 않는다). 그 경우 검색
  결과 수가 로그에 그대로 남아(`[rss] … 검색결과 N건`) 0건이면 드러난다.
- 🔴 **기사 귀속·추출은 DB 표기 그대로**다. 질의에만 현지 표기를 쓴다 —
  귀속까지 바꾸면 나중에 경기와 못 맞춘다. 계약이 `_qs.append((team,` 로
  그것을 잠근다.

## ⑤ 시스템에 이미 있는 사실을 다시 적고 있지 않은가

- 팀 목록을 새로 적지 않았다 — `config/tiers/*.yaml` 의 키(운영 DB 표기)에서
  생성했다.
- 한국어 별칭은 손대지 않았다. 두 표가 각자 한 가지 일만 한다.
