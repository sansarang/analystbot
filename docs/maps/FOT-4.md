# FOT-4 — LLM 을 보조로 내린다 (out·xi 는 JSON 정본). 사용자 지시

## 왜

FotMob JSON 이 `out`·`xi` 를 정확히 준다(실측: 토리노 결장 3 · 선발 11, id 포함).
LLM 추출은 같은 자리에서 **비거나 지어낸다**(실측: 로마 out 0, 파르마 out 0인데
JSON 에는 1명). 그런데 지금 코드는 LLM 결과를 그대로 쓴다.

사용자 지시: `out`·`xi` 는 **JSON 정본**, LLM 은 `notes`·`midweek`·
`bench_notable` **보조**. LLM 이 `out` 을 돌려줘도 JSON 과 다르면 **JSON 채택 +
conflict 플래그**.

재현:
```
PYTHONPATH=. .venv/bin/python <scratchpad>/repro_fot4.py
  → TypeError: extract_game_facts() got an unexpected keyword argument 'jg'
```

## ① 이 함수/상태를 읽는 곳 **전부**

```
$ grep -rn "extract_game_facts" app/ tests/
app/collectors/satellite.py   정의 · gather(유일한 호출부)
tests/test_scout_extract.py   계약
```
`gather` 는 `jg` 를 들고 있고 그 안에 `fotmob` 이 이미 붙어 있다(FOT-2 순서).
넘겨 주기만 하면 된다 — 새 상태가 필요 없다.

## ② 만드는/바꾸는 상태

**없다.** 추출 결과 dict 안에서 칸의 **출처**가 바뀐다:
| 칸 | 출처 |
|---|---|
| `out`·`xi`·`xi_status` | **FotMob JSON**(있으면). 없으면 종전대로 LLM |
| `notes`·`midweek`·`bench_notable` | LLM |
| `conflict` | LLM `out` 이 JSON 과 다르면 True |
| `out_src` | `fotmob` \| `llm` — 어디서 온 값인지 남긴다 |

🔴 **덮어쓰기 방향이 계약이다.** JSON 이 있으면 LLM 값은 **버리지 않고
   비교만** 한다 — 버리면 왜 달랐는지 영영 모른다.

## ③ 리그·종목·경로 분기가 생기는가

**생기지 않는다.** `jg["fotmob"]` 이 없으면(축구가 아니거나 FotMob 결측)
종전 동작 그대로다.

## ④ 실패하면 "시끄럽게" 실패하는가

- `conflict` 가 서면 로그에 남긴다 — 두 소스가 갈린 경기를 나중에 셀 수 있다.
- `out_src` 가 값마다 붙어 원장·카드가 "어디서 온 사실인가"를 말할 수 있다.
- ⚠️ **빅매치 한정은 이번에 넣지 않는다.** 태그가 아직 없다(FOT-3 과 같은
  이유). 지금은 전 경기에서 LLM 이 돌되 **보조 칸만** 쓴다.

## ⑤ 시스템에 이미 있는 사실을 다시 적고 있지 않은가

- 스키마·검증·병합은 `scout_config` 원본 그대로.
- FotMob 모양도 `fotmob.parse_lineup` 이 정한 것을 읽기만 한다.
