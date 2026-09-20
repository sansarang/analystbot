# STEP 0 — 발견·대조 (통합 지시문 v2)

편집 0. 측정 2026-09-20 10:30~10:45 KST · 운영 컨테이너/DB/Redis 직접 조회.
HEAD `e8e39a3`.

```
e8e39a3 LDG-2 (b) — 내가 붙인 배선이 LLM 을 끌어들였다. 바로 막는다.
430b259 LDG-2 — 사람 판정 행의 CLV 가 영원히 NULL 이었다.
709aebb OBS-2 — 관측 상태기계가 한 번도 안 돌았다. 그리고 그게 둘이었다.
c267f74 Phase 4 대조 — 그리고 내 계수기가 다섯 번 틀렸다는 정정.
2c6a087 CNF-2 — ⑥의 반증이 구조적으로 불가능했다. 켜는 김에 뜻도 바로잡는다.
```

---

## 0-a. 판정 경로의 LLM 호출 — **한 곳뿐이다**

```
app/flow/nodes/n12_text.py:98    from app.llm.provider import complete
app/flow/nodes/n12_text.py:102   res = await complete("narrator", [...], max_tokens=2000, temperature=0.0)
```

`app/flow/` 전체에서 실제 LLM 호출은 위 둘이 전부다(나머지 매칭은 전부 주석).
④ 가설·⑦ 조정·⑨ 확신·⑪ 값은 이미 코드다.

⚠️ 구경로(`app/engine/`)에는 남아 있다 — `interpret.py:28` · `narrator.py:258` ·
`comparator.py:26` · `interpreter.py:26` · `team_form.py:281` ·
`collectors/grounding.py:170`. 이들은 v1.4 판정 경로가 아니다.

→ **STEP 4** 가 `n12_text` 를 템플릿으로 대체하면 판정 경로 LLM 은 0 이 된다.

## 0-b. fix_direction 산출물

**`app/flow/direction.py`** — 순수 함수 4개:
`era3_of:22` · `starter_direction:31` · `bullpen_direction:61` · `lineup_direction:81` · `merge:97`

**`config/rules.yaml` `flow.direction.*` 원문** (유일한 원본):
```yaml
starter_dev_bad: 0.25
starter_dev_good: -0.25
starter_min_ip: 9.0
starter_short_ip: 5.0
bullpen_ip_heavy: 12.0
bullpen_b2b_heavy: 3
lineup_out_heavy: 2
dev_full: 0.5
```

**FIX-4b(파생 시장 동의·open 검사)** → `app/flow/nodes/n11_value.py:98-116`
`_market_agrees()`. open 이 없으면 `False`(fail closed).
→ **STEP 8** 이 이것을 `n10b_priced_in.py` 로 옮겨 단일화한다.

## 0-c. `snap_tag='open'` 리그별 존재 비율 (최근 30일 · 배당 있는 경기 기준)

| 리그 | 경기 | `open` | `open` 계열(=`open`+`open_proxy`) |
|---|---|---|---|
| MLB | 278 | 11 (**4.0%**) | 278 (100%) |
| NPB | 87 | 3 (3.4%) | 87 (100%) |
| KBO | 73 | 0 (**0.0%**) | 73 (100%) |
| 라리가 | 24 | 4 (16.7%) | 24 (100%) |
| 세리에A | 15 | 5 (33.3%) | 15 (100%) |
| EPL | 14 | 7 (50.0%) | 14 (100%) |
| K리그1 | 14 | 9 (64.3%) | 14 (100%) |
| J1 리그 | 11 | 10 (90.9%) | 11 (100%) |
| ACL엘리트 | 8 | 0 (0.0%) | 8 (100%) |
| 덴마크 | 8 | 3 (37.5%) | 8 (100%) |
| 분데스리가 | 7 | 5 (71.4%) | 7 (100%) |

🔴 **STEP 8 에 직접 닿는다.** 진짜 `open`(T-24h 이전)은 야구에서 거의 없다
(MLB 4% · KBO 0%). 그러나 **`open_proxy` 는 전 리그 100%** 다. 지시문 STEP 8 의
`first_with_tag("open") or first_with_tag("open_proxy")` 순서가 그대로 맞고,
이 폴백이 없으면 야구는 전건 `unknown` 이 되어 픽이 0 이 된다.

## 0-d. 선행 항목 구현 여부

| 항목 | 여부 | 파일:행 |
|---|---|---|
| T-3h·T-60 export 자동화 | **예** | `app/scheduler.py:552 export_t3h_job` · `:559 export_lineup_job` |
| 결장 basis 필드 | **예** | `app/collectors/absences.py:34-39`(IL·lineup_excluded·transfermarkt·fotmob_unavailable) · `classify():51` · export `for_fable.py:712` |
| `pick_ledger.judge_by` | **예** | `db/schema.sql` · `tools/ledger_add.py`(JUDGES 3종) · `tools/report.py:14 --by` |
| 팀토탈·F5 배당 수집 | **예** | `app/collectors/oddsapinet.py:49`(F5 는 별도 칸 `_f5`) |
| 선발 recent 창 라벨 | **예** | `n05_evidence.py:165 _STARTER3_SQL`(최근 3등판) · STR-1 이 `season`→`recent6` 로 정정 |
| 투구수 | **예** | `pitcher_appearances.pitches` (`db/schema.sql:990`) |
| 이닝캡·재활 투구수 제한 | 🔴 **아니오** | 칸 없음. `registry.py:301` 에 IL 상태 문자열 `"rehab assignment"` 가 있을 뿐 |
| 파크팩터 | **예** | `config/park_factors.yaml` (표는 없고 yaml) |
| KBO·NPB 라인업 소스 | 🔴 **부분** | `crawler_feed.py:355` 가 NPB 타순을 다루나 **`lineup_history` 에 야구 0행** |
| FotMob lineupType·unavailable·시장가치 | **예** | `fotmob.py:182 lineup_type` · `:10 unavailable` · `:130 market_value` · `:191 total_market_value` |
| `lineup_history` 리그별 | **축구만** | 18,507행 / 39리그. Championship 960 · DFB Pokal 929 · LaLiga 779 · Serie A 726 · J.League 720 … **MLB·KBO·NPB 0행** |

### 🔴 표가 아예 없는 것 (STEP 7·11·12 가 만들어야 한다)

```
standings          **표 없음**       ← 순위·동기 소스가 0 이다
evidence_cards     **표 없음**       (STEP 7-1)
manual_odds        **표 없음**       (STEP 11)
chat_sessions      **표 없음**       (STEP 11)
jobs               **표 없음**       (STEP 11)
evidence_ledger    **표 없음**       (STEP 12)
park_factors       **표 없음**       (config yaml 로 존재)
team_elo           **표 없음**       ← Redis 캐시로만 산다
soccer_elo         **표 없음**       ← 축구 Elo 자체가 없다
lineup_history     있음 18,507행 (축구 전용)
pitcher_appearances 있음 8,656행
```

Redis elo 키: `elo:mlb:*` · `elo:kbo:*` · `elo:npb:*` 뿐 — **축구 키 0개.**
`bridge.ELO_SPORTS = ("mlb","kbo","npb")` 가 축구를 뺀 것과 일치한다.

## 0-e. 능력 매트릭스 (오늘 경기 1건의 **실제 값**)

`null` 은 호출해서 못 받은 것이고 사유를 함께 적는다.

| 변수 | MLB (g10925) | KBO (g1767) | NPB (g11754) | 축구 (라리가 g11323 등 7리그) |
|---|---|---|---|---|
| ① 사전값 | `elo:mlb:2026-09-19` 30팀 | `elo:kbo:2026-09-20` 10팀 | `elo:npb:2026-09-20` 12팀 | 🔴 **null** — elo 캐시 키 없음 (전 리그) |
| open 배당 | 204행 · open 0 · **proxy 6** | 74행 · open 0 · **proxy 2** | 38행 · open 0 · **proxy 2** | 268~380행 · open 7~11 · proxy 18~21 |
| 결장 | `research.absences` **7건** (예: `Baltimore Orioles의 Dylan Beavers(주전 타자) 라인업 제외로 결장`) | null — 판정 캐시에 absences 없음 | null — 같음 | null — 같음 (전 리그) |
| 확정 라인업 | null — `lineup_history` 0행 | null — 0행 | null — 0행 | 🔴 null — **오늘 경기** 0행 (과거 18,507행은 있다) |
| 핵심 전력 최근 폼 | `pitcher_appearances`(선발) 30일 **26행** | **18행** | **22행** | `games(final)` 홈팀 60일 **0~5경기** (덴마크·J1·K리그1 = 0) |
| 후반 자원·피로 | `pitcher_appearances`(구원) 3일 **7행** | **0행** | **3행** | 🔴 null — 축구 교체 자원 소스 없음 |
| 순위·동기 | 🔴 null — `standings` 표 없음 | 같음 | 같음 | 같음 (전 리그) |
| 일정 | `games` 향후 7일 0경기 | **6경기** | 1경기 | 1경기 |
| 환경 | `venue=Oriole Park at Camden Yards` | null — `venue_name` 없음 | null | null (전 리그) |

### 0-e 추가 — 순위·폼 외부 소스 실측 (2026-09-20 15:20 KST · KJ-1·3·4)

딥서치 로그(K리그·J리그 2026-09-13)가 제시한 소스를 **우리 컨테이너에서**
직접 호출해 확인했다. 남의 보고를 그대로 옮기지 않는다.

| 소스 | 상태 | 바이트 | `<tr>` | 판정 |
|---|---|---|---|---|
| `jleague.jp/standings/j1/` | **200** | 976,619 | **21** (20팀+헤더) | ✅ 정적 HTML — 순위·승점·득실·최근 5경기 폼이 한 페이지에 |
| `flashscore.co.kr/…/k-league-1/standings/` | 🔴 **404** | 6,286 | 0 | ❌ JS 이전에 **URL 자체가 죽었다**(보고는 "JS 렌더링"이라 했으나 이유가 다르다) |
| `gwangjufc.com` (구단 공식) | 200 | 79,810 | 13 | ✅ 정적 — 킥오프·일정 |

**보고된 실패 목록(재확인하지 않고 그대로 옮긴다):**
위키 fetch 불가 도메인 · `matchcalendar` J1 상위 5팀만(table/results **404**) ·
플래시스코어 standings **JS/404** · 다음스포츠 JS 렌더링 ·
아시아뉴스 프리뷰에 대상 경기 없음. **12~14콜 중 성공 약 절반.**

🔴 **KJ-1** `jleague.jp/standings/j1/` 는 J1 순위·폼의 **화이트리스트 1순위**다.
   STEP 0-e 에서 `standings` 는 **표 자체가 없다**고 나왔고, 그래서 v2 STEP 5
   `motivation_gap` 과 STEP 7-3 `motivation_state` 가 소스부터 없었다 —
   J리그에 한해 그 공백이 메워진다.

🔴 **KJ-3** K리그는 순위·폼 **외부 소스가 없다**(플래시스코어 404 · 다음 JS).
   남은 길은 구단 공식(정적) + 연맹 보도자료를 받아쓰는 지방지뿐이다.
   → 능력 매트릭스의 K리그1 `순위·동기` 칸은 계속 `null — 소스 없음` 이다.

🔴 **KJ-4** 같은 보도자료가 **8개 매체**에 뜬다 → 매체 수를 근거 수로 세면
   하나의 원문이 여덟 개로 부풀려진다. `n_sources` 는 매체 수가 아니라
   **서로 다른 원문 수**여야 한다(v2 STEP 7-4 에서 본문 기준 중복 제거).

⚠️ **순위·폼의 1순위 소스는 외부가 아니라 우리 DB 계산이다.** 외부 표는
   **교차검증용**이다(아래 "넘기는 사실" 7·8 참고).

### 0-e 추가 — `games(final)` 적재 완결성 (2026-09-20 15:33 KST)

"완결된 리그는 DB 에서 순위·폼을 계산한다"의 **전제를 실측했다.**

```
리그                 종료   팀   팀당min  팀당max  기간
라리가                54   20      4       7    2026-08-22~2026-09-19
세리에A               42   20      3       5    2026-08-22~2026-09-19
EPL                 28   20      1       5    2026-08-22~2026-09-19
분데스리가             21   18      1       4    2026-08-28~2026-09-19

── 야구(참고)
  mlb   경기 547  팀 30  2024-08-26~2026-09-20
  kbo   경기 269  팀 10  2026-06-28~2026-09-19
  npb   경기 209  팀 12  2026-08-06~2026-09-19
```

🔴 **DB 계산으로 순위·폼을 낼 수 있는 축구 리그는 지금 0개다.**
   · 적재된 리그가 **넷뿐**이다 — K리그1·K리그2·J1·J2·리그앙·에레디비시·
     덴마크·ACL 은 **종료 경기 0행**.
   · 그 넷도 **팀당 1~7경기**다. 정규 시즌(34~38경기)의 한 자리 수이고,
     팀마다 경기 수가 달라(EPL 1~5) **순위표로 쓸 수 없다.**

⚠️ 그러므로 v2 STEP 7-3 의 "완결된 리그만 DB 계산, 나머지만 외부"는
   **지금은 전부 외부**라는 뜻이다. 순서(DB 우선)는 유지하되, 실제로 DB 가
   이길 날은 결과 적재가 시즌 전체로 소급된 뒤다.
   → 선행 과제: **`games(final)` 소급 적재**. 여기서는 사실만 적는다.

⚠️ 야구는 사정이 낫지만 시즌 전체가 아니다(KBO 는 2026-06-28 부터).

---

## STEP 0 이 STEP 1~14 에 넘기는 사실

1. **축구는 ① 사전값이 구조적으로 없다** — 종목 목록에서 빠져 있고 `soccer_elo`
   표도 없다. 오늘 `n03_freeze` 18건의 원인이며 **STEP 1-e** 가 정확히 그 자리다.
   **STEP 10** 이 clubelo 로 채울지를 AUC 로 결정한다.
2. **`standings` 표가 없다** — STEP 5 의 `motivation_gap` 플래그와 STEP 7-3 의
   `motivation_state` 는 **소스부터 만들어야 한다.** STEP 7-2 정본표는
   "실측된 소스만 올린다"고 했으므로 그 규칙대로 처리한다.
3. **야구 `lineup_history` 가 0행이다** — 확정 타순 diff 는 지금 판정 캐시의
   `absences` 문장으로만 가능하고, 그것도 **MLB 만** 찼다.
4. **`open_proxy` 폴백이 없으면 야구 픽은 0 이 된다** (진짜 `open` 4%/0%/3.4%).
5. **판정 경로 LLM 은 `n12_text` 하나** — STEP 4 로 0 이 된다.
6. **이닝캡·재활 투구수 칸이 없다** — STEP 5 `opp_starter_cap` 플래그의 전제라
   STEP 7-3 에서 소스를 함께 만들어야 한다.
7. **순위·폼은 DB 계산이 1순위다.** `games(final)` 이 완결된 리그는 순위·승점·
   득실·최근5 를 **우리가 계산한다**(외부 순위표 불필요 · 폼 방향은 날짜로
   확정된다). 완결되지 않은 리그만 외부를 본다 — 후보 순서는
   FotMob 리그 테이블 → 리그 공식 → 구단 공식이고, **기사 받아쓰기가 마지막**이다.
   구현은 v2 **STEP 7-3**, 여기서는 실측만 한다.
8. **`jleague.jp/standings/j1/` 는 교차검증 소스다** — 하루 1회 캐시하고,
   DB 계산 순위와 승점이 다르면 **결과 적재 누락 경보**로 `/status` 에 띄운다.
   ⚠️ robots·이용약관 확인은 **아직 안 했다** — STEP 7-3 착수 전에 적는다.
