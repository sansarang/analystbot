# HYC-1 영향 지도 — 검증 근거는 코드가 쓴 것만 쓴다

## 0. 재현 (실측 2026-09-20)

운영 Redis 추출 상자 전수(`scout:*:*` 123키 → 팀 카드 42쪽):

```
상자 쪽 수 42 · 종목별 {'kbo': 10, 'soccer': 26, 'npb': 6}
  out 값 있는 쪽      24
  conflict=true       17
  source 빈 칸        30
  fetched_at 빈 칸    42      ← 전건
  세 조건 모두 통과    0  (0.0%)
```

🔴 **`fetched_at` 은 채우는 코드가 0건이다.** `EXTRACT_SCHEMA` 에 칸만 있고
LLM 에게 기사에서 뽑으라고 맡기는데, 기사 본문에 "우리가 언제 수집했는지"가
적혀 있을 리 없다. 42/42 빈 칸은 그 결과다.

🔴 **`source` 도 코드가 채우려던 자리가 죽어 있었다.**
`satellite.py:1214` 의 `got.setdefault("source", picked[0]...)` 는
`validate()` 가 이미 `source: ""` 키를 만들어 두기 때문에 **한 번도 동작하지
않는다**(`setdefault` 는 빈 문자열을 덮지 않는다).

그런데 ⑤는 이 셋을 **하나도 보지 않고** `out` 값이 있으면 증거로 실었다.
오늘 인천-대전의 유일한 `confirmed` 가 그런 카드였다 — `conflict: true`
(무고사·하창래가 결장 목록과 선발 XI에 동시 존재), `source: ""`.

## 1. 사용자 결정 (2026-09-20)

> 수집 시각 검사는 상자 최상위 `gathered_at`(코드가 쓴 값)으로 한다.
> 쪽 카드의 `fetched_at`(LLM 칸)은 검사에 쓰지 않는다.
> `source` 검사도 LLM 칸이 아니라 **코드가 아는 출처**로 한다 —
> 그 LLM 호출에 실제로 넣은 기사 URL 목록을 `sources_fed[]` 로 기록한다.
> `out_src` 가 구조 소스인 카드는 그 소스명과 조회 시각을 출처로 본다.
> LLM 이 채운 값은 버리지 말고 `llm_source`·`llm_fetched_at` 으로 이름만 바꿔
> 남긴다(판정·검사에 쓰지 않는다).

## 2. 영향 지도 5문

**① 어디를 고치나.**

| 파일 | 무엇 |
|---|---|
| `app/engine/scout_config.py` | `EXTRACT_SCHEMA` 에서 `fetched_at` 제거 (프롬프트가 스키마에서 생성되므로 프롬프트도 같이 빠진다) |
| `app/collectors/satellite.py` | `extract_game_facts` 가 **LLM 에 실제로 넣은 기사 URL**을 `sources_fed` 로 쓴다 · LLM 의 `source`/`fetched_at` 을 `llm_*` 로 개명 · 죽어 있던 `setdefault("source", …)` 제거 |
| `app/flow/nodes/n05_evidence.py` | `card_trust()` 신설(순수 함수) · `_extract_box` 가 **상자 전체**를 돌려준다 · 못 믿을 쪽은 증거로 싣지 않고 `value=None` + `untrusted_reason` |

**② 새 수집기·새 테이블을 만드나.** 만들지 않는다. 기록은 이미 쓰고 있는
상자(`scout:{sport}:{game_id}`)에 칸 하나가 는다.

**③ 규칙은 어디에 한 번만 두나.** `n05_evidence.card_trust` 한 곳이다.
⑥은 그 결과(`value=None`)를 **이미 있는 규칙**으로 읽는다 —
`_judge`: `None → unknown`. 채점 쪽에 조건을 다시 적지 않는다(사본 금지).

**④ 무엇이 깨질 수 있나.**

- 🔴 **증거가 줄어든다.** 그것이 정직한 방향이다 — 종전에는 검증할 수 없는
  값을 검증된 것처럼 세고 있었다. 다만 **이미 쌓인 상자에는 `sources_fed` 가
  없으므로** 배포 전 상자는 전부 미상이다(아래 3절).
- ⚠️ **공식 결장을 같이 버리면 안 된다.** `_cache_absences` 는 상자가 아니라
  판정 캐시에서 온다 — 상자 카드가 못 믿을 것이어도 그대로 센다.
  계약 테스트가 이 **반대 위험**을 잠근다.
- ⚠️ `_extract_box` 반환 모양이 바뀐다. 옛 모양(teams 만)으로 주입하는
  테스트가 7개 있어 **두 모양을 다 받는다**(`teams` 키가 있으면 상자,
  없으면 teams-only 로 읽고 메타는 없음).
- ⚠️ `merge()` 는 `source` 로 순위를 매긴다 — 개명은 **merge 뒤**에 한다.
  merge 동작은 한 글자도 바뀌지 않는다.
- ⚠️ `analyze.fact_words` 는 `EXTRACT_SCHEMA` 를 돌며 낱말을 만든다.
  개명한 칸은 스키마 밖이라 **자동으로 빠진다**(추가 조치 불필요).

**⑤ 틀렸을 때 알려줄 테스트.** `tests/pipeline/test_hyc1_card_trust.py` —
픽스처 `f_box_no_gathered_at` · `f_box_no_sources_fed` · `f_box_struct_source` ·
`f_llm_source_ignored` · `f0920_incheon`(오늘 실측 상자) + ⑤⑥ 배선 + 반대 위험.

## 3. 옛 상자 복원 가능성 (사용자 요구 — 먼저 본다)

**복원되지 않는다.** 상자에 남은 것은 `gathered_at` 과 팀 카드뿐이고,
"그때 LLM 에 넣은 기사가 무엇이었나"를 가리키는 칸이 없다.
URL 묶음 캐시 키(`scout:x:{해시}`)는 **해시**라 URL 로 되돌릴 수 없고,
기사 캐시(`satellite:{sport}:{game_id}`)에는 그날 모은 기사 **전부**가 있을
뿐 그중 어느 것이 프롬프트에 들어갔는지는 기록이 없다.
추정으로 채우면 그것은 **지어낸 출처**이므로 하지 않는다.

→ 기존 상자는 미상으로 둔다. 사후 재실행에서 증거가 줄어드는 것은 감수한다
(사용자 결정 원문). 배포 뒤 위성이 한 번 돌면 새 상자부터 `sources_fed` 가 붙는다.

## 4. 다음 커밋 (HYC-1b · 범위 밖)

기사별 수집 시각을 위성이 코드로 기록하고, LLM 출력이 `source` 문자열 대신
`article_idx` + `quote` 를 돌려주게 한다. 그때 상자 단위 검사를 **항목 단위**로
좁힌다. 이 커밋에서는 하지 않는다.
