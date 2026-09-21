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

