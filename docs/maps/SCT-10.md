# SCT-10 — 추출이 tier1/2 현지 기사를 읽지 않았다 + 승격 후보 반영

## 왜

RSS·티어·별칭을 다 고쳐 **tier1/2 이탈리아 기사 3건을 열었는데**, 추출 결과의
출처는 여전히 `transfermarkt`·`v.daum.net` 이었다(실측 2026-09-14):
```
"away": {"team": "AS Roma", "out": [], "xi_status": null,
         "source": "http://v.daum.net/v/20260914143255111"}
```
원인: `extract_facts` 가 **목록 앞에서 3건**을 자르는데, 수집 순서가
`층1(트랜스퍼마크트·플래시스코어) → 다음 → RSS` 라 현지 기사가 항상 잘렸다.
Dybala 선발이 든 `teleradiostereo.it` 를 **열어 놓고 읽지 않았다.**

함께: 사용자가 정한 승격을 표에 반영한다.

재현:
```
PYTHONPATH=. .venv/bin/python <scratchpad>/repro_sct10.py
  → 채택 출처: https://www.transfermarkt.com/x   (tier1 기사를 읽지 않았다)
```

## ① 이 함수/상태를 읽는 곳 **전부**

```
$ grep -rn "extract_facts\|FETCH_PER_STAGE" app/ tests/
app/collectors/satellite.py  extract_facts (정의) · gather (유일한 호출부)
app/engine/scout_config.py   FETCH_PER_STAGE · rank · RANK_UNLISTED
tests/test_scout_extract.py
```

## ② 만드는/바꾸는 상태

**없다.** 읽는 **순서**만 바뀐다.
| 무엇 | 전 | 후 |
|---|---|---|
| 추출 대상 3건 | 목록 앞에서 | **등급 순**(동률이면 원래 순서) |
| `sources.yaml` serie_a | tier1 11 · tier2 10 | tier1 14 · tier2 12 · blocked +2 |

승격(사용자 지시): tier1 += gazzetta.it · corrieredellosport.it · sport.sky.it ·
tier2 += ilriformista.it · dazn.com · blocked += sportnews.snai.it · sudefuturi.it

## ③ 리그·종목·경로 분기가 생기는가

**생기지 않는다.** 축구만 추출하는 것은 그대로이고(SCT-5), 정렬 규칙은
리그 무관이다. 등급은 `rank()` 원본이 정하고 목록에 없으면 `RANK_UNLISTED`
로 **동률 처리**한다 — 미상이라고 뒤로 더 밀지 않는다(그건 tier 표의 일이다).

## ④ 실패하면 "시끄럽게" 실패하는가

- 추출 성적은 이미 경기별 로그에 남는다(`[scout] {팀} 추출 — out N …`).
- 미상으로 읽힌 도메인은 `[scout] 승격후보 …` 로 남는다(SCT-9).
- 🔴 이번 변경의 반대 위험: 층1(트랜스퍼마크트 부상표)이 tier 표에 없어
  뒤로 밀릴 수 있다. 실제로 밀렸는지는 **추출 출처**가 로그·JSON 에 그대로
  남으므로 다음 사이클에서 바로 보인다.

## ⑤ 시스템에 이미 있는 사실을 다시 적고 있지 않은가

- 상한(3)·등급·미상 처리 전부 `scout_config` 원본을 부른다.
- 도메인 목록은 `sources.yaml` 한 곳.
