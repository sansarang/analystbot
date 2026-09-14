# SCT-5 — 긁은 본문을 스키마로 추출하지 않는다 (Part 2 / 4-4 배선)

## 왜

`SCT-3` 이 추출 스키마(`EXTRACT_SCHEMA`)·검증(`validate`)·병합(`merge`)·
벤치 판정(`bench_notable`)을 만들었는데 **부르는 곳이 0** 이었다. 위성은 본문을
긁어 캐시에 쌓기만 했고, 결장·XI·최근3 이 **칸으로 서지 않았다.**

그 결과가 오늘 실측된 위험이다 — `analyze.build_input` 은 결장 목록이 비면
`"결장 없음"` 이라고 쓴다. 추출이 없으면 분석 LLM 이 **모든 경기를 "양 팀
결장 없음"으로** 읽는다. "없는 것"과 "모르는 것"을 같게 만드는 자리였다.

재현:
```
PYTHONPATH=. .venv/bin/python <scratchpad>/repro_sct5.py
  → AttributeError: module 'app.collectors.satellite' has no attribute 'extract_facts'
```

## ① 이 함수/상태를 읽는 곳 **전부**

```
$ grep -rn "EXTRACT_SCHEMA\|validate(\|merge(\|bench_notable" app/ tests/
app/engine/scout_config.py   EXTRACT_SCHEMA · validate · merge · bench_notable · rank
   → app/ 안 호출부 **0** (테스트만)
app/collectors/satellite.py  gather() — 기사만 캐시에 쓴다
```
새로 쓰는 곳은 `satellite.gather` 한 곳이고, 읽는 길은 `read_extract` 하나다.

## ② 만드는/바꾸는 상태

| 상태 | 성격 |
|---|---|
| Redis `scout:{sport}:{game_id}` | **새 키.** 추출 JSON(팀별) · TTL 은 기사 캐시와 같은 `CACHE_TTL` |

🔴 **기사 캐시(`satellite:{sport}:{game_id}`)를 덮지 않는다.** 원문과 해석을
   한 칸에 섞으면 어느 쪽이 실패했는지 못 가른다(계약이 그것을 단언한다).
DB 컬럼·env 는 만들지 않는다. 새 외부 소스도 없다 — **이미 긁어 둔 본문**만
읽는다.

⚠️ LLM 은 **무료 사슬만** 쓴다(`judge_route.chain("form")`). 오늘 유료 차단
   (`PAID_LLM_ALLOWED=0`) 뒤 그 사슬은 groq 둘 + openrouter `:free` 다.

## ③ 리그·종목·경로 분기가 생기는가

생긴다. **축구만 추출한다.** 4-4 스키마는 축구 칸(out·xi·bench_notable)이고,
야구 대응(엔트리 말소·타순·선발 최근 3등판)은 지시문이 말만 해 두고 스키마를
주지 않았다. 없는 칸을 억지로 채우면 그게 곧 거짓 재료다. 계약 테스트가
"야구는 추출하지 않는다"를 잠근다.

## ④ 실패하면 "시끄럽게" 실패하는가

- 팀 칸이 없는 추출은 버리고 그 사실을 남긴다(`validate` → None).
- 본문이 없는 기사에는 **LLM 을 태우지 않는다**(돈·시간 둘 다 낭비).
- 추출 0건이면 `[scout] {팀} — 추출 0건` 이 남고, 키를 쓰지 않는다 —
  빈 JSON 을 써 두면 "추출했는데 결장이 없다"로 읽힌다.
- 성공하면 `out` 수·`xi_status`·소스 수·충돌 여부가 한 줄로 남는다.
- 추출이 실패해도 `gather` 의 반환(기사 수)은 그대로다 — 재료 수집을
  해석 실패가 되돌리면 안 된다.

## ⑤ 시스템에 이미 있는 사실을 다시 적고 있지 않은가

- **스키마를 프롬프트에 손으로 적지 않는다** — `EXTRACT_SCHEMA` 의 키에서
  만든다. 칸이 늘면 프롬프트가 따라간다.
- 검증·병합·충돌 규칙·tier 순서는 `scout_config` 원본을 부른다.
- fetch 상한도 `FETCH_PER_STAGE` 를 쓴다(3 을 적지 않는다).
- 캐시 TTL·키 형식은 위성의 기존 상수를 따른다.

⚠️ `bench_notable` 은 아직 코드가 채우지 않는다 — 예상 XI·공식 XI·주전 목록
   셋이 필요한데 주전(최근 10경기 선발)이 배선 전이다. LLM 자기보고를 대신
   쓰지 않는다(지시문 4-4 가 금지). 그 자리는 비어 있고, 그 사실이 남는다.
