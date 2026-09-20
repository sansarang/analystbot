# FMR-1 영향 지도 — FotMob 결과 적재 (STEP 1-i-2)

## 0. 재현 (실측 2026-09-20)

football-data 무료로는 J·K·UEL·ACL 결과를 **받을 수 없다**:

```
/competitions/{FL1|DED|CL|EL|JJL|J2L|ACL|PL|PD}/matches → 전건 ApiAuthError
   "The resource you are looking for is restricted"
```

그런데 FotMob 하루치 목록이 **그 전부를 결과까지** 준다:

```
K-League 1(KOR)  09-13 2경기 종료 2      K League 2  4/4
J. League / J2 / J3 (JPN)  09-19  8·8·4  전부 종료
Europa League(INT)  09-16 9/9            AFC Champions League Elite  2/2
```

🔴 `slate()` 이 `id·league·home·away·utc` 만 뽑고 **점수를 버리고 있었다.**

결과: `games.status` 가 J1 8 · K리그1 2 · ACL 10 **전건 `scheduled`**,
ACL 은 판정 8건이 **영원히 미채점**(채점 0 · 결과 0).

## 1. 연장·승부차기 실측 (지시 ④)

`matchDetails` 6144851(AET) · 6144860(Pen) 원문:

**(a) 정규시간 점수를 직접 주는 칸 — 없다.**
`header.teams[].score` 는 **연장 포함**(3-4)이고, `general`·`header.status`
어디에도 90분 점수가 없다. (`whoLostOnPenalties`·`whoLostOnAggregated` 는 있다.)

**(b) 득점 이벤트의 분은 깔끔히 갈린다.**

```
time=89                                newScore=[2,1]
time=90  timeStr="90 + 1" overloadTime=1  newScore=[2,2]   ← 후반 추가시간
time=94                                newScore=[2,3]   ← 연장 전반
time=107 / 115                         newScore=[3,3] / [3,4]
```

승부차기는 본선 `events` 에 `{"type":"PenaltyShootout","newScore":null}` 로만
있고 점수는 `penaltyShootoutEvents` **별도 배열**에 있다.

🔴 **판정(지시 분기대로)**: (a) 없음 · (b) 분리됨 →
**`minute <= 90` 인 득점만 합산**하고 `result_basis` 에 근거를 적는다.
⚠️ **자기검증** — `AET`/`Pen` 인데 90분 점수가 **동점이 아니면** 계산이 틀린
것이다(동점이라야 연장에 간다) → **수동 확인 목록**. 추측으로 채점하지 않는다.
⚠️ 승부차기 득점은 **어디에도 합산하지 않는다.**
⚠️ 상세 호출은 `reason.short != "FT"` 인 경기에만 한다(오늘 23경기 중 0건).

## 2. 팀 매칭 — `norm()` 실측 (지시 1)

```
Brøndby IF   → 'brndby if'     ❌   (우리 'Brondby IF' → 'brondby if')
SønderjyskE  → 'snderjyske'    ❌
FC København → 'fc kbenhavn'   ❌
Málaga CF    → 'malaga cf'     ✅
1. FC Köln   → '1. fc koln'    ✅
```

원인: `unicodedata.normalize("NFKD", …).encode("ascii","ignore")`.
`á`·`ö` 는 **분해되어** 기본 문자가 남지만, `ø`·`æ`·`ß`·`ł`·`đ` 는 **분해되지
않는 독립 문자**라 `ascii ignore` 가 **통째로 지운다**.

→ **명시적 치환표를 `config/team_name_map.yaml` 에 두고 `norm` 이 읽는다.**
코드에 박지 않는다.

**FotMob 실제 이름·id (지시 3 — "후보 없음" 4건 확정):**

| 우리 이름 | FotMob 이름 | id | 리그 |
|---|---|---|---|
| `Brondby IF` | `Brøndby IF` | **8595** | Superligaen |
| `FC Copenhagen` | `FC København` | **8391** | Superligaen |
| `Jeju United FC` | `Jeju SK` | **133898** | K-League 1 |
| `Club Atlético de Madrid` | `Atlético Madrid` | **9906** | LaLiga |
| `Bayer 04 Leverkusen` | `Bayer Leverkusen` | **8178** | Bundesliga |
| `Real Madrid CF` | `Real Madrid` | **8633** | LaLiga |

🔴 `Jeju SK` 는 **개명**이고 `FC København` 은 **언어가 다르다** — 치환표로
풀리지 않는다. 그래서 `config/team_alias_pending.yaml` 에 적고 **사람이
승인한 행만** 별칭표로 옮긴다. **자동 승격 금지**(AC밀란 오매칭 재발 방지).

⚠️ `SønderjyskE` 는 오늘 경기가 없어 FotMob 이름을 **확인하지 못했다** —
대기표에 `fotmob_id: null` 로 남긴다.

## 3. 영향 지도 5문

**① 어디를 고치나.**

| 파일 | 무엇 |
|---|---|
| `app/collectors/fotmob.py` | `slate()` 가 점수·상태를 함께 뽑는다 · `status_of` · `score_at_90` · `ninety_ok` · `norm` 이 치환표를 읽는다 |
| `config/team_name_map.yaml` (신규) | 발음부호 치환표 |
| `config/team_alias_pending.yaml` (신규) | 승인 대기 별칭 |
| `app/leagues.py` | `fotmob_id` 칸 |
| `app/collectors/finals.py` | 일일 적재에 FotMob 경로 |

**② 새 적재기를 만드나.** 만들지 않는다. **기존 `upsert_slate` 경로**가 같은
`games` 행에 점수·status 를 쓴다(`ext_id='fotmob:{id}'` · 멱등).

**③ 주 소스는 어떻게 가르나.** `leagues.py` 의 `result_source` 로 둔다 —
코드에 박지 않는다. `fd_names` 가 있는 리그는 football-data, 나머지는 FotMob.
겹치는 리그에서 두 소스 점수가 다르면 **덮어쓰지 않고** `conflict` 로그.

**④ 무엇이 깨질 수 있나.**
🔴 **오매칭이 최대 위험이다** — 다른 팀 경기에 점수를 붙이면 채점이 통째로
거짓이 된다. 그래서 (i) 이름으로 한 번 확정된 팀은 **id 우선** (ii) 못 찾으면
**행을 만들지 않고** `unmatched` 로그 (iii) 대기표는 **사람 승인**만.
⚠️ 185개 리그를 전부 저장하지 않는다 — v2 라우터 `league[]` 대상만.

**⑤ 틀렸을 때 알려줄 테스트.**
`tests/test_fmr1_fotmob_results.py` — 상태 매핑 · **실측 JSON 조각으로 만든
`f_fm_aet`** · 동점 자기검증 · 승부차기 미합산 · `slate` 가 점수를 뽑나 ·
`norm` 치환 · **대기표 자동승격 금지**.

## 4. 완료 조건 (원문)

> 09-13~09-20 구간 K1·K2·J1·J2·UEL·ACL 적재 행 수, `games.status` 의
> `scheduled` 잔존 0 확인, ACL 8건 채점 닫힘 로그, unmatched·conflict 목록,
> pytest 마지막 20줄.
> **그리고 1-i-1b 의 `xfail`(test_judge_requires_results)을 뗀다.**
