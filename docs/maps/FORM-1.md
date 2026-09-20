# FORM-1 영향 지도 — 폼 문자열의 순서를 아무도 검증하지 않는다 (STEP 1-h)

## 0. 재현 — 생산자와 순서 가정 (원문)

**생산자 둘, 둘 다 검증 없음.**

```
app/collectors/football.py:168
    "form": (row.get("form") or "").replace(",", "")
```
football-data.org 가 준 문자열을 **그대로** 넣는다. 순서 가정이 **코드에 적혀
있지 않다** — "가정 없음"이다.

```
app/research/deep.py:33
    "home_recent_form": {"form": "WWLWL (최근 5경기, 최신부터)", …}
app/research/deep.py:62
    "home_recent_form": {"form": "WWDLW (최근 5경기, 최신부터)", …}
```
LLM 에게 **"최신부터"를 요구**할 뿐이다. 돌아온 값을 확인하지 않는다.

소비:
```
app/pipeline.py:461-466
    season_h = {"form": hr.get("form") or "", "position": hr.get("rank"), …}
    out["home_season"], out["away_season"] = season_h, season_a
```

순서를 **쓰지 않는** 소비자도 있다 — `crosscheck._form_win_rate:22` 는 W/D/L
개수만 센다. 문제는 **"직전 경기가 무엇이냐"** 를 읽는 자리다.

⚠️ **v1.4 흐름에는 이 결함이 없다.** `n05_evidence:418` 의 `form_recent5` 는
`_LAST3_SQL`(`ORDER BY starts_at DESC`)로 DB 에서 만든다 — 날짜가 순서를
정한다. 고치는 대상은 **외부에서 문자열로 받는 경로**다.

## 1. 왜 위험한가

소스가 순서를 뒤집어 내보내면 "직전 승"이 "직전 패"로 읽혀 **정반대 판정**이
된다. 값이 그럴듯해서 아무도 모른다.

실측(딥서치 2026-09-13 J리그): `jleague.jp` 표만 보고는 방향을 알 수 없었고,
기사의 "고베 4연승"과 표 `L W W W W` 를 대조해서야 **오래된→최신**임을
확정했다. 그 대조를 안 했으면 지바의 직전 결과를 정반대로 읽었을 것이다.

## 2. 영향 지도 5문

**① 어디를 고치나.** `app/engine/form_order.py`(신규 · 순수 함수).
검증 규칙을 **한 곳**에 둔다 — 생산자마다 각자 검증하면 그게 사본이다.

**② 무엇과 대조하나.** `games(final)` 의 그 팀 **최근 1경기 결과**다.
🔴 외부 소스를 또 부르지 않는다 — 우리 DB 에 이미 있는 사실이다.

**③ 판정 규칙.**
```
최신 쪽 글자 == 최근 1경기 결과      → verified   (그대로 쓴다)
뒤집으면 일치                        → flipped    (뒤집은 값을 쓴다)
둘 다 불일치 · 최근 경기 없음 · 빈 값 → unverified (폼 = null + reason)
```
`null` 폼은 ⑥ 에서 **미상**으로 집계된다. 검증 결과는 증거 카드에 남긴다.

**④ 무엇이 깨질 수 있나.**
🔴 **폼이 null 인 경기가 는다** → ⑥ 미상 비율이 오르고 `모름과반` 이 늘 수
있다. 그건 **정직한 방향**이다 — 종전에는 방향을 모르는 값을 안다고 쓰고
있었다. ⚠️ 반대 위험은 빈 문자열을 `verified` 로 적는 것이고, 테스트가 막는다.

**⑤ 틀렸을 때 알려줄 테스트.**
`tests/test_form1_order.py` 6건 — 검증 함수 존재 · `f_form_ok` ·
`f_form_flipped` · `f_form_unverified` · 최근 경기 없음 · **빈 폼**.

## 3. 이번에 하지 않는 것

- **DB 계산 순위·폼**(1순위 소스)은 v2 **STEP 7-3** 이다. 여기서는 외부
  문자열의 **방향만** 검증한다.
- `jleague.jp` 교차검증 소스 등록도 STEP 7-3 이다.
