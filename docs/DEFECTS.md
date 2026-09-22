# DEFECTS — 배선 결함 원장 (정본)

작성 2026-09-21 07:55 KST · 지시문 `wiring_first_0920` W0 ·
**이 표가 정본이다.** 이후 단계는 이 표의 행을 닫는 일이다.

- 배포된 커밋: **`62c3da9`** (실측 `boot_line`)
- 미배포 커밋 2개: `2c6daf0`(FMR-1) · `9b5f39c`(HYC-1)
- 상태 정의 — `열림`(손대지 않음) · `커밋됨`(코드 있음·배포 전) ·
  `배포됨`(운영에 올라감·미검증) · `검증됨`(운영 실측으로 확인)

⚠️ **상태는 증빙 없이 올리지 않는다.** 행마다 원문 1개(커밋 해시 또는 질의
결과)를 붙인다. 증빙이 없으면 `열림`이다.

---

## 표

| id | 증상 | 2026-09-20~21 실측 | 상태 | 커밋 | 단계 |
|---|---|---|---|---|---|
| D01 | 축구 추출 키 불일치 — ⑤는 리그명 키, 위성은 `soccer` 키 | `read_extract(r,"k리그1",11338)` → `{}` · `…,"soccer",…` → 상자 존재. 그래서 K리그 2경기 **증거 0건** | **열림** | — | W8 |
| D02 | 추출 상자 `source`·`fetched_at` 공란 — LLM 에게 맡긴 칸 | 팀 카드 44쪽: `fetched_at` **44/44 공란** · `source` 30/42 공란 → 배포 후 출처 검사 통과 **3/32 (9%)** | **배포됨** | `9b5f39c` | W8 |
| D03 | 위성 추출이 구경로 게이트 라벨에 막힘 | 09-20 K리그 2경기 모두 추출 실행(기사 13·14건 → 상자 생성) | **검증됨** | `6fce5aa` | W8 |
| D04 | 검색 예산 선착순 · DB 변수도 예산 차감 | 09-20 흐름 로그 `(예산 0/5)` — 21경기 전건 소진 0 | **검증됨** | `f500ba8` | W8 |
| D05a | `DEEPSEARCH_SPORTS=soccer` — 야구 기사 수집 꺼짐 | 운영 env 실측 `DEEPSEARCH_SPORTS = soccer` | **열림** | — | W8 |
| D05b | `league_labels()["KBO"]` 가 빈 문자열 | 실측 `{'KBO': 'kbo', 'NPB': 'npb', 'MLB': 'mlb', …}` 전 리그 non-empty | **검증됨** | `ddfc88d` | W8 |
| D06a | 리그앙·에레디비시가 화이트리스트 밖이라 버려짐 | 최근 30일 리그앙 13/15 final · 에레디비시 11/15 final | **검증됨** | `ddfc88d` | W3 |
| D06b | J1·K1·ACL·덴마크 결과 **0건** | 소급 195건 적재 후(11:25 실측) — J1 **80/86** · K리그1 **53/60** · 덴마크 **42/48** · **ACL 20/20(미적재 0)**. 팀당 종료 경기 1 → **7~9** | **검증됨** | `905b194`·`7a4b9db`·`f28c023` | W3-4 |
| D30 | `upsert_slate` 이 **중복 행을 만들었다** | W3-1 배포 직후 같은 경기가 `odds:*`(scheduled)·`fotmob:*`(final) 두 행 — 판정이 붙은 행은 채점이 안 닫힌다. 중복 3그룹 → `apply_result` 로 고치고 병합해 **0** | **검증됨** | `7a4b9db` | W3 |
| D07a | `games.status='scheduled'` 잔존 (종료 6h 초과) | 축구 61경기 · KBO 4경기 | **열림** | — | W3 |
| D07b | ~~채점 미닫힘~~ **오탐(내 오답)** | 갈라 보니 전부 정상 — 진짜 미채점(`graded_at IS NULL`) **0건** · 무승부(분모 제외) 9 · `predicted_side=None`(보드) 2. 규칙 그대로다(`hit = None if side is None or winner=='draw'`) | **정정·닫힘** | `9e3aefd` | — |
| D31 | 종료 근거(`result_basis`)를 버리고 있었다 | FotMob 이 `FT`·`AET`·`Pen` 을 주는데 저장할 칸이 없어 연장 3-2 가 정규시간 홈 승으로 채점된다 | **검증됨** | `9e3aefd` | W3-2 |
| D08a | 폼 문자열 방향 미검증 | `form_order.verify` 배선 완료 | **배포됨** | `983ec66` | W6 |
| D08b | 폼에 대회가 혼재(리그·ACL·컵 구분 없음) | FotMob `teamForm` 에 대회 코드 없음 — 09-20 포항 `last5` 에 ACL 포함 | **열림** | — | W6 |
| D09a | KBO 등판 적재가 09-12 에 중단 | `max(date)` KBO **2026-09-12** (MLB 09-21 · NPB 09-20 정상) | **열림** | — | W5 |
| D09b | `pitches` 전건 NULL (KBO) | KBO 2,367행 중 `pitches` 채움 **0** (MLB 2,511/4,703 · NPB 1,041/1,789) | **열림** | — | W5 |
| D10 | 예고 선발 칸 없음 — 팀 최근 선발을 대신 봄 | `probable_starters` 테이블 없음(스키마 전수) | **열림** | — | W5 |
| D11 | `lineup_history` 야구 0행 | `lineup_history ⋈ games` **조인 결과 0행**(전 종목) | **열림** | — | W5 |
| D12a | 총점·핸디 **경기 커버리지**가 낮다 (※ "0행"은 사실이 아니었다) | 최근 7일 `totals`: KBO 5/23경기 · NPB 7/36 · MLB 54/95 · 축구 44/88 | **열림** | — | W4 |
| D12b | `open` 태그 없음 — 이동을 잴 수 없다 | `with_open` KBO **0/23** · NPB 3/36 · MLB 7/95 · 축구 40/88 | **열림** | — | W4 |
| D12c | 스냅샷 1개일 때 이동을 `0.0` 으로 적는다 | 09-20 포항-서울 등 4경기 `open == now` | **열림** | — | W4 |
| D13 | 장기 결장자가 "평소 타순" 창에서 사라짐 | 09-20 KBO 김도영 — 결장 목록 부재 | **열림** | — | W7 |
| D14a | 결장 명단 팀 귀속 복사(양 팀 동일) | 09-20 마치다@가시와 · AT마드리드@레알 동일 명단 → 배포 후 `abs_same_both_sides` **1 → 0** (09-21 09:00·09:25 실측) | **검증됨** | `3bc759a` | W2 |
| D14b | 타 팀 동명 선수 혼입 | 🔴 **전제가 틀렸다** — 박건우는 NC 26회·롯데 9회로 **동명이인**(g1723 양 팀 동시 출전·타순 2/8). 이름이 유일할 때만 거르도록 배선, `player_team_mismatch` **0** | **검증됨**(정정) | `3bc759a` | W2 |
| D15 | FotMob 경기·팀 매칭 실패 · `norm()` 의 ø·æ 처리 · 개명 팀 | 치환표가 2건(Brondby·SonderjyskE) 닫음. 09-21 슬레이트 `match_unmapped` **1건**(Deportivo A Coruña — 갈리시아어 표기) · 대기표 8행 전건 미승인 | **검증됨** | `2c6daf0`·`bcf363b` | W2 |
| D16 | 휴식 시간이 `games(final)` 기준이라 600h 로 나옴 | 09-20 포항 597~621h. **원인은 계산이 아니라 빈 원본이었다** — 소급 후 팀당 7~9경기(`f28c023`). W6 에서 재측정 | **부분 해소** | `f28c023` | W6 |
| D17 | `venue_name` NULL | 최근 30일 KBO **0/188** · NPB **0/145** · 축구 **0/241** (MLB 296/418) | **열림** | — | W5·W6 |
| D18a | `conflict`·출처 없는 카드를 `confirmed` 로 셈 | 09-20 인천 `conflict=true`·`source=""` 인데 확인 1 | **배포됨** | `9b5f39c` | W9 |
| D18b | `xi_status=lastStarting11` 을 확정 XI 로 셈 | 09-20 두 경기 모두 `lastStarting11`(지난 경기 선발) | **열림** | — | W9 |
| D19 | 소스 없는 변수(`travel`·`motivation`)가 미상 분모에 들어감 | ⑤에 두 변수 분기 **0건** · 추출 스키마에 칸 없음 → 영구 미상 | **열림** | — | W9 |
| D20 | 빈 목록을 "봤는데 없음"(반증)으로 셈 | `lineup_out` 만 `absences` 유무를 보고, 기사·`sources_fed` 조건 없음 | **열림** | — | W9 |
| D21a | 멈춤 사유가 ⑬에 안 남음 | 09-20 ⑬ `why` null **0건**(종전 21건) | **배포됨** | `3349c2e` | W9 |
| D21b | ⑨ 스냅샷에 `sum_adj_pp`·`n_directional` 없음 | 09-20 ⑨ `{grade, reason, confirmed, core_confirmed, struct_*}` — 둘 다 없음 | **열림** | — | W9 |
| D22 | 죽은 공급자가 사슬·스모크에 남음 | 운영 env `JUDGE_PROVIDER=gemini` · 09-20 gemini **402** · groq TPD 소진 → ⑫ 전멸 | **열림** | — | W8 |
| D23 | `standings` 테이블 없음 (순위·동기 산술 불가) | 스키마 전수 — `standings` 부재(`UndefinedTableError`) | **열림** | — | W3 |

## 지시문 표에서 정정한 행

| 원문 | 정정 | 근거 |
|---|---|---|
| D05 한 행 | **D05a / D05b** 로 나눔 | `league_labels` 는 이미 닫혔고(`ddfc88d`) `DEEPSEARCH_SPORTS` 만 열려 있다 — 한 행으로 두면 닫을 때 한쪽이 묻힌다 |
| D06 한 행 | **D06a / D06b** 로 나눔 | 리그앙·에레디비시는 **이미 적재되고 있다**(13/15 · 11/15). 남은 것은 J1·K1·ACL·덴마크다 |
| D07 한 행 | **D07a / D07b** 로 나눔 | `scheduled` 잔존과 채점 미닫힘은 원인이 다르다(적재 vs 채점 잡) |
| D08 한 행 | **D08a / D08b** 로 나눔 | 방향 검증은 배포됐고 대회 혼재만 남았다 |
| D09 한 행 | **D09a / D09b** 로 나눔 | 적재 중단과 `pitches` NULL 은 원인이 다를 수 있다(소스에 없음 vs 파싱 누락) — 아직 갈리지 않았다 |
| D12 "총점·핸디 스냅샷 **0행**" | **사실이 아니다** → D12a/b/c | 최근 7일 KBO `totals` **8,797행**·NPB 9,321행·축구 924행. 문제는 행 수가 아니라 **경기 커버리지**(KBO 5/23)와 `open` 태그 부재다 |
| D18 한 행 | **D18a / D18b** 로 나눔 | conflict·출처는 `9b5f39c` 로 커밋됨, `xi_status` 만 남았다 |
| D21 한 행 | **D21a / D21b** 로 나눔 | ⑬ 사유는 배포됐고 ⑨ 칸만 남았다 |

## 추가 행 (지시문 표에 없던 것)

| id | 증상 | 실측 | 상태 | 단계 |
|---|---|---|---|---|
| D24 | `close` 태그는 있는데 `open` 이 없다 — 규칙이 한쪽만 있다 | 최근 7일 KBO `with_close` 23/23 · `with_open` **0/23** | **열림** | W4 |
| D25 | 미배포 커밋이 쌓인다 | 로컬 `9b5f39c` vs 운영 `62c3da9` — 2커밋 차이 → **`5fbdf5c` 배포 완료 08:20 KST** (`boot_line` 실측) | **검증됨** | 닫힘 |
| D29 | `match_unmapped` 점검이 **세 번 오탐을 냈다** | ±1일 창(25건) · 정규화 규칙 베끼기(20건) · KST 날짜 기준(10건). 셋 다 원본을 안 보고 다시 지은 것 — `bcf363b` 에서 원본(`starts_at`·`find_match`·UTC 색인)에 맞췄다 | **검증됨** | W2 |
| D32 | 소급이 **타국 동명 리그**를 끌어왔다 | 이름만 보고 적재해 EPL 에 694경기(상한 ~70). `'Premier League'` 가 WAL·BLR·RUS·KAZ·EGY·UKR·TAN 에도 있다. `fotmob_ccode` 추가로 막고 오염 750행 삭제(백업 `/data/deleted_polluted_20260921.json`) | **검증됨** | `87ff421` | W3-4c |
| D33 | **robots 가 거부하는 KBO·네이버 경로를 치고 있었다** | `koreabaseball.com/robots.txt` (200·EUC-KR): `User-agent: * / Disallow: /` + "사전 승인 없이 자동 수집·크롤링·복제하는 행위를 금지합니다" 고지. 우리는 7경로 사용 중이었다(kbo.py:31·89 · kbo_stats.py:26·28·29 · kbo_roster.py:25 · kbo_boxscore `/ws/GetBoxScoreScroll`). `api-gw.sports.naver.com` 3경로는 robots.txt 404(판단불가)이나 같은 계열이 `Disallow: /` 라 함께 중단 | **커밋됨** | `SRC-OFF` | [2]a |
| D26 | `fotmob.norm()` 이 **한글을 통째로 지운다** | `norm('박건우')` → `''` (NFKD → ascii ignore). 이름 대조에 그대로 쓰면 한국 선수가 전부 일치한다 | **배포됨**(우회) `3bc759a` — 빈손이면 소문자 정리로 되돌린다. 진짜 해법은 player_id | W2→W5 |
| D27 | `llm.daily_call_cap` 이 **config 에서 안 읽힌다** | `_llm_budget_ok` 가 `app.flow.rules` 를 쓴다 → 경로에 `flow.` 가 붙어 `flow.llm.daily_call_cap` 을 찾는데 실제 블록은 최상위 `llm:` 이다. 실측: `flow.rules → None` · `engine.rules → 200`. 지금은 폴백이 같은 값이라 증상이 없지만 **config 를 고쳐도 반영되지 않는다** | **열림** | W8 |
| D28 | 선수 **id 원본이 없다** | `batter_appearances`·`pitcher_appearances` 에 이름만 있고 id 칸 없음 · `lineup_history` 는 id 칸이 있으나 ⋈ games **0행**. 동명이인(박건우 NC/롯데 · 김민석 두산/KT)이 실재해 이름으로는 귀속을 판정할 수 없다 | **열림**(지시 대기) | W5 |

---

## 다음 단계 순서 (지시문)

`W0 → W1 → W2 → W3 → W4 → W5 → W7 → W8 → W9 → W6 → W10 → W11`

⚠️ 단계마다 T1~T4 증빙과 COVERAGE 전/후를 낸다. 완료 조건 원문 없이 다음
단계로 가지 않는다. 배포는 슬레이트 창(KST 17~22) 밖에서만 한다.

## D34 — 운영 수집 경로가 **브라우저 UA 로 위장**한다 (2026-09-21 · 등록만)

20개 수집기가 `User-Agent: Mozilla/5.0 …` 을 쓴다 — `fotmob`·`flashscore`·
`yahoo_npb`·`satellite`·`news_rss`·`oddsportal`·`kbo_*`·`npb_stats`·
`statcast_velo`·`espn_odds`·`lineup_season`·`starter_season`·`grounding`·
`tor_search`·`deepsearch` 등.

지시문 규율은 "봇 크롤러는 **식별 가능한** User-Agent 를 쓴다"이다. DS-0 프로브만
`AnalystBot/1.0 (+research; respects robots)` 를 썼고 **운영 경로는 전부 위장**이다.

⚠️ 고치면 403 이 늘 수 있다(식별되면 막는 사이트가 있다) — 그것이 이 규율의
   대가이고, 대가를 치르는 것이 규율이다. **범위 밖이라 등록만 한다.**

## D35 — KBO 박스스코어가 **게이트 이전부터** 끊겨 있었다 (2026-09-21 · 등록만)

`batter_appearances`·`pitcher_appearances` 의 `source='boxscore'` 마지막 경기일이
**2026-09-12** 다. SRC-OFF 게이트는 09-21 13:0x 에 켰다 — **9일 전부터** 안 들어왔다.
D09a 와 같은 자리로 보인다. 원인은 경로를 치지 않고 확인해야 한다([2]c).

## D36 — Go 크롤러가 `source_gate` 밖이다 (2026-09-21 · 등록만)

`crawler/internal/source/source.go:137·159` 가 `api-gw.sports.naver.com` 을 10분마다
친다. SRC-OFF 는 Python 진입점 5곳만 막았다.
⚠️ **끄지 않았다** — 지금 KBO 라인업의 **유일한** 공급원이다
(`lineup_events` `source='crawler'` 마지막 경기일 2026-09-20). 끄면 0 이 된다.
사용자 지시를 기다린다.

## D37 — `published_before` 가 datetime·ISO 를 **조용히 통과**시킨다 (2026-09-21 · 등록만)

`app/engine/situation.py:125`. `published` 를 `parsedate_to_datetime(str(raw))` 로
읽으므로 **RFC 2822 문자열만** 파싱된다. datetime 객체나 ISO 문자열
(`2026-09-11 12:00:00+09:00`)을 주면 ValueError → "모르면 통과" 규칙에 따라
**True** 를 돌려준다.

실측 2026-09-21:
```
published_before({'published': datetime(2026,9,11,...)}, 09-21 경기, 'kbo') → True   (통과)
published_before({'published': 'Fri, 11 Sep 2026 12:00:00 +0900'}, …)      → False  (정상)
```
10일 전 기사가 24시간 창을 통과한다.

⚠️ **지금 운영은 멀쩡하다.** `analysis:*` 의 `published` 159건 전부 RFC 2822 이고
   전건 파싱된다(실측). 살아 있는 결함이 아니라 **잠재 함정**이다.
⚠️ 위험한 이유: `json.dumps(..., default=str)` 로 저장하므로 어느 경로든
   datetime 을 넣는 순간 ISO 문자열이 되고, 그 뒤로는 창 검사가 조용히 무력화된다.
   `scout_config.screen` 은 같은 칸을 **datetime 으로** 기대한다 — 두 관례가 공존한다.
⚠️ `app/deepsearch/search.py:verify` 는 `format_datetime` 으로 맞춰 넘긴다(계약이 잠금).

## D38 — `is_recap` 이 **예고 기사**를 경기 후 기사로 버린다 (2026-09-21 · 등록만)

`app/registry.py` 의 `recap_markers` 를 `_norm(w) in title` 로 **부분 문자열**
검사한다. 그래서:

```
[AI프리뷰] 20일 잠실 LG-한화전, 한화 좌완 황준서 선발 기회 살릴
   → 표지 '리뷰' 가 **'프리뷰'** 안에서 걸린다. 정확히 반대 뜻의 기사다.
【中日スタメン速報】ドラ1ルーキー…7月15日以来の勝利目指し先発 岡林勇希が
   → 표지 '勝利' 가 **'勝利目指し'**(승리를 노린다·미래) 안에서 걸린다.
```

🔴 **우리가 가장 원하는 기사(스타멘 발표·프리뷰)를 버리는 방향의 오탐이다.**

⚠️ **지금 운영 규모는 0 이다.** 캐시 기사 제목 137건 중 `is_recap` 이 버린 것
   40건(29%)인데, 그중 라인업·선발 단어가 있고 점수 표기가 없는 오탐 후보는
   **0건**이었다(실측 2026-09-21).
   → 내가 "추출 2/44 의 원인일 수 있다"고 적었던 것은 **측정이 부정했다.**
⚠️ 다만 Bing 결과에서는 **실제로 터졌다**. 소스를 바꾸면 나타나는 위험이다 —
   DS-3 배선 전에 봐야 한다.

## D39 — 상보 표지 목록에 `game summary`·`walk off` 가 없다 (2026-09-21 · 등록만)

D38 을 고치면서 **우연히 가려져 있던 구멍**이 드러났다.

운영 제목 137건 전후 대조(실측 2026-09-21):
```
분류 같음          132
구=폐기 → 신=통과    5   ← 전부 `Twins` 안의 `wins ` 오탐이었다
구=통과 → 신=폐기    0   ← 반대 위험 없음
```

되살아난 5건 중 **둘은 진짜 경기 후 기사**다:
```
Minnesota Twins at Los Angeles Angels - MLB Game Summary - September 20
Detmers joins Ohtani in 200-K club as Angels walk off Twins
```
구 규칙이 이것들을 잡고 있던 이유는 `Game Summary`·`walk off` 때문이 아니라
**`Twins` 안의 `wins `** 때문이었다. 즉 **맞는 결론을 틀린 이유로** 내고 있었다.

⚠️ 표지 목록에 `walk-off`(하이픈)는 있으나 `walk off`(띄어쓰기)가 없고,
   `recap`·`final score` 는 있으나 `game summary` 가 없다.
⚠️ **고치지 않았다** — 표지 목록 변경은 지시받지 않은 파라미터 변경이고,
   늘리면 반대 위험(예고 기사 폐기)이 다시 커진다. 늘릴 때는 137건으로
   전후를 다시 재야 한다.
⚠️ 영향 범위: 둘 다 **MLB** 제목이다. KBO·NPB·축구에서는 이번 대조에서
   새는 것이 없었다.

## D40 — `_daum_fetch` 가 아직 robots 거부 경로다 (2026-09-21 · 등록만)

`app/collectors/satellite.py:320` `_DAUM_URL = "https://search.daum.net/search"`.
`search.daum.net/robots.txt` 는 `Disallow: /` 다([3] 감사 · 커밋 `1303164`).

부르는 곳 둘:
```
satellite.py:452          KBO 기사 검색
satellite_soccer.py:538   축구 기사 검색 (parse_daum_news)
```

⚠️ **DS-3 에서 안 건드렸다.** `rss_hits`(구글 RSS)와 한 번에 바꾸면 무엇이
   깨졌는지 못 가린다. 파서도 다르다(`parse_daum_news` vs RSS).
⚠️ 영향: KBO·축구의 **층1 검색**이 아직 거부 경로로 나간다. DS-3 이 바꾼 것은
   `rss_hits`(현지어 질의 통로)뿐이다.

## D41 — KBO 소스 등급표가 사실상 비어 있다 (2026-09-21 · 등록만)

`config/sources.yaml`:
```
tier1_club_local.kbo  = ['gukjenews.com']   ← 1개
tier2_aggregator.kbo  = []                  ← 빈 목록
tier0_primary         에 kbo 없음
```
그래서 `rank()` 가 `osen.co.kr`·`yna.co.kr`·`mt.co.kr`·`fnnews.com` 을 전부
`RANK_UNKNOWN(9)` 로 본다. 오디션 표의 **"화이트리스트 0%"** 가 이것이었다.

⚠️ **채우지 않았다** — 소스 등급은 "어느 매체를 믿나"라는 판단이고, 내가
   고르면 취향이다. 사용자가 정할 표다.
⚠️ 실측된 KBO 매체 도메인(Bing 12건): `osen.co.kr` · `yna.co.kr` · `mt.co.kr` ·
   `fnnews.com` · `newspim.com` · `sportsworldi.com` · `ajunews.com` ·
   `msn.com`(래핑 4건).

## D42 — 변화 감지에 **파서가 안 붙었다** (2026-09-21 · 등록만)

DS-2(커밋 예정)가 `watch_job` 을 10분마다 돌린다. 운영 실측:
```
1회차  rows 9 · changed 9 (기준선)
2회차  rows 9 · changed 0   ← 잡음이 오탐을 안 만든다
watch_events 9행 기록됨 · 전부 parsed_ok = False
```
🔴 `parsed_ok=False` 는 **파서를 안 넘겼기 때문**이다(`run_watch(parse=None)`).
   즉 **"바뀌었다"는 알지만 "무엇이 바뀌었는지"는 아직 못 읽는다.**

지시문 DS-2a 3 의 나머지가 이것이다:
```
바뀌면 → 파서 → Fact(event_date·as_of 필수) → DS-6 검증 → 카드
```
⚠️ 파서는 페이지마다 다르다(npb.jp 공시 · 구단 공지 · 스포츠나비 경기 페이지).
   **다섯 개를 한 커밋에 넣으면 무엇이 틀렸는지 못 가린다.** 별 단위로 남긴다.
⚠️ 지금 상태의 값어치: 인지 **지연을 재기 시작한다**(`watch_events`). 그 표가
   쌓여야 "공지 게시 → 봇 인지"가 몇 분인지 말할 수 있다.

## D43 — `msn.com` 래핑 기사는 본문이 **3자**다 (2026-09-21 · 등록만)

DS-1W 실측(기사 URL 24건 · 도메인 15종, 본문을 실제로 열어 봄):
```
www.msn.com            본문 3자   × **6건**   ← 24건 중 25%
www.mt.co.kr           본문 1,200자
www.newspim.com        본문 1,200자
www.sportsworldi.com   본문 1,200자
www.starnewskorea.com  본문 1,200자
www.fnnews.com         본문 803자 × 2
www.osen.co.kr         본문 295자
news.yahoo.co.jp       본문 578자 × 2
…
열림 23 · **robots 거부 0** · 실패 1 (chosun.com ReadTimeout)
```

🔴 Bing 결과의 1/4 이 MSN 으로 감싸여 오는데, MSN 페이지는 JS 렌더라
   정적 HTML 에 본문이 없다. **제목만 남는다.**
⚠️ `<News:Source>` 는 원 매체 이름을 준다(`노컷뉴스 on MSN`) — 그 이름으로
   원문을 다시 찾을 수는 있으나 **요청이 한 번 더** 든다.
⚠️ **고치지 않았다.** 선택지가 둘로 갈린다(같은 기사를 원 매체에서 다시 찾기 /
   MSN 결과를 버리기), 둘 다 회수율을 건드린다. 오디션(DS-3a 3)이 답할 자리다.
⚠️ 함께: `www.chosun.com` 이 ReadTimeout 이었다(1건). 반복되는지 봐야 한다.

## 설정 변경 이력 — `fotmob.bulk_allowed` (2026-09-21 신설)

사용자 지시 2026-09-21: "`bulk_allowed` 관문은 **기본 false** 이고, true 로 바꾸는
것은 **사용자 지시가 있을 때만**(설정 변경 이력을 DEFECTS 에 남긴다)."

| 날짜 | 값 | 누가 | 사유 |
|---|---|---|---|
| 2026-09-21 | **false**(신설) | 사용자 결정 1a | FotMob 끄는 방향 · 즉시 대량 호출 중단 |

⚠️ 이 표에 줄이 늘어나지 않은 채로 `bulk_allowed=True` 가 코드나 설정에
   들어가면 **그것이 결함이다.**
⚠️ 테스트에서 `bulk_allowed=True` 를 쓰는 것은 예외다 — 요청이 나가지 않는다
   (`tests/test_lineup_history.py` 가 국가 코드 필터를 시험하려고 연다).

## D44 — 경기 상태의 정본이 둘이다 (2026-09-21 · 등록만)

사용자 지시: "경기 상태 파서가 DB 보다 앞선다는 실측을 **D 행으로 등록**하고,
상태의 정본을 어느 쪽으로 할지는 **W3 에서**."

실측 2026-09-21 17:55 KST — 같은 다섯 경기:
```
                        파서(npb.jp, 17:55)   DB(updated_at 14:00)
中日 vs 広島             final 10-0           live
阪神 vs DeNA             live  2-2            **scheduled**   ← 진행 중인데 '예정'
日本ハム vs オリックス     final 5-3            live
소프트뱅크 @ 라쿠텐       cancelled            cancelled ✅
세이부 @ 마린스          cancelled            cancelled ✅
```
🔴 **파서가 세 경기에서 DB 보다 앞선다.** DB 다섯 행이 전부 `updated_at 14:00`
   이다 — 배치라 사건이 아니라 시각에 맞춰 돈다.

⚠️ **정본을 정하지 않았다.** 지금은 `watch_events` 와 로그에만 남고 `games` 를
   건드리지 않는다. 어느 쪽을 정본으로 할지는 **W3**(결과 적재 경로)에서 정한다.
⚠️ 성급히 파서를 정본으로 삼으면 안 되는 이유: 파서는 NPB 한 리그뿐이고,
   `games.status` 는 채점·발송 게이트가 읽는다.

## D45 — robots.txt 자리에 HTML 이 오면 "허용"으로 읽힌다 (2026-09-21 · 등록만)

실측: `fsp-data-cards-service.uefa.com/robots.txt` 가 **HTML 을 200 으로**
돌려줬다. 규칙 줄(`User-agent:`/`Disallow:`)이 하나도 없으므로
`robots_allows` 가 "빈 robots = 전면 허용"으로 답했다.

🔴 **그건 "파일 없음(판단 불가)"과 같게 봐야 한다.** 허용으로 적으면 거짓이다.

⚠️ 고치는 법(제안): 200 이어도 본문에 `user-agent:` 가 없으면 `unknown` 으로
   본다. `Content-Type` 이 `text/html` 인 경우도 같다.
⚠️ **고치지 않았다** — 감사 표를 이미 낸 뒤라, 고치면 그 표를 다시 돌려야 한다.
   재감사 42행 중 이런 행이 더 있는지 함께 확인할 때 고치는 것이 맞다.

## D46 — 문서 문구가 텍스트 매칭 계약을 깨뜨린다 (2026-09-21 · 오늘 3회)

"코드에 X 가 없어야 한다"를 `X in source` 로 검사하면 **설명하려고 적은 문구**가
걸린다. 오늘 세 번 겪었다:

| 계약 | 걸린 문구 | 실제 뜻 |
|---|---|---|
| `test_별칭_표를_새로_만들지_않았다`(DS-5) | docstring 의 `千葉ロッテマリーンズ` | 표를 만든 게 아니라 **예시를 설명**한 것 |
| `test_추가_검색을_하지_않는다`(ADD-2) | docstring 의 "추가 검색을 하지 않는다" 안의 `fetch`·`await` | **금지를 설명**한 문장 |
| `test_모든_외부_요청이_런타임을_지난다` | docstring 의 `httpx` | 같음 |

🔴 **셋 다 "규율을 설명할수록 계약이 깨지는" 구조다.** 문서를 줄이면 계약은
   통과하지만 그건 잘못된 방향이다.

고친 방식(권장):
- docstring 을 잘라내고 **코드 본문만** 검사 (`src.split('"""')[-1]`)
- 또는 낱말이 아니라 **실제 사용**을 검사(`import httpx` · `httpx.` )

⚠️ 남은 텍스트 매칭 계약에 같은 함정이 더 있을 수 있다. **전수로 고치지
   않았다** — 걸릴 때마다 고치고 여기 줄을 더한다.

## D47 — `park_factors.yaml` 에 Oracle Park 가 없다 (2026-09-22 · 등록만)

사용자 지시 2026-09-22: "D46 park_factors.yaml 에 Oracle Park 없음 →
**W5(구장) 에서 30개 구장 전수 채움.**"

⚠️ **번호를 밀었다.** 사용자가 적은 `D46` 은 이미 다른 결함이다(문서 문구가
   텍스트 매칭 계약을 깨뜨린다 · 2026-09-21). 번호를 재사용하면 원장이
   깨지므로 **D47** 로 적었다. 지난번 D27→D33 과 같은 처리다.

실측 2026-09-22 (fable_request_0922_mlb F 항목):
```
config/park_factors.yaml   최상위 키 ['parks']
Oracle / Giants / SF 로 걸리는 항목   **0건**
```
→ MIN@SF 자료에서 파크팩터 칸이 `null` 이 됐다.

**고칠 자리: W5(구장) 에서 30개 구장 전수.** 한 구장만 채우면 다음 경기에서
같은 일이 난다.
⚠️ 값은 **사용자가 준 표**여야 한다 — 파크팩터를 내가 추정하면 그건 취향이고,
   `config/tiers/kbo.yaml` 이 같은 이유로 "Claude Code 는 이 값을 추측해서
   채우지 않는다"고 적고 있다.

## D48 — MLB 기사가 전부 `MLB Transactions` 다 (2026-09-22 · 등록만)

사용자 지시: "기사 41건이 전부 MLB Transactions 페이지 — **프리뷰·팀뉴스
쿼리가 안 돌았거나 화이트리스트가 좁음. DS-3 쿼리 템플릿(MLB en) 점검.**"

실측 2026-09-22 (game 823169):
```
기사 41건 · 전부 source="MLB Transactions" · 최신 age 289h
url 이 전부 https://www.mlb.com/player/{id} 형태
```
🔴 **어젯밤 DS-3 로 검색을 Bing 으로 갈았는데 MLB 는 그 경로를 안 탄 것으로
   보인다.** 41건이 한 소스뿐이고 289시간 전 것이다.

점검할 것:
1. `config/search_terms.yaml` 에 **mlb 항목이 있나**
2. `scout_config.locale("mlb")` 가 무엇을 주나
3. `satellite` 의 MLB 어댑터가 `rss_hits` 를 **부르나** (KBO·NPB 는 별도
   경로였다 — `_daum_fetch`·`_yahoo_fetch`)
4. 화이트리스트(`sources.yaml` tier*.mlb)가 좁은가

### 🔴 원인을 쟀다 (2026-09-22) — **둘이다**

**(1) `gather_mlb` 이 `rss_hits` 를 부르지 않는다.** `satellite.py:111`:
```python
arts  = transactions_to_articles(...)      ← 41건이 전부 여기서 나왔다
arts += _mlb_velocity_articles(...)
arts += _mlb_weather_article(...)
arts += _tor_supplement(...)               ← 기사 검색은 Tor/DDG 뿐
```
🔴 **`rss_hits` 호출이 0건이다.** 어젯밤 DS-3(`98921cd`)이 `rss_hits` 를 Bing
   으로 갈았지만 **MLB 는 애초에 그 함수를 안 쓴다.** 갈아도 MLB 에는 아무
   변화가 없었다.
🔴 그래서 `config/search_terms.yaml` 의 mlb 항목도 **쓰이지 않는다**:
```
mlb.pre     ["{team} probable pitcher injury report"]
mlb.lineup  ["{team} lineup today"]
locale(mlb) {hl: en, gl: US, ceid: US:en}     ← 다 준비돼 있는데 부르는 곳이 없다
```

**(2) 화이트리스트가 비었다** — D41(KBO)과 같은 상태:
```
tier0_primary.mlb      **키 없음**
tier1_club_local.mlb   []
tier2_aggregator.mlb   []
LOCAL_ALIASES[mlb]     0개
```

⚠️ **고치지 않았다.** 지시는 "점검"이었고, (1)은 `gather_mlb` 에 검색 경로를
   **더하는** 일이라 범위가 크다(MLB 어댑터 구조 변경). (2)는 "어느 매체를
   믿나"라서 **사용자가 정할 표**다(D41 과 같은 이유).
⚠️ **DS-3 의 효과 범위를 정정해야 한다.** 어젯밤 나는 "기사 검색을 robots
   허용 경로로 갈았다"고 적었는데, 정확히는 **`rss_hits` 를 쓰는 경로만**
   갈렸다. MLB 는 그 경로가 아니었다 — 커밋 메시지가 과했다.

## D49 — 야구 `lineup_history` 적재가 아직 안 붙었다 (2026-09-22 · 재확인)

사용자 지시: "09-21 타순이 DB 에 없어 diff 불가 — **lineup_history 야구
적재(W5-3)가 아직 안 붙어 있음의 재확인.**"

실측: MIN@SF 자료에서 `yesterday_diff = null`,
사유 `"어제(09-21) 타순이 DB·캐시에 없다"`.

⚠️ **새 결함이 아니라 재확인**이다. W5-3 이 붙기 전에는 "어제와 무엇이
   달라졌나"를 물어도 답할 수 없다.

## D50 — 요청이 T-35 에 접수돼 폴링 창을 놓쳤다 (2026-09-22)

사용자 지시: "요청이 T-35 에 접수돼 폴링 창을 놓침 — **MLB T-60 자동
폴링(DS-2)이 붙기 전까지는 사용자가 T-90 전에 요청해야 한다.**"

⚠️ **내 잘못이 겹쳤다.** 지시문을 받고 바로 시작하지 않아 그 사이 창이 더
   줄었다. 사용자가 "머하니?"·"모하냐고???"를 세 번 물었다.

운영 규칙(사용자 결정):
```
MLB T-60 자동 폴링(DS-2)이 붙기 전까지 — 사용자는 **T-90 전에** 요청한다.
```
⚠️ MLB 는 지금 `source_map` 의 `watch: true` 대상이 **아니다**(NPB 5행만).
   DS-2 에 MLB 경기 페이지를 더하는 것이 이 항목의 해소 조건이다.

## D51 — (내 오류) 확인 항목의 선수 이름을 로스터에서 뽑지 않았다 (2026-09-22)

사용자 지시: "**(제 오류)** Correa 를 확인 항목에 넣은 것은 제가 로스터를
확인하지 않고 쓴 것. **확인 항목의 선수 이름은 봇의 활성 로스터에서 뽑도록
지시문에 추가.**"

실측: `statsapi teams/142/roster?rosterType=fullRoster` 에 **Correa 가 없다.**

🔴 **이것은 사용자가 스스로 적은 항목이지만, 내가 잡을 수 있었던 것이기도
   하다.** 나는 "로스터에 없음"으로 적고 넘어갔는데, **왜 없는지**를 묻지
   않았다. 이름이 틀렸는지·이적했는지·요청이 잘못됐는지 구분하지 않았다.

해소 방법(사용자 지시):
```
확인 항목의 선수 이름은 **봇의 활성 로스터에서 뽑는다.**
```
⚠️ 그러려면 활성 로스터를 **읽을 수 있는 자리**가 있어야 한다.
   지금은 `statsapi teams/{id}/roster` 를 그때그때 치고 있고, 저장하지 않는다
   (KBO 는 `kbo_roster` 가 있었으나 D33 으로 막혔다).
   → 이 항목은 **W5·W7 의 엔트리 칸**과 같은 자리를 요구한다.

## 🔴 D52 — daum 을 끄자 **KBO 기사 수집이 0 이 됐다** (2026-09-22 · 회귀)

실측 2026-09-22 10:29 KST · 운영 · 오늘 경기 `KT Wiz @ SSG Landers`(18:30):
```
gather_kbo → 기사 **0건**
  [satellite] KBO 다음검색 실패 SSG Landers/라인업 : daum_search robots 거부
  [satellite] KBO 다음검색 실패 SSG Landers/부상   : (같음)
  [satellite] KBO 다음검색 실패 SSG Landers/선발   : (같음)
  [satellite] KBO 다음검색 실패 SSG Landers/엔트리 : (같음)
  … KT Wiz 4건도 같음 (합 8회 전부 차단)

gather_npb → 기사 9건 (Yahoo 경로라 무사)
```

🔴 **내가 만든 회귀다.** DEC-2(`804916a`) 커밋에 이렇게 적었다:

> "DS-3 이 `rss_hits` 를 Bing 으로 갈았으므로 **대체가 이미 있다**"

**그 대체는 연결되지 않았다.** KBO 어댑터(`gather_kbo`)는 `_daum_fetch` 만
쓰고 `rss_hits` 를 **부르지 않는다**(D48 과 같은 구조).
차단 사유 문구에까지 "대체가 있다"고 적혀 나가고 있다 — **그 문구가 거짓이다.**

### 왜 못 잡았나
- 계약 `test_daum_을_부르면_요청이_안_나간다` 는 **차단되는지만** 봤다.
  "차단한 뒤 대체가 도는지"는 **아무도 안 봤다.**
- 전체 스위트 5,519건이 통과했다 — 이것은 **거짓 통과**의 한 부류다
  (막는 것을 시험하고 **메우는 것을 시험하지 않았다**).

### 선택지 (사용자 결정)
| 갈래 | 뜻 | 대가 |
|---|---|---|
| (가) `gather_kbo` 에 `rss_hits`(Bing) 를 **잇는다** | 대체를 실제로 연결 | 어댑터 수정 · 오늘 저녁 슬레이트 전에 배포해야 한다 |
| (나) `daum_search` 를 **다시 켠다** | 즉시 복구 | robots 거부 경로로 돌아간다 |
| (다) 그대로 둔다 | KBO 는 기사 0 · 미상으로 멈춘다 | **오늘 저녁 KBO 카드에 근거가 없다** |

⚠️ 지금 시각 10:29 · 오늘 KBO 첫 경기 **18:30**. 배포 금지 창은 17:00 부터다.
   (가)로 가려면 **17:00 전에** 고치고 배포해야 한다.

### ✅ 처리 — (가) (사용자 결정 2026-09-22 · 수정 단위 `D52F`)

🔴 **문구 정정(사용자 지시 — 삭제가 아니라 정정).** DEC-2(`804916a`) 와
   `source_gate.REASONS["daum_search"]`(운영 로그로 나간다) 의

> "DS-3 이 `rss_hits` 를 Bing 으로 갈았으므로 **대체가 이미 있다**"

는 다음으로 정정한다:

> **"대체 함수(`rss_hits`)는 있었으나 KBO 에 미연결이었다. 2026-09-22 연결."**

⚠️ DEC-2 커밋 메시지 자체는 다시 쓰지 않는다(역사를 고치지 않는다) — 정정은
   **읽히는 자리**에 둔다: 이 항목 · `config/rules.yaml` 주석 ·
   `source_gate.REASONS` · `docs/maps/DEC-2.md` · `gather_kbo` 머리말.

| 무엇 | 어디 |
|---|---|
| `gather_kbo` 가 `rss_hits`(Bing) 를 1순위로 부른다 | `app/collectors/satellite.py` |
| 다음 검색은 **그 팀 RSS 가 0건일 때만** (지금은 게이트가 막는다) | 같음 |
| 꺼진 소스의 대체를 **설정에 선언** (`fallback`·`fallback_consumers`) | `config/rules.yaml` |
| 대체가 없는 소스는 `fallback: none` + 사유 (KBO 공식 = D33) | 같음 |

⚠️ **KBO 하나만 고쳤다**(사용자 지시). NPB(`_yahoo_fetch`)·MLB(transactions+tor)
   는 한 줄도 안 건드렸다. **MLB 의 `rss_hits` 미연결은 D48 로 남아 있고 별도
   커밋(2026-09-23)이다.** MLB 경로의 tor 호출부는 지시대로 보고만 했다.

계약 2건 — **차단과 대체를 따로 시험한다**(D52 의 교훈):
`test_kbo_gather_uses_rss_when_daum_disabled`(가짜 RSS 서버) ·
`test_disabled_source_has_wired_fallback`(소비처 → 대체 **호출 그래프** 검사).
🔴 "함수가 존재한다"로는 D52 를 못 잡는다 — `rss_hits` 는 존재했고 축구에서
   불리고 있었다. **막힌 소비처에서 닿는가**를 본다.



## D53 — 계약이 **시각에 의존해 스스로 깨졌다** (2026-09-22 · 고침)

`tests/deepsearch/test_ds3_wire.py` 의 `BING_RSS` 픽스처는 pubDate 가
**2026-09-20** 으로 고정인데, `rss_hits` 는 신선도 상한
(`scout_config.MAX_AGE_H['pre']` = 48h)을 **지금 시각 기준**으로 건다.

```
같은 코드 · 같은 픽스처
  2026-09-22 10:49 KST  전체 5526 passed
  2026-09-22 11:20 KST  test_출력_모양을_바꾸지_않는다 FAILED
                        (OSEN 기사 48.3h → 폐기 → out[0] 이 MSN 항목으로 밀렸다)
```

🔴 **내 변경이 깬 것이 아니다.** 픽스처 날짜가 창 밖으로 나간 것이고, 이런
   계약은 그날이 오면 반드시 깨진다 — 그리고 그때 사람은 **방금 고친 코드를
   의심한다.** 그게 이 결함의 값어치 있는 피해다.

수정: 픽스처 날짜를 옮기지 않고(그건 사본이다) `now=NOW` 를 박았다.
⚠️ 같은 형태가 다른 계약에도 있는지는 **아직 안 쟀다.** 등록만 한다.


## D11 정정 — **테이블을 잘못 봤다.** 야구 타순은 `lineup_events` 에 살아 있다

원 서술: "`lineup_history` 야구 0행 — `lineup_history ⋈ games` 조인 결과
0행(전 종목)".

🔴 **두 가지가 틀렸다** (실측 2026-09-22 · 운영 DB).

**① 조인 키가 `id` 가 아니다.** `lineup_history.game_id` 에는 **FotMob 경기
   id** 가 들어 있다(`5911161`·`1000015892`). 우리 `games.id` 는 1~16,270 이다.

```
JOIN games g ON g.id = l.game_id                      →     0행   ← 원 측정
JOIN games g ON g.ext_id = 'fotmob:'||l.game_id::text →  4,296행   ← 실제
전체 18,507행 · distinct game_id 527개
```

   남은 77% 는 **우리가 안 보는 리그**다(Championship 960 · DFB Pokal 929 ·
   EFL Cup 918 · League Two 863 · National League 839 · J.League 2 800 …).
   `league IN (SELECT league FROM games)` 가 0 인 것은 리그 **표기**가 다를 뿐이다.

**② `lineup_history` 는 축구 전용이다.** 야구 타순은 **`lineup_events`** 에 적재된다
   (`kbo_lineup_history_job` 의 독스트링이 "`lineup_events` 에 적재"라고 적고 있다).
   그 테이블은 **살아 있다**:

```
sport  source     행수    마지막 경기일
kbo    crawler     148    2026-09-20      ← 살아 있다
kbo    boxscore    380    2026-09-10      ← 멈췄다 (koreabaseball = robots 거부 · D33)
npb    crawler     194    2026-09-21
npb    boxscore    240    2026-09-12
mlb    crawler     616    2026-09-22
mlb    boxscore  1,113    2026-09-21

최근 7일 타순 커버리지: KBO 23/53(43%) · NPB 30/39(77%) · MLB 87/87(100%)
```

🔴 **그래서 "야구 타순 적재가 안 붙어 있다"는 서술은 틀렸다.** 붙어 있고
   돌고 있다. 진짜 결함은 **커버리지**(KBO 43%)와 `boxscore` 소스 중단이며,
   후자의 원인은 이미 아는 것이다 — `koreabaseball` 을 robots 거부로 껐고
   **대체가 없다**(`config/rules.yaml` 의 `fallback: none` 에 그렇게 적었다).

⚠️ D49("09-21 타순이 DB 에 없어 diff 불가")도 **다시 봐야 한다** — MLB 는
   crawler 가 09-22 까지 넣고 있다. 그 항목은 테이블이 아니라 **조회 경로**를
   의심해야 한다. 재측정 전까지 D49 는 "원인 미확정"으로 둔다.


## D24 · D12b 정정 — `open` 태그는 있다. 이름이 **`open_proxy`** 다

원 서술: "`open` 태그 없음 — 이동을 잴 수 없다. `with_open` KBO **0/23**".

🔴 **태그 이름을 틀려 본 것이다**(실측 2026-09-22 · 운영 DB).
   칸 이름은 `tag` 가 아니라 **`snap_tag`** 이고, 값에 `open` 은 없지만
   **`open_proxy` 가 8,727행** 있다.

```
snap_tag 분포   NULL 165,240 · open_proxy 8,727 · late 1,854 · close 1,473
                lineup 1,243 · pre 1,030

최근 7일 · open_proxy 포함
sport    경기   totals   open 확보   close 확보
kbo       53       5        27         23
npb       39       9        39         31
mlb       87      57        87         87
soccer   192      44        78         43
```

| 행 | 판정 |
|---|---|
| **D24** `open` 태그 없음 | 🔴 **정정 — 있다**(`open_proxy`). MLB·NPB 는 전건 확보 |
| **D12b** `with_open` KBO 0/23 | 🔴 **정정 — 27/53**. 측정이 틀렸다 |
| **D12a** 총점 커버리지 | **여전히 열림** — KBO 5/53 · NPB 9/39 · MLB 57/87 · 축구 44/192 |
| **D12c** 이동 0.0 | **미확정** — open==close 인 경기 KBO 2/23 · MLB 14/87 · NPB 3/29 · 축구 8/43. "스냅샷 1개라서 0"인지 "실제로 안 움직였는지" 아직 안 갈랐다 |

⚠️ **코드를 안 고쳤다.** 정정만이다. `open_proxy` 가 진짜 시초가인지
   (이름에 proxy 가 붙은 이유)는 별개 질문이고 아직 안 쟀다.
