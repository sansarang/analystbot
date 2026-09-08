# 전수 검토 발견 목록 (2026-09-07) — 코드 수정 없음

## app/config.py

- **C-1 [중] `intent_model` 이 두 번 선언돼 앞 줄이 죽었다.**
  51행 `intent_model: str = "claude-haiku-4-5"` / 454행 `intent_model: str = ""`.
  pydantic 은 뒤가 이긴다. 51행은 실행되지 않는 죽은 줄.
  ⚠️ 이 파일 26~27행이 `gemini_api_key` 에 대해 **똑같은 사고**를 경고해 뒀는데
     같은 결함이 `intent_model` 에 그대로 남아 있다.

- **C-2 [상] 설정은 야구 딥서치를 끄고 있는데 야구 딥서치가 돈다.**
  324행 `deepsearch_sports = "soccer"` · `deepsearch_enabled()` 는 soccer 만 True.
  그런데 `game_trace` 에 mlb 559 · npb 8 · kbo 4 건의 딥서치 기록이 있다.
  호출부는 `pipeline.py:305`, `pipeline.py:1558` 둘뿐 — 어느 경로가 이 스위치를
  우회하는지 확인 필요.

- **C-3 [중] `disabled_providers="grok,perplexity"` 인데 grok 을 최종 판정에 쓴다.**
  367행. 오늘 `judge_route.chain` 이 Anthropic 소진 시 `xai` 를 돌려주도록 바꿨는데,
  가드는 `is_disabled("xai")` 를 보므로 걸리지 않는다(이름이 `grok` vs `xai`).
  433~435행이 "grok(xAI) 과 groq 은 다르다, 한 글자 차이가 사본으로 굳었다"고
  경고해 둔 바로 그 자리에서 설정과 실제가 어긋난다.

- **C-4 [하] 죽은 모델명.** 49행 `judge_model = "claude-opus-4-6"`.
  `soccer_judge_enabled=False` 라 지금은 안 쓰이지만, 켜면 존재하지 않는 모델명.

- **C-5 [중] 한시 조치가 상시가 됐다.** 537~545행 `market_agree_required=True` 는
  "재캘리브레이션 끝나면 꺼라"는 한시 조치인데 켜진 채다. 오늘 실측상
  추천 33.3%(n=15) < 보드만 58.8%(n=97) 로 목적을 달성하지 못했다.

## app/db.py

- **D-1 [상] `get_pool()` 에 동시성 잠금이 없다.** `if _pool is None: _pool = await create_pool(...)`.
  두 코루틴이 동시에 들어오면 풀이 **두 개** 만들어지고 하나는 참조를 잃은 채
  커넥션을 붙잡는다. 스케줄러 기동 시 잡이 병렬로 뜨는 구조라 실제로 가능하다.
- **D-2 [중] 스키마 적용 실패가 매 호출 재시도된다.** 실패 시 `_schema_applied` 가
  False 로 남아 **모든 `get_pool()` 호출마다** schema.sql 전체를 다시 실행한다.
  DDL 은 락을 잡으므로 실패가 지속되면 DB 부하가 눈덩이가 된다.
- **D-3 [중] `create_pool` 에 크기 지정이 없다** → asyncpg 기본 min=10/max=10.
  스케줄러·봇·크롤러가 각각 10개를 잡는다. 다른 코드(tools·프로브)는 전부
  `max_size=3~4` 를 명시하는데 본체만 무제한이다.
- **D-4 [하] `SCHEMA_PATH.read_text()` 인코딩 미지정.** 파일에 한글 주석이 대량인데
  플랫폼 기본 인코딩에 의존한다. 저장소 다른 곳은 `encoding="utf-8"` 을 쓴다.

## app/api_guard.py

- **G-1 [상] 이름 정규화가 xai/grok 을 갈라놓는다.** `_KEY_ATTR` 는 `grok` 키에
  `xai_api_key` 를 매달아 두는데, provider 이름이 `xai` 로 오면
  `canonical_provider("xai")` 는 아무것도 못 맞춰 `"xai"` 를 그대로 돌려준다.
  → 차단이 `api:blocked:xai` 와 `api:blocked:grok` 두 곳으로 갈린다.
  오늘 `judge_route` 가 Anthropic 소진 시 `xai` 를 쓰도록 바뀌면서 실효 위험이 생겼다.
- **G-2 [상] `_memory` 가 Redis 보다 먼저 읽혀 원격 해제를 못 본다.**
  `_get` 은 `_memory` 에 값이 있으면 Redis 를 안 본다. `tools/unblock` 을
  `railway ssh` 로 **다른 프로세스**에서 돌리면 Redis 는 지워지지만 스케줄러
  프로세스의 `_memory` 는 그대로 → 재기동 전까지 계속 차단.
  ⚠️ CLAUDE.md 가 "해제는 사람이 tools/unblock 으로 한다"고 규정한 바로 그 경로다.
- **G-3 [중] Redis 클라이언트를 호출마다 새로 만들고 닫는다.** `raise_if_unusable`
  은 모든 외부 호출 앞에 있어 핫패스다.
- **G-4 [하] `canonical_provider` 의 부분문자열 매칭이 순서에 의존한다.**
  길이 내림차순 정렬로 지금은 맞지만, `football` / `football_data` 처럼
  접두 관계인 이름이 늘면 조용히 오분류된다.

## app/notify.py

- **N-1 [중] `recharge_url` 이 dict 삽입 순서에 의존한다.** `football_data` 가
  `football` 보다 앞에 있어서 지금 맞다. 순서가 바뀌면 잘못된 충전 링크가 나간다.
- **N-2 [하] `recharge_url("xai")` → None.** grok 링크는 `"grok"` 키에만 있다(G-1 연쇄).
- **N-3 [하] `_notified` 는 죽은 전역.** 147행. `reset_notified` 만 비우고 아무도 안 읽는다.

## app/alerts.py

- **A-1 [상·중대] 전역 알림 예산을 리포트가 먹어 **진짜 경보가 조용히 막힌다.**
  `_send` 는 `bypass_suppression` 여부와 무관하게 `_over_budget()`(INCR)을 **먼저**
  부른다. `prefetch_report`·`cycle_report`·`cycle_errors`·`dispatch_report`·`crashed`
  는 전부 bypass 라 예산을 쓰기만 하고 막히지 않는다. 그 결과 10분 12건을 넘기면
  **`watchdog()`·`stage_failed()`·`stages_summary()` 만 막힌다.**
  → 시끄러운 정상 리포트가 조용한 고장 경보를 밀어낸다.
- **A-2 [중] 억제된 알림도 예산을 먹는다.** `_claim` 이 False 여도 INCR 은 이미 됐다.
- **A-3 [상] `our_frames` 가 운영에서 무력하다.** 필터가 `"/app/" in f.filename` 인데
  배포 경로가 `/app/.venv/lib/python3.12/site-packages/...` 라 **라이브러리 프레임이
  전부 "우리 코드"로 잡힌다**(오늘 railway 트레이스에서 실측). 알림에 실리는
  "위치(우리 코드)" 가 asyncpg 내부를 가리킨다.
- **A-4 [중] 같은 실패가 두 번 나간다.** 전면 중단은 `stage_failed` 로 즉시,
  같은 항목이 `stages_summary` 의 `bad` 에도 들어가 끝에 또 나간다(억제 키가 달라 통과).
- **A-5 [중] `cycle_report`/`cycle_errors` 억제 키에 분(minute)이 들어가 억제가 무효.**
  bypass 라 어차피 안 막지만, A-1 과 겹쳐 예산만 태운다.
- **A-6 [중] `dispatch_report` 가 `unchanged` 를 발송으로 센다** → 발송률이 부풀 수 있다.
- **A-7 [하] `reset_shared` 가 `KEYS alert:*`** — 운영 Redis 블로킹 명령.

## app/registry.py

- **R-1 [상] `x_account_is_official` 이 흔한 낱말을 공식 계정으로 인정한다.**
  팀명을 공백 분해해 3글자 이상 낱말을 전부 후보로 넣는다 —
  "New York Yankees" → `new`·`york`·`yankees`. `@new`·`@york`·`@red`·`@bay` 같은
  무관 계정이 **구단 공식**으로 승격된다.
- **R-2 [중] `is_trusted_source` 가 부분문자열이라 도메인 위조에 열려 있다.**
  `"mlb.com" in "mlb.com.evil.example"` → True.
- **R-3 [중] `_RECAP_EN` 이 정밀도·재현율 양쪽에서 어긋난다.** `"hits "`,`"wins "`,
  `"snap"`,`"photos"` 같은 흔한 낱말은 정상 기사를 죽이는데, 정작 오늘 실측에서
  본 노이즈("Condensed Game", "Live Stream: How to Watch")는 통과했다.
- **R-4 [하] `WATCHED_JOBS.job_id` 는 스케줄러 잡 이름의 사본.** 주기는 안 적었지만
  이름은 적혀 있어, 잡 이름이 바뀌면 워치독이 없는 잡을 감시한다(대조 테스트 필요).

## 발송 통계 (alerts ↔ pregame_push ↔ dispatch_stats)

- **P-1 [중] `alerts.dispatch_report` 는 호출부가 0건 — 죽은 코드.**
  (`daily_summary` 는 `dispatch_stats.render/summary` 를 따로 쓴다.)
  게다가 `run_pregame()` 반환 dict(`due/sent/revised/skipped/failed/unavailable`)와
  `dispatch_report` 가 읽는 키(`target/unchanged/misses`)가 **하나도 안 맞는다** —
  누가 실수로 연결하면 `target=0` → 발송률 "—", `misses={}` → "미발송 0건" 이
  나가며 조용한 0을 만든다.
- **P-2 [중] 로그와 원장이 다른 이름을 쓴다.** `pregame_push.py:605` 는
  `skip_reason=both_hash_same` 을 로그에 찍고, 608행은 원장에 `unchanged` 로 적는다.
  `dispatch_stats.REASON_KR["both_hash_same"]` 은 그래서 영원히 안 쓰이는 항목이다.
  ⚠️ `matchup.py:876~879` 이 "로그와 원장이 다른 말을 했다"는 같은 사고를
     이미 기록해 뒀는데 여기 그대로 남아 있다.

## tools/unblock.py

- **U-1 [상] 문서가 동작하지 않는 명령을 안내한다.**
  독스트링: `railway run python -m tools.unblock --list  # 운영에서`.
  그런데 루트 CLAUDE.md 는 **`railway run` 은 로컬 실행이라 `.railway.internal`
  Redis 에 닿지 않는다**고 실측으로 못박아 뒀다(2026-09-05, 이 도구가 바로 그
  실패 사례로 적혀 있다). 도구의 안내문만 갱신되지 않았다.
- **U-2 [상] 원격 해제가 실행 중인 프로세스에 반영되지 않는다** (G-2 연쇄).
  `clear_block` 은 자기 프로세스의 `_memory` 와 Redis 만 지운다. 스케줄러의
  `_memory` 는 그대로라 재기동 전까지 계속 차단 상태다.

## app/pipeline.py (6,140줄) — 1~2000행

- **PL-1 [중] `_collect_research` 의 타입 주석·독스트링이 반환값과 다르다.**
  선언 `-> tuple[str, list[str], dict, dict]` (4개) · 독스트링도 4개인데
  실제 `return` 은 **5개**(sentiment 추가). 읽는 사람이 매번 속는다.
- **PL-2 [상] 병렬 리서치 경로에만 실패 폴백이 없다.**
  `sequential=True` 는 `except` 에서 `statuses[g["id"]]="missing"` 을 남긴다.
  `sequential=False`(gather) 는 `return_exceptions=True` 로 예외를 삼키는데
  `results[0], results[1]` 만 읽고 나머지는 **버린다** → 실패한 경기는
  `statuses` 에 키가 아예 없어 `record("리서치", …)` 계측에서 조용히 빠진다.
- **PL-3 [상] 야구는 "리서치" 계측이 언제나 ✅ 다.**
  `_deep_off` 이면 `_ok_research = _research_total` 로 **성공을 대입**한다.
  야구는 항상 `_deep_off` 이므로 이 단계는 절대 실패할 수 없다 —
  같은 파일 1743행이 "분모가 자기 자신이라 절대 실패할 수 없었다. 계측이
  아니라 장식이다"라고 비판한 것과 같은 형태다.
- **PL-4 [상] 축구 xG 를 수집해서 버린다.**
  1988행 `statcast_data = (by_league, {})` — **튜플**. 그런데
  `merge_source_data` 첫 줄이 `if not isinstance(statcast_data, dict): return []`
  라 축구는 병합이 **한 번도 실행되지 않는다.** Understat xG 를 리그별로 받아
  로그까지 찍고 그대로 버린다.
- **PL-5 [상] `load_source_bundle` 의 독스트링이 코드와 정반대다.**
  "Redis 캐시에서만 읽는다. HTTP 재수집은 하지 않는다. 라인업 폴링이 30분마다
  공식 기록실을 치면 안 된다" 라고 적어 놓고, 바로 아래 KBO 분기에서
  `refresh_naver(redis, date)` 로 **HTTP 재수집을 한다**(1024~1029행).
- **PL-6 [중] `_market_probs` 에 배당 나이(stale) 검사가 없다.**
  `DISTINCT ON (book, side) … ORDER BY captured_at DESC` 만 하고 시각 상한이
  없어 **며칠 전 배당도 "최신"** 으로 잡힌다. 같은 저장소를 읽는
  `market_baseline.p_market` 은 `market_snapshot_max_age_min`(90분)을 검사한다 —
  한 저장소를 두 규칙으로 읽는다.
- **PL-7 [중] MLB 라인업 확정이 DB 로 내려가지 않는 경로가 있다.**
  `_merge_mlb` 는 `jg["lineup_status"]="confirmed"` 를 **직접 대입**하고
  `_lineup_promoted` 플래그를 세우지 않는다. 그래서 `sync_lineup_status` 가
  즉시 False 로 빠지고 `_persist_lineup_rows` 도 안 돈다.
  (`promote_lineup_status` 경로만 플래그를 세운다 — 그건 크롤러/네이버 전용.)
- **PL-8 [중] Redis 장애 시 구제 가드가 통째로 열린다.**
  `ensure_analysis_cache` 의 가드는 `except Exception: 계속 진행` 이라
  Redis 가 죽으면 **5분 폴링마다 전체 파이프라인**이 돈다. 주석이 스스로
  "5분마다 돌면 Sonnet 6~15콜 × 100틱" 이라고 경고한 그 상태가 된다.
- **PL-9 [중] `_wp` 의 접미사 양방향 매칭이 오매칭을 만든다.**
  `team.endswith(name) or name.endswith(team)` — "Sox"/"Red Sox"/"White Sox"
  처럼 접미가 겹치면 dict 순회 순서에 따라 **다른 팀 승률**을 준다.
- **PL-10 [중] `_collect_mlb_stats` 의 박스스코어 수집이 순차·무상한.**
  14일 폼의 모든 game_id 를 `for pk in pks:` 로 하나씩 받는다(최대 ~90 요청).
- **PL-11 [하] `analysis_cache_ready(raw, date, sport="")` 의 기본값이 위험하다.**
  sport 를 빠뜨리면 MLB 가 KST 문자열 비교로 떨어져 **언제나 False** —
  독스트링이 기록한 바로 그 사고(하루치 구제 토큰 소진)가 재발한다.

## app/pipeline.py — 2000~3900행

- **PL-12 [최상] 시장 동의 게이트가 문서와 정반대로 동작한다.**
  `market_disagreement()` 독스트링: "**추천은 시장과 같은 방향일 때만**".
  실제 구현: `abs(우리_p_home − 시장_p_home) >= 4%p → 탈락`. 이건 **방향이 아니라
  거리** 검사다. 결과:
    · 둘 다 홈 우세인데 우리 0.56 · 시장 0.51 → 5%p → **탈락** (방향은 같다)
    · 우리 0.52(홈) · 시장 0.49(원정) → 3%p → **통과** (방향이 갈렸다)
  v1.4 의 핵심 게이트가 의도한 것과 다른 것을 재고 있다.
- **PL-13 [상] 시장값이 없으면 추천이 아예 불가능하다.**
  `market_disagreement` 는 `p_market_send` 가 None 이면 `MARKET_MISSING` 을 돌려주고
  `qualifies()` 는 그것도 탈락으로 친다. 오늘 실측에서 **시장 미수집 34경기가
  61.8% 로 가장 잘 맞았는데**, 그 구간은 구조적으로 추천에서 배제된다.
- **PL-14 [중] 근접픽이 시장 탈락 사유를 말해주지 않는다.**
  `near_miss_picks` 의 사유 목록에 market 항목이 없다. 야구 추천 탈락의
  최대 원인이 시장 게이트인데 사용자는 "왜 탈락했는지" 볼 수 없다.
- **PL-15 [중] `_compute_picks` 를 야구에서 두 번 돌린다(순수 낭비).**
  2220행 계산 → `_apply_line_moves`(야구는 전건 skip) → 2224행 재계산.
  `build_board`·`qualified_singles` 가 슬레이트 전체에 대해 두 번 돈다.
- **PL-16 [중] `_second_opinion` 의 `except (ApiQuotaError, Exception)`.**
  `Exception` 이 이미 포괄해 앞의 항목은 죽은 코드이고, 결과적으로
  **크레딧 소진 예외가 여기서 삼켜져** 상위의 슬레이트 중단 로직에 닿지 않는다.
- **PL-17 [중] `_attach_verdicts` 가 `v["p_claude"]`·`v["verdict"]` 를 직접 인덱싱.**
  나머지 필드는 `.get()` 인데 둘만 대괄호 — 판정 JSON 에 키가 빠지면 KeyError 로
  슬레이트가 죽는다.
- **PL-18 [중] 재판정 경로에는 RSS·그라운딩 주입이 없다.**
  `_run_baseball_forms` 만 뉴스/그라운딩을 `research` 에 꽂는다.
  `_run_baseball_matchups` 단독 호출(라인업 재판정)에서는 그 주입이 없어
  그 회차의 자료2 는 낮에 받은 것 그대로다.
- **PL-19 [하] `_run_baseball_matchups` 가 종목을 `games[0]` 하나로 결정한다.**
  빈 목록이면 `""` 가 되어 elo 조회가 무의미해진다(오늘 실측한 자료12 공백과
  같은 계열의 취약점).

## app/pipeline.py — 3900~6141행 (완독)

- **PL-20 [최상] 신선도 게이트 전체가 꺼져 있다.**
  `_freshness_gate` 첫 줄: `if settings.is_disabled("grok") … : return cached_card`.
  `disabled_providers` 기본값이 `"grok,perplexity"` 이므로 **항상 첫 줄에서 반환**한다.
  그 뒤에 있는 것들이 전부 도달 불가가 된다:
    · `_refresh_stale_research` (리서치 신선도 게이트)
    · **야구 3리그의 크롤러 diff 속보 감지** — 주석은 "크레딧이 끊겨도 동작한다"
      고 적혀 있는데, grok 비활성 하나로 같이 죽었다.
  결과: 카드 캐시가 있으면 12시간 동안 갱신 없이 같은 카드를 돌려준다.
- **PL-21 [상] `ensure_game_fresh` 가 판정 승계 보호를 우회한다.**
  `_save_caches` 는 "여기가 유일한 전체 덮어쓰기 지점이라 막을 곳도 여기 한 곳"
  이라고 선언하고 `_carry_verdicts` 로 판정을 지킨다. 그런데 `ensure_game_fresh`
  (5761행)는 `redis.set(f"analysis:…")` 를 **직접** 호출한다 →
  2026-09-06 15:34 "캐시 재생성이 Opus 최종 판정을 지웠다" 사고가 이 경로로는
  여전히 가능하다.
- **PL-22 [중] `_reco_reject_detail` 에 `if False:` 죽은 블록**(5067행).
  시장 괴리 사유를 적는 코드가 통째로 비활성이라, 단식 0건 사유에 **시장 게이트가
  절대 표시되지 않는다**(PL-14 와 같은 결과).
- **PL-23 [중] `_reco_reject_detail` 이 다른 기준으로 자격을 판정한다.**
  보드 행 `c` 를 `qualifies(c)` 에 **감싸지 않고** 그대로 넘긴다. `sport`·
  `lineup_status`·`p_market_send` 가 없어 야구 분기를 안 타고 `two_source` 만 본다.
  `qualified_singles` 는 `wrapped` 로 감싸는데 여기만 안 감싼다 — 같은 질문에
  두 답이 나온다.
- **PL-24 [중] `_reco_reject_detail` 은 배당 없는 행을 건너뛴다** (`not c.get("odds")`).
  야구는 대부분 배당이 없어 결과가 늘 비고, "자격을 통과하지 못한 마켓도
  없습니다 — 배당·판정이 부족한 슬레이트입니다" 라는 오해를 부르는 문구가 나간다.
- **PL-25 [중] `_render_card` 의 `surest` 선정식이 사실상 확신도만 본다.**
  `confidence*100 − |p_claude−p_market|*100` — 확신도 한 단계가 괴리 100%p 를
  이긴다. 그런데 오늘 실측상 확신도는 정보가 아니다.
- **PL-26 [중] `except (ApiQuotaError, Exception)` 이 두 곳**(`_second_opinion`
  5306행·`_rejudge_after_breaking`). `Exception` 이 포괄하므로 앞은 죽은 절이고,
  결과적으로 **크레딧 소진이 삼켜져** 상위 중단 로직에 닿지 않는다.
- **PL-27 [하] `run_pipeline` 이 `int(remaining)` 을 방어 없이 호출**(5868행).
  Redis 값이 숫자가 아니면 ValueError 로 파이프라인이 죽는다.

## app/engine/matchup.py

- **M-1 [상] "최종은 한 번" 규약이 함수 안에서 깨진다.**
  `config.py:274` 는 "⚠️ 재시도 없음 — role='matchup' 이면 1회만 부른다"고
  못박았는데, `judge_matchup` 은 `for attempt in (1, 2):` 로 **바깥에서 두 번**
  부른다. `claim_final` 락은 *호출 진입*을 막을 뿐 한 진입 안의 2회 호출은 못 막는다.
- **M-2 [중] 재시도 상향이 불변식을 깬다.**
  `budget = min(12000*2, MAX_TOKENS_CEILING=16000)` → 16000.
  `deepsearch_max_tokens` 도 16000 이라 "딥서치 > 매치업" 불변식이 같아진다.
- **M-3 [중] 자료1 결측 판정이 한쪽만 있어도 "있음"이 된다.**
  `boxscore_payload` 는 자료가 없는 side 를 통째로 생략한다.
  `confidence.material_gaps` 는 `if not boxscore_payload(jg)` 만 보므로
  **한쪽 팀 박스스코어만 있어도 결측으로 세지 않는다.**
  (`judge_matchup` 자신은 `home`·`away` 둘 다 확인한다 — 두 곳의 기준이 다르다.)
- **M-4 [중] 유료 심의·상황 비용이 `claim_final` 실패 시 버려진다.**
  순서가 `situation` → `council`(LLM 호출) → `claim_final` 이라,
  다른 호출이 최종 권한을 먼저 가져가면 이미 태운 심의 호출이 헛돈다.
- **M-5 [중] `apply_matchup` 이 근거 배열을 공백으로 이어 붙여 `jg["verdict"]` 로 만든다.**
  오늘 실측에서 본 "근거 3개가 뭉개진 카드"의 원인. `verdict_block` 은 고쳤지만
  `render_game_section`(4757행)은 여전히 이 뭉갠 문자열을 쓴다.
- **M-6 [중] 자료2 JSON 스키마가 섞인다.** `news_payload` 는 `{"home":[…],
  "away":[…]}` 인데 `council.payload` 결과를 `out.update()` 로 **같은 층에** 붙인다
  (실측 프롬프트: `"상황·심의": {...}` 가 home/away 배열과 나란히 있다).
- **M-7 [하] `clip_p_home` 이 종목과 무관하게 야구 상수(0.32~0.68)를 쓴다.**
  축구 상수(0.10~0.72)는 이 함수를 안 탄다 — 이름이 그것을 말하지 않는다.

## app/engine/pregame_push.py
- **PP-1 [중] 발송 카드가 `split_message` 를 안 쓰고 `[:4096]` 으로 자른다.**
  `bot/main.py` 만 분할한다. 실측 결과 현재 카드는 1,180~1,728자로 한계의
  절반 이하라 **지금은 절단 0건** — 구조적 위험이지 현행 결함은 아니다.
- **PP-2 [중] `card_cap`·`card_reserved` 가 미발송(misses)으로 집계된다.**
  둘 다 정상 동작인데 발송률 분모에서 실패로 잡혀 100% 가 구조적으로 불가능하다.
- **PP-3 [하] `pregame_push` 가 `app.pipeline` 을 모듈 최상단에서 import** 한다.
  발송 모듈이 판정 파이프라인 전체(anthropic·asyncpg·수집기)를 끌어온다.
- **PP-4 [하] `lineup_confirmed` 정의가 import 문 위에 있다**(30~50행 vs 52행~).

## app/engine/markets.py
- **MK-1 [중·잠재] `_enforce_data_rules` 의 종목 가드가 재판정 3경로에 없다.**
  `build_analysis`(2184행)에만 `if sport not in _BB` 가드가 있고,
  `_refresh_stale_research`(5406) · `rejudge_after_lineup`(5654) ·
  `ensure_game_fresh`(5753) 는 **가드 없이** 부른다.
  그 기준(`has_season_data`)은 시즌 승률·시즌 ERA·순위표 — 야구에서 폐지된
  자료7·8 계열이다. 통과 못 하면 확신도가 '하'로 강등돼 거부권탈락이 된다.
  ⚠️ 실측: MLB 15/15 통과(`season_edge=True`) — **현재 발동 0건.**
     KBO·NPB 는 오늘 캐시가 없어 미측정.

## app/watchdog.py
- **W-1 [중] `W-SOURCE-DRIFT` 가 경보 사전에 없다.**
  `watchdog.py` 는 이 코드를 내는데 `alerts.WATCHDOG_CODES` 에 항목이 없어
  라벨이 **"점검 필요"** 로 뭉개진다. (다른 코드는 전부 대응됨을 확인)
- **W-2 [상] `W-LLM-FAIL` 은 판정 실패를 세지 않는다.**
  `note_llm_failure` 를 부르는 곳은 `llm/provider.py` 뿐이고, 그것이 맡는
  역할은 narrator·interpreter·intent·judge_a 다. **매치업 판정(judge_route·
  team_form.complete_json)의 실패는 이 카운터에 안 잡힌다.**
  → 오늘 Anthropic 소진으로 최종 판정이 전건 실패했을 때 이 경보는 안 울렸다.
- **W-3 [중] 경보 발송이 실패해도 `check_stale_games` 는 기준선을 갱신한다.**
  조회와 저장이 같은 자리(533~534행)라, 알림이 실패하면 그 유령 경기는
  `prev` 에 들어가 **다시는 보고되지 않는다.**
- **W-4 [하] 무료 배당 소스는 차단 검사를 안 한다.**
  `check_odds` 는 `odds_provider == "theodds"` 일 때만 `W-ODDS-BLOCKED` 를 본다.

## 죽은 코드 (전 저장소 정적 검사)
- **X-1 [상] 확률 상한 경보가 통째로 안 돈다.**
  `scoring.record_cap_hit()` · `cap_alert_count()` — **호출부 0건**.
  `config.prob_cap_alert_n=3`("하루 3건 넘으면 모델 점검 필요")이 이 함수
  안에서만 쓰인다. MODEL.md 가 "이 값을 넘는 산출은 모델이 틀렸다는 신호"라고
  규정한 안전장치가 **한 번도 작동한 적이 없다.**
- **X-2 [중] `alerts.dispatch_report()` — 호출부 0건** (P-1 과 동일).
- **X-3 [하] `collectors/news_rss.fetch_team_situation()` — 호출부 0건.**
- **X-4 [하] `collectors/starter_season.py:338 if True:`** — 죽은 조건절.

## 정적 검사에서 **깨끗한** 항목 (174파일)
bare except 0 · 가변 기본 인자 0 · dict 중복 키 0 · 운영 assert 0 ·
함수/클래스 재정의 0 · `== None` 비교 0.

## app/scheduler.py (2,055줄 완독)

- **S-1 [상] 크롤러 스냅샷이 없으면 T-30 첫 카드 보장이 통째로 건너뛰어진다.**
  `crawler_lineup_poll` 은 `snap = load_snapshot(...); if not snap: continue` 인데,
  `guarantee_first_cards` 호출이 **그 continue 뒤 같은 루프 안**에 있다.
  크롤러가 죽으면 KBO·NPB 는 카드도 보장도 없다.
  (MLB 경로 `mlb_pregame_poll` 은 무조건 호출해서 이 문제가 없다 — 비대칭)
- **S-2 [상] `heartbeat_2m` 은 감시 대상인데 실행 기록을 남기지 않는다.**
  `_instrument` 래퍼를 안 거치는 유일한 잡이라 `record_job_run` 이 안 불린다.
  워치독 `check_jobs` 는 `if not row: continue` 로 **영원히 건너뛴다.**
  실측: 감시 대상 7개 중 `heartbeat_2m` 만 기록 없음.
- **S-3 [상] 중요한 잡 20개가 감시 밖이다.**
  `prefetch_asia`(그날 KBO·NPB 캐시를 만드는 잡) · `ingest_finals_13h`(채점) ·
  `daily_summary_*` · `watchdog_5m` 자신 등이 `WATCHED_JOBS` 에 없다.
  실행 기록에는 남지만 `W-JOB-LATE` 가 안 울린다.
- **S-4 [중] 1회성 코드가 상시 실행된다.**
  · `startup_backfill_job` 안의 `[ledger-snapshot]`·`[appearances]` 블록 —
    주석: "확인이 끝나면 다음 배포에서 이 블록도 함께 지운다"
  · `BACKFILL_SINCE="2026-08-29"` 백필 — "다음 배포에서 통째로 지워도 된다"
  · **`soccer_lineup_probe_job`** — `SOCCER_PROBE_ENABLED=True`,
    `main()` 이 매 기동마다 `probe_run(hours=30, interval=600)` 태스크를 띄운다.
    주석: "관측이 끝나 로그를 회수한 뒤에는 통째로 지운다".
    오늘 4번 배포 = **30시간짜리 fotmob 프로브가 4개** 동시 실행 중.
- **S-5 [중] Redis 장애 시 NPB 관망 카드가 2분마다 폭주한다.**
  `_npb_pending_notice` 는 중복 가드 실패를 `except` 로 잡고 **`continue` 하지
  않은 채** 발송으로 내려간다.

## app/llm/*

- **L-1 [상] 유료 최종 판정에 seed·temperature 가 없다.**
  `LLM_SEED=20260905` 는 `_complete_free`(무료)에만 전달되고,
  Anthropic 경로 `message_kwargs` 는 model/max_tokens/messages 뿐이다.
  게다가 `_NO_SAMPLING` 에 `claude-opus-5` 가 있어 `temperature=0` 도 안 나간다.
  실측: `message_kwargs('claude-opus-5', …)` 키 = `['max_tokens','messages','model']`.
  → 판정 안정성 작업(JUDGE_STABILITY·LLM_SEED)이 **최종 판정에만 빠져 있다.**
- **L-2 [상] `W-LLM-PAID` 가 경보 사전에 없다** (W-SOURCE-DRIFT 와 같은 결함).
  `judge_route.note_paid_call` 이 이 코드를 내는데 라벨이 "점검 필요"로 뭉개진다.
- **L-3 [중] `judge_route` 모듈 독스트링이 옛 동작을 설명한다.**
  "폴백 사슬: 무료 주전 → 무료 후보 → (둘 다 죽으면) Anthropic" 인데,
  본문은 "유료 폴백을 삭제했다 — 무료 후보가 없으면 빈 목록".
- **L-4 [중] 배포마다 최종 판정 1건이 Anthropic 400 으로 태워진다.**
  소진 플래그 `_EXHAUSTED` 가 프로세스 내 dict 라(의도된 설계 — 충전 시 재기동으로
  복구) 재기동 직후 `_anthropic_gone()=False` → 첫 최종이 anthropic 으로 가서
  실패 → 그때 플래그가 서고 다음 폴링부터 grok. 카드 손실은 아니고 5분 지연.
- **L-5 [중] `openai_compat.complete()` 가 `api_guard` 가드를 안 부른다.**
  `disabled_providers` 에 있어도 호출된다. `xai` 이름 불일치(C-3)와 겹친다.

## app/engine/scoring.py (776줄 완독)

- **SC-1 [상] λ 엔진 전체가 야구 운영 경로에서 도달 불가.**
  `_compute_picks` 의 야구 분기가 `continue`(offset 3779) 하는데
  `game_distribution` 호출은 offset 15058 — **실행으로 확인**했다.
  따라서 `mlb_lambdas`·`mlb_market_probs`·**`cap_probability`** 가 야구에서 안 돈다.
  → X-1(확률 상한 경보 미작동)의 기계적 원인이 이것이다.
  야구 절사는 `matchup.clip_p_home` 이 따로 한다(같은 상수, 다른 코드 = 사본).
  운영 호출부는 `pipeline.py:3704`(축구) 하나뿐이고 나머지는 `models/`·`tools/`
  백테스트다. **776줄 + `models/lambda_model.py` + `models/calibrate.py` 가
  야구 기준 휴면 상태다.**
- **SC-2 [하] `_weather_factor` 는 기온이 정확히 20도면 `None` 을 돌려준다**
  → 정상인데 "날씨" 결측으로 기록된다.

## app/engine/card.py
- **CD-1 [중] `예상점수_생략` 사유가 카드에 안 나온다.**
  `check_flow` 가 어긋난 점수를 지우고 `전개.예상점수_생략` 에 사유를 남기는데
  `verdict_block` 은 그 칸을 읽지 않는다 — 사용자는 왜 예상 점수가 없는지 모른다.

## 전 저장소 스캔 (174파일)
- TODO/FIXME **2건**(실질 1건: `models/features.py:46` 구장 시간대 테이블).
- 코드에 박힌 시각 비교 3건(`pregame_checklist.py:142` 외 도구 2건).
- `except` 가 로그 없이 삼키는 자리 186건 — 대부분 파서 가드라 결함이 아니다.
  **판단 근거를 남겨야 하는 자리만 별도로 봐야 한다**(전수 판정은 아직 안 했다).

## 수집기 · 크롤러

- **LN-1 [상] "확정은 타순 9명"이 최소 10곳에 흩어져 있다.**
  CLAUDE.md v1.3 A-1 은 "확정 규칙은 **한 곳**에만 있다 — `lineup_confirmed`"
  라고 선언했는데, 숫자 9 가 박힌 자리:
    `pregame_push.LINEUP_FULL`(원본) · `pipeline.py:646`·`:823` ·
    `collectors/lineups.py:153`(`parse_boxscore.confirmed`)·`:182`·`:341` ·
    `naver_kbo.py:334` · `kbo_boxscore.py:89` · `yahoo_npb.py:653` ·
    `matchup.py`(`_slots>=9`) · `confidence.py`(`slots<9`)
  이 중 `parse_boxscore.confirmed` 는 **두 번째 확정 판정**이다 —
  MLB 라인업 상태를 그것이 정한다.
- **LN-2 [상] `refresh_mlb_lineup` 의 games UPDATE 에 확정 보호가 없다.**
  `UPDATE games SET lineup_status = $2 … WHERE id = $1` — 무조건 덮는다.
  `pipeline.sync_lineup_status` 는 `AND lineup_status <> 'confirmed'` 가드가
  있는데 여기는 없어 **confirmed → predicted 역행**이 가능하다.
  역행 감지(`note_lineup_regress`)는 KBO·NPB 폴링에만 있고 MLB 엔 없다.
- **LN-3 [중] MLB 라인업 이력이 `source="crawler"` 로 기록된다**(`lineups.py:277`).
  MLB 는 statsapi 이고 Go 크롤러 대상이 아니다(`registry` 가 그렇게 적어 뒀다).
  `lineup_history.SOURCE_KR["crawler"]="발표 라인업"` — **원장이 거짓 소스를 적는다.**
- **LN-4 [중] `save_lineup` 의 유니크 키가 `(game_id, side, source, status)`** 라
  predicted 행과 confirmed 행이 둘 다 남는다. 읽는 쪽이 status 를 안 거르면
  옛 predicted 를 집는다.
- **NR-1 [중] 방금 발행된 기사가 정렬에서 맨 뒤로 밀린다.**
  `parse_feed` 의 `round(age,1) if age else None` — `age=0.0` 이 falsy 라
  `age_h=None` 이 되고, `for_game` 정렬 키가 `(age_h is None, …)` 라 **최신
  기사가 12건 상한에서 잘려나간다.** (실행으로 확인)
- **NR-2 [중] 모듈 독스트링의 전제가 깨져 있다.**
  `news_rss` 10~11행: "본문은 `web_fetch`(무료)가 따로 가져온다. **제목만으로
  판정을 흔들지 않는다**". 실측: 본문이 전부 `"Google News"` 다(오늘 조사).
- **CR-1 [상] 워치독이 크롤러 생존을 안 본다.**
  `crawler_feed.is_alive` 는 `/health`(사람이 열어야 봄)와 `pregame_checklist`
  (수동 도구)에서만 쓰인다. 워치독 9개 점검에 크롤러가 없다.
  **S-1 과 겹치면**: 크롤러가 죽으면 KBO·NPB 폴링이 `continue` 로 빠지고
  T-30 보장도 안 돌아 카드가 0장이 되는데, **원인을 가리키는 경보가 없다**
  (증상은 `W-CARD-LATE` 가 잡는다).
- **CR-2 [중] 하트비트 TTL 이 정지 판정 문턱보다 짧다.**
  Go `store.go:79` 가 `crawl:heartbeat` 를 **2시간** TTL 로 쓰는데
  `crawler_feed.STALE_MINUTES = 180`(3시간)이다. 121~180분 구간에서 키가 이미
  사라져 "N분째 멈춤" 분기는 **도달 불가**다.
  ⚠️ 그 상수 주석도 "평시 60분 × 3"이라고 적혀 있는데 실제 배포는
     `crawler -interval 10m` 이다(`tools/deploy.sh:105`).

## 커버리지 (이번 검토에서 실제로 읽은 것)
완독: config · db · api_guard · notify · alerts · registry · **pipeline 6,141**
 · matchup · pregame_push · dispatch_stats · confidence · team_form · scoring
 · watchdog · **scheduler 2,055** · llm 전부(judge_route·openai_compat·gemini
 · ledger · provider) · credit_guard · news_rss · crawler_feed · lineups
 · card(판정 블록) · markets(전반)
기계 검사: app+tools **174파일 전수** (AST 기반 8종 + 죽은 함수 + 중복 상수)
미독: bot/main.py(901) · engine 나머지 약 11,000 · collectors 나머지 약 9,000
 · tools(6,526) · research(1,700) · models(1,470) · Go 크롤러(1,205) · 훅(9개)

---

# 2차 정독 (남은 소스) — 2026-09-07

## app/bot/main.py · aliases.py

**B-1 [상·실측] KBO·NPB 는 사용자가 물어볼 방법이 없다.**
 - 명령은 `/mlb /soccer /today /health /checklist /픽` 뿐 (`main.py:584~662`).
   `/kbo` `/npb` 가 없다.
 - `TEAM_ALIASES`(`aliases.py:3~95`)에 **KBO 10팀·NPB 12팀이 한 줄도 없다.**
   MLB 30 + 축구만 있다. `KR_TEAM_NAMES` 에는 22팀이 다 있는데 **질의 사전에만
   없다** — 표기 사전과 질의 사전이 갈렸다.
 - 그래서 "한화 오늘 어때?" → `find_team` 미스 → `route_query`→"full"
   → `parse_intent_mock`(`main.py:257`)이 축구 키워드가 없으면 **무조건 mlb**
   → **KBO 질문에 MLB 전체 카드가 나간다.**

**B-2 [상] 자동 발송 카드에는 인라인 버튼이 없다.**
 `reply_markup` 을 붙이는 곳은 `_send_card`·`_league_flow` 둘뿐이고 둘 다
 사용자가 `/mlb`·`/soccer` 를 쳤을 때만 탄다. 스케줄러가 보내는 KBO·NPB·MLB
 자동 카드는 `📊 경기별 심층 / 📰 부상·속보 / 📎 출처 / 🎯 추천픽` 이 없다.

**B-3 [중] `game:` 콜백이 mlb·soccer 만 뒤진다** (`main.py:715`).
 `for sport in ("mlb","soccer")` — kbo·npb 캐시를 안 본다. B-2 때문에 지금은
 도달 경로가 없지만, 버튼을 붙이는 순간 KBO 는 전부 "만료"가 된다.

**B-4 [중] `sport2` 판정식이 항상 참인 조건을 달고 있다** (`main.py:732`).
 `any(x["game_id"]==g["game_id"] for x in analysis["games"])` — `g` 는 그
 목록에서 꺼낸 것이라 항상 True. 실질은 `analysis.get("sport")` 하나다.

**B-5 [중] `perf` 섹션은 도달 불가** — `sec:*:perf` 를 만드는 키보드가 없다
 (`main.py:706`). 그 안의 `render_performance` 는 고정 문자열만 돌려준다.

**B-6 [중] `_polling_watchdog` 은 이름과 다른 것을 잰다** (`main.py:793`).
 `getUpdates` 정체가 아니라 `bot.get_me()` 성공으로 `poll_tick()` 을 갱신한다.
 → **폴링만 죽고 API 는 살아 있는 경우(바로 그 잡으려던 상황)를 절대 못 잡는다.**
 실제로 잡는 것은 "봇 API 자체가 6회 연속 실패"다.

**B-7 [하] `intent_system()`·`INTENT_SYSTEM` 은 죽은 코드**인데
 `tests/test_pipeline_bot.py:822` 가 그것을 지키고 있다. 테스트는 통과하지만
 운영 경로는 `parse_intent_mock` 고정(`main.py:264~`)이라 아무것도 검증하지 않는다.

**B-8 [하] `two_layer_html`(`main.py:100`)의 `detail[:-cut]`** 은 `cut` 이
 `len(detail)` 을 넘으면 빈 문자열이 된다. 그때는 `send_two_layer` 의
 `[:4096]` 절단 → HTML 태그 중간 절단 → 400 → 플레인 폴백으로 살아난다.

## app/config.py

**C-1 [중] `intent_model` 이 같은 `Settings` 클래스에 두 번 선언돼 있다.**
 `config.py:51` `= "claude-haiku-4-5"` · `config.py:454` `= ""`.
 파이썬 클래스 본문이라 **뒤가 이긴다** — 실효값은 `""`. 51행을 읽은 사람은
 틀린 값을 믿는다. (전수 검사 결과 중복 필드는 이 하나뿐이다.)

## app/engine/deepsearch.py

**D-1 [중] `triggers()` 에 T6 가 없다** (`deepsearch.py:61~93`).
 T6(라인업 최초확정)는 재판정 경로(`run_for_rejudge`)에서만 걸린다.
**D-2 [중] 조사 실패는 상한을 먹지 않는다** — `data is None` 이면 `investigated`
 도 `_incr` 도 없다(`deepsearch.py:768`). 실패가 반복되면 슬레이트 전체를 계속 시도한다.
**D-3 [하] 유료 잔재가 남아 있다** — `SRC_PAID`·`PAID_KEY`·`_paid_budget_left`·
 `_spend_paid` 는 유료 경로 삭제 후 호출자가 없다.
**D-4 [중] T2 트리거가 시장이다** (`market_divergence`). 딥서치는 `p_claude` 를
 ±4%p 움직이므로, **배당이 트리거를 통해 판정 숫자에 간접 관여**한다.
 프롬프트는 배당 조사를 금지하지만 트리거 자체는 못 막는다.

운영 실측: `DEEPSEARCH_ENABLED=true` · `DEEPSEARCH_SPORTS=mlb,soccer`
(→ Perplexity 여론 축은 KBO·NPB 미수집. 트리거형 조사는 전 종목 동작.)

## app/engine/fact_audit.py

**F-1 [상] `verified` 는 진영을 안 가린다** (`fact_audit.py:466~470`).
 `pool = numbers_in_prompt(전체 프롬프트, unit)` 에 값이 하나라도 있으면 곧장
 `verified`. 홈 값을 원정 것으로 잘못 인용해도 통과한다. 주체 귀속(`subject`)은
 그 다음 단계(재계산)에서만 쓰인다.
**F-2 [중] `era_recomputed` 가 `UNIT_PATTERNS` 를 인덱스 0·1·2 로 참조한다**
 (`fact_audit.py:440~442`). 지금은 이닝·실점·자책이 맞지만, 패턴을 앞에 하나
 끼워 넣는 순간 **조용히 다른 단위를 ERA 재료로 쓴다.**
**F-3 [하] elo 패턴 `\b(1\d{3})\b` 은 프롬프트 전체에서 1000~1999 를 전부
 elo 풀로 담는다** — 감시를 느슨하게 하는 방향(오탐은 아님).

## app/engine/soccer_trial.py  (운영에서 꺼져 있음: `soccer_trial_enabled=False`)

**S-1 [상·잠재] `judge()` 가 Anthropic 을 직접 부른다** (`soccer_trial.py:337~365`).
 `judge_route.chain`·`paid_allowed`·`note_paid_call` 어느 것도 안 탄다 →
 **`ANTHROPIC_DAILY_CAP` 밖에서 하루 최대 12콜.** 봇의 유료 의도파싱을 없앤
 것과 같은 종류의 누수가 여기 남아 있다.
**S-2 [중] 일일 카운터가 판정 성공 뒤에만 오른다** (`run_once` 말미) — 실패한
 유료 호출은 상한을 안 먹는다.
**S-3 [중] `_last5` 가 `"%m/%d"` **문자열**로 정렬한다 (`soccer_trial.py:216`).
 유럽 리그는 8월~5월 시즌이라 **해가 바뀌는 순간 최근 5경기가 8~12월 경기로
 채워진다.** 지금이 9월이라 아직 안 드러났다.

## app/engine/variable_ref.py  ← 🔴 실측 결함

**V-1 [상·실측] 자료10 의 상대 선발 시즌 ERA 가 키 이름이 어긋나 항상 null.**
```
slim_season / slim_asia 가 쓰는 키 :  "ERA"          (starter_season.py:67, 258)
variable_ref 가 읽는 키           :  .get("era")    (variable_ref.py:305)
```
운영 실측(2026-09-07, railway ssh):
```
fetch_mlb(["Zack Wheeler"]) → {"선발":24,"이닝":"136.1","ERA":"3.23", …}
   .get("era") → None        .get("ERA") → 3.23
판정 프롬프트 26건 중 opp_starter_season_era 가 실값 :  0건
판정 프롬프트 26건 중 키가 null 로 실려 있는 것      : 26건
DB 조회 자체는 된다 — 상대 선발 이름 조회 18건 중 16건 적중
```
→ 2026-09-07 에 붙인 자료10 1-c 는 **경기당 6회 DB 를 때리고 결과는 전부 null.**
 `form_gap`(`variable_ref.py:129`)도 같은 소문자 `era` 를 읽어 **`부진후회귀`
 분기가 영영 발동하지 않는다.**

⚠️ **고치기 전에 결정이 필요하다.** 이 오타가 지금 유일하게 막고 있는 것이
   "시즌 ERA 가 판정 프롬프트에 들어가는 것"이다 → V-2.

**V-2 [상] 문서와 코드가 어긋난다 — 자료1이 시즌 집계를 이미 싣고 있다.**
 `app/engine/CLAUDE.md` 대원칙: "시즌 누적 통계(타율·ERA·**승패** 등 집계표)는
 판정 입력 금지. 예외는 둘뿐 — 2단 연구 prior, 자료12."
 실측(프롬프트 26건):
```
opponent_win_pct (상대 시즌 승률) 포함 : 26/26
opponent_rank    (상대 시즌 순위) 포함 : 26/26
```
 그리고 `prompts.py:145` 는 판정에게 **그 값을 쓰라고 지시한다.**
 `tests/test_season_ban.py` 는 `*_starter_season`·`*_lineup_season` 키만
 잠그므로 이 경로를 못 본다. 셋 중 하나여야 한다 — 예외를 문서에 명시하거나,
 프롬프트에서 빼거나, 계약 테스트를 이 경로까지 넓히거나.

## app/engine/interpreter.py

**I-1 [중] 방향 검증 기준선이 조용히 꺼진다.** `scoring_baselines` 는
 `len(v) >= 4` 인 지표만 사분위를 만든다(`interpreter.py:390`). 3경기 슬레이트면
 방향 오독 검증이 통째로 없는데 **로그 한 줄도 없다.**
**I-2 [하] `interpret_slate` 는 경기×진영을 전부 순차로 돈다** — 15경기 MLB면
 LLM 30콜이 직렬. 정확성 문제는 아니나 T-차감에 그대로 들어간다.

## 감시·계측 (실측 2026-09-07 22:21 KST · railway ssh)

**W-1 [상·실측] `[materials]` 조립 도장에 자료12·자료14 가 없다** (`matchup.py:803`).
```
_mat_msg = "[materials] game=%s 자료3=%s(타순 %d명) 자료9=%s 자료10=%s 자료11=%s"
```
 → 어제 문서 `docs/ACCURACY_2026-09-07.md` §6 "내일 볼 것 ①: `[materials]` 에
 자료12 가 실리는가"는 **구조적으로 관측 불가능하다.** `game_trace`·일일 요약·
 투명 리포트 어디에도 자료12·14 의 유무가 남지 않는다.

**W-2 [중] 투명 리포트 ①절의 `MATERIALS` 목록이 자료11 에서 끝난다**
 (`glass_report.py:86~97`). 자료12(실력 레이팅)·자료14(분기점)가 없다.
 `stamped = {3,9,10,11}` 도 같은 하드코딩 사본이다.

**W-3 [상·실측] 감시 L2(검사역)·L3(독립 판정)는 태어난 이후 한 건도 기록된 적이 없다.**
```
judgement_audit  n=1111  2026-09-03 05:03 ~ 2026-09-07 12:36   (L1 정상)
judge_review     n=   0
shadow_panel     n=   0
```
 `fe26660`(2026-09-07 17:44 KST, 배포본 `7c0f9be` 에 포함)이 `pick_targets`
 의 등급 조회를 고쳤고 지금은 등급이 제대로 계산된다. 그런데 **대상이 여전히 0**이다:
```
analysis:mlb:2026-09-07 → 경기 11 · 패널 대상 0 · 등급 {보드만 9, 거부권탈락 2}
gemini is_available() = True
```
 원인은 파싱이 아니라 **선정 조건**이다 — `pick_targets` 는 `엣지·추천`만 본다.
 추천이 나오는 날이 드물어 (오늘 0/11) 감시 두 층이 사실상 상시 휴면이다.
 "고쳤다"와 "돈다"는 다르다.

**W-4 [중] `daily_summary.build` 가 같은 경기를 두 번 셀 수 있다.**
 `WHERE l.is_final AND …` 뿐이고 경기당 1행으로 접지 않는다.
 실측: **`is_final` 행이 2개 이상인 경기 10 / 전체 149.**

**W-5 [중] 요약이 삭제된 경로를 매일 보고한다.** `cost_lines` 가
 `deepsearch.PAID_KEY` 를 읽어 `web_search 0/3콜` 을 찍는데, 유료 web_search
 경로는 2026-09-06 에 삭제됐다(`deepsearch.py:530` 주석). 항상 0 이다.

**W-6 [하] 표시 문자열이 옛 버전에 굳어 있다** — `freeze_progress_lines` 가
 `"🔒 v1.3 동결 진행률"` 을 찍는다(현재 v1.4). `FREEZE_START = {}` 는 빈 dict
 인데 위 주석 12줄이 "MLB 만 근거가 다르다"를 설명한다 — 코드가 주석을 떠났다.

**W-7 [중] `market_baseline_ledger` 적재가 09-06 23:10 에 멈췄다.**
 같은 기간 `judgement_audit` 는 09-07 12:36 까지 쌓였다 — 판정은 계속됐는데
 시장 기준선만 안 쌓인다. (66행 · 09-04 08:20 ~ 09-06 23:10)

**W-8 [하] 오탐 아님(확인함)**: `analysis:kbo:2026-09-07`·`npb` 가 `games=0` 인 것은
 결함이 아니다 — DB 상 그날 KBO·NPB 경기가 실제로 0경기다(09-08 부터 재개).

## app/engine/glass_report.py

**G-1 [중] `build()` 의 재료 결측 판정이 자료1·4 만 본다** (`glass_report.py:405`).
 자료3(타순)·9(불펜)·12(레이팅)가 통째로 비어도 `cause_class` 는
 "(a) 재료 부족" 을 안 붙이고 "(c) 판단 오류"로 넘긴다.

## 🔴 최상위 — v1.1 4단계(엣지)가 통째로 배선되지 않았다

**E-1 [최상·실측] `app/engine/market_edge.py` 는 아무도 부르지 않는다.**
```
$ grep -rn "market_edge" app/ tools/
app/engine/deepsearch.py:352   ← 주석 안의 언급뿐
(호출·import 0건. 유일한 import 는 tests/test_market_edge.py)
```
이 모듈이 채우기로 되어 있는 `jg["edge_status"]`·`jg["market_divergence"]` 는
**영원히 None** 이다. 실측(운영 DB):
```
pick_ledger.edge_status : NULL 159 / 159 (is_final 전건)
gate_result = '엣지'     : 0건
```
연쇄로 죽는 것들 —
 · `pick_ledger.gate_result_of` → `GATE_EDGE` 도달 불가
 · 딥서치 T2 트리거 `edge_status == "candidate" or market_divergence` → 영구 미발동
 · `daily_summary` 의 `🎯 엣지 N건` 줄 → 영구 0
 · `calibration._edge_buckets`(「우리가 시장을 이기는 영역」) → 영구 표본 0
 · `glass_report` ④절 `엣지 —`

**E-2 [최상] 배선하더라도 `GATE_EDGE` 는 여전히 나올 수 없다.**
```
value_gate.classify:  if edge_status == "confirmed":  return CLS_EDGE
market_edge.apply  :  edge_status = EDGE_CANDIDATE    ("candidate")
candidate → confirmed 로 올리는 코드는 코드베이스에 없다 (grep 전수).
```
`EDGE_CONFIRMED` 상수는 정의만 되어 있고 대입하는 곳이 0곳이다.

⚠️ 이것은 이 저장소가 스스로 적어둔 상품 정의와 정면으로 어긋난다 —
   `market_edge.py:931`: *"이 시스템의 상품은 '이길 팀 찾기'가 아니라
   **'시장이 저평가한 팀 찾기'** 다. 수익의 원천은 적중률이 아니라 시장과의
   정보 격차다."*

**E-3 [중] 테스트가 죽은 모듈을 지키고 있다.** `tests/test_market_edge.py`
 는 통과하지만, 검사하는 것은 **호출되지 않는 함수의 순수 계산**과
 "판정 모듈이 market_edge 를 import 하지 않는가"(격리)뿐이다. 격리는 지켜지는데
 배선이 없다는 사실은 어느 테스트도 묻지 않는다. 같은 모양이 `app/bot/main.py`
 의 `intent_system()` 에도 있다(B-7).

## app/engine/market_edge.py · linemove.py (배선됐을 때의 성질)

**E-4 [중] 확신도 강등이 원장에 남지 않는다.**
 게이트가 읽는 값은 `jg["judge_confidence"]`(영문 high/medium/low)이고,
 원장 `pick_ledger.confidence` 에 적히는 값은 `matchup["확신도"]`(한국어 상/중/하,
 **강등 전 자기신고**)다. `market_edge.apply`(시장 우위 시 1단계 강등)와
 `linemove.attach_line_move`(축구, ±1단계)가 그 사이에서 값을 바꾸는데
 **바뀐 사실이 어디에도 기록되지 않는다.**
 실측: 거부권탈락 24건은 전부 원장 확신도 '하' — 지금은 강등이 게이트를 뒤집은
 사례가 0건이다(E-1 때문에 강등 자체가 안 돈다). 배선하는 순간 추적 불가가 된다.

**E-5 [하] `linemove` 는 축구 전용이다** — `pipeline._apply_line_moves` 가
 야구를 `continue` 로 건너뛴다(`pipeline.py:2191`). 그리고 실전 축구 경로
 (`soccer_trial`)는 이 함수를 타지 않는다. 사실상 휴면.

**E-6 [실측] 게이트 등급 × 원장 확신도 (is_final 전건)**
```
추천      확신도 중  15 · 확신도 상   2
보드만    확신도 중 113
가치주의  확신도 중   5
거부권탈락 확신도 하  24
```
 확신도 '상' 이 전 기간 **2건**뿐이다. 확신도 축이 사실상 2값(중/하)으로 붕괴해
 있다 — 어제 진단(`docs/ACCURACY_2026-09-07.md` §5)의 표본 문제가 여기서 나온다.

## 🔴 최상위 — 자료9 가 "최근 폼만"이라 적어놓고 시즌 지표를 싣는다

**P-1 [최상·실측] 호출 순서가 뒤집혀 있어 대원칙이 매 프롬프트에서 깨진다.**

```
app/pipeline.py:2749  # ⚠️ 시즌 부착(위 `mlb_team_pitching` 등)보다 **뒤**여야 지워진다.
app/pipeline.py:2751  await _bp_recent(pool, jg)     ← 시즌 키를 pop 하는 쪽
app/pipeline.py:2765  await attach_opp_starter_era(...)
app/pipeline.py:2772  await _pen(jg, redis=redis)    ← 시즌 키를 채우는 쪽  🔴 더 뒤에 있다
```
`bullpen_recent.attach` 는 `for stale in ("era","whip","k9","bb9"): dst.pop(stale)`
로 시즌 값을 지우도록 만들어졌는데, **지운 다음에** `mlb_team_pitching.attach`
가 다시 채운다. 주석은 정확히 반대로 적혀 있다.

운영 실측(2026-09-07, railway ssh):
```
research.*_bullpen 안의 키 : {최근3경기 22, 가용성 22, era 22, whip 22, k9 22, bb9 22, …}
판정 프롬프트 자료9 블록에 era/whip/k9/bb9 포함 : 26 / 26
```
실제 프롬프트 원문:
```
9. 양팀 불펜 — **최근 폼만** (없으면 빈 객체): {"home": {"최근3경기": {...},
   "가용성": {...}, "era": 3.98, "whip": 1.28, "k9": 9.94, "bb9": 3.06}, …
```
→ `app/engine/CLAUDE.md` 대원칙("시즌 누적 통계는 판정 입력 금지, 예외는
   2단 연구 prior 와 자료12 뿐")이 **전 슬레이트에서 깨져 있다.**
   `tests/test_season_ban.py` 는 `*_starter_season`·`*_lineup_season` 키만
   잠그므로 이 경로를 보지 못한다.

⚠️ 고치는 방법은 두 줄 순서를 바꾸는 것이지만, **v1.4 동결 대상(자료 구성)**
   이므로 지시 없이 손대지 않는다. 그리고 이 값을 빼면 MLB 자료9 는 원래대로
   `최근3경기`+`가용성` 만 남는다 — `mlb_team_pitching.py`(112줄)의 존재 이유가
   사라지므로 그 모듈을 어떻게 할지도 함께 결정해야 한다.

## app/collectors — 그 밖

**P-2 [중] `last3.attach_opponent_context` 는 상대의 *현재* 순위·승률을 과거
 경기 행에 붙인다.** 8/30 경기의 `opponent_rank` 는 8/30 시점 순위가 아니라
 **오늘 순위**다. 판정은 그것을 그 경기의 맥락으로 읽는다(프롬프트 자료1 설명).
 시점이 어긋난 값이고, `opponent_win_pct` 는 시즌 승률이라 V-2 와 같은 건이다.

**P-3 [중] `game_match.merge_duplicate_games` 의 그룹 기준과 매칭 기준이 다르다.**
 병합 그룹은 `date_trunc('day', starts_at AT TIME ZONE 'UTC')`, 결과 매칭
 (`_FIND`)은 ±20시간 창이다. MLB 야간 경기처럼 UTC 일자가 갈리는 중복은
 `_FIND` 로는 같은 경기인데 병합에서는 다른 그룹이 된다.

**P-4 [중] `merge_duplicate_games` 의 `keep` 은 `predictions` 로 고른다** —
 판정 기록은 `pick_ledger` 에 있다. 두 표가 서로 다른 행에 붙어 있으면
 판정이 없는 쪽을 남긴다(이후 이관하므로 손실은 없지만 기준이 갈려 있다).

**P-5 [하] `sharp_odds.parse` 는 실응답으로 검증된 적이 없다**(모듈이 그렇게
 적고 있다). 키가 들어오면 구조 불일치로 **조용히 0건**이 된다.

## 🔴 날씨가 경기 시각이 아니라 UTC 정오 값을 쓴다

**W-X [상·실측] `weather.pick_hour` 의 시각 매칭이 항상 실패하고, 폴백이
 "가장 가까운 시각"이 아니라 "배열 한가운데"다.**

```python
# collectors/weather.py:1112
starts = str(g.get("starts_at") or "")
day, hour_utc = (starts[:10], starts[:13]) ...
# pick_hour
for i, t in enumerate(times):
    if str(t).startswith(hour_utc): idx = i; break
if idx is None:
    idx = min(range(len(times)), key=lambda i: abs(i - len(times) // 2))  # ← 가운데
```
`starts_at` 은 asyncpg 가 준 **datetime 객체**다. `str()` 이 공백 구분자를 쓴다:
```
str(starts_at)[:13]  = '2026-09-07 17'     ← 공백
Open-Meteo time      = '2026-09-07T17:00'  ← T
```
그래서 `startswith` 가 **절대 맞지 않는다.** 그리고 폴백은 시각과 무관하게
`len(times)//2` = **UTC 12:00** 을 고른다. docstring 은 "정확히 없으면 가장
가까운 시각"이라고 적혀 있다 — 코드가 그렇게 하지 않는다.

운영 실측(2026-09-07, PHI 홈경기 · UTC 17:05 = 현지 13:05):
```
str(starts_at)[:13]='2026-09-07 17'  매칭 False
isoformat()[:13]  ='2026-09-07T17'   매칭 True
실제 경기시각 기온 : 24.8 ℃
코드가 고른 값     : 18.6 ℃  (time=2026-09-07T12:00 = 현지 08:00 아침)
차이               : 6.2 ℃
```
그 값이 `describe()` → `research["weather"]` → `scoring._weather_factor`(λ 계수)
→ 자료11 `날씨.계수·라벨` 로 **판정 프롬프트까지** 흐른다.
KBO·NPB(KST/JST 저녁 경기 = UTC 09~11시)는 우연히 정오와 가까워 오차가 작고,
**MLB 야간 경기가 가장 크게 어긋난다.**

## 🔴 최상위 — 자료12(실력 레이팅)가 실력이 아니라 "최근 2주"를 재고 있다

**E12-1 [최상·실측] 감쇠가 하루 0.9 라 반감기가 6.6일이다.**
`app/config.py:536 elo_decay = 0.9`, `team_elo._decay_weight` 는 **경과일**의
지수로 K 를 줄인다:
```
decay=0.9  → 반감기  6.6일 · 30일 전 가중 4.2% · 90일 전 0.008%
```
자료12 는 "시즌 집계표가 아니라 오늘 시점 **실력** 상태값"이라는 근거로
대원칙 예외를 받았다(`app/engine/CLAUDE.md` 개정 2026-09-07). 그런데 실제로
반영되는 것은 사실상 **최근 2주 성적**이다 — 그건 자료1·4·9 가 이미 보는 것이다.

**E12-2 [최상·실측] 감쇠를 바꾸면 실력 축 상관이 크게 달라진다.**
운영 DB 실측 (r = 레이팅 ↔ 그 리그 시즌 승률):
```
            반감기      레이팅 폭      MLB      KBO      NPB
decay 0.9    6.6일    49.7/67.4/68.1  +0.767   +0.575   +0.821   ← 현행
decay 0.95  13.5일    72.8/84.5/81.8  +0.903   +0.726   +0.916
decay 0.98  34.3일   105.2/109.7/94.7 +0.953   +0.856   +0.955
decay 0.99  69.0일   118.9/125.4/99.8 +0.964   +0.898   +0.964
decay 1.0   (없음)   135.8/142.0/105.5 +0.982  +0.930   +0.971
```
`docs/ACCURACY_2026-09-07.md` 가 인용한 근거는 **시장 p ↔ 시즌 실력 r=+0.707**
이었다. 실력 축을 복원하려고 넣은 자료12 가, 현행 설정에서는 셋 중 **가장 약한
실력 상관**을 낸다(KBO +0.575).

**E12-3 [상·실측] 프롬프트가 가르친 눈금이 데이터에 존재하지 않는다.**
`app/engine/prompts.py:100`:
> `격차`(홈−원정)가 이 경기의 실력차다. 대략 **격차 70점 ≈ 홈 승률 +10%p**.

실제 캐시된 자료12 (2026-09-07):
```
elo:mlb:2026-09-07  30팀 · 최고 Atlanta Braves 1522.8 · 최저 Baltimore Orioles 1473.1 · 폭 49.7
elo:kbo:2026-09-07  10팀 · 최고 Samsung Lions   1528.8 · 최저 Lotte Giants      1461.4 · 폭 67.4
elo:npb:2026-09-07  12팀 · 최고 Nippon-Ham      1540.9 · 최저 Rakuten           1472.8 · 폭 68.1
```
**MLB 는 리그 최강과 최약의 격차가 49.7점**이다 — 70점 격차인 경기가 존재할 수
없다. 판정은 프롬프트가 준 눈금으로 읽는데 그 눈금에 닿는 값이 안 온다.

**E12-4 [상·실측] 표본이 얇다.** 2026 시즌 종료 경기가 DB 에 이만큼뿐이다:
```
팀당 종료 경기  MLB 22.4 (19~26) · KBO 44.8 (42~47) · NPB 25.7 (24~27)
연도 분포       mlb 2026:336 · **mlb 2024:10** · kbo 2026:224 · npb 2026:154
```
- MLB 팀당 22경기 위에 6.6일 반감기를 곱하면 **실효 표본은 그보다 훨씬 작다.**
- `refresh` SQL 에 **시즌·날짜 조건이 없다** — 2024년 경기 10건이 섞여 있다.
  지금은 감쇠가 지워 주지만, 감쇠를 키우는 순간 작년 경기가 되살아난다.

**E12-5 [중] `refresh(pool, redis, sport, date)` 의 `date` 는 캐시 키에만 쓰인다.**
계산 쿼리에 상한이 없어 **어느 날짜로 불러도 "지금까지의 전부"** 로 계산한다.
실측: `elo:mlb:2026-09-06`·`09-07`·`09-08` 세 키의 값이 완전히 같다.
소급 재현·백테스트가 불가능하고, 내일 슬레이트가 오늘 값으로 미리 굳는다.

## 운영·감시 계층 · 훅 · Go

**O-1 [상] `api_guard` 의 차단 상태가 프로세스 메모리에 남아 수동 해제가 안 먹는다.**
 `_get` 은 `_memory` 를 **Redis 보다 먼저** 본다(`api_guard.py:104`). `clear_block`
 은 자기 프로세스의 `_memory` 만 지운다. 그래서 `railway ssh` 로 `tools/unblock`
 을 돌려 Redis 를 지워도, **이미 돌고 있는 스케줄러는 계속 차단으로 본다** —
 그 프로세스를 재시작해야 풀린다. CLAUDE.md 가 적은 "`tools/unblock` 이 운영
 상태를 바꾸지 못했다"의 **두 번째 원인**이다(첫째는 `railway run`).

**O-2 [중] CLAUDE.md 의 워치독 코드 목록이 뒤처졌다.** 코드에 16개, 문서에 9개:
```
문서에 없는 것: W-CARD-LATE · W-GAME-INVISIBLE · W-JUDGE-OBJECTION ·
                W-LLM-PAID · W-PANEL-DIVERGE · W-SOURCE-DRIFT · W-STALE-GAME
```
`app/watchdog.py` 의 모듈 docstring 도 9개만 적어 같은 사본이다.
CLAUDE.md 스스로 "사본 금지"를 규칙으로 두고 있는데 이 목록이 바로 그 사본이다.

**O-3 [중] `W-TRACE` 는 존재하지 않는 경보다.** `glass_report.py:281·396` 이
 "G3 가 이 숫자로 `W-TRACE` 를 울린다"고 두 번 적지만, 그 코드는 저장소 어디에도
 없다. 주석이 미구현 기능을 있는 것처럼 말한다.

**O-4 [중] 워치독의 "판정 있음" 판별이 빈 캐시를 통과시킨다.**
 `check_pending_sends`·`check_card_late` 는 `analysis:{sport}:{date}` **키의
 존재**만 본다. 실측에서 `analysis:kbo:2026-09-07` 은 존재하되 `games=0` 이었다 —
 그런 날엔 "판정 있음·발송 안 됨"이라는 틀린 사유가 붙는다.

**O-5 [중·자기관측] `claim-gate.sh` 의 "파일을 고쳤다" 판별이 너무 넓다.**
```
WRITE_HINTS = ("> ", ">>", "sed -i", "tee ", "io.open(", "patch ")
```
어떤 bash 명령이든 `> ` 를 포함하면 `edited=True` 다. 조사용 heredoc
(`cat > /tmp/probe.py <<EOF`)이나 `… > /dev/null` 도 걸린다.
**이 세션에서 실제로 그 오탐이 났다** — 저장소 파일 변경이 0(`git status`
비어 있음)인 턴에서 훅이 "완료 주장에 테스트 실행 없음"으로 울렸다.
훅 자신의 주석이 "헛경보가 쌓이면 이 훅은 곧 꺼지고, 꺼진 훅은 없는 훅이다"
라고 적고 있다.

**O-6 [중] 게이트 규칙이 Go 와 파이썬에 다른 값으로 두 벌 있다.**
```
crawler/internal/gate/gate.go   "home_rank": {kInt, min:1, max:12}
app/engine/physical.py          "rank": (1, 15)
```
`physical.py` 는 "Go 게이트와 **필드 집합이 겹치지 않는다** — 드리프트가 없다"
고 적고 있지만 `rank` 는 겹치고 값도 다르다.

**O-7 [하] 기계 검사 결과** (app+tools 전수, tests 제외)
```
except: pass (조용한 삼킴)   35건
create_task 반환 미보관       7건 (GC 시 태스크가 사라질 수 있다)
상수 분기 `if False:`         1건  app/pipeline.py:5067
상수 분기 `if True:`          1건  app/collectors/starter_season.py:338
가변 기본인자                  0건
== None                       0건
```

## 그 밖 (중·하)

**X-1 [중] `xsearch`·`grounding` 이 dedupe 표식을 캡 검사보다 먼저 소비한다.**
 `fetch_for_game` → `_once_ok`(표식 set nx) → `_cap_ok`(초과면 False).
 캡에 걸린 경기는 **표식만 소비하고 조사는 못 한 채** 그날 다시 시도되지 않는다.

**X-2 [중] `grounding` 은 "경기당 1회 고정"이라 적고 실제로는 2회 부른다** —
 `fetch_for_game` 이 홈·원정 각각 `fetch_for_team` 을 호출한다.

**X-3 [중] `football.similar_team` 은 토큰 1개만 겹쳐도 True.**
 `Manchester City` vs `Manchester United` → `{manchester}` → True.
 `odds._match_game`·`upsert_games_from_odds_events` 가 이 함수를 쓰고,
 후자는 그것으로 **중복 여부**를 판정한다(같은 시각 ±2h 의 맨유 경기가 맨시티
 경기 때문에 "중복"으로 안 실릴 수 있다). 같은 파일의 `match_team_name` 은
 동점이면 None 을 주는데 이쪽만 그 안전장치가 없다.

**X-4 [중] `kbo_stats.fetch_team_stats` 에 죽은 조건이 있다.**
```python
ip, er = _num(p.get("IP")), _num(p.get("ER"))
if ip and er is not None and g:
    stats["runs_allowed_per_game"] = ... _num(p.get("R")) ...   # ip·er 를 안 쓴다
```
`ER`·`IP` 가 없으면 무관한 값(`R`)의 계산이 통째로 막힌다.

**X-5 [하] `variable_parse._PAT` 의 대시 문자 클래스가 `[—-]` 뿐이다** —
 en dash(`–`)를 모델이 쓰면 그 변수는 형식 위반으로 빠진다.

**X-6 [하] `soccer_stats` 는 Big5 중 4리그만 지원**하고 K리그·J1·덴마크는
 Perplexity 폴백인데, `deepsearch_sports=mlb,soccer` 라 축구는 Perplexity 가
 살아 있다. 단 `soccer_trial_enabled=False` 라 실전 축구 경로는 꺼져 있다.

---

# 3차 — tools/ · 검증 하네스 (2026-09-07 23시대)

## 🔴 최상위 — 검증 도구 5개가 전부 죽어 있다 (실행으로 확인)

**TL-1 [최상·실행확인] 자료7·8 폐지(2026-09-04) 때 소비자를 안 고쳤다.**
`app/engine/matchup.py` 에서 `starters_season_payload`·`lineup_season_payload`
두 함수가 사라졌는데, 이것을 부르는 도구가 5개 남아 있다.

실제로 돌려본 결과:
```
$ uv run python -c "from tools.rehearsal import material_flags; material_flags({...})"
🔴 AttributeError: module 'app.engine.matchup' has no attribute 'starters_season_payload'

$ uv run python -c "from app.engine.matchup import bullpen_payload, lineup_season_payload"
🔴 ImportError: cannot import name 'lineup_season_payload' from 'app.engine.matchup'

$ uv run python -c "from app.engine.matchup import lineups_payload, starters_season_payload"
🔴 ImportError: cannot import name 'starters_season_payload' from 'app.engine.matchup'
```

| 도구 | 줄 | 어떻게 죽는가 |
|---|---|---|
| `tools/rehearsal.py` | `material_flags` (137·140) | `AttributeError` — 2단계에서 리허설 전체가 멈춘다 |
| `tools/rehearsal_kbo.py` | 105 | `ImportError` (import 문 자체) |
| `tools/rehearsal_mlb.py` | 106 | `ImportError` |
| `tools/probe_mlb_shadow.py` | 189–190 | `ImportError` |
| `tools/probe_league.py` | 199–200 | `AttributeError` |

전부 **함수 안 지연 import** 라 모듈 import 는 통과한다 — `python -c "import tools.rehearsal"`
는 OK 다. **실행해야만 드러난다.**

**TL-2 [상] 하네스가 폐지된 자료를 "필수"로 요구한다.**
```python
# tools/rehearsal.py
REQUIRED_BEFORE_LINEUP = ("1박스", "7선발시즌", "9불펜")   # ← 자료7 은 2026-09-04 폐지
OK_TO_BE_EMPTY = ("3타순", "8타선시즌")
```
설령 `AttributeError` 를 고쳐도, 자료7이 없는 것이 **정상**인 지금은 매 리허설이
`🔴 공시무관 재료 결손: ['7선발시즌']` 을 찍는다. 하네스가 정상을 결함으로 센다.

**TL-3 [중] 왜 아무도 몰랐나.** `rehearsal.run()` 은 `now.hour >= 17` 이면
즉시 반환한다(`tools/rehearsal.py:325`). 저녁 이후에 돌리면 조용히 건너뛰므로
`AttributeError` 를 만날 일이 없었다.

## 🔴 상위 — 리허설 격리 프록시가 5가지 경로로 샌다 (실행으로 확인)

**TL-4 [상·실행확인] `RehearsalRedis` 의 `_KEYED` 목록에 없는 메서드는
접두사 없이 실 Redis 로 그대로 나간다.**

가짜 Redis 를 물려 실제로 넘어가는 인자를 찍어봤습니다:
```
  ✅ ('get',          'rehearsal:analysis:kbo:2026-09-08')
  🔴 ('delete',       'rehearsal:a', 'b', 'c')      ← 첫 키만 접두사, 나머지는 실 키
  🔴 ('keys',         'alert:*')                    ← 실 키 목록
  🔴 ('mget',         'x', 'y')
  🔴 ('srandmember',  'cell_retry_queue')
  🔴 ('scan_iter',    'scout:kbo:*')                ← 실 Redis 전체를 훑는다
```

접두사가 안 붙는 메서드를 **실제로 쓰는 코드**:
```
app/engine/pick_ledger.py:373   scan_iter("analysis:*")        ← 실 슬레이트 캐시 전부
app/engine/scout.py:229         scan_iter(match=pattern)       ← 실 정찰 기록
app/engine/cell_grade.py:135-6  srandmember + srem             ← 실 재시도 큐를 소비·삭제
app/alerts.py:69-71             keys("alert:*") + delete(*keys) ← 실 알림 억제 키 전량 삭제
```

⚠️ **지금 당장 터지는 것은 아닙니다** — 위 넷은 전부 스케줄러 잡에서만 불리고,
리허설이 타는 `build_analysis` 경로에는 없습니다. 그러나 격리는 "지금 안 부른다"가
아니라 **"불러도 안 샌다"** 여야 합니다. 리허설/스모크가 재는 범위가 넓어지는
순간(예: 일일 요약·워치독 한 줄 검증) 바로 샙니다.

⚠️ 가드 자체는 확인 결과 **정상**입니다 — `send_telegram` 은 코드베이스 전체가
   함수 안에서 지연 import 하므로 `_install_guards` 의 이름 교체가 유효합니다.
   (전수 확인: 최상단 import 는 `notify_api_error` 3곳뿐이고, 그것도 결국
   `alerts._send` 를 지나므로 막힙니다.)

## tools/deploy.sh

**TL-5 [상] "스케줄러 먼저"가 실제로는 지켜지지 않는다.**
```bash
all) deploy_one analystbot-scheduler ...   # railway up --detach — 요청만 보내고 즉시 반환
     deploy_one analystbot-bot ...          # 곧바로 다음 요청
     deploy_one analystbot-crawler ...
# 그 뒤에야
for svc in $DEPLOYED; do wait_success "$svc"; done
```
`--detach` 라 **세 서비스가 동시에 빌드·기동**합니다. 주석은
*"스케줄러를 먼저 배포한다 — 기동 시 DB 스키마를 적용하므로, 봇이 먼저 새
코드로 뜨면 아직 없는 컬럼을 참조할 수 있다"* 라고 약속하는데, 보장되는 것은
**업로드 요청 순서**뿐이고 실제 기동 순서는 빌드 시간이 정합니다.

**TL-6 [상] `wait_success` 가 직전 배포의 SUCCESS 를 보고 통과할 수 있다.**
```bash
railway deployment list ... --json | python3 -c '...json.load(sys.stdin)[0]["status"]'
```
**배포 ID 를 비교하지 않습니다.** 목록의 `[0]` 이 방금 요청한 배포라는 보장이
없고, 새 배포가 아직 큐에 들어가기 전이면 **이전 성공 배포를 읽어 즉시 SUCCESS**
로 판정합니다. 이 게이트의 존재 이유가 *"요청 ≠ 배포"* 인데 그 구멍이 남아 있습니다.

**TL-7 [중] `deploy_one` 의 `cmd` 인자는 화면 표시에만 쓰인다.**
`railway up` 은 서비스에 이미 설정된 start command 를 쓰므로, 화면에 찍히는
`python -m app.scheduler` 는 **사본**입니다. 실제 설정과 갈려도 아무도 모릅니다.

## tools/stability_smoke.py — 배포 게이트가 최종 판정을 재지 않는다

**TL-8 [상] 운영 설정에서 이 게이트는 항상 1차 예비(무료)만 잰다.**
`JUDGE_PROVIDER=anthropic`(운영 실측) → `chain(MATCHUP_ROLE)[0][0] == "anthropic"`
→ `role = PRELIM_ROLE` 로 대체 → `gemini/gemini-3.7-flash` 를 3회 부른다.
모듈 주석이 그 사실을 인정하지만, `deploy.sh` 의 실패 문구는
*"같은 재료가 다른 답을 냈다 — 배포 중단"* 이라 **최종 판정(Opus) 얘기처럼
읽힙니다.** 최종 판정의 안정성은 배포 시 한 번도 검사되지 않습니다.

## tools/ 문서가 CLAUDE.md 와 정면으로 어긋난다

**TL-9 [상] 세 도구가 아직 `railway run` 을 쓰라고 안내한다.**
```
tools/unblock.py:14         railway run python -m tools.unblock --list  # 운영에서
tools/resend.py:14          `railway run python -m tools.resend --sport mlb` 로 쓴다.
tools/repair_lineups.py:16  railway run python -m tools.repair_lineups   # 운영에서 실행
```
CLAUDE.md 는 *"🔴 `railway run` 은 '서버에서 돌린다'가 아니다 … `tools/resend`·
`tools/unblock` 이 이것 때문에 운영 상태를 바꾸지 못했다 (실측 2026-09-05)"*
라고 적고 있습니다. **사고를 겪고 루트 문서는 고쳤는데 도구 본문은 안 고쳤습니다.**
`resend.py` 는 같은 docstring 안에서 *"서버에서 돌린다. 로컬 Redis·DB는 운영과
다른 저장소라…"* 라고 경고한 **바로 다음 줄**에 `railway run` 을 권합니다.

## tools/smoke_e2e.py

**TL-10 [중] 스모크의 `[materials]` 가 운영 로그와 다른 것을 잰다.**
`_materials()` 가 문자열을 **재구현**하면서 `자료12` 를 포함시켰는데, 운영이
실제로 찍는 `matchup.py:803` 에는 자료12 가 없습니다(앞서 W-1). `game_trace` 의
규약("포맷을 두 번 쓰지 않는다")을 스모크가 어겼고, 그래서 **스모크는 통과하는데
운영 원장에는 자료12 기록이 없는** 상태가 됩니다.

**TL-11 [중] `_counts["자료1박스"]` 가 홈만 센다.** `home_usage` 만 보고
원정은 안 봅니다 — `boxscore_payload` 는 양쪽을 보는데 비대칭입니다.

**TL-12 [중] 스모크 1회의 LLM 호출량이 문서에 없다.**
`build_slate` → `build_analysis`(슬레이트 전체 판정) + 경기당 `_judge` 2회(④·⑩).
KBO 5경기면 최소 5 + 10 = **15회 판정 호출**입니다.

**TL-13 [하] `run_game(pool, redis, rredis, …)` 의 `redis` 인자는 본문에서
한 번도 안 쓰입니다** — 실 Redis 객체를 넘기는데 사용처가 없습니다(죽은 인자).

## 🔴 /health 가 존재하지 않는 잡을 보고 "프리페치 기록 없음"을 영구 표시한다

**HE-1 [상·운영실측] `health.JOB_PERIODS` 가 실제 스케줄러와 어긋난다.**

`build_scheduler()` 를 실제로 돌려 잡 목록을 뽑고 운영 Redis 의 실행 기록과
대조했습니다.
```
스케줄러 실제 잡                     24개
운영 Redis 에 기록된 잡              26개 (죽은 이름 3개 포함)
health.JOB_PERIODS 가 조회하는 잡    10개

🔴 /health 가 적었는데 실제로는 없는 잡 : ['prefetch_daily']
🔴 실제 잡인데 /health 가 안 보여주는 것: 15개
   calibration_weekly · daily_summary_asia/overseas/soccer · heartbeat_2m ·
   kbo/mlb/npb_lineup_history · npb_pregame_2m · park_weekly ·
   prefetch_asia/dawn/evening · soccer_trial_10m · watchdog_5m
```
`prefetch_daily` 는 **이름이 갈린 뒤 남은 사본**입니다(실제는
`prefetch_dawn`·`prefetch_asia`·`prefetch_evening` 셋). 그 결과:
 · `/health` §2 잡 표에 `prefetch_daily 마지막 기록 없음`(🟡)이 늘 뜨고
 · `/health` §4 는 `runs.get("prefetch_daily")` 를 보므로
   **"⚪ 마지막 프리페치 기록 없음"이 영구 표시**됩니다.

운영 실측 — 프리페치는 정상 동작 중입니다:
```
prefetch_asia     2026-09-07T05:01:02 ok=True
prefetch_dawn     2026-09-06T19:31:47 ok=True
prefetch_evening  2026-09-07T12:42:57 ok=True
```
**정상인데 화면은 "기록 없음"이라고 말합니다.**

**HE-2 [중] `JOB_PERIODS` 자체가 금지된 사본이다.**
`app/registry.py` 는 *"잡의 **주기는 여기 적지 않는다.** 트리거 객체
(`scheduler._JOB_TRIGGERS`)가 원본이다 — 여기 옮겨 적으면 그 순간 다시
사본이 된다"* 고 못박고, 워치독은 그 규율을 지킵니다(`_next_expected`).
그런데 `/health` 는 10개 잡의 주기를 손으로 적어 두었고, 거기엔
`mlb_pregame_5m: 5분` — **워치독 오탐 4건을 만든 바로 그 항목**이
그대로 있습니다(실제는 `CronTrigger(hour="5-11")`).

**HE-3 [중] 워치독이 24개 잡 중 7개만 봅니다.** 감시 밖:
```
elo_refresh_weekly · statcast_daily · soccerdata_daily · ingest_finals_13h ·
prefetch_dawn/asia/evening · daily_summary_asia/overseas/soccer ·
kbo/mlb/npb_lineup_history · park_weekly · calibration_weekly · soccer_trial_10m ·
watchdog_5m(자기 자신)
```
**프리페치 3종이 전부 감시 밖**입니다 — 프리페치가 멈춰도 `W-JOB-LATE` 가
뜨지 않습니다.

**HE-4 [중] 죽은 잡 기록이 Redis 해시에 영구히 남습니다.**
`record_job_run` 은 `hset` 만 하고 정리하지 않습니다. 운영 실측:
```
asia_lineup_1700    2026-08-28T08:40  ← 10일 전, 지금 없는 잡
grade_yesterday     2026-08-29T04:00  ← 9일 전, 지금 없는 잡
pregame_push_1745   2026-08-28T08:57  ← 10일 전, 지금 없는 잡
```

**HE-5 [중] `/health` 의 "오늘 지표"가 MLB·축구만 봅니다.**
`for sport, label in (("mlb","MLB"),("soccer","축구"))` — **KBO·NPB 가 없습니다.**
자동 발송의 주력 두 리그가 지표 절에서 통째로 빠져 있습니다.

**HE-6 [중] `/health` 가 틀린 모델명을 찍습니다.** `judge 모델 {s.judge_model}`
은 **구 Judge(축구·`--old`) 전용** 값입니다. 실제 최종 판정은 `matchup_model`
(운영 `MODEL_MATCHUP=claude-opus-5`), 1차 예비는 `free_judge_model`
(`gemini/gemini-3.7-flash`) 입니다.

**HE-7 [하] "Odds API 잔여 N콜" 줄은 항상 `?`** — 무과금 전환(`ODDS_PROVIDER=free`)
으로 그 카운터를 아무도 안 채웁니다.

## tools/ — 나머지

**TL-14 [상·실행확인] 배포 게이트의 프롬프트에 선발 투수 이름이 없다.**
`stability_audition.build_prompt()` 의 픽스처가 `{"이름": "톨허스트"}` 인데
`starter_recent.pitcher_name` 은 `p.get("name")` 을 읽습니다. 실행 확인:
```
pitcher_name(home) = ''      pitcher_name(away) = ''
'톨허스트' 프롬프트에 있나: False    '이승현' 프롬프트에 있나: False
```
전수 확인 결과 **운영 수집기는 전부 `"name"`** 을 쓰고 `"이름"` 을 쓰는 곳은
이 픽스처뿐입니다. 배포마다 도는 안정성 게이트가 **자료4의 주체가 없는
프롬프트**로 산포를 재고 있습니다. (V-1 `ERA`/`era` 와 같은 계열의 결함입니다.)

**TL-15 [중] 1회성 도구가 하드코딩된 채 남아 있다.**
`rejudge_failed_matchups.py` — `DATE="2026-08-29"` + game_id 13개 고정.
`llm_audition.py` — `BASELINE` 에 game_id 2559~2564 과 p 값 고정.
지금 돌리면 "analysis 캐시 없음"만 나옵니다.

**TL-16 [실측] `app/` 자체에는 끊어진 심볼 참조가 0건**입니다.
AST 로 `from app.* import ...` 와 별칭 속성 접근을 전수 검사한 결과, 끊어진
참조 9건은 **전부 `tools/`** 에 있습니다(그중 8건이 자료7·8 폐지 잔재,
1건은 `smoke_e2e` 의 `hasattr` 로 방어된 `lineup_slots`).
운영 코드는 내부적으로 일관됩니다 — 뒤처진 것은 검증 도구뿐입니다.

---

# 4차 — 테스트·스키마·research·죽은 수집기

## 🔴 파이프라인 E2E 테스트 19개가 "수집 실패 상태"만 검사한다

**TS-1 [상·실행확인] 전체 스위트는 초록인데, 그 안에서 세 소스가 통째로 막혀 있다.**
```
$ PYTHONPATH=. uv run pytest tests -q
2521 passed, 4 skipped in 67.03s          (2026-09-07 23:2x KST · HEAD 21e84d2)

===== 외부 HTTP 차단 — 목이 필요한 지점 =====
19개 테스트 → statsapi.mlb.com · news.google.com · generativelanguage.googleapis.com
```
막힌 19개에 **파이프라인 회귀 방어가 통째로 들어 있습니다**:
```
test_pipeline_end_to_end_card            test_pipeline_uses_cache
test_pipeline_survives_research_failure  test_board_lists_every_game_and_market
test_recommended_picks_meet_win_prob_and_odds_floor
test_judge_pass_excluded_from_recommendations   … 외 13
```
`conftest._guard` 가 예외를 던지고, 파이프라인의 넓은 `except` 가 그것을 삼키고,
테스트는 **부분 수집된 상태**를 검사해 통과합니다. 즉 **statsapi(일정·선발)·
Google News RSS(자료2)·Gemini 세 경로가 깨져도 스위트는 초록입니다.**
conftest 자신이 이것을 "목이 필요한 지점의 지도"라 부르며 매 실행마다 빨간
헤더로 출력합니다 — **알고 있고, 아직 안 채웠습니다.**

## db/schema.sql — 정상

**SQ-1 [실측] 스키마와 운영 DB가 일치합니다.** 표 16/16 · 뷰 6/6, 양쪽 어디에도
없는 것 0건. 표별 행수:
```
odds_snapshots 33,463 · pitcher_appearances 6,261 · game_trace 2,169 ·
lineup_events 1,639 · predictions 1,278 · judgement_audit 1,119 · games 958 ·
variable_ledger 653 · pick_ledger 636 · lineups 566 · lineup_verdicts 320 ·
cell_verdicts 258 · market_baseline_ledger 66 · judge_review 0 · shadow_panel 0
```
`market_baseline_ledger` 66 vs `pick_ledger` 636 — **시장 기준선이 판정의 10%에만
남아 있습니다.**

## 수집은 하는데 야구 판정에 도달하지 않는 것

**UN-1 [중·실측] Perplexity 를 하루 24~43콜 태우고 무효율이 절반입니다.**
```
research_calls:2026-09-06 = 43콜        무효 15/25 = 60.0%
research_calls:2026-09-07 = 24콜        무효  7/15 = 46.7%
```
`/health` 는 "무효율 30% 초과 — 키워드 과잉 의심" 경고선을 갖고 있는데
**계속 초과 중**입니다. MLB 11경기×2팀=22칸 채움률 실측:
```
offense.woba_30d          2/22  ( 9%)
offense.vs_lhp_woba      21/22  (95%)   ← 좌우 스플릿: 프롬프트가 "쓰지 마라"고 못박은 지표
bullpen.fip               2/22  ( 9%)
bullpen.ip_last3d         2/22  ( 9%)
bullpen.closer_available  6/22  (27%)
pitcher.siera             0/22  ( 0%)
```

**UN-2 [중·실측] `_offense`·`league_baselines`·`bullpen_overused`·`splits`·
`motivation` 은 λ 전용인데, 야구는 λ를 끕니다.**
`pipeline._compute_picks` 가 `BASEBALL_SPORTS` 에 대해 `jg["lam"]=None ·
p_model 미사용 · p_final = p_claude` 로 못박습니다(`pipeline.py:3460~`).
소비자를 전수 추적한 결과 위 다섯 키는 전부 `scoring`/`lambda_model`/`performance`
(= λ 경로)로만 흐릅니다.
그런데 `statcast_daily` 는 매일 돌고(운영 실측 2026-09-06 18:30 ok), 그것이
받는 것은 **30일치 투구 단위 원본**입니다.

**UN-3 [중] `app/collectors/lineup_season.py`(567줄)의 수집 로직은 호출자가 없습니다.**
자료8 폐지(2026-09-04) 뒤 `attach`·`fetch_mlb`·`fetch_kbo`·`fetch_npb` 를 부르는
곳이 `app/` 에 0곳입니다. 재사용되는 것은 헬퍼 5개(`_f`·`NPB_TEAMS`·`_cells`·
`norm_jp`·`strip_pos`)뿐입니다.
⚠️ `app/engine/CLAUDE.md:64` 는 *"수집기(`starter_season.py`·`lineup_season.py`)는
   지우지 않았다 — `variable_ref` 가 자료10 참조에 쓴다"* 고 적었는데,
   `variable_ref` 가 쓰는 것은 **`starter_season` 뿐**입니다. 문서가 든 이유가
   `lineup_season` 에는 해당하지 않습니다.

## alerts.py

**AL-1 [중] 전역 예산 카운터가 `bypass_suppression` 경보에도 증가합니다.**
`_over_budget` 이 `incr` 를 먼저 하고, bypass 경보(폴링 중단·크래시)는 그 값을
소비하면서 자기는 통과합니다. bypass 가 잦으면 **일반 경보가 예산에 막힙니다.**
예산은 10분 12건인데 워치독 코드는 16종입니다.

## Go 크롤러 — 확인 결과 정상

**GO-OK [실측] NPB 홈/원정 순서 규약이 Go·Python 양쪽에서 일치합니다.**
`/top 打順` 첫 표 = 홈 (Go `parseNPBLineups` · Python `parse_batting_orders` 둘 다),
`/stats` 첫 표 = 원정 (Python `parse_pitching_stats`, 주석에 명시).
처음 "뒤집혔을 수 있다"고 의심했으나 테스트 픽스처(`神宮 ヤクルト 巨人`)까지
확인해 **오탐으로 접었습니다.**

**GO-1 [중] 게이트 규칙이 Go·Python 에 다른 값으로 두 벌 있습니다** (앞서 O-6).
```
crawler/internal/gate/gate.go  "home_rank": {kInt, min:1, max:12}
app/engine/physical.py         "rank": (1, 15)
```

## 훅

**HK-1 [중] `guard-bash.sh` 의 heredoc 제거가 문자열 안의 `<<` 도 인식합니다.**
`echo "a << b"` 같은 문장이 heredoc 시작으로 읽혀 뒤 줄들이 스캔에서 빠집니다.
지금은 게이트를 **느슨하게** 만드는 방향이라 오탐은 아니지만 회피 경로입니다.

---

# 5차 — 🔴🔴 지금 당장 조치가 필요한 것

## S-1 [최상·실측] 운영 API 키 2개가 Redis 에 평문으로 남아 있다 (최대 13.5일)

`app/llm/provider.py:698~703`
```python
except Exception as exc:
    logger.warning("[llm:%s] %s/%s 실패: %s", role, p.name, p.model, exc)   # ← 로그에 평문
    await _ledger.record_outage(redis, p.name, role, _outage_kind(exc), str(exc))  # ← Redis 에 평문
```
httpx 의 `Illegal header value b'Bearer <키 전체>'` 예외 문자열이 **마스킹 없이**
그대로 저장됩니다.

운영 Redis 실측 (값은 출력하지 않고 **현재 환경변수와 일치하는지만** 대조):
```
🔴 운영 API 키가 평문으로 들어 있는 Redis 키:
   GROQ_API_KEY:
      llm_outage:2026-09-07   TTL 13.5일
      llm_outage:2026-09-06   TTL 13.3일
      llm_outage:2026-09-05   TTL 12.3일
      llm_outage:2026-09-04   TTL 11.1일
   NVIDIA_API_KEY:
      llm_outage:2026-09-04~07  (같은 4개 키)
```
**지금 쓰고 있는 키**입니다(현재 `os.environ` 값과 문자열이 일치). Railway 로그에도
같은 줄이 남아 있습니다.

⚠️ `tools/check_llm.py` 는 `mask()` 를 두고 *"키 값을 절대 그대로 찍지 않는다 —
   로그·화면은 공유된다"* 고 적었고, `app/db.py:329` 는 *"실사고 2026-08-27:
   Railway pre-deploy 로그에 DB 비밀번호가 평문으로 찍혀 있었다. 로그는 보관되고
   공유되므로 한 번 새면 되돌릴 수 없다"* 를 기록했습니다.
   **같은 유형이 LLM 키에서 재발했고, 아직 안 지워졌습니다.**

## S-2 [상·실측] 그 원인 — `GROQ_API_KEY` 에 `.env` 세 줄이 통째로 들어가 있었다

`llm_outage` 원문:
```
"provider": "groq", "role": "narrator", "kind": "other",
"detail": "Illegal header value b'Bearer gsk_…\\nNVIDIA_API_KEY=nvapi-…\\nMISTRAL_API_KEY=xN5…"
```
Railway 변수에 여러 줄을 붙여넣어 한 변수에 3줄이 들어갔고, `Authorization` 헤더가
불법 값이 되어 **groq 이 전량 실패**했습니다.

`llm_calls:{date}` 실측:
```
2026-09-04  groq:fail  49 · gemini:ok 23 · gemini:fail 26
2026-09-05  groq:fail  57 · gemini:ok 32 · gemini:fail 25
2026-09-06  groq:fail 102 · gemini:ok 102     ← groq 100% 실패, 전량 gemini 폴백
2026-09-07  groq:fail   6 · groq:ok 8         ← 이 사이에 복구된 것으로 보임
```
운영 `GROQ_API_KEY` 는 **지금은 정상**입니다(스케줄러·봇 둘 다 56자 1줄).
사흘간 `INTENT_PROVIDER=groq`·`NARRATOR_PROVIDER=groq`·`INTERPRETER_PROVIDER=groq`
세 역할이 매 호출마다 실패 → gemini 재시도를 했습니다.

## S-3 [상] 워치독이 그 사흘을 한 번도 알리지 않았다

`W-LLM-FAIL` 은 `LLM_FAIL_KEY` **연속** 카운터가 3에 닿아야 울립니다. 그런데
`provider.complete` 는 폴백이 성공하면 `clear_llm_failures` 로 카운터를 지웁니다.
**"1순위 provider 가 100% 실패하지만 폴백이 매번 성공"** 은 이 감시의 사각지대입니다.
사흘 208건이 조용히 지나갔습니다.

---

# `/health` 실행 결과 (운영, 2026-09-07 23:08 KST) — 앞 발견들의 실물 확인

```
🟢 코드 7c0f9be · 가동 0분
   🟡 prefetch_daily       마지막 기록 없음      ← HE-1 (존재하지 않는 잡)
   …
   Odds API 잔여 ?콜                            ← HE-7
   judge 모델 claude-opus-4-6                    ← HE-6 🔴 실제 최종 판정은 claude-opus-5
⚪ 마지막 프리페치 기록 없음                      ← HE-1 (실제로는 3회 정상 실행)
📊 오늘 지표
   MLB λ 0/11 (0%) · 판정 11/11 (100%) · 리서치 6/11 (55%)
   축구 분석 캐시 없음                            ← KBO·NPB 는 아예 표시 안 됨 (HE-5)
   리서치 무효율 47% (7/15) ⚠️ 30% 초과          ← UN-1
🗄 경기 958 · 픽 기록 1278 · ⚠️ 상태 밀림 75건    ← 이전 세션 27건 → **75건으로 악화**
🔴 크롤러 하트비트 없음 — 미실행                  ← GO-10
🤖 provider 마지막 성공: 🔴anthropic 22:22 · 🔴gemini 01:23 · 🟢groq 13:50
🤖 LLM 3일 사용: gemini 140건(실패 25) · groq 4건(실패 165)   ← S-2
```

**H-EX1 [중] `λ 0/11 (0%)` 는 고장이 아니라 설계입니다.** 야구는 `pipeline` 이
λ를 명시적으로 끕니다. 그런데 `/health` 는 그것을 **0%** 로 표시해 사용자가
고장으로 읽습니다.

**H-EX2 [상·실측] 미확정 경기가 27건 → 75건으로 늘었습니다.**
```
상태 밀림(시작 6시간 경과·final 아님): 75건
```
`W-STALE-GAME` 은 "**새로** 생긴 것"만 울리도록 설계돼 서 있는 더미는 조용합니다
— 설계대로지만, 등록부(`evidence/OPEN.md` #15)가 27건으로 멈춰 있는 동안
실제로는 2.8배가 됐습니다.

## GO-10 [상·실측] 휴식일에는 크롤러가 "미실행"으로 보고된다

```
crawl:kbo:2026-09-06:latest   ← 어제
crawl:npb:2026-09-06:latest   ← 어제
crawl:heartbeat = None        ← 🔴
```
`crawler/cmd/crawler/main.go:117~121` 이 `len(raw)==0` 이면 **`Save()` 를 건너뜁니다**.
`store.Save` 만이 `crawl:heartbeat` 를 갱신하므로, 경기가 0인 날에는 하트비트가
2시간 뒤 만료되고 `/health` 가 `🔴 크롤러 하트비트 없음 — 미실행` 을 찍습니다.
오늘 KBO·NPB 는 실제로 0경기입니다(DB 확인) — **정상인데 고장으로 보고합니다.**

**GO-11 [중] 상수 둘이 서로 모순입니다.**
```
Go   store.Save          crawl:heartbeat TTL = 2시간
Py   crawler_feed        STALE_MINUTES   = 180분(3시간)
```
TTL 이 판정선보다 짧아 `"크롤러 N분째 멈춤"` 분기는 **영원히 도달할 수 없고**,
항상 `"하트비트 없음 — 미실행"` 만 나옵니다.

## 교차검증(절대 규칙 2의 감시)이 9일간 0건이었다

**CC-1 [상·실측]**
```
research_crosscheck:2026-08-28 ~ 09-05   checked=0  (9일 연속)
research_crosscheck:2026-09-06           checked=6
research_crosscheck:2026-09-07           checked=7
```
*"LLM 수치와 API 숫자가 충돌하면 API가 이긴다"*(절대 규칙 2)의 감시 구현이
**9일 동안 아무것도 대조하지 않았고, 경보도 없었습니다.** 지금도 하루 6~7항목
(`SAMPLE_SIZE=2` 경기 × 최대 4항목)뿐입니다.

## 그 밖

**TL-17 [중] `tools/ablation_lambda.py:9` 에 삭제된 세션의 절대경로가 박혀 있습니다.**
```python
pickle.load(open('/private/tmp/claude-501/…/e226050e-…/scratchpad/statcast_raw.pkl','rb'))
```
그 세션 스크래치패드는 없습니다(확인). 실행 즉시 `FileNotFoundError` 입니다.
전수 검사 결과 이런 하드코딩 절대경로는 이 한 곳뿐입니다.

**PR-1 [중] `soccer_lineup_probe_job` 은 스케줄 잡이 아니라 기동 시 뜨는
맨 `asyncio.create_task` 입니다** (`scheduler.py:2050`). `probe_run(hours=30,
interval=600)` 의 `while pending:` 루프가 **최대 30시간** 돌며 FotMob 을 칩니다.
`record_job_run` 을 안 하므로 `/health`·워치독 어디에도 안 나옵니다.
운영 로그로 지금 돌고 있는 것을 확인했습니다(`[soccer-probe] … T-145.8m …`).
그리고 태스크 참조를 보관하지 않아 GC 되면 조용히 멈춥니다.

**GO-6 [하] Go 크롤러는 KBO·NPB 전용입니다** (`fetchers` 맵에 mlb 없음).
`crawl:mlb:*` 키는 파이썬 `collectors/lineups.py:206` 이 씁니다.

---

# 6차 — 변수 평의회 · Perplexity · api_guard 우회 (2026-09-08 00시대)

## 🔴 CO-1 [최상·실측] 배당 사이트 제목이 자료2를 타고 판정 프롬프트에 들어간다

`app/engine/prompts.py:127` — *"근거는 위 자료 안에서만 찾는다. **배당**, 팀 명성,
사전 지식은 쓰지 않는다."* 그런데 자료2 안에 배당 사이트 기사 제목이 실려 있습니다.

운영 판정 프롬프트 12건 실측 (playoff odds 같은 오탐은 제외하고 **베팅 문맥만**):
```
🔴 자료2에 베팅 문맥 포함: 2/12

judge_prompt:4092
  {"tag": "[상황][미확인] roster_move", "dir": "=",
   "근거": "Braves vs Phillies Prediction, Pick, MLB Odds for Monday, September 7
            - Action Network (actionnetwork.com)", "확인": "미확인"}

judge_prompt:4097
  {"tag": "더비/라이벌전", "dir": "▼",
   "근거": "Cubs vs Brewers Prediction, Pick, MLB Odds for Monday, September 7
            - Action Network, …"}
```

경로: `news_rss` 가 Google News 에서 제목을 긁음 → `situation.classify` 가
`roster_move` 키워드(`acquired`·`trade` 등)에 걸어 상황 태그로 승격 →
`matchup.news_payload:277~281` 이 그 **제목을 근거 문자열 그대로** 자료2에 실음.

⚠️ `deepsearch.strip_odds` 는 `_ODDS_WORDS` 로 이 오염을 정확히 막습니다 —
   `"odds"`·`"prediction"`·`"sportsbook"` 이 목록에 있습니다. 그런데 그 방어는
   **딥서치 결과에만** 걸리고, **자료2(상황 태그) 경로에는 안 걸립니다.**
   같은 위험에 방어가 한쪽에만 있습니다.

⚠️ 실제 배당 숫자는 아니고 기사 **제목**입니다. 그러나 `market_edge.py` 가 적은
   금지선은 *"판정 숫자가 배당에 좌우되는 것"* 이고, 판정 모델이
   `"Braves vs Phillies Prediction, Pick"` 을 읽는 것은 그 선에 닿습니다.

## CO-2 [상·실측] 경기 후 상보가 평의회 조사 입력으로 들어간다

`council._headlines` 는 `research["{side}_news"]` **원본 RSS 목록**을 그대로 씁니다.
`situation.is_recap`(경기 후 기사 필터)을 타지 않습니다.

운영 심의록 10건 · 인용 기사 39개 실측:
```
🔴 경기후 상보(is_recap 판정): 3/39
   - Atlanta Braves at Philadelphia Phillies Game Story, Scores/Highlights - 09/06/2026
   - Field View: Kyle Schwarber's solo homer - MLB.com
   - Breaking down Derek Hill's home run - MLB.com
🔴 배당 탐지어 포함: 1/39
   - Braves vs Phillies Prediction, Pick, MLB Odds for Monday - Action Network
```
`registry.py` 는 *"🔴 경기 후 기사는 의미가 없다 … 지나간 사건을 오늘의 공기로
오인한다"* 며 `RECAP_MARKERS` 를 실측으로 채웠는데, 평의회는 그 필터 앞을
지나갑니다.

**CO-3 [중] 평의회 심의의 절반이 "불명"입니다.** 운영 10건:
```
조사경로: perplexity 8 · free_chain 2
기전    : 라인업변화 4 · 없음 3 · 동기 2 · (None) 1
방향    : 불명 4 · 원정 3 · 홈 2 · (None) 1
확실성  : 뒷받침 6 · 약함 3 · (None) 1
```
프롬프트가 *"`방향`이 `불명`이거나 `확실성`이 `없음` 이면 그 상황은 판단 근거로
쓰지 마라"* 라고 하므로, **10건 중 4~5건은 유료 조사를 태우고 판정이 쓰지 않는
결과**입니다. `(None) 1` 은 심의 자체가 실패한 건인데 심의록은 저장돼 있습니다.

## 🔴 AG-1 [상] 크레딧 차단(`api_guard`)이 절반의 외부 호출을 막지 못한다

`raise_if_unusable` 를 부르는 곳은 코드베이스 전체에서 **`collectors/base.py:197`
한 곳**입니다. 즉 `BaseAPIClient` 를 상속한 것만 보호됩니다.

`httpx` 를 직접 여는 경로 (전부 가드 밖):
```
app/research/perplexity.py:238   ask_json         ← 평의회 조사 (유료)
app/collectors/grounding.py:181  search_uris      ← Gemini 그라운딩 (유료)
app/collectors/grounding.py:210  resolve
app/llm/openai_compat.py:162     complete         ← 판정 무료 사슬 전부
app/engine/deepsearch.py:420     _fetch_body
```
`ask_json` 은 자기 docstring 에 *"크레딧 소진(401 insufficient_quota)도 여기서
조용히 None 이 되고"* 라고 적어 이 사실을 인정하지만, **차단 회로가 열려 있어도
계속 호출합니다.** CLAUDE.md 의 *"차단을 자동으로 풀지 않는다 — 잔액 없는 키로
계속 호출하면 요금만 태운다"* 가 이 경로에서는 지켜지지 않습니다.

⚠️ `PerplexityClient`(BaseAPIClient 상속)는 보호됩니다. 보호되지 않는 것은
   같은 파일의 **`ask_json` 독립 함수**이고, 평의회가 그것을 씁니다.

## PP-1 [중] `fetch_expert_picks` 는 스스로 "미사용"이라 적고 있다

`app/research/perplexity.py:124~126` 주석: *"⚠️ 미사용 — 실운영 경로는
`deep_research_game` 의 응답에 expert_picks 가 함께 온다. (2026-08-25 확인:
app/ 안에 호출처 없음. 테스트만 참조한다.)"* — 전수 grep 으로 **여전히 사실**입니다.
그런데 `expert_picks` 표에는 **437행**이 쌓여 있습니다(`deep.py` 경로).
한편 `coverage.UNCOLLECTED` 는 야구 3리그 전부 `expert_picks` 를 "미수집"으로
선언합니다 — 축구분만 쌓이는 것으로 보이나 확인하지 않았습니다.

---

# 7차 — models/ · 학습 아티팩트 (2026-09-08 00시대)

## 🔴 ML-1 [상·실측] 학습 아티팩트가 서버에 하나도 없다

```
로컬                              서버(/app)
data/lambda_poisson.json  3,543B   ❌ 없음
data/elo/ratings.json     8,603B   ❌ 없음
data/elo/params.json     11,191B   ❌ 없음
data/elo/csv/            36개 파일  ❌ 없음
$ ls /app/data →  (빈 디렉토리)
```
`.gitignore:7` 에 `data/` 가 있고, Dockerfile 은 *"data/ 는 이미지에 넣지 않는다
… COPY 하면 빌드가 깨진다"* 며 빈 디렉토리만 만듭니다(`RUN mkdir -p /app/data`).

**결과 — 조용히 죽은 것 둘:**

① `lambda_model.predict_game` 은 `load_artifact()` 가 None 이라 **항상 None** 을
   돌려줍니다(`pipeline.py:3127` 이 부르는 병렬 채점 경로). 야구는 어차피 λ를
   끄므로 지금은 무해하지만, **"병렬 채점으로 실전 성능을 비교한다"는 목적이
   0건**입니다.

② `SoccerElo.load()` 가 `FileNotFoundError` → `elo = None` → 전 경기
   `p_model=0.5 · model_valid=False`. 축구는 λ를 **쓰는** 종목이고
   `p_final = 0.5*p_model + 0.5*p_claude` 인데, 모델 축이 통째로 비어 있어
   `blend()` 가 `p_claude` 단독으로 폴백합니다.
   `elo_refresh_weekly` 잡은 매주 월 05:00 에 돌지만(운영 실측 09-07 05:00 ok=True),
   그 결과는 **컨테이너 파일시스템**에 쓰이므로 다음 배포에 사라집니다.

⚠️ 지금 축구 분석 캐시가 0건이라(`analysis:soccer:*` 없음) 당장 카드에 영향은
   확인되지 않습니다. 그러나 `soccer_trial` 을 켜거나 `/soccer` 를 치는 순간
   이 경로를 탑니다.

## ML-2 [중] 학습된 λ 모델의 실측 성능이 사실상 동전던지기다

`data/lambda_poisson.json` (2026-08-25 학습):
```
train 2024-04-07 ~ 2025-09-23 (8,262 레코드)
test  2025-09-23 ~ 2026-08-23 (3,541 레코드 · 경기 1,658)

test 정확도 0.5229   ← 기준선 0.5000
test Brier  0.2489   ← 기준선 0.2500
p_max 0.6267 · 58% 이상 비율 0.009 (1,658경기 중 15건)
```
피처 중요도(순열):
```
+ park_factor        0.01909   ← 1위가 구장
+ sp_velo            0.00793
+ sp_xwoba_allowed   0.00576
…
- off_xwoba          0.00020   ← 타선 지표가 사실상 0
- off_k_pct          0.00014
- is_home           -0.00044   ← 홈 이점이 음수
```
`features.py:26` 은 *"Wharton: 타선 영향이 크다"* 를 근거로 타선 피처를 넣었는데,
**실측에서 타선 축이 전부 0 근처**입니다. 그리고 `is_home` 이 음수라는 것은
학습이 홈 이점조차 못 잡았다는 뜻입니다.

⚠️ 이 진단은 어제 문서(`docs/ACCURACY_2026-09-07.md`)가 **판정**에 대해 내린
   결론("확률의 크기에는 정보가 없다, Brier 0.2523 > 상수 0.2498")과 같습니다.
   **λ 모델도 같은 자리에 있었고, 그건 1년 전 학습 시점부터였습니다.**

## ML-3 [하] `evaluate_totals` 의 import 순서가 프로젝트 규약과 다르다
`from app.engine.metrics import ...` 가 `from app.engine.scoring import ...` 뒤에
옵니다(알파벳순 위반). 기능 영향 없음 — 린트가 잡지 않는 자리입니다.

## expert_picks — 확인 결과 정상 동작

**EP-1 [실측] `expert_picks` 는 실제로 채점되고 있습니다.**
```
종목별   mlb 349 · soccer 94
채점상태 win 192 · loss 194 · push 2 · 미채점 55  (적중률 49.7%)
```
⚠️ 다만 `coverage.UNCOLLECTED` 는 mlb·kbo·npb 전부 `expert_picks` 를 "미수집"으로
   선언합니다. **MLB 349건이 쌓여 있는데 선언은 "안 받는다"** 입니다 — 카드에
   "전문가 픽 미수집 — 2축 판정"이라 표기되면서 뒤에서는 받고 있습니다.

**EP-2 [중] `expert_ledger` 뷰의 "전문가"가 익명 문자열입니다.**
```
'미확인' 2건 · '프랑스어권 분석 팀' 1건 · '무기명 필자' 2건 ·
'무명 필자' 3건(승률 100%·ROI 0.81) · '익명 패널' 1건(ROI 1.17)
```
`consensus.expert_weight` 가 `roi_90d` 로 가중치(0.2~2.0)를 매기는데, 표본
1~3건짜리 익명 항목이 ROI 0.81~1.17 로 **최대 가중치**를 받습니다.
`MIN_GRADED_FOR_ADOPTION=5` 는 "불채택" 판정에만 쓰이고 **가중치 계산에는
안 걸립니다**(`expert_weight` 는 표본 수를 보지 않음).

**EP-3 [중] `predictions` 표는 사실상 미채점입니다.**
```
미채점 1,253 · win 11 · loss 6     (최근 7일에도 394행 신규)
```
`finals_job` 주석이 *"픽 채점은 하지 않는다 (2026-08-29 사용자 지시)"* 라고
적고 있어 **의도된 것**이지만, `predictions` 는 계속 쌓이고 `/health` 는
`픽 기록 1278` 로 셉니다. 채점은 `pick_ledger` 로 옮겨갔는데 이 표는 남아
매일 커집니다.

---

# 8차 — 훅 체계 (2026-09-08 00시대)

## HK-2 [상] 슬레이트 성역 우회의 사유가 감사 로그에 남지 않는다

`guard-bash.sh:89`
```bash
log_audit "OVERRIDE slate-window ${H}시 reason=${SLATE_OVERRIDE:-inline}"
```
`SLATE_OVERRIDE` 는 훅 프로세스의 **환경변수**인데, 실제 사용법은
`SLATE_OVERRIDE='사유' tools/deploy.sh` 로 **명령줄 앞에 붙는 인라인 할당**입니다.
그 값은 훅에 상속되지 않으므로 셸 변수는 항상 비어 있고, 항상 `:-inline` 폴백이
찍힙니다.

실제 감사 로그 (전체 8건):
```
2026-09-05  OVERRIDE slate-window 19시 reason=inline   × 2
2026-09-07  OVERRIDE slate-window 19시 reason=inline   × 4
2026-09-07  OVERRIDE slate-window 20시 reason=inline   × 2
```
훅 자신이 *"그 사유는 감사 로그에 남는다. '더 좋아질 것 같다'는 사유가 아니다"*
라고 약속하는데, **8건 전부 사유가 유실됐습니다.** 통과 판정은 `$SCAN` 문자열에
`SLATE_OVERRIDE=` 가 있는지로 하므로 **통과는 되고 기록만 안 됩니다** — 가장
나쁜 조합입니다(게이트는 열리는데 왜 열었는지는 안 남음).

⚠️ 어제(09-07) 저녁 슬레이트 창에 **6회** 우회했습니다. 성역 규칙은
   `docs/ENGINEERING.md §5` 이고 실사고 근거(17:45 배포로 NPB 재판정이 끊김)가
   있는 규칙입니다.

## HK-3 [중] `record-green.sh` 는 pytest 출력만 보고 종료 코드를 안 본다

```bash
if ! printf '%s' "$OUT" | grep -qE '[0-9]+ passed'; then exit 0; fi
if printf '%s' "$OUT" | grep -qE '[0-9]+ (failed|error)'; then … exit 0; fi
```
`tool_response` 의 `exit_code` 를 확인하지 않습니다. pytest 가 `2521 passed` 를
찍은 뒤 **teardown 에서 죽거나**(exit≠0), `-p no:cacheprovider` 류 플러그인 오류로
비정상 종료해도 마커가 남습니다. `collected N items / M errors` 형태의 **수집
단계 실패**도 `failed|error` 정규식에 안 걸립니다(문구가 `errors` 로 복수형).

## HK-4 [중] `plan-gate` 의 턴 카운터는 사용자 입력에서만 리셋된다

`turn-reset.sh` 는 `UserPromptSubmit` 훅입니다. 그런데 이 세션처럼 **한 턴이
길게 이어지면**(사용자 입력 없이 수십 번 도구 호출) 카운터가 계속 누적됩니다.
`plan-ack` 파일이 한 번 생기면 그 턴 내내 통과하므로 실질 피해는 없지만,
"3파일" 판정의 기준이 **대화 턴이 아니라 사용자 발화 간격**입니다.

## HK-5 [실측] 훅 체계 자체는 정상 동작 중

```
.claude/state/last-green
  dab4189fb0b5d480677664b64213f67650ace754
  2026-09-07 23:02:40
  2521 passed

현재 작업트리 서명: dab4189fb0b5d480677664b64213f67650ace754   ← 일치
```
그리고 감사 로그가 커밋 게이트의 실동작을 증명합니다:
```
2026-09-07 20:15:08 DENY commit-stale marker=4d3cd4… now=dab4189…
```
**서명이 바뀐 상태의 커밋이 실제로 차단됐습니다.** `worktree_sig` 가 커밋 여부와
무관하게 파일 내용만 해싱하는 설계도 의도대로입니다.

---

# statcast — 확인 결과 정상

**ST-1 [실측] Statcast 캐시는 정상입니다.**
```
statcast:offense:2026-09-07    팀  29  TTL 23.1h
statcast:pitchers:2026-09-07   투수 567
statcast:bullpen:2026-09-07    팀  29
statcast:batters:2026-09-07    팀  29
statcast:league:2026-09-07     지표  2
```
`_xwoba` 의 삼진 포함 계산, `_tail_games` 의 경기 수 절단, `MIN_PITCHER_PITCHES`
표본 가드, `STALE_FALLBACK_DAYS=3` 폴백까지 코드가 서술한 대로 동작합니다.

**ST-2 [중] 그런데 이 값들의 소비자가 야구 판정에는 없습니다** (UN-2 와 같은 건).
`merge_into_research` 가 채우는 `{side}_offense`·`{side}_pitcher.xwoba_allowed`·
`bullpen_overused`·`league_baselines` 는 전부 λ 경로 전용이고, 야구는 λ를 끕니다.
**하루 12만 행을 받아 29팀·567투수를 집계하는데, 그 결과를 읽는 것은
`predict_game`(아티팩트 없어 항상 None)과 `mlb_lambdas`(야구에서 미호출)뿐입니다.**

---

# 9차 — alerts.py 후반 (2026-09-08)

## AL-2 [중·실측] 워치독 코드 2개가 라벨 없이 "점검 필요"로 나간다

```
코드에 실재하는 W- 코드         16개
alerts.WATCHDOG_CODES 등재      14개
🔴 실재하는데 라벨 없음: W-LLM-PAID · W-SOURCE-DRIFT
```
`watchdog()` 은 `WATCHDOG_CODES.get(code, "점검 필요")` 이므로 두 경보는
텔레그램에 `🚨 W-LLM-PAID · 점검 필요` 로 나갑니다. **유료 호출 캡 근접**과
**소스 파서 무언 변경** — 둘 다 사람이 즉시 알아야 하는 것인데 제목이 무의미합니다.
(앞서 O-2 의 문서 사본 문제와 **다른 건**입니다. 이건 코드 안의 사본입니다.)

## AL-3 [중] 전역 예산을 bypass 경보가 먹는다 (앞서 AL-1 의 실측 확인)

```python
over = await _over_budget(r)          # incr 를 **먼저** 한다
if over is not None and not bypass_suppression:   # bypass 는 통과
    return False
```
`bypass_suppression=True` 로 보내는 경보 6종:
```
crashed / prefetch_report / cycle_report / cycle_errors / dispatch_report
+ bot/main.py:822 (폴링 중단 감지)
```
예산은 **10분 12건**입니다. 아시아·MLB 두 사이클이 각각 5분마다 돌고, 일이 있으면
`cycle_report` + `cycle_errors` 로 최대 2건씩 — 10분이면 최대 8건입니다.
거기에 `dispatch_report`·`prefetch_report` 가 겹치면 **예산이 bypass 경보로 차고,
정작 워치독 경보(bypass 아님)가 막힙니다.**

⚠️ 아직 실제로 막힌 기록은 확인하지 못했습니다(`alert:budget` 키가 10분 TTL 이라
   사후 확인 불가). 구조상 가능하다는 것까지가 확인된 사실입니다.

## AL-4 [실측] 알림 설계 자체는 잘 짜여 있습니다

`StageResult.severity` 의 4분류(정상·부분·실패·경기없음), `no_games` 를 `cause`
보다 **먼저** 보는 순서, `zero_ok` 를 호출부가 선언하게 한 것, `stages_summary`
가 부분 실패를 묶는 것 — 전부 실사고에서 나온 설계이고 코드가 그대로 지킵니다.
`overall_verdict` 가 휴식일을 "수집 실패가 아닙니다"로 먼저 답하는 것도 정확합니다.

---

# 10차 — 죽은 코드 전수 · research/deep 후반 (2026-09-08)

## DC-1 [실측] 정의만 있고 참조 0인 공개 함수 27개 — AST 전수

`app/` 정의 × `app+tools+tests` 전체 텍스트 참조로 교차했습니다.
**`bot/main.py` 의 `on_*` 12개는 오탐**입니다(aiogram `@router.message` 데코레이터
등록). 나머지 15개가 실제로 아무도 안 부릅니다:

```
app/alerts.py:537              dispatch_report()        ← 발송률 알림
app/collectors/football.py:200 fetch_team_form()
app/collectors/lineup_history.py:131 changes_since()    ← "18:05에 4번이 빠졌다"
app/collectors/news_rss.py:216 fetch_team_situation()
app/collectors/soccer_stats.py:189 load_elo()
app/engine/glass_report.py:445 load_final_jg()          ← 투명 리포트 DB 로더
app/engine/glass_report.py:472 load_sources()           ←        ″
app/engine/scoring.py:613      record_cap_hit()         ← 승률 상한 초과 계측
app/engine/scoring.py:626      cap_alert_count()
app/engine/variable_ledger.py:301 situation_report()    ← 상황 유형별 현실화율
app/engine/variable_ledger.py:351 situation_lines()
app/leagues.py:52              league_labels()
app/models/features.py:316     build_dataset()          ← λ 학습 진입점
app/models/lambda_model.py:128 evaluate_totals()
app/pipeline.py:3211           near_miss_picks()        ← "픽 없음으로 끝내지 않는다"
app/research/deep.py:484       fill_gaps()              ← 빈칸 보충 조사
```

## 🔴 DC-2 [상] 투명 리포트(G1·G2·G3)가 통째로 배선되지 않았다

```
$ grep -rn "glass_report" app/ tools/
(0건)
$ grep -rn "glass_report" tests/
tests/test_glass_report.py  ← 테스트만
```
`app/engine/glass_report.py` **508줄**이 `build()`·`load_final_jg()`·`load_sources()`
까지 완성돼 있는데 **스케줄러·봇·도구 어디도 부르지 않습니다.**
`game_trace` 표에는 2,169행이 쌓여 있습니다 — 원장은 채워지는데 그것을 읽어
문서로 만드는 층이 연결되지 않았습니다.

같은 파일이 두 번 *"G3 가 이 숫자로 `W-TRACE` 를 울린다"* 고 적는데 그 경보 코드도
없습니다(앞서 O-3). **G1(원장) 만 살아 있고 G2(리포트)·G3(경보)는 코드만 있습니다.**

## 🔴 DC-3 [상·실측] 승률 상한 초과가 한 번도 기록되지 않았다

`cap_probability` 는 절사만 하고 `record_cap_hit` 을 부르지 않습니다.
```
운영 Redis: prob_cap_hits:* 키 → 없음 (한 번도 기록된 적 없다)
config     prob_cap_alert_n = 3   "하루 이만큼 초과하면 모델 점검 필요 경고"
```
CLAUDE.md 는 *"이 값을 넘는 산출은 '강한 픽'이 아니라 **모델이 틀렸다는 신호**다"*
라고 못박는데, **그 신호를 세는 장치가 배선되지 않았습니다.**

⚠️ 다만 실측상 지금 클립에 닿는 판정은 거의 없습니다:
```
pick_ledger p_home 분포 (is_final 159건)
  mlb  n=106  상한(≥0.679) 0건 · 하한(≤0.321) 1건 · 범위 0.320~0.650
  kbo  n=29                0건            0건 · 범위 0.340~0.660
  npb  n=24                0건            0건 · 범위 0.360~0.640
```
`0.66~0.68` 구간이 1건, `0.32~0.34` 가 2건. **판정이 스스로 클립 근처를 피하고
있습니다** — 어제 진단의 "확률 크기에 정보가 없다"와 같은 그림입니다.

## DC-4 [중] `near_miss_picks` — "픽 없음으로 끝내지 않는다"가 실현되지 않았다

`pipeline.py:3211` 주석: *"[3-1] 자격 미달이어도 승률 상위 N개는 사유와 함께
보여준다 ('픽 없음'으로 끝내지 않는다)"*. 호출부 0곳입니다.
오늘 MLB 11경기가 전부 보드만이었는데, 이 함수가 배선됐다면 "왜 못 갔는지"를
상위 3건이라도 보여줬을 것입니다.

## DC-5 [중] Perplexity 쿼터가 두 경로에서 안 세어진다

`_record_call` 을 부르는 곳은 `get_game_research` **한 곳**뿐입니다.
```
app/research/deep.py:509      fill_gaps  → client.chat()  ← 배선 안 됨(DC-1)
app/research/perplexity.py:151,156  fetch_expert_picks    ← 배선 안 됨(PP-1)
app/engine/council.py:233     ask_json                    ← 🔴 **배선돼 있다**
```
`ask_json` 은 `PerplexityClient` 를 쓰지 않고 `httpx` 를 직접 열어 `client.calls`
자체가 없습니다. 평의회는 슬레이트당 최대 10콜(운영 실측 `council:calls=10`)을
태우는데 **`DAILY_RESEARCH_CAP=60` 에 한 건도 안 잡힙니다.**
`/health` 의 `Perplexity 24/60콜` 은 실제 사용량보다 **최대 10 적습니다.**

## DC-6 [하] `fill_gaps` 는 이미 정규화된 응답을 한 번 더 정규화한다
```python
raw  = await client.chat(prompt)      # chat() 이 이미 normalize_response 를 적용
text = normalize_response(raw)        # 두 번째 — "output" 키가 없어 그대로 반환
```
동작에는 문제가 없습니다(멱등). 배선되면 혼란의 소지입니다.

## RS-1 [중] `deep.py` 의 신선도 게이트는 잘 짜여 있다 (정상 확인)

`research_is_fresh`(캐시 6h + 킥오프 3h), `needs_refresh`(라인업 확정·선발 변경 시
강제), `cached_empty` 를 폴백에서 제외, `_record_call` 이 **재요청 콜까지** 세는 것,
`queue_for_retry` 가 429 만 큐잉하는 것 — 전부 서술대로 동작합니다.
`get_game_research` 의 status 6값(`fresh`·`refreshed`·`stale_fallback`·`missing`·
`invalid`·`quota`·`off`)도 호출부가 구분해 씁니다.

---

# 11차 — 소스 교차검증 (2026-09-08)

## 🔴 XC-1 [상] 사고를 잡으라고 만든 X 소스가 교차검증에 참여하지 않는다

`crosscheck_sources.py` 는 실사고(2026-08-26 NC@LG)를 근거로 만들어졌습니다:
```
딥서치·네이버  NC 선발 = 구창모
X 구단 공식     NC 선발 = 박준현   ← 가장 최신
```
그래서 `SOURCE_RANK` 최상위가 `official_x: 5 (구단 공식 X/홈페이지)` 입니다.

그런데 `pipeline.py:3676~3680`:
```python
_x = extract_starters_from_text(f"{news}\n{sentiment}", (jg["home"], jg["away"]))
if _x.get("any"):
    jg["x_starter_mention"] = _x["any"]     # ← 저장만 하고 끝
if len(_srcs) >= 2:
    jg["crosscheck"] = crosscheck_apply(research_clean, jg, _srcs, …)
```
**`_x` 는 `_srcs` 에 안 들어갑니다.** X 텍스트에서 뽑은 선발 이름은
`x_starter_mention` 에 저장되고 아무도 읽지 않습니다(전수 grep 확인).

## XC-2 [상] `official_x` 자리에 들어가는 것은 X 가 아니라 Go 크롤러다

```python
_crawl_snap = statcast_data.get("crawler")      # Go 크롤러(네이버 10분 주기)
if _crawl_snap:
    _srcs["official_x"] = {...}                  # ← 랭크 5 를 크롤러에 준다
_crawl = statcast_data.get("naver")              # 파이썬 네이버 수집기
_srcs["portal"] = {...}                          # ← 랭크 4
```
**`official_x`(5)와 `portal`(4)이 둘 다 네이버**입니다. 하나는 Go, 하나는 Python
경로일 뿐 **같은 원천**이라 값이 갈릴 이유가 거의 없습니다.
즉 교차검증이 실질적으로 대조하는 것은 `naver ↔ naver ↔ perplexity` 이고,
사고를 만든 축(X 구단 공식)은 빠져 있습니다.

## XC-3 [상·실측] `extract_starters_from_text` 는 홈/원정을 구분하지 못한다

시그니처는 `(text, teams)` 인데 **`teams` 를 본문에서 한 번도 쓰지 않습니다.**
반환은 `{"any": <첫 매치>}` 하나뿐입니다. 실행 확인:
```
'[KBO] LG 선발: 임찬규 / 두산 선발: 곽빈'        → {'any': '임찬규'}
'한화 선발 문동주, KIA 선발 양현종 예고'          → {'any': '문동주'}
```
두 팀 선발이 다 적힌 문장에서 **앞의 하나만** 가져옵니다. 어느 팀 것인지 모릅니다.
설령 `_srcs` 에 넣으려 해도 넣을 수 없는 모양입니다.

## XC-4 [실측] 교차검증이 실제로 돈 경기는 0건이다

```
운영 캐시 전수: crosscheck 실행된 경기 0 · 불일치 판정 0
```
조건이 `sport in ("kbo","npb")` **그리고** `len(_srcs) >= 2` 인데, 오늘·어제는
KBO·NPB 경기가 0이라 확인이 안 됩니다. 다만 앞선 KBO 슬레이트 캐시에도
`crosscheck` 키가 없습니다 — `_srcs` 가 2개를 못 채웠거나 이 블록에 도달하지
않았다는 뜻이고, **어느 쪽인지 로그가 남지 않습니다**(성공 시에만 `jg["crosscheck"]`
를 새기고, 미달 시 로그가 없습니다).

## XC-5 [중] `_refill_starter_stats` 가 채우는 필드가 대원칙과 충돌한다

```python
STARTER_STAT_FIELDS = ("era_season", "whip", "ip_avg_recent", "era_vs_opponent")
```
전부 **시즌 누적**입니다. 자료7 폐지(2026-09-04) 이후 이 값들은 판정 프롬프트로
가지 않으므로 지금은 무해하지만, 교차검증이 "선발이 바뀌면 시즌 성적을 다시
채운다"는 목적으로 여전히 공식 기록실 투수맵을 요구합니다
(`statcast_data["kbo_pitchers"]`).

## XC-6 [실측] `mark_collected` / `missing_fields` 는 정상 동작합니다

`kbo_roster.py:154`·`kbo_news.py:460` 두 곳이 `mark_collected` 를 부르고,
*"결장자 0명"과 "결장 정보를 못 구했다"* 를 구분합니다. 설계 의도대로입니다.
`provenance.py` 가 `SOURCE_RANK`·`norm_name` 을 재사용하는 것도 사본 없이 맞습니다.

---

# 12차 — 축구 Elo (2026-09-08)

## 🔴 SE-1 [최상·실측] 리그 코드 매핑이 한국어 라벨을 못 읽어 축구 모델이 80% 죽는다

`soccer_elo.LABEL_TO_CODE` 는 **영문 소문자 부분 문자열** 매칭인데,
`games.league` 에 실제로 들어 있는 값은 **한국어 라벨**입니다.

```
LABEL_TO_CODE = [("premier league","E0"), ("bundesliga","D1"),
                 ("primera","SP1"), ("la liga","SP1"), ("serie a","I1"), …]
```

실행 확인 (아티팩트를 실제로 로드해 `probs()` 호출):
```
league             경기  league_code   probs()
라리가               31   None          None      🔴
세리에A              27   None          None      🔴
EPL                12   E0            (0.727, 0.152, 0.122)   ✅
K리그1               8   None          None      (CSV 자체가 없음 — 설계상 정상)
분데스리가             6   None          None      🔴
덴마크 수페르리가         5   DNK           (0.484, 0.273, 0.243)   ✅
J1 리그              1   JPN           (0.465, 0.258, 0.277)   ✅

모델이 사는 경기: 18/90 (20%)
```

**라리가·세리에A·분데스리가 — 아티팩트가 멀쩡히 있는데(SP1·I1·D1) 라벨을 못
읽어 버려집니다.** DB 기준 64경기(90건 중 71%)가 `p_model=0.5 · model_valid=False`
로 떨어지고, `blend()` 가 `p_claude` 단독으로 폴백합니다.

⚠️ **`app/leagues.py` 에 정확한 매핑이 이미 있습니다.**
```python
"la_liga":    {"label": "라리가",    "elo": "SP1"}
"serie_a":    {"label": "세리에A",   "elo": "I1"}
"bundesliga": {"label": "분데스리가", "elo": "D1"}
```
`leagues.py` 는 자기 docstring 에 *"축구 리그 화이트리스트 레지스트리 —
일정·배당·모델·표기의 **단일 소스**"* 라고 적었는데, `soccer_elo` 가 그것을
읽지 않고 **자기 사본(`LABEL_TO_CODE`)을 따로 들고 있습니다.** CLAUDE.md 의
"사본 금지"가 정확히 이 모양을 금지합니다.

⚠️ EPL 만 우연히 맞은 이유: 라벨이 `"EPL"` → `.lower()` = `"epl"` 이고
   `("epl","E0")` 항목이 있습니다. 덴마크·J1 도 한글/영문 별칭이 우연히 겹칩니다.

⚠️ 이 결함은 **ML-1(서버에 아티팩트 없음)에 가려 지금은 안 보입니다.**
   서버에서는 `SoccerElo.load()` 가 `FileNotFoundError` 라 전 리그가 이미 무효입니다.
   아티팩트를 서버에 넣는 순간 이 결함이 드러납니다 — **두 개를 같이 고쳐야
   합니다.**

## SE-2 [중·실측] 피팅된 10리그 중 9리그가 시장보다 나쁘다

`data/elo/params.json` 백테스트 메트릭 (최근 2시즌 walk-forward):
```
리그    HA   c1   c2   n_eval  Brier모델  Brier시장   판정
E0      90 -0.4  0.6     760   0.6089    0.5922    시장승
E1      90 -0.3  0.8    1104   0.6324    0.6223    시장승
D1      90 -0.4  0.7     612   0.5974    0.5757    시장승
SP1     90 -0.5  0.7     760   0.5798    0.5654    시장승
I1      90 -0.4  0.9     760   0.5918    0.5748    시장승
F1      90 -0.2  0.9     612   0.5890    0.5738    시장승
N1      90 -0.3  0.8     612   0.5848    0.5686    시장승
P1      90 -0.3  0.7     612   0.5656    0.5398    시장승
DNK     30 -0.7  0.5     214   0.6239    0.6008    시장승
JPN     30 -0.5  0.6      20   0.5523    0.5532    모델승 ← n=20
```
**유일한 "모델승"이 n=20 인 J1 리그**입니다. 나머지 9리그는 전부 시장이 낫고,
격차도 일정합니다(0.010~0.026). 이것은 `docs/ACCURACY_2026-09-07.md` 가 야구
판정에 대해 내린 결론과 같은 그림입니다 — **축구 모델도 시장을 못 이깁니다.**

⚠️ `home_adv` 가 메이저 8리그 전부 **그리드 상한 90.0** 에 붙어 있습니다
   (`for ha in (30.0, 60.0, 90.0)`). 최적값이 격자 밖에 있을 가능성이 높은데
   그리드를 넓힌 기록이 없습니다.

## SE-3 [중] `p_final = 0.5*p_model + 0.5*p_claude` 인데 p_model 이 시장보다 나쁘다

`app/engine/CLAUDE.md` 축구 절: *"`p_final = 0.50*p_model + 0.50*p_claude`.
시장 가중치 0."* SE-2 대로면 **Brier 가 더 나쁜 축에 절반 가중치**를 주고
있습니다. 지금은 SE-1·ML-1 때문에 대부분 `p_claude` 단독으로 폴백하므로
**결함이 결함을 가리고 있는 상태**입니다.

## SE-4 [하] `--refresh` 없이 실행하면 무조건 백테스트를 출력한다
```python
if args.backtest or not args.refresh:
    _print_backtest(params)
```
`python -m app.models.soccer_elo` (인자 없음) → `SoccerElo.load()` → 아티팩트가
없으면 `FileNotFoundError` 로 죽습니다. CLI 사용법(`--refresh`)을 모르면
스택트레이스만 봅니다.

## CB-1 [중] `models/calibrate.py`(251줄) 전체가 배선되지 않았다

```
$ grep -rn "models.calibrate|load_learned|Coefficients" app/ tools/
(0건 — tests/test_calibrate.py 만 10곳)
$ ls data/lambda_coefficients.json  → 없음
```
`load_learned()` 는 *"저장된 학습 계수. 없으면 None(=config 기본값 사용)"* 이라
적었는데, **부르는 곳이 없어 config 기본값이 유일한 경로**입니다.
`scoring.py` 는 `s.exp_offense`·`s.exp_pitcher`·`s.home_run_edge` 를 그대로 씁니다.

모듈 docstring 이 스스로 문제를 적고 있습니다:
> *"현재 계수(exp_offense 1.20, exp_pitcher 0.50, home_run_edge 0.03 …)는 근거
> 있는 것이 변수 중요도 순서와 상한값뿐이고 **숫자 자체는 임의값**이다.
> docs/MODEL.md §9가 이 사실을 명시하고 있다."*

**그 임의값을 데이터로 교체하려고 만든 모듈이 배선되지 않아, 임의값이 그대로
운영 중입니다.** (야구는 λ를 끄므로 지금 영향은 축구 경로뿐입니다 — 그런데
축구는 SE-1·ML-1 로 이미 모델 축이 죽어 있습니다.)

## CB-2 [실측] 학습 계열 4모듈이 전부 같은 상태다

| 모듈 | 줄 | 배선 | 아티팩트 |
|---|---|---|---|
| `models/features.py` | 400 | `build_dataset()` 호출 0 | — |
| `models/lambda_model.py` | 315 | `predict_game` 만 호출, 아티팩트 없어 항상 None | 로컬만 |
| `models/calibrate.py` | 251 | 호출 0 | 없음 |
| `models/soccer_elo.py` | 309 | `refresh`(주1회)·`load` 호출됨 | 로컬만·서버 없음 |
| `models/elo_core.py` | 60 | 야구 자료12·축구 양쪽이 씀 ✅ | — |

**`elo_core` 하나만 실제로 판정에 닿습니다**(자료12). 나머지 1,275줄은 매주
`elo_refresh_weekly` 가 CSV 를 받아 재피팅하지만 그 결과가 컨테이너와 함께
사라집니다.

---

# 13차 — 백테스트 실행 (2026-09-08) · 🔴🔴 자료12 예측력 실측

## 🔴🔴 BT-1 [최상·실행측정] 자료12(elo)가 MLB·NPB 에서 동전던지기보다 못하다

`tools/backtest_tempo.py` 를 **운영 DB에서 실제로 돌렸습니다.** 그 안의
`기준선_elo` 가 곧 자료12 의 단독 예측력입니다. 그것만 따로 walk-forward 로
다시 재봤습니다(하루 1회 리플레이, 그 경기 이전 데이터만):

```
=== MLB 종료 379경기 ===
  decay  판정가능  적중   적중률    홈고정
   0.90    215   104   48.4%    52.1%   ← 현행. 홈고정보다 3.7%p 나쁘다
   0.95    214   106   49.5%    51.9%
   0.98    213   104   48.8%    52.1%
   1.00    215   107   49.8%    52.1%

=== KBO 종료 224경기 ===
   0.90    165    95   57.6%    52.1%   ← 현행. 유일하게 기준선을 이긴다
   0.95    166    98   59.0%    51.8%   ← 최고
   0.98    166    93   56.0%    51.8%
   1.00    166    90   54.2%    51.8%

=== NPB 종료 154경기 ===
   0.90     88    43   48.9%    52.3%   ← 현행. 홈고정보다 3.4%p 나쁘다
   0.95     88    40   45.5%    52.3%
   0.98     88    42   47.7%    52.3%
   1.00     88    44   50.0%    52.3%
```

**MLB·NPB 에서 자료12 는 어느 감쇠값으로도 "항상 홈팀"을 못 이깁니다.**
KBO 만 이깁니다(57.6%, 0.95 에서 59.0%).

⚠️ 이것은 앞서 E12-2 에서 잰 **`r(레이팅, 시즌승률)`** 과 정반대 그림입니다.
   그 상관은 MLB 에서 +0.767~+0.982 로 높았는데, **실제 경기 방향 예측은
   48.4%** 입니다. *"레이팅이 시즌 승률을 잘 설명한다"* 와 *"레이팅 차이로
   다음 경기 승자를 맞힌다"* 는 다른 질문이고, **후자가 우리가 쓰는 용도**입니다.
   제가 12차에서 상관계수만 보고 "0.95~0.98 이 낫다"고 시사했던 것을 여기서
   **바로잡습니다** — 방향 적중으로 재면 MLB 는 어느 값도 기준선 미달입니다.

⚠️ 자료12 는 2026-09-07 에 *"시장 대비 열세의 최대 원인 = 실력 축 부재"* 를
   근거로 판정 프롬프트에 **기본 축**으로 들어갔습니다
   (`prompts.py:102`: *"자료12 실력 격차는 기본 축, 최근 폼은 그 위의 조정 축"*).
   MLB 는 오늘 슬레이트가 11경기이고 KBO·NPB 는 0경기입니다 —
   **가장 많이 판정하는 리그에서 그 축이 기준선 미달입니다.**

## BT-2 [최상·실행측정] 자료13(전개 계산기)은 관문을 못 넘는다 — 보류가 옳았다

같은 실행의 본 지표:
```
[KBO] 유효 173건   승자 일치율 55.0% [관문 통과]  · 기준선 홈고정 51.5% · elo 57.1%
        MAE 3.89점 (기준선 리그평균 3.03점)        ← 기준선보다 나쁘다
[NPB] 유효  89건   승자 일치율 44.8% [미달]        · 홈고정 55.2% · elo 47.2%
        MAE 2.80점 (기준선 2.13점)
[MLB] 유효 263건   승자 일치율 52.5% [미달]        · 홈고정 52.5% · elo 49.0%
        MAE 3.47점 (기준선 2.50점)
```
**세 리그 전부 기대득점 MAE 가 "양팀 모두 리그평균으로 찍기"보다 나쁩니다.**
KBO 는 방향 관문(55%)을 간신히 넘지만 elo(57.1%)보다 못하고,
MLB 는 홈고정과 **소수점까지 같습니다**(52.5% vs 52.5%).

## BT-3 [중] 표본 탈락률이 높다 — 얇은 선발이 통째로 빠진다
```
[KBO] 제외 {'리그평균 없음': 1, '선발 이전 등판 부족': 50}    → 173/224 (77%)
[NPB] 제외 {'리그평균 없음': 1, '선발 이전 등판 부족': 64}    →  89/154 (58%)
[MLB] 제외 {'선발 기록 없음': 9, '선발 이전 등판 부족': 106}  → 263/379 (69%)
```
**NPB 는 42% 가 탈락**합니다(6인 로테이션 · 등판 간격이 길다).
자료13 이 배선되면 그 경기들은 전개 값이 아예 없습니다.

## BT-4 [실측] `backtest_tempo.py` 자체는 잘 만들어졌다

- `build_sides` 가 교차 배선(홈 득점 = 상대 투수진 × 자기 타선)을 명시적으로
  분리하고 부호 뒤집힘 위험을 주석에 적었습니다 — `backtest_lambda.py` 가
  기록한 2026-08-26 실사고와 같은 유형을 미리 막습니다.
- 모든 피처가 `starts_at <` 로 잘립니다. elo 도 **하루 한 번만** 리플레이해
  as-of 를 지킵니다.
- `score_totals` 가 **관문을 실행 전에 선언**하고(Wilson 95% 하한이 세 기준선을
  전부 이길 것) 푸시 규약까지 못박았습니다.
- 정의를 재구현하지 않고 `variable_ref.quantiles`·`config`·`team_elo.compute`
  를 그대로 가져옵니다(사본 금지 준수).

## BT-5 [중·실측] λ 계열 백테스트 7개가 전부 실행 불가

```
--pickle 을 required=True 로 요구하는 도구:
  ablation_markets · backtest_lambda · backtest_pclaude · backtest_f5 ·
  calibrate_distribution · backtest_window · offense_metrics
+ ablation_lambda (경로 하드코딩, TL-17)

Statcast 원본 pkl:  로컬 없음 · 서버 없음 (검색 결과 전부 joblib 테스트 픽스처)
```
이 8개는 **30일치 Statcast 원본 pickle** 을 인자로 받아야 하는데, 그 파일이
어디에도 없고 **만드는 절차도 저장소에 없습니다**(`_fetch_statcast` 는
`statcast.refresh` 안에서만 불리고 집계만 Redis 에 넣습니다).

즉 λ·타선 지표·창 길이·F5·분포 형태에 대한 **모든 검증 도구가 지금 돌릴 수
없습니다.** `docs/MODEL.md §9` 가 인정한 "계수가 임의값"을 고치려면 이 도구들이
필요한데, 재료를 만들 경로가 끊겨 있습니다.

## BT-6 [실측] 백테스트 문서가 기록한 λ 실측치

`backtest_f5.py` docstring (2026-08-26 측정):
> *"우리 λ는 승패에서 51.5%(기준선 52.8% 미달), 토탈에서 57.0%(기준선 52.4%)다."*

`offense_metrics.py` docstring:
> *"현행 팀 30일 xwOBA는 실측 상관 +0.018로 사실상 무력했다(§8-3)."*

`backtest_window.py` docstring:
> *"30일 창(팀당 약 1,000타석)에서도 타선 지표 상관은 r≈0.025였다. 즉 **안정화가
> 부족해서 신호가 없는 게 아니다.** 팀 단위 집계 자체가 약하다."*

**세 문서가 각자 λ의 타선 축이 무력하다고 기록했고**, 12차에서 확인한
`lambda_poisson.json` 의 피처 중요도(`off_xwoba 0.0002`)가 같은 말을 합니다.
그런데 `config.exp_offense = 1.20` 은 *"Wharton: 타선 영향이 크다"* 라는 주석과
함께 그대로입니다.

---

# 14차 — tools/fit_elo.py 운영 실행 (walk-forward 홀드아웃)

`railway ssh` 로 스케줄러 컨테이너에서 실행. 도구가 **선언한 관문**:
"홀드아웃 logloss 를 세 리그 전부 낮춰야 변경 검토."

```
현행 운영값: decay=0.9 K=20 home_adv=15 · MIN_GAMES=10

[KBO] 224경기 · 홀드아웃 [156,224)
   현행 logloss=0.67561 brier=0.2339 방향=57.6%
   기준선(홈승률 상수) logloss=0.69557 brier=0.2439      ← 현행이 이긴다 ✅
[NPB] 154경기 · 홀드아웃 [107,154)
   현행 logloss=0.68476 brier=0.2352 방향=55.6%
   기준선           logloss=0.69312 brier=0.2393         ← 현행이 이긴다 ✅
[MLB] 379경기 · 홀드아웃 [265,379)
   현행 logloss=0.70757 brier=0.2571 방향=46.5%
   기준선           logloss=0.69933 brier=0.2531         ← 🔴 현행이 진다
   후보(1.00/K10)  logloss=0.70041 brier=0.2536 방향=48.2%  ← 후보도 진다
```

## 🔴🔴 FE-1 [최상·실행측정] MLB 자료12 는 홀드아웃에서 "홈승률 상수"보다 나쁘다

- logloss **+0.00824** 열세, brier **+0.0040** 열세, 방향 **46.5%**(동전 미만).
- 그리드 20조합 어디도 기준선을 못 넘는다. 최선 후보(decay=1.00,K=10)조차
  0.70041 > 0.69933.
- 13차 BT-1(방향 48.4%)과 **독립적인 두 번째 측정**이 같은 결론을 낸다.
  BT-1 은 전 구간 walk-forward, FE-1 은 앞 70% 로 고르고 뒤 30% 에서만 보고 —
  선택 편향을 뺀 상태에서도 진다.
- 그런데 `prompts.py:102` 는 자료12 를 **"기본 축"**이라고 판정 LLM 에 못박는다.
  MLB 는 슬레이트 대부분을 차지하는 리그다.

## FE-2 [중] 도구 자신의 관문이 "변경 없음"을 낸다 — 그러나 그건 파라미터 얘기다

세 리그 전부 낮추는 후보가 없으므로 관문상 **파라미터 변경은 없음**이 맞다.
하지만 관문이 답하지 않는 질문이 남는다 — *MLB 에서 이 축을 아예 쓸 것인가.*
도구는 "어떤 decay 가 나은가"만 묻게 설계돼 있고, "이 축이 기준선을 넘는가"는
출력에 있지만(기준선 행) 관문에는 없다.

## FE-3 [중] KBO·NPB 는 현행값이 그리드 최적이 아닌데도 홀드아웃에서 이긴다

선택 구간 1위는 KBO(0.95,K10)·NPB(0.90,K10)인데, 홀드아웃에서는 둘 다
현행(0.90,K20)이 더 낮다(KBO -0.00378, NPB -0.00177 로 후보가 악화).
→ 선택 구간 순위가 홀드아웃으로 이어지지 않는다 = **표본이 그리드 20조합을
가릴 만큼 크지 않다.** 도구가 이 불안정성을 표시하지 않는다(1위만 ★ 표시).

## FE-4 [하·설계] p폭이 여전히 좁다 — 도구 머리말의 진단이 실측으로 확인됨

홀드아웃 p폭: KBO 0.205 · NPB 0.150 · MLB 0.194.
즉 elo 가 만드는 최대 확률차가 ±10%p 안쪽이다. 시장은 MLB 내재확률 최대
75.8% 를 매긴다(선행 측정). 자료12 는 판정 프롬프트에서 "기본 축" 지위를
받지만 **실제로 실어 나르는 정보량은 ±10%p** 다.

---

# 15차 — 시장값 백필 이후 원장 재측정 (운영 DB, 경기당 1행)

`market_prob` 이 이제 **515/657** 채워져 있다(백필 완료). `odds` 36/657,
`edge_status` **0/657**(여전히 미배선), `confidence_llm` 컬럼 **없음**
(계획 변경3 미배포).

집계 조건: `hit IS NOT NULL AND void IS NOT TRUE`, `DISTINCT ON (game_id)`
최신 판정 1행 = **134경기**.

## 🔴🔴🔴 GATE-1 [최상·실행측정] 게이트가 가장 못 맞는 경기를 고른다

```
gate_result   n    적중    적중률
추천         15     5    33.3%   ← 사용자에게 나가는 것
가치주의       5     1    20.0%   ← 사용자에게 나가는 것
보드만        97    57    58.8%   ← 추천하지 않은 것
거부권탈락     17    10    58.8%   ← 게이트가 버린 것
```

- 추천+가치주의 **20건 6적중 = 30.0%**. 추천 안 한 114건은 **58.8%**.
- 목표는 58~60%. **추천만 골라내면 30%다.** 정확히 뒤집혀 있다.
- 거부권(확신도 하)이 버린 17건이 58.8% — **버린 게 더 잘 맞았다.**
- 전체 134경기는 **55.2%**(74/134). 즉 판정 자체보다 **선별이 손해를 만든다.**

## 🔴🔴 GATE-2 [최상] 괴리가 클수록 틀린다 — 그런데 게이트는 괴리를 '가치'로 읽는다

```
|divergence_pp|   n    적중률
  <5pp          39    53.8%
  5-10pp        32    56.3%
  10-20pp       29    44.8%   ← 시장에서 멀수록 나쁘다
  null          34    61.8%
```
동의/충돌:
```
시장과 같은 편  70건  54.3%
시장과 반대편   30건  46.7%
```
같은 100경기에서 **시장 56 · 우리 52**. 시장이 4건 더 맞는다.

`value_gate` 는 우리 p 가 시장 내재확률보다 높을 때를 '가치'로 본다.
실측은 그 방향이 **역**이다.

## 🔴🔴 GATE-3 [최상] 확률이 단조가 아니다 — p 가 정보를 싣고 있지 않다

```
우세측 p 구간      n   적중률   평균 p
홈측 0.50–0.55    27   70.4%   0.521
홈측 0.55–0.60    28   32.1%   0.570   ← 확률을 올렸는데 적중률이 반토막
홈측 0.60–0.65    18   44.4%   0.618
홈측 0.65–0.70     7   85.7%   0.656
원정 0.50–0.55     8   62.5%
원정 0.55–0.60    18   50.0%
원정 0.60–0.65    22   54.5%
원정 0.65–0.70     6   83.3%
```
추천 하한 0.58 은 **적중률이 가장 낮은 구간(0.55–0.60) 한가운데를 자른다.**
GATE-1 의 33.3% 는 이것의 직접 결과다.

## 🔴 GATE-4 추천 20건 전수 — 하나도 '상' 근거로 나가지 않았다

확신도 분포: 중 18 · 상 2 · 하 0. 즉 **거부권만 작동하고 확신도 상은
사실상 존재하지 않는다**(전체 134경기 중 '상' 2건).
```
확신도  n     적중률
중     115   53.9%
하      17   58.8%   ← 게이트가 탈락시키는 등급이 가장 높다
상       2   50.0%
```
계획서(2026-09-07)에 적힌 것과 **동일한 수치**다 — 그 계획의 변경3
(확신도 계산값 교체)은 **아직 배포되지 않았다**(`confidence_llm` 컬럼 부재).

## 🔴 GATE-5 종목별 — NPB 가 42.9%

```
mlb  84경기  57.1%
kbo  29경기  55.2%
npb  21경기  42.9%
```
NPB 는 13차·14차에서 자료12 가 기준선 미달로 나온 리그이면서,
발송 규율상 T-15/T-10 로 가장 촉박한 리그다.

## ⚠️ GATE-4 정정 — "확신도가 역정보"는 확정된 사실이 아니다

`app/engine/confidence.py` 머리말이 **이미 같은 절단 민감도를 기록**해 두었다.
```
134경기 전체    하 58.8%(17) > 중 53.9%(115)
100경기(시장O)  하 45.5%(11) < 중 52.9%( 87)
```
절단을 바꾸면 방향이 뒤집힌다. 위 GATE-4 는 "134경기 절단에서 그렇다"까지가
사실이고, **"확신도는 역정보다"로 읽으면 과대주장**이다. 여기 바로잡아 둔다.
(GATE-1 의 추천 33.3% vs 보드만 58.8% 는 절단과 무관하게 같은 표에서 나온다.)

## 🔴 GATE-6 [상] 채점된 134경기에 배당이 **0건**인데 '가치주의' 판정이 5건 있다

```
gate_result   n    odds 보유
보드만        97      0
거부권탈락     17      0
추천          15      0
가치주의        5      0     ← 배당 없이는 나올 수 없는 등급
```
`value_gate.classify` 는 `passes_value(p, odds)` 가 `False` 일 때만
`가치주의`를 낸다. `odds=None` 이면 `None` 을 돌려 **추천 자격을 유지**한다.
따라서 이 5건은 **판정 시점에는 배당이 있었는데 원장에는 남지 않았다.**
`_market_cols` 는 `odds` 를 `pick.get("odds")` 에서만 읽는다 —
`gate_result_of` 가 본 `pick` 과 원장에 넘어가는 `pick` 이 같은 dict 가
아니거나, 채점 시점에 재기록되며 지워졌다.
→ **가치 게이트의 판정을 사후에 재현할 수 없다.** 전 원장 657행 중 36행만
   `odds` 가 있고, 그 36행은 전부 미채점 구간이다.

## 🔴 CONF-1 [상] `confidence_probe` 의 M축이 36/36 전부 '상' — 변별력 0 (모듈 예고대로)

```
probe 보유 36행 (2026-09-07 이후만) / 전체 657행
M=상 36 · 분기점_미해결 0 · 결측 항목은 "자료3 오늘 타순" 21건뿐
```
- `material_gaps` 가 세는 다섯 항목(자료1·3·9·10·11·12) 중 **자료3 외에는
  한 번도 결측이 잡히지 않는다.** 자료12 는 13·14차에서 MLB 예측력이
  기준선 미달로 나왔는데도 "있음"으로만 세어진다 — 있고 없고만 보고
  쓸모는 보지 않는다.
- 자료3 결측 21/36(58%)은 **판정이 타순 전에 돈다**는 뜻이고, 이는 설계상
  의도된 잠정 카드 경로다. 즉 M축이 실제로 재는 것은 "타순이 떴는가" 하나다.

## 🔴 CONF-2 [중] `branch_unresolved` 는 "분기점 없음"과 "전부 해결"을 구분하지 못한다

```python
return bool(items) and not any(it.get("답") for it in items)
```
`items` 가 비면 False. probe 는 `분기점_미해결: false` 만 새기고 **항목 수를
기록하지 않는다.** 실측 36행 전부 false 인데, 그것이 "분기점을 안 물었다"인지
"물어서 다 풀었다"인지 원장만으로는 알 수 없다 — 12차에서 잰
"대조성공 18/638" 과 대조할 수단이 없다.
→ `분기점수`를 함께 새기면 한 칸으로 구분된다.

## 🔴 LED-1 [상] 경기당 판정 4.9회 — 재판정 최대 16회

```
rejudge_count  0:160  1:148  2:117  3:78  4:50  5:30  6:16  7:12
               8:8  9:8  10:8  11:7  12:6  13:4  14:3  15:1  16:1
전체 657행 / 종료 159경기
```
한 경기가 **17번** 판정됐다. `_SIG_FIELDS` 가 바뀔 때마다 새 행이 생기는
설계인데, 무엇이 바뀌어 재판정이 걸렸는지 원장에 사유 칸이 없다.
LLM 호출 비용과 판정 안정성(`JUDGE_STABILITY` 문서의 전제)이 모두 여기에 걸린다.

## ❌ GATE-6 취소 — 제 오탐이었다

날짜별로 재보니 `odds` 는 **2026-09-07 부터만** 기록된다.
```
date        n    odds  market  probe
08-31      58     0      0      0
09-02      88     0     78      0
09-05      96     0     96      0
09-06     190     0    190      0
09-07      36    36     36     36     ← 시장·확신도 배선이 들어간 날
```
`가치주의` 5건은 09-03~09-06 행이다 — 그 시점 INSERT 가 `odds` 컬럼을
쓰지 않았을 뿐, 판정 시점 메모리의 `pick["odds"]` 는 있었다.
"게이트 판정을 재현할 수 없다"는 **과거 행에만** 해당하고, 09-07 이후로는
재현된다. 제가 날짜를 나눠 보지 않고 결론을 냈다.

## 🔴 LED-2 [상] 09-06 하루에 원장 190행 — 같은 날 슬레이트가 5배로 불었다

```
09-02  88 · 09-03  41 · 09-04  79 · 09-05  96 · 09-06 190 · 09-07 36
```
09-06 은 하루 슬레이트가 30~40경기인데 **190행**이다. `_SIG_FIELDS`
(p_home·favored·confidence·lineup_status·gate_result·model) 중 하나만
달라도 새 행이 생긴다. 09-06 은 GROQ 100% 실패로 사슬이 계속 갈아탄
날이고(9차 측정: groq:fail 102), **`model` 이 바뀔 때마다 재판정 행이
새로 쌓였다**는 가설이 성립한다. 즉 프로바이더 장애가 원장 표본을 부풀린다.
경기당 1행으로 접지 않은 집계는 그만큼 09-06 에 가중된다.

## 🔴 LED-3 [상] 2026-09-07 슬레이트는 추천이 **0건**이다

```
09-07  보드만 31 · 거부권탈락 5 · 추천 0 · 가치주의 0 · 엣지 0
```
자료12(elo)를 "기본 축"으로 넣고 시장 배선을 켠 첫날, 하루 종일
사용자에게 나간 추천이 **없다.** 발송 규율의 "조용한 0은 결함이다"가
카드 미발송에는 걸리지만 **추천 0건에는 걸리지 않는다** — 워치독 16종에
`추천 0건`을 보는 코드가 없다.

## 🔴🔴 LED-4 [최상·전수추적] 한 경기 17회 판정 — p 가 ±0.06 로 떨며 재판정을 자가생산한다

game_id=1719 (09-06) 전 이력. 10시간 동안 17행:
```
21:16 p=0.550 gemini  ls=none      rejudge 0
22:16 p=0.560 gemini  ls=none              1
23:34 p=0.550 gemini  ls=none              2
00:23 p=0.560 gemini  ls=none              3
01:11 p=0.550 gemini  ls=none              4
02:20 p=0.600 fable   ls=none              5
02:27 p=0.570 fable   ls=none              6
02:28 p=0.570 gemini  ls=none              7
02:38 p=0.570 fable   ls=none              8
02:43 p=0.550 gemini  ls=none              9
05:02 p=0.540 gemini  ls=none             10
06:17 p=0.550 gemini  ls=none             11
06:21 p=0.540 gemini  ls=none             12
06:34 p=0.550 gemini  ls=none             13
07:14 p=0.500 opus    ls=confirmed        14
07:16 p=0.550 gemini  ls=none             15   ← 🔴 확정 라인업이 다시 none 으로
07:32 p=0.560 gemini  ls=confirmed        16
```
셋을 동시에 보여준다.

**(a) 판정이 흔들린다.** 같은 모델(gemini)·같은 라인업 상태(none)에서
p 가 0.540~0.600 사이를 오간다. 폭 6.0%p. 우세는 늘 home 이라
`tools/stability_smoke` 는 **통과시킨다** — 그 게이트는 `set(sides)` 크기만
보고 산포는 출력만 하고 막지 않는다(`if len(set(sides)) > 1: return 1`).
그런데 6.0%p 폭은 추천 하한 0.58 을 **넘었다 안 넘었다** 한다.

**(b) 그 흔들림이 원장 행을 자가생산한다.** `_SIG_FIELDS` 의 `p_home` 은
1e-9 정확도로 비교한다(`_same_judgement`). 0.001 만 달라도 새 이력 행이다.
09-06 190행 · 09-05 96행 · 09-04 79행이 이렇게 쌓였고, 그만큼 **LLM 을 다시
불렀다.**

**(c) 라인업 상태가 뒤로 간다.** rejudge 14 에서 `confirmed`, 15 에서 다시
`none`, 16 에서 다시 `confirmed`. 확정 라인업은 되돌아갈 수 없는 상태인데
1분 간격으로 왕복했다. 07:14 opus(확정 최종 판정)와 07:16 gemini(예비)가
**같은 경기를 서로 다른 재료로 동시에 덮어쓰고 있다** — 2단계 판정
(예비 무료 → 확정 유료)의 순서가 지켜지지 않는다.

모델 분포도 그 혼선을 보여준다.
```
09-06 전체:  gemini 152 · opus 24 · fable 14
원장 전체:   sonnet 361 · gemini 215 · nemotron 26 · opus 24 · fable 14
             · grok 9 · minimax 8
```
같은 슬레이트가 최대 3개 모델에게 판정된다(`models` 컬럼 count DISTINCT = 3).

## 🔴🔴 LED-5 [최상·코드확정] `lineup_status` 역행 경로 — 세 곳 중 한 곳만 가드가 없다

`lineup_status` 를 쓰는 자리는 셋이다.

| 위치 | 가드 |
|---|---|
| `pipeline.py:633/635/643` (`merge_source_data` 계열) | ✅ `_lu_ok()` 로만 confirmed 승격 · `elif prev == "none"` 조건. prev 가 confirmed 면 어느 분기도 안 걸려 **유지**된다 |
| `pipeline.py:693` `promote_lineup_status` | ✅ `if prev not in ("none","predicted"): return False` — 역행 차단 |
| **`pipeline.py:5514` `rejudge_after_lineup`** | 🔴 **`jg["lineup_status"] = lineup["status"]` 무조건 대입** |

세 번째가 `lineup_poll_30m` · `asia_pregame_5m` · `npb_pregame_2m` ·
`mlb_pregame_5m` 이 부르는 경로다. 폴이 그 틱에 타순을 못 읽어
`status="none"` 을 들고 오면 **확정을 none 으로 되돌린다.**

LED-4 의 실측 이력이 정확히 그 모양이다.
```
07:14 ls=confirmed  (opus, 유료 최종)
07:16 ls=none       ← 2분 뒤 역행
07:32 ls=confirmed
```
같은 파일 605~624행 주석이 **이 결함의 반대 방향**(가짜 확정으로 유료 최종이
타순 0명으로 나감, P0 실사고 2026-09-05)을 이미 기록해 두었다. 그때 승격
쪽에는 가드를 넣었는데, **강등 쪽은 그대로 남았다.**

파급:
- `pick_state`/`pick_state_label` 이 함께 되돌아간다(5527행) → 카드가
  "확정"에서 "잠정"으로 되돌아간다.
- `_SIG_FIELDS` 에 `lineup_status` 가 있어 **왕복할 때마다 원장 행이 늘고
  LLM 을 다시 부른다** — LED-4(b) 의 증폭원이다.
- `sync_lineup_status` 는 DB 를 `'confirmed'` 로만 올린다(786행,
  `WHERE lineup_status <> 'confirmed'`). 즉 **캐시는 none 으로 내려가고 DB 는
  confirmed 로 남아** 두 저장소가 갈린다 — 09-02 NPB 4경기 사고와 같은 종류의
  불일치가 반대 방향으로 생긴다.

## 🔴🔴 LED-6 [최상·DB증거] 라인업 역행이 **DB에 13건 남아 있다**

```sql
SELECT sport, lineup_status, count(*) FROM games
 WHERE lineup_confirmed_at IS NOT NULL AND lineup_status <> 'confirmed'
```
```
mlb  predicted  13
```
`lineup_confirmed_at` 은 `lineups.py:257` 에서 **`$2='confirmed'` 일 때만**
찍힌다. 즉 이 13경기는 한때 확정이었다가 **predicted 로 내려갔다.**
추론이 아니라 표에 남은 흔적이다.

원인 라인은 같은 UPDATE 다.
```sql
UPDATE games SET lineup_status = $2,
  lineup_confirmed_at = CASE WHEN $2='confirmed' THEN now() ELSE lineup_confirmed_at END,
  ...
```
`$2` 를 **무조건 대입**한다. `refresh_mlb_lineup` 은 `parsed["confirmed"]`
(양팀 타순 9명)이 아니면 `predicted` 를 낸다 — statsapi 가 한 틱 비면
확정이 예정으로 내려간다. 반대 방향인 `sync_lineup_status:785` 에는
`WHERE lineup_status <> 'confirmed'` 가드가 있는데 여기엔 없다.

### LED-6b `lineup_confirmed_at` 은 KBO·NPB 에서 항상 NULL

```
kbo confirmed 31건 · npb confirmed 32건 → lineup_confirmed_at 전부 NULL
```
아시아 야구는 `sync_lineup_status` 로 확정되는데 그 UPDATE 는
`lineup_status` 와 `updated_at` 만 쓴다(`pipeline.py:785`). 따라서
**"언제 확정됐나"를 아시아 리그에서는 알 수 없고**, 위 역행 탐지 쿼리도
KBO·NPB 에는 작동하지 않는다. LED-4 의 KBO game=1719 역행이 DB 흔적을
남기지 못한 이유다.

### LED-6c 종료 경기의 라인업 확정률
```
sport  confirmed  predicted  none    확정률
kbo       31         0       193    13.8%
npb       32        15       107    20.8%
mlb      142        13       224    37.4%
soccer     0         0        72     0%
```
KBO 종료 224경기 중 **193경기(86%)가 타순 없이 판정**됐다. 발송 규율은
"타순이 뜨면 재판정해 수정 카드"를 전제하는데, 실제로는 대부분 잠정에
머문다. `confidence.probe` 의 M축이 자료3 결측만 잡는 것(CONF-1)과 같은
사실의 다른 단면이다.

## ❌ LED-6c 정정 — "KBO 86% 가 타순 없이 판정" 은 제 오탐이다

전 기간 집계에는 크롤러 도입 **이전의 소급 적재분**이 섞여 있었다.
최근 10일로 잘라 다시 재면 이렇다(종료 경기, 확정/전체).
```
날짜     kbo      npb      mlb
08-29    0/5      6/6     11/14
08-30    2/2      1/6     16/17
09-01    5/5      6/6     12/12
09-02    5/5      1/5     15/15
09-03    4/4      2/2     12/15
09-04    5/5      5/5      8/9
09-05    5/5      6/6      1/16   🔴
09-06    5/5      5/5     11/15
09-07     —        —      14/15
```
KBO 는 09-01 이후 **5/5 로 매일 100%** 다. LED-6c 를 취소한다.

대신 두 개의 진짜 구멍이 보인다.
- **MLB 2026-09-05: 16경기 중 확정 1건.** 코드 주석(pipeline.py:610~623)이
  기록한 P0 실사고("09-05 MLB 13경기가 통째로 가짜 확정")와 같은 날이다.
  가드를 넣어 가짜 확정은 막았지만, 그날 **진짜 확정도 15건 못 받았다**.
- **NPB 08-30 1/6 · 09-02 1/5.** Yahoo `/top` 공시(T-30)와 재판정 마감(T-10)
  사이 20분 창을 놓치면 그 경기는 끝인데, 그 실패가 워치독에 잡히지 않는다
  (`W-CARD-LATE` 는 카드 지연을, `W-SEND-PENDING` 은 미발송을 본다 —
  "확정 못 받고 잠정으로 끝났다"를 세는 코드는 없다).

---

# 16차 — `.claude/hooks/` 자기검증 7종 실행

실행 조건: 작업트리 클린 · `last-green` 신선(2521 passed) · KST 06:54
(슬레이트 창 밖) · HEAD 가 임시 커밋 아님. 즉 **배포해도 되는 상태**다.

```
selftest.sh   통과 12 · 실패 1   exit 1
selftest2.sh  통과  5 · 실패 5   exit 1
selftest3.sh  통과  5 · 실패 2   exit 1
selftest5.sh  통과  5 · 실패 0   exit 0
selftest7.sh  통과  6 · 실패 0   exit 0
```
(selftest4·6 은 저장소·마커를 변조하므로 이번 감사에서는 돌리지 않았다.)

## 🔴🔴 HK-1 [최상] 자기검증이 **정상 상태에서 실패한다** — 8건 전부 오탐

실패한 8건은 전부 같은 모양이다: "배포 명령은 무조건 deny 여야 한다"고
단언한다.
```
selftest2  실행 (tools/ 접두)   기대=deny  결과=allow
           실행 (./ 접두)       기대=deny  결과=allow
           실행 (bash 경유)     기대=deny  결과=allow
           railway up 실행      기대=deny  결과=allow
           && 뒤 실행           기대=deny  결과=allow
selftest3  heredoc 종료 후 실제 배포  기대=deny  결과=allow
           실제 배포 실행            기대=deny  결과=allow
selftest.sh 창 밖 배포는 다른 게이트로 기대=deny 결과=allow
```
그런데 `guard-bash.sh` 의 배포 게이트는 **조건부**다 — 슬레이트 창(17~22시)
· 미커밋 · WIP 커밋 · 마커 불일치, 넷 중 하나라도 걸려야 막는다. 지금은
넷 다 통과하므로 **allow 가 정답이고, 훅은 정상 동작 중이다.**
`bash -x` 로 확인:
```
+ H=6 ; '[' 6 -ge 17 ']'                      ← 성역 아님
++ git status --porcelain ; '[' -n '' ']'      ← 클린
+ grep -qiE '^(wip|fixup!|…)' (불일치)          ← WIP 아님
+ '[' dab4189f… '!=' dab4189f… ']'             ← 마커 일치
+ exit 0
```
즉 **테스트가 틀렸다.** 배포 가능한 상태를 결함으로 보고한다.

파급이 크다.
- `CLAUDE.md` 가 `.claude/hooks/selftest.sh` 를 명령어 목록에 올려 두었다.
  그 문서대로 돌리면 **healthy 한 저장소에서 exit 1 이 나온다.**
- 이 저장소가 스스로 적은 원칙이 정확히 이것을 금한다 — selftest3 머리말
  *"문서를 쓰는 것만으로 발동하는 게이트는 곧 꺼진다"*, selftest7 머리말
  *"헛경보가 쌓이면 훅은 꺼진다."* 그 규칙이 자기 자신에게는 적용되지 않았다.
- 진짜 게이트 고장(예: 마커 검사 로직이 깨져 늘 allow)이 생겨도 **같은
  🔴 로 보이므로 구분되지 않는다.**

고치는 방향은 상태를 만들고 재는 것이다 — selftest.sh 의 커밋 게이트 절이
이미 그렇게 한다(마커를 지우고/낡게 만들고/신선하게 만들어 각각 확인).
배포 절만 그 방식을 안 쓴다.

## 🔴 HK-2 [중] `selftest4.sh` 는 저장소를 변조하는데 **trap 이 없다**

```bash
git commit -q --allow-empty -m "probe(자동): 서명 불변 확인"
B=$(worktree_sig)
git reset --soft HEAD~1
...
printf '\n' >> README.md      # 추적 파일 수정
D=$(worktree_sig)
cp "$BAK" README.md
```
중간에 실패·중단되면 **빈 커밋이 HEAD 에 남거나 README.md 가 수정된 채
방치**된다. `selftest7.sh` 는 `trap 'rm -rf "$TMP"' EXIT` 를 쓰는데
selftest4 에는 없다 — 가장 위험한 스크립트에만 없다.

## 🔴 HK-3 [하] `selftest5.sh` 의 printf 인자 순서가 뒤집혀 있다

```bash
printf "  %s %-40s 기대=%-5s 결과=%s\n" "$1" "$m" "$2" "$got"
```
다른 6개는 `"$m" "$1"` 순서다. 그래서 출력이 이렇게 나온다.
```
  reset --hard (클린) ✅                    기대=allow 결과=allow
```
이름과 체크마크가 자리를 바꿔, 실패해도 🔴 가 이름 뒤에 숨는다.

## ✅ HK-4 정상 확인 — 위험 명령·커밋 게이트는 살아 있다

```
rm -rf app/            → deny (exit 2)
rm -rf 스크래치패드      → allow
git push --force main  → deny
마커 없음 → 커밋        → deny
낡은 마커 → 커밋        → deny
신선한 마커 → 커밋      → allow
heredoc 안의 위험 문자열 3종 → allow (오탐 없음)
git reset --hard (클린) → allow · (dirty 면 deny — 이번엔 클린이라 미검증)
claim-gate 6종 전부 정상
```
`worktree_sig` 도 정상이다. (제가 처음 zsh 에서 `source lib.sh` 로 직접
불러 `da39a3ee…`(빈 문자열의 SHA-1)를 받고 "상수를 돌려준다"고 볼 뻔했는데,
zsh 에는 `BASH_SOURCE` 가 없어 `REPO` 가 엉뚱한 경로로 잡힌 탓이었다.
훅이 bash 로 실행될 때는 `dab4189f…` 로 정상 산출된다.)

---

# 17차 — `yahoo_npb.py` 후반 · `game_match.apply_result`

## 🔴🔴 NPB-1 [최상·코드확정] `starts_at` 은 한 번 새겨지면 **영원히 고쳐지지 않는다**

`game_match.apply_result` 의 두 경로 모두 `starts_at` 을 쓰지 않는다.
```sql
_UPDATE: UPDATE games SET status=$2, home_score=COALESCE(...), away_score=..., updated_at=now()
_INSERT: ... ON CONFLICT (sport, ext_id) DO UPDATE SET
           status=EXCLUDED.status, home_score=COALESCE(...), away_score=..., updated_at=now()
```
그런데 `yahoo_npb.upsert_schedule` 은 개시 시각을 못 읽으면 **18:00 JST 를
지어 넣는다**(`hhmm = "18:00"`). 주석은 이 폴백이 안전하다고 적는다 —
*"타임스탬프는 매칭용 18:00 폴백을 남긴다. MATCH_WINDOW_HOURS=20 이라
같은 날 어느 시각이든 기존 행을 찾아 갱신한다."*

**매칭에는 안전하지만 저장된 시각은 틀린 채로 굳는다.** 뒤에 정확한 시각을
읽어도 UPDATE 문에 `starts_at` 이 없어 반영되지 않는다.

시각을 못 읽는 조건은 코드가 스스로 적어 두었다 — *"야후는 경기가 시작되면
시각 칸을 스코어·이닝으로 바꾼다."* 실행으로 확인했다(운영 컨테이너에서
`parse_schedule` 직접 호출):
```
2026-09-05 (지난날) 6경기 전부  hhmm=None  state=started
2026-09-06 (지난날) 6경기 전부  hhmm=None  (1건 cancelled)
2026-09-08 (오늘)   6경기 전부  hhmm=18:00 state=scheduled
```
즉 **경기가 시작한 뒤 처음 본 경기는 무조건 18:00 으로 박힌다.**

운영 DB 실측:
```
NPB starts_at (JST):  18:00 163건 · 17:00 1건 · 16:00 1건   (총 165)
NPB 행 생성 시각(JST): 05시 73 · 09시 6 · 11시 52 · 13시 30 · 14시 4
```
**34건이 13~14시 JST 에 처음 생성됐다.** 14:00 개시 경기라면 그 시점엔 이미
시작했고, 그 행들은 폴백 18:00 을 받은 뒤 영원히 그대로다.
(163/165 가 18:00 인 것이 전부 폴백 탓이라고 단정하지는 않는다 — 그 날의
야후 원문을 사후에 재현할 수 없다. 단정할 수 있는 것은 **경로가 열려
있다는 것**과 **한 번 틀리면 고칠 길이 없다는 것**이다.)

파급:
- 발송 트리거는 전부 `starts_at` 상대다(T-180 창 · T-30 보장선 · NPB 풀
  T-15 · 경량 T-10). 시각이 4시간 밀리면 **그 경기의 카드는 경기가 끝난
  뒤에 나갈 준비를 한다.**
- `market_baseline` 의 CLOSE/SEND 스냅샷 선택, `backtest_tempo`·`fit_elo` 의
  as-of 정렬이 모두 `starts_at` 을 기준으로 한다.
- `pregame_push.still_upcoming` 도 이 값을 본다 — 이미 시작한 경기를
  "예정"으로 보게 된다. 2026-09-06 실사고(토요일 13:00 종료 경기가
  "오늘 18:00 예정"으로 슬레이트에 들어옴)에서 **status 는 고쳤지만
  starts_at 은 고치지 않았다.**

KBO 는 같은 문제가 없다 — 실측 시각 분포가 18:30/18:00/19:00/17:00/14:00 로
갈려 있어 파서가 실제 시각을 읽고 있다.

## ✅ NPB-2 정상 확인 — 표 순서 혼동은 없다

`parse_game` 은 `/top` 을 읽어 `starters[0] → home_pitcher`,
`parse_batting_stats` 는 `/stats` 를 읽어 `found[0] → away`.
`YahooNPBClient.stats` 의 docstring 이 *"`/top` 打順과 표 순서가 반대다
(실측 2026-08-28)"* 라고 적어 둔 것과 일치한다. 서로 다른 페이지이므로
모순이 아니다. (앞 세션에서 의심했다가 철회한 것과 같은 결론.)

## ✅ NPB-3 정상 확인 — ERA 표본 가드

`MIN_STARTER_APPEARANCES=3` · `MAX_CREDIBLE_ERA=15.0` 로 1등판 ERA 189.00
같은 값을 λ 에 넣지 않고 **버린다**(리그 평균으로 대체하지 않는다).
"없는 것을 있는 척하지 않는다"는 규칙이 코드로 지켜진 드문 예다.

---

# 18차 — `dispatch_stats` 발송 가동률

운영 Redis 실측 (2026-09-08 06:50 KST):
```
dispatch:mlb:2026-09-06  sent 16 · revised  9 · unchanged  78 · card_cap  55 · window_not_open  42
dispatch:mlb:2026-09-07  sent  9 · revised  4 · unchanged 204 · card_cap 128 · window_not_open 115
                                                              · card_reserved 1
```
(KBO·NPB 키가 없는 것은 결함이 아니다 — 09-07 은 두 리그 휴식일이고 TTL 이
30시간이라 09-06 분이 09-08 00:00 에 만료됐다. 확인 후 제외한다.)

## 🔴🔴 DSP-1 [상] 발송률의 분모가 **경기가 아니라 폴링 틱**이다 — 100% 는 구조상 불가능하다

`dispatch_stats.summary` 정의대로 계산하면 09-07 MLB 는 이렇다.
```
target    = 전체 − NOT_TARGET(window_not_open 115)
          = 9 + 4 + 204 + 128 + 1 = 346
delivered = sent 9 + revised 4 + unchanged 204 = 217
발송률     = 217/346 = 62.7%
미발송     = card_cap 128 (37.0%) · card_reserved 1
```
그런데 09-07 MLB 슬레이트는 **15경기**다. 346 은 경기 수가 아니라
`mlb_pregame_5m` 이 5분마다 각 경기를 훑으며 남긴 **틱 수**다.

- 카드 2장을 다 채운 경기는 **그 뒤 모든 틱마다** `card_cap` 을 한 번씩
  적는다. 즉 미발송 건수가 **폴링 주기에 비례해 늘어난다.**
- 09-07 에 MLB 폴링이 `CronTrigger(hour="5-11")` 에서 `IntervalTrigger(5분)`
  로 바뀐 날이다(scheduler.py:1934 주석). 그래서 09-06 55건 → 09-07 128건 으로
  **틱이 2.3배 늘자 '미발송'도 2.3배 늘었다.** 발송이 나빠진 게 아니다.
- 반대로 `unchanged` 도 틱마다 쌓여 분자를 부풀린다(78 → 204).

CLAUDE.md 는 *"목표는 발송률 100%이고, 미발송은 전건에 사유가 붙어야 한다"*
고 적는다. 지금 정의로는 **100% 가 나올 수 없다** — 정상 운영에서 card_cap 이
반드시 쌓이기 때문이다. 지표가 목표와 같은 단위가 아니다.

경기 단위로 세려면 `hincrby` 대신 경기별 최종 결과 1건만 남겨야 한다
(예: `HSET dispatch:{sport}:{date}:games {game_id} {outcome}` 로 덮어쓰기).

## ⚠️ DSP-2 [중] `card_cap` 은 사유 이름이 결과를 오해하게 만든다

`REASON_KR["card_cap"] = "카드 2장 상한 도달"`. 사람이 읽으면 "보내야 하는데
못 보냈다"로 읽힌다. 실제 의미는 **"두 장을 이미 다 보냈다"** — 성공이다.
`NOT_TARGET` 에 들어가야 할 값이 `misses` 에 들어가 있다.
`unchanged` 는 같은 이유로 `DELIVERED` 에 넣어 두었는데(주석이 그 이유를
명시한다), `card_cap` 만 반대로 분류돼 있다.

⚠️ DSP-2 단서: `card_cap` 을 무조건 `NOT_TARGET` 으로 옮기라는 뜻은 아니다.
두 장을 정상적으로 다 보낸 뒤의 틱이면 성공이지만, **의미 있는 3번째 수정이
상한에 막힌 경우**는 진짜 미발송이다. 지금 코드는 둘을 같은 이름으로 세므로
**구분 자체가 불가능하다.** 구분하려면 "이미 보낸 두 장과 내용이 같은가"를
함께 기록해야 한다 — `card_reserved` 가 그 발상으로 만들어졌으므로 설계는
이미 있다.

---

# 19차 — `lineup_season.py` (567줄) 전량

## 🔴 LS-1 [상] `lineup_season` 은 **어디서도 호출되지 않는다** — 문서가 반대로 적고 있다

`app/engine/CLAUDE.md:64` 는 이렇게 적는다.
> 수집기(`starter_season.py`·`lineup_season.py`)는 **지우지 않았다** —
> `variable_ref` 가 자료10 참조에 쓴다.

실제로 `variable_ref.py` 가 import 하는 것은 `starter_season` 하나다.
```
app/engine/variable_ref.py:264
  from app.collectors.starter_season import fetch_asia, fetch_mlb, lookup_asia
```
`lineup_season` 전수 참조 (app/ · tools/ · tests/):
```
$ grep -rn "lineup_season" app/ tools/ tests/ --include='*.py'
  → 전부 app/collectors/lineup_season.py 자기 자신 (로그 문자열·캐시 키)
```
즉 `attach()`·`fetch_kbo()`·`fetch_npb()`·`fetch_mlb()`·`team_line()`·
`lookup()` **전부 죽어 있다.** 567줄, 그중 KBO 기록실 ASP.NET 폼 POST(20요청)와
NPB `npb.jp/bis` 스크레이퍼 12요청이 포함된다.

이것이 문제인 이유는 "쓸모없는 코드"라서가 아니다.
- **문서가 근거로 든 사실이 틀렸다.** 이 파일을 지워도 되는지 판단할 때
  다음 세션은 CLAUDE.md 를 믿고 남길 것이다. CLAUDE.md 스스로 금지한
  "사본" 이 정확히 이 모양이다.
- `tests/test_season_ban.py` 가 자료8 부착을 잠그고 있는데, **잠글 대상이
  이미 배선돼 있지 않다.** 테스트가 무엇을 지키는지 실제로는 알 수 없다.
- KBO 기록실 페이지 구조가 바뀌면 `parse_kbo` 가 헤더 불일치 로그를 내지만,
  **아무도 부르지 않으므로 그 로그도 안 난다** — 소스 드리프트 감시
  (`W-SOURCE-DRIFT`)의 사각이다.

## 🔴 LS-2 [하] KBO 만 `AVG` 를 **문자열**로 넣는다 — 리그별 타입이 다르다

```python
# fetch_kbo
if page == "Basic1":
    blk["AVG"] = cs[3]          # ← 문자열 그대로
for label, idx in cols.items():
    v = _f(cs[idx])             # ← 나머지는 float
```
```python
# fetch_npb
for label, idx in _NPB_IDX.items():   # AVG 포함
    v = _f(cs[idx])                   # ← 전부 float
```
`fill_ops`·`team_line` 은 `_num()` 을 거치므로 지금은 터지지 않는다.
그러나 이 dict 가 그대로 판정 프롬프트로 나가면 KBO 는 `"0.312"`,
NPB 는 `0.312` 로 **같은 재료가 리그마다 다른 모양**이 된다.
(현재는 LS-1 때문에 아무 데도 안 나가므로 실피해는 없다.)

## ⚠️ LS-3 [하] `lookup` 은 이적 선수를 조용히 버린다

```python
if team and blk.get("team") and blk["team"] != team:
    return {}
```
동명이인 방지 의도는 맞지만, 시즌 중 이적한 선수는 표에 이전 팀으로 남아
있어 **이름이 맞는데도 빈 dict** 를 받는다. 이 경우 `hit` 카운터가 줄어
로그의 매칭률만 낮아지고, 왜 낮은지는 기록되지 않는다.

## ✅ LS-4 정상 확인 — 누수 가드와 투수 타순 제외

- `attach(replay=True)` 는 시즌 라인을 **붙이지 않고** `lineup_season_suppressed`
  를 새긴다. 끝난 경기를 재현할 때 그 경기가 시즌 집계에 포함되는 누수를 막는다.
- `is_pitcher_slot` 이 `(投)`·`(투수)`·`(P)` 세 표기를 모두 본다.
  주석이 실사고(2026-09-02 요미우리 戸郷 翔征(投) 를 놓쳐 센트럴 6경기 전부
  타자 9명으로 셈)를 근거로 남겨 두었다.
- `team_line` 은 **타석 가중** OPS 이고 재료가 없으면 빈 dict 다 (0.000 을
  만들지 않는다).

## ⚠️ LS-1 단서 정정 — `test_season_ban.py` 는 제대로 잠그고 있다

위에서 "테스트가 무엇을 지키는지 알 수 없다"고 쓴 것은 과했다. 읽어 보니
그 파일은 **배선의 부재 자체**를 잠근다 — 그것이 맞는 방식이다.
```python
test_render_does_not_pass_season_payloads      # matchup.py 원문에 심볼 없음
test_pipeline_no_longer_attaches_season_lines  # pipeline.py 에 "lineup_season import attach" 없음
test_rendered_prompt_carries_no_season_numbers # 옛 캐시가 남아도 렌더 결과에 안 샌다
```
즉 **`lineup_season` 이 미배선인 것은 의도이고 테스트가 그 상태를 지킨다.**
LS-1 에서 유효하게 남는 것은 하나뿐이다 — `app/engine/CLAUDE.md:64` 의
근거 문장("`variable_ref` 가 쓴다")이 **`lineup_season` 에 대해서는 사실이
아니다.** `starter_season` 에만 해당한다.

관련해서 눈에 걸리는 것: `variable_ref` 가 자료10 해결에 쓰는 값의 이름이
`opp_starter_season_era` 다 — **시즌 ERA** 다. 대원칙("시즌 집계표는 판정
입력 금지")과 자료10 예외의 경계가 이 한 필드에 걸려 있는데, 앞서
(변수해결 절) 측정한 대로 **키 대소문자 불일치로 26/26 프롬프트에서 null**
이라 지금은 프롬프트에 실린 적이 없다. 즉 경계 논쟁이 실전에서 발생한 적이
없고, 그 버그를 고치는 순간 이 대원칙 판단이 필요해진다.

---

# 20차 — `app/bot/` (봇 대화 경로)

## 🔴🔴🔴 BOT-1 [최상·실행측정] KBO·NPB 는 **봇으로 물어볼 방법이 없다**

이 프로그램의 첫 줄은 *"KBO·NPB·MLB 자동 발송"* 이다. 그런데 대화 경로에서
두 리그에 도달하는 길이 하나도 없다.

실행 측정 (`route_query` · `find_team` · `find_league` 직접 호출):
```
'KBO'          → ('full', None)   → parse_intent_mock → sport='mlb' → **MLB 카드**
'NPB'          → ('full', None)   → **MLB 카드**
'오늘 KBO 어때'  → ('full', None)   → **MLB 카드**
'KBO 전체'      → ('full', None)   → **MLB 카드**
'일본프로야구'    → ('league','j1')  → 🔴 **J1 축구 카드**
'한국프로야구'    → find_league='kleague1' → 🔴 **K리그1 축구 카드**
```
팀 이름도 전부 막혀 있다.
```
한화·한화 이글스·LG·두산·기아·롯데·SSG·키움·삼성·NC·KT   → find_team = None (10/10)
요미우리·한신·소프트뱅크·니혼햄·야쿠르트·주니치·오릭스        → find_team = None (7/7)
다저스 → ('mlb','Los Angeles Dodgers')  ✅
맨시티 → ('soccer','Manchester City')   ✅
```

원인은 사전이 **두 벌인데 한 벌만 채워져 있는 것**이다.
```python
# app/bot/aliases.py
KR_TEAM_NAMES  : 영문 → 한국어 표기 (출력용)  … KBO 10팀·NPB 12팀 **있음** (206~239행)
TEAM_ALIASES   : 한국어 → (종목, 영문) (조회용) … 171개, **MLB + 축구뿐**
find_team()    : TEAM_ALIASES 만 본다 (113행)
```
즉 **표시용 사전에는 넣고 조회용 사전에는 안 넣었다.**

명령어도 없다. 등록된 핸들러는 `/start · /mlb · /soccer · /health ·
/checklist · /today · /픽` 이고 `/kbo`·`/npb` 는 존재하지 않는다.
`/today` 는 `_card_flow(message, "mlb", None)` 이라 **MLB 전용**이다.

그리고 코드가 스스로 모순을 만든다 — `_format_team_reply` 는 KBO·NPB 카드
하단에 이렇게 안내한다.
```python
_SLATE_CMD = {"mlb": "/mlb", "soccer": "/soccer", "kbo": "KBO", "npb": "NPB"}
easy += f"\n\n전체 슬레이트는 '{_cmd}'라고 물어보세요"
```
그 안내대로 "KBO"라고 치면 **MLB 슬레이트가 온다.** (게다가 그 카드에
도달할 경로 자체가 팀 질의뿐인데 KBO 팀 별칭이 없어 도달할 수 없다 —
이 분기는 실행된 적이 없을 가능성이 높다.)

## 🔴 BOT-2 [상] `/픽`·"오늘 추천"·"🎯 오늘 전체 추천픽" 버튼도 MLB·축구만 본다

```python
async def answer_full_reco() -> str:
    for sport in ("mlb", "soccer"):        # ← KBO·NPB 없음
        a = await load_analysis(sport, default_date(sport))
```
자동 발송의 주력 두 리그가 "오늘 전체 추천"에서 빠진다.

## 🔴 BOT-3 [중] `game:` 콜백도 두 종목만 뒤진다

```python
for sport in ("mlb", "soccer"):
    analysis = await load_analysis(sport, default_date(sport))
```
KBO·NPB `game_id` 로는 못 찾아 `expired_text("soccer")` — *"분석이 만료됐어요.
/soccer 로 새로 요청해 주세요"* 가 나간다. 야구 사용자에게 축구 명령을
안내하는 문구다. (`_format_team_reply` 에서 같은 유형을 이미 한 번 고쳤다는
주석이 붙어 있는데, 여기는 남아 있다.)

## ⚠️ BOT-4 [하] `two_layer_html` 의 4096자 절단이 이스케이프 경계를 자를 수 있다

```python
cut = len(html) - TELEGRAM_LIMIT + 40      # 이스케이프된 길이로 계산하고
detail = detail[:-cut] + "\n…(생략)"        # 이스케이프 안 된 문자열에 적용한다
```
`detail` 에 `&`·`<` 가 많으면 재조립 후에도 4096을 넘고, `send_two_layer` 가
`html[:TELEGRAM_LIMIT]` 로 자른다 — `&amp;` 중간이나 태그 안에서 끊길 수 있다.
파싱 오류는 `except` 가 잡아 플레인으로 폴백하므로 카드가 사라지지는 않지만,
**접힌 상세가 통째로 평문으로 풀린다.**

## ✅ BOT-5 정상 확인

- `parse_intent` 가 규칙 기반으로 고정됐다 — 자유 문장마다 나가던 계량 안 되는
  유료 Anthropic 호출이 제거됐다(2026-09-06 지시). 주석이 이유를 남겼다.
- `sanitize_intent_date` 가 ±7일 창으로 LLM 날짜를 검증한다
  (실사고 2026-08-26: 모델이 2024-08-26 을 반환해 2년 전 경기 12건 분석).
- `_quota_reply` 가 429/401/402 를 구분해 안내한다 — 429 에 "충전" 문구를
  쓰지 않는다.
- `_polling_watchdog` 이 `get_me()` 로 살아있음을 직접 확인한다(롱폴링이
  조용한 것과 죽은 것을 구분).

---

# 21차 — `registry.py` 상황 축 · `situation.match_types`

## 🔴🔴🔴 SIT-1 [최상·근본원인] `_norm` 이 단어경계용 공백을 지워 `" il "` 을 `"il"` 로 만든다

```python
# app/engine/situation.py:58
def _norm(s: str) -> str:
    """대소문자·공백만 정규화. 원문을 바꾸지 않는다."""
    return re.sub(r"\s+", " ", (s or "")).strip().lower()   # ← .strip()

# app/engine/situation.py:70
if any(_norm(w) in t for w in words):
```
`registry._SIT_EN["roster_move"]` 에는 `" il "` 이 있다 — **부상자 명단(IL)이
단어로 나올 때만 잡으려고 일부러 앞뒤에 공백을 넣은 키워드**다.
`_norm` 이 그 공백을 `.strip()` 으로 지워 `"il"` 이 되고, 부분 문자열 검사라
**"il" 이 들어간 모든 제목**이 `roster_move` 가 된다.

실행 측정:
```
Phillies win 5-3                  → ['roster_move']   (Ph-il-lies)
Milwaukee Brewers bullpen notes   → ['roster_move']   (M-il-waukee)
Wild pitch decides it             → ['roster_move']   (W-il-d)
Available relievers for tonight   → ['roster_move']   (ava-il-able)
Miller dominates                  → ['roster_move']   (M-il-ler)
Family day at the park            → ['roster_move']   (fam-il-y)
Until further notice              → ['roster_move']   (Unt-il)
While Judge rests                 → ['roster_move']   (Wh-il-e)
Philadelphia weather outlook      → ['roster_move']   (Ph-il-adelphia)
Cardinals vs Pirates preview      → []
                                  → 오탐 9/10
```

### 운영 실측 — 저장된 판정 프롬프트 12건 전수

```
상황 태그가 실린 프롬프트  12/12
유형별   roster_move 22 · trade 1
확인     미확인 23 · 공식 0
```
근거 문장 전수에서 실제 로스터 이동은 몇 건뿐이다.
```
🔴 오탐  AL wild-card roundup: Guardians retake last spot…      ← "wild"
🔴 오탐  Braves vs Phillies Prediction, Pick, MLB Odds…         ← "Phillies"  (배당 기사!)
🔴 오탐  Phillies' rotation gamble looks sharp as Aaron Nola…   ← "Phillies"
🔴 오탐  Bobby Miller gets surprise hero moment for Dodgers…    ← "Miller"
🔴 오탐  Chicago Cubs at Milwaukee Brewers - Where to Watch…    ← "Milwaukee"
🔴 오탐  From 'fire drill' to firm hand, Chad Tracy…            ← "drill"
🔴 오탐  Orioles probable pitchers: Cantillo vs Rogers…         ← "Cantillo"
✅ 진짜  Orioles place OF Luis Robert Jr. on 10-day IL, recall…
✅ 진짜  Phillies Tanner Banks (Left Forearm Strain) 오늘 IL 복귀
```

**이것이 앞서(2차 감사) 기록한 "판정 프롬프트에 배당 기사가 들어간다"의
근본 원인이다.** `deepsearch.strip_odds` 가 배당어를 막지만, 이 경로는
자료2 상황 태그라 그 필터를 타지 않는다. 그리고 그 배당 기사가 태그로
승격된 이유가 **팀 이름 "Phillies" 안의 il** 이었다.

### 왜 그동안 안 보였나

`registry.py` 주석이 2026-09-06 에 이렇게 적었다.
> `@Athletics` 공식 계정의 "Athletics roster moves announced" 를 못 잡았다.
> … 구단 계정이 실제로 쓰는 말을 넣는다.

**놓치는 문제(재현율)를 고치려고 키워드를 넓혔고, 반대 위험(정밀도)을
같이 재지 않았다.** CLAUDE.md 가 명시한 규칙 — *"새 필터·가드를 추가할 때는
반대 위험(정상 데이터 폐기)을 함께 측정한다"* — 의 거울상이다.
2026-09-05 실사고("감시 오탐을 고친다며 측정 없이 규칙을 넓혀 검증
184→137건으로 악화")와 같은 형태다.

## 🔴 SIT-2 [상] `"signs"` 도 같은 종류의 오탐을 만든다

```
'Shohei Ohtani signs autographs for fans' → ['contract']
```
`_SIT_EN["contract"] = ("extension", "free agent deal", "signs")`.
`"signs"` 는 `designs`·`signs of fatigue`·`signs autographs` 에 다 걸린다.
`_SIT_EN["trade"]` 의 맨 마지막 `"trade"` 도 `trade deadline recap` 을 잡는다
(실행 확인: `'MLB trade deadline recap: who won' → ['trade']`).

## 🔴 SIT-3 [중] 상황 태그가 **23건 전부 `[미확인]`** 이다

`_is_official` 을 통과한 것이 하나도 없다. `TRUSTED_SOURCE_MARKERS` 에
`mlb.com`·`espn.com`·`sportsnet.ca`(없음)·`x.com`(없음) 이 있는데, 실제
수집원은 `x.com`·`actionnetwork.com`·`sportsnet.ca`·`nbcsportsphiladelphia`
같은 곳이라 대부분 목록 밖이다. 즉 **자료2 상황 축은 지금
"오탐 22건 + 진짜 1건, 전부 신뢰도 0" 상태로 판정 프롬프트에 실린다.**

## 🔴 REG-1 [중] `WATCHED_JOBS` 의 설명이 또 어긋났다 — 이 파일의 존재 이유가 그것이었다

```python
WatchedJob("mlb_pregame_5m", 10, "MLB 아침 발송 (cron 05~11시)"),
```
`scheduler.py:1940` 은 2026-09-07 에 `IntervalTrigger(minutes=5)` 로 바꿨고,
그 커밋 주석이 *"종전에는 CronTrigger(hour='5-11', …) 로 시각을 박아 01~04시
KST 경기 81건(24%)에서 아예 돌지 않았다"* 고 적는다.
`registry.py` 머리말은 이 파일이 생긴 이유를 이렇게 적었다.
> `W-JOB-LATE mlb_pregame_5m` — 워치독이 적은 "주기 5분" vs 실제 cron(5-11시)

**같은 사본이 이번엔 반대 방향으로 어긋났다.** 지금은 로직이 아니라 설명
문자열(`why`)뿐이라 오탐을 만들지는 않는다. 그러나 다음 사람이 이 줄을 보고
"MLB 는 아침에만 돈다"고 믿을 근거가 된다.

## ⚠️ REG-2 [하] `is_trusted_source` 는 부분 문자열이라 도메인을 검증하지 않는다

```python
return any(m in s for m in TRUSTED_SOURCE_MARKERS)
```
`"mlb.com"` 은 `"notmlb.com"`·`"mlb.com.example.io"` 에도 걸린다.
docstring 은 *"모르면 False — 모호하면 `[미확인]` 이 안전하다"* 라고 적지만,
**모르는 것을 True 로 만드는 방향의 구멍**이다. 지금 실측에서는 공식 판정이
0건이라 피해가 없다(SIT-3).

---

# 22차 — `app/version.py`

## 🔴 VER-1 [상] `staleness_line()` 은 **컨테이너에서 항상 None** — 만들어진 이유가 그 환경이었다

```python
def commits_behind() -> int:
    info = boot_info()
    if info.commit == "unknown":
        return 0
    if not _git("rev-parse", "--git-dir"):
        return 0      # 컨테이너 배포 — 비교 대상 저장소가 없다
```
이미지에는 `.git` 이 없다(`.dockerignore`). 따라서 운영에서 `commits_behind()`
는 **항상 0** 이고 `staleness_line()` 은 **항상 None** 이다.
`run_bot()` 이 기동 시 부르는 알림도 나가지 않는다.

모듈 머리말이 적은 존재 이유가 바로 그 상황이다.
> 실사고(2026-08-25): 봇이 **26커밋 뒤처진 코드**로 하루 넘게 돌고 있었다.
> → 기동 시 커밋 해시를 로그·알림에 남기고, 작업트리가 앞서 있으면 경고한다.

**남는 것은 "커밋 해시를 로그에 남긴다"까지다.** "뒤처짐 경고"는 로컬
개발 환경에서만 동작한다. 그래서 CLAUDE.md 가 *"`/health` 로 커밋 해시를
대조하라"* 는 **사람의 절차**를 따로 적어 둔 것이고, 그 절차가 지금
유일한 방어선이다.

컨테이너에서 뒤처짐을 재려면 비교 대상이 필요하다 — `.git` 없이 하려면
Railway 가 아는 최신 배포 SHA 나 저장소 쪽 값을 받아와야 한다.

### 현재 드리프트 (실측 2026-09-08 07:10 KST)
```
로컬 HEAD                21e84d2  "판정 정확도 진단 …"      (문서만)
운영 scheduler·bot        7c0f9be
미커밋                    0
로컬이 앞선 커밋           1  (문서 전용)
```
코드 드리프트는 없다.

---

# 23차 — `app/health.py` · 판정 사슬 · 서비스 간 환경 분기

## 🔴🔴 ENV-1 [최상·실측] **봇 서비스에 무료 판정 키가 없다** — 사용자 요청 판정이 사슬 없이 돈다

같은 코드가 도는 두 서비스에서 사슬을 원본(`judge_route.chain`)으로 읽고
키 보유를 `openai_compat.ENDPOINTS` 로 확인했다.
```
== analystbot-scheduler ==
matchup          ['anthropic/claude-opus-5']
matchup_prelim   ['gemini/gemini-3.7-flash']
form             ['nvidia/nemotron…', 'groq/qwen3.8-27b', 'groq/gpt-oss-120b', 'openrouter/gemma-4-31b-it:free']

== analystbot-bot ==
matchup          ['anthropic/claude-opus-5']
matchup_prelim   ['gemini/gemini-3.7-flash [키없음]']        ← 🔴 후보 0
form             ['nvidia/… [키없음]', 'groq/qwen3.8-27b', 'groq/gpt-oss-120b',
                  'openrouter/… [키없음]']                    ← 4개 중 2개만
```
`printenv` 길이로도 확인된다.
```
             scheduler   bot
GEMINI_API_KEY      53     0   🔴
NVIDIA_API_KEY      70     0   🔴
OPENROUTER_API_KEY  73     0   🔴
MISTRAL_API_KEY     32     0
GROQ_API_KEY        56    56
XAI_API_KEY         84    84
ANTHROPIC_API_KEY  108   108
```
봇은 `/mlb`·`/soccer`·팀 질의에서 `run_pipeline`→`build_analysis` 로
**직접 판정을 돌린다.** 그 경로의 1차 예비 사슬이 봇에서는 **후보 0개**다.

## 🔴 LLM-1 [상] `FREE_JUDGE_MODEL` 이 **후보 1개** — 코드가 바로 그것을 금지한다

```
운영 FREE_JUDGE_MODEL = "gemini/gemini-3.7-flash"            (1개)
운영 FREE_FORM_MODEL  = "nvidia/…,groq/…,groq/…,openrouter/…" (4개)
```
`judge_route.chain` 바로 위 주석:
> 🔴 무료 후보를 **여럿** 둔다. Nemotron 이 오디션에서 6건 중 1건을
> `503 Service temporarily overloaded` 로 놓쳤다 — 무료 인프라는 가끔 밀린다.
> **하나만 두면 그 경기는 카드가 못 나간다.**

폼 사슬은 그 규칙을 지켰고 **판정 사슬은 안 지켰다.** 판정이 더 중요한
쪽인데 여유가 없다. (Gemini 를 단독 승격한 근거는 안정성 실측이었다 —
산포 2.00%p·뒤집힘 0회. 안정성으로 고른 것과 **가용성 예비를 없앤 것**은
다른 결정인데 한 번에 이뤄졌다.)

`LLM_SEED` 는 두 서비스 모두 **미설정**이다(빈 출력) — 즉 seed 를 보내지
않는다. `.env` 문서는 "0 이면 미전송"이라 적었고 지금이 그 상태다.

## 🔴 HL-1 [상] `/health` 의 `JOB_PERIODS` 는 손으로 적은 사본이다 (registry 규칙 위반)

```python
JOB_PERIODS = {  # app/health.py:21
    "prefetch_daily": timedelta(days=1),        # ← 존재하지 않는 잡 id
    "odds_snapshot_30m": timedelta(minutes=30),
    ... 총 10개
}
```
`registry.py` 머리말이 명시한다.
> ⚠️ 잡의 **주기는 여기 적지 않는다.** 트리거 객체(`scheduler._JOB_TRIGGERS`)가
> 원본이다 … 여기 옮겨 적으면 그 순간 다시 사본이 된다.

`health.py` 가 정확히 그 금지된 사본을 갖고 있다.
- 실제 스케줄러 잡은 **24개**, `JOB_PERIODS` 는 **10개**.
- `prefetch_daily` 는 **없는 잡**이다 — 실제는 `prefetch_evening`(21:00) ·
  `prefetch_dawn`(04:30) · `prefetch_asia`(14:00) 셋이다.
  그래서 `/health` 가 항상 `🟡 prefetch_daily 마지막 기록 없음` 과
  `⚪ 마지막 프리페치 기록 없음` 을 낸다 — **프리페치는 세 번 다 성공했는데도.**
  (앞선 감사에서 렌더 결과로 관찰했던 두 줄의 원인이 이 상수다.)
- 빠진 감시: 프리페치 3종 · `watchdog_5m` · `npb_pregame_2m` ·
  `soccer_trial_10m` · `daily_summary_*` 3종 · `calibration_weekly` ·
  `park_weekly` · `*_lineup_history` 3종 · `heartbeat_2m`.

## 🔴 HL-2 [상] `/health` 가 **틀린 판정 모델**을 보여준다

```python
L.append(f"   judge 모델 {s.judge_model}")     # health.py:154
```
`s.judge_model` 은 **구 Judge(축구·`--old`)** 필드다. 운영값:
```
judge_model = claude-opus-4-6      ← /health 에 표시되는 값
실제 최종 판정 = anthropic/claude-opus-5   (MODEL_MATCHUP)
실제 예비 판정 = gemini/gemini-3.7-flash   (FREE_JUDGE_MODEL)
```
"지금 믿어도 되는 상태인가"를 답하는 화면이 **어떤 모델이 판정하는지를
틀리게 말한다.**

## 🔴 HL-3 [상] `/health` 의 "오늘 지표" 도 MLB·축구만 본다

```python
for sport, label in (("mlb", "MLB"), ("soccer", "축구")):
```
KBO·NPB 가 없다. 그래서 `/health` 는 자동 발송 주력 두 리그의 판정률·
리서치율을 **한 줄도 보여주지 않는다.** (BOT-1·BOT-2 와 같은 계열의 누락 —
"MLB + 축구" 라는 옛 이분법이 코드 여러 곳에 화석으로 남아 있다.)

## ⚠️ HL-4 [중] `commits_behind()` 가 컨테이너에서 항상 0이라 코드 아이콘이 늘 🟢

`/health` 1절은 `behind = commits_behind()` 로 🔴/🟢 를 정한다.
VER-1 대로 컨테이너에서는 항상 0 → **항상 🟢**. 26커밋 뒤처졌던 그 상황을
`/health` 로는 감지할 수 없다. 사람이 해시를 눈으로 대조해야 한다.

## ⚠️ HL-5 [하] `λ 0/11 (0%)` 은 고장처럼 보이지만 의도된 상태다

야구는 `_compute_picks` 가 `jg["lam"]=None` 으로 λ 를 끈다. `/health` 는
그것을 모르고 가동률 0% 로 찍는다. 실제 결함(λ 산출 실패)과 구분되지 않는다.

---

# 24차 — 운영 로그 실측 (2026-09-07 20:34~22:09 UTC)

`railway` 배포 로그를 직접 읽었다. **지금 돌고 있는 상태**다.

## 🔴🔴🔴 LIVE-1 [최상] Anthropic 잔액 소진 — 최종 판정이 grok 으로 대체되고 있다

```
21:04:03  WARNING  anthropic(matchup): Error code: 400 - {'type':'error',
                   'error': {'type':'invalid_request_error', …
21:04:03  WARNING  [judge_route.py:89] Anthropic 소진 — 최종 판정을 grok 으로 대체
```
원장이 그 결과를 확인해 준다.
```
2026-09-07  gemini/gemini-3.7-flash   28건  12:42 ~ 22:09 UTC
2026-09-07  xai/grok-4.3-latest        9건  14:35 ~ 21:04 UTC
            (anthropic 판정 0건)
```
설계대로 동작한 것이다(2026-09-07 지시로 만든 대체 경로). 다만 **아무도
그 사실을 알림으로 받지 않았다** — `_EXHAUSTED` 는 프로세스 메모리의 dict
(`provider._is_exhausted`)이고 Redis `api_block:*` 은 **비어 있다.**
즉 재기동하면 소진 표식이 사라져 다시 Anthropic 을 때린다.

## 🔴🔴 LIVE-2 [최상] LLM-1(후보 1개)이 **실제로 판정 실패를 만들었다**

```
21:14:06  WARNING  gemini 429 — 2초 후 재시도   (×3)
21:14:07  WARNING  무료 사슬 실패 (후보 1개 소진)        team_form.py:295
21:14:07  ERROR    🔴 무료 사슬 전부 실패 — 유료로 내려가지 않는다.
                   이 건은 재료 없이 간다                team_form.py:344
21:14:07  WARNING  JSON 파싱 실패 1회                    matchup.py:847
21:14:16  … 같은 순서 반복 → JSON 파싱 실패 2회
21:14:16  WARNING  Los Angeles Dodgers vs Cincinnati …   matchup.py:861
21:14:16  WARNING  서술 실패(폴백 렌더 사용)             narrator.py:247
22:09:09  같은 패턴 재발 (Athletics)
```
**"후보 1개 소진"** 이 로그에 그대로 찍힌다 — `FREE_JUDGE_MODEL` 이
`gemini/gemini-3.7-flash` 하나뿐이라는 사실이 그대로 장애가 됐다.
`judge_route.chain` 주석이 예고한 문장이 그대로 실현됐다.
> 하나만 두면 그 경기는 카드가 못 나간다.

⚠️ 정정: 로그의 `🔴 무료 사슬 전부 실패 — 유료로` 는 Railway 표시가 잘린
것이고, 원문은 *"유료로 **내려가지 않는다**"* 다. 유료 폴백은 일어나지
않았다(2026-09-04 지시대로). 결과는 **그 건이 재료 없이 판정**된 것이다.

## 🔴 LIVE-3 [상] oddsportal 이 KBO·NPB 에서 계속 503 — 워치독이 5분마다 운다

```
20:34:39  npb 조회 실패 (시도 2/2): Server error '503 Service Unavailable'
20:39:09  W-ODDS-STALE oddsportal
20:44:01  W-ODDS-STALE oddsportal
20:49:01  … 20:54 … 20:59 … 21:04 … 22:09  (5분마다 계속)
21:34:31  kbo 조회 실패 (시도 1/2, 2/2) 503
22:04:31  kbo·npb 각 2회 재시도 전부 503
```
KBO·NPB 담당 배당 소스가 **1개뿐**(`registry.ODDS_PROVIDERS`: oddsportal)이라
폴백이 없다. MLB 는 espn + sharp 2단이다. 앞선 15차에서 잰
`odds 36/657`·`edge_status 0/657` 의 배경이 이것이다.

## 🔴 LIVE-4 [상] `llm_calls` 원장이 **유료·grok 호출을 세지 않는다**

```
llm_calls:2026-09-05  gemini:ok 32 · gemini:fail 25 · groq:fail 57
llm_calls:2026-09-06  gemini:ok 102 · groq:fail 102
llm_calls:2026-09-07  gemini:ok 6 · groq:ok 8 · groq:fail 6
llm_calls:2026-09-08  (없음)
```
같은 날 원장에는 **grok 판정 9건**이 있고 gemini 판정 28건이 있는데,
`llm_calls:2026-09-07` 의 gemini 는 6건뿐이고 **xai·anthropic 은 한 줄도 없다.**
`_ledger.record_call` 은 `provider.complete_with_chain` 경로에만 걸려 있고,
판정·폼이 쓰는 `team_form._complete_free` / anthropic 직접 호출 경로에는
없다. 그래서 `/health` 의 LLM 절과 `W-LLM-PAID` 감시가 **유료 사용량을
못 본다** — 비용이 새는 것을 잡으려고 만든 계량이 정작 유료를 안 센다.

## 🔴 LIVE-5 [상] 평문 키 유출이 **아직 Redis 에 남아 있다** (재확인)

```
llm_outage:2026-09-06  (list, 102건)
llm_outage:2026-09-07  (list,   6건)
   detail = "Illegal header value b'Bearer gsk_…\nNVIDIA_API_KEY=nvapi-…\nMISTRAL_API_KEY=xN5…'"
```
앞서 보고한 그대로다. TTL 이 남아 있고 **두 날짜 키에 108건**이 평문으로
들어 있다. 원인은 이미 고쳐졌지만(키가 1줄로 정상) **기록은 지워지지 않았다.**
(값은 여기 옮겨 적지 않는다 — 접두 4자만 남긴다.)

## ⚠️ LIVE-6 [중] 봇은 배포 이후 **한 번도 사용되지 않았다**

```
2026-09-07T11:03:47  Starting Container
2026-09-07T11:03:54  [version] bot 기동 — 커밋 7c0f9be
2026-09-07T11:03:55  Run polling for bot @sports_analyst_2026_bot
   (이후 로그 없음 — 20시간)
```
따라서 ENV-1(봇에 gemini 키 없음)은 **아직 사고로 드러나지 않았을 뿐**이다.
사용자가 `/mlb` 한 번 치면 그 자리에서 예비 판정 후보가 0개가 된다.

## ⚠️ LIVE-7 [하] 모든 로그가 `severity=error` 로 올라간다

봇·스케줄러 모두 파이썬 로깅이 stderr 로 나가 Railway 가 전부 `error` 로
분류한다(`INFO:app.bot.main:starting polling` 도 severity error).
심각도 기반 알림·필터를 걸 수 없다.

## ❌ 자기정정 — `analysis:{sport}:{game_id}:{date}` 는 결함이 아니다

46개 키가 `games` 를 안 갖고 있어 "빈 캐시"로 읽었는데, 제 조회 스크립트가
슬레이트 스키마를 기대한 탓이었다. 실제 내용은 의도된 3칸 기록이다.
```
analysis:mlb:4093:2026-09-07 → {"model":"gemini/gemini-3.7-flash","p_home":0.49,"우세":"박빙"}
```
`matchup.py:495` 가 "사용 모델 ID를 남긴다"는 목적으로 쓰는 키다. 정상.

## 🔴🔴 LIVE-8 [최상] 워치독은 **판정 사슬을 감시하지 않는다** — 스스로 그렇게 적어 두었다

```python
# app/watchdog.py:189
return [("W-LLM-FAIL", role or "aux",
         f"연속 {n}회 실패 — {what}이 멈춰 있다 "
         f"(매치업 판정은 별도 무료 사슬이라 무관)" …)]
```
연속 실패 카운터를 올리는 곳은 `provider.py` 뿐이다.
```
$ grep -rn "record_call\|record_outage" app/ | grep -v app/llm/ledger.py
app/llm/provider.py:668,682,683,696,697,702,703      ← 여기만
```
판정·폼이 실제로 쓰는 `team_form._complete_free` 와 anthropic 직접 호출은
**카운터를 건드리지 않는다.** 따라서

- LIVE-2 의 `무료 사슬 실패 (후보 1개 소진)` → 경보 없음
- LIVE-1 의 `Anthropic 소진` → 경보 없음 (`api_block:*` 도 비어 있음)
- `/health` LLM 절 · `W-LLM-FAIL` · `W-LLM-PAID` 모두 판정 경로를 못 본다

워치독 머리말이 적은 존재 이유가 바로 이것이었다.
> · 크레딧이 소진돼 판정이 멈췄는데 카드도 경보도 없었다.

그 문장이 가리키는 사고가 **어제 다시 일어났고, 이번에도 경보는 없었다.**
(카드는 grok 대체 덕분에 나갔다 — 대체가 없었으면 같은 사고 반복이었다.)

덧붙여 워치독 머리말은 코드 8종만 적는데 실제 코드는 **16종**이다
(`W-LLM-PAID`·`W-RESCUE-DEAD`·`W-STALE-GAME`·`W-FACT-MISMATCH`·
`W-PANEL-DIVERGE`·`W-JUDGE-OBJECTION`·`W-MONITOR-DOWN`·`W-SEND-PENDING`
이 문서에 없다). 또 하나의 사본 드리프트다.

---

# 25차 — 자료12(elo) 캐시 실측

## 🔴🔴 ELO-1 [최상·실행측정] 오늘 판정이 쓰는 레이팅이 **33경기(8.7%) 뒤처져 있다**

운영 Redis 의 `elo:mlb:2026-09-08` 과, 같은 순간 DB 로 다시 계산한 값을 비교했다.
```
팀                        캐시     지금     차이   경기수 캐시/지금
Arizona Diamondbacks    1489.2  1512.8  +23.6    19/24
Texas Rangers           1511.2  1497.3  -13.9    22/25
St. Louis Cardinals     1492.2  1505.3  +13.1    24/26
Atlanta Braves          1522.8  1511.2  -11.6    26/27
… 10점 이상 벌어진 팀 4/30 · 27/30 팀이 경기수 부족
캐시 경기수 합 692(=346경기) / DB 종료 379경기
```
DB 무결성은 정상이다 — `home_score`·`away_score` 가 한쪽만 있는 행은
**전 종목 0건**(mlb 379/379 · kbo 224/224 · npb 154/154 · soccer 72/72).
즉 데이터 결손이 아니라 **캐시 시점 문제**다.

왜 중요한가: **MLB 레이팅 전체 폭이 55.5점**(1469.1~1524.6)이다.
23.6점 오차는 **리그 전체 폭의 43%** 다. 자료12 는 판정 프롬프트에서
"기본 축"인데, 그 축이 한 팀에서 리그 폭의 4할만큼 틀린 값으로 들어간다.

구조도 확인했다.
```python
# pipeline.py:2726
_elo_map = await _team_elo.load(redis, _sport, date)          # 26h TTL 캐시
if not _elo_map and pool is not None:
    _elo_map = await _team_elo.refresh(pool, redis, _sport, date)   # 미스일 때만
```
"슬레이트당 한 번만 계산한다"는 설계는 맞다(경기마다 리플레이하면 같은 값을
N번 만든다). 문제는 **그 한 번이 언제인가**다. MLB 경기는 KST 아침에 끝나고
`ingest_finals_13h` 는 13:00 KST 에 점수를 적재하는데, 오늘 슬레이트의 elo 는
그보다 **먼저** 계산돼 굳는다. 결과적으로 **자료12 는 구조적으로 직전
하루치 결과를 못 본다.**

## 🔴 ELO-2 [상] 세 날짜 키가 **바이트까지 동일**하다

```
elo:mlb:2026-09-06   md5 4ac4aa6c29  ttl 53858
elo:mlb:2026-09-07   md5 4ac4aa6c29  ttl 53888
elo:mlb:2026-09-08   md5 4ac4aa6c29  ttl 53993
elo:kbo:2026-09-07/08  md5 eed2e58640 (동일)
elo:npb:2026-09-07/08  md5 fb60de38a4 (동일)
```
TTL 이 135초 안에 몰려 있어 **세 키가 한 번에 쓰였다.** 즉 `elo:{sport}:{date}`
의 `date` 는 "그 날짜 기준 레이팅"이 아니라 **"그 키를 만든 순간의 레이팅"**
이다.

지금은 새는 곳이 없다(`pipeline` 은 당일 키만 읽고, 백테스트 도구들은
`ratings_asof` 로 자기가 다시 리플레이한다 — `tools/fit_elo.py` 가 그
누수를 막으려고 일부러 그렇게 짰다). 그러나 **키 이름이 "as-of" 를
약속하는데 내용은 아니다.** 누군가 `elo:mlb:2026-09-06` 을 "9월 6일 시점
실력"으로 읽고 백테스트에 쓰는 순간 미래가 새어 들어간다.

## 🔴 ELO-3 [상] 자료12 가 만들 수 있는 최대 확률은 **60.0%** 다

지금 레이팅으로 계산하면:
```
최강 홈(PHI 1524.6) vs 최약 원정(LAA 1469.1) + home_adv 15
  diff = 70.5 → expected_home = 60.0%
```
추천 하한이 0.58(원정 0.63)이다. 즉 **자료12 단독으로는 리그 최강이 리그
최약을 홈에서 맞아도 추천선을 겨우 2%p 넘긴다.** `tools/fit_elo.py` 머리말이
같은 지적을 했다(*"자료12 가 만들 수 있는 최대 편차가 ±9.2%p"*).
13차·14차에서 잰 "MLB 에서 기준선 미달"과 합치면, 자료12 는 MLB 에서
**방향도 못 맞히고 진폭도 없다.**

## ✅ ELO-4 정상 확인 — 커널 사본은 없다

`elo_core.replay` 하나를 야구·축구가 같이 쓴다(`team_elo`·`soccer_elo`).
최근 가중은 `weight` 콜백으로 주입하고 커널 안에서만 K 에 곱한다 —
"최근 가중은 여기 한 곳에서만" 이라는 주석 그대로다.
`MIN_GAMES=10` 미만 팀은 평균 계산에서 뺀다.

---

# 26차 — 자료9 시즌 스탯 역주입: **판정이 실제로 그것을 근거로 썼다**

앞서(2차) `pipeline.py:2751 _bp_recent` 가 지운 `era/whip/k9/bb9` 를
`pipeline.py:2772 _pen` 이 다시 채워 넣는 순서 결함을 기록했다.
이번에는 **그 결과가 판정 문장에 나타난 것**을 찾았다.

## 🔴🔴🔴 M9-1 [최상·실측] 판정 근거에 "시즌 ERA 4.63" 이 그대로 적혔다

`judge_prompt:4098` 에 실린 직전 판정의 `근거` 배열:
```json
"근거": [
  "자료12 실력 레이팅에서 원정(1490.4)이 홈(1475.6)에 14.8점 앞서나 홈 어드밴티지로 상쇄되는 박빙 구도",
  "자료1·2 최근 3경기 득실점에서 홈(11득 7실)이 원정(8득 18실) 대비 …",
  "자료9 불펜 폼에서 홈(3경기 6이닝 1실점, ERA 3.68)이 원정(시즌 ERA 4.63) 대비 경기 후반 안정성 유지"
]
```
같은 프롬프트가 몇 줄 위에서 이렇게 지시한다.
```
- 시즌 **집계표**(타율·ERA·승패표·좌우 스플릿·통산·상대전적)는 쓰지 않는다.
- **시즌 누적·통산·상대전적은 판정 입력이 아니다** (2026-09-04 대원칙).
```
**모델이 규칙을 어긴 것이 아니다 — 우리가 그 숫자를 자료9 라고 이름 붙여
건네줬다.** 자료9 블록의 라벨은 `"양팀 불펜 — **최근 폼만**"` 이다.

전수 확인:
```
자료9 블록에 era/whip/k9/bb9 가 실린 프롬프트   12/12  (100%)
   예: "era": 3.7, "whip": 1.17, "k9": 9.32, "bb9": 3.12
       "era": 4.7, "whip": 1.39, "k9": 7.92, "bb9": 3.69
근거 문장에 "시즌 ERA" 가 나온 프롬프트         1/12
   (나머지 12건의 "시즌/통산/상대전적" 매치는 전부 프롬프트의 금지 문구다)
```
`test_season_ban.py` 는 자료7·8(선발/타선 시즌 라인)만 잠근다. **자료9 경로는
그 테스트의 사각지대다** — 금지된 값이 다른 자료 번호를 달고 들어온다.

## ✅ M9-2 정상 확인 — 리서치의 `era_season` 은 프롬프트에 닿지 않는다

`research:{game_id}` 페이로드에는 `home_pitcher.era_season` 이 있다.
```
research:3711  home_pitcher = {'name': 'Brady Singer', 'era_season': 4.83, 'trend': '악화', 'throws': 'R'}
```
그러나 `judge_prompt:*` 12건에 `era_season` 은 **0건**이다. 조립 단계가
걸러낸다. (즉 자료9 만 새고 있다.)

---

# 27차 — 리서치 무효율

## 🔴 RV-1 [상] 무효율이 26% → 60% 로 뛰었고, 원인은 `validate.py` 가 아니다

```
research_fill 실측 (운영 Redis)
  2026-08-26  27경기  무효  7  (26%)
  2026-08-27  40경기  무효 11  (28%)
  2026-09-06  25경기  무효 15  (60%)   🔴
  2026-09-07  15경기  무효  7  (47%)   ⚠️ /health 경고선 30% 초과
  2026-09-08   4경기  무효  1  (25%)
research_fail 은 전부 `parse` 다 (08-28 credit 5 제외).
```
`validate.py` 는 **2026-08-29 이후 변경이 없다**(git log 확인). 즉 게이트를
넓혀서 늘어난 것이 아니라 **응답 품질이 실제로 나빠졌다.**

같은 기간 필드 충족률도 함께 무너졌다.
```
             08-27(40경기)   09-06(25경기)
form_filled      16 (40%)        4 (16%)
splits_filled    11 (28%)        1 ( 4%)
bullpen_filled   16 (40%)        3 (12%)
```
저장된 페이로드에서도 보인다 — `research:3712`(616자)·`research:3716`(332자)
는 선발 이름과 빈 `absences` 뿐이고 폼·불펜·동기가 통째로 없다.

`PPLX_API_MODE=chat` 이다. CLAUDE.md 가 적은 **Agent API 마이그레이션 기한
2026-09-27 까지 19일** 남았고, 지금 상태에서 전환하면 이 무효율이 어떻게
움직일지 기준선이 없다 — 전환 **전에** 지금 값을 고정해 둬야 한다.

## ✅ RV-2 정상 확인 — `validate.py` 는 반대 위험을 함께 다룬다

- `_KEEP_PHRASES = ("출전 불가","출장 불가","기용 불가","선발 불가")` 로
  결장 정보의 "불가" 를 미확보 산문으로 오판하지 않는다.
- `_HARD_TO_RE` 가 `<동작>하기 어렵` 으로 한정돼 "타선 공략이 어렵다" 같은
  정상 평가를 살린다.
- 반향(echo) 판정은 자카드 0.72 · 최소 토큰 5 로 임계를 높게 잡고,
  순수 자리표시자는 `INSTRUCTION_MARKERS` 로 따로 잡는다.
- 각 보강 커밋이 **미탐 실측 문장을 주석에 남겼다**(2026-08-25·08-26).
이 모듈은 이번 감사에서 본 것 중 반대 위험을 가장 성실히 다룬 코드다.

---
---

# 이번 이어달리기(14~27차) 요약 — 심각도 순

작업트리는 처음부터 끝까지 **0 변경**이다. 모든 수치는 운영(`railway ssh`)
DB·Redis·로그, 또는 운영 컨테이너에서 모듈을 직접 실행해 얻었다.

## 🔴🔴🔴 최상 — 지금 사용자에게 나가는 것이 틀렸거나, 나가지 않는다

| 코드 | 한 줄 | 증거 |
|---|---|---|
| GATE-1 | 게이트가 **가장 못 맞는 경기**를 고른다 | 추천 15건 33.3% vs 보드만 97건 58.8% |
| GATE-3 | 확률이 단조가 아니다 — 추천 하한 0.58 이 최악 구간을 자른다 | 홈 0.55–0.60 구간 32.1%(n=28) |
| BOT-1 | **KBO·NPB 를 봇으로 물어볼 방법이 없다** | 팀 별칭 17/17 미등록 · "KBO"→MLB 카드 · "일본프로야구"→J1 축구 |
| SIT-1 | `" il "` 이 `"il"` 로 뭉개져 **"Phillies"·"Milwaukee"·"Wild" 가 로스터 이동 태그** | 오탐 9/10 · 운영 태그 22/23 이 roster_move |
| M9-1 | 판정이 **"시즌 ERA 4.63"** 을 근거로 썼다 | 자료9 블록에 era/whip/k9/bb9 12/12 |
| LIVE-1 | Anthropic 잔액 소진 — grok 대체 중, **경보 0** | 09-07 grok 판정 9건 · anthropic 0건 |
| LIVE-2 | 무료 판정 후보가 1개라 429 한 번에 사슬이 끝났다 | `무료 사슬 실패 (후보 1개 소진)` 로그 2회 |
| LIVE-8 | 워치독이 **판정 사슬을 감시하지 않는다** | `record_call` 은 provider.py 에만 |
| ENV-1 | **봇 서비스에 gemini/nvidia/openrouter 키가 없다** | 예비 판정 후보 0개 |
| LED-4 | 한 경기 **17회 판정**, p 가 ±0.06 로 떨며 재판정을 자가생산 | game 1719 전 이력 |
| LED-5/6 | `lineup_status` 역행 — DB 에 흔적 13건 | `rejudge_after_lineup:5514` 무가드 대입 |
| NPB-1 | NPB `starts_at` 은 한 번 틀리면 **영원히 안 고쳐진다** | `apply_result` 두 경로 모두 starts_at 미갱신 |
| ELO-1 | 오늘 판정의 자료12 가 **33경기 뒤처져** 최대 23.6점(리그 폭의 43%) 틀리다 | 캐시 vs 재계산 대조 |
| BT-1/FE-1 | 자료12 가 MLB·NPB 에서 **홈고정보다 못하다** | 독립 측정 2회(전구간·홀드아웃) |
| HK-1 | 훅 자기검증이 **정상 상태에서 8건 실패** | selftest 1·2·3 실행 |

## 🔴 상 — 계량·감시·경로가 사실과 다르다

GATE-2(괴리 클수록 틀림) · GATE-5(NPB 42.9%) · CONF-1(M축 36/36 '상') ·
LED-1(경기당 4.9회 판정) · LED-2(09-06 원장 190행) · LED-3(09-07 추천 0건) ·
DSP-1(발송률 분모가 폴링 틱) · LS-1(`lineup_season` 전량 미배선) ·
BOT-2(`/픽` 이 MLB·축구만) · SIT-2(`"signs"`) · VER-1(뒤처짐 경고가 컨테이너에서 무력) ·
HL-1(JOB_PERIODS 사본, 없는 잡 `prefetch_daily`) · HL-2(/health 가 틀린 판정 모델 표시) ·
HL-3(/health 에 KBO·NPB 없음) · LLM-1(FREE_JUDGE_MODEL 후보 1개) ·
LIVE-3(oddsportal 503 · KBO·NPB 배당 소스 1개) · LIVE-4(유료 호출 미계량) ·
LIVE-5(평문 키 108건 잔존) · ELO-2(세 날짜 키 동일) · ELO-3(자료12 최대 60.0%) ·
RV-1(리서치 무효율 26%→60%)

## 반복되는 한 가지 형태

이번에 찾은 것 중 **9건이 같은 병**이다 — *원본이 있는 사실을 다른 곳에
한 번 더 적었고, 원본이 바뀔 때 사본이 따라가지 않았다.*

```
HL-1  health.JOB_PERIODS      ← scheduler._JOB_TRIGGERS  (registry 가 금지한 바로 그것)
REG-1 WATCHED_JOBS.why        ← scheduler 트리거
HL-2  s.judge_model           ← MODEL_MATCHUP / FREE_JUDGE_MODEL
LS-1  engine/CLAUDE.md:64     ← variable_ref 의 실제 import
LIVE-8 watchdog 머리말 8종     ← 코드의 16종
SIT-1 " il " 패딩             ← _norm 이 지움
LED-5 lineup_status 가드      ← 세 곳 중 한 곳만
BOT-1 KR_TEAM_NAMES/TEAM_ALIASES ← 표시용엔 있고 조회용엔 없음
ELO-2 elo:{date} 키 이름       ← 내용은 as-of 가 아님
```
CLAUDE.md 의 「사본 금지」가 정확히 이 병을 겨냥해 쓰였고, 그 규칙이 적힌
파일들 자신이 사본을 갖고 있다.

## 두 번째 형태 — "고치는 쪽만 재고 반대 위험은 안 쟀다"

SIT-1(재현율 넓히다 정밀도 붕괴) · HK-1(게이트 테스트가 정상을 결함으로) ·
DSP-2(성공을 미발송으로 셈) · LLM-1(안정성으로 고르며 가용성 예비 제거).
CLAUDE.md 가 *"새 필터·가드를 추가할 때는 반대 위험(정상 데이터 폐기)을
함께 측정한다"* 고 적어 둔 그 규칙이다.

---

# 28차 — 감시층 L1·L2·L3 의 실제 적재량

운영 DB 전수:
```
judgement_audit         1154행   최신 2026-09-07 22:19   ✅ L1 살아 있다
game_trace              2268행   최신 2026-09-07 22:19   ✅
variable_ledger          665행   최신 2026-09-07 22:19   ✅
lineup_events           1739행   최신 2026-09-07 22:19   ✅
market_baseline_ledger    76행   최신 2026-09-07 22:14   ✅
pitcher_appearances     6628행                          ✅
expert_picks             443행   최신 2026-09-07 19:31   ✅
predictions             1270행   최신 2026-09-07 12:42   ✅
cell_verdicts            258행   최신 2026-08-29 05:10   🔴 10일째 정지
judge_review               0행                          🔴 전 기간 0
shadow_panel               0행                          🔴 전 기간 0
```

## 🔴🔴 MON-1 [최상] L2(검사역)·L3(독립 판정)은 **여전히 0행**이다 — 09-07 수리 후에도

`shadow_panel.py:98~104` 주석이 종전 원인을 적어 두었다.
> 🔴 [P0 실사고 2026-09-07] 종전에는 `g["gate_result"]` 를 읽었는데 분석
> 캐시의 경기 dict 에는 그 키가 없다 … 그래서 `pick_targets` 가 **언제나
> 0건** 이었고 … `judge_review` 0행 · `shadow_panel` 0행(전 기간).

그 수리는 **기계적으로는 동작한다.** 운영에서 직접 실행해 확인했다.
```
gemini is_available: True · shadow_max_per_slate: 5
analysis:mlb:2026-09-07  경기 4  등급 {'보드만': 4}  → 패널 대상 0
   game=4099 pick_summary=있음 gate_result=None p=0.56   ← 재계산이 '보드만' 을 낸다
```
즉 `_grade` 폴백은 제대로 등급을 낸다. **그런데 대상이 0이다** —
`pick_targets` 는 `엣지`·`추천` 만 고르는데, 09-07 슬레이트의 등급은
**보드만 31 · 거부권탈락 5 · 추천 0** 이었다(LED-3).

## 🔴🔴 MON-2 [최상·구조] 감시층이 **추천 건수에 종속**돼 있다

```
추천이 안 나온다 (GATE-3: 확률 비단조 + 하한 0.58)
        ↓
pick_targets = 0
        ↓
judge_review · shadow_panel 0행
        ↓
"판정이 맞는가"를 검사할 신호가 없다
```
그리고 이 상태는 **고장과 구분되지 않는다.** `W-MONITOR-DOWN` 은
`fact_audit`·`shadow_panel` 내부에서 **예외가 났을 때만** 울린다
(`fact_audit.py:639` · `shadow_panel.py:285`). 대상이 0이면 예외도 없으니
조용히 0행이 쌓인다 — 이 저장소가 「조용한 0은 결함이다」라고 부르는 바로
그 형태다. 발송에는 그 규율을 적용했고(`dispatch_stats`) **감시층에는
적용하지 않았다.**

## 🔴 MON-3 [상] `cell_verdicts` 는 2026-08-29 이후 한 건도 없다

`interpreter.py:231` 이 적재한다("pool이 있으면 판정을 `cell_verdicts`에
적재한다(#63)"). 258행에서 멈춘 지 10일이다. 같은 기간 `judgement_audit`
은 계속 쌓였으므로 **판정 자체는 돌고 있다** — 이 경로만 끊겼다.
(끊긴 지점은 아직 특정하지 못했다. `interpreter` 호출 자체가 사라졌는지,
pool 이 안 넘어가는지 확인이 필요하다. **측정 전이라 원인은 쓰지 않는다.**)

## 이 세 개가 앞의 발견들과 이어지는 자리

L2·L3 는 판정 품질을 검사하라고 만든 층이다. 그런데
- 자료9 시즌 스탯 역주입(M9-1) — 검사역이 봤다면 잡았을 종류다
- 자료12 33경기 지연(ELO-1)
- 상황 태그 오탐 22/23(SIT-1)

이 셋 다 **L2·L3 가 한 번도 돌지 않은 기간에** 발생했다. 감시층이 비어
있었던 것이 이번 감사에서 사람이 이 결함들을 먼저 발견한 이유다.
CLAUDE.md 워치독 절의 목표 — *"사람이 먼저 발견하는 고장은 0건이어야
한다"* — 가 지켜지지 않았다.

---

# 29차 — 🔴🔴🔴 **P0 재발: Anthropic 차단기가 무료 사슬 역할까지 죽인다**

## CG-1 [최상·운영에서 재현] `provider.py:655` 의 무조건 `abort_if_credit_gone(role)`

```python
# app/llm/provider.py:643~663  (complete_with_chain)
chain = provider_chain(role, settings)
...
from app.engine.credit_guard import abort_if_credit_gone

abort_if_credit_gone(role)          # ← 🔴 사슬을 보지 않고 무조건 중단
for p in chain:
    if s.is_disabled(p.name):
        tried.append(f"{p.name}(disabled)"); continue
    if (why := _is_exhausted(p.name)):        # ← 이 줄이 올바른 판단이다
        tried.append(f"{p.name}(소진·생략)"); continue
```
바로 아래 루프에 **provider 별** 소진 검사가 이미 있다. 655행은 그것을
전역으로 한 번 더 하는데, `abort_if_credit_gone` 은 **오직 anthropic 만**
본다(`credit_guard.py:24 _is_exhausted("anthropic")`).

따라서 사슬에 Anthropic 이 **하나도 없는 역할**까지 죽는다.

### 운영 컨테이너에서 직접 재현 (별도 프로세스, 운영 상태 불변)
```
interpreter chain: [('groq','openai/gpt-oss-120b'), ('gemini','gemini-3.6-flash')]
→ credit_guard.trip_credit("probe/anthropic", ...) 후
🔴 interpreter 차단: anthropic: 잔액 소진으로 중단 (interpreter): probe/anthropic: …
🔴 narrator   차단: anthropic: 잔액 소진으로 중단 (narrator): …
🔴 intent     차단: anthropic: 잔액 소진으로 중단 (intent): …
```
세 역할 모두 `groq → gemini` 사슬이고 **Anthropic 을 부르지 않는다.**

### 운영 로그가 그대로 보여준다 (2026-09-07 14:14~15:54, 20여 건)
```
WARNING:app.pipeline:[2단-라인업] New York Mets 해석 실패 — 사실만 남긴다:
  anthropic: 잔액 소진으로 중단 (interpreter):
  matchup:New York Mets@Miami Marlins: anthropic(matchup): Error code: 400 -
  {'type':'invalid_request_error','message':'Your credit balance is too low …'}
```
문자열 구조가 사고를 그대로 적는다.
```
잔액 소진으로 중단 (interpreter)      ← 죽은 것: 무료 사슬 역할
matchup:NYM@MIA: anthropic(matchup)  ← 죽인 것: 유료 판정이 남긴 사유
```

## CG-2 [최상] 이것은 **2026-09-06 P0 의 재발**이다 — 같은 병, 다른 호출부

`tests/test_credit_guard_scope.py` 머리말이 그 사고를 적어 두었다.
> 🔴 실사고: 축구 실험(`soccer_trial`)이 Anthropic 400 을 맞고 공용 차단기를
> 내렸다. 야구 판정은 무료 사슬(Gemini)로 도는데도 **호출을 시도조차 못 하고**
> 전부 죽었다 — MLB 발송 0/85 (0%) …
> 차단기 자체는 옳다. 틀린 것은 **적용 범위**였다.

그때의 수리는 **호출부 두 곳에만** 가드를 붙였다.
```python
app/engine/team_form.py:492   if not _free_primary(FORM_ROLE): abort_if_credit_gone(...)
app/engine/matchup.py:728     if not _free_primary(...):       abort_if_credit_gone(...)
```
`provider.py:655` 는 손대지 않았다. 그래서 `complete()` 를 쓰는
**모든 보조 역할**(interpreter·narrator·intent)이 같은 방식으로 계속 죽는다.

테스트도 그 사각을 그대로 물려받았다.
```python
def test_free_chain_is_not_blocked_by_anthropic_exhaustion(monkeypatch):
    monkeypatch.setattr(tf, "_free_primary", lambda role: True)   # ← team_form 만
    ...
```
`complete_with_chain` 을 지나가는 케이스가 없다. **2521개 테스트가 전부
통과하면서 이 결함이 살아 있다.**

## CG-3 [상] 측정된 파급

| 무엇 | 증거 |
|---|---|
| `cell_verdicts` 적재 정지 | 258행, 최신 **2026-08-29 05:10** (10일) |
| 2단 해석 = "판정 미수행" | 카드에 ▲▼ 가 없고 사실만 나간다 |
| 서술 폴백 | `서술 실패(폴백 렌더 사용)` narrator.py:247 반복 |
| 라인업 의도 해석 소실 | `[2단-라인업] … 해석 실패` 20+건 |

`_attach_cell_verdicts` 는 실패를 삼키고 `cells_status="판정 미수행"` 으로
정직하게 표시한다(설계대로다). 그래서 **카드는 계속 나가고, 아무도
"해석층이 열흘째 죽었다"는 것을 몰랐다.** 정직한 폴백이 결함을 가린 형태다.

## CG-4 [상] 차단기가 프로세스 메모리라 **재기동으로만 풀린다**

`credit_guard.trip_credit` 은 의도적으로 `api_guard.trip_credit`(Redis 영구
차단)을 부르지 않는다 — 충전 후 자동 복구를 위해서다. 그 판단은 옳다.
다만 결과적으로:
- 소진 상태는 `provider._EXHAUSTED` dict 뿐 → **어떤 조회로도 밖에서 안 보인다**
  (`api:blocked:*` 에는 `odds` 하나뿐이고 anthropic 은 없다)
- `/health` · 워치독 모두 이 플래그를 읽지 않는다
- 충전해도 **재기동 전까지 안 풀린다** — 스케줄러는 배포 때만 재기동한다

즉 지금 운영은 **"Anthropic 소진 → 보조 LLM 역할 전멸" 상태로 잠겨 있고,
그 상태를 밖에서 확인할 방법이 없다.**

---

# 요약 보강 (28·29차 추가분)

| 코드 | 한 줄 | 증거 |
|---|---|---|
| 🔴🔴🔴 CG-1 | `provider.py:655` 무조건 `abort_if_credit_gone(role)` — **Anthropic 없는 사슬까지 죽인다** | 운영 컨테이너 재현: interpreter·narrator·intent 3/3 차단 |
| 🔴🔴🔴 CG-2 | 2026-09-06 P0 의 **재발** — 그때 호출부 2곳만 고쳤다 | `test_credit_guard_scope.py` 가 `complete_with_chain` 을 안 지난다 |
| 🔴🔴 CG-3 | `cell_verdicts` **10일 정지**(최신 08-29) · 2단 해석 전멸 · 서술 폴백 | 로그 20+건 · DB 258행 정지 |
| 🔴🔴 CG-4 | 소진 상태가 프로세스 메모리뿐 — **밖에서 안 보이고 재기동으로만 풀린다** | `api:blocked:*` 에 anthropic 없음 |
| 🔴🔴 MON-1 | L2·L3 여전히 **0행** (09-07 수리 후에도) | `pick_targets` 실행 결과 0 |
| 🔴🔴 MON-2 | 감시층이 **추천 건수에 종속** — 추천 0이면 조용히 0행 | `W-MONITOR-DOWN` 은 예외 때만 운다 |

## 지금 상태에서 가장 먼저 볼 것 하나

**CG-1 이다.** 한 줄(`provider.py:655`)이 세 개의 무료 사슬 역할을 죽이고,
그 결과가 `cell_verdicts` 10일 정지 · 2단 해석 전멸 · 서술 폴백으로 이미
나타나 있다. 아래 루프의 provider 별 검사(`_is_exhausted(p.name)`)가
**이미 올바른 판단을 하고 있으므로**, 655행은 사슬에 anthropic 이 있을
때만 유효하다.

⚠️ 다만 **고치기 전에 반대 위험을 먼저 재야 한다** — 655행을 그냥 지우면
잔액 0인 Anthropic 키를 사슬에 anthropic 이 있는 역할에서 계속 때리게 되는지,
아래 루프의 `_is_exhausted(p.name)` 가 그것을 막아 주는지 확인이 필요하다
(읽어 보면 막아 준다. 그러나 **읽은 것과 잰 것은 다르다** — 이 문서의
규칙이다).

## 이 감사에서 코드는 한 줄도 바꾸지 않았다
```
git status --porcelain : 0
HEAD                   : 21e84d2
운영                    : 7c0f9be (scheduler·bot)
테스트                  : 이번 이어달리기에서 재실행하지 않음
                          (마지막 기록 2026-09-07 23:02:40 · 2521 passed)
```

---
---

# 30차 — 판정 본체 정독 시작 · `app/engine/prompts.py` (280줄)

렌더된 **운영 프롬프트 12건**과 대조했다.

## 🔴🔴 PR-1 [최상] 판정 규칙이 **없는 자료 번호**를 가리킨다 — 자료11

`MATCHUP` 템플릿의 절 번호는 `1·2·3·4·5·6·7·8(폐지)·9·12·14` 다.
**10·11·13 절이 없다.** 그런데 `matchup.insert_ledger` 가 `[판정 규칙]` 앞에
한 블록을 끼워 넣는데, 그 머리가 이렇다.
```python
_LEDGER_HEAD = """10. 변수 대장 — **변수의 크기를 여기서 가져온다** (해당 경기만):
```
그 안에 `[참조]`(= `jg["material10"]`)와 `[맥락]`(= `jg["material11"]`)이
**둘 다** 들어간다. 즉 **자료11 은 프롬프트에서 번호를 잃는다.**

그런데 판정 규칙은 자료11 을 이름으로 부른다.
```
· 좌우 **스플릿 성적**(좌투 상대 타율 등)도 시즌 누적이다. 자료11의
  `선발손`은 **오늘의 사실**이라 주는 것이지, 스플릿을 떠올리라는 뜻이 아니다.
```
운영 프롬프트 실측: `자료11` 언급 **1회**, 그러나 `11.` 로 시작하는 절 **0개**.
모델은 "자료11 을 보라"는 지시를 받고 **자료11 을 찾을 수 없다.**

## 🔴🔴 PR-2 [최상] 결론 지시가 **자료12·14 를 제외한다** — 그 둘이 가장 비싼 자료다

```
- 🔴 **마지막에 `결론` 을 내려라. 이것이 이 판정의 답이다.**
  자료1~11 · 변수 · 상황 · 심의를 **전부 한 상에 놓고** 종합해서 …
```
그리고 자료2 설명에도 같은 문구가 있다.
```
**이것도 재료일 뿐 결론이 아니다** — 자료1~11 과 함께 놓고 네가 결론을 내라.
```
`자료1~11` 은 **자료12(실력 레이팅)와 자료14(분기점 조사)를 뺀 범위**다.
운영 프롬프트 실측: `자료1~11` **2회 등장**.

같은 프롬프트가 몇 줄 위에서는 자료12 를 이렇게 못박는다.
```
🔴 **자료12 실력 격차는 기본 축, 최근 폼(자료1·4·9)은 그 위의 조정 축이다.**
```
**"기본 축"이라고 선언한 자료를 결론 종합에서 이름으로 빼놓았다.**
자료14 도 마찬가지다 — 분기점 조사는 DB 를 뒤져 만든 가장 비싼 재료인데
결론 지시에 포함되지 않는다.

이 범위는 자료12·14 가 생기기 **전에** 쓰인 문구가 그대로 남은 것이다
(자료11 까지가 마지막이던 시절). 전형적인 사본 드리프트다.

## 🔴 PR-3 [상] 렌더된 절 순서가 번호순이 아니다 — `… 9, 12, 14, 10`

운영 프롬프트 실측(줄 번호 순):
```
L  3  1. 양팀 최근 3경기 원본 박스스코어
L  8  2. 최근 72시간 뉴스 태그
L 18  3. 오늘 확정 라인업
L 21  4. 선발투수 최근 등판
L 23  5. 직전 판정
L 24  6. 라인업 의도
L 28  7·8. 폐지됨
L 33  9. 양팀 불펜
L 44  12. 양팀 실력 레이팅
L 55  10. 변수 대장        ←── 12 뒤에 10 이 온다
L 81  [판정 규칙]
```
(자료14 는 `[판정 규칙]` 직전, 12 와 10 사이. 09-07 이후 프롬프트 11/12 건에
들어 있다 — 09-06 건에는 없어서 처음엔 누락인 줄 알았다. 그건 자료14 배선
전 프롬프트였다. 결함 아님.)

`insert_ledger` 가 `_RULES_MARK = "[판정 규칙]"` 바로 앞에 끼우기 때문에
**항상 마지막 절**이 된다. 번호는 10 인데 자리는 맨 뒤다.
그리고 **자료13 은 어디에도 없다** — 번호 체계에 구멍이 있다.

## 🔴 PR-4 [상] "기본 축"이 "조정 축"보다 **진폭이 작다** — 상한이 반대로 걸려 있다

프롬프트가 각 축에 준 크기:
```
자료12 실력 레이팅   "격차 70점 ≈ 홈 승률 +10%p"   ← 상한 없음, 그러나 실측 최대 격차 55.5점
자료2 뉴스 태그      "최대 ±3%p"                    ← 명시 상한
자료6 라인업 의도    "뉴스와 합쳐 ±3%p"             ← 명시 상한
[상황] 태그          "%p 반영은 0"                  ← 0 고정
최근 폼(자료1·4·9)   **상한 없음**
```
25차에서 잰 대로 지금 MLB 레이팅 폭은 **55.5점**이고, 최강 홈 대 최약 원정에
홈 이점을 얹어도 자료12 가 낼 수 있는 최대는 **60.0%** 다(±10.0%p).
반면 "조정 축"인 최근 폼에는 상한이 없다.

즉 **"기본 축을 먼저 놓고 폼으로 조정하라"고 지시했지만, 조정 축이 기본 축을
얼마든지 덮을 수 있다.** 13·14차에서 잰 "MLB 에서 자료12 가 홈고정보다
못하다"와 합치면, 지금 자료12 는 **이름만 기본 축**이다.

## ⚠️ PR-5 [중] 변수 형식의 두 규칙이 충돌할 수 있다

```
🔴 `발생 확률 X%` 는 자료14 가 그 리스크의 빈도를 알려줬을 때만 쓴다.
   ⚠️ 자료14 에 답이 없으면 **이 칸을 통째로 빼라.**
   ⚠️ M(기반영)은 대략 `N × 발생 확률` 을 넘지 않는 것이 자연스럽다
① … 참조가 없으면 "근거 없음 — 보수 반영"이라 쓰되 **M 은 0 이 아니어야 한다.**
```
자료14 에 답이 없으면 발생 확률을 못 쓰는데, 그 경우에도 M > 0 이어야 한다.
**M 의 상한을 정할 근거가 사라진 상태에서 M 을 강제**한다. 12차에서 잰
"대조성공 18/638" 을 감안하면 대부분의 변수가 이 경로로 간다.

## ⚠️ PR-6 [하] `fill()` 은 순차 치환이라 주입 여지가 있다

```python
def fill(template, **fields):
    out = template
    for key, value in fields.items():
        out = out.replace("{{" + key + "}}", value)
```
먼저 치환된 값 안에 `{{NEWS_JSON}}` 같은 문자열이 있으면 뒤 라운드에서
치환된다. 재료는 전부 `json.dumps` 를 거치므로 실제로 일어나기는 어렵지만,
뉴스 제목·근거는 **외부 텍스트**다. 실피해는 아직 없다(측정: 운영 12건에
자리표시자 잔여 0).

---

# 31차 — `app/engine/scoring.py` (776줄) 정독

## 🔴🔴 SC-1 [최상·실행측정] `league_era` 인자를 만들어 넘기는데 **쓰지 않는다**

```python
def _suppression(pitcher, s, research=None, league_era: float | None = None):
    league_era = league_era if league_era is not None else s.league_era   # ← 계산만 하고
    ...
    for key, label in (("siera",…), ("era_recent",…), ("era_season",…)):
        val = pitcher.get(key)
        if val is None: continue
        coef = _ratio(float(val), s.league_era, s.exp_pitcher, …)          # ← s.league_era 를 쓴다
```
호출부는 리그별 값을 **정확히 넘긴다**.
```python
# mlb_lambdas:236
coef, label = _suppression(pit[opp], s, research,
    league_era=(s.kbo_league_era if sport == "kbo"
                else s.npb_league_era if sport == "npb" else s.league_era))
```
지역변수 `league_era` 는 **어디서도 읽히지 않는다.** 리그 분기가 통째로 무효다.

실행 측정 (그 리그 **평균** 선발이 받아야 할 계수는 1.0000):
```
설정: league_era=4.20 · kbo=4.66 · npb=3.34 · exp_pitcher=0.50 · clip[0.85,1.18]

MLB 평균 선발 ERA 4.20 → 1.0000   (정상)
KBO 평균 선발 ERA 4.66 → 1.0533   ← 상대 λ +5.3%
NPB 평균 선발 ERA 3.34 → 0.8918   ← 상대 λ −10.8%
```
NPB 는 **모든 선발이 리그 평균보다 10.8% 잘 던지는 것으로** 계산된다.
모듈 머리말이 정확히 이 사고를 경고해 두었다.
> 한 상수를 두 리그에 쓰면 KBO λ가 통째로 낮게 나오고, 그 오차가
> 승패·토탈 전 마켓으로 번진다.

### 지금 실피해는 없다 — 그러나 측정 도구가 전부 오염돼 있다

운영 캐시 확인: 야구 λ 는 꺼져 있다.
```
analysis:mlb:2026-09-07  경기 4 · lam 있음 0 · h2h_lambda_unused 4
  예: lam=None trace=0 missing=[]
```
`pipeline.py:3465` 가 야구에서 `jg["lam"]=None` 으로 끈다. 따라서 카드에는
영향이 없다. **문제는 λ 를 다시 켤지 판단하는 도구들이다** —
`mlb_lambdas` 를 직접 부르는 7개 백테스트 도구
(`backtest_lambda`·`backtest_f5`·`backtest_window`·`backtest_pclaude`·
`ablation_lambda`·`ablation_markets`·`calibrate_distribution`)가 전부 이 계수로
돈다. **KBO·NPB 백테스트 결과는 이 편향을 안고 나온 값이다.**

## 🔴 SC-2 [상] `record_cap_hit`·`cap_alert_count` 가 **전수 미참조** — 승률 절사 경보가 없다

```
$ grep -rn "record_cap_hit|cap_alert_count" app/ tools/ tests/
  → 정의부 외 참조 0건 (테스트도 0건)
```
`cap_probability` 는 절사 문구를 돌려주고 `game_distribution` 이
`jg["prob_cap_note"]` 에 담는다. 그런데 **그 건수를 세는 코드를 아무도
부르지 않는다.** `config.prob_cap_alert_n = 3`("하루 이만큼 초과하면
'모델 점검 필요' 경고")은 **작동한 적이 없다.**

모듈 주석이 밝힌 절사의 의미가 이것이다.
> 상한 초과는 '강한 픽'이 아니라 **모델이 틀렸다는 신호**다.

그 신호를 세는 장치가 죽어 있다. (`tools/verify_section9.py` 만 수동으로
같은 값을 센다 — 사람이 부를 때만.)

## 🔴 SC-3 [중] KBO·NPB 가 **축구의 분산모수 설정을 상속**한다

```python
def dispersion_for(sport, settings=None):
    if s.score_dispersion is not None: return s.score_dispersion
    if sport == "mlb": return s.score_dispersion_mlb        # 3.3 (실측)
    return s.score_dispersion_soccer                        # None → 포아송
```
KBO·NPB 가 **`score_dispersion_soccer` 를 받는다.** 지금은 `None` 이라
포아송이 되고 그 의도는 주석대로 옳다("KBO·NPB 과분산은 측정한 적이 없다").
그러나 누군가 축구 분산을 재서 그 값을 넣는 순간 **KBO·NPB 가 조용히 축구의
튜닝을 물려받는다.** 야구 두 리그를 위한 `None` 상수가 따로 있어야 한다.

## 🔴 SC-4 [중] `_weather_factor` 정규식이 `℃` 를 **절대 못 읽는다**

```python
m = re.search(r"(-?\d{1,2})\s*(?:도|℃|C)\b", text)
```
실행 측정:
```
'기온 24도'   → 24      ✅
'기온 24C'    → 24      ✅
'기온 24℃'    → ❌ 매치 실패
'24℃ 맞바람'  → ❌
'기온 -3℃'    → ❌
```
`℃` 는 단어 문자가 아니라 뒤의 `\b` 가 성립하지 않는다.

우리 수집기는 `weather.py:157` 에서 `f"기온 {round(temp_c)}도"` 로 만들므로
**내부 경로는 무사하다**(그쪽 주석도 이 정규식을 명시한다). 위험한 것은
딥서치가 채운 `research["weather"]` 다 — LLM 이 `24℃` 로 쓰면 기온이 통째로
무시되고 `missing` 에 "날씨"가 들어간다. **그 경로가 실제로 발생했는지는
측정하지 않았다.**

부수적으로, `coef == 1.0`(정확히 20도·무풍)이면 `None` 을 돌려줘
**"날씨 미수집"으로 기록된다.** 중립인 것과 못 받은 것이 같아진다.

## ⚠️ SC-5 [중] `_nearest_line` 이 **0.5 다른 라인의 확률**을 돌려준다

```python
key = min(table, key=lambda k: abs(float(k) - line))
return table[key] if abs(float(key) - line) <= 0.5 else None
```
8.5 를 물으면 9.0 블록이 답이 될 수 있다(차이 0.5 ≤ 0.5). 토탈 0.5점은
푸시 여부까지 바뀌는 크기다. 어느 라인의 값인지 호출부에 알려주지 않는다.

## ⚠️ SC-6 [하] λ 절사 범위가 **세 리그 공용**이다

```python
lam_min = 2.80 · lam_max = 6.20   # 주석: "MLB 현실 범위"
리그 평균 득점: MLB 4.40 · KBO 5.09 · NPB 3.61
```
NPB 평균이 3.61 인데 하한이 2.80 이다 — 약체 타선이 정당하게 그 아래로
갈 여지를 리그 공용 상수가 막는다. SC-1·SC-3 과 같은 형태(리그 상수는
갈라 두었는데 정작 쓰는 곳이 공용값)다.

## ✅ SC-7 정상 확인

- `BASEBALL_SPORTS` 한 곳 정의 — KBO·NPB 를 축구 함수로 보내 무승부 행이
  생겼던 두 번의 실사고가 주석에 남아 있고, 지금은 `is_baseball` 한 변수로
  분기한다.
- `_default_total_lines` 가 **반 점 라인만** 만든다 (정수 라인 푸시 문제를
  실측으로 잡은 흔적: "라인 9.0 언더 41.3% vs 실제 29.3% · 푸시 12.0%").
- `_baseline` 이 키마다 다른 폴백 상수를 쓴다 (xwOBA 에 wOBA 기준을 써서
  전 팀 −4% 하향됐던 사고를 고친 자리).
- `edge_vs_market` 삭제 주석 — "시장과 5% 넘게 벗어나면 지운다"를 없앤 이유가
  적혀 있다. 15차에서 잰 GATE-2(괴리 클수록 틀림)와 정반대 방향의 결정이라,
  **다시 볼 가치가 있는 자리**다.

---

# 32차 — `app/engine/card.py` (766줄) 정독

## 🔴🔴 CARD-1 [최상] 5칸 카드의 "선발 상태" 칸이 **시즌 ERA·WHIP 으로 채워진다**

```python
# _starter_facts
if p.get("era_season") is not None: bits.append(f"시즌 ERA {_f(p['era_season'])}")
if p.get("whip")       is not None: bits.append(f"WHIP {_f(p['whip'])}")

# _scoring_facts (득점 환경 칸)
if p.get("era_season") is not None:
    bits = [f"{name} 선발 {p.get('name')} ERA {_f(p['era_season'])}"]
```
그리고 그 값이 **2단 해석의 정오 검증 근거**가 된다.
```python
CELL_METRICS = {
    "starter": (("era_season", False), ("whip", False), ("ip_avg_recent", True)),
    …
}
SCORING_METRICS = (("starter_era_avg", True), …)   # _pair("pitcher","era_season")
```
`CELL_METRICS` 주석이 그 쓰임을 밝힌다 — *"칸별 **수치 지표와 방향** — 기계적
오독 검증의 근거."* 즉 **시즌 ERA 가 ▲▼ 판정의 맞고 틀림을 가른다.**

대원칙("시즌 집계표는 판정 입력이 아니다")과의 경계가 여기 있다.
판정 프롬프트에는 안 들어간다(운영 12건에 `era_season` 0회 — 확인함).
**들어가는 곳은 카드의 사실 층과 그것을 채점하는 `cell_verdicts` 다.**
`test_season_ban.py` 는 프롬프트·`matchup.py`·`pipeline.py` 만 잠근다 —
`card.py` 는 그 잠금 밖이다.

## ✅ CARD-2 확인 — 사용자 카드에는 지금 안 나간다 (다른 이유로)

운영 `card:mlb:2026-09-07`(2,173자) 전수 검색:
```
'시즌 ERA' 0회 · 'WHIP' 0회 · '선발 상태' 0회 · '득점 환경' 0회 · '▲' 0회 · '▼' 0회
```
5칸 카드 자체가 발송 카드에 실리지 않는다. **그리고 ▲▼ 가 0회인 이유는
CG-1 로 2단 해석이 죽어 있기 때문이다.** 즉 카드에 시즌 스탯이 안 보이는
것은 정책이 막아서가 아니라 **해석층이 고장 나서**다. CG-1 을 고치면
▲▼ 가 살아나고, 그때 시즌 ERA 기반 판정이 사용자 카드에 실린다.

## 🔴 CARD-3 [상] 같은 카드에 **자료9 불펜 시즌 ERA 가 서술로 새고 있다**

운영 카드 상세층 원문:
```
홈팀 Padres는 최근 3경기에서 강한 Yankees 상대로 2승을 거뒀고
불펜 ERA 3.91로 안정적이다.
```
26차에서 잰 자료9 역주입(`_pen` 이 `_bp_recent` 가 지운 era/whip/k9/bb9 를
다시 채움, 12/12)이 **서술을 거쳐 사용자에게 도달한 실물**이다.
판정 근거(M9-1 "원정 시즌 ERA 4.63")에 이어 두 번째 도달 경로다.

## ⚠️ CARD-4 [중] 리그 기준선이 **그 슬레이트 안에서만** 만들어진다

```python
def league_baselines(research_by_side):
    ...
    if len(vals) < 4: continue      # 사분위를 낼 표본이 아니다
```
`research_by_side` 는 그날 슬레이트다. NPB 2경기(2026-09-03)면 side 4개 —
**정확히 하한**이라 q1/q3 가 사실상 최소·최대다. "리그 기준선"이라는 이름과
달리 **그날 몇 경기가 있었나에 따라 기준이 흔들린다.**
주석이 경계한 것("한 팀의 이상치가 기준선을 밀어버리면")은 사분위로 막았지만,
표본이 4일 때는 사분위 자체가 이상치에 붙는다.

## ✅ CARD-5 정상 확인 — 층 분리와 "모름" 처리

- 사실 층에 **LLM 쓰기 접근이 없다**(권한으로 막는다). 머리말이 이유를
  적었다 — "한 번에 시키면 LLM 은 먼저 결론을 세우고 칸을 거기 맞춘다."
- 값이 없으면 **모름**이고 0 으로 채우지 않는다("소모 0"이 "충분함 ▲"으로
  오독되는 것을 막는다). `MAX_UNKNOWN=2` 초과면 판정하지 않는다.
- `SCORING_METRICS` 의 True/False 가 "유리한가"가 아니라 "득점이 느는가"임을
  주석으로 명시하고 `CELL_METRICS` 와 섞지 말라고 못박았다.
- `_batting_facts` 가 경기 단위 값(발표 시각·변경 이력)만으로 칸을 '채워짐'
  으로 만들지 않는다 — 테스트가 실제로 잡았다는 주석이 붙어 있다.

---

# 33차 — `app/engine/deepsearch.py` (1,007줄) 정독

## ❌ 먼저 제 오류 정정 — `LLM_SEED`

23차 LLM-1 에서 *"`LLM_SEED` 는 두 서비스 모두 미설정이다 — 즉 seed 를
보내지 않는다"* 고 썼다. **틀렸다.** 환경변수가 비어 있는 것은 맞지만
`config.Settings.llm_seed` 의 기본값이 **20260905** 이고, 운영 설정 객체를
직접 읽어 확인했다: `llm_seed=20260905`. **seed 는 전송된다.**
`printenv` 가 비었다는 것만 보고 결론을 낸 것이 잘못이다.

## 🔴🔴 DS-1 [최상] 딥서치가 **KBO·NPB 에서 꺼져 있다**

```
운영 설정: deepsearch_sports = 'mlb,soccer'
def deepsearch_enabled(self, sport): return sport.lower() in {'mlb','soccer'}
```
자동 발송의 주력 두 리그가 **트리거형 딥서치 대상이 아니다.**
그런데 T4·T5·T6(선발 변경·라인업 이상·최초 공시)는 **야구 라인업 경로에
붙어 있는 트리거**다. 모듈이 스스로 그 사고를 기록해 두었다.
> 결과: **T4·T5·T6 가 야구에서 통째로 죽어 있었다.** 딥서치가 꺼져 있어도
> "어떤 경기가 걸리는가"를 관찰하는 것이 이 단계의 목적인데 그 관찰이
> 한 건도 남지 않았다(실측 2026-09-04 KBO 저녁 슬레이트, 재판정 8건 전부).

버그(`'str' object has no attribute 'get'`)는 고쳤지만 **`deepsearch_sports`
는 여전히 `mlb,soccer`** 다. 즉 KBO·NPB 는 판별·기록은 되지만 조사는
`status="disabled"` 로 끝난다.

운영 Redis 확인 — 딥서치 결과 키는 **MLB 만** 있다.
```
deepsearch:MLB:4096:2026-09-07   triggers=["T3_추가확인"]
deepsearch:MLB:4099:2026-09-07   triggers=["T1_경계확률","T3_추가확인"]
deepsearch:MLB:4101:2026-09-07   triggers=["T1_경계확률","T3_추가확인"]
deepsearch:count:mlb:2026-09-07  7
deepsearch:rejudge:{4092,4095,4097}:…  각 1
(kbo·npb 키 0건)
```

## 🔴 DS-2 [상] 저장된 딥서치 "발견"이 **전부 '못 찾았다'** 이다

운영 3건 전수:
```
4096 "제공된 최신 기사들(9월 6~7일자) 어디에도 원정 선발 J. Cabrera의 최근 실전
      투구 이닝, 투구 수, 혹은 금일 선발 확정 여부가 언급되지 않음."
      소스유형=뉴스 · url="수집된 기사 …"
4099 "제공된 자료에서 Nick Pivetta의 금일 경기 투구 수 제한 관련 정보를 찾을 수 없음"
      소스유형=기록 · url="제공된_기사목록_전체"
4101 "MLB.com 공식 기사(5시간 전)에서 오타니가 4경기 연속 선발 라인업에서 제외됐으나
      월요일 복귀가 예상된다고 보도함. 다만 금일 경기 선발 …"   ← 유일하게 사실이 있다
```
3건 중 2건이 **"없음"을 사실 칸(`발견.사실`)에 적었다.**
`research/validate.py` 의 `UNAVAILABLE_MARKERS` 는 리서치(`deep.py`) 응답에
적용되고, **딥서치 결과에는 그 게이트가 없다.** 그래서 "찾을 수 없음"이
`발견` 배열에 사실로 남는다. `url` 도 `"제공된_기사목록_전체"` 처럼
URL 이 아니다.

27차 RV-2 에서 "validate.py 는 이 감사에서 본 것 중 반대 위험을 가장 성실히
다룬 코드"라고 적었는데, **그 게이트가 딥서치 경로에는 안 붙어 있다.**
(CLAUDE.md 규칙: *"새 리서치 필드를 추가할 때 `validate.py` 정책을 함께
정의한다"* — 딥서치 `발견` 은 그 정의가 없다.)

## ✅ DS-3 정상 확인 — 배당 격리는 코드가 강제한다

```python
_ODDS_WORDS = ("배당","머니라인","스포츠북","북메이커","내재확률","언더독",
               "odds","moneyline","sportsbook","implied","favorite","-1.5","+1.5")

def strip_odds(data):
    발견에서 배당 문장 제거
    if _odds_tainted(조정.사유): 조정.pop("p_home")   # 숫자까지 폐기
```
**증거만 지우고 숫자는 남기는 반쪽 처리를 하지 않는다** — 조정 사유가
배당이면 조정 자체를 버린다. 주석이 그 이유를 명시한다.
⚠️ 다만 21차 SIT-1 에서 본 대로, **자료2 상황 태그는 이 필터를 타지 않는다.**
`actionnetwork.com` 의 "MLB Odds" 기사가 `roster_move` 로 프롬프트에 들어간
경로가 그것이다.

## ✅ DS-4 정상 확인 — 트리거 설계

- `triggers()` 는 T1~T5, `run_for_rejudge()` 는 **T6·T4·T5** 를 따로 본다.
  T6 는 정의만 있고 `triggers()` 에 없어 처음엔 죽은 상수로 보였는데,
  재판정 경로에 별도로 붙어 있다 — 결함 아님.
- `first_lineup_evidence` 가 **껍데기 dict 를 "직전 있음"으로 읽지 않는다**
  (`_names(_lineup_of(...))` 로 안을 본다). 그 주석에 "dict 가 truthy 라고
  읽으면 T6 가 영원히 안 걸린다"는 실측이 남아 있다.
- 모양을 아는 곳을 `_lineup_of`+`_names` 한 쌍으로 모았다 — KBO·NPB 는 타순이
  **문자열**, MLB 는 dict 라 같은 실수를 두 번 겪은 뒤의 조치다.
- T6 는 상한 면제, 중복은 `(game_id, 라인업 서명)` 으로 막는다.
- 발동 근거를 `SRC_MODEL`/`SRC_FACT`/`SRC_BOTH` 로 구분해 남긴다 —
  "모델 자백으로 걸린 건과 사실로 걸린 건은 완전히 다른 데이터다."

---

# 34차 — `app/engine/fact_audit.py` (643줄) · 감시 L1 실적

운영 `judgement_audit` 전수 (1,154행 · 청구 12,538건):
```
verified 9,687 · derived 977 · not_found 1,462(11.7%) · mismatch 412(3.3%)
빈 행 0

일자·종목별 (mismatch)
  09-03 kbo 4 · mlb 7 · npb 0
  09-04 kbo 12 · mlb 265 · npb 3     ← MLB 499행에 not_found 948
  09-05 kbo 26 · mlb 10 · npb 13
  09-06 kbo 15 · mlb 20 · npb 23
  09-07 mlb 14
```
L1 은 **살아 있고 신호를 낸다.** 그런데 그 신호의 일부가 오탐이다.

## 🔴🔴 FA-1 [최상·실행측정] `\b` 가 한국어 조사 앞에서 소수점을 잘라 **정확한 인용을 환각으로 찍는다**

```python
(r"\b(1\d{3}(?:\.\d+)?)\b", "elo", ("레이팅",)),
```
실행 측정:
```
'원정 1475.6으로'                     → ['1475']      🔴 소수점 잘림
'홈 1522.1 대 원정 1475.6으로 …'       → ['1522.1', '1475']
'레이팅 1475.6 이다' / '1475.6,' / '1475.6)'  → ['1475.6']  ✅
```
소수 뒤에 **한글 조사**가 붙으면(`…6으로`) 뒤쪽 `\b` 가 성립하지 않아
정규식이 되돌아가 **정수만** 잡는다. 그러면 감시는 `claimed=1475` 대
`source=1475.6` 을 보고 **mismatch** 를 낸다.

운영 elo mismatch **2건 전수 = 2건 모두 이 오탐이다.**
```
claimed=1492.0  source=1492.2  | 실력 레이팅 원정 1507.6 vs 홈 1492.2로 …
claimed=1475.0  source=1475.6  | 자료12: 홈 1522.1 대 원정 1475.6으로 …
```
두 인용 모두 **원문과 글자까지 같다.** 판정은 옳았고 감시가 틀렸다.

🔴 **이 저장소에서 같은 실수가 세 번째다.**
```
SIT-1   registry `" il "` → `_norm.strip()` 이 공백을 지워 "il" 부분일치 (오탐 9/10)
SC-4    weather `(?:도|℃|C)\b` → '℃' 뒤 `\b` 불성립으로 기온 미인식
FA-1    fact_audit `(1\d{3}(?:\.\d+)?)\b` → 한글 조사 앞에서 소수 절단
```
셋 다 **`\b`·`strip` 을 비ASCII 텍스트에 쓴 것**이 원인이다.

## 🔴 FA-2 [상] **임계 서술**("5이닝 미만")을 인용 수치로 추출한다

```
'자료14 Derek Law 같은처지 5이닝 미만 95%'  → 이닝 인용 5.0 으로 추출
                                          → 원문 최근접 6.0 → mismatch
'최근 4경기 모두 5이닝 이상 소화'            → 같은 방식
```
자료14 는 프롬프트가 **그렇게 쓰라고 지시한 형식**이다.
> `같은처지` … "5이닝 이상 35/51(69%)" 처럼 실제로 몇 번 중 몇 번이었는지를 준다

즉 판정이 규칙대로 쓴 문장을 감시가 환각 후보로 읽는다.
실측: mismatch 412건 중 **26건(6%)** 이 `이닝 이상/미만` 문구다.

## 🔴 FA-3 [중] mismatch 의 21%가 **자릿수 의심 구간**에 있다

```
|claimed − nearest_in_source| < 1.0  →  88/412 (21%)
   그중 claimed 가 정수                →  12건
단위별 mismatch: ip 264 · r 79 · so 41 · era 13 · bb 7 · er 2 · runs 2 · elo 2 · hits 1 · elo_gap 1
```
모듈은 이미 두 종류의 자릿수 문제를 잡아 두었다 —
`_IP_NOTATION`(5.2 = 5⅔)과 `written_at`(인용이 쓴 자릿수로 원문을 줄인다).
그럼에도 21%가 1.0 미만 차이로 남는다. **이 구간을 전수로 눈으로 보기 전에는
"환각률 3.3%"를 그대로 믿으면 안 된다.**

## 🔴 FA-4 [중] 09-04 MLB 하루가 전체 mismatch 의 64%를 차지한다

```
09-04 MLB  499행 · verified 3,660 · not_found 948 · mismatch 265
다른 날 MLB  50~130행 · mismatch 7~20
```
행 수도 mismatch 도 그날만 한 자릿수 다르다. 하루 499행은 재판정 폭주
(LED-2·LED-4 와 같은 형태)로 보이지만 **원인을 특정하지 않았다.**
집계에 이 하루를 넣은 채 "환각률 3.3%"를 말하면 그 수치는 한 날에 끌려간다.

## ✅ FA-5 정상 확인 — 이 모듈은 오탐을 가장 많이 잡아 온 코드다

주석에 남은 **실측 기반 수정 이력**:
- `_IP_NOTATION` — 원문은 소수(5.667), 판정은 야구 표기(5.2). 숫자만 비교해
  정확한 인용이 환각으로 찍혔다(2026-09-05 game=1711).
- `DERIVED_MARKERS` 에 "합계·총·도합" 추가 — "최근 4경기 27이닝"의 27을
  경기별 이닝(≈8)과 비교해 19이닝 차 환각으로 찍었다(2026-09-03 NPB 2건).
- `written_at` — tolerance 0.05 가 1자리 절사 최대오차(0.0999)보다 작아
  정상 인용을 걸렀다.
- 자료9 `실점`·`경기당실점` 키 추가 — 목록에 없어 불펜 실점이 감시에
  통째로 안 보였다(2026-09-05).
- 자료12 elo 를 **같은 커밋에서** 감시 목록에 넣었다 — "자료12 가 감시 없이
  배포됐던 실수를 되풀이하지 않는다."
- `배율` 패턴에서 캡처 그룹을 하나만 두라는 주석(교대에서 `group(1)` 이
  None 이 되는 것을 실제로 겪었다).

설계도 옳다 — **`mismatch` 만 경보**하고 `not_found` 는 "환각 후보, 확정
아님"으로 둔다. 판정 뒤에 읽고 되먹이지 않는다.

---

# 35차 — `app/engine/interpreter.py` (528줄) · 감시 L2 이전의 2단 해석

## 🔴🔴 INT-1 [최상] 2단이 **시즌 ERA 로 ▲▼를 매기고, 시즌 ERA 로 그 판정의 정오를 가른다**

시스템 프롬프트가 방향을 못박는다.
```
[칸별 방향 — 이 지표가 커지면 어느 쪽인가]
- 선발 상태: **ERA·WHIP가 낮을수록 ▲**, **평균 이닝이 길수록 ▲**
```
그리고 `direction_check` 가 같은 지표로 "방향 오독"을 판정해 **그 칸을 버린다**.
```python
from app.engine.card import CELL_METRICS
#   "starter": (("era_season", False), ("whip", False), ("ip_avg_recent", True))
if all(votes) and symbol == "▼":  return "수치는 유리를 가리킨다 — …"
if not any(votes) and symbol == "▲": return "수치는 불리를 가리킨다 — …"
```
즉 **시즌 ERA 가 나쁜 선발을 최근 폼 근거로 ▲ 로 읽으면 그 칸이 폐기된다.**

판정 프롬프트의 대원칙과 정면으로 어긋난다.
```
· 선발은 자료4(최근 등판)가 전부다. 최근 등판이 2경기 이하면 …
  시즌 라인으로 메우지 말고 확신도를 낮추고 0.50 쪽으로 당겨라.
- 시즌 **집계표**(타율·ERA·…)는 쓰지 않는다.
```
**같은 시스템의 두 층이 서로 반대 규칙으로 돌고 있다.**
1단 카드는 시즌 ERA 를 사실로 싣고(CARD-1), 2단은 그것으로 ▲▼를 매기고
그 정오를 다시 시즌 ERA 로 검증하는데, 3단 판정은 시즌 ERA 를 쓰지 말라는
지시를 받는다.

## 🔴 INT-2 [상] 방향 검증의 기준선이 **그날 슬레이트**라 작은 슬레이트에서 무력하다

```python
baselines = league_baselines([(res, side) for _, res in pairs
                              for side in ("home","away")])
# card.league_baselines: if len(vals) < 4: continue
# direction_check:       if q1 <= val <= q3: continue   ← 사분위 안이면 검증 안 함
```
NPB 2경기 슬레이트면 side 4개 → q1·q3 가 사실상 2번째·3번째 값이라
**거의 모든 값이 사분위 안**에 들어와 오독 검증이 한 번도 발동하지 않는다.
`interpret_slate` 의 docstring 이 그 한계를 스스로 적는다 —
*"경기 하나만 보고는 '평소보다 많이 던졌다'를 말할 수 없다."*
그 말은 **경기 두 개일 때도 거의 그렇다.**

## 🔴 INT-3 [상] 이 모듈이 CG-1 의 직접 피해자다 (코드 확인)

```python
res = await complete(ROLE, [...], system=SYSTEM, schema=VERDICT_SCHEMA, …)
```
`ROLE="interpreter"` · 사슬 `groq → gemini`(둘 다 무료). 그런데
`provider.complete_with_chain` 이 맨 앞에서 `abort_if_credit_gone(role)` 을
무조건 부른다(CG-1). Anthropic 잔액이 끊긴 순간부터 **이 모듈이 통째로
예외로 죽고**, `_attach_cell_verdicts` 가 그것을 삼켜 `cells_status="판정
미수행"` 으로 정직하게 표시한다. 그래서 카드는 계속 나갔다.
→ `cell_verdicts` 258행, 최신 **2026-08-29**(MON-3)의 원인이 여기서 닫힌다.

## ⚠️ INT-4 [중] `cell_verdicts` 키와 분석 캐시 키가 다를 수 있다

```python
out[jg.get("game_id")] = per_game               # 반환은 game_id
gid = jg.get("db_id") or jg.get("game_id")      # 적재는 db_id 우선
await record_verdicts(pool, gid, side, …)
```
`db_id` 가 있는 경로에서는 **적재 키와 조회 키가 갈린다.** 지금
`cell_verdicts` 가 비어 있어 실피해를 잴 수 없다 — CG-1 을 고친 뒤
`db_id` 가 실제로 설정되는 경로가 있는지 확인해야 한다.

## ✅ INT-5 정상 확인 — 차단벽과 폐기 사유 분리

- `build_payload` 가 **그 팀의 사실만** 담는다. 상대·확률·배당이 한 조각도
  들어가지 않고, 테스트가 그 함수를 직접 검사한다. 머리말이 이유를 적었다 —
  "한 번에 시키면 LLM 은 먼저 결론을 세우고 칸을 거기 맞춘다."
- 폐기 사유를 **`인용 없음` 과 `방향 오독` 으로 나눠 센다** — "지어내기와
  오독은 다른 문제이고 대응도 다르다."
- `direction_check` 가 `=` 를 오독으로 치지 않고, 지표가 갈리면 판정하지
  않는다. 사분위 밖일 때만 본다(중앙값 기준이면 0.004 차이도 폐기했던
  실측 2026-08-27 을 고친 자리).
- `apply_weight_rule` 이 **양쪽 모두 경쟁권 밖이면 순위 ▲를 지운다** —
  "없는 동기 차이를 만들어내지 않는다." 그리고 문턱을 LLM 이 아니라
  config 가 갖는다("LLM 이 문턱을 판단하게 두면 측정되지 않은 튜닝이 된다").
- `out_of_contention` 이 선두 게임차만 보지 않는다(선두차 16.5 인데 컷차
  9.0 이던 한화 실측).

---

# 36차 — `app/engine/branch_resolve.py` (619줄) · 자료14

## ✅ BR-1 — **이 감사에서 본 것 중 가장 건강한 모듈이다**

운영 프롬프트 11/12 건에 자료14 가 실려 있고, 실제 답이 붙어 있다.
```
유형 분류:  기록형 21 · 실시간형 4 · 미분류 2
답:        답 있음 22 · 사유만 5 · 오늘의사실 11
```
실물(judge_prompt:4092):
```json
{"유형":"기록형","질문":"Grant Holmes 가 5이닝을 넘기는가",
 "답":{"away":{
   "본인":{"등판":[{"날짜":"2026-09-02","역할":"선발","이닝":3.0,"상대타자":9,"실점":0},
                  {"2026-08-28",5.0,23,3},{"2026-08-20",6.0,22,0},{"2026-08-15",3.67,20,6}],
          "선발수":4},
   "소속팀":{"창":"최근 30일","표본":25,"평균이닝":5.4,"5이닝이상":"19/25 (76%)"},
   "같은처지":{"조건":"직전까지 선발 등판 4건인 투수","표본":51,
              "평균이닝":5.31,"5이닝이상":"35/51 (69%)"}}}}
```
본인 표본 4건짜리 질문에 **리그 51건**이 붙는다. 새 크롤 없이
`pitcher_appearances`(6,628행)·`games` 재사용만으로 만든다.
`오늘의사실`(라인업 확정_T마이너스분 151 · 결장 투수자원 수·명단)도 함께 온다.

## ⚠️ CONF-2 정정 — "분기점 없음과 전부 해결을 구분 못 한다"는 절반만 맞다

29차 CONF-2 에서 `confidence.branch_unresolved` 가 `분기점_미해결: false`
36/36 인 것을 두고 "안 물었는지 다 풀었는지 모른다"고 적었다.
자료14 실측으로 답이 나온다 — **같은 날 프롬프트에 답이 붙은 항목이 22건**
이므로 `false` 는 "물어서 풀었다" 쪽이다.
남는 지적은 하나다: **원장(`confidence_probe`)에 항목 수가 없어 그 판별을
원장만으로는 못 한다.** 프롬프트를 따로 뒤져야 알 수 있다.

## 🔴 BR-2 [중] `미분류` 2건 — 해결사가 없는 질문이 남는다

```
질문 표본 중: "Jonah Tong의 투구수 제한 등 세부 등판 운용 계획"
              "Jonah Tong 선발 표본 부재에 따른 조기 강판 리스크"
```
`_LIVE_PAT` 에 `제한\s*여부` 는 있지만 `제한 등`·`운용 계획` 은 없고,
`_RECORD_PAT` 에는 `투구` 가 있어 걸릴 법한데 실제 분류는 갈렸다.
분류 패턴이 **실제로 온 문장을 보고 넓혀 온** 이력(주석에 3회 기록)이라
같은 방식으로 계속 넓혀야 하는데, **`미분류` 건수를 세는 감시가 없다.**

## ✅ BR-3 정상 확인 — 설계 규약

- 새 크롤 소스를 만들지 않는다(전부 기존 테이블 재사용).
- **%p 를 만들지 않는다** — 사실만 주고 확률 변환은 판정의 몫.
- 답이 없으면 `사유` 만 적는다("모른다도 판정에 필요한 정보다").
- `classify` 가 **기록형을 뉴스형보다 먼저** 본다. 실측 6건이 전부 기록으로
  답할 질문인데 뉴스 검색기로 가서 미확인이 됐던 사고의 수정이다.
- `_LIVE_PAT`("구단 발표"·"제한 여부")를 기록형보다 **앞**에 둔 이유도
  실측이다 — opus 가 리그 표본을 받고도 `추가확인` 에 같은 질문을 다시
  적어 중복이 됐다.
- `_RECORD_PAT` 확장 때 **반대 위험(뉴스형을 빼앗음)을 실변수 638건으로
  측정**했다고 주석에 적혀 있다. 21차 SIT-1(측정 없이 넓혀 오탐 폭증)과
  정반대의 모범 사례다.

---

# 37차 — 🔴🔴🔴 M9-1 근본원인 확정: 두 가드가 **서로를 정확히 무력화**한다

26차에서 "판정이 시즌 ERA 4.63 을 근거로 썼다"를 실측했다. 원인을 코드로
끝까지 특정했다.

## CR-1 [최상·코드확정] 호출 순서가 주석이 요구한 것과 **반대**다

```python
# app/pipeline.py
2746  # [C1 2026-09-04] 자료9 를 **최근 폼으로 교체**한다.
2747  #   🔴 대원칙: 시즌 누적은 판정 입력이 아니다. 시즌 ERA 를 지우고
2748  #      최근 3경기 실점 + 최근 3일 가용성을 넣는다.
2749  #   ⚠️ 시즌 부착(위 `mlb_team_pitching` 등)보다 **뒤**여야 지워진다.
2751          from app.engine.bullpen_recent import attach as _bp_recent
2753          await _bp_recent(pool, jg)          # ← 시즌 값을 pop 한다
...
2772          from app.collectors.mlb_team_pitching import attach as _pen
2774          await _pen(jg, redis=redis)         # ← 21줄 **뒤**에서 다시 채운다
```
주석은 `mlb_team_pitching` 이 **"위"**에 있다고 적었는데, 실제 호출은
**아래(2774)** 다. 요구 조건이 코드에서 거꾸로다.

## CR-2 두 함수가 **정확히 상보적**이라 100% 되살아난다

```python
# app/engine/bullpen_recent.py:140,159
#   🔴 시즌 값(`era`·`whip`·`k9`·`bb9`)을 **지운다.** 남겨 두면 프롬프트에 …
dst.pop(stale, None)

# app/collectors/mlb_team_pitching.py:attach
if dst.get("era") is None:              # ← _bp_recent 가 방금 None 으로 만든 상태
    dst["era"] = blk["era"]
for k in ("whip", "k9", "bb9"):
    dst.setdefault(k, blk[k])           # ← 역시 방금 비워진 자리
```
`_pen` 의 `setdefault`/`is None` 가드는 **"이미 다른 소스가 채웠으면 덮지
않는다"** 는 뜻인데, `_bp_recent` 가 바로 앞에서 비워 놓았으므로
**언제나 채워진다.** 실측 12/12 와 정확히 일치한다.

## CR-3 그 값의 정체 — **팀 시즌 투수 ERA** (구원 전용도 아니다)

```python
# mlb_team_pitching.py
CACHE_TTL = 12 * 3600          # 시즌 누적이라 하루 두 번이면 충분
data = await StatsAPIClient().get("/teams/stats",
        {"season": season, "group": "pitching", "stats": "season", …})
```
모듈 자신이 밝힌다.
> ⚠️ **KBO·NPB 와 같은 기준을 쓴다.** 두 리그 모두 `team_era`(팀 투수 방어율)를
> 자료9 에 넣는다 — 구원 전용 ERA 가 아니다. … 그래서 라벨도 "팀 투수 ERA"로
> 정직하게 적는다.

그런데 프롬프트의 자료9 라벨은 **"양팀 불펜 — 최근 폼만"** 이다.
모델은 그것을 불펜 최근 폼으로 읽고, 실제로 그렇게 인용했다
(M9-1: "자료9 불펜 폼에서 홈(3경기 6이닝 1실점, ERA 3.68)이 원정(시즌 ERA 4.63) 대비").

## CR-4 상류에도 같은 값이 있다 — `deep.py` 스키마가 **직접 요구한다**

```
# app/research/deep.py  _SCHEMA_MLB
"home_pitcher": {…, "siera": 3.95, "xfip": 4.02, "fip": 4.10,
                 "era_recent": 5.40, "era_season": 3.86, …},
"home_offense": {…, "vs_lhp_woba": 0.330, "vs_rhp_woba": 0.312},   ← 좌우 스플릿
"home_bullpen": {"era": 3.85, "fip": 4.02, "ip_last3d": 8.2, "closer_available": true},
```
리서치 스키마가 **시즌 ERA·FIP·좌우 스플릿·불펜 시즌 ERA 를 명시적으로
요구**한다. 대원칙(2026-09-04)이 자료7·8 을 폐지하고 자료9 를 최근 폼으로
바꾼 뒤에도 **이 스키마는 개정되지 않았다.**

즉 시즌 값이 들어오는 경로가 셋이다.
```
① deep.py 스키마 → research.{side}_bullpen.era / {side}_pitcher.era_season
② mlb_team_pitching → research.{side}_bullpen.era  (statsapi 팀 시즌)
③ card.py         → 5칸 "선발 상태" 사실 + CELL_METRICS 방향 검증
```
①②는 자료9 를 거쳐 **판정 프롬프트**로, ③은 **2단 해석·cell_verdicts** 로 간다.
`test_season_ban.py` 는 셋 중 **하나도** 잠그지 않는다 —
자료7·8 자리표시자와 `matchup.py`·`pipeline.py` 의 심볼만 본다.

## 범위 — MLB 만이다

`mlb_team_pitching.attach` 는 `sport != "mlb"` 면 0 을 돌려준다.
KBO·NPB 의 `team_era` 는 `naver_kbo.py:319`·`npb_stats.py:225` 가 채우고
`_bp_recent` 가 그 뒤에 지우므로 순서가 맞다.
운영 프롬프트 12건이 전부 MLB 라 12/12 로 나온 것도 이와 일치한다.

---

# 38차 — `app/pipeline.py` `_compute_picks`·`qualified_singles` (3412~3878)

## 🔴🔴 PL-1 [최상] 야구의 `p_final` 은 **LLM 숫자 그대로**다 — 앙상블이 없다

함수 docstring:
```
[5] p_final = 0.5*p_model + 0.5*p_claude (시장 가중치 0).
```
그런데 야구 분기는 `blend()` 를 **부르지 않는다**.
```python
if sport in BASEBALL_SPORTS:
    ph = jg.get("p_claude")
    jg["lam"] = None; jg["model_valid"] = False; jg["prob_adjust"] = None
    p_final = {jg["home"]: round(float(ph),4), jg["away"]: round(1-ph,4)}
```
즉 **KBO·NPB·MLB 의 최종 확률 = 판정 LLM 이 말한 `p_home` 하나**다.
λ 도, elo 도, 시장도 확률에 들어가지 않는다(자료12 는 프롬프트 재료로만 간다).

이것이 15차 GATE-3(확률 비단조: 홈 0.55–0.60 구간 32.1%)의 의미를 바꾼다 —
**평활할 두 번째 축이 아예 없다.** 모델 평균이 있었다면 LLM 의 잡음이
절반으로 줄었을 것이고, 그 축을 끈 것은 의도(λ off)다.

## 🔴🔴 PL-2 [최상·실측] 2026-09-07 MLB 는 **최고 확률이 0.57** 이라 추천이 0 이었다

운영 캐시를 그대로 재계산했다.
```
경기 4 · picks 4 · recommended 0 · qualified_singles 재계산 0
  game=4100 '세인트루이스 카디널스 승'  p=0.57  approved=True  recommended=False
  game=4102 '토론토 블루제이스 승'      p=0.57  approved=True  recommended=False
  game=4099 '샌디에이고 파드리스 승'    p=0.56  approved=True  recommended=False
  game=4101 'LA 다저스 승'             p=0.53  approved=True  recommended=False
```
네 경기 전부 **승인(approved)** 됐고 확률은 0.53~0.57 이다.
추천 하한은 **0.58**. 즉 **1%p 차이로 슬레이트 전체가 0 건**이 됐다.

LED-3("09-07 추천 0건")의 원인이 여기서 닫힌다. 고장이 아니라 **분포와 문턱의
문제**다. 25차 ELO-3(자료12 최대 60.0%)·15차 GATE-3(0.55–0.60 이 최악 구간)과
같은 자리를 가리킨다 — **판정이 내는 확률이 0.5 부근에 몰려 있고, 문턱이
그 봉우리 바로 위에 있다.**

## 🔴 PL-3 [상] 마켓 보드가 사실상 **h2h 2행뿐**이다

```
board game=4099 행 2 승인 2 [('h2h','San Diego Padres',0.56), ('h2h','Washington Nationals',0.44)]
board game=4100 행 2 승인 2 · game=4101 행 2 · game=4102 행 2
```
토탈·런라인·F5 행이 **한 줄도 없다.** 배당(`alt_markets`)이 비어 있기 때문이다
(15차: 채점 134경기 `odds` 0건 · LIVE-3: oddsportal 503).
`scoring.mlb_market_probs` 가 만드는 totals/spreads/f5 는 λ 가 꺼져 있어
애초에 생성되지 않는다.

그래서 "전 마켓 보드"·"조합(파레이)"·"가치 게이트"가 **구조적으로 작동할 수
없다.** 카드가 그것을 그대로 적는다 —
*"조합: 승패 전 마켓 검토 — 승인 레그가 0경기분뿐이라 조합 성립 불가"*.

## 🔴 PL-4 [중] `recommended` 표시가 **문자열 `desc` 매칭**이라 어긋날 수 있다

```python
board = qualified_singles(judge_games, settings)     # 보드 전체에서 자격 통과
recommended = clean[: mode["max_picks"]]
rec_keys = {(r["game_id"], r["desc"]) for r in recommended}
for p in picks_out:
    p["recommended"] = (p["game_id"], p.get("desc")) in rec_keys
```
- `picks_out` 의 `rep` 는 `approved or h2h or scored` 중 **p 최대**
- `qualified_singles` 는 `approved and qualifies(...)` 중 **p 최대**

두 조건이 다르므로 **다른 마켓이 뽑힐 수 있다.** 그러면 그 경기의 `picks`
엔트리는 `recommended=False` 가 되고, `pick_ledger.gate_result_of` 는
`pick.get("recommended")` 만 보므로 **원장에 `보드만` 으로 남는다** —
사용자 카드에는 `analysis["recommended"]` 를 통해 추천이 나가는데도.

지금은 보드가 h2h 2행뿐이라(PL-3) 두 선택이 같아 **발현하지 않는다.**
배당이 복구돼 토탈·런라인 행이 생기는 순간 원장과 카드가 갈린다.
(`qualified_singles` docstring 자체가 같은 유형의 과거 사고를 적어 두었다 —
"사용자에게는 '단식 없음 — 관망'이라 하면서 같은 베팅을 조합 레그로 추천했다.")

## ✅ PL-5 정상 확인

- 야구에서 `model_valid=False` 로 두는 이유가 주석에 있다 — True 면
  `markets._axis_model` 이 없는 `jg["p_model"]` 을 인덱싱해 **야구 슬레이트가
  통째로 KeyError 로 죽는다**(실측 2026-08-30).
- 세 방식 확률(`p_heuristic`·`p_learned`·`p_claude`)을 **h2h 일 때만** 기록한다
  — 토탈 픽에 승패 확률을 실으면 그 픽 결과로 채점돼 원장이 오염된다.
- `qualified_singles` 가 **보드 전체**를 심사한다(대표 1건만 보던 2026-08-26
  사고의 수정). `per_game=1` 로 같은 경기 두 마켓을 이중 계산하지 않는다.
- 판정 미수신이어도 보드는 만들고 추천만 뺀다.

---

# 39차 — `app/pipeline.py` `build_analysis` (1321~2515)

## 🔴🔴 PL-6 [최상·설계확정] 야구는 `build_analysis` 에서 **배당을 조회하지 않는다** — PL-3 의 뿌리

```python
# 배당 조회는 경기가 있는 리그 키만 (크레딧 절약)
if sport in ("mlb", "kbo", "npb"):
    # 야구는 배당·토탈 라인을 조회하지 않는다. snapshot_odds 도 0을 반환한다.
    active_keys = []
```
그래서 `alt_markets`(토탈·런라인 라인 목록)가 비고, λ 도 꺼져 있어
(`scoring.mlb_market_probs` 미호출) **마켓 보드가 h2h 2행으로 고정**된다.
PL-3 에서 실측한 "board 행 2 · 승인 2" 가 이것이다.

파급 사슬이 하나로 이어진다.
```
야구 배당 미조회 + λ off
  → 보드가 h2h 2행뿐
  → 토탈·런라인·F5 후보 0
  → 가치 게이트(p×배당)가 잴 것이 없다     (15차 GATE-6·odds 0/134)
  → market_edge / edge_status 영영 0        (2차 · 15차)
  → 조합(파레이) "성립 불가"                 (카드 원문)
```
설계 의도는 코드가 밝힌다 — *"배당이 판정에 스며들면 안 되기 때문이고,
그 격리는 옳다."* 그리고 판정 **뒤**에 `refresh_odds_for_game` 으로 다시
붙인다(2026-09-04 수정). 즉 **격리는 지켜지고 있고, 잃은 것은 마켓 다양성**이다.

## ✅ PL-7 — "추천이 거의 안 나오는 것"은 버그가 아니라 **선언된 의도**다

```python
#   ⚠️ Statcast에 해당하는 타구 데이터가 없다 → λ를 산출할 수 없다.
#      p_model은 무효가 되고 확률은 **판정(p_claude) 단독**으로 간다.
#      그래서 2-소스 룰의 '모델' 축이 서지 않으며, 추천 자격은 대부분
#      통과하지 못한다 — 이는 버그가 아니라 **의도된 보수성**이다.
```
그리고 알림에서도 0 건을 실패로 세지 않는다.
```python
await record("게이트·발송", _gate_ok, len(_scheduled), …, zero_ok=True,
             impact="판정 없는 경기는 카드를 보내지 않습니다")
#  [§8-15] **추천 0건은 실패가 아니다.** … 진짜 실패는 마켓 보드 자체가 비었을 때다
```
→ **LED-3·PL-2 를 "고장"으로 읽으면 안 된다.** 그러나 15차 GATE-1 이 남긴
질문은 그대로다 — *드물게 나가는 그 추천이 33.3% 라면, 보수성이 고른 것이
오히려 나쁜 쪽이다.*

## 🔴 PL-8 [중] `_compute_picks` 를 **두 번** 부르는데 야구에서는 두 번째가 무의미하다

```python
picks_out, parlays, recommended = _compute_picks(...)      # 2220
await _apply_line_moves(judge_games)                       # 2222
picks_out, parlays, recommended = _compute_picks(...)      # 2224
```
`_apply_line_moves` 는 야구를 건너뛴다.
```python
for g in games:
    if (g.get("sport") or sport) in _BB:   continue
```
즉 야구 슬레이트는 **같은 입력으로 전체 픽 계산을 두 번** 돈다.
계산은 멱등이라 결과는 같지만, 경기마다 `build_board`·`qualified_singles`
가 두 번 돈다. 라인 이동이 축구 전용이라면 재계산도 축구 전용이어야 한다.

## ✅ PL-9 정상 확인 — 단계 계측(`record`)의 설계

- 단계마다 즉시 발송하지 않고 **요약 1건**으로 묶는다(종전 한 분석에 알림
  7~8건이 쏟아져 정작 카드가 안 보였다 — 실측 2026-08-27).
- `unit` 을 명시해 "출처 대조 438경기" 같은 거짓 숫자를 막는다.
- `expect_full=False`·`zero_ok` 로 **부분 수집이 정상인 단계**와 진짜 실패를
  가른다. 라인업 0건은 `lineup_timing.classify` 로 "아직 발표 전"과 "수집
  실패"를 시각으로 구분한다(킥오프 6시간 전 0건에 매일 거짓 알림이 나갔던
  사고의 수정).
- KBO·NPB 일정은 공식 소스(koreabaseball.com·Yahoo)로 이관됐고, 실패해도
  DB 기존 일정으로 간다("없는 것을 만들지는 않는다").
- 날짜 필터가 `(starts_at AT TIME ZONE 'Asia/Seoul')::date = $2` 다 —
  `now()-12h` 만 쓰다가 다음날·모레 경기가 한 캐시에 섞여 15경기가 됐던
  실측(2026-08-28)의 수정.

---

# 40차 — `app/scheduler.py` (2,055줄)

## 🔴🔴 SCH-1 [최상] LED-5(라인업 역행)의 **유입 경로 3개**를 특정했다

`rejudge_after_lineup(game, lineup)` 은 `jg["lineup_status"] = lineup["status"]`
를 **가드 없이** 대입한다(pipeline.py:5514). 그 `lineup` 을 넘기는 곳이 셋이다.

| 호출부 | `lineup["status"]` 의 출처 | 위험 |
|---|---|---|
| `scheduler.py:452` (MLB 폴링) | `refresh_mlb_lineup` 반환값 | statsapi 가 한 틱 타순 9명을 못 주면 `predicted` → **확정 강등** |
| `scheduler.py:847` (KBO·NPB 크롤 폴링) | 크롤러 스냅샷 상태 | 같은 방식 |
| `scheduler.py:959` (**T-30 보장**) | `row.get("lineup_status") or "none"` = **DB 값** | 캐시가 confirmed 인데 DB 가 뒤처져 있으면 **캐시를 DB 로 끌어내린다** |

세 번째가 특히 위험하다. `sync_lineup_status` 는 DB 를 confirmed 로 **올리기만**
하고(`WHERE lineup_status <> 'confirmed'`), 캐시→DB 반영이 실패하면 두 값이
갈린다. 그 상태에서 T-30 보장이 돌면 **DB 의 낮은 값이 캐시를 덮는다.**
(`already_sent` 가드가 있어 카드가 이미 나간 경기는 건너뛴다 — 그래서
LED-4 의 game=1719 왕복은 852/847 경로 쪽이다.)

그리고 `refresh_mlb_lineup` 은 **`predicted` 를 기본값으로** 낸다.
```python
status = STATUS_CONFIRMED if parsed.get("confirmed") else STATUS_PREDICTED
```
`confirmed` 는 "양팀 타순 9명"이므로, statsapi 응답이 한 번만 얕아도 강등된다.
DB 에 남은 흔적 13건(LED-6)이 이것이다.

## 🔴 SCH-2 [상] 재판정 방아쇠가 **`changed` 한 줄**이고, 그 정의가 넓다

```python
# collectors/lineups.py
changed = status != prev or bool(notes)
# scheduler.py:450
for game, res in updated:            # updated = res["changed"] 인 것
    ok = await rejudge_after_lineup(game, res)     # → LLM 재판정 + 원장 새 행
```
`notes` 에는 "홈 선발 변경: A → B" 같은 문자열이 들어간다. 즉 **노트가 하나만
생겨도 재판정**이고, 폴링은 5분(NPB 2분)마다 돈다.
LED-1(경기당 4.9회 판정)·LED-2(09-06 원장 190행)·LED-4(한 경기 17회)의
공급원이 여기다. `_SIG_FIELDS` 에 `lineup_status` 가 있어 SCH-1 의 왕복이
그대로 원장 행으로 찍힌다.

## 🔴 SCH-3 [상] 리서치 무효율 경고가 **로그에만** 있다

```python
if fill["invalid_rate"] is not None and fill["invalid_rate"] > 0.30:
    logger.warning("[scheduler] ⚠️ 무효율 %s > 30%% — 무효 키워드 과잉 의심 …")
if cross["mismatch"]:
    logger.warning("[scheduler] ⚠️ 교차검증 불일치 %d건 — 지어내기 의심 …")
```
27차 RV-1 에서 잰 대로 09-06 은 **60%**, 09-07 은 **47%** 였다. 두 번 다
문턱을 넘었지만 **텔레그램 알림도 워치독 코드도 없다** — `prefetch_report` 는
`StageResult` 만 싣고 이 두 값은 스테이지가 아니다.
`/health` 는 같은 값을 보여주지만(⚠️ 표시) **사람이 `/health` 를 쳐야** 보인다.

## ✅ SCH-4 정상 확인 — 대칭화와 창 게이트

- `mlb_poll_window`·`asia_poll_window` 로 **시각을 크론에 박지 않는다.**
  MLB 는 `CronTrigger(hour="5-11")` 때문에 01~04시 KST 경기 81건(30일 337경기의
  24%)에서 아예 돌지 않았던 실사고의 수정이다.
- MLB 사이클에 `observe_slate`(정찰)·`guarantee_first_cards`(T-30)·
  `_run_shadow_panel`(L2·L3)을 **아시아와 대칭으로** 넣었다. 세 가지 모두
  "아시아 사이클에만 있어 MLB 가 조용히 감시 밖에 있던" 결함의 수정(2026-09-03).
- `rejudge_after_lineup` 이 캐시 없으면 `return False` 로 조용히 끝나는 것을
  막기 위해 `ensure_analysis_cache` 구제를 넣었다 — "04:30 프리페치가 한 번
  실패하면 그날 MLB 카드가 0장"(실측 2026-09-01).
- `prefetch_job` 이 한 종목 실패로 다른 종목을 죽이지 않는다(Anthropic 400 이
  분류를 빠져나가 축구 judge 에서 전체가 크래시했던 사고).
- 휴식일이면 🔴 7건 대신 **1장**으로 알린다("사용자가 장애인지 휴식일인지 알
  수 없었다" 2026-08-31).
- `finally` 에서 **항상** 실행 리포트를 보낸다 — 조용한 실패 금지.
- `guarantee_first_cards` 가 판정 설계·게이트·트리거를 바꾸지 않고
  **언제 보내는가만** 바꾼다. `already_sent` 로 이미 나간 경기를 건드리지 않는다.

---
---

# 30~40차 요약 — 판정 본체 정독에서 새로 나온 것

읽은 것: `prompts.py`(280) · `scoring.py`(776) · `card.py`(766) ·
`deepsearch.py`(1,007) · `fact_audit.py`(643) · `interpreter.py`(528) ·
`branch_resolve.py`(619) · `research/deep.py` 스키마 · `config.py` 필드 스캔 ·
`pipeline.py` 핵심 절(`build_analysis`·`_compute_picks`·`qualified_singles`) ·
`scheduler.py`(2,055) 핵심 절.

## 🔴🔴🔴 최상

| 코드 | 한 줄 |
|---|---|
| **CR-1~4** | 자료9 시즌 ERA 역주입의 **근본원인 확정** — `_bp_recent`(2753)가 지운 것을 `_pen`(2774)이 21줄 뒤에 정확히 되채운다. 주석은 순서가 반대라고 적혀 있다. 상류 `deep.py` 스키마도 시즌 ERA·좌우 스플릿·불펜 시즌 ERA 를 **직접 요구**한다 |
| **PR-1** | 판정 규칙이 **자료11 을 이름으로 부르는데 프롬프트에 11번 절이 없다**(변수 대장이 10번 한 블록으로 흡수) |
| **PR-2** | 결론 지시가 `자료1~11` — **자료12(기본 축)와 자료14(분기점 조사)를 제외**한다 |
| **SC-1** | `_suppression` 이 `league_era` 인자를 만들고 **쓰지 않는다**. NPB 평균 선발이 −10.8%, KBO 가 +5.3% 로 계산된다. λ 는 꺼져 있지만 **백테스트 도구 7개가 전부 이 계수로 돈다** |
| **PL-1** | 야구의 `p_final` 은 **LLM p_home 그대로** — 앙상블·모델 축이 없다. GATE-3(확률 비단조)를 평활할 두 번째 축이 존재하지 않는다 |
| **PL-2** | 09-07 MLB 4경기 최고 확률 **0.57**, 문턱 0.58 → 추천 0. LED-3 의 원인 |
| **FA-1** | `\b` 가 한글 조사 앞에서 소수점을 잘라 **정확한 인용을 환각으로 찍는다**. elo mismatch 2/2 전부 오탐 |
| **INT-1** | 2단이 **시즌 ERA 로 ▲▼를 매기고 시즌 ERA 로 그 정오를 검증**한다 — 3단 대원칙과 정반대 |
| **SCH-1** | 라인업 역행의 **유입 경로 3곳** 특정 (MLB 폴링 · 아시아 폴링 · T-30 보장이 DB 값을 캐시에 덮어씀) |

## 🔴 상

`SC-2`(승률 절사 경보가 전수 미참조 — `prob_cap_alert_n` 작동한 적 없음) ·
`SC-3`(KBO·NPB 가 축구 분산모수 설정을 상속) ·
`SC-4`(`℃` 정규식이 절대 매치 안 됨) ·
`CARD-1`(5칸 "선발 상태"가 시즌 ERA·WHIP) · `CARD-3`(불펜 시즌 ERA 가 서술로
사용자에게 도달) · `DS-1`(딥서치가 **KBO·NPB 에서 꺼져 있다**) ·
`DS-2`(딥서치 `발견` 에 validate 게이트가 없어 "찾을 수 없음"이 사실로 남는다) ·
`FA-2`(임계 서술 "5이닝 미만"을 인용 수치로 추출 — mismatch 의 6%) ·
`FA-3`(mismatch 의 21%가 자릿수 의심 구간) · `INT-2`(방향 검증 기준선이 그날
슬레이트라 작은 슬레이트에서 무력) · `PL-3`(마켓 보드가 h2h 2행뿐) ·
`PL-6`(야구는 배당을 조회하지 않는다 — 가치·엣지·조합이 구조적으로 불가) ·
`PL-4`(추천 표시가 `desc` 문자열 매칭 — 배당 복구 시 원장·카드 분기) ·
`PL-8`(`_compute_picks` 를 야구에서 무의미하게 두 번 호출) ·
`SCH-2`(재판정 방아쇠 `changed` 가 너무 넓다 — 원장 폭주의 공급원) ·
`SCH-3`(리서치 무효율 60%·47%가 **로그에만** 있고 알림이 없다)

## `\b` / `strip` 을 비ASCII 에 쓴 실수 — **세 번째**

```
SIT-1  registry `" il "` → `_norm.strip()` 이 공백 제거 → "Phillies"가 roster_move (오탐 9/10)
SC-4   weather `(?:도|℃|C)\b`   → '℃' 뒤 경계 불성립 → 기온 미인식
FA-1   fact_audit `(1\d{3}(\.\d+)?)\b` → '…6으로' 앞에서 소수 절단 → 정상 인용이 환각
```

## 이 저장소가 잘하고 있는 것 (같은 무게로 기록한다)

- `branch_resolve`(자료14) — 본인·소속팀·같은처지 3갈래, 새 크롤 0,
  %p 를 만들지 않고 사실만 준다. 패턴을 넓힐 때 **반대 위험을 실변수 638건으로
  측정**했다. 이 감사에서 본 최고의 모범이다.
- `fact_audit` — 오탐을 실측으로 다섯 번 고친 이력이 주석에 남아 있다.
- `research/validate.py` — `_KEEP_PHRASES`·`_HARD_TO_RE` 로 반대 위험을 다룬다.
- `card.py`/`interpreter.py` 의 **정보 차단벽** — 2단이 상대를 모르고, 사실 층에
  LLM 쓰기 접근이 없다. 권한으로 막았다.
- `scheduler` 의 **대칭화** — MLB 가 조용히 감시 밖에 있던 세 구멍(정찰·T-30
  보장·그림자 패널)을 같은 커밋에서 메웠다.

작업트리 **0 변경** · HEAD `21e84d2` · 운영 `7c0f9be`.

---

# 41차 — 추천 게이트 실행 대조 · PL-2 정정

운영 캐시의 09-07 MLB 4경기에 **두 게이트를 동시에 실행**했다.

```
설정: market_agree_required=True · market_divergence_pp=4.0
      min_win_prob=0.58 · away_prob_penalty=0.05

game  p_claude  p_market_send  우세   fav_p  rec_label  market_disagreement
4099    0.56       0.6284      home   0.56    보드만    market_disagree   (괴리 6.84%p)
4100    0.43       0.5492      away   0.57    보드만    market_disagree   (11.92%p)
4101    0.53       0.6154      home   0.53    보드만    market_disagree   ( 8.54%p)
4102    0.43       0.3549      away   0.57    보드만    market_disagree   ( 7.51%p)
   qualifies(h2h 후보 8개 전부) = False
```

## ❌ PL-2 정정 — 09-07 추천 0건의 실제 원인은 **문턱 0.58 이 아니다**

38차에서 *"최고 확률 0.57, 문턱 0.58 — 1%p 차이로 슬레이트 전체가 0건"*
이라고 적었다. **불완전했다.** 네 경기 전부 **시장 동의 게이트에서 먼저
탈락**한다. 확률이 0.58 을 넘었어도 결과는 같았다.

## 🔴🔴 MKT-1 [최상] `market_agree_required` 가 사실상 **전부 차단**한다

임계는 **4.0%p** 인데, 09-07 우리 확률과 시장의 괴리는 **6.84 · 11.92 · 8.54 ·
7.51 %p** 다. 4/4 전부 임계의 1.7~3배다.

코드가 그 위험을 스스로 적어 두었다.
```
⚠️ **이 조건은 구조적으로 시장을 이길 수 없게 만든다.** 정보 우위가
   있어도 추천으로 낼 수 없다. 재캘리브레이션이 끝나면
   `MARKET_AGREE_REQUIRED=false` 로 꺼라 — 종전 동작으로 돌아간다.
```
즉 **LED-3(09-07 추천 0건)은 고장이 아니라 이 정책의 직접 결과**다.
그러나 "임시 방어"라고 적힌 게이트가 **얼마나 오래 켜져 있을지, 무엇을 보고
끌지**를 정하는 장치가 없다 — 재캘리브레이션의 완료 조건이 코드·문서
어디에도 없고, 추천 0건은 `zero_ok=True` 라 알림도 안 난다(PL-7).

## 🔴🔴 MKT-2 [최상·측정] 우리 확률이 시장보다 **체계적으로 0.5 쪽에 몰려 있다**

홈 기준으로 정렬해 보면 방향이 한쪽이다.
```
게임   우리 p_home   시장 p_home   차이
4099     0.56         0.6284      -6.84%p
4100     0.43         0.5492     -11.92%p
4101     0.53         0.6154      -8.54%p
4102     0.43         0.3549      +7.51%p
```
4건 중 3건에서 **우리가 시장보다 홈을 낮게** 본다. 그리고 우리 값은
0.43~0.56(폭 0.13), 시장은 0.35~0.63(폭 0.28) — **시장의 절반 진폭**이다.

이것이 여러 발견과 하나로 이어진다.
```
PL-1  야구 p_final = LLM p_home 단독 (평활할 두 번째 축 없음)
ELO-3 자료12 가 낼 수 있는 최대가 60.0% (리그 폭 55.5점)
FE-4  홀드아웃 p폭 KBO 0.205 · NPB 0.150 · MLB 0.194
GATE-3 0.55~0.60 구간 적중 32.1% — 우리 확률이 몰려 있는 바로 그 구간
MKT-2 시장 대비 진폭 절반 · 계통적 편향
```
`tools/fit_elo.py` 머리말이 같은 말을 이미 적었다 — *"축은 넣었는데
**진폭이 없다**."* 그 진단이 자료12 만이 아니라 **판정 확률 전체**에
해당한다는 것이 이번 측정이다.

## ⚠️ GATE-1 정정 — 제가 발견한 것이 아니라 **이미 알고 조치한 것**이다

15차에서 *"게이트가 가장 못 맞는 경기를 고른다 — 추천 15건 33.3% vs 보드만
97건 58.8%"* 를 새 발견처럼 적었다. `market_disagreement` docstring 이
**같은 측정을 먼저 적어 두었다.**
> 🔴 [v1.4 임시 방어 2026-09-07 사용자 지시] **추천은 시장과 같은 방향일 때만.**
> 근거: 620행 분석 — 추천 게이트 통과분 적중 **30.8%(n=13)** vs 보드만
> **59.7%(n=77)**. 우세팀이 갈린 8경기는 시장 7승 우리 3승.
> 시장을 거스르는 확신이 데이터상 **안티 신호**였다.

제 15차 수치(33.3% n=15 / 58.8% n=97)는 **같은 현상의 이틀 뒤 재측정**이다.
GATE-1 은 새 발견이 아니라 **이미 진단됐고 09-07 에 대응이 배포된 문제**이며,
남는 질문은 하나다 — *그 대응이 옳은가.* MKT-1·MKT-2 가 그 질문에 답한다:
지금 방식은 오차를 고치는 것이 아니라 **추천 자체를 없앤다.**

## 🔴 GATE-7 [상] 게이트가 **두 벌**로 구현돼 있다 (같은 사고를 두 번 겪고도)

| | `pipeline.qualifies()` (원장·조합) | `form_card.rec_label()` (사용자 카드) |
|---|---|---|
| NPB 미검증 | ✅ | ✅ (문구 "NPB: 참고용") |
| `form_unavailable` | ✅ | ✅ + `judgement_void` |
| `starter_low_sample` | ✅ | ✅ |
| `pick_state != final` | ✅ | ✅ |
| 시장 동의 | ✅ | ✅ (같은 함수 호출) |
| **확신도 '하'·패스 권장** | ❌ (`_compute_picks` 가 밖에서 뺀다) | ✅ (안에서 막는다) |
| 확률 비교 대상 | **그 마켓 후보의 `p`** | **`favored_side_and_p(jg)`** |

`rec_label` 주석이 과거 사고 두 건을 적어 두었다 —
`starter_low_sample` 이 카드 경로에 없어 "표본 0 선발"이 `🟢 추천` 으로 나갔고,
시장 게이트도 같은 이유로 옮겨졌다. **두 번 옮겼지만 합치지는 않았다.**
지금 보드가 h2h 2행뿐이라 두 확률 원천이 우연히 같아 어긋나지 않는다 —
배당이 복구되면(PL-3·PL-6) 다시 갈린다.

## 🔴 REN-1 [상] 야구 카드는 **렌더 경로가 통째로 다르다**

```python
def render_game_easy(jg, news="", used=None):
    if sport in ("mlb","kbo","npb") and jg.get("matchup"):
        return render_form_card(jg, sport)      # ← 여기서 끝. 아래는 실행되지 않는다
```
이 아래 약 110줄(서술 context·causal·decider·adjustment_case·market_case ·
`_value_candidates` · `_caution_candidates` · 신뢰도 별점 · **5칸 카드
요약(`card_summary_line`)** · **3단 결론(`compare_lines`)** ·
`card_markets.market_calls`)은 **판정된 야구 경기에 한 줄도 적용되지 않는다.**

그래서 32차 CARD-2 에서 "카드에 5칸·▲▼가 0회"라고 잰 것은 CG-1(2단 해석
사망) 때문만이 아니다 — **애초에 야구는 그 렌더를 타지 않는다.**
`card.py`(766줄)·`interpreter.py`(528줄)·`cell_grade.py` 가 만드는 5칸
체계는 **축구에만** 사용자에게 도달한다. 그리고 축구는
`soccer_trial_enabled=False`·`soccer_judge_enabled=False` 로 꺼져 있다.

→ **5칸 카드 체계는 지금 아무에게도 보이지 않는다.**

---

# 42차 — ❌ 중대 정정: `cell_verdicts` 정지의 원인은 CG-1 이 아니다

## 제가 틀렸다 — 날짜를 안 맞춰 봤다

35차 INT-3 과 28차 MON-3 에서 이렇게 적었다.
> `cell_verdicts` 258행, 최신 2026-08-29 … CG-1(크레딧 차단기)이 interpreter 를
> 죽여 `cells_status="판정 미수행"` 이 됐다. → MON-3 의 원인이 여기서 닫힌다.

**틀렸다.** git 으로 확인했다.
```
$ git log -S "_BB_SKIP_OLD" --oneline -- app/pipeline.py
  c3b1c8e 2026-08-30  야구는 배당·λ·알트마켓·구 해석 스택을 쓰지 않는다.
$ git log -S "야구는 이 스택을 타지 않는다"
  8ce3945 2026-08-30  야구 재판정은 구 카드 스택을 타지 않는다.

cell_verdicts 마지막 행: 2026-08-29
```
**`cell_verdicts` 는 그 가드가 들어간 바로 그날 멈췄다.** 고장이 아니라
**의도된 설계 변경**이다. 코드가 그 이유를 명시한다.
```python
# pipeline.py:2067
from app.engine.scoring import BASEBALL_SPORTS as _BB_SKIP_OLD
if sport not in _BB_SKIP_OLD:
    await _attach_lineup_intent(...)
    await _attach_cell_verdicts(...)
    await _attach_card_compare(...)
```
```
# rejudge_card_stack docstring
⚠️ **야구는 이 스택을 타지 않는다.** … 5칸·언더오버·핸디는 야구에 없는
   마켓이다 (DISCIPLINE 1-A-1).
   이 함수는 종목 가드가 **없어서** 이번 개편에서 통째로 누락됐다. 5분
   폴링마다 야구 경기당 2단 해석 5콜 + 3단 대조 1콜이 나갔고, 그 결과물을
   발송 카드는 쓰지도 않았다. 실측 2026-08-29 크레딧 소진의 한 축이다.
```
즉 08-30 에 **야구를 5칸 스택에서 뺀 것**이고, 그 이유는 낭비된 LLM 콜이었다.
CG-1 은 실재하지만 `cell_verdicts` 와는 무관하다 — 야구는 애초에 그 경로를
안 타고, 축구는 `soccer_judge_enabled=False`·`soccer_trial_enabled=False` 로
꺼져 있다(2026-09-06 `f8020ad`).

## 정정 후에 남는 사실 — 그리고 새로 드러난 것

### 🔴 REN-2 [상] 5칸 체계 약 1,900줄이 **지금 아무 경로도 타지 않는다**
```
card.py 766 · interpreter.py 528 · comparator.py 269 · cell_grade.py 196 · card_markets.py 182
호출 조건: sport not in BASEBALL_SPORTS  →  축구 전용
축구 상태: soccer_judge_enabled=False · soccer_trial_enabled=False
```
야구는 `form_card.render_form_card` 가 매치업 JSON 만 읽어 카드를 만든다.
32차 CARD-1(5칸 "선발 상태"가 시즌 ERA)·35차 INT-1(2단이 시즌 ERA 로 ▲▼)은
**코드로는 사실이지만 지금 실행되지 않는다.** 대원칙 충돌은 잠재 상태다.
(그 대신 `card.py` 가 죽은 코드가 되어 `test_season_ban.py` 의 사각으로 남는다.)

### 🔴 CG-3 정정 — CG-1 이 실제로 죽이는 것은 **자료6 라인업 의도**다
운영 로그의 `[2단-라인업] … 해석 실패` 는 `interpreter.interpret_lineup_intent`
(≠ `interpret_side`)이고, 이것은 **2026-09-07 `63acfcb`("자료6 야구 배선")로
야구에 배선됐다.** 그 경로는 `complete("interpreter", …)` 를 타므로 CG-1 에
정확히 걸린다.
```
pipeline.py:5968  items = await interpret_lineup_intent(...)
pipeline.py:5975  await LI.record_verdicts(pool, …)   # lineup_intent.record_verdicts
```
즉 CG-1 의 실제 피해는 **어제 배선된 자료6** 이고, `cell_verdicts` 가 아니다.
로그 20+건이 그 하루치다.

### 왜 틀렸나 — 기록해 둔다
`cell_verdicts` 정지(08-29)와 Anthropic 소진(09-03 이후)은 **날짜가 5일
어긋나 있었다.** 그 한 줄만 맞춰 봤으면 즉시 배제됐다. 그럴듯한 기전을
찾자마자 원인으로 확정했다 — CLAUDE.md 가 금지한 "절제 실험 없이 추론"이다.

---

# 43차 — `crawler/` (Go, 1,775줄) · 하트비트

현재 상태는 정상이다(실측 2026-09-08 08:10 KST).
```
crawl:heartbeat = 2026-09-08T08:04:07+09:00 · is_alive = (True, '크롤러 정상 (마지막 08:04)')
crawl:kbo:2026-09-08:{0003,0103,…,0804,latest} — 시각별 스냅샷 10개
crawl:mlb:2026-09-07:latest
```

## 🔴🔴 CRW-1 [최상·코드확정] **휴식일이면 하트비트를 안 찍는다** — /health 🔴 오탐의 원인

```go
// crawler/cmd/crawler/main.go  once()
if len(raw) == 0 {
    log.Printf("[%s] %s 경기 0건 — 소스 구조 변경 가능성", sport, date)
    return starts, nil          // ← st.Save() 를 부르지 않고 반환
}
...
if err := st.Save(ctx, sport, date, snap, changes, now); err != nil { … }
```
```go
// crawler/internal/store/store.go  Save()
pipe.Set(ctx, "crawl:heartbeat", now.Format(time.RFC3339), 2*time.Hour)
```
**하트비트는 `Save()` 안에만 있다.** 크롤러는 KBO·NPB 만 긁으므로 두 리그가
모두 휴식이면 `Save()` 가 한 번도 안 불리고 하트비트가 만료된다.

앞선 감사에서 `/health` 를 운영에서 실행해 본 결과가 정확히 그것이었다.
```
2026-09-07 23:08 KST  🔴 크롤러 하트비트 없음 — 미실행
```
그날은 **KBO·NPB 동시 휴식일**이었다(DB: 09-07 종료 경기 mlb 15 · soccer 7,
kbo·npb 0). 크롤러는 멀쩡히 돌고 있었다.

## 🔴 CRW-2 [상] 하트비트 TTL(2h) < 판정 임계(3h) — **"멈춤" 분기가 도달 불가능**

```go
pipe.Set(ctx, "crawl:heartbeat", …, 2*time.Hour)        # Go: TTL 2시간
```
```python
STALE_MINUTES = 180     # 평시 60분 × 3 — 이보다 오래되면 죽은 것으로 본다
async def is_alive(redis):
    raw = await redis.get(HEARTBEAT_KEY)
    if not raw:  return False, "크롤러 하트비트 없음 — 미실행"
    age = …
    if age > STALE_MINUTES:  return False, f"크롤러 {age:.0f}분째 멈춤 (마지막 …)"
```
키가 **120분에 사라지므로** `age > 180` 조건은 영원히 성립하지 않는다.
`"크롤러 N분째 멈춤"` 문구는 **한 번도 출력된 적이 없고 앞으로도 없다.**

결과: `is_alive` 는 **"살아 있음"과 "하트비트 없음" 두 상태만** 낸다.
그리고 "하트비트 없음"은 세 가지가 섞인 값이다.
```
① 크롤러 프로세스가 죽었다        ← 진짜 고장
② 두 리그가 모두 휴식일이다        ← 정상 (CRW-1)
③ 2시간 넘게 못 돌았다            ← 진짜 고장
```
`STALE_MINUTES` 주석("평시 60분 × 3")은 크롤러의 평시 주기가 60분이라는 가정인데
운영 인자는 `crawler -interval 10m` 이다(CLAUDE.md 서비스 표). **또 하나의 사본
드리프트다** — 상수는 60분을 가정하고 실제는 10분이다.

## ✅ CRW-3 정상 확인 — 게이트와 폐기 로그

```go
snap, drops := gate.Apply(raw)          // Redis 에 넣기 **전에** 거른다
for _, d := range drops { log.Printf("[%s] 🚫 %s", sport, d) }   // 조용한 폐기 금지
if n := countFields(raw); n > 0 && len(drops)*2 > n {
    log.Printf("[%s] ⚠️ 수집값 %d개 중 %d개 폐기 — 게이트 과잉이거나 소스 구조 변경", …)
}
```
- **반대 위험을 코드가 직접 감시한다** — 폐기율이 절반을 넘으면 "게이트 과잉"을
  경고한다. 21차 SIT-1(측정 없이 넓혀 오탐 폭증)과 정반대의 태도다.
- `countFields` 가 "몇 경기"가 아니라 **"몇 개 값"**을 센다 — 주석이 그 이유를
  적었다("그래야 게이트 과잉을 볼 수 있다").
- `len(raw)==0` 이면 **조용히 넘기지 않고** "경기 0건 — 소스 구조 변경 가능성"을
  남긴다. (다만 그 자리에서 하트비트를 안 찍는 것이 CRW-1 이다.)
- Redis 전용 — Postgres 를 직접 안 건드린다. "크롤러가 DB 를 쓰면 미검증 값이
  그대로 λ 로 흘러간다."
- 시각별 스냅샷(`crawl:kbo:{date}:{HHMM}`)을 남긴다 — "변화 자체보다 **언제
  바뀌었는지**가 정보일 때가 많다." 실제로 오늘 10개가 쌓여 있다.
- `pace.Wait` 가 **종목별로** 가속한다 — "KBO 18:30 과 NPB 18:00 을 한 시계로
  묶지 않는다."

## ✅ CRW-1 운영 로그로 **직접 확인**

크롤러 서비스 로그 원문:
```
2026/09/07 20:03:28 [kbo] 2026-09-07 경기 0건 — 소스 구조 변경 가능성
2026/09/07 20:03:29 [npb] 2026-09-07 경기 0건 — 소스 구조 변경 가능성
2026/09/07 21:03:29 [kbo] … 0건        2026/09/07 21:03:30 [npb] … 0건
2026/09/07 22:03:30 [kbo] … 0건        2026/09/07 22:03:31 [npb] … 0건
2026/09/07 23:03:31 [npb] … 0건        2026/09/07 23:03:32 [kbo] … 0건
2026/09/08 00:03:34 [npb] 2026-09-08 — 6경기 수집, 값 30개(폐기 0), 변화 0건, 예정 6
2026/09/08 00:03:36 [kbo] 2026-09-08 — 5경기 수집, 값 40개(폐기 0), 변화 0건, 예정 5
```
09-07 저녁 내내 **두 리그 모두 0건** → `Save()` 미호출 → 하트비트 미기록.
같은 시각(23:08) `/health` 가 🔴 를 냈다. **크롤러는 정상이었다.**
자정에 09-08 슬레이트가 잡히자 곧바로 수집·저장이 재개됐다.

## ❌ CRW-2 부분 정정 — 주기가 어긋난 쪽은 **CLAUDE.md** 다

CRW-2 에서 *"`STALE_MINUTES` 주석은 60분을 가정하는데 운영은 `-interval 10m`"*
이라고 적었다. 로그 타임스탬프를 보니 **실제 주기는 60분**이다.
```
20:03 · 21:03 · 22:03 · 23:03 · 00:03 · 01:03 · … · 08:04   (정확히 1시간 간격)
```
즉 코드 주석("평시 60분 × 3")이 맞고, **CLAUDE.md 서비스 표의
`crawler -interval 10m` 이 틀린 사본**이다.
(`pace.Wait` 이 타순 창에서만 2분으로 가속하므로, 심야 시간대가 60분인 것은 정상.)

**TTL 2h < STALE 3h 로 "N분째 멈춤" 분기가 도달 불가능하다**는 지적은 그대로
유효하다 — 그리고 주기가 60분이면 **TTL 2시간은 두 틱치 여유뿐**이라 더 빠듯하다.

## 🔴 CRW-4 [중] 휴식일 로그 문구가 **"소스 구조 변경 가능성"** 이다

```go
log.Printf("[%s] %s 경기 0건 — 소스 구조 변경 가능성", sport, date)
```
휴식일에도 이 문장이 나간다. 09-07 저녁에만 **8번**(kbo·npb × 4틱) 찍혔다.
"오늘 경기가 없다"와 "파서가 깨졌다"가 **같은 문장**이라, 진짜 구조 변경이
왔을 때 이 로그로는 구분되지 않는다. 파이썬 쪽에는 이미
`pipeline.is_rest_day` 와 `scheduler._notify_rest_day` 가 있는데 크롤러는
그 사실을 모른다.

## ✅ CRW-5 정상 확인 — 게이트가 실제로 통과하고 있다

```
09-08 kbo 5경기 값 40개 (폐기 0) · npb 6경기 값 30개 (폐기 0)
```
`gate.Apply` 폐기 0건. 게이트 과잉 경고(`drops*2 > n`)도 없다.
`rules` 는 **등록된 필드만** 검사하고 미등록은 통과시킨다 — 주석이 그 이유를
적었다("미등록 필드를 폐기하면 수집이 조용히 멈춘다").
그리고 **빈 값은 위반이 아니다** — "값이 있는데 불가능할 때만 폐기한다.
그러지 않으면 정상 데이터를 버리는 반대 방향 사고가 난다."
`home_era: {min:0, max:15}` 는 齋藤 響介 ERA 189.00 사고에서 나온 한계다.

---

# 44차 — 🔴🔴 `tools/deploy.sh` 가 **적용하지 않는 시작 명령을 출력한다**

## DEP-1 [최상·코드확정] `deploy_one` 의 2번 인자는 `echo` 에만 쓰인다

```bash
deploy_one() {
  local svc="$1" cmd="$2" path="${3:-.}"
  railway variables … --set "GIT_COMMIT_SHA=$SHA" … --skip-deploys >/dev/null
  echo "▶ $svc 배포 ($cmd)"                       # ← cmd 는 화면 출력뿐
  ( cd "$path" && railway up … --service "$svc" --detach )   # ← cmd 를 넘기지 않는다
}
```
호출부:
```bash
deploy_one analystbot-scheduler "python -m app.scheduler"
deploy_one analystbot-bot       "python -m app.bot"
deploy_one analystbot-crawler   "crawler -interval 10m" crawler
```
배포할 때 화면에는 `▶ analystbot-crawler 배포 (crawler -interval 10m)` 이
찍히지만 **그 명령은 어디에도 적용되지 않는다.**

## DEP-2 [최상·실측] 그래서 크롤러 주기가 세 곳에서 서로 다르다

```
tools/deploy.sh:105,108   "crawler -interval 10m"      ← 출력만 되고 미적용
CLAUDE.md 서비스 표        crawler -interval 10m        ← deploy.sh 를 베낀 사본
crawler/Dockerfile:20     CMD ["crawler","-interval","60m"]
운영 실제 (로그 타임스탬프)  20:03·21:03·22:03·23:03·00:03 … 08:04  = **60분**
app/collectors/crawler_feed.py  STALE_MINUTES = 180  # "평시 60분 × 3"  ← 이것만 맞다
```
**운영은 60분이고, 문서와 배포 스크립트는 10분이라고 말한다.**
`STALE_MINUTES` 주석만 실제와 일치한다.

## 🔴 DEP-3 [상] 배포 설정이 **저장소에 없다** — Railway 대시보드에만 있다

Railway 서비스 설정을 직접 조회했다.
```
analystbot-scheduler
  builder            RAILPACK
  startCommand       "python -m app.scheduler"          ← 저장소에 없음
  preDeployCommand   ["python -m app.db init"]          ← 저장소에 없음
analystbot-crawler
  builder            RAILPACK
  startCommand       (없음)
```
- **`preDeployCommand` 가 DB 스키마를 적용한다.** CLAUDE.md 는 이것을
  *"기동 시 DB 스키마를 적용하므로 스케줄러를 먼저 배포한다"* 고 적는데,
  실제로는 **기동(start)이 아니라 배포 전(preDeploy)** 단계다. 규율의 근거가
  되는 사실이 저장소 어디에도 없고 문서 설명도 한 칸 어긋나 있다.
- 저장소의 `railway.json` 은 `"builder": "DOCKERFILE"` 인데 서비스 설정은
  `RAILPACK` 을 보고한다. 둘 중 무엇이 이기는지 **저장소만 보고는 알 수 없다.**
  (관측된 동작은 `crawler/Dockerfile` 의 `-interval 60m` 과 일치한다.
   어느 쪽이 적용된 것인지는 **측정하지 않았다 — 모른다고 적는다.**)

## 왜 중요한가

이 저장소는 git remote 가 없고 `tools/deploy.sh` 수동 배포 하나에 의존한다.
그 스크립트가 **자기가 하지 않는 일을 했다고 출력한다.** 사람이 화면을 보고
"크롤러가 10분마다 돈다"고 믿을 근거를 스크립트가 스스로 제공한다.

같은 규율이 이미 이 파일에 적혀 있다.
```bash
# 🔴 [2026-09-05] **"배포 요청 완료"는 배포된 것이 아니다.** … 요청은 갔는데
#    마지막 SUCCESS 는 하루 전이었다 — 아무도 몰랐다.
#    이제 기계가 확인한다. 사람의 다짐이 아니라 종료 코드다.
```
`wait_success` 는 그 교훈으로 만들어졌다. **시작 명령에는 같은 교훈이
적용되지 않았다** — 출력하고 확인하지 않는다.

## ✅ DEP-4 정상 확인

- `wait_success` 가 `SUCCESS` 를 실제로 확인하고, 8분 안에 안 뜨면 exit 1.
- 스케줄러 → 봇 → 크롤러 순서와 그 이유가 주석에 있다.
- `railway variables --skip-deploys` 로 커밋 해시를 먼저 주입한 뒤 `railway up`
  — `/health` 의 커밋 대조가 성립하는 근거.
- (앞서 기록한 대로 `--detach` 라 세 서비스가 동시에 빌드되고, `wait_success`
  가 배포 ID 를 대조하지 않는 문제는 그대로다.)

---

# 45차 — 자료9 시즌값 유입구 전수 · `roster` 라는 두 번째 구멍

## 유입구는 다섯 곳이다

```
naver_kbo.py:320          research[{side}_bullpen]["era"]  ← KBO 팀 시즌 ERA
kbo_stats.py:283          같은 자리                          ← KBO 공식 기록실 team_era
npb_stats.py:226          같은 자리                          ← NPB team_era
yahoo_npb.py:637          {side}_bullpen 블록 전체           ← 불펜 명단 평균 ERA + **roster**
mlb_team_pitching.py:103  같은 자리                          ← MLB statsapi 팀 시즌
```
`bullpen_recent.attach` 가 그 뒤에 지운다.
```python
for stale in ("era", "whip", "k9", "bb9"):
    dst.pop(stale, None)
if blk: dst.update(blk)
```

## 🔴🔴 M9-2 [최상·코드확정] `roster` 는 **pop 목록에 없다** — 개별 투수 시즌 ERA 가 그대로 남는다

```python
# yahoo_npb.merge_into_research
blk["roster"] = ", ".join(
    f"{x['name']}({x['era']:.2f}" + (f"·{x['condition']}" if …) + ")"
    for x in pen if x.get("era") is not None)[:400]
```
그 `era` 의 정체를 `bullpen_payload` docstring 이 **직접 밝힌다.**
```python
def bullpen_payload(jg: dict) -> dict:
    """양팀 불펜 — 팀 ERA + 등록 투수 개별. 경기 후반을 결정한다.
    ⚠️ `roster` 의 괄호는 `ERA·컨디션` 이다. …
       (실측 2026-09-02: `清水 昇(2.16·매우 나쁨)` 은 라벨 반전이 아니라
        "**시즌 ERA 2.16**, 현재 컨디션 나쁨"이다).
    """
```
그리고 판정 프롬프트 자료9 가 그것을 읽으라고 지시한다.
```
`roster`의 컨디션(매우 좋음~매우 나쁨)은 최근 상태 정보다.
```
자료9 블록 라벨은 **"양팀 불펜 — 최근 폼만"** 이다.

즉 `_pen`(MLB)을 고쳐도 **NPB·KBO 는 `roster` 로 개별 시즌 ERA 가 계속 들어간다.**
`bullpen_payload` 의 docstring 첫 줄("**팀 ERA** + 등록 투수 개별")도 C1 개정
전 문구가 그대로 남아 있다 — 지금 팀 ERA 는 지워지는데 설명은 아직 넣는다고 말한다.

⚠️ **실측 한계:** 오늘 저장된 판정 프롬프트 12건은 전부 MLB 라
`roster` 가 0/12 다(MLB 경로는 roster 를 안 만든다). **NPB·KBO 프롬프트에
실제로 실렸는지는 아직 측정하지 못했다** — KBO·NPB 판정은 14:00 KST
프리페치라 지금(08:30) 캐시가 없다. 코드 경로만 확인했다.

## ✅ M9-3 확인 — CR-1(MLB 순서 뒤집힘)의 범위는 MLB 로 한정된다

`build_analysis` 호출 순서:
```
2012  merge_source_data(...)          ← naver_kbo·kbo_stats·npb_stats 가 시즌 era 주입
2109  _run_baseball_matchups(...)
        2753  _bp_recent  → era/whip/k9/bb9 pop
        2774  _pen        → MLB 만 다시 채움 (sport != "mlb" 이면 0 반환)
```
KBO·NPB 는 `_pen` 을 타지 않으므로 **팀 시즌 ERA 는 정상적으로 지워진다.**
CR-1 의 피해는 MLB 전용이 맞다. 남는 것이 `roster`(M9-2)다.

---

# 46차 — 상황 축(자료2)의 **검색과 분류가 비대칭**이다 · SIT-1 의 실제 모양

## 🔴🔴 SIT-4 [최상·실행측정] 운영에서 가장 많이 붙는 태그가 **검색된 적이 없는 유형**이다

세 수집 경로 모두 **유형당 첫 낱말 하나씩, 최대 8개**만 질의어로 쓴다.
```python
# news_rss.situation_query
terms = [words[0] for words in axes.values() if words]
picked = terms[:_SIT_QUERY_TERMS]        # _SIT_QUERY_TERMS = 8
# grounding.py:  terms = [w[0] for w in axes.values() if w][:8]
# xsearch.py:    _terms = [w[0] for w in _axes(sport).values() if w][:8]
```
실행 측정:
```
mlb    쿼리 8개 낱말  ·  분류 62개 낱말
kbo    쿼리 8개       ·  분류 55개
npb    쿼리 8개       ·  분류 41개
soccer 쿼리 8개       ·  분류 38개

MLB 실제 쿼리:
  TEAM MLB (retirement ceremony OR jersey retirement OR manager fired OR
            coaching staff OR traded OR extension OR losing streak OR
            extra batting practice) when:1d
```
`SITUATION_TYPES` 는 14개인데 앞 8개만 질의된다. **뒤 6개는 한 번도 검색되지
않는다** — `front_office · crowd · travel · conflict · captain · roster_move`.

그런데 21차에서 잰 운영 태그 분포는 이렇다.
```
roster_move 22 · trade 1   (전부 [미확인])
```
**태그의 96%(22/23)가 검색된 적 없는 유형이다.** 다른 8개 질의로 돌아온 기사에
`"il"` 부분일치가 걸려 붙은 것이다(SIT-1). 즉 자료2 상황 축은
**질문한 것은 안 나오고, 안 물어본 것이 오탐으로 채워지는** 상태다.

## 🔴 SIT-5 [상] 이 비대칭은 세 수집기에 **똑같이 복제**돼 있다

`news_rss`·`grounding`·`xsearch` 가 각자 `[w[0] for …][:8]` 을 다시 적는다.
`registry.situation_axes` 를 원본으로 두는 규율은 지켰지만,
**"유형당 첫 낱말 8개"라는 선택 규칙은 세 곳에 사본으로 있다.**
질의 낱말을 늘리려면 세 파일을 함께 고쳐야 하고, 하나만 고치면 소스마다
다른 것을 묻게 된다.

## ✅ SIT-6 정상 확인 — 최신성 게이트

```python
SITUATION_RECENCY = "when:1d"
#   🔴 [2026-09-06 사용자 지시] 오늘 날짜로 검색한다.
#      실측: 상황 기사 219건 중 133건(61%)이 어제 이전이었고 전부 어제 경기
#      리뷰였다. '김성현 은퇴식 특별 엔트리 등록'(뉴시스 09-05 16:11)이
#      공식 소식통으로 오늘 카드에 실려 지나간 사건이 오늘의 공기로 오인됐다.
```
- `is_recap` 이 경기 결과 기사를 따로 거른다.
- `published_before(it, starts_at)` 로 **경기 시각 이전 기사만** 본다.
- `grounding` 은 프롬프트에 "경기 결과·스코어 기사는 제외하고, 아직 열리지
  않은 일정·발표·논란만 찾아라"를 명시하고, "명시적으로 검색하라고 말한다"
  (일반 서술형 질문은 도구를 발동시키지 않아 `groundingChunks` 가 0 이었다).
- `grounding._cap_ok` 은 **Redis 가 없으면 막는다** — "셀 수 없으면 쓰지 않는다."

---
---

# 47차 — 🔴🔴🔴 **CR-1 을 막으라고 만든 테스트가, CR-1 을 설명하는 주석에 통과한다**

이 감사 전체에서 가장 무거운 발견이다.

## TST-1 [최상·실행확인] 초록 테스트가 깨진 불변식을 지키고 있다고 말한다

`tests/test_bullpen_recent.py:123`
```python
def test_pipeline_attaches_after_season_sources():
    """시즌 부착보다 **뒤**여야 지워진다."""
    src = Path("app/pipeline.py").read_text(encoding="utf-8")
    seg = src[src.index("async def _run_baseball_matchups"):]
    assert seg.index("mlb_team_pitching") < seg.index("bullpen_recent")
    assert seg.index("bullpen_recent") < seg.index("await judge_matchup")
```
이 단언이 실제로 무엇을 가리키는지 실행해 봤다.
```
mlb_team_pitching  첫 등장 → 줄 2749
   2749: #   ⚠️ 시즌 부착(위 `mlb_team_pitching` 등)보다 **뒤**여야 지워진다.   ← 주석이다
bullpen_recent     첫 등장 → 줄 2751
   2751: from app.engine.bullpen_recent import attach as _bp_recent
await judge_matchup 첫 등장 → 줄 2832
단언 통과? True
```
**진짜 호출 순서는 정반대다.**
```
줄 2753: await _bp_recent(...)     ← 시즌 값을 pop
줄 2774: await _pen(...)           ← 21줄 뒤에 다시 채움
```

즉 이렇게 되어 있다.
```
요구사항:  _pen  →  _bp_recent           (시즌 부착 뒤에 지운다)
실제:      _bp_recent(2753) → _pen(2774)  ← 반대
테스트:    "mlb_team_pitching"(2749=주석) < "bullpen_recent"(2751=import)  → 통과
```
**테스트는 요구사항을 적어 놓은 주석을 보고 통과한다.** 그 주석은
CR-1 이라는 결함 자체를 설명하는 문장이다.

이것이 26차 M9-1(판정이 "시즌 ERA 4.63"을 근거로 씀)·32차 CARD-3(불펜 시즌
ERA 가 사용자 카드 서술로 도달)·37차 CR-1~4 가 **2,521개 테스트를 통과하며
살아 있던 이유**다.

## 🔴 TST-2 [최상·구조] 테스트 165개 중 **88개가 소스 텍스트를 읽어 단언한다**

```
$ grep -rln "read_text(encoding" tests/ | wc -l
88
```
그중 **위치 비교**(`.index(A) < .index(B)`)를 쓰는 것들:
```
tests/test_bullpen_recent.py:127,128     ← 🔴 주석에 통과 (TST-1)
tests/test_anthropic_final_only.py:116   ✅ 둘 다 실제 코드 (줄 205 `if not s.soccer_trial_enabled:` · 209 import)
tests/test_api_guard.py:180              (대상 파일이 달라 미확인)
tests/test_branch_resolve.py:253,254     (프롬프트 문자열 내부 — 주석 위험 없음)
tests/test_alerts.py:377,393,412 · test_alert_hygiene.py:99,308,317,324  (record 호출 지점 기준)
```
텍스트 위치 단언은 **주석·docstring·import 문·로그 문자열**이 심볼 이름을
포함하기만 하면 만족된다. 이 저장소는 주석이 매우 상세해서
(모든 결함에 실사고 기록을 남기는 규율) **주석이 많을수록 이 함정이 커진다.**

`test_season_ban.py` 도 같은 계열이다.
```python
src = Path("app/engine/matchup.py").read_text(encoding="utf-8")
assert "STARTER_SEASON_JSON" not in src        # ← 부재 단언이라 안전
```
**부재 단언(`not in`)은 안전하고, 순서·존재 단언은 위험하다.** 부재는
주석에 써 있어도 실패하므로 오히려 엄격하다.

## 고치는 방향 (참고 — 이번 감사는 수정하지 않는다)

순서를 재려면 텍스트가 아니라 **실행 순서**를 봐야 한다. 예:
```python
calls = []
monkeypatch.setattr(bullpen_recent, "attach", lambda *a, **k: calls.append("recent"))
monkeypatch.setattr(mlb_team_pitching, "attach", lambda *a, **k: calls.append("season"))
await _run_baseball_matchups(...)
assert calls.index("season") < calls.index("recent")
```
또는 최소한 텍스트에서 **주석·문자열을 제거한 뒤** 위치를 재야 한다
(`ast` 로 호출 노드의 `lineno` 를 비교하는 것이 정확하다).

## 이 발견이 바꾸는 것

앞서 40차 요약에서 *"tests/ 는 우선순위가 가장 낮다 — 결함은 테스트가 없는
자리에서 나왔다"* 고 적었다. **절반만 맞았다.**
CR-1 은 테스트가 **있었고**, 그 테스트가 **거짓 초록**이었다.
`tests/` 34,431줄을 안 읽은 것이 이 감사의 가장 큰 남은 구멍이다 —
특히 **소스 텍스트를 읽는 88개 파일**이 우선 대상이다.

## TST-2 정밀화 — 순서 단언 **18건 중 주석에 걸리는 것은 1건뿐이다**

`assert X.index(A) < Y.index(B)` 형태를 전수 추출해 A·B 가 각각 코드인지
주석인지 판정했다.
```
test_anthropic_final_only  soccer_trial_enabled < run_once            코드/코드
test_api_guard             is_disabled("grok") < GrokClient()          코드/코드
test_bullpen_recent        mlb_team_pitching < bullpen_recent          🔴주석/코드   ← 유일
test_bullpen_recent        bullpen_recent < await judge_matchup        코드/코드
test_coverage              if _use_deep: < live_briefing               코드/코드
test_coverage              if _use_deep: < _grok.sentiment             코드/코드
test_variable_ledger       await judge_matchup < variable_ledger …     코드/코드
test_variable_ref          attach_material10 < await judge_matchup     코드/코드
test_yahoo_npb             yahoo_finals < odds_finals(…)               코드/코드
test_council · test_form_card · test_situation_today_only ·
test_two_cards_one_final · test_variable_ref('10. 변수 대장')          프롬프트 문자열 대상 — 주석 위험 없음
(test_cache_carry_verdict · test_game_match 는 파일 전체가 아니라 함수 구간을
 잘라서 재므로 제 스캔의 단언=False 는 스캔 한계이지 실패가 아니다)
```
**즉 TST-1 은 유행병이 아니라 한 건이다.** 그러나 그 한 건이 하필
**대원칙(시즌 누적 금지)을 지키는 유일한 순서 보증**이었고, 그것이 깨진 결과가
M9-1(판정 근거에 "시즌 ERA 4.63")·CARD-3(사용자 카드 서술의 "불펜 ERA 3.91")이다.

## ⚠️ TST-3 [중] `assert "문구" in src` 형태의 **문서 테스트**가 다수 있다

`test_scout_registry.py` 가 `"#: 워치독이 지연을 볼 잡"` 이 `registry.py` 에
있는지 단언하는 식이다. 이것은 **의도된 문서 테스트**로 보이므로 결함으로
세지 않는다. 다만 성격이 섞여 있다는 것은 적어 둔다 — 같은 파일에서
`assert "X" in src` 가 어떤 것은 **동작 보증**, 어떤 것은 **주석 보존**을
뜻한다. 앞의 것이 주석에 걸리면 TST-1 이 된다.

구분 규칙 하나면 충분하다.
- **부재 단언**(`assert "X" not in src`) — 안전. 주석에 있어도 실패한다.
- **존재·순서 단언** — 주석·docstring 을 제거한 뒤 재야 한다.
  (`ast` 로 호출 노드 `lineno` 를 비교하는 것이 정확하다.)

---

# 48차 — 🔴🔴🔴 **테스트가 결함을 계약으로 못박고 있다** — CR-1 사슬의 종착점

## TST-4 [최상] `test_mlb_bullpen_material.py` 는 자료9 에 **시즌 ERA 가 있어야 한다**고 단언한다

```python
@pytest.mark.asyncio
async def test_mlb_bullpen_reaches_material_9(_stub):
    """🔴 이 테스트가 이 파일의 목적이다 — 조립 결과에 자료9가 있는가."""
    assert await MTP.attach(jg, season=2026) == 2
    pay = bullpen_payload(jg)
    assert set(pay) == {"home", "away"}, "자료9 가 비었다 — MLB 만 칸이 빈다"
    assert pay["home"]["era"] == 3.68 and pay["away"]["era"] == 4.24
```
`3.68`·`4.24` 는 statsapi `/teams/stats?group=pitching&stats=season` 의
**팀 시즌 방어율**이다(같은 파일 `FAKE` 픽스처가 그렇게 적혀 있다).

그리고 `3.68` 은 26차에서 인용한 **운영 판정 근거의 그 숫자**다.
```
"자료9 불펜 폼에서 홈(3경기 6이닝 1실점, ERA 3.68)이 원정(시즌 ERA 4.63) 대비
 경기 후반 안정성 유지"        ← judge_prompt:4098 의 직전 판정 근거
```

## 두 테스트가 **정반대를 요구**하고, 둘 다 통과한다

```
tests/test_bullpen_recent.py        "시즌 값(era·whip·k9·bb9)을 지운다"
tests/test_mlb_bullpen_material.py  "자료9 에 era 3.68 이 있어야 한다"

$ uv run pytest tests/test_mlb_bullpen_material.py tests/test_bullpen_recent.py -q
  18 passed in 0.61s
```
같이 통과하는 이유:
- `test_mlb_bullpen_material` 은 `MTP.attach` 를 **단독 호출**한다. `_bp_recent`
  가 없는 세계라 시즌 ERA 가 당연히 남는다.
- `test_bullpen_recent` 의 순서 보증은 **주석에 걸려 있다**(TST-1).
- 둘을 잇는 통합 경로를 재는 테스트가 없다.

## `setdefault` 계약을 테스트가 **명시적으로 요구**한다

```python
async def test_existing_bullpen_is_not_overwritten(_stub):
    """이미 다른 소스가 채웠으면 덮지 않는다 — `setdefault` 계약."""
    jg = {..., "research": {"home_bullpen": {"era": 1.11, "roster": ["기존"]}}}
    await MTP.attach(jg, season=2026)
    assert jg["research"]["home_bullpen"]["era"] == 1.11
```
이 계약이 CR-2 의 기전 그 자체다 — `_bp_recent` 가 방금 `era` 를 `None` 으로
만들어 놓았으므로 `setdefault` 는 **언제나 채운다.**

## 날짜가 사고의 모양을 그대로 보여준다

```
2026-09-03  5cd2ba8  v1.3 — 세 리그 재료를 대칭으로 맞춘다   ← mlb_team_pitching 신설 (시즌 ERA 주입)
2026-09-03  14d6020  MLB 자료9 — 회귀만 잠그고 동결 기준을 분리한다  ← 위 테스트 신설
2026-09-04  e8c594a  C1 — 자료9 를 최근 폼으로 교체. 시즌 누적을 판정에서 걷어낸다  ← 정반대 방침
```
**하루 차이로 정반대 결정이 내려졌고, 앞선 것의 호출부·테스트가 회수되지
않았다.** C1 은 `bullpen_recent` 를 넣고 "시즌 부착보다 뒤여야 한다"는
순서 조건을 **주석과 텍스트 단언으로만** 걸었다. 코드 순서는 반대였고,
B-1 의 테스트는 그대로 남아 시즌 ERA 를 계약으로 지켰다.

## 이 사슬의 전체 모습 (26·32·37·47·48차 종합)

```
① deep.py 스키마가 home_bullpen.era 를 요구           (상류)
② mlb_team_pitching 이 statsapi 팀 시즌 ERA 를 주입    (2026-09-03 B-1)
③ test_mlb_bullpen_material 이 그 값을 계약으로 못박음  (2026-09-03)
④ bullpen_recent 가 시즌 값을 pop                      (2026-09-04 C1)
⑤ 그러나 호출 순서가 반대 — _bp_recent(2753) → _pen(2774)
⑥ _pen 의 setdefault 가 방금 빈 자리를 정확히 되채움
⑦ 순서 보증 테스트는 2749행 **주석**에 걸려 통과        (TST-1)
⑧ 결과: 자료9 12/12 에 시즌 era/whip/k9/bb9
⑨ 판정이 그것을 "시즌 ERA 4.63"이라고 근거에 적음      (M9-1)
⑩ 서술이 "불펜 ERA 3.91로 안정적"으로 사용자에게 전달  (CARD-3)
⑪ yahoo_npb 의 roster 는 pop 목록에 없어 NPB·KBO 로도 샘 (M9-2)
```
**2,521개 테스트가 전부 통과하는 동안 열 단계가 전부 성립했다.**

## TST-5 [최상] 자료9 시즌 ERA 를 계약으로 요구하는 테스트가 **네 곳**이다 (MLB·NPB)

`app/engine/bullpen_recent.py:158` 이 `("era","whip","k9","bb9")` 를 pop 하는데,
같은 키를 **"있어야 한다"**고 단언하는 테스트를 전수로 뽑았다.
```
tests/test_mlb_bullpen_material.py:86
    assert pay["home"]["era"] == 3.68 and pay["away"]["era"] == 4.24   ← MLB 팀 시즌 ERA
tests/test_npb_stats.py:101
    assert research["home_bullpen"]["era"] == 3.10                     ← NPB team_era
tests/test_v13_fixes.py:212
    assert jg["research"]["home_bullpen"]["era"] == 3.10               ← 덮어쓰기 금지 계약
tests/test_yahoo_npb.py:145
    """불펜 전원 방어율·컨디션은 딥서치가 못 주는 재료다."""
    assert research["home_bullpen"]["era"] == pytest.approx(2.405)     ← 명단 시즌 ERA 평균
    assert "清水 昇" in research["home_bullpen"]["roster"]              ← roster 도 계약이다 (M9-2)
```
네 테스트 모두 **수집기를 단독 호출**하므로 `_bp_recent` 가 없는 세계에서
돈다. 그래서 통과한다. **자료9 조립 전체를 한 번에 재는 테스트가 없다.**

특히 `test_yahoo_npb.py:145~147` 은 `roster` 문자열까지 계약으로 못박는다 —
M9-2(개별 투수 시즌 ERA 가 pop 목록 밖) 가 **의도된 계약**으로 잠겨 있다는 뜻이다.

## 이 두 절(TST-4·TST-5)이 말하는 것

C1(2026-09-04 "시즌 누적을 판정에서 걷어낸다")은 **모듈 하나를 추가했을 뿐,
그 이전 계약을 회수하지 않았다.**
```
회수했어야 할 것          실제
─────────────────────────────────────────────
mlb_team_pitching 호출     그대로 남음 (게다가 순서가 뒤)
그 테스트 4건              그대로 남아 시즌 ERA 를 요구
deep.py 스키마의 era/fip   그대로 남아 LLM 에 시즌 값을 요청
yahoo_npb 의 roster        pop 목록에 없어 계속 통과
card.py CELL_METRICS       era_season 으로 ▲▼ 정오를 가름
```
CLAUDE.md 의 「사본 금지」가 **문서·상수**를 겨냥해 쓰였는데, 같은 병이
**테스트 계약**에서도 일어났다. 그리고 테스트 쪽이 더 위험하다 —
사본이 아니라 **강제력**이라서, 고치려는 사람을 막는다.

---

# 49차 — 🔴🔴🔴 SIT-1 은 **한 번 오진됐다** — 테스트 docstring 이 증거를 남겼다

## SIT-7 [최상·실행측정] 2026-09-06 에 원인을 "타 종목 유입"으로 진단하고 **질의어를 고쳤다**

`tests/test_situation.py:392`
```python
def test_queries_carry_a_league_qualifier():
    """🔴 실측: MLB `Athletics` 기사 102건 중 **60건(59%)** 이 타 종목이었다.

      "Athletic Bilbao crush Simeone's flat Atletico"   ← 스페인 축구
      "Quakers Outlast Coppin State in Five Set Thriller" ← 대학 배구
    둘 다 `roster_move` 태그로 잡혀 판정 재료에 들어갔다.
    `MLB` 를 붙이니 47건 중 6건(13%)으로 떨어졌고, 상황 태그의 타 종목은
    **0건**이 됐다.
    """
```
그 두 제목을 지금 `match_types` 에 그대로 넣어 봤다.
```
Athletic Bilbao crush Simeone's flat Atletico     → ['roster_move']   유발어: [' il ']
Quakers Outlast Coppin State in Five Set Thriller → ['roster_move']   유발어: [' il ']
```
**B-il-bao · Thr-il-ler.** 두 기사가 `roster_move` 로 잡힌 이유는 종목이 아니라
`" il "` 이 `_norm.strip()` 으로 `"il"` 이 되어 생긴 **부분 문자열 충돌**이었다.

## 그래서 무슨 일이 벌어졌나

```
증상   : roster_move 태그에 엉뚱한 기사가 들어온다
진단   : "타 종목 기사가 딸려온다"                    ← 절반만 맞다
처방   : 질의어에 리그 한정어를 붙인다 (Athletics → Athletics MLB)
측정   : 타 종목 59% → 13% · 상황 태그의 타 종목 0건   ← 증상은 줄었다
기전   : `" il "` 부분일치는 **그대로 남았다**
현재   : 같은 충돌이 이제 **종목 안에서** 일어난다 —
         Ph-il-lies · M-il-waukee · M-il-ler · W-il-d · ava-il-able
결과   : 운영 상황 태그 22/23 이 roster_move (21차 실측)
```
질의어 수정이 **효과가 있었기 때문에** 진단이 맞다고 확정됐고, 진짜 기전은
검증되지 않았다. CLAUDE.md 가 적은 규율이 정확히 이 자리를 겨냥한다.
> **절제 실험(하나씩 빼보기) 한 번이 추론 세 번보다 정확하다.**

`" il "` 을 목록에서 하나 빼 보는 것이 그 절제 실험이었다.

## SIT-8 [상] 오탐 방어 테스트가 **충돌하지 않는 문장으로만** 짜여 있다

```python
def test_ordinary_game_news_is_not_tagged():
    """반대 위험 — 평범한 경기 기사를 상황으로 읽으면 신호가 잡음이 된다."""
    items = [{"title": "두산 선발 곽빈 6이닝 무실점 호투", …}]   ← 한국어. 'il' 없음
    assert situation.classify(items, "kbo") == []

def test_game_recap_is_still_not_a_roster_move():
    assert situation.classify([{"title": "Mariners beat Athletics 7-6", …}], "mlb") == []
```
실행 확인: `'Mariners beat Athletics 7-6'` → `[]` (유발어 없음). **통과한다.**
반대 위험을 재는 테스트가 **두 건 있고 둘 다 우연히 안전한 문장**이다.
운영 기사 제목 하나만 넣었으면 즉시 잡혔다.
```
'Phillies win 5-3'                  → ['roster_move']
'Milwaukee Brewers bullpen notes'   → ['roster_move']
'Bobby Miller gets surprise hero…'  → ['roster_move']   ← 운영 실제 태그
```

## 이 발견이 더하는 것

21차 SIT-1 에서 *"재현율을 넓히며 정밀도를 안 쟀다"* 고 적었다. 실제는 한 단계
더 나쁘다 — **정밀도 문제를 인지했고, 측정했고, 다른 원인으로 귀속시켰다.**
그리고 그 오진이 **테스트 docstring 에 근거와 함께 박제**돼, 다음 사람이
읽으면 "이미 조사·해결된 문제"로 보인다.

---

# 50차 — 🔴🔴 별점에서 확신도를 빼는 수정이 **쓰이지 않는 함수에** 적용됐다

## STR-1 [최상·실행측정] 사용자 카드의 별은 여전히 확신도를 센다

2026-09-07 수정의 근거(`markets.row_stars` docstring):
> 🔴 [v1.4 2026-09-07 사용자 지시] 종전에는 확신도 `상` 이면 한 칸 올렸다.
> 620행 분석에서 **확신도 표기가 역정보**로 나왔다 — 추천(확신 높은 쪽) 적중
> 30.8%(n=13) < 보드만 59.7%(n=77). 확신을 별점으로 증폭하면 사용자가 가장
> 못 맞히는 픽을 가장 굵게 본다. … **표시에서 뺀다.**

그런데 **사용자 카드의 별점은 `row_stars` 가 아니라 `board_stars` 가 만든다.**
```
pipeline.star_rows:4224      stars, warn = board_stars(c, jg, s)     ← 카드 경로
  └ render_star_board → "📋 경기별 마켓 — 별점 순"  (card:mlb:2026-09-07 실물)
pipeline.board_row:4600      stars = row_stars(c, confidence)        ← 다른 경로
```
`board_stars` 는 **수정되지 않았다.**
```python
if jg.get("judge_confidence") == "high":
    n += 1
```
실행 대조:
```
확신도 medium → ★3
확신도 high   → ★4      ← 확신도가 별 하나를 더 준다
확신도 low    → ★3⚠

범례(pipeline.py:4965): "★ = 충족한 조건 수: 승률 58%↑ / 62%↑ / 근거 2축↑"   (조건 3개)
board_stars 실제:        승률58 · 승률62 · 근거2축 · **확신도 high**          (조건 4개)
```
같은 커밋이 **범례에서는 확신도를 지웠다.**
```python
# [v1.4 2026-09-07] 범례에서 확신도를 뺐다 — `row_stars` 가 더는 안 본다.
lines.append(f"★ = 충족한 조건 수: 승률 {_s.min_win_prob:.0%}↑ / …")
```
주석이 근거로 든 `row_stars` 는 **이 화면이 쓰는 함수가 아니다.**
결과: **범례는 3개라 하고 별은 4개까지 붙으며, 그 넷째가 하필 역정보다.**

## STR-2 [최상] 그리고 테스트가 그 넷째 별을 **계약으로 잠근다**

`tests/test_pipeline_bot.py:907`
```python
n3, _ = board_stars(_mk_row(0.63, 1.74, {"data": True, "model": True}),
                    {"judge_confidence": "high"}, s)
assert n3 == 4                                   # + 판정 high
```
TST-4(자료9 시즌 ERA)·TST-5 와 **같은 형태의 세 번째 사례**다.
```
방침 변경   → 새 코드 추가 / 문구 수정
             ↳ 옛 호출부는 남는다
             ↳ 옛 테스트가 옛 동작을 계약으로 지킨다
             ↳ 전 스위트 통과 → 아무도 모른다
```

## STR-3 [중] 별점 함수가 **두 벌**이고 조건이 다르다

```
markets.row_stars   STARS_BY_GRADE[grade]  — 등급(확률)만. 0·1·3·4
pipeline.board_stars 조건 4개 카운트        — 확률 2 + 축 + 확신도. 0~4
```
같은 화면 언어("★")를 쓰는 두 계산이 서로 다른 것을 센다.
`row_stars` 는 `board_row`(마켓 행 렌더)가, `board_stars` 는 `star_rows`(별점
보드)가 쓴다. 어느 것이 "그 마켓의 별"인지 코드만 보고는 알기 어렵다.

## 실피해 범위

운영 원장 134경기 중 확신도 `상` 은 **2건**(15차 GATE-4)이고, 09-07 슬레이트는
4경기 전부 `medium` 이었다(41차). 따라서 **지금 넷째 별이 붙은 카드는 드물다.**
결함은 실재하되 노출은 작다 — 다만 확신도 분포가 바뀌면 즉시 커진다.

---

# 51차 — 같은 개념의 **두 벌 구현** 전수

`app/` 에서 같은 이름의 함수가 2곳 이상 정의된 것 **101개**. 대부분은 수집기
공통 인터페이스(`refresh`·`load`·`_key`·`merge_into_research`)라 정상이다.
같은 **개념**을 두 번 구현해 어긋날 수 있는 것만 추렸다.

## 🔴 DUP-1 [중] `consecutive_days` — 연전 계산이 두 벌 (자료11 · 자료14)

```
app/engine/context_recent.py:40    자료11 `연전` 을 만든다        → int | None
app/engine/branch_resolve.py:398   자료14 `연전일차` 를 만든다     → int (항상)
```
같은 입력으로 실행 대조:
```
케이스                    branch_resolve   context_recent   일치
오늘만 / 오늘+어제 / 3일 연속 / 더블헤더 / 하루 빔 / 어제부터    같음   ✅ (7/9)
미래 값 섞임                    1              2          🔴
빈 목록                        1            None         🔴
```
- **빈 목록**: `branch_resolve` 는 자료가 없어도 **"연전 1일차"** 를 만들어낸다.
  `context_recent` 는 `None`("모른다")을 낸다. 이 저장소가 반복해 적은
  *"0 과 모름을 섞지 마라"* 를 한쪽만 지킨다.
  (현재 `series_outlook` 이 `if not rows: return {}` 로 막고 있어 실피해는 없다.)
- **미래 값**: `_SERIES_DAYS` 가 `starts_at < $3` 로 거르므로 그 경로에서는 안 난다.

운영 프롬프트 12건 실측: 자료11 `연전` 은 12/12 에 있고(값 1 또는 4),
자료14 `연전일차` 는 **0/12**(연전 관련 분기점이 안 나왔다). **오늘은 충돌이
관측되지 않는다** — 잠재 결함이다.

## 🔴 DUP-2 [중] 별점 계산이 **다섯 벌**이다

```
markets.row_stars          등급(확률)만                    → 0·1·3·4
pipeline.board_stars       조건 4개 카운트(확률2+축+확신도)  → 0~4   ← 사용자 카드
value_gate.stars           확률 사다리 ★~★★★★★           → 문자열
soccer_trial.stars         (축구 시범)
daily_summary.stars        (일일 요약)
```
같은 화면 언어 `★` 를 다섯 함수가 각자 계산한다. 50차 STR-1 이 그중 둘이
어긋난 실제 사례다 — **2026-09-07 수정이 `row_stars` 에만 적용되고
`board_stars` 는 그대로였다.**

## 🔴 DUP-3 [중] `trip_credit` 두 벌 — 의도된 분리지만 **상태가 갈린다**

```
api_guard.trip_credit    → Redis 영구 차단(`api:blocked:*`), 사람이 풀어야 함
credit_guard.trip_credit → 프로세스 메모리 `_EXHAUSTED`, 재기동으로만 풀림
```
`credit_guard` 주석이 분리 이유를 밝힌다(충전 후 자동 복구). 그러나 결과적으로
**Anthropic 소진 상태가 Redis 어디에도 안 남아** 밖에서 조회할 수 없다
(24차 LIVE-1·CG-4). `api:blocked:*` 에는 `odds` 하나뿐이고 anthropic 은 없다.

## 🔴 DUP-4 [하] `record_verdicts` 두 벌 · `league_baselines` 네 벌 · `_ratio` 두 벌

```
record_verdicts   lineup_intent.py:85 · cell_grade.py:44        (35차 INT-4)
league_baselines  statcast:162 · npb_stats:183 · kbo_stats:217 · card.py:132
_ratio            starter_season.py:273 · scoring.py:96
has_material      validate.py:554 · comparator.py:121
compare_game      crosscheck.py:32 · comparator.py:223
```
`league_baselines` 넷은 각각 다른 것을 만든다(리그 평균 vs 슬레이트 사분위)
— 이름이 같아 호출부에서 무엇을 받는지 헷갈릴 여지가 있다.

## ✅ DUP-5 정상 — 수집기 공통 인터페이스

`refresh`/`load`/`_key`/`merge_into_research`/`attach` 가 12~16곳에 있는 것은
**의도된 규약**이다. 파이프라인이 종목별 분기 없이 같은 이름으로 부를 수 있게
한 것이고, 각 구현은 자기 소스만 안다. 사본이 아니라 인터페이스다.

## ✅ DUP-6 검증 — 자료11 `연전` 값은 **실제와 맞다**

`judge_prompt:4092`(2026-09-07 ATL@PHI)의 자료11:
```json
[맥락] {"home": {"연전": 4, "이동": "홈 연속", "구장변경": false},
        "away": {"연전": 4, "이동": "원정 연속", "원정연전": 3},
        "날씨": {"수치": "기온 25도, 풍속 2.4m/s", "라벨": "타자 유리", "계수": 1.02},
        "선발손": {"home": "L", "away": "R"}}
```
DB 로 대조:
```
Philadelphia Phillies  직전 경기일 09-06 · 09-05 · 09-04 · 09-02 · 09-02 · 09-01
                       → 09-03 이 비었다 → 오늘(09-07) 포함 4일 연속  ✅
Atlanta Braves         직전 경기일 09-06 · 09-05 · 09-04 · 09-02 · 09-01 · 08-31
                       → 같음, 4  ✅
```
09-02 이 두 번 나오는 것은 더블헤더인데 `consecutive_days` 가 집합으로 중복을
제거해 하루로 센다 — docstring 이 명시한 규약대로다.

**자료11 은 이 감사에서 값까지 실측 대조해 맞은 몇 안 되는 재료다.**
(자료14 도 46차에서 같은 수준으로 확인됐다.)

---
---

# 41~51차 요약

## 🔴🔴🔴 최상 — 새로 나온 것

| 코드 | 한 줄 |
|---|---|
| **TST-1** | CR-1 을 막으라고 만든 순서 테스트가 **CR-1 을 설명하는 주석**(pipeline:2749)에 통과한다 |
| **TST-4/5** | 자료9 에 **시즌 ERA 가 있어야 한다**고 단언하는 테스트가 4건(MLB·NPB). `roster` 까지 계약이다 |
| **SIT-7** | SIT-1 은 2026-09-06 에 이미 **오진**됐다 — "타 종목 유입"으로 귀속하고 질의어를 고쳤다. `Bilbao`·`Thriller` 가 `" il "` 로 걸린 것이었다 |
| **MKT-1/2** | 09-07 추천 0건의 실제 원인은 문턱 0.58 이 아니라 **시장 동의 게이트**(4/4 전부 괴리 6.8~11.9%p). 우리 확률 진폭이 시장의 절반 |
| **STR-1/2** | "확신도를 별점에서 뺀다" 수정이 **쓰이지 않는 함수**(`row_stars`)에 적용됐다. 카드는 `board_stars` 를 쓰고 거기엔 확신도가 남아 있다. 테스트가 그 넷째 별을 잠근다 |
| **DEP-1/2** | `deploy.sh` 가 **적용하지 않는 시작 명령을 출력**한다. 크롤러 주기가 문서 10분 / 실제 60분 |
| **CRW-1** | 휴식일이면 크롤러가 하트비트를 안 찍어 `/health` 가 🔴 오탐 (운영 로그로 확인) |
| **CG-1** | `provider.py:655` 가 사슬을 안 보고 `abort_if_credit_gone` — Anthropic 없는 역할까지 죽는다 (운영 재현) |

## ❌ 이번 구간에서 **제가 정정한 것**

1. **`cell_verdicts` 정지(08-29)를 CG-1 탓으로 적었다 → 틀렸다.**
   `git log -S "_BB_SKIP_OLD"` = 2026-08-30. 가드가 들어간 그날 멈췄고,
   야구를 5칸 스택에서 뺀 **의도된 설계 변경**이었다. 날짜 한 줄만 맞춰
   봤으면 즉시 배제됐다.
2. **PL-2 "문턱 0.58 때문에 추천 0건" → 불완전.** 시장 동의 게이트가 먼저
   전부 탈락시킨다(MKT-1).
3. **GATE-1 을 새 발견처럼 적었다 → 이미 알고 조치한 것이다.**
   `market_disagreement` docstring 이 같은 측정(30.8% vs 59.7%)을 먼저 적었다.
4. **CRW-2 "주기가 10분인데 상수는 60분" → 반대다.** 실제가 60분이고
   CLAUDE.md·deploy.sh 가 틀린 사본이다.
5. **LS-1 "테스트가 무엇을 지키는지 모른다" → 과했다.** `test_season_ban.py`
   는 배선의 부재를 제대로 잠근다.
6. **LLM_SEED 미설정 → 틀렸다.** 환경변수는 비었지만 config 기본값 20260905 가
   전송된다.
7. **GATE-6 "가치주의인데 배당 0" → 오탐.** 날짜별로 보면 `odds` 는 09-07
   부터만 기록된다.
8. **LED-6c "KBO 86% 가 타순 없이 판정" → 오탐.** 소급 적재분이 섞였다.
   최근 10일은 KBO 5/5.

## 이 시스템의 지배적 실패 형태 (이제 확실하다)

```
방침을 바꾼다  →  새 코드/문구를 **추가**한다
               ↳ 옛 호출부를 회수하지 않는다
               ↳ 옛 테스트가 옛 동작을 **계약으로** 지킨다
               ↳ 새 보증은 텍스트·주석에 걸려 초록이 된다
               ↳ 2,521개 전부 통과 → 아무도 모른다
```
확인된 사례 셋:
```
① 자료9 시즌 ERA   C1(09-04)이 B-1(09-03)을 회수 안 함 + 테스트 4건이 계약화 + 순서 보증이 주석에 걸림
② 5칸 카드         08-30 에 야구를 뺐는데 card.py·interpreter.py 1,900줄이 남고 축구는 꺼짐
③ 별점 확신도      09-07 수정이 row_stars 에만 · board_stars 와 그 테스트는 그대로
```

작업트리 **0 변경** · HEAD `21e84d2` · 운영 `7c0f9be`.

---

# 52차 — `crawler/` Go 나머지 · 배당 수집기 · 실데이터 대조

## ✅ CRW-6 — Go·Python 팀 매핑이 **정확히 일치**한다

`source.go` 의 `kboTeams`·`npbTeams` 는 주석이 *"파이썬 쪽 TEAM_TO_ODDS 와
같아야 한다"* 고 적은 **의도된 사본**이다. 전수 대조했다.
```
KBO  Go 10개 · Python 10개 → 차이 0 ✅
NPB  Go 12개 · Python 12개 → 차이 0 ✅
```
사본이지만 **어긋나지 않았다.** 이번 감사에서 확인한 사본 중 유일하게 그렇다.

## ✅ CRW-7 — NPB 홈/원정 판정이 map 순서에 의존하지 않는다

```go
for jp := range npbTeams { ... found = append(found, jp) }   // ← Go map 순회는 무작위
if strings.Index(inner, found[0]) > strings.Index(inner, found[1]) {
    found[0], found[1] = found[1], found[0]                  // ← 원문 위치로 정렬
}
```
무작위 순서를 **원문 등장 위치로 다시 정렬**한다. 파이썬 `parse_finals` 의
`teams.sort(key=t.index)` 와 같은 규약이다. 팀 약칭 12개 중 서로의 부분
문자열인 것도 없다. ✅

## ✅ CRW-8 — 오늘 크롤 스냅샷이 정상이다 (실측)

```
crawl:kbo:2026-09-08:latest  5경기
  Doosan Bears@Hanwha Eagles#20260908OBHH02026
     home_pitcher 류현진 · away_pitcher 최승용 · stadium 대전
     starts_at 2026-09-08T18:30:00+09:00 · status 경기전 · lineup_home "" (공시 전)
crawl:npb:2026-09-08:latest  6경기
  Chunichi Dragons@Yomiuri Giants#2021039390
     home_pitcher 戸郷 翔征 · away_pitcher 柳 裕也 · starter_status 예상
```
빈 타순은 정상이다(KBO 공시 T-60, 지금 08:50 KST vs 18:30 경기).
`crawler_feed.merge_into_research` 도 `if not order: continue` 로 막는다. ✅

## 🔴 ODD-1 [최상·실측] 수집되는 배당은 **h2h 뿐이다** — 토탈·런라인 행이 0

`odds_snapshots` 최근 5일 전수:
```
날짜     provider     market   행수    경기
09-08    espn         h2h      230     11
09-08    oddsportal   h2h       20      5
09-07    espn         h2h      374     25
09-06    oddsportal   h2h      916     11
09-06    espn         h2h      516     25
09-05    oddsportal   h2h     1106     11
…
→ market 컬럼이 **전 행 'h2h'**. totals·spreads 행 0건.
```
이것이 PL-3(마켓 보드가 h2h 2행뿐)의 **더 깊은 뿌리**다.
39차 PL-6 에서 *"야구는 build_analysis 에서 배당을 조회하지 않는다"* 를 찾았는데,
그 뒤 `refresh_odds_for_game`·`odds_snapshot_30m` 으로 붙는 배당조차
**소스 자체가 h2h 만 준다.**
```
가치 게이트(p × 배당)      → h2h 로는 가능 (배당이 있다)
토탈·런라인 보드            → 소스가 없어 **구조적으로 불가능**
조합(파레이)               → h2h 레그만 가능
`_attach_alt_markets`      → totals 스냅샷 0건이라 항상 빈 목록
```
`espn_odds`·`oddsportal`·`sharp_odds` 세 무료 소스 모두 승패만 준다.
"전 마켓 보드"라는 설계는 **유료 The Odds API 시절의 잔재**다.

## 🔴 ODD-2 [상] KBO 배당 커버리지가 **25.5%** 다

최근 5일 경기 대비 배당 보유:
```
mlb     69경기 중 61  (88.4%)   espn + sharp 2단
npb     25경기 중 19  (76.0%)   oddsportal
kbo     98경기 중 25  (25.5%)   oddsportal   🔴
soccer  22경기 중  0  ( 0.0%)
```
KBO 만 4분의 1이다. 담당 소스가 oddsportal 하나뿐이고(24차 LIVE-3: 503 반복),
MLB 처럼 2단 폴백이 없다.

시장 동의 게이트(`market_agree_required=True`)는 `p_market_send` 가 없으면
`MARKET_MISSING` 으로 **추천을 막는다**(41차 MKT-1). 즉 **KBO 는 배당 커버리지
25.5% 때문에 나머지 74.5% 에서 구조적으로 추천이 불가능하다.**
(kbo 98경기는 소급 적재분을 포함한 수치라 최근 실슬레이트 비율은 더 높을 수
있다 — 이 분모는 정밀하지 않다. 다만 세 종목 중 KBO 가 가장 낮다는 순위는 유효하다.)

## ✅ ODD-3 정상 확인 — `odds_free` 의 오탐 방어

- `upcoming_mlb_dates` 가 **날짜를 계산하지 않고 DB 에서 역으로 읽는다** —
  `mlb_slate_date()` 로 계산했다가 "ESPN 14경기 정상인데 매칭 0" 이 나온
  실사고(2026-09-02)의 수정. 원인은 소스가 아니라 **아직 적재 안 된 슬레이트**였다.
- `no_games=True` 를 **소스 실패와 구분**한다("붙일 경기가 DB 에 없다").
- 슬레이트가 전부 시작·종료됐으면 WARNING 대신 INFO — "대상이 없어진 것을
  전부 실패로 30분마다 WARNING 하면 진짜 고장이 그 속에 묻힌다."
- 붙일 경기가 없으면 **소스를 때리지도 않는다**(헛호출 절약).

---

# 53차 — `app/collectors/statcast.py` (553줄)

## 🔴🔴 STC-1 [최상·실측] **애리조나만 Statcast 재료가 통째로 없다**

운영 Redis 캐시 전수:
```
statcast:offense:2026-09-07   29/30   빠진 팀: ['Arizona Diamondbacks']
statcast:bullpen:2026-09-07   29/30   빠진 팀: ['Arizona Diamondbacks']
statcast:batters:2026-09-07   29/30   빠진 팀: ['Arizona Diamondbacks']
statcast:pitchers:2026-09-07  567명
statcast:league:2026-09-07    {'xwoba': 0.3107, 'xwoba_allowed': 0.312}
```
애리조나가 경기를 안 한 것이 아니다.
```
Arizona Diamondbacks  최근 30일 종료 경기 24
Athletics             최근 30일 종료 경기 24   ← 캐시에 있음
Colorado Rockies      최근 30일 종료 경기 23   ← 캐시에 있음
```

기전은 하나뿐이다. 팀을 떨구는 경로가 `TEAM_CODE_TO_NAME.get(code)` 하나이고,
`None` 이면 그 행이 버려진다.
```python
def _team_of_batter(row) -> str | None:
    code = row.get("away_team") if top.startswith("Top") else row.get("home_team")
    return TEAM_CODE_TO_NAME.get(str(code))      # ← 매핑 밖이면 None → 폐기
```
매핑에는 `"ARI": "Arizona Diamondbacks"` 가 있다. **Statcast 원본이 내보내는
애리조나 코드가 `ARI` 가 아니라는 뜻이다.**
(Statcast/pybaseball 은 애리조나를 `AZ` 로 쓴다 — 저는 원본 응답을 직접
관측하지 못했으므로 그 리터럴까지는 단정하지 않는다. **확정된 것은
"매핑 밖의 코드라서 29팀만 남았다"** 이고, 남은 29팀이 전부 매핑에 있는
팀이라는 사실이 그것을 뒷받침한다.)

같은 파일이 **오클랜드 개명은 두 코드로 처리해 두었다.**
```python
"OAK": "Athletics", "ATH": "Athletics",
```
코드 변형을 아는 저자가 애리조나만 놓쳤다.

### 파급
- ARI 경기는 `research.{side}_offense`(xwOBA·배럴·하드히트·좌우 스플릿)와
  `{side}_bullpen`(Statcast 계열)이 **비어서** 판정에 간다.
- `_merge_mlb` 의 `statcast_filled` 가 그 경기에서 빈 목록이 되고,
  `/health` 의 "1차 소스 수집 현황"에도 실패로 잡히지 않는다 —
  **한 팀만 빠지는 것은 어느 계측에도 걸리지 않는다.**
- λ 는 지금 꺼져 있어 확률에는 영향이 없다. 재료 결손만 남는다.
- `league_baselines` 의 리그 평균도 29팀으로 계산된다(0.3107 / 0.312).

## ✅ STC-2 정상 확인 — 표본 가드와 xwOBA 정의

```python
MIN_PITCHER_PITCHES = 50 · MIN_PITCHER_APPEARANCES = 3
LOW_SAMPLE_NOTE = "표본 부족 — 리그 평균 적용"
#  가드가 없어 허용 xwOBA 분포가 0.012~1.010 까지 벌어졌다(실력값일 수 없다)
```
```python
def _xwoba(frame, pd):
    """정식 xwOBA — **삼진·볼넷을 포함한다**.
       `estimated_woba_using_speedangle` 은 인플레이 타구에만 값이 있다.
       그것만 평균 내면 삼진(wOBA 0)이 통째로 빠져 **부호가 뒤집힌다**"""
```
삼진 제외로 부호가 뒤집히는 것은 실제로 흔한 실수이고, 그것을 알고 고쳐 둔
드문 코드다.
- `_fetch_statcast` 가 블로킹임을 명시하고 `to_thread` 사용을 요구한다.
- 캐시 날짜가 **미 동부 슬레이트 날짜**다(09-08 03:30 KST 실행 → `2026-09-07` 키).
  TTL 26h·실측 잔여 20.3h 로 정상.

---

# 54차 — 리서치 교차검증(지어내기 감시)의 실적

`app/research/crosscheck.py` 는 절대규칙 2("LLM 수치와 API 가 충돌하면 API 가
이긴다")의 감시 구현이다. 운영 Redis 전수:

```
research_crosscheck:2026-08-26   checked 2   mismatch 0
                   :2026-08-27   checked 6   mismatch 0
                   :2026-08-28   checked 0   mismatch 0   ← 여기부터
                   :2026-08-29   checked 0
                   :2026-08-30   checked 0
                   :2026-08-31   checked 0
                   :2026-09-01   checked 0
                   :2026-09-02   checked 0
                   :2026-09-03   checked 0
                   :2026-09-04   checked 0
                   :2026-09-05   checked 0   ← 9일 연속 0
                   :2026-09-06   checked 6   mismatch 0
                   :2026-09-07   checked 7   mismatch 0
                   :2026-09-08   checked 4   mismatch 0
```

## 🔴🔴 CC-1 [최상] 지어내기 감시가 **9일 연속 0건**이었다

08-28 ~ 09-05 동안 한 항목도 대조하지 않았다. 같은 기간에 리서치는 계속 돌았고
(`research_fill` 09-02 88건 · 09-05 96건), 무효율이 60% 까지 갔다(27차 RV-1).
**지어내기를 가장 의심해야 할 구간에 감시가 꺼져 있었다.**

09-06 에 저절로 재개됐다. **왜 멈췄고 왜 돌아왔는지는 특정하지 못했다** —
`compare_game` 은 `era_season` 이 없거나 `stats["era"]` 에 그 투수 이름이
없으면 조용히 건너뛴다(`continue`). 둘 중 무엇이었는지는 그 시점 데이터가
없어 잴 수 없다. **모른다고 적는다.**

## 🔴 CC-2 [상] 14일 동안 대조한 항목이 **총 25개**다

설계상 상한이 그렇다.
```python
SAMPLE_SIZE = 2                     # 하루 2경기
if sport != "mlb": return []        # MLB 만
비교 항목: {home,away}_pitcher.era_season · {home,away}_recent_form.form
   → 경기당 최대 4행 · 하루 최대 8행
```
2주치 합계 25행. **mismatch 는 14일 내내 0** 이고,
`scheduler.prefetch_job` 의 경보
```python
if cross["mismatch"]:
    logger.warning("[scheduler] ⚠️ 교차검증 불일치 %d건 — 지어내기 의심 …")
```
는 **한 번도 발화할 기회가 없었다.** 표본 25개로 "지어내기 없음"을 말할 수 없다.

## 🔴 CC-3 [중] 감시의 유일한 수치 축이 **시즌 ERA** 다 — 대원칙이 지운 값

```python
name, era = block.get("name"), block.get("era_season")
if not name or era is None: continue
...
"mismatch": abs(era - api_era) > ERA_TOLERANCE
```
`era_season` 은 2026-09-04 대원칙이 **판정 입력에서 걷어낸** 값이다(37차 CR-1).
리서치 스키마에는 아직 남아 있어서(CR-4) 지금은 대조가 되지만,
**스키마를 정리하는 순간 이 감시는 축이 없어진다.**
나머지 한 축(`form` 승률 vs statsapi 최근 승률)은 `FORM_TOLERANCE = 0.40` 으로
허용 오차가 40%p 다 — 5경기 폼에서 3승2패(0.6)와 1승4패(0.2)의 차이가
0.4 라 **경계에 걸려야 겨우 잡힌다.**

## 🔴 CC-4 [중] KBO·NPB 는 대조 대상이 아니다

```python
if sport != "mlb":
    logger.info("[crosscheck] %s는 대조 대상 아님 (statsapi 미적용) — 생략", sport)
    return []
```
사유는 명시돼 있다("축구는 대조 가능한 무료 실데이터 소스가 얇아").
그러나 KBO·NPB 는 **공식 기록실·npb.jp 라는 실데이터 소스를 이미 갖고 있다**
(`kbo_stats.py`·`npb_stats.py` 가 그것을 긁어 `team_era`·`avg` 를 만든다).
대조할 재료가 있는데 대조하지 않는다.

---

# 55차 — `odds_coverage` 로 ODD-2 정정 · 정찰·평의회 상태

## ❌ ODD-2 정정 — KBO 배당 커버리지는 **최근 슬레이트에서 100%** 다

52차에서 *"KBO 98경기 중 25경기만 배당 보유(25.5%)"* 라고 적으며 분모가
정밀하지 않다고 단서를 달았다. 시스템이 이미 **일자별 커버리지 지표**를
남기고 있었다.
```
odds_coverage:kbo:2026-09-06   total  5 · with_odds  5 · rate 1.00
odds_coverage:kbo:2026-09-08   total  5 · with_odds  5 · rate 1.00
odds_coverage:mlb:2026-09-05   total 15 · with_odds 15 · rate 1.00
odds_coverage:mlb:2026-09-06   total 14 · with_odds 14 · rate 1.00
odds_coverage:mlb:2026-09-07   total 11 · with_odds 11 · rate 1.00
odds_coverage:npb:2026-09-06   total  6 · with_odds  6 · rate 1.00
odds_coverage:npb:2026-09-08   total  6 · with_odds  0 · rate 0.00   🔴
```
**KBO 는 최근 슬레이트에서 5/5 다.** 제 25.5% 는 소급 적재분을 분모에 넣은
탓이었다. 취소한다.

남는 사실 둘:
- **오늘(09-08) NPB 는 6경기 전부 배당 0** — `rate 0.00`. 24차 LIVE-3 의
  oddsportal 503 이 NPB 쪽에서 계속되고 있다는 뜻이다.
- **ODD-1(수집 배당이 h2h 뿐)은 그대로다** — `odds_snapshots.market` 전 행 `h2h`.
  커버리지가 100% 여도 토탈·런라인 행은 0이다.

## ✅ 정찰(scout)·평의회(council)는 돌고 있다

```
scout:mlb:{3711..}:2026-09-06  26건
   {"hours_to_start": 0.14, "active": true,
    "lineup": {"state": "확정", "sides": 2, "first_seen": …}}
council:calls:2026-09-07 = 10 · council:done:mlb:{4092..}:2026-09-07  20건
matchup:final:mlb:{4092..}:2026-09-07  11건   ← 최종 판정 락
```
- 정찰이 라인업 확정 시각과 `hours_to_start` 를 남긴다 — 관행값(KBO 1h·MLB 3h)을
  실측으로 바꾸기 위한 재료다(`lineup_lead_observed` 해시도 존재).
- 평의회가 09-07 에 10콜, 경기 20건 처리. 앞선 세션에서 "평의회 심의가 늘
  비었다"고 기록된 문제는 해소된 상태다.
- 최종 판정 락 11건 = 그날 MLB 경기 중 11건이 `✅ 최종` 을 받았다.
  (같은 날 원장은 36행 — 나머지는 예비 재판정이다.)

## 이 절에서 배운 것 — **시스템이 이미 남기는 지표를 먼저 찾아야 했다**

`odds_coverage:{sport}:{date}` 는 정확히 제가 계산하려던 값을 **일자별로**
갖고 있었다. 저는 그것을 안 보고 `games ⋈ odds_snapshots` 를 직접 세다가
소급 적재분에 걸려 틀린 수치를 냈다.
이 저장소의 「사본 금지」 규율은 코드에만 적용되는 것이 아니다 —
**감사도 이미 있는 계측을 먼저 읽어야 한다.**

---

# 56차 — 🔴🔴🔴 라인업 역행 카운터가 **역행이 일어나는 경로에 안 붙어 있다**

`app/engine/monitor_metrics.py` 는 정확히 LED-5/LED-6 을 세라고 만든 계측이다.
```python
async def note_lineup_regress(redis, sport, date):
    """[M-1] 확정 → 비확정 **역행** 1건.
    🔴 정상 전이(none→predicted→confirmed)는 세지 않는다. 세야 할 것은
       "확정이라고 해놓고 되돌아간" 경우뿐이다 — KBO 카드가 (잠정)을 다시
       달던 현상의 빈도를 이 숫자로 잡는다."""
    await _bump(redis, sport, date, "regress")
```

## MON-4 [최상·실측] 운영 카운터에 `regress` 필드가 **아예 없다**

```
monitor:mlb:2026-09-06  {'mat_total': '65', 'mat_injected': '19'}
monitor:mlb:2026-09-07  {'mat_total': '36', 'mat_injected': '10'}
                        ← regress 키가 없다 = 한 번도 증가하지 않았다
```
그런데 역행은 실제로 일어났고 **DB 에 흔적 13건**이 남아 있다(21차 LED-6).
```sql
SELECT sport, lineup_status, count(*) FROM games
 WHERE lineup_confirmed_at IS NOT NULL AND lineup_status <> 'confirmed'
→ mlb  predicted  13
```
그리고 원장에 왕복 이력도 있다(LED-4: 07:14 confirmed → 07:16 none → 07:32 confirmed).

## 원인 — 호출부가 **네 경로 중 하나**에만 있다

```
호출부 전수: app/scheduler.py:802  (단 한 곳)
  └ crawler_lineup_poll() 안 — **KBO·NPB 폴링 경로**
  └ 조건: DB 의 r["lineup_status"] == "confirmed" 이고 새 status ≠ confirmed
```
역행을 만들 수 있는 자리는 넷인데(40차 SCH-1) 계측은 하나에만 있다.
```
① lineups.py:257  refresh_mlb_lineup 의 무가드 UPDATE      ← DB 13건의 출처   계측 ✗
② pipeline.py:5514 rejudge_after_lineup 의 무가드 대입      ← 캐시 역행        계측 ✗
③ scheduler.py:959 guarantee_first_cards 가 DB 값을 캐시에 덮음               계측 ✗
④ scheduler.py:802 crawler_lineup_poll (KBO·NPB)                              계측 ✅
```
**기록된 역행 13건은 전부 MLB 인데, 계측은 KBO·NPB 경로에만 있다.**
그래서 `monitor:mlb:*` 의 `regress` 는 영원히 0 이고, 일일 요약도
"역행 0건"으로 나간다.

이 저장소가 스스로 적은 규율이 여기서 깨진다.
> `note_lineup_regress` docstring: "KBO 카드가 (잠정)을 다시 달던 현상의
> **빈도를 이 숫자로 잡는다**"

빈도를 잡으려면 현상이 일어나는 곳에 붙어야 한다.

## ✅ MON-5 — 같은 파일의 M-2(자료3 주입률)는 제대로 돌고 실측값을 준다

```
monitor:mlb:2026-09-06  mat_injected 19 / mat_total 65  = 29.2%
monitor:mlb:2026-09-07  mat_injected 10 / mat_total 36  = 27.8%
```
**판정 10건 중 3건만 오늘 타순(자료3)을 받고 돈다.** 나머지 7건은 잠정
라인업 상태에서 판정된다. 이것은 설계상 의도(T-30 잠정 카드 보장)와
일치하지만, **자료3 을 전제로 쓰인 프롬프트 규칙**("오늘 나온 9명이 기준이다")
이 실제로는 30%에서만 성립한다는 뜻이다.

`note_materials` docstring 이 이 지표의 존재 이유를 정확히 적었다 —
*"수집률이 아니라 **주입률**이다. 수집 로그는 18/18 인데 카드 2장이
'자료8 부재'라고 적었다 — 두 숫자가 갈리는 지점을 본다."*

## ✅ MON-6 — M-3 을 카운터로 만들지 않은 판단은 옳다

```python
⚠️ M-3(lineups 길이 이상)은 여기서 세지 않는다. `lineups` 테이블에 **행이
   남아 있어** DB 한 줄로 집계할 수 있다 — 이미 있는 사실을 카운터로 베끼면
   두 숫자가 어긋날 때 어느 쪽이 옳은지 알 수 없게 된다(사본 금지).
```
55차에서 제가 배운 것과 같은 원칙이다. **이 판단은 이 저장소의 규율이
가장 잘 적용된 예 중 하나다.**

---

# 57차 — `alerts.py` · `daily_summary.py` · `market_baseline.py` 전량

## 🔴🔴🔴 MB-1 [최상·코드확정] 시장 채점이 **픽 채점보다 먼저** 돌아 `our_hit` 이 71% 유실된다

`pick_ledger.grade_pending()` 의 실행 순서:
```python
# ① variable_ledger.grade()
# ② market_baseline.grade()      ← 여기서 our_hit 을 pick_ledger 에서 복사
mb = await _grade_market(pool, sport)
# ③ 그 다음에야 pick_ledger 자신을 채점
rows = await pool.fetch("... WHERE l.graded_at IS NULL ...")
for r in rows: UPDATE pick_ledger SET hit=…, graded_at=now()
```
그런데 `market_baseline.grade` 가 복사하는 쿼리는 **이미 채점된 행만** 본다.
```sql
_OUR_HIT = """SELECT hit FROM pick_ledger
               WHERE game_id = $1 AND is_final AND graded_at IS NOT NULL
               ORDER BY graded_at DESC LIMIT 1"""
```
새로 종료된 경기의 첫 통과에서는 ③이 아직 안 돌았으므로 **`our_hit = NULL`**
로 기록되고, 동시에 `graded_at = now()` 가 찍힌다. 다음 실행에서
`_PENDING` 이 `b.graded_at IS NULL` 만 고르므로 **그 행은 영원히 다시 안 본다.**

실측:
```
market_baseline_ledger  전체 77행 · graded 64 · void 1
   our_hit IS NULL      55행  (71.4%)   🔴
   market_hit IS NULL   21행
   divergence IS NULL   14행
```
같은 파일 주석이 이 결합을 피하려고 한 잡에 넣었다고 적는다.
> [시장 기준선] 같은 잡에서 채점한다 — **새 잡을 만들지 않는다**
> (타이밍 결합 회피: 따로 돌면 한쪽만 밀린다).

잡은 하나로 묶었는데 **그 안의 순서가 반대**다. 37차 CR-1(자료9)과 같은 형태다.

## 🔴🔴 MB-2 [최상·실측] 그래서 "시장 vs 우리"는 **77건 중 19건**으로만 성립한다

`daily_summary.market_lines` 가 내보내는 숫자는 이렇게 나온다.
```
summary(): 시장 34승22패 · 우리 12승10패 · 이견 47건 중 6적중
```
**분모가 서로 다르다.** 시장 56건 · 우리 22건이고, "이견 47건 중 6적중"의
47 에는 `our_hit` 이 NULL 인 행이 대부분 섞여 있다.

둘 다 채점된 행만 골라 다시 냈다 (n=19).
```
전체      n=19   시장 15/19 (78.9%)   우리 10/19 (52.6%)
시장 동의  n= 7   시장  6/7  (85.7%)   우리  6/7  (85.7%)   ← 같다
시장 이견  n=12   시장  9/12 (75.0%)   우리  4/12 (33.3%)   ← 우리가 크게 진다
종목별     mlb 10건(우리 6·시장 9) · kbo 5건(3·3) · npb 4건(1·3)
```
**시장과 갈릴 때 우리는 33.3%, 시장은 75.0%.** 표본 12건이지만 방향은
`market_agree_required` 게이트의 근거(30.8%)와 일치한다.
그리고 **동의할 때는 둘이 정확히 같다(6/7)** — 즉 우리 판정이 시장에 더하는
정보가 지금은 관측되지 않는다.

⚠️ 요약 카드가 내보내는 "이견 47건 중 6적중(12.8%)"은 **읽으면 안 되는 수치**다.
NULL 을 분모에 넣은 값이다.

## 🔴🔴 FRZ-1 [최상·실측] 동결 진행률이 **0/50 · 0/50 · 0/50** 이다

```python
FREEZE_START = {}                       # 리그별 예외 없음
FREEZE_START_DEFAULT = "2026-09-07"     # 어제
FREEZE_TARGET = 50
```
```
재시작(09-07) 이후 graded:  0건 (세 리그 전부)
전 기간 graded:            kbo 29 · mlb 94 · npb 23  = 146건
```
**146건을 쌓아 놓고 어제 0 으로 되돌렸다.**

같은 파일이 그 위험을 스스로 적어 두었다.
```python
#: 🔴 **이 재시작이 마지막이다.** 다음 재시작은 50건 리포트 이후에만 가능하다.
#   재료를 바꿀 때마다 표본을 버리면 영원히 50건에 도달하지 못한다.
FREEZE_RESTART_IS_FINAL = True

# ⚠️ [v1.4 2026-09-07] **이 잠금을 한 번 넘었다.** 사용자 지시로 표본을
#    다시 시작했다 — 자료12(실력 레이팅)가 판정 입력에 들어갔고 …
```
**"마지막"이라고 잠근 바로 다음 변경에서 그 잠금이 깨졌다.**
그리고 `FREEZE_RESTART_IS_FINAL = True` 는 상수일 뿐 아무것도 막지 않는다 —
읽는 코드가 없다(테스트만 이 값을 단언한다).

재시작 이력(주석에서 복원):
```
2026-09-03  v1.3 동결 시작 (MLB 는 자료9 주입 개시)
2026-09-04  C1·C2·C3 — 자료7·8 폐지, 자료9 교체 → 재시작
2026-09-05  C6 — 변수 대장 완성 → 전 종목 일괄 재시작 ("마지막")
2026-09-07  v1.4 — 자료12 + 시장 동의 게이트 → 또 재시작
```
**5일에 네 번 재시작했다.** 50건을 채우려면 MLB 약 4일·KBO/NPB 약 10일이
필요한데, 재료 변경 주기가 그보다 짧다.

## 🔴 ALT-1 [중] 워치독 코드 2개가 **라벨 없이** 나간다

```
코드에서 사용하는 W- 코드 16개 · alerts.WATCHDOG_CODES 등록 14개
🔴 미등록: W-LLM-PAID · W-SOURCE-DRIFT
```
`watchdog()` 은 `WATCHDOG_CODES.get(code, "점검 필요")` 라 두 코드는
`🚨 W-LLM-PAID · 점검 필요` 로 나간다. 다른 14개는 사람이 읽는 설명이 붙는데
이 둘만 무엇인지 알 수 없다. (`app/watchdog.py` 머리말은 8개만 적어 또 다르다.)

## 🔴 ALT-2 [중] `alert:budget` 이 TTL 없이 남으면 **모든 알림이 영구 차단**된다

```python
async def _over_budget(r):
    n = await r.incr(BUDGET_KEY)
    if n == 1:
        await r.expire(BUDGET_KEY, GLOBAL_WINDOW_SEC)   # ← n==1 일 때만 TTL
    return n - GLOBAL_BUDGET if n > GLOBAL_BUDGET else None
```
`incr` 는 성공하고 `expire` 가 실패하면(예외는 바깥 `except` 가 삼킨다)
키가 TTL 없이 남는다. 이후 `incr` 는 n≠1 이라 TTL 을 다시 안 건다 →
12 를 넘는 순간부터 **`bypass_suppression=False` 인 모든 알림이 영구 차단**된다.
단서는 `logger.warning("[alerts] 전역 예산 초과…")` 한 줄뿐이고, 그것을 감시하는
코드는 없다. 실측 시점에는 `alert:*` 키가 0개라 **지금은 정상**이다.

## ✅ ALT-3 정상 확인 — 억제 설계

- 억제 상태를 **Redis** 에 둔다. 프로세스 메모리 딕셔너리로 했더니 전혀
  억제되지 않았던 실사고(2026-08-25)의 수정 — 알림 주체가 매번 새 프로세스다.
- `SET NX EX` 로 선점하고 억제된 건수를 `HELD_KEY` 에 세어 **합산 표기**한다.
- 크래시·실행 리포트·사이클 리포트는 `bypass_suppression=True`.
- 워치독은 창을 15분으로 좁혔다("30분이면 5분 잡에서 6틱 중 1번만 도착").
  키가 **코드+대상**이라 서로 다른 고장이 서로를 막지 않는다.
- `_notify_mod.send_telegram` 을 **모듈 속성으로** 부른다 —
  "발송 지점이 둘로 갈라지면 한쪽만 막아도 다른 쪽으로 샌다."
- `StageResult.severity` 가 `no_games` 를 `cause` 보다 **먼저** 본다.
  휴식일마다 전량 실패 알림이 나가던 사고(2026-08-31 KBO·NPB 7건)의 수정.
- `overall_verdict` 가 휴식일을 "신뢰도 낮음"이 아니라 **확인된 사실**로 답한다.

## ✅ DS-5 정상 확인 — 요약 카드

- `build()` 가 **날짜가 아니라 킥오프**로 고른다. `l.date = today_kst()` 로
  조회해 MLB 판정이 해외판 요약에 **영원히 안 나타나던** 사고의 수정.
- 픽이 0건인 날에도 **가동률을 함께** 낸다 — "고장과 한산한 날을 구분".
- `monitor_lines` 의 M-3(타순 길이 이상)이 **확정 상태만** 센다.
  잠정 단계의 9명 미만은 정상인데 그것을 매일 "이상"으로 찍으면
  "정상을 결함으로 세는 지표는 진짜 결함을 그 속에 묻는다"(2026-09-03 교정).
- `cost_lines` 가 `odds_coverage` 를 읽어 커버리지를 낸다 — 55차에서 제가
  뒤늦게 찾은 그 지표를 요약 카드는 이미 쓰고 있었다.

---

# 58차 — `variable_ledger.py` 전량 · 변수 채점의 실적

## 실측 (전 기간 666행)

```
n 666 · 정량(claimed_n 있음) 599 (89.9%) · 주체 있음 484 (72.7%) · 채점 590
realized:  true 4 · false 22 · unverifiable 568 (85.3%) · NULL 72
채점 가능(true|false) = 26건 = 전체의 3.9%

subject_kind:  pitcher 328 (채점가능 23) · None 182 (0) · team 156 (3)
일자별 unverifiable:  09-03 33/36 · 09-04 98/107 · 09-05 211/220 · 09-06 223/246
raw 에 '[상황]' 포함:  1행
```

## 🔴🔴 VL-1 [최상] 변수의 **98.2%가 임계를 적지 않아** 채점 불능이다

`unverifiable` 568건 중 **임계가 읽힌 것은 10건뿐**이다(1.8%).
`threshold_of` 는 `숫자 + (이닝|실점|득점) + (미만|이하|이상|초과)` 만 읽는다.
실제 변수 서술 표본:
```
✗ 홈 선발 최원태의 피홈런 및 조기 실점 리스크 — 발생 시 원정 방향 약 7%p …
✗ 류현진의 두산전 대량 실점 재현 리스크 — …
✗ Minnesota Twins 불펜 최근 3경기 11이닝 7실점으로 후반 붕괴 — …
✗ Chicago White Sox 오프너 조기 강판 후 롱릴리프 실점 노출 — …
✗ 홈 타선의 득점력 침체 지속 리스크 — …
✓ Grant Holmes 조기 강판(4이닝 이하) 발생 시 홈 방향 약 +4%p …    ← 드문 경우
```

**원인은 프롬프트와 원장의 요구가 어긋난 것이다.**
```
프롬프트 [변수 형식] (prompts.py):
  "<리스크 서술> — 발생 시 <홈|원정> 방향 약 N%p · 발생 확률 X%
   · 현재 p에 M%p 기반영 · 근거 <자료 번호>"
   → 방향·크기·근거는 강제한다. **측정 가능한 임계는 요구하지 않는다.**

원장 채점 (variable_ledger.threshold_of):
  숫자 + 이닝/실점/득점 + 미만/이하/이상/초과  → 없으면 채점 대상 아님
```
모듈 머리말이 이 위험을 정확히 예고했다.
> ⚠️ **발명 금지.** 변수가 임계("3이닝 미만")를 명시하지 않으면 채점하지 않는다.
> 우리가 임계를 상상해서 붙이면 그 채점은 우리 상상을 채점하는 것이다.

판단은 옳다. **문제는 프롬프트가 그 임계를 쓰라고 시키지 않는다는 것**이다.
그래서 "변수를 정량화했다"(정량 89.9%)는 사실이지만, 그 정량은 `N%p·M%p`
(우리가 매긴 크기)이지 **검증 가능한 사건 정의**가 아니다.

## 🔴 VL-2 [상] 판정이 **성(姓)만 쓰면** 주체 매칭이 실패한다

`subject_kind IS NULL` 182건(27.3%) 표본:
```
"Sandoval의 제구 난조로 인한 5이닝 미만 조기 강판 리스크 — …"
   → 임계 있음(5이닝 미만) · 투수 이름 있음 · 그런데 subject = None
```
`subject_of` 는 `pitcher_name(jg, side)` 가 돌려주는 **전체 이름**이 원문에
그대로 있어야 매칭한다(`if name and name in text`). 판정은 성만 쓴다.
지시어 경로(`홈 선발`·`원정 타선`)도 이 문장에는 없다.

**임계도 있고 이름도 있는데 채점되지 않는다** — 두 결함이 겹친 자리다.

## 🔴 VL-3 [상] `team` 주체는 채점 축이 **득점 하나뿐**이다

```
team 156건 → 채점가능 3건
_TEAM_RUNS: SELECT home_score|away_score FROM games   ← 팀 득점만
judge_realized 의 단위 매핑: 이닝→innings · 실점→runs · 득점→runs
```
"불펜 3.5실점", "타선 침체" 같은 팀 변수는 임계를 적어도 **실측 축이 없다**
(팀 단위 이닝·불펜 실점을 조회하지 않는다). `pitcher_appearances` 는 있는데
쓰지 않는다.

## 🔴 VL-4 [중] 상황 변수 측정 장치 셋이 **전부 미참조**다

```
$ grep -rn "situation_report|situation_lines|team_report" app/ tools/
  → variable_ledger.py 자신 외 0건
```
- `situation_report` — 유형별 20건 표본으로 prior 승격 후보를 내는 함수
- `situation_lines` — 그 결과를 일일 요약에 실을 줄
- `team_report` — 팀×변수 현실화율

셋 다 부르는 곳이 없다. 그리고 재료도 없다 — **`raw` 에 `[상황]` 이 들어간
변수 원장 행이 1건**이다(21차에서 잰 대로 프롬프트에는 상황 태그가 22건 실렸다).
즉 상황 축은 **프롬프트에는 들어가고 원장에는 안 남는다.**

모듈 주석이 설계 의도를 적었다.
> 🔴 **prior 는 우리 채점 데이터가 만든다.** … 유형별로 20건이 쌓이고 리그 평균
> 대비 유의 편차가 나오면, 그때 비로소 그 유형에 %p 를 실을 자격이 생긴다.

1건으로는 영원히 20건에 도달하지 못한다.

## ✅ VL-5 정상 확인 — 얇은 표본에 숫자를 만들지 않는다

```python
TEAM_MIN_SAMPLE = 20
"rate": (round(realized / gradable, 3) if enough and gradable else None),
"status": "집계" if enough else f"표본 부족 (채점가능 {gradable}/{TEAM_MIN_SAMPLE})"
#  얇은 표본의 비율은 **보는 순간 믿게 된다**
```
- `unverifiable` 을 분모에서 뺀다(리그 기준선 계산에서도).
- 파싱 실패도 행으로 남긴다 — "형식 위반율을 재는 것이 이 원장의 절반이다."
- `subject_of` 가 이름도 지시어도 없으면 **`(None, None)`** 이다.
  "억지로 팀으로 넘기지 않는다 — 잘못된 주체로 채점하면 그 결과가 더 나쁘다."
- 승격을 자동화하지 않는다 — "측정이 스스로 판정 입력을 바꾸면 감시가 아니라
  되먹임이 된다."

---

# 59차 — 미참조 모듈 사냥 · 무료 사슬 실측 · 서술 경로

읽은 것: `starter_season.py`(447) `starter_recent.py`(178) `context_recent.py`(208)
`judge.py`(355) `council.py`(349) `narrator.py`(298) `performance.py`(373)
`lineup_diff.py`(378) `comparator.py`(269) `glass_report.py`(508)
`models/features.py`(400) `llm/ledger.py`(170) — 3,933줄.

## 🔴🔴🔴 LLM-1 [최상] 무료 사슬 1순위(groq)가 **환경변수가 깨져 2.7일간 전량 실패**했다

운영 Redis `llm_outage:*` 실측 (읽기 전용, 값은 마스킹):

```
Illegal header value b'Bearer <KEY>\nNVIDIA_API_KEY=<KEY>\nMISTRAL_API_KEY=xN5R…
  총 211건 · 최초 2026-09-04T08:22:59Z · 최후 2026-09-07T00:02:21Z
```

`GROQ_API_KEY` 안에 **groq 키 + `NVIDIA_API_KEY=…` + `MISTRAL_API_KEY=…` 세 줄이
통째로** 들어가 있었다. 여러 줄 블록을 그대로 붙여넣은 것이다. 줄바꿈이 들어간
문자열로 `Authorization` 헤더를 만들 수 없으니 **요청이 네트워크에 나가기도 전에**
죽는다.

일별 호출 원장(`llm_calls:*`)이 그대로 보여준다:

```
2026-09-04  groq:fail 49   gemini:ok 23  gemini:fail 26
2026-09-05  groq:fail 57   gemini:ok 32  gemini:fail 25
2026-09-06  groq:fail 102  gemini:ok 102      ← 정확히 1:1
2026-09-07  groq:fail 6    groq:ok 8    gemini:ok 6
```

09-06 은 **groq 실패 102 · gemini 성공 102** — 모든 호출이 1순위를 한 번 태우고
2순위로 떨어졌다. 09-07 00:02 이후 복구됐다(지금 스케줄러 env 는 56자 · 줄바꿈 0).

### 왜 아무도 몰랐나 — 분류가 `other` 였다

```python
async def record_outage(redis, provider, role, kind, detail=""):
    """kind는 `quota`·`rate_limit`·`auth`·`budget`·`other`."""
```
211건 전부 `kind=other` 다. **`auth` 가 아니므로 소진 표식이 안 붙었고**,
`_is_exhausted(p.name)` 가 매번 통과시켜 groq 을 계속 1순위로 불렀다.
영구적 설정 오류가 일시적 장애로 분류된 것이다.

`/health` 에는 `groq 0건(실패 102)` 로 **숫자는 보였다.** 그러나 표시는
`기타 (interpreter)` 뿐이고 `detail` 은 화면에 안 나간다 — 사용자가 볼 수 있는
것은 "groq 이 102번 실패했다" 까지고, **왜인지는 볼 수 없었다.**

## 🔴🔴🔴 LLM-2 [최상 · 보안] 그 실패 기록이 **API 키 3개를 평문으로** Redis 에 14일 보관한다

```python
"detail": detail[:200]     # ← 예외 문자열 원문. 마스킹 없음
TTL = 14 * 24 * 3600
```

예외 문자열이 `Bearer <groq키>\nNVIDIA_API_KEY=<키>\nMISTRAL_API_KEY=<키>` 를
그대로 담고 있으므로, **211개 행 각각에 세 벤더의 키가 들어 있다.**

지금도 살아 있는 키인지 확인했다 — 운영 env 의 `MISTRAL_API_KEY` 앞 4자
(`xN5R`)와 `NVIDIA_API_KEY` 접두사(`nvapi-`)가 유출된 문자열의 것과 **같다.**
즉 **현재 사용 중인 자격증명이 평문으로 남아 있다.**

> ⚠️ 값은 출력하지 않았다. 앞 4자·길이·접두사만 대조했다.

`format_summary` 가 `detail` 을 텔레그램에 안 내보내는 것은 다행이지만,
**저장 시점에 마스킹이 없다**는 것이 결함이다. 예외 문자열은 언제든 자격증명을
품을 수 있다 — 지금은 헤더였고, 다음엔 URL 쿼리일 수 있다.

## 🔴🔴 LLM-3 [상] 유료 확정 판정이 **09-03 이후 한 번도 성공하지 않았다**

```
llm_last_ok  {"anthropic": "2026-09-03T22:22:29+00:00",
              "gemini":    "2026-09-07T01:23:05+00:00",
              "groq":      "2026-09-07T14:09:09+00:00"}
```
`llm_calls:*` 에도 **09-04 부터 anthropic 항목이 아예 없다**(ok 도 fail 도 0).
`JUDGE_PROVIDER=anthropic` 인데 5일째 호출 자체가 안 나가고 있다.
`llm_outage` 에 `role=matchup` 행도 0건이다 — **실패한 게 아니라 부르지 않았다.**
(CG-1 무조건 `abort_if_credit_gone` 과 같은 계열인지 별도 확인 필요)

## 🔴🔴 ORP-1 [최상] `glass_report.py` 508줄 — **운영 호출부가 0건**이다

전 저장소 참조 실측:
```
tests/test_glass_report.py       (테스트 3곳)
tests/test_model_and_dedupe.py   (소스를 문자열로 읽는 계약 테스트)
→ app/ · tools/ 에서 부르는 곳 0
```
경기당 5절 투명 리포트는 **한 번도 생성된 적이 없다.**

자기 독스트링이 감시 연동을 주장한다:
> 🔴 역참조 실패(근거가 자료 번호를 안 가리킴)는 **환각 후보**다 —
> G3 가 이 숫자로 `W-TRACE` 를 울린다.

`W-TRACE` 를 전 저장소에서 찾으면 **이 파일의 주석 두 줄뿐**이다. 워치독 코드에도,
`alerts.WATCHDOG_CODES` 에도 없다. G3 도 없다. **울릴 곳이 없는 종을 문서가
울린다고 적어 두었다.**

계약 테스트 2개는 초록이다 — 소스 문자열을 검사하기 때문이다. 58차까지 다섯 번
나온 그 패턴이 그대로다: **텍스트를 검사하는 테스트는 배선이 끊긴 것을 못 본다.**

## 🔴 ORP-2 [상] `market_edge.py` 174줄 — 참조 0인데 **DATAFLOW.md 는 게이트로 문서화**한다

```
docs/DATAFLOW.md:51  ## ④ 게이트 — `engine/value_gate.py` · `engine/market_edge.py`
```
`value_gate.py` 는 실제로 배선돼 있다(`pick_ledger`·`form_card`·`daily_summary`).
`market_edge.py` 는 테스트에서만 불린다. 테스트 이름이 상황을 요약한다 —
`test_judgement_modules_never_import_market_edge`. **아무도 import 하지 않는 것을
"판정 모듈이 import 하지 않는다"고 검사하고 있다.**

## 🔴 ORP-3 [중] 그 외 참조 0 모듈

| 줄 | 모듈 | 상태 |
|---|---|---|
| 251 | `models/calibrate.py` | 테스트만 |
| 86 | `engine/interpret.py` | 어디서도 안 부름 (`interpreter.py` 와 별개 파일) |
| 63 | `collectors/betman.py` | `registry` 에 `wired=False` 로 등재만 |
| 36 | `app/main.py` | — |

`engine/interpret.py` 와 `engine/interpreter.py` 가 **동시에 존재**하고, 살아 있는
쪽은 `interpreter.py` 다. 이름이 한 글자 차이인 죽은 쌍둥이는 다음 세션이
잘못 여는 자리다.

## 🔴🔴 NAR-1 [최상] 서술 입력에 **배당·EV 가 들어간다** — 동결 규칙 위반

CLAUDE.md 동결:
> **배당은 판정·폼·서술의 입력에 절대 넣지 않는다** (판정 확정 후 후처리만)

`narrator._payload_game`:
```python
board = [
    {"desc": c["desc"], "odds": c["odds"], "ev": c["ev"],     # ← 배당·EV
     "grade": c.get("grade"), "note": c.get("grade_note")}
    for c in (jg.get("market_board") or [])[:6]
]
...
"market_board": board,
```

프롬프트는 말로 막는다 —
> 11. **배당·시장 확률을 서술에 쓰지 마라.**

**값은 들어가고 금지는 문장으로만 있다.** 이것은 "판정 입력에서 배당을 뺐다"는
설계를 문서가 아니라 배선으로 지키지 못한 자리다.

운영 실측 — MLB 보드 행이 실제 시장 배당을 들고 있다:
```
{"desc":"샌디에이고 파드리스 승","odds":1.52,"ev":-0.1488,"grade":"🔴"}
{"desc":"워싱턴 내셔널스 승",    "odds":2.57,"ev": 0.1308,"grade":"🔴"}
```

## 🔴🔴 NAR-2 [상] 그 서술은 **야구 카드에 실리지 않는다** — 버려지는 호출이다

```python
pipeline.py:2309   if sport not in _BB:
2311                   _narrated = await attach_narratives(judge_games, sport)
```
정규 경로는 야구를 막는다. 그런데 **재판정 경로에는 그 가드가 없다**:
```
5411  await _renarrate(refreshed, sport)          # _refresh_stale_research
5664  await _renarrate([jg], sport)               # rejudge_after_lineup  ← 야구 확정 라인업
5758  await _renarrate([jg], sport)               # ensure_game_fresh
```
`rejudge_after_lineup` 은 **KBO·NPB·MLB 확정 타순 재판정의 본선**이다.

그리고 산출물은 쓰이지 않는다. `render_game_easy` 는 판정된 야구를 4448 줄에서
`render_form_card` 로 조기 반환하고, `form_card.py` 에는 `narrative` 문자열이
**한 번도 등장하지 않는다**. `narrative` 를 읽는 4471·4484·4529·4737 은 전부
그 조기 반환 **뒤**에 있다 — 축구 전용이다.

운영 장애 원장이 호출을 증명한다:
```
역할별 장애: groq/narrator 76건 · gemini/narrator 15건 (09-04~09-07)
```
09-04~09-07 슬레이트는 야구뿐이다. **야구 재판정마다 서술을 부르고, 배당을
입력에 넣고, 결과는 버린다.**

## 🔴 GR-1 [중] 투명 리포트의 자료 목록에 **자료12·14 가 없다**

```python
MATERIALS = ((1,…),(2,…),…,(10,"변수 참조",""),(11,"이동·연전·날씨",""))
```
1~11 뿐이다. 지금 살아 있는 **자료12(ELO)·자료14(분기점 조사)** 는 리포트가
보여줄 자리조차 없다. 폐지된 7·8 은 "왜 없는지 매번 다시 묻지 않도록" 남겨
두었으면서, 새로 생긴 둘은 들어오지 않았다.

`stamped = {3, 9, 10, 11}` 도 사본이다. 조립 로그 원본을 확인했다:
```python
matchup.py:803
_mat_msg = "[materials] game=%s 자료3=%s(타순 %d명) 자료9=%s 자료10=%s 자료11=%s"
```
지금은 일치한다. 로그에 자료12 를 더하는 순간 이 집합은 따라가지 않는다.

## 🔴 JDG-1 [중] 구 Judge 도구 스키마가 `strict` 인데 필드 하나가 `required` 에서 빠졌다

```python
VERDICT_TOOL = {"strict": True, …
  "properties": {… "sentiment_used": {...} …},
  "required": ["game_id","p_claude","verdict","pass_recommended",
               "confidence","reversal_factor","conclusion_revised","excluded_picks"],
  "additionalProperties": False}
```
`sentiment_used` 만 `required` 밖에 있다. `strict` + `additionalProperties:False`
조합에서 이 형태는 벤더 검증에 걸릴 수 있다.

지금 터지지 않는 이유는 이 경로가 **이중으로 꺼져 있기** 때문이다:
```python
if sport in BASEBALL_SPORTS: return {"games": []}          # 야구 차단
if not self.mock and not self.settings.soccer_judge_enabled: return {"games": []}
```
야구는 못 들어오고 축구는 스위치가 꺼져 있다 — **구 Judge 355줄은 현재 목 모드
외에는 실행 경로가 없다.**

## 🔴 JDG-2 [하] 같은 프롬프트가 "2자 대조"와 "3자 대조"를 동시에 말한다

```
③ 2자 대조: 모델 확률 vs 전문가 컨센서스 … **시장(배당 암시확률)은 대조 대상이 아니다.**
…
- verdict: ③3자 대조 결론 + ⑤(a)승패/(b)가치 분리 판단 …
```
시장을 빼는 개정이 **본문에만 반영되고 출력 규격에는 안 됐다.** 모델은 있지도
않은 세 번째 축을 요구받는다.

## 🔴 CNL-1 [상] 평의회는 **Redis 가 없으면 절대 돌지 않는다**

```python
async def _once_ok(redis, ...):
    if redis is None: return False        # → run() 이 그 자리에서 None 반환
async def _cap_ok(redis, date):
    if redis is None: return False
```
캡을 셀 수 없으면 안 부른다는 판단 자체는 옳다("캡 없는 AI 호출을 만들지 않는다").
다만 **Redis 없는 실행에서 심의가 조용히 0건**이 되고, 그 사실은 `logger.info`
한 줄로만 남는다.

## 🔴 CNL-2 [중] "유료 경로를 절대 타지 않는다"고 적고 **주전이 유료(퍼플렉시티)** 다

```python
#: 🔴 심의·조사는 **절대 유료 판정 경로를 타지 않는다.**
COUNCIL_ROLE = "council"
…
async def investigate(jg):
    from app.research.perplexity import ask_json
    got = await ask_json(prompt)          # ← 주전. 유료다.
```
주석이 막으려는 것은 **Anthropic** 이다(`judge_route.chain()` 이 `matchup` 역할에만
유료를 허용). 그러나 문장은 "유료 경로"라고 적혀 있고, 조사의 1순위는 퍼플렉시티다.
비용을 세는 사람이 이 주석을 믿으면 경기당 퍼플렉시티 1콜을 못 본다.

## 🔴 PERF-1 [하] `WinProbAdjuster.home_edge()` 는 **아무도 부르지 않는다**

```python
def home_edge(self, sport: str) -> float:
    return self.s.adj_home_mlb if sport == "mlb" else self.s.adj_home_soccer
```
전 저장소 참조 1건 — 정의 그 자체뿐. `adjust()` 의 순차 적용에 홈 어드밴티지
단계가 없다. `adj_home_mlb`·`adj_home_soccer` 설정값도 따라서 죽어 있다.

## 🔴 CMP-1 [중] 3단 대조봇 269줄도 **야구에서 안 돈다**

`compare_game` 은 `cells`(5칸 카드)를 읽는다. 5칸 카드는 2026-08-30 커밋
`c3b1c8e` 이후 야구에서 만들어지지 않는다(`_BB_SKIP_OLD`). 축구는 꺼져 있다.
→ 34차에서 잰 "5칸 카드 계열 약 1,900줄 사문화"에 이 269줄이 포함된다.

## 🔴 FEAT-1 [중] λ 학습 계열 715줄도 같은 상태다

`models/features.py`(400) → `models/lambda_model.py`(315) → `pipeline.py`.
야구는 `jg["lam"] = None` 이라 λ 를 안 쓴다(37차). 축구는 꺼져 있다.
`features.py` 의 누수 방지 장치(`assert_no_leakage`·`rolling_park_factors`·
`time_split`)는 잘 만들어져 있으나 **현재 어떤 판정에도 닿지 않는다.**

## ✅ 정상 확인 — `today_nine` 순서는 어긋나지 않았다

`attach_lineup_view`(오늘 9명)가 `_attach_lineup_intent`(평소 대조) **뒤**에
와야 `compared=True` 가 된다. CR-1 과 같은 순서 결함을 의심하고 실측했다:

```
운영 analysis:* 39키 → today_nine 보유 4경기
슬롯 status 분포: {'usual': 71, 'new': 1}
note("평소 비교 불가") 사이드: 0
```
`unknown` 0 건 — 재판정 경로(`_prepare_games_for_judge` at 5571·5733)가
`_attach_lineup_intent`(2792) 뒤에 오므로 순서가 맞다. **의심은 틀렸다.**

---

# 60차 — 발송 계측 · 카드 · 배당 소스

읽은 것: `pregame_push.py`(798) `form_card.py`(240) `card_markets.py`(182)
`collectors/base.py`(267) `collectors/odds.py`(336) `collectors/odds_free.py`(212)
`pitcher_matchup.py`(307) `value.py`(33) `physical.py`(93) `dispatch_stats.py`(106)
`metrics.py`(75) — 2,649줄.

## 🔴🔴🔴 DSP-1 [최상] 발송률이 **구조적으로 100%에 닿을 수 없다** — 다 보낸 경기가 미발송으로 집계된다

CLAUDE.md 발송 규율:
> **목표는 발송률 100%이고, 미발송은 전건에 사유가 붙어야 한다 —
> "조용한 0"은 결함이다.** 결과는 `dispatch:{sport}:{date}` 에 쌓인다.

운영 원장 실측:
```
dispatch:mlb:2026-09-06 {"window_not_open":42,  "sent":16, "unchanged":78,  "revised":9, "card_cap":55}
dispatch:mlb:2026-09-07 {"window_not_open":133, "sent":11, "unchanged":239, "revised":6, "card_cap":186, "card_reserved":1}
```

`dispatch_stats.summary` 의 셈법을 그대로 적용하면:

| | 09-06 | 09-07 |
|---|---|---|
| 대상(target) | 158 | 443 |
| 도달(sent+revised+unchanged) | 103 | 256 |
| **발송률** | **65.2%** | **57.8%** |
| 미발송 | card_cap 55 | card_cap 186 · card_reserved 1 |

**이 186건은 미발송이 아니다.** 카드 2장을 이미 다 보낸 경기를 5분 폴링이
계속 다시 집어서, 그때마다 `card_cap` 을 하나씩 적은 것이다.

```python
# pregame_push.send_game_prediction
_n = int(prev.get("n") or 0)
if _n >= CARD_CAP:                       # ← 해시 비교보다 **앞**
    return await _skip("card_cap")
...
if prev and not lineup_changed and not verdict_changed:
    return await _skip("unchanged")      # ← 이건 DELIVERED 로 센다
```

```python
# dispatch_stats
DELIVERED  = ("sent", "revised", "unchanged")
NOT_TARGET = ("window_not_open", "already_started", "not_supported", "void")
#  card_cap · card_reserved 는 둘 다 아니다 → 전부 misses
```

같은 사실("이미 도달했다")을 두 이름으로 부르는데 **한쪽만 도달로 센다.**
`unchanged` 를 도달로 세기로 한 판단은 주석에 명시돼 있다 —
> 이미 도달한 카드다 — 미발송이 아니다. 분자에 넣는다.

`card_cap` 은 **더 확실하게** 도달한 상태인데 분모에만 들어간다.

결과: 일일 요약이 `📮 MLB 발송 256/443 (58%) · 미발송 186건 — 카드 2장 상한 도달`
로 나간다. 실제로는 그날 모든 경기가 카드를 받았다. **100%가 목표인 지표가
잘 돌아갈수록 낮아진다** — 경기가 일찍 카드를 받을수록 남은 폴링 틱이 많아지고,
그만큼 `card_cap` 이 쌓인다.

`window_not_open`(133)이 NOT_TARGET 인 것과 대조하면 의도는 분명하다 —
"보낼 상황이 아닌 것"은 분모에서 뺀다. `card_cap` 이 바로 그 부류다.

## 🔴 ODD-3 [중] "야구는 배당을 안 쓴다"는 주석과 실제가 어긋난다

`collectors/odds.py`:
```python
# 야구는 Odds 배당·토탈 라인을 쓰지 않는다 (2026-08-29).
BASEBALL_ODDS_SPORTS = ("mlb", "kbo", "npb")
async def snapshot_odds(...):
    if sport in BASEBALL_ODDS_SPORTS:
        logger.info("[odds] snapshot skipped — 야구 언더오버 미사용"); return 0
```
맞다 — **The Odds API 경로**로는 안 받는다. 그러나 배당은 다른 문으로 들어온다:

```
odds_free.collect_mlb → espn(1순위) → sharp(2순위)  → odds_snapshots(provider 컬럼)
odds_free.collect_asia → oddsportal                → odds_snapshots
```
운영 MLB 보드 실측: `odds 1.52 · ev -0.1488` · `odds 2.57 · ev 0.1308`.

`odds.py` 만 읽으면 "야구에 배당이 없다"고 결론 내리게 된다. 39차에서 내가
`active_keys=[]`(pipeline:1533)를 보고 같은 오판을 했다.

## 🔴 ODD-4 [중] 무료 배당 모듈의 격리 선언이 **import 경계로만** 지켜진다

`odds_free.py` 머리말:
> 🔴 **배당은 판정 입력에 흐르지 않는다.** 이 모듈도 판정 경로에서 import 되지
> 않는다 — import 경계 테스트가 강제한다.

배당이 새는 실제 경로는 import 가 아니라 **데이터 필드**다 —
`odds_snapshots` → `build_board` → `jg["market_board"]` → `narrator._payload_game`
(59차 NAR-1). import 경계 테스트는 이 길을 볼 수 없다.

**"판정 경로가 이 모듈을 import 하지 않는다"와 "판정 입력에 배당이 없다"는
같은 명제가 아니다.** 지금 전자만 검사한다.

## 🔴 CRD-1 [중] `card_markets.py` 182줄 중 야구가 쓰는 것은 없다

```python
def market_calls(jg):
    hc = handicap_call(cmp_.get("counts") or {}, cmp_.get("favored"))   # jg["compare"]
    ...
    if (jg.get("sport") or "").lower() in ("mlb","kbo","npb"):
        return out                     # ← 토탈은 여기서 끝
```
- `jg["compare"]` 는 3단 대조봇 산출이고, 대조봇은 5칸 카드를 읽는다 →
  야구에서 5칸 카드가 안 만들어지므로(`_BB_SKIP_OLD`) `compare` 는 항상 비어
  `handicap_call` 이 `{}` 를 돌려준다.
- 토탈은 그 아래 야구 조기 반환에 막힌다.
→ **야구에서 `market_calls` 는 항상 빈 목록이다.** `league_total_baseline`·
`totals_call`·`expected_total` 도 함께 죽는다.

## 🔴 FC-1 [중] 카드 게이트는 **파이프라인과 같은 함수를 부른다** — 정상 확인

```python
from app.pipeline import market_disagreement    # form_card.rec_label
from app.pipeline import MARKET_DISAGREE, market_disagreement   # _market_why
```
2026-09-05 실사고("요약과 카드가 서로 다른 말을 했다")의 수정이 제대로 들어가
있다. 게이트 사본이 아니라 **호출**이다. 확인용으로 남긴다.

다만 `form_card` 가 `app.pipeline` 을 import 한다 — 엔진이 파이프라인을 거꾸로
당긴다. `pregame_push` 도 `app.bot.main.two_layer_html` 을 import 한다.
계층이 뒤집힌 자리 둘이다.

## 🔴 PGP-1 [하] `_bet_line` 이 사유를 **덮어쓴다**

```python
if jg.get("judge_confidence") == "low": why = "확신도 하"
elif jg.get("starter_low_sample"):      why = "선발 표본 부족"
elif _market_why(jg, s):                why = _market_why(jg, s)
elif p is not None: ... why = f"추천 하한 …"
state = jg.get("pick_state") or _ps(...)[0]
if state != "final":
    why = "라인업 미확정"            # ← 앞의 사유를 무조건 덮는다
```
라인업이 미확정이면 앞에서 무엇이 걸렸든 사유가 "라인업 미확정" 하나로 뭉개진다.
확신도 하 + 표본 부족 + 시장 이견이 동시에 있어도 카드는 그중 아무것도 안 적는다.

## ✅ BASE-1 정상 확인 — 429 오분류 방지가 코드로 서 있다

```python
if status == 429:
    if any(m in lowered for m in RATE_LIMIT_MARKERS): return "rate_limit"
    if any(k in lowered for k in CREDIT_MARKERS):     return "credit"
    return "rate_limit"                     # 기본이 rate_limit
if status == 400:
    # Anthropic 은 크레딧 소진을 402 가 아니라 400 invalid_request_error 로 준다
    return "credit" if any(k in lowered for k in CREDIT_MARKERS) else "other"
```
CLAUDE.md 의 에러 분류표와 일치한다. 400→credit 승격 조건도 본문 문구를 요구해
과잉 승격을 막는다.

## ✅ PM-1 정상 확인 — 투수 맞대결이 표본 하한을 지킨다

```python
MIN_RATE_APPS = 3          # 이 미만이면 ERA 를 산출하지 않는다
MIN_SIMILAR_NINE = 7       # 오늘 9명과 7명 이상 겹친 등판만 '유사'
SEASON_VS_TEAM_LABEL = "시즌 상대팀 방어율"   # last-5 오표기 금지
if st is None or st >= cutoff: continue     # 오늘 경기는 한 줄도 안 넣는다
```
라벨을 상수로 박아 "시즌 상대팀 ERA"가 "오늘 9명 상대"로 읽히는 것을 막는다.
다만 발동 조건이 좁다 — `attach` 는 `_lineup_intent_one` 안에 있고, 그것은
`allow_final and lineup_is_confirmed` 일 때만 돈다.

---

# 61차 — 별점이 **다섯 벌** 있고, 서로 다른 눈금을 쓴다

읽은 것: `card.py`(766) `value_gate.py`(앞 70) `markets.row_stars` 주변 —
그리고 별점 다섯 구현의 전수 대조.

## 🔴🔴🔴 STR-1 [최상] 같은 경기가 카드와 보드에서 **다른 별 개수**로 나간다

전 저장소에 별점 함수가 **다섯 개** 있다. 눈금도 상한도 다르다.

| 어디 | 함수 | 눈금 | 상한 | 쓰는 화면 |
|---|---|---|---|---|
| `value_gate.py:33` | `stars(p, provisional=)` | 확률 0.53/0.58/0.63/0.68 | ★5 | **야구 카드**(form_card) |
| `daily_summary.py:25` | `stars(p)` | 확률 0.53/0.58/0.63/0.68 | ★5 | 일일 요약 |
| `pipeline.py:4173` | `board_stars(c, jg, s)` | **충족 조건 개수** | ★4 | 슬레이트 보드 |
| `markets.py:386` | `row_stars(c, confidence)` | 등급 🟢4·🟡3·🔴1·⚪0 | ★4 | 심층 마켓 행 |
| `soccer_trial.py:67` | `stars(p)` | 확률 0.45/0.50/0.55/0.60 | ★5 | 축구 트라이얼 |

승률 0.60 짜리 픽은
- 카드에서 **★★★** (0.58 사다리)
- 보드에서 **★★** (58% 통과 1 + 축 2개 1, 62% 미달)
- 심층 행에서 **★★★** (🟡 등급)
로 각각 나온다. 같은 화면 안에서 별 개수가 어긋난다.

## 🔴🔴 STR-2 [최상] 2026-09-07 "확신도를 별점에서 뺀다" 수정이 **한쪽에만 들어갔다**

`markets.row_stars` 는 고쳤다:
```python
"""🔴 [v1.4 2026-09-07 사용자 지시] 종전에는 확신도 `상` 이면 한 칸 올리고
   `하` 면 한 칸 내렸다. 620행 분석에서 **확신도 표기가 역정보**로 나왔다 —
   추천 적중 30.8%(n=13) < 보드만 59.7%(n=77).
   확신을 별점으로 증폭하면 사용자가 가장 못 맞히는 픽을 가장 굵게 본다."""
return STARS_BY_GRADE.get(c.get("grade"), 0)      # confidence 인자를 버린다
```

`pipeline.board_stars` 는 **그대로다**:
```python
if jg.get("judge_confidence") == "high":
    n += 1                       # ← 확신도로 별을 하나 더 준다
```

커밋 이력이 갈린 지점을 그대로 보여준다:
```
row_stars   확신도 제거 → d222bb0  2026-09-07  "v1.4 — 실력 축을 복원하고…"
board_stars 확신도 가산 → 78d4444  2026-08-27  (그 뒤로 손대지 않았다)
```

그리고 `board_stars` 쪽이 **슬레이트 보드**를 만든다
(`star_rows` → `render_star_board` → `render_analysis`).
즉 "사용자가 가장 못 맞히는 픽을 가장 굵게 본다"는 그 현상이, 고쳤다고 기록된
뒤에도 주 화면에서 계속되고 있다.

## 🔴🔴 STR-3 [상] `daily_summary.stars` 는 `value_gate._STAR_LADDER` 를 **손으로 베낀 사본**이다

```python
# app/engine/value_gate.py:31  ← 원본
_STAR_LADDER = ((0.68,"★★★★★"),(0.63,"★★★★"),(0.58,"★★★"),(0.53,"★★"),(0.0,"★"))

# app/engine/daily_summary.py:25  ← 같은 숫자를 다시 적었다
return ("★★★★★" if p >= 0.68 else "★★★★" if p >= 0.63 else
        "★★★" if p >= 0.58 else "★★" if p >= 0.53 else "★")
```

CLAUDE.md 가 이름 붙여 금지한 그 패턴이다:
> **시스템에 이미 존재하는 사실은 다시 적지 말고 원본을 읽어라.**
> 임계값을 손으로 옮겨 적는 순간 그것은 미래의 오탐이다.

`value_gate.stars` 는 `provisional` 인자로 "(잠정)"을 병기한다. 사본에는 그
개념이 없다 — **일일 요약은 잠정 카드와 확정 카드를 같은 별로 적는다.**

## 🔴🔴 CARD-1 [상] `card.py` 766줄 중 야구가 쓰는 것은 **`verdict_block` 하나**다

| 함수 | 야구에서 도달하는가 |
|---|---|
| `build_card` · `build_side` · `_*_facts` (5칸 사실층) | ❌ `_attach_cell_verdicts` 안 — `_BB_SKIP_OLD` 가 막는다 |
| `render_state_card` · `compare_lines` · `compare_line` · `card_summary_line` · `slate_compare_row` | ❌ `render_game_easy` 안 — 4448 조기반환 뒤 |
| `league_baselines` · `cell_metrics` · `CELL_METRICS` | ❌ 5칸 해석층(2단) 전용 |
| `tilt_by_cell` | ❌ **참조 0건** |
| `scoring_metrics` · `SCORING_CELL` | ❌ `card_markets` 가 야구를 조기반환 |
| `SYM_VALUE` | △ `comparator` 만 쓴다(그것도 야구에서 안 돈다) |
| **`verdict_block`** | ✅ `render_star_board`(4271) — 슬레이트 심층 |

`verdict_block` 만 2026-09-07 에 새로 쓰였고, 그 위 700줄은 08-27~08-30 의
5칸 체제 유물이다. 주석이 그 사실을 모른 채 아직 "1단 수집봇"·"2단"·"3단"을
설명한다 — **다음 세션이 이 파일을 열면 살아 있는 체제로 읽는다.**

## 🔴 CARD-2 [중] `verdict_block` 이 카드 본문과 **다른 확신도 표기**를 쓴다

```python
_CONF_KR = {"high":"높음", "medium":"보통", "low":"낮음"}     # card.py
```
`form_card` 는 `m.get('확신도')`(판정이 한국어로 낸 값 '상/중/하')를 그대로 쓴다.
`verdict_block` 은 `jg["judge_confidence"]`(영문 high/medium/low)를 한국어로
번역해 쓴다. **같은 경기에 대해 카드는 "확신도 중", 보드 심층은 "확신도 보통"**
이라고 적는다. 같은 값의 두 표기다.

## ✅ CARD-3 정상 확인 — `verdict_block` 은 확률을 지어내지 않는다

```python
if q is not None and n is not None:
    out.append(f"      발생 확률 {q:.0f}% · 그때 {side} 쪽으로 {n:.0f}%p")
elif n is not None:
    out.append(f"      발생하면 {side} 쪽으로 {n:.0f}%p (발생 확률은 미확인)")
```
`발생 확률` 은 자료14 가 답을 준 경우에만 붙는 선택 칸이고, 없으면 없다고 쓴다.
09-07 형식 개편의 주석도 실측(`card:mlb:2026-09-06`)에 근거해 여섯 결함을
번호로 적어 두었다 — 이 저장소에서 가장 잘 쓰인 개편 기록 중 하나다.

---

# 62차 — 라인업 의도 해석이 **선수가 아니라 유형으로** 묶여 40%를 잃는다

읽은 것: `interpreter.py`(528) `lineup_intent.py`(154) `markets.py`(775).

## 🔴🔴🔴 LI-1 [최상] 실측 — 변경점 272건이 원장에 164건만 남는다 (**39.7% 유실**)

운영 DB 에서 최근 60개 사이드를 골라, 그 경기의 확정 타순(`lineup_events`)과
평소(`lineup_history.usual`)를 **운영 코드 그대로** 돌려 변경점을 다시 셌다:

```
검사한 사이드 60
실제 변경점 272건 → 유형 164종
유실 108건 (39.7%)
중복 유형이 있는 사이드 50/60 (83%)

  game=4093 New York Mets       {'regular_out': 3, 'order_promote': 1}
  game=3725 Washington Nationals {'regular_out': 3, 'order_demote': 1}
  game=3724 Chicago White Sox   {'regular_out': 3, 'order_promote': 1, 'new_starter': 1}
  game=3723 New York Yankees    {'regular_out': 3, 'order_promote': 1, 'order_demote': 1}
```

**주전 셋이 빠져도 원장에는 "주전 결장" 한 줄만 남는다.**

원장 현황이 그 결과를 그대로 보여준다:
```
lineup_verdicts  323행 / 166사이드 = 사이드당 1.95종
  regular_out 158 · position_change 48 · order_demote 44
  order_promote 29 · new_starter 27 · dh_rest 17
  부호  ▼213 · =105 · ▲5
```

## 왜 — 병목이 **둘** 있고, 둘 다 `change_type` 을 키로 쓴다

### ① 해석 단계 (`interpreter.interpret_lineup_intent`)

```python
by_type = {c["type"]: c for c in changes}      # ← 같은 유형이면 **덮어쓴다**
for row in (res.data or {}).get("items") or []:
    src = by_type.get(row.get("change_type"))
    if not cites_facts(why, [src["detail"]]):  # ← 마지막 1건의 문구하고만 대조
        dropped.append(f"{t}(인용 없음)")
        continue
```

LLM 은 변경점 3건을 받아 3건을 답한다. 그런데 셋 다 `change_type="regular_out"`
이므로 **전부 같은 `src`(마지막 선수)** 를 가리키고, 다른 두 선수를 인용한
답은 "인용 없음"으로 폐기된다. **인용 강제 장치가 정상 판정을 죽인다.**

프롬프트가 요구하는 스키마 자체가 이 구조를 만든다:
```python
"change_type": {"description": "주어진 변경점의 type 값 그대로"}
```
변경점을 식별하는 키가 **유형뿐**이고 인덱스도 선수 이름도 없다.

### ② 적재 단계 (`lineup_intent.record_verdicts`)

```sql
ON CONFLICT (game_id, side, change_type) DO UPDATE
```
설령 셋이 해석을 통과해도 **DB 유니크 키가 (game_id, side, change_type)** 이라
서로를 덮는다. 마지막 하나만 남는다.

두 병목이 독립적이므로 **한쪽만 고치면 다른 쪽이 계속 지운다.**

## 🔴 LI-2 [상] 사실은 살아 있고 **해석만 죽는다** — 그래서 눈에 안 띈다

```python
def merge_changes_into_research(research, side, changes, headline):
    by_cell = {}
    for c in changes or []:
        by_cell.setdefault(c.get("cell") or "batting", []).append(c["detail"])  # 전부 보존
```
변경점 **문장**은 세 건 다 `research` 에 들어가 카드·프롬프트에 실린다.
사라지는 것은 그 각각에 대한 **▲▼ 판단과 득점 방향**이다.

그래서 화면상으로는 "라인업 변경 3건"이 정상으로 보이고,
`scoring_direction`·`handicap_note` 만 **한 건 몫의 표**로 계산된다:

```python
def scoring_direction(items_home, items_away):
    for it in items or []:
        v = _SCORE_VALUE.get(it.get("scoring_dir"), 0)   # items = 유형 수만큼
```
주전 3명 결장(저득점 3표)이 **1표**로 들어간다. 상대가 다른 유형 1건만
있어도 상쇄돼 "중립"이 된다.

`handicap_note` 는 다행히 `changes`(원본 목록)를 받으므로 온전하다 —
같은 모듈 안에서 한 함수는 원본을, 다른 함수는 유실본을 쓴다.

## 🔴 MKT-1 [중] 야구 추천 자격이 **시즌 누적**을 아직 쓴다

2026-09-04 대원칙:
> 판정에 들어가는 모든 데이터는 최근 3~5경기만. **시즌 누적·통산·상대전적 금지.
> 예외 없음.** (자료7·8 폐지)

그런데 추천 자격의 실데이터 축은 시즌값이다:
```python
def _season_edge(jg):
    hw, aw = st.get("home_win_pct"), st.get("away_win_pct")     # 시즌 승률
    he, ae = st.get("home_pitcher_era"), st.get("away_pitcher_era")
    ...
def _research_pitcher_era(research, side):
    era = blk.get("era_season")            # ← 시즌 ERA 우선
    if era is None: era = blk.get("era_recent")
```
`_axis_data` → `axes` → `board_stars`(★) · `axes_count` 로 흘러간다.

대원칙이 막은 것은 **판정 프롬프트 입력**이고 여기는 **표시·별점**이므로
형식상 위반은 아니다. 다만 **같은 시즌 ERA 가 자료7 에서는 폐지되고
근거 축에서는 살아 있다** — 문서 어디에도 그 구분이 적혀 있지 않다.

## 🔴 MKT-2 [하] `approved` 는 "추천"이 아닌데 이름이 그렇게 읽힌다

운영 실측 — 승률 44% 행:
```json
{"desc":"워싱턴 내셔널스 승","p":0.44,"required_prob":0.63,
 "approved":true,"grade":"🔴","grade_note":"승률 44% < 하한 63%"}
```
`_approve` 는 확률 문턱을 보지 않는다(패스 권장·저신뢰·플래그만 본다).
실제 문턱은 `grade_candidate` 와 `qualifies` 가 건다.

호출부는 항상 `c.get("approved") and qualifies(...)` 로 둘을 함께 본다 —
지금은 안전하다. 그러나 `approved=True` 인 44% 행이 원장·캐시에 그대로
남으므로, 나중에 이 필드를 단독으로 읽는 코드가 생기면 즉시 틀린다.

## ✅ INT-1 정상 확인 — 방향 오독 검증이 사분위로 서 있다

```python
if q1 <= val <= q3: continue        # 사분위 안은 "평소" — 표를 던지지 않는다
if all(votes) and symbol == "▼": return "수치는 유리를 가리킨다 — …"
```
2026-08-27 실사고(OPS 0.760 vs 기준 0.756 이 "방향 오독"으로 폐기)의 수정이
임의 여유값이 아니라 **데이터 자체의 산포**로 들어가 있다. 가드가 반대 위험
(정상 판정 폐기)을 함께 고려한 드문 사례다.

다만 이 장치는 5칸 체제 전용이라 **야구에서 돌지 않는다**(`_BB_SKIP_OLD`).
`interpret_lineup_intent` 에는 방향 검증이 없다 — 야구에서 실제로 도는 쪽에는
그 보호가 없다.

---

# 63차 — 정정 하나, 그리고 그 정정이 드러낸 더 큰 구멍

읽은 것: `team_form.py`(629 중 440) `llm/judge_route.py`(120) + 운영 설정 실측.

## ⛔ 59차 LLM-3 **정정** — "유료 판정이 09-03 이후 없었다"는 **틀렸다**

내가 근거로 쓴 것:
```
llm_calls:2026-09-04~09-07  → anthropic 항목이 0
llm_last_ok {"anthropic": "2026-09-03T22:22:29+00:00"}
```

원장을 쓰는 곳을 전수로 찾아보니 **`app/llm/provider.py` 한 곳뿐**이다:
```
app/llm/provider.py:668  record_call(redis, p.name, role, True)
app/llm/provider.py:682  record_call(...False) / record_outage(...)
app/llm/provider.py:696  record_call(...) / record_outage(..., "budget", ...)
app/llm/provider.py:710  record_blackout(redis, role)
→ 그 외 app/ 전체에 record_call 호출 0건
```

판정 사슬은 `provider.py` 를 지나지 않는다 —
`team_form.complete_json` 이 `_complete_free`(→`llm/openai_compat`) 또는
`anthropic.AsyncAnthropic` 를 **직접** 부른다.

다른 계수기로 재확인:
```
llm:anthropic:calls:2026-09-07 = 28      ← judge_route.note_paid_call 이 센다
```
**유료 판정은 09-07 에 28회 나갔다.** 내 결론이 틀렸다.

> 실수의 형태: "계수기가 0이다"를 "일이 0이다"로 읽었다.
> CLAUDE.md 가 적어 둔 것과 같다 — **상태값은 의도한 것이 동작한다는 증거가
> 아니다.** 계수기를 쓸 때는 **그 계수기가 무엇을 세는지 먼저** 확인해야 했다.

## 🔴🔴🔴 LLM-4 [최상] 그런데 그 사실이 더 큰 결함이다 — **원장이 판정을 못 본다**

`llm/ledger.py` 머리말이 원장의 목적을 이렇게 적는다:
> **왜 기록하는가.** 지금 폴백 체인은 Gemini → Groq → Anthropic 순인데,
> 그 순서가 옳다는 근거가 없다. 어느 provider 가 실제로 가장 안정적인지는
> **며칠 치 장애 이력을 봐야** 안다. **순서를 바꾸기 전에 이 표를 먼저 본다.**

그 표에 잡히는 역할은 실측상 **넷뿐**이다:
```
llm_outage 역할별 (09-04~09-07): interpreter 173 · narrator 91 · intent 1
```
`matchup` · `matchup_prelim` · `form` · `council` — **판정 사슬 전체가 없다.**

즉 "폴백 순서를 바꾸기 전에 보는 표"가 정작 **폴백 순서가 가장 중요한 경로를
안 본다.** 그리고 `/health` 는 그 표로 provider 생사를 표시한다:

```python
mark = "🟢" if _alive(iso, now) else "🔴"     # 6시간 내 성공이 없으면 🔴
```
`llm_last_ok["anthropic"]` 이 09-03 에 멈춰 있으므로 **`/health` 는 오늘도
`🔴anthropic` 을 찍는다** — 실제로는 어제 28번 성공한 provider다.
모듈 자신이 그 함정을 경고해 놓았는데(`"부르지 않은 provider 는 '미확인'이지
'죽음'이 아니다"`) 정작 이 경우를 못 걸렀다. 부르긴 부르는데 **기록 경로가
다른** 세 번째 상태가 있다.

## 🔴🔴🔴 LLM-5 [최상] 예비 판정의 무료 사슬이 **후보 1개**다 — 설계 주석과 정반대

`judge_route.chain()` 주석:
> 🔴 무료 후보를 **여럿** 둔다. Nemotron 이 오디션에서 6건 중 1건을
> `503 Service temporarily overloaded` 로 놓쳤다 — 무료 인프라는 가끔 밀린다.
> **하나만 두면 그 경기는 카드가 못 나간다.**

운영 실효 설정:
```
free_judge_model = 'gemini/gemini-3.7-flash'          ← 후보 1개
free_form_model  = 'nvidia/nvidia/nemotron-3-ultra-550b-a55b,
                    groq/qwen/qwen3.8-27b,
                    groq/openai/gpt-oss-120b,
                    openrouter/google/gemma-4-31b-it:free'   ← 후보 4개
```

폼은 넷, **판정은 하나**다. 그리고 판정 역할은 재시도도 1회뿐이다:
```python
soft_retries = 1 if role in JUDGE_ROLES else 2      # 판정은 한 번만 묻는다
hops = _MAX_HOPS if judged else len(candidates)     # = 2, 그러나 후보가 1개
```

→ **`matchup_prelim`(1차 잠정 카드)은 gemini 한 번 실패하면 끝난다.**
그 gemini 가 09-04~09-07 에 **429 quota 를 50회** 맞았다:
```
gemini kind=quota  50건
  "code": 429, "message": "You exceeded your current quota, …"
```

주석이 정확히 예언한 상황("하나만 두면 그 경기는 카드가 못 나간다")이
설정 한 줄 때문에 지금 성립하고 있다.

## 🔴🔴 LLM-6 [상] `groq` 헤더 파손은 **판정 후보 하나를 통째로 먹었다**

59차 LLM-1 의 후속이다. `free_form_model` 사슬은
```
① nvidia/nemotron  ② groq/qwen  ③ groq/gpt-oss  ④ openrouter/gemma:free
```
인데 ②③이 둘 다 groq 이었다. 09-04~09-06 에 그 둘은 **요청이 나가기도 전에**
죽었으므로, 폼 사슬은 사실상 `nemotron → gemma:free` 두 칸이었다.

그리고 ① nemotron 은 코드 주석이 직접 지목한 문제아다:
> Nemotron 은 JSON 대신 **영어 사고문**을 돌려주는 회차가 있다 —
> 비어 있지 않으니 `ok=True` 고, 호출부는 그것을 받아 파싱에 실패한다.

주전이 산문을 내고, 2·3번이 헤더 파손으로 죽고, 4번 하나가 받는 구조로
사흘을 돌았다.

## 🔴 LLM-7 [중] 소진 대체가 `xai` 로 가는데 그 경로도 원장에 안 남는다

```python
if _anthropic_gone() and s.xai_api_key:
    return [("xai", s.grok_model)]        # grok-4.3-latest
```
`_complete_free` 는 `p != "anthropic"` 인 후보를 무료 사슬로 처리한다 —
**xai(grok)도 그 길로 간다.** grok 은 유료 API 인데
`judge_route.is_free()` 는 `openrouter` 가 아니면 무조건 True 를 돌려준다:
```python
_SUFFIX_REQUIRED = {"openrouter"}
def is_free(provider, model):
    if provider in _SUFFIX_REQUIRED: return model.endswith(":free")
    return True                      # ← xai 도 "무료"로 분류된다
```
`note_paid_call` 도 `_paid_ok` 도 타지 않으므로 **grok 대체 판정은 캡도
계수도 없이 나간다.** (지금은 anthropic 이 살아 있어 발동하지 않는다.)

## ✅ TF-1 정상 확인 — 후행 쉼표 회수가 "문법만" 고친다

```python
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")
#  ⚠️ **내용을 고치지 않는다.** 문법만 회수한다 — 값·키를 우리가 주무르면
#     그건 파싱이 아니라 창작이다
```
P0 실사고(2026-09-07 KBO game=1721 판정 2회 실패 → 카드 미발송)의 수정이
최소 범위로 들어갔다. 원문·회수본 두 번만 시도하고, 잘린 JSON 은 회수하지
않는다("그때는 max_tokens 를 늘린다").

## ✅ TF-2 정상 확인 — 모르는 모델에는 `temperature` 를 안 보낸다

```python
_NO_SAMPLING = ("claude-sonnet-5", "claude-fable-5", "claude-opus-5")
def _sampling_allowed(model):
    """이 모델이 `temperature` 를 받는가. **모르면 안 보낸다.**"""
```
`claude-opus-5`(현 `matchup_model`)는 실측 전이지만 같은 세대라 안전한 쪽에
넣어 두었다 — "판정은 이제 단 한 번이라 400 이 나면 그 경기는 판정 없이
끝난다"는 이유까지 적혀 있다.

---

# 64차 — 판정 본체 완독 (`matchup.py` · `branch_resolve.py` · 게이트류)

읽은 것: `matchup.py`(899 전량) `branch_resolve.py`(619) `situation_gate.py`(97)
`credit_guard.py`(86) `game_trace.py`(104) `variable_parse.py`(103) — 1,908줄.

## 🔴🔴 BR-1 [상] "오늘의 사실은 항상 싣는다"고 적어 놓고, **첫 판정에는 안 싣는다**

`branch_resolve.attach` 의 주석:
> 🔴 **오늘의 사실은 분기점과 무관하게 항상 싣는다.**
> 분류 결과에 그것의 전달 여부를 맡기지 않는다 — 분류는 틀릴 수 있고,
> 이 블록은 싸다(수백 자).

그런데 그 블록보다 **위**에 조기 반환이 있다:
```python
    if not qs:
        jg["branch"] = {}
        return False              # ← 여기서 끝난다
    ...
    # 🔴 오늘의 사실은 분기점과 무관하게 항상 싣는다.
    today = await live_status(pool, jg, None)
```

`qs` 는 **직전 판정**(`jg["matchup"]`)의 `전개.분기점`·`변수`·`추가확인` 에서
나온다. 최초 판정에는 직전 판정이 없다 → `qs` 가 비어 → 조기 반환.

→ **1차 예비 판정(`🕐 잠정` 카드)은 라인업 공시 시각·IL 명단·결장 투수자원을
한 번도 못 본다.** 그 재료가 필요한 이유를 모듈 자신이 적어 두었다:
> 실측 2026-09-07 WSH@LAD: `research.absences` 에 다저스 **선발 자원 5명
> 이상**이 들어 있었다. Wrobleski 가 선발로 나오는 이유이자 불펜이 피로한
> 이유인데, 판정에는 "결장자 목록"으로만 갔지 분기점의 답으로는 가지 않았다.

운영 캐시 4경기는 전부 재판정이라 `오늘의사실` 이 4/4 있다 — 첫 판정 표본이
지금 캐시에 없어 실측으로는 못 봤다. 코드 경로는 위와 같다.

## 🔴 MU-1 [중] 확신도 강등이 **한 곳에만** 반영된다

```python
# situation_gate.apply
jg["judge_confidence"] = after          # 영문 high/medium/low
jg["situation_demoted"] = True
```
`jg["matchup"]["확신도"]`(한국어 상/중/하)는 **그대로 남는다.**

- `_bet_line`·`rec_label`·`board_stars` → `judge_confidence`(강등 반영 ✅)
- `compose_lineup_only_card` → `m.get('확신도')`(강등 미반영 ❌)
- `verdict_block` → `_CONF_KR[judge_confidence]`(반영 ✅)
- `glass_report` §③ → `m.get('확신도')`(미반영 ❌)

**라인업 변경 카드와 투명 리포트는 강등 전 값을 보여준다.**
61차 CARD-2 와 같은 뿌리다 — 확신도가 두 필드에 두 언어로 산다.

## 🔴 MU-2 [중] `_real_model` 이 **프로세스 전역 변수**에 기댄다

```python
from app.engine.team_form import LAST_USAGE      # 모듈 전역 dict
if (LAST_USAGE or {}).get("role") in JUDGE_ROLES and LAST_USAGE.get("model"):
    return str(LAST_USAGE["model"])
```
독스트링이 위험을 인정한다 — "다른 역할(폼)이 그 사이에 끼면 그 모델이 잡힌다".
role 확인으로 막았지만, `judge_matchup` 은 슬레이트를 **순차**로 돈다.
경기 A 의 판정이 실패해 `LAST_USAGE` 를 안 건드리고 경기 B 가 성공하면
A 는 이미 반환했으니 문제가 없다 — 지금은 안전하다.

다만 **동시성이 들어오는 순간 조용히 틀린다.** 판정을 병렬로 돌리는 변경이
오면 경기 A 가 경기 B 의 모델명을 기록한다. 원장의 `model` 은 "모델별 성적을
가르는" 유일한 열쇠라고 주석이 말한다.

## 🔴 MU-3 [하] 자료 번호가 **13을 건너뛴다** — 이유가 프롬프트에 없다

프롬프트 자료 번호: 1·2·3·4·5·6·(7·8 폐지)·9·10·11·12·**14**.
13 이 없다. 찾아보니 폐기된 것이고, **잘 폐기됐다**:

```
evidence/OPEN.md:21
 자료13 전개 계산기는 h2h·총득점 두 관문 모두 미달로 폐기
 (docs/BACKTEST_TEMPO_2026-09-07.md). 실패 원인은 축이 아니라
 **표본 1~3짜리 비율 셋을 곱한 것** — 예측 sd 5.25 vs 실제 3.82,
 최대 예측 40.4점. 계산기는 tools/backtest_tempo.py 에 보존, app/ 미접합
```

7·8 은 프롬프트에 "폐지" 라고 자리를 남겼는데 13 은 자리 자체가 없다.
`glass_report.RETIRED` 도 7·8 만 안다. **번호가 뛴 이유를 프롬프트만 봐서는
알 수 없다** — 다음 세션이 "13이 빠졌다"를 결함으로 읽을 자리다.

## ✅ BR-2 정상 — 자료14 는 이 저장소에서 가장 잘 설계된 모듈이다

- **곱하지 않는다**: "세 갈래를 곱하지 않는다. 자료13 이 무너진 자리가
  그것이다 (표본 1~3 짜리 비율의 곱 → 예측 sd 5.25 vs 실제 3.82)."
- **표본 하한이 계약**: `branch_min_n` 미만이면 `사유` 를 적고 답을 안 낸다.
- **사본 금지 준수**: 주체 판별을 다시 쓰지 않고 `variable_ledger.subject_of`
  를 **부른다** — "두 곳에 적으면 하나가 바뀔 때 다른 하나가 안 따라간다".
- **분류 확장을 실데이터로 측정**: `불펜|구원|필승조|연전` 을 추가하며
  반대 위험(뉴스형을 빼앗음)을 실변수 638건으로 쟀다.
- **중복 억제에 예외를 뒀다**: 같은 답이어도 **유형이 다르면 남긴다** —
  "기록형과 실시간형은 다른 질문에 답한다(대리값 vs 오늘의 사실)".

## ✅ MU-4 정상 — 최종 판정 락이 실패 시 **반납**된다

```python
if parsed is None:
    if final: await release_final(redis, jg, date)
```
P0 실사고(npb game=3603: 락은 잡혔는데 판정이 없어 카드가 영영 0장)의
수정이 두 겹으로 들어갔다 — 실패 시 반납, 그리고 `final_done` 이지만
`has_verdict` 가 아니면 **예비(무료)로 내려가 한 장은 낸다**.

## ✅ MU-5 정상 — 전개 정합 검사가 값을 **고치지 않고 지운다**

```python
if h == a and sport not in _DRAW_LEAGUES:
    bad.append(f"{sport.upper()} 는 무승부로 끝나지 않는데 예상점수가 동점이다")
# ⚠️ **고쳐 쓰지 않고 지운다.** 점수를 우리가 지어내면 그건 판정이 아니라 우리 추정이다.
```
실측(2026-09-07 NYY@SD: 승자 SD 인데 예상점수 3-3)에서 나온 가드이고,
프롬프트로 막으려던 것을 코드로 옮긴 판단이 옳다.

## ✅ VP-1 정상 — 읽는 쪽만 관대하게 넓혔다

```python
_SIDE = {"홈":"home","원정":"away","home":"home","away":"away","HOME":"home","AWAY":"away"}
# ⚠️ **쓰는 쪽은 한국어로 못박고 읽는 쪽만 관대하게 한다.**
#    형식을 넓히는 것이 아니라, 형식을 어겨도 값을 잃지 않게 하는 것이다.
```
grok 대체 모델이 `home` 으로 쓰는 순간 변수 정량화가 통째로 무력화되던 것을
잡았다. 형식 위반 감시(`unverifiable` 집계)는 그대로 두면서 값만 살렸다.

## ✅ GT-1 정상 — 원장이 로그보다 많이 알지 않는다

```
msg = "[materials] game=%s …" % (...)
logger.info(msg)
await note(pool, ..., summary=msg)
```
"포맷을 두 번 쓰지 않는다. 두 번 쓰면 언젠가 갈린다." — 사본 금지 원칙이
계측 층에까지 적용된 드문 사례다. 알 수 없는 `stage` 는 **거절하고 남긴다**.

---

# 65차 — "침묵이 가장 나쁜 출력이다"를 고친 코드가 **한 번도 실행된 적이 없다**

전 저장소 공개 함수 참조 전수 조사(동명 함수 제외, tests 제외) → 참조 0 함수 34개.

## 🔴🔴🔴 PGP-2 [최상] 판정 불가 카드 — 도입 후 6일간 **발송 0건**, 호출부 0개

`pregame_push.compose_unavailable_card` 의 존재 이유:
> 🔴 실사고 2026-09-02: Anthropic 크레딧이 끊겨 판정이 0건이 됐는데 카드도
> 경보도 없었다. 사용자는 "봇이 죽었나"와 "오늘 픽이 없나"를 구분할 수
> 없었다. **침묵이 가장 나쁜 출력이다.**

도입 커밋: `f5dc765 2026-09-02  가동만 고친다 — 안 돌던 것을 돌게, 죽으면 알리게.`

**그 카드는 `run_pregame_push` 안에서만 불린다. 그리고 `run_pregame_push` 를
부르는 곳이 없다.**

```
run_pregame_push        참조 0
  └ _should_say_unavailable   참조 0
      └ send_unavailable      참조 0
          └ compose_unavailable_card  참조 0
          └ _unavailable_reason       참조 0
```

운영 확인 — 중복 가드 키가 **한 번도 세워진 적이 없다**:
```
pregame:unavailable:*  →  0개
pregame_card_sig:*     → 11개   (정상 카드는 나갔다)
```

## 왜 — 스케줄러가 같은 일을 **따로 구현했다**

`app/scheduler.py` 는 `send_game_prediction` 을 **5곳에서 직접** 부른다:
```
scheduler.py:455  sent = await send_game_prediction(redis, game, date, now=now)
scheduler.py:477  …
scheduler.py:855  …
scheduler.py:880  …
scheduler.py:945  …   (T-30 보장선 경로)
scheduler.py:964  …
```
취소 처리도 자기가 한다:
```
scheduler.py:724  cancelled = await crawler_feed.mark_cancelled_games(pool, rows, snap)
scheduler.py:726  await void_analysis_games(redis, sport, date, cancelled)
```

즉 `run_pregame_push` 는 **스케줄러 루프의 죽은 사본**이다. 두 구현이 갈렸고,
살아 있는 쪽에 "판정 불가 카드" 분기가 없다.

이 저장소가 다섯 번 반복한 그 패턴이다 —
**새 기능을 만들고, 옛 호출부를 회수하지 않고, 새 것을 아무도 안 부른다.**
다만 이번에는 방향이 반대다: **새로 만든 쪽이 죽었고 옛 경로가 살아 있다.**

## 🔴🔴 DEAD-1 [상] 참조 0 공개 함수 34개 전수

| 파일 | 함수 | 무엇이었나 |
|---|---|---|
| `pregame_push.py` | **`run_pregame_push`** · `card_signature` | 발송 오케스트레이터(죽은 사본) |
| `glass_report.py` | `load_final_jg` · `load_sources` | 투명 리포트 DB 로더 (ORP-1) |
| `scoring.py` | `record_cap_hit` · `cap_alert_count` | 승률 상한 히트 계측 |
| `variable_ledger.py` | `situation_report` · `situation_lines` · `team_report` | 상황 변수 prior 승격 (VL-4) |
| `cell_grade.py` | `format_ledger` · `format_scoring_ledger` | 칸 적중률 표 |
| `comparator.py` | `thin_card_caps_confidence` | 구버전 확신도 상한 |
| `interpreter.py` | `apply_weight_rule` | ④칸 "양쪽 무의미" 결정적 규칙 |
| `pitcher_matchup.py` | `format_pitcher` | 카드·판정용 한 줄 |
| `pipeline.py` | `near_miss_picks` · `render_games_easy` | 아깝게 탈락한 픽 · 다경기 렌더 |
| `alerts.py` | `dispatch_report` · `reset_shared` | 발송 리포트 |
| `models/calibrate.py` | `build_training_set` · `load_learned` | λ 캘리브레이션 |
| `models/features.py` | `build_dataset` | λ 학습셋 |
| `models/lambda_model.py` | `evaluate_totals` | 토탈 평가 |
| `research/deep.py` | `fill_gaps` | 결측 보충 |
| `research/perplexity.py` | `fetch_expert_picks` | 전문가 픽 수집 |
| `research/crosscheck_sources.py` | `missing_fields` | — |
| `collectors/news_rss.py` | `fetch_team_situation` | 팀 상황 수집 |
| `collectors/lineup_history.py` | `changes_since` | — |
| `collectors/soccer_stats.py` | `load_elo` | — |
| `registry.py` | `sports_of` · `uses_source` | — |
| `api_guard.py` | `set_redis` · `set_network_redis` | — |
| `notify.py` | `reset_notified` | — |
| `leagues.py` | `league_labels` | — |

그중 **의미가 큰 셋**:

**① `interpreter.apply_weight_rule`** — "양쪽이 모두 경쟁권 밖이면 순위 차이가
동기 차이를 뜻하지 않는다"는 결정적 규칙. 주석이 명시한다:
> ⚠️ 이것은 **결정적 규칙**이지 해석이 아니다. LLM 이 문턱을 판단하게 두면
> 측정되지 않은 튜닝이 된다.
LLM 에게서 되찾아 온 규칙인데, 되찾아 온 자리에서 아무도 안 부른다.

**② `research/perplexity.fetch_expert_picks`** — 전문가 픽 수집기.
`markets._axis_expert`·`expert_support_count`·`EXPERT_STRONG_N` 이 전부
전문가 픽을 전제로 하는데, 그것을 **가져오는** 함수가 죽어 있다.
(MLB 보드에 `expert: true` 가 뜨는 걸 보면 다른 경로가 있다 — 확인 필요)

**③ `scoring.record_cap_hit` · `cap_alert_count`** — 승률 상한(0.68/0.72)에
몇 번 걸렸는지 세는 장치. CLAUDE.md 는 상한 초과를 "모델이 틀렸다는 신호"라고
쓴다. **그 신호를 세는 계수기가 아무 데도 연결돼 있지 않다.**
(38차에서 이미 적었고, 여기서 전수 조사로 재확인됐다)

## 🔴 LM-1 [중] `linemove` 는 **배당 움직임으로 확신도를 바꾼다** — 야구에는 안 걸린다

```python
jg["judge_confidence"] = after     # 배당이 모델과 반대로 움직이면 한 단계 ↓
```
확신도 `low` → `judge_pass` → **거부권탈락**. 즉 배당 움직임이 추천 자격을
박탈할 수 있다. 야구는 `_apply_line_moves` 가 건너뛰므로 지금은 축구 전용이고,
축구는 꺼져 있다 — 현재 무해하다.

다만 CLAUDE.md 는 "배당은 판정·폼·서술의 입력에 절대 넣지 않는다"이고,
확신도는 판정의 출력이자 게이트의 입력이다. **야구에 이 경로를 켜는 변경이
오면 그 순간 동결 위반이 된다.**

## ✅ DRV-1 정상 — 변별력 없는 지표를 **측정하고 안 쓰기로 했다**

```python
# ⚠️ `bullpen_overused`는 **일부러 채우지 않는다.** (2026-08-27 측정)
#   한화 86(평균의 1.64배) · LG 58(1.11) · NC 54(1.03) · 키움 53(1.01)
#   — 10팀 중 4팀이 평균 초과라 매 경기 발동하고, 진짜 이상치와 3% 초과가
#     같은 통에 들어간다.
#   함수 자체는 남겨둔다 — 채점 회로가 복구되면 문턱을 실측해 다시 켠다.
```
"만들었으니 쓴다"를 하지 않은 사례다. 남겨 둔 이유와 되살릴 조건까지 적혀 있다.

## ✅ OA-1 정상 — 상대 보정이 **얇은 표본을 뺀다**

```python
if got < len(games):
    out["주의"] = f"{len(games)}경기 중 {got}경기만 보정(상대 표본 부족)"
# ⚠️ 표본이 얇은 상대는 **뺀다**. 얇은 숫자로 얇은 숫자를 보정하면 오늘
#    자료13 이 무너진 자리로 돌아간다(표본 1~3짜리 비율의 곱).
```
몇 경기를 실제로 보정했는지 판정에 함께 밝힌다 — 자료13 의 교훈이
새 모듈의 계약으로 들어간 사례다.

---

# 66차 — `scheduler.py` 완독 (2,055줄)

## 🔴🔴🔴 SCH-1 [최상] PGP-2 의 정확한 경위 — **5일 전에 죽은 함수에 수정을 넣었다**

운영 실행 기록 `scheduler:job_last_run` (26필드) 에 **유령 잡 둘**이 남아 있다:
```
pregame_push_1745 = {"at": "2026-08-28T08:57:45Z", "ok": true,
                     "note": "{'due': 6, 'sent': 6, 'skipped': 0, 'failed': 0}"}
asia_lineup_1700  = {"at": "2026-08-28T08:40:00Z", "ok": true}
```
둘 다 **2026-08-28 이후 한 번도 안 돌았다.**

커밋 이력:
```
e066539  2026-08-28  KBO·NPB 예측을 매일 17:45에 한꺼번에 보내…   ← run_pregame_push 배선
a76f809  2026-08-28  KBO·NPB를 경기마다 보내고…                  ← 같은 날 배선 제거
f5dc765  2026-09-02  가동만 고친다 — 안 돌던 것을 돌게, 죽으면 알리게.  ← 판정 불가 카드 추가
```

**`run_pregame_push` 는 2026-08-28 에 죽었고, 2026-09-02 의 "죽으면 알리게"
수정은 그 죽은 함수 안에 들어갔다.** 그래서 6일이 지나도록 판정 불가 카드가
0장이고, `pregame:unavailable:*` 키가 하나도 없다.

이 저장소의 지배적 실패 패턴에 **여섯 번째 사례**가 추가된다. 다만 형태가
가장 나쁜 쪽이다 — 앞의 다섯은 "새 것을 만들고 옛 것을 회수 안 함"인데,
이건 **이미 죽은 곳에 새 것을 넣었다.**

## 🔴🔴 SCH-2 [상] `lineup_poll_30m` 이 5분·2분 잡과 **같은 일을 겹쳐서** 돈다

```python
async def lineup_poll_job() -> None:
    await mlb_pregame_poll()
    await crawler_lineup_poll()          # 기본값 ("npb", "kbo")
```
등록된 잡 넷이 전부 살아 있다:
```
lineup_poll_30m  (30분)  → mlb_pregame_poll + crawler_lineup_poll(npb,kbo)
mlb_pregame_5m   (5분)   → mlb_pregame_poll
asia_pregame_5m  (5분)   → crawler_lineup_poll(kbo)
npb_pregame_2m   (2분)   → crawler_lineup_poll(npb)
```
운영 최근 실행(2026-09-08 UTC):
```
lineup_poll_30m 01:04 · asia_pregame_5m 01:08 · mlb_pregame_5m 01:09 · npb_pregame_2m 01:12
```

도입 순서를 보면 회수를 잊은 것이다:
```
lineup_poll_30m  469cbf0  2026-08-25
asia_pregame_5m  a76f809  2026-08-28   ← 이때 30m 을 뺐어야 한다
mlb_pregame_5m   9dcdd56  2026-08-29
```

`max_instances=1` 은 **같은 job id** 안에서만 겹침을 막는다. 서로 다른 잡이므로
30분마다 KBO·NPB·MLB 폴링이 **두 벌 동시에** 돌 수 있다. 그 안에는
`refresh_mlb_lineup`(statsapi HTTP), 크롤러 스냅샷 읽기, `rejudge_after_lineup`
(LLM 판정 호출), `send_game_prediction`(텔레그램) 이 전부 들어 있다.

## 🔴🔴 SCH-3 [상] "1회성"이라고 적힌 코드가 **재배포마다 다시 돈다**

`main()` 이 기동할 때마다 백그라운드로 띄우는 것:
```python
asyncio.create_task(startup_backfill_job())
asyncio.create_task(_catchup())
asyncio.create_task(soccer_lineup_probe_job())
```

### ① `startup_backfill_job` — 주석이 "다음 배포에서 지워도 된다"
```python
# ⚠️ 아래는 **1회성 코드다.** … 백필 완료를 로그로 확인한 뒤에는 다음
#    배포에서 이 함수와 main()의 create_task 호출을 통째로 지워도 된다.
BACKFILL_SINCE = "2026-08-29"
```
안에 든 것들도 전부 "확인 후 지운다"라고 적혀 있고 아직 있다:
- `[ledger-snapshot]` — **매 기동마다 원장 20행을 로그로 덤프**
  ("운영 DB를 직접 조회할 수 없어… 확인이 끝나면 다음 배포에서 이 블록을 지운다")
- `[appearances]` — 종목별 등판 행수 덤프
- `_startup_forensics` — 차단 상태·배당 최신·오염 타순 진단
- `backfill_from_redis(pool, redis, "2026-08-29")` — Redis 전 슬레이트 스캔
- `grade_pending(pool)` — **채점을 다시 돌린다** (MB-1 의 순서 결함이 여기서도 탄다)

### ② `soccer_lineup_probe_job` — **30시간짜리 외부 폴링 루프**
```python
SOCCER_PROBE_ENABLED = True                 # env 로 못 끈다
out = await probe_run(hours=30, lead_start=150, interval=600, ...)
```
주석: "**1회성 코드다.** 축구 라인업 리드타임·레이트리밋을 하룻밤 재기 위한
프로브이고, 관측이 끝나 로그를 회수한 뒤에는 다음 배포에서 … 통째로 지운다."

- CLAUDE.md 는 "**축구는 요청 시에만**"이라고 못박는다.
- `soccer_trial_enabled=False`(운영 실측)로 축구 판정은 꺼져 있다.
- 그런데 이 프로브는 스위치를 보지 않고 **매 기동마다 30시간·10분 간격으로
  외부 사이트를 친다.**

배포가 잦은 이 저장소에서(하루 여러 번) 매번 새 30시간 루프가 시작된다.

## 🔴 SCH-4 [중] 문서 문자열이 실제 소스와 어긋난다

```python
async def _free_odds_snapshot() -> None:
    """무료 3원 배당 수집. …
    KBO·NPB  배트맨 스냅샷(Go 크롤러 적재)을 DB 로 옮긴다"""
```
실제로는 `collect_asia` 가 **oddsportal** 을 쓴다. 배트맨은 못 썼다고
`odds_free.collect_asia` 가 직접 적어 놓았다:
> 🔴 배트맨은 못 썼다. `requestClient.js` 가 광고하는 엔드포인트 10개가 전부
> "페이지 오류 안내 — 삭제 또는 이름이 변경" 을 돌려준다(6회 시도 후 중단).

스케줄러 쪽 문장만 옛 계획에 남아 있다.

## 🔴 SCH-5 [중] `finals_job` 이 **어제 하루만** 본다 — 야구는 오늘 새벽 종료분을 놓친다

```python
for sport in ("mlb", "soccer", "kbo", "npb"):
    done[sport] = await ingest_finals(pool, yesterday_kst(), sport)
    if sport == "soccer":
        done["soccer_today"] = await ingest_finals(pool, today_kst(), sport)
```
축구만 오늘 날짜를 한 번 더 훑는다. 사유도 적혀 있다 —
"유럽 킥오프는 KST 새벽이라 오늘 01:30~05:00에 끝난 경기가 어제에 잡히지 않는다".

**MLB 도 같은 사정이다.** 미국 동부 저녁 경기는 KST 로 다음 날 오전에 끝나고,
잡은 13:00 KST 에 돈다. `yesterday_kst()` 로 조회하면 그 슬레이트가 어느 쪽에
잡히는지는 `ingest_finals` 의 날짜 규약에 달렸다 — **여기서는 확인하지 못했다.**
운영 실행 기록이 그 자리를 비워 놓았다:
```
ingest_finals_13h note = "{'mlb': None, 'soccer': None, 'soccer_today': None,
                          'kbo': None, 'npb': None}"
```
**다섯 종목 전부 `None`** 이다. `ingest_finals` 의 반환을 확인해야 이것이
"0건"인지 "반환값 없음"인지 갈린다 — 아직 안 읽었다.

## ✅ SCH-6 정상 — 시각을 크론에 박던 결함을 세 번 다 고쳤다

```
asia_poll_window(pool, now)   ← KBO·NPB, hour="17,18" 제거
mlb_poll_window(pool, now)    ← MLB, hour="5-11" 제거 (2026-09-07)
```
MLB 쪽 주석에 실측이 붙어 있다:
> 실측(최근 30일 337경기): 01시 7 · 02시 40 · 03시 25 · 04시 9 = **81경기(24%)가
> 창 밖**이라 발송 창이 열려도(T-180) 폴링이 자고 있어 카드가 나가지 못했다.
> `CLAUDE.md` 발송 규율의 "첫 카드 보장선 T-30"이 그 24%에는 적용된 적이 없다.

그리고 **새 상수를 만들지 않았다** — `SEND_OPEN_MIN[sport] + 20분` 으로 창을
잡는다. 규율을 두 번 적지 않은 사례다.

## ✅ SCH-7 정상 — 재기동이 삼킨 cron 을 따라잡는다

```python
async def _catchup_missed_crons(redis):
    """🔴 APScheduler 는 in-memory jobstore 라 재기동하면 잡을 새로 단다.
       cron 잡의 오늘 발화 시각이 이미 지났으면 **그 하루는 통째로 건너뛴다**"""
```
실사고(2026-09-03, 14:00 `prefetch_asia` 가 14:03 배포로 사라짐)에서 나온
장치이고, 창은 `MISFIRE_GRACE_SEC` 하나를 재사용한다("여기 새 숫자를 적지
않는다 — 사본 금지"). 이미 돈 잡은 **실행 기록**으로 건너뛴다.

## ✅ SCH-8 정상 — `RUN_AT_BOOT` 이 배포 직후의 눈먼 구간을 막는다

```python
RUN_AT_BOOT = ("odds_snapshot_30m",)
#  🔴 실측 2026-09-04: 15:21 기동 → 첫 실행 15:51. 그 사이 워치독이
#     `W-ODDS-STALE oddsportal` 을 66·71·76분으로 세 번 울렸다.
#     oddsportal 은 멀쩡했다 — 소스가 아니라 **우리 배포 리듬**이 원인이다.
```
오탐의 원인을 소스가 아니라 자기 배포 리듬으로 정확히 지목한 사례다.

## ⛔ SCH-5 **정정** — `None` 은 실패가 아니라 **반환값이 없는 것**이다

`collectors/finals.py` 를 읽고 확인했다:
```python
async def ingest_finals(pool, date: str, sport: str) -> None:
    """그 종목의 결과 적재 — games.status='final' + 점수."""
```
반환 타입이 `None` 이다. `done[sport] = await ingest_finals(...)` 는 항상 `None`
을 담는다. 운영 기록의 `{'mlb': None, …}` 는 정상이다. 내 추론이 성급했다.

### 다만 그 자리에 **다른 결함**이 있다

```python
logger.info("[scheduler] 종료 점수 적재: %s", sorted(done))
```
`sorted(dict)` 는 **키 목록**이다. 그래서 이 줄은 매번 똑같이 찍힌다:
```
종료 점수 적재: ['kbo', 'mlb', 'npb', 'soccer', 'soccer_today']
```
0경기를 적재한 날과 30경기를 적재한 날의 로그가 **글자 하나 다르지 않다.**
채점(`grade_pending`)은 바로 아래에서 건수를 찍는데, 그 재료를 만드는
적재 단계는 건수를 남기지 않는다.

바로 옆 `reconcile_stale_games` 는 정확히 그것을 센다:
```python
after = await pool.fetchval(count_sql, sport, r["d"])
fixed[sport] = fixed.get(sport, 0) + max(0, (after or 0) - (before or 0))
```
**구제 경로는 계측하고 주 경로는 계측하지 않는다.**

### MLB 새벽 종료분은 안전망이 받는다

`finals_job` 이 `yesterday_kst()` 하나만 보는 것은 맞지만, 같은 잡이 그보다
**먼저** `reconcile_stale_games` 를 돌린다. 그것은 날짜를 계산하지 않고
"시작 후 6시간이 지났는데 final 이 아닌 경기"를 DB 에서 역으로 찾는다.
종목별 날짜 기준(축구 KST · 나머지 UTC)도 주석에 실측 근거와 함께 갈라 놓았다.
→ **MLB 누락 우려는 근거 없음.** 축구만 `today_kst()` 를 더 보는 것은
안전망을 한 겹 더 둔 것이지 다른 종목이 빠진 것이 아니다.

---

# 67차 — CR-1 **운영 재현 성공** · 수집기 통독

읽은 것: `collectors/mlb.py`(364) `lineups.py`(358) `crawler_feed.py`(378)
`kbo_usage.py`(454) `absences.py`(176) `mlb_team_pitching.py`(112)
`finals.py`(92) — 1,934줄.

## 🔴🔴🔴 CR-1 [최상] **재현했다** — 자료9 "불펜 최근 폼"에 **시즌 팀 투수 ERA** 가 들어간다

호출 순서(파이프라인 실제 코드):
```
pipeline.py:2749  #   ⚠️ 시즌 부착(위 `mlb_team_pitching` 등)보다 **뒤**여야 지워진다.
pipeline.py:2751      from app.engine.bullpen_recent import attach as _bp_recent
pipeline.py:2753      await _bp_recent(pool, jg)          ← ① 먼저 돈다
pipeline.py:2772      from app.collectors.mlb_team_pitching import attach as _pen
pipeline.py:2774      await _pen(jg, redis=redis)         ← ② 21줄 뒤에 돈다
```
주석은 "시즌 부착이 **위**에 있다"고 말하는데, 실제 코드에서 시즌 부착은
**아래**에 있다. 주석이 가리키는 순서와 코드의 순서가 반대다.

### 운영 컨테이너에서 그대로 실행해 확인했다

```
경기: Toronto Blue Jays @ Athletics
① bullpen_recent 후:
   home = {"최근3경기": {"실점":3,"이닝":12.3,"등판":9,"경기":3,"경기당실점":1.0},
           "가용성": {"종합":"피로", "주력":[…]}}          ← era 없음(pop 됨)
② mlb_team_pitching 반환: 2
   후: home = {"era": 5.40, "whip": 1.49, "k9": 8.63, "bb9": 4.03}
       away = {"era": 3.92, "whip": 1.30, "k9": 8.77, "bb9": 3.71}
```

**`bullpen_recent` 가 지운 시즌값을 `mlb_team_pitching` 이 21줄 뒤에서 되채운다.**

### 그 값이 프롬프트 자료9 로 그대로 간다

```python
# matchup.bullpen_payload
blk = r.get(f"{side}_bullpen") or {}
if blk: out[side] = blk           # 통째로 넘긴다 — 키를 고르지 않는다
```
```
prompts.py:83   9. 양팀 불펜 — **최근 폼만** (없으면 빈 객체): {{BULLPEN_JSON}}
```
라벨은 "최근 폼만"이고 내용에는 **시즌 누적 ERA 5.40** 이 함께 들어간다.

### 두 모듈이 서로를 모른다

`mlb_team_pitching.py` 머리말이 자기 값의 성격을 정직하게 적어 두었다:
> ⚠️ **KBO·NPB 와 같은 기준을 쓴다.** 두 리그 모두 `team_era`(**팀 투수 방어율**)를
> 자료9 에 넣는다 — 구원 전용 ERA 가 아니다. ⚠️ 그래서 라벨도
> "팀 투수 ERA"로 정직하게 적는다.

`bullpen_recent` 는 그것을 지우려고 만들어졌다(C1, 2026-09-04):
> 🔴 대원칙: 시즌 누적은 판정 입력이 아니다. 시즌 ERA 를 지우고 최근 3경기
> 실점 + 최근 3일 가용성을 넣는다.

**두 커밋이 하루 차이다(B-1 09-03 → C1 09-04). 뒤 커밋이 앞 커밋의 호출을
회수하지 않았고, 순서까지 반대로 놓였다.**

그리고 `attach` 는 `setdefault` 라 "이미 다른 소스가 채웠으면 덮지 않는다" —
즉 **비어 있을 때만** 채운다. `bullpen_recent` 가 방금 비워 놓았으므로
**항상** 채워진다. 방어 장치가 정확히 반대로 작동한다.

### 계약 테스트가 이것을 못 잡는 이유(TST-1 재확인)

```python
seg = src[src.index("async def _run_baseball_matchups"):]
assert seg.index("mlb_team_pitching") < seg.index("bullpen_recent")
```
`mlb_team_pitching` 의 **첫 등장**이 2749줄 **주석**이다. 문자열 인덱스로
비교하니 주석이 조건을 만족시킨다. 초록이 뜨고 실제 순서는 반대다.

## 🔴 KU-1 [중] `key_relievers` 의 "관측 창 전체"가 실은 **3경기**다

```python
# [핵심 불펜 자체 산출] 관측 창 전체에서 **구원 등판이 잦은 순**.
for g in games:                      # 최근 3경기가 아니라 **관측 창 전체**
    ...
```
그런데 수집 루프가 팀당 3경기에서 멈춘다:
```python
if len(by_team.setdefault(team, [])) < RECENT_GAMES:   # RECENT_GAMES = 3
    by_team[team].append({...})
```
`games` 는 **최대 3개**다. `key_reliever_top = 4` 이므로 3경기에서 등판 횟수
상위 4명을 고른다 — 1회 등판한 투수가 "핵심 불펜"이 될 수 있다.

그 라벨이 그냥 표시로 끝나지 않는다:
```
kbo_usage.key_relievers
  → lineup_diff.bullpen_absences("핵심 불펜 %s 이(가) 1군 엔트리에 없음")
  → merge_absences_from_diff  → research["absences"]
  → performance.absences      → adj_key_reliever_out (%p 차감)
```
1회 등판으로 뽑힌 이름이 결장하면 **핵심 불펜 결장**으로 확률이 깎인다.

주석 자체는 상한이 실측이 아님을 밝혀 놓았다("운용값이지 실측이 아니다.
채점이 쌓이면 몇 명이 적당한지 재서 교체한다"). 문제는 **창의 크기**이고,
그건 주석이 말하는 것과 다르다.

## 🔴 LU-1 [중] MLB 라인업 역행에 **가드가 없다** (MON-4 위치 확정)

```python
# collectors/lineups.py  refresh_mlb_lineup
await pool.execute(
    "UPDATE games SET lineup_status = $2, ... WHERE id = $1",
    game["id"], status, ...)          # ← confirmed → predicted 를 그냥 쓴다
```
KBO·NPB 경로에는 있다:
```python
# scheduler.py  crawler_lineup_poll
if r["lineup_status"] == "confirmed" and status != "confirmed":
    await note_lineup_regress(redis, sport, date)      # 역행 계수
```
그래서 `monitor:mlb:*` 에 `regress` 필드가 없고, DB 에 기록된 13건의 역행이
전부 MLB 인데 계수기는 0 이다.

## ✅ ABS-1 정상 — 결장을 **id 로** 대조한다

```python
⚠️ 선수 대조는 이름이 아니라 **MLBAM id**로 한다. Statcast 의 `player_name` 은
   투수 이름이라 타자에 쓸 수 없고, statsapi 도 같은 id 체계를 쓴다.
```
그리고 근거를 라벨로 남긴다 — `라인업 확정` vs `IL 명단`, 사이드별로 갈라서.
"근거가 약하다는 뜻이고, 그대로 표기한다."

## ✅ KU-2 정상 — 경기값과 시즌값을 **실측으로** 갈랐다

```
⚠️ 경기값과 시즌값이 한 행에 섞여 있다. 실측으로 갈랐다(2026-08-27):
   **경기값** inn·pa·ab·hit·bb·kk·hr·er·r  (선수 pa 합 = 팀 pa 합으로 확인: 47/47, 50/50)
   **시즌값** bf·gameCount·era·w·l·seasonWin·seasonLose
   bf를 경기값으로 오인하면 상대 타자 수가 4배로 부풀려진다.
```
검증 방법(선수 합 = 팀 합)까지 적어 두었다.

## ✅ CF-1 정상 — 크롤러가 **Redis 에만** 쓴다

> ⚠️ 크롤러는 **Redis에만 쓴다.** Postgres를 직접 건드리지 않으므로, 검증을
> 통과한 값만 파이썬이 DB에 반영한다. 크롤러가 DB를 쓰면 미검증 값이 λ로 흘러간다.

`mark_cancelled_games` 가 그 경계를 지키며 취소만 반영한다.
`notable_rows` 와 `notable_changes` 를 나눈 이유도 정확하다 —
"둘을 zip 하면 다른 경기의 변화가 엉뚱한 경기에 붙는다."

---

# 68차 — `sanitize_research` 는 **화이트리스트 재조립**이다

읽은 것: `research/deep.py`(621) `research/validate.py`(556) — 1,177줄.

## 실측 — 운영 research 40키 중 **19키만 통과**한다

운영 캐시의 실제 경기(`game=4099`)에 `sanitize_research` 를 그대로 돌렸다:

```
원본키 40 → 통과 19  (탈락 21)

탈락: home_usage, away_usage,            ← 자료1 (3경기 박스스코어)
      home_lineup, away_lineup,          ← 자료3 (오늘 확정 라인업)
      home_starter_recent, away_starter_recent,
      home_starter_relief, away_starter_relief,   ← 자료4 (선발 최근 등판)
      today_nine,                        ← 오늘 9명
      home_lineup_changes, away_lineup_changes,
      home_lineup_headline, away_lineup_headline, ← 자료6 (라인업 의도)
      lineup_record, lineup_matchup,
      home_news, away_news,              ← 자료2 원천
      home_standing, away_standing, starter_status, _prov
```

**판정 재료 자료1·2·3·4·6 이 전부 탈락한다.** 이 함수는 딥서치(퍼플렉시티)
응답을 정제하려고 만들어졌고, 그 시절 스키마에 있던 키만 화이트리스트에 있다.
2026-09-02 이후 대원칙 개정으로 들어온 수집기 산출물은 목록에 없다.

CLAUDE.md 가 정확히 이 위험을 경고해 두었다:
> **새 리서치 필드를 추가할 때 `validate.py` 정책을 함께 정의한다** —
> 문장 필터 대상인지 전량 폐기 대상인지.

**그 규칙이 지켜지지 않았다.** 새 필드들은 정책이 정의되지 않은 채 추가됐고,
정책이 없으면 **전량 폐기**가 기본값이다.

## 🔴🔴 SAN-1 [상] 파이프라인이 그 결과를 **원본에 덮어쓴다** (한 곳)

```python
pipeline.py:2011   _r, _ = sanitize_research(_jg.get("research") or {}, sport)
pipeline.py:2012   merge_source_data(_r, _jg, sport, statcast_data)
pipeline.py:2018   _blocked = strip_unusable(_r)
pipeline.py:2032   _jg["research"] = _r          ← **파괴적 대입**
```

여기는 **결과적으로 무사하다** — 바로 아래 `merge_source_data` 가
`{side}_usage`·`{side}_lineup`·`{side}_standing`·`{side}_news` 를 다시 채우고,
`{side}_starter_recent`·`today_nine` 은 그 뒤 단계(2081·2109)가 다시 만든다.

**우연히 무사한 것이지 설계로 막은 것이 아니다.** 순서가 한 칸만 바뀌거나
새 필드가 하나 늘면 그날 조용히 사라진다.

## 🔴🔴🔴 SAN-2 [최상] 봇 버튼 경로는 **복구가 없다** — 재료를 지우고 그대로 저장한다

```python
async def ensure_game_fresh(sport, date, game_id):
    """경기 버튼·팀 질문용 — 해당 경기만 신선도 게이트 적용 후 …"""
    ...
    data, status = await get_game_research(redis, jg, sport)   # 퍼플렉시티 정제본
    if status != "refreshed" or data is None: return analysis, False
    jg["research"] = data                    # ← 40키 → 19키. 자료1·3·4·6 소멸
    _prepare_games_for_judge([jg], sport)    # today_nine 재생성 → 타순이 없어 n=0
    await _run_baseball_matchups(redis, date, [jg], allow_final=True)
    ...
    await redis.set(f"analysis:{sport}:{date}", json.dumps(analysis, …))  # ← 공유 캐시에 기록
    card = await generate_card(analysis)
    await redis.set(f"card:{sport}:{date}", card, …)                      # ← 카드도 덮어쓴다
```

`merge_source_data` 를 **부르지 않는다.** 그래서:

1. `judge_matchup` 이 첫 관문에서 떨어진다 —
   ```python
   boxes = boxscore_payload(jg)        # research[f"{side}_usage"]["games"]
   if not boxes.get("home") or not boxes.get("away"):
       jg["form_unavailable"] = True
       logger.info("[matchup] … 3경기 박스스코어 없음 — 추천 탈락")
       return None
   ```
2. `_prepare_games_for_judge` 가 `{side}_lineup` 없이 `today_nine` 을 다시 만들어
   `{"order": [], "n": 0, "note": "타순 미수집"}` 이 된다.
3. **그 상태가 슬레이트 공유 캐시(`analysis:{sport}:{date}`)에 저장된다.**
   발송(`send_game_prediction`)도 재판정도 같은 키를 읽는다.

호출부는 사용자 조작이다:
```
app/bot/main.py:359   fresh, refreshed = await ensure_game_fresh(sport, date, game["game_id"])
app/bot/main.py:733   fresh, refreshed = await ensure_game_fresh(sport2, …, g["game_id"])
```
**사용자가 경기 버튼을 누르면 그 경기의 판정 재료가 캐시에서 사라진다.**

### 피해 범위 — 자가 복구되지만 창이 있다

`rejudge_after_lineup` 은 야구에서 `merge_source_data(research, jg, sport, bundle)`
를 부르므로 `{side}_usage`·`{side}_lineup` 을 되살린다. 5분 폴링이 그것을 돈다.

그래서 손상은 **다음 라인업 폴링까지**다. 다만:
- 그 사이의 `p_claude` 는 직전 값이 남아 카드가 나갈 수 있다(`_judged` 가 통과).
- `rejudge_open` 이 닫힌 뒤(KBO T-20 · NPB T-10)에 버튼을 누르면 **복구가 없다.**
  그 경기는 남은 시간 내내 자료1 없는 상태로 캐시에 남는다.
- 유료 최종 판정 권한은 안전하다 — `claim_final` 이 박스스코어 관문 **뒤**에
  있어 자료가 없으면 락을 잡지 않는다(MU-4 의 설계가 여기서 값을 한다).

## 🔴 SAN-3 [중] 서술 입력도 같은 19키만 받는다

```python
# narrator.narrate
_payload_game(g, sanitize_research(g.get("research") or {}, sport)[0])
```
서술 모델은 **자료1·3·4·6 을 한 번도 본 적이 없다.** 프롬프트는
"수치를 사건으로 연결하라"고 요구하는데, 최근 3경기 박스스코어도 오늘 타순도
선발 최근 등판도 payload 에 없다. 남는 것은 퍼플렉시티 산문과 `market_board`
(배당 포함, NAR-1)뿐이다.

야구는 산출물이 버려지므로(NAR-2) 지금은 무해하고, 축구는 꺼져 있다.

## 🔴 DEEP-1 [중] `fill_gaps` 에 **NameError** 가 잠들어 있다

```python
# app/research/deep.py:510
text = normalize_response(raw)
```
`normalize_response` 는 `app/research/perplexity.py` 에 있고,
**`deep.py` 는 그것을 import 하지 않는다**(AST 로 전수 확인 — 정의도 임포트도 없음).

호출되면 `NameError` 가 나는데, 바로 감싸는 `except Exception` 이 삼킨다:
```python
except Exception as exc:
    logger.warning("[deep] 빈칸 보충 실패 %s: %s", gaps, exc)
    return {"asked": labels, "filled": [], "error": str(exc)[:120]}
```
→ **100% 실패하면서 "빈칸 보충 실패"라는 API 장애처럼 보이는 로그**만 남는다.

지금은 `fill_gaps` 참조가 0이라 터지지 않는다(DEAD-1). 배선하는 순간 조용히
죽는다. 그리고 이 함수는 실측 근거를 갖고 만들어진 것이다 —
> 실측(2026-08-26): 프롬프트가 길수록 모델이 검색을 포기한다
> (962→1442자에서 채움률 6/10 → 0/10). 그래서 전체 스키마를 다시 묻지 않고
> 빠진 항목만 한 줄로 묻는다.

## 🔴 DEEP-2 [중] 딥서치 스키마가 아직 **시즌 지표를 요구**한다

```
"home_pitcher": {… "siera": 3.95, "xfip": 4.02, "fip": 4.10,
                   "era_recent": 5.40, "era_season": 3.86 …}
"home_bullpen": {"era": 3.85, "fip": 4.02, "ip_last3d": 8.2, "closer_available": true}
```
2026-09-04 대원칙(시즌 누적은 판정 입력이 아니다) 이후에도 스키마는 그대로다.
`era_season` 은 프롬프트에 직접 실리지 않으므로(자료4는 `starter_recent` 만
넘긴다) 판정 입력 위반은 아니다. 다만 `home_bullpen.era` 는 **자료9 로 그대로
간다** — CR-1 의 두 번째 시즌 유입 경로다.

## ✅ VAL-1 정상 — 이 저장소에서 가장 잘 측정된 필터

- 미확보 표현을 **실호출에서 놓친 것만** 추가한다. 추가할 때마다 그 응답 원문을
  주석에 남긴다("…세부 로그에 현재 바로 접근이 되지 않아…" 2026-08-26 KBO).
- `_KEEP_PHRASES = ("출전 불가", "출장 불가", …)` — 결장 정보에 정상적으로
  나오는 "불가"를 오판하지 않게 뺀다. **반대 위험을 함께 다뤘다.**
- `_ECHO_JACCARD = 0.72` — 자카드를 쓴다("한쪽이 짧다는 이유로 반향 판정되는
  오탐을 막는다").
- `filter_sentences` — "실수치와 '못 찾았다' 단서를 한 값에 섞어 보낸다.
  통째로 버리면 실데이터가 같이 사라지고, 통째로 살리면 비데이터가 데이터인 척
  나간다 — **문장으로 가른다.**" 그러면서 구간을 단언하는 필드(`last5`)에는
  이 완화를 쓰지 않는 이유까지 적었다.
- `clean_form` — 한/일 표기(승패무·勝敗分)를 받되 `3승 2패` 같은 **집계 서술은
  거부**한다("순서 정보가 없다 — 폼이 아니다").

---

# 69차 — 워치독 완독 · **경보 코드 목록이 네 벌 있고 넷 다 다르다**

읽은 것: `watchdog.py`(665 전량) — 그리고 코드 목록 네 곳 전수 대조.

## 🔴🔴 WD-1 [상] 같은 목록을 네 곳에 적었고, **네 곳이 전부 다르다**

```
① 코드에서 실제로 발생 (grep '"W-…"')     16개
② app/alerts.py  WATCHDOG_CODES           14개   ← 사용자가 보는 라벨
③ app/watchdog.py 모듈 독스트링             9개
④ CLAUDE.md 워치독 절                       9개
```

| 코드 | ①발생 | ②라벨 | ③독스트링 | ④CLAUDE.md | 발생 지점 |
|---|:--:|:--:|:--:|:--:|---|
| W-SEND-PENDING | ✅ | ✅ | ✅ | ✅ | watchdog |
| W-ODDS-STALE | ✅ | ✅ | ✅ | ✅ | watchdog |
| W-ODDS-BLOCKED | ✅ | ✅ | ✅ | ✅ | watchdog |
| W-LLM-FAIL | ✅ | ✅ | ✅ | ✅ | watchdog |
| W-STORE-DOWN | ✅ | ✅ | ✅ | ✅ | watchdog |
| W-JOB-LATE | ✅ | ✅ | ✅ | ✅ | watchdog |
| W-CARD-LATE | ✅ | ✅ | ✅ | ❌ | watchdog |
| W-GAME-INVISIBLE | ✅ | ✅ | ✅ | ❌ | watchdog |
| W-STALE-GAME | ✅ | ✅ | ❌ | ❌ | watchdog |
| **W-SOURCE-DRIFT** | ✅ | **❌** | ✅ | ❌ | watchdog |
| W-RESCUE-DEAD | ✅ | ✅ | ❌ | ✅ | pipeline:1239 |
| **W-LLM-PAID** | ✅ | **❌** | ❌ | ❌ | judge_route:192 |
| W-FACT-MISMATCH | ✅ | ✅ | ❌ | ✅ | fact_audit:625 |
| W-MONITOR-DOWN | ✅ | ✅ | ❌ | ✅ | fact_audit:639 · shadow_panel:285 |
| W-PANEL-DIVERGE | ✅ | ✅ | ❌ | ❌ | shadow_panel:235 |
| W-JUDGE-OBJECTION | ✅ | ✅ | ❌ | ❌ | shadow_panel:180 |

### 실제 영향

```python
label = WATCHDOG_CODES.get(code, "점검 필요")
head = f"🚨 {code} · {label}"
```
`W-SOURCE-DRIFT` 와 `W-LLM-PAID` 는 라벨이 없어 텔레그램에
**`🚨 W-SOURCE-DRIFT · 점검 필요`** 로 나간다. 둘 다 중요한 경보다 —
전자는 "파서가 조용히 0을 반환한다"(소스 구조 변경), 후자는
"**유료 판정이 캡에 닿았다**"(비용 경보)다.

### 아이러니

`watchdog.py` 자신이 사본 금지를 세 번 못박는다:
```
#: 🔴 **사본을 두지 않는다.** 담당 리그·활성 여부는 `app.registry` 가 원본이다.
#: 🔴 잡 유예도 `app.registry` 가 원본이다. **주기는 어디에도 적지 않는다**
⚠️ 보장선 값은 `pregame_push.FIRST_CARD_GUARANTEE_MIN` 이 원본이다 — 여기 숫자를 적지 않는다
⚠️ 문턱은 `finals.STALE_AFTER_HOURS` 를 **원본으로 참조**한다 — 숫자를 여기 베껴 적으면…
```
숫자는 전부 원본을 참조하는데, **코드 목록은 자기 독스트링에 손으로 적혀 있고
이미 원본과 어긋났다.**

## ✅ WD-2 정상 — 오탐 수정이 전부 **실측으로** 이뤄졌다

이 모듈은 오탐이 날 때마다 그 사고를 주석에 박고 원인을 구조로 고쳤다.

| 오탐 | 원인 | 수정 |
|---|---|---|
| `W-ODDS-STALE espn` 15분마다(09-02 14:32~16:33) | 전 종목 합산으로 `due` 를 셈 | 소스별 담당 리그를 `registry` 에서 읽는다 |
| `mlb_pregame_5m` 12:40 W-JOB-LATE | 주기를 손으로 "5분"이라 적음 | `_JOB_TRIGGERS` 가 다음 발화를 계산 |
| `W-ODDS-STALE betman` | 미구현 소스를 목록에 적음 | `wired=False` 를 registry 가 관리 |
| `W-SOURCE-DRIFT KBO/라인업` 16:01(공시 전) | `scout:{sport}:*` 가 **어제 경기**를 긁음 | 패턴에 오늘 날짜를 넣는다 |
| `W-STALE-GAME` 27건 폭주 우려 | 서 있는 더미를 매번 셈 | **기준선을 심고 새로 생긴 것만** 울린다 |
| KBO 우천취소 53건 | 취소 계열을 안 뺌 | 제외 → 7건 (오탐 46건 차단) |

특히 마지막 둘의 판단이 정확하다:
> 코드가 답할 질문은 "지금 유령이 몇 개냐"가 아니라 **"오늘 새로 안 끝난
> 경기가 있냐"** 다. **등록부가 할 일을 사이렌에 시키지 않는다.**

## ✅ WD-3 정상 — "폴링과 **다른 눈**으로 센다"

```python
🔴 그래서 이 점검은 **폴링과 다른 눈으로 센다.** `status` 를 조건에 넣지
   않고 "곧 시작하는 경기"를 전부 센 뒤, 그중 폴링이 볼 수 있는 것이
   몇 개인지 비교한다. 같은 눈으로 감시하면 폴링이 못 보는 것을 감시도 못 본다.
```
2026-09-03 실사고(KBO 4경기가 `live` 오적재로 폴링 조회에서 통째로 빠졌는데
"잡 executed successfully + 워치독 이상 없음"이 찍힘)의 교훈이 감시 설계
원칙으로 승격된 사례다.

그리고 그 자리에서만 "읽기만 한다" 원칙의 예외를 허용하되, 예외 조건을
명시했다 — "이건 '차단 해제'가 아니라 **불가능한 상태의 교정**이고,
사람이 개입할 판단 여지가 없다(시작 전 경기는 진행 중일 수 없다)."

## ✅ WD-4 정상 — `W-LLM-FAIL` 문구를 **틀렸다고 인정하고** 고쳤다

```python
# 🔴 [2026-09-04] 종전 문구는 **"판정이 멈춰 있다"** 였는데 사실이 아니었다.
#    이 카운터를 올리는 것은 구 체인(`llm/provider.py`)뿐이고 …
#    실측 2026-09-04: 이 경보가 24회로 울리는 동안 KBO·NPB 카드는 정상
#    발송됐다. **틀린 문구가 사람을 엉뚱한 곳으로 보냈다.**
```
그리고 역할 이름을 지어내지 않고 `last` 문자열에서 읽는다.

⚠️ 다만 이 주석이 63차 LLM-4 를 다시 확인해 준다 —
**`provider.py` 만 계수기를 올린다는 사실을 워치독은 알고 있었고,
`ledger.py` 머리말은 모르고 있었다.**

---

# 70차 — 봇 · Go 크롤러

읽은 것: `bot/main.py`(901) `crawler/internal/gate/gate.go`(281)
`crawler/internal/pace/pace.go`(114) `crawler/internal/diff/diff.go`(103) — 1,399줄.

## 🔴🔴 BOT-1 [상] 폴링 워치독이 **자기가 잡으려는 고장을 못 잡는다**

```python
async def _polling_watchdog() -> None:
    """폴링이 POLL_STALL_SEC 이상 멈추면 알린다.
    aiogram이 조용히 죽는 경우(네트워크·토큰 문제) 사용자는 봇이 죽은 줄도 모른다."""
    while True:
        await asyncio.sleep(30)
        try:
            bot = Bot(token=…)
            await bot.get_me()
            poll_tick()          # ← 여기서 하트비트를 **스스로 갱신한다**
            notified = False
        except Exception as exc:
            idle = time.monotonic() - _last_poll_tick
            if idle >= POLL_STALL_SEC and not notified: …경보…
```

`_last_poll_tick` 은 원래 **메시지 핸들러**가 갱신하는 값이다(`poll_tick()` 은
`/health`·`/checklist` 핸들러에도 있다). 그런데 이 감시 루프가 30초마다
**자기가 갱신한다.** 그래서:

- `dp.start_polling` 이 죽고 텔레그램 API 는 살아 있는 경우 → `get_me()` 성공 →
  `poll_tick()` → `idle` 이 30초를 넘지 않는다 → **영원히 경보 없음.**
- 경보가 나가는 유일한 조건은 `get_me()` 자체가 실패할 때, 즉 **네트워크·토큰
  장애**뿐이다.

독스트링이 목표로 적은 "aiogram 이 조용히 죽는 경우"가 정확히 감지 못 하는
경우다. 그리고 이 루프는 **30초마다 새 `Bot` 세션을 만들어 `get_me()` 를
호출한다** — 하루 2,880 콜이다.

## 🔴 BOT-2 [중] `/픽`(전체 추천)이 **KBO·NPB 를 뺀다**

```python
async def answer_full_reco() -> str:
    for sport in ("mlb", "soccer"):        # ← 야구 자동발송 두 리그가 없다
        a = await load_analysis(sport, default_date(sport))
```
CLAUDE.md 는 "KBO·NPB·MLB 자동 발송. 축구는 요청 시에만"이다.
전체 추천 카드는 그 반대로 **꺼져 있는 축구는 넣고 자동발송 두 리그는 뺀다.**

같은 파일 안에서 이 비대칭을 이미 한 번 고쳤다:
```python
# 🔴 KBO·NPB 질문에 "/soccer"를 안내하고 있었다 — 종목이 셋 이상인데
#   이분법으로 나눠서다.
_SLATE_CMD = {"mlb": "/mlb", "soccer": "/soccer", "kbo": "KBO", "npb": "NPB"}
```
같은 뿌리(2종목 이분법)가 `answer_full_reco` 에는 남아 있다.

## 🔴 BOT-3 [하] 죽은 분기 셋

- `section == "perf"` → `render_performance` 는 고정 문자열만 돌려준다.
  그리고 `card_keyboard` 는 `perf` 버튼을 만들지 않는다 — 도달 불가.
- `route_query(text, llm_teams)` 의 `llm_teams` 분기 — `parse_intent` 가
  규칙 기반으로 고정돼 `teams` 가 항상 `[]` 다(2026-09-06 유료 제거).
- `on_game` 의 `sport2` 삼항식은 전개하면 `analysis.get("sport","soccer")` 와 같다.

## ✅ BOT-4 정상 — LLM 이 준 날짜를 **API 기준으로 검증**한다

```python
INTENT_DATE_WINDOW_DAYS = 7
# 실사고(2026-08-26): 프롬프트에 오늘 날짜가 없어 모델이 **2024-08-26**을 반환했고,
# 검증이 없어 2년 전 종료 경기 12건이 분석돼 사용자에게 나갔다.
```
CLAUDE.md 절대규칙 2("LLM 출력의 수치는 API 숫자와 교차검증")를 날짜에도
적용했다. 지금은 의도 파싱이 규칙 기반이라 이 검증이 안 쓰이지만,
`parse_intent_mock` 도 같은 함수를 통과시킨다.

## 🔴 CRW-3 [중] Go 게이트의 **일관성 검사가 도달 불가능**하다

`gate.go` 가 자랑하는 검사:
```go
// 전적 — 승+패+무 = 경기수. 어긋나면 그 팀 전적 전체를 버린다.
// 이 검사가 스냅샷의 **시점**을 증명한다(2026-08-27 실측).
if w+l+d != g { … }
```

그런데 크롤러가 실제로 내보내는 필드는 **9개뿐**이다:
```
away_pitcher · home_pitcher · lineup_away · lineup_home
stadium · starter_status · starts_at · status · game_id
```

게이트 규칙표 27개 중 **18개가 오지 않는 필드**다:
```
home/away_w, _l, _d, _g          ← 승패무 일관성 검사의 입력
home/away_era, _ip_avg, _rank
home/away_pitches_l3, _closer_b2b
```

`w/l/d/g` 가 없으므로 `if !(okW && okL && okD && okG) { continue }` 에서
**항상 빠진다.** 게이트 ②의 세 검사 중 살아 있는 것은 타순 중복과
"양 팀 선발 동일인" 둘뿐이다.

주석이 이 상태를 예고하고 있다 —
> 아래는 **[2][3] 수집 확대에서 채워질 필드**다. 규칙을 **먼저** 박아둔다 —
> 값이 들어오기 시작한 뒤에 규칙을 만들면 그 사이 데이터가 무검증으로 샌다.

의도는 옳다. 다만 **그 수집 확대가 오지 않았고**, 문서(게이트 ② 설명)는
그 검사가 작동 중인 것처럼 읽힌다.

## ✅ CRW-4 정상 — 정상 타순을 100% 폐기하던 가드를 **좁혀서** 고쳤다

```go
// 🔴 KBO 타순은 "나승엽(1루수)" 꼴이다. 1루수·2루수·3루수에 숫자가 들어 있어
//    checkName 의 숫자 검사가 **정상 타순을 100% 폐기**했다.
//    실측 2026-08-30 17:09 운영 로그: 키움@두산·LG@롯데 4건 전부
//    "이름에 숫자가 섞임 — 컬럼 밀림"으로 폐기, 변화 0건 →
//    스케줄러 crawler_lineup_poll 이 타순을 못 봐 저녁 재판정이 트리거되지 않았다.
//    NPB는 포지션이 中堅手 처럼 숫자가 없어 이 사고를 겪지 않았다.
//
// 가드를 푸는 것이 아니다 — 검사 대상을 **원래 의도했던 이름 칸**으로
// 되돌리는 것이다. 컬럼이 밀려 이름 자리에 숫자가 오면 여전히 잡힌다.
```
가드를 넓히지 않고 **적용 지점**을 고쳤다. 그리고 왜 NPB 에서는 안 터졌는지
까지 적었다.

## ✅ CRW-5 정상 — 첫 수집을 "전부 신규"로 내보내지 않는다

```go
// ⚠️ 첫 수집을 "전부 신규"로 내보내면 매일 첫 실행마다 알림이 폭주한다.
// 실사고 유형: **관측 장치가 본체보다 시끄러우면 아무도 안 본다.**
if len(old) == 0 { return nil }
```
그리고 출력 순서를 정렬로 고정한다 — "같은 입력이면 같은 결과여야 비교·테스트가
가능하다."

## ✅ PACE-1 정상 — 창이 열릴 때 **맞춰 깨운다**

```go
// UntilWindow … 평시 주기(60분)만 자면 창 시작을 지나쳐 늦게 들어간다
// (실측 2026-08-28: 11:32 수집 → 60분 주기면 NPB 17:00 창을 17:32에야 만난다).
func Wait(sport, now, starts, idle, fast) time.Duration {
    if Fast(...) { return fast }
    if u := UntilWindow(...); u > 0 && u < idle { return u }
    return idle
}
```
⚠️ 다만 `NPBStopBefore = 15 * time.Minute` 는 파이썬
`pregame_push.NPB_FINISH_MIN = 15` 의 **언어를 넘은 사본**이다. Go 가 파이썬을
import 할 수 없으니 불가피하지만, 한쪽이 바뀌면 다른 쪽은 따라가지 않는다.
지금은 일치한다.

---

# 71차 — 배포 스크립트 · 운영 환경변수 · 딥서치 무효율

## 🔴🔴🔴 RES-1 [최상] 딥서치 응답의 **절반 가까이가 "데이터가 아님"으로 폐기**된다

운영 `research_fill:*` 실측:

| 날짜 | 조사 경기 | 무효 | 무효율 | 경고선 30% |
|---|---:|---:|---:|:--:|
| 2026-08-26 | 27 | 7 | 25.9% | |
| 2026-08-27 | 40 | 11 | 27.5% | |
| **2026-09-06** | 25 | **15** | **60.0%** | 🔴 |
| **2026-09-07** | 15 | **7** | **46.7%** | 🔴 |
| 2026-09-08 | 4 | 1 | 25.0% | |

원인 분류도 남아 있다 — 전부 `parse` 다:
```
research_fail:2026-09-06:parse = 15
research_fail:2026-09-07:parse = 7
research_fail:2026-09-08:parse = 1
```
`classify_research_failure` 에서 `parse` 는 `ResearchUnusableError` 를 포함한다:
```python
raise ResearchUnusableError(
    f"재료 없음 — 무효 필드 {len(dropped)}개 제거 후 recent_form·전문가 픽·결장 정보 전무")
```
즉 **응답은 200 OK 로 왔는데 정제 후 재료가 하나도 안 남았다.**

### 경고선이 있는데 아무도 못 본다

```python
# scheduler.prefetch_job
if fill["invalid_rate"] is not None and fill["invalid_rate"] > 0.30:
    logger.warning("[scheduler] ⚠️ 무효율 %s > 30%% — 무효 키워드 과잉 의심 "
                   "(docs/RESEARCH_VALIDATION.md 튜닝 기준)", _pct(fill["invalid_rate"]))
```
**`logger.warning` 한 줄뿐이다.** 워치독 코드도, `stage_failed` 도, 텔레그램
경보도 없다. 09-06 에 60% 가 나온 날 그 사실을 아는 방법은 Railway 로그를
직접 여는 것뿐이었다.

⚠️ 대상은 MLB·축구뿐이다(`DEEPSEARCH_SPORTS = mlb,soccer` — KBO·NPB 는
크롤링 전용). 그러니 이 무효율은 **MLB 판정의 재료 결손률**이다.

### 채움률도 함께 떨어졌다

```
2026-08-27  40경기 · form 16 · absences 20 · splits 11 · bullpen 16
2026-09-06  25경기 · form  4 · absences  7 · splits  1 · bullpen  3
2026-09-07  15경기 · form  5 · absences  7 · splits  —  · bullpen  4
```
`form` 채움이 40%(16/40) → 16%(4/25) 로 떨어졌다. 모듈 주석이 정확히 이
신호를 예고했다:
> 프롬프트 금지문("못 찾은 이유를 설명하지 말고 null을 써라")이 **과하면
> 채움률이 급락**하고, 반대로 모델이 빈칸을 지어내기 시작하면 채움률만 치솟는다.

**계측은 만들어져 있고, 값도 쌓여 있고, 읽는 사람이 없다.**

## 🔴🔴 ENV-1 [상] `RUN_PREFETCH_ASIA=1` 이 **아직 켜져 있다** — 재기동마다 전체 프리페치

운영 스케줄러 환경변수:
```
RUN_PREFETCH_ASIA = 1
```
`startup_backfill_job` 이 이 값을 읽는다:
```python
#   ⚠️ 14:00 cron 은 **이미 실행됐다**(크레딧 부족으로 실패). 실행 기록이 있으니
#      `_catchup_missed_crons` 가 다시 돌리지 않는다 … 그래서 명시적 훅이 필요하다.
if os.getenv("RUN_PREFETCH_ASIA") == "1":
    asyncio.create_task(_manual_prefetch())   # → prefetch_asia_job()
```
주석이 말하는 상황은 **2026-09-0x 하루짜리 사고**였다. 값은 그대로 남아,
**배포할 때마다 KBO·NPB 전체 프리페치가 한 번 더 돈다** — 팀 폼 LLM 호출 +
매치업 판정 + 크롤 전체를 포함하는 가장 무거운 잡이다.

같은 기동 경로에 SCH-3 의 것들이 함께 붙어 있다:
```
startup_backfill_job   (Redis 전 슬레이트 스캔 + grade_pending + 원장 20행 덤프)
_catchup_missed_crons  (놓친 cron 따라잡기)
soccer_lineup_probe_job (30시간 · 10분 간격 외부 폴링)
_manual_prefetch       (아시아 전체 프리페치)   ← RUN_PREFETCH_ASIA=1
```
**배포 한 번이 이 넷을 동시에 띄운다.**

## 🔴 ENV-2 [중] `PPLX_API_MODE = chat` — 마이그레이션 기한 **19일 남았다**

CLAUDE.md:
> ⚠️ **Perplexity Agent API 마이그레이션 기한: 2026-09-27.**
> `PPLX_API_MODE=agent` 로 코드 수정 없이 전환한다.

운영값은 `chat` 이다. 오늘이 2026-09-08 이므로 **19일**.
코드 수정 없이 env 한 줄로 되는 일이고, 전환 후 무효율이 어떻게 변하는지는
`research_fill` 이 이미 재고 있다 — 지금이 기준선을 잡을 시점이다.

## 🔴 ENV-3 [중] `DISABLED_PROVIDERS` 가 서비스마다 다르다

```
analystbot-scheduler   DISABLED_PROVIDERS = (빈 값)
analystbot-bot         DISABLED_PROVIDERS = grok,perplexity
```
봇은 grok·퍼플렉시티를 안 부르고 스케줄러는 부른다. 의도적일 수 있지만
(사용자 요청마다 유료 호출이 나가는 것을 막는 것), **저장소 어디에도 그 의도가
적혀 있지 않다.** `.env.example` 에도 이 비대칭이 없다.

봇 쪽 `_next_game_message` 는 `OddsClient().fetch_events` 를 직접 부르는데
그것은 `DISABLED_PROVIDERS` 가 아니라 `api_guard.is_disabled("odds")` 소관이라
이 설정과 무관하다 — 다른 문으로 유료 호출이 나갈 수 있다(try/except 로
감싸여 있어 실패해도 조용하다).

## 🔴🔴 DEP-1 [상] `deploy.sh` — **"스케줄러를 먼저"가 보장되지 않는다**

```bash
# ⚠️ **스케줄러를 먼저** 배포한다 — 기동 시 DB 스키마를 적용하므로,
#    봇이 먼저 새 코드로 뜨면 아직 없는 컬럼을 참조할 수 있다.
all)  deploy_one analystbot-scheduler …
      deploy_one analystbot-bot …
      deploy_one analystbot-crawler … ;;
…
for svc in $DEPLOYED; do wait_success "$svc" || RC=1; done
```

`deploy_one` 은 `railway up --detach` 다. **업로드만 시작하고 즉시 반환한다.**
셋의 업로드가 연달아 나가고, `wait_success` 는 **세 개를 다 올린 뒤에** 돈다.

→ 보장되는 것은 "스케줄러 업로드가 먼저 시작됐다"뿐이고,
**"스케줄러가 먼저 기동해 스키마를 적용했다"는 보장되지 않는다.**
빌드 시간이 서비스마다 다르므로(Go 크롤러는 짧고 파이썬은 uv sync 가 있다)
순서가 뒤집힐 수 있다. 주석이 막으려던 그 상황이다.

## 🔴 DEP-2 [중] `cmd` 인자는 **찍기만 하고 쓰이지 않는다** — 그리고 값이 틀렸다

```bash
deploy_one() {
  local svc="$1" cmd="$2" path="${3:-.}"
  …
  echo "▶ $svc 배포 ($cmd)"          # ← 화면에 찍기만 한다
  ( cd "$path" && railway up … --detach )   # ← cmd 를 넘기지 않는다
}
crawler) deploy_one analystbot-crawler "crawler -interval 10m" crawler ;;
```

실제 실행 명령은 `crawler/Dockerfile` 의 `CMD` 다:
```dockerfile
# 평시 60분 — 타순 창에 들어선 종목만 2분.
CMD ["crawler", "-interval", "60m"]
```

**`10m` 은 어디에도 없다.** 그런데 두 곳이 그렇게 적고 있다:
```
tools/deploy.sh   "crawler -interval 10m"      (화면 출력)
CLAUDE.md 표       `crawler -interval 10m`      (서비스 표)
```
사본 둘이 원본과 어긋났고, 배포할 때마다 화면에 **틀린 값**이 찍힌다.

## 🔴 DEP-3 [중] 스케줄러의 **실행 명령이 저장소에 없다**

```
Dockerfile      CMD ["python", "-m", "app.bot"]       ← 기본은 봇
railway.json    startCommand 없음
```
스케줄러의 `python -m app.scheduler` 는 **Railway 대시보드 설정에만** 있다.
Dockerfile 주석이 그것을 인정한다:
> 기본은 봇. 스케줄러는 railway.json / 서비스 설정에서 startCommand로 덮어쓴다.

`railway.json` 에는 없으므로 남는 것은 대시보드뿐이다. 그 설정이 지워지거나
서비스를 다시 만들면 **스케줄러 서비스가 봇을 두 개 띄운다** — 프리페치·폴링·
발송·워치독이 통째로 멈추고, 봇은 정상 응답하므로 겉으로는 멀쩡해 보인다.

## 🔴 DEP-4 [하] 운영이 **1커밋 뒤처져 있다**

```
GIT_COMMIT_SHA(3서비스 전부) = 7c0f9be
로컬 HEAD                    = 21e84d2  "판정 정확도 진단 — 방향엔 정보가 있고…"
```
CLAUDE.md 의 실사고 이력(14커밋·26커밋 뒤처짐)에 비하면 작지만,
**미배포 상태 자체는 지금도 계속되고 있다.**

## ✅ DEP-5 정상 — 배포 게이트가 **기계로** 걸려 있다

```bash
① 미커밋 변경 → 중단
② `git archive HEAD | docker build` — 배포될 파일만으로 빌드 검증
   ("로컬 docker build는 .gitignore를 보지 않아 이 결함을 못 잡는다")
③ 판정 안정성 스모크 — 같은 프롬프트 3회, 우세가 갈리면 중단
   ("인프라 장애(503)는 막지 않는다 — 유효 응답 2건 미만이면 SKIP.
     503 이 배포를 막으면 이 게이트는 곧 꺼지고, 꺼진 게이트는 없는 게이트다")
④ 커밋 SHA 주입 (/health 버전 추적)
⑤ SUCCESS 확인 — "**'배포 요청 완료'는 배포된 것이 아니다**"
```
특히 ③의 SKIP 판단과 ⑤가 좋다. ⑤의 주석이 이 저장소의 핵심 규율을 한 줄로
말한다 — "**기계가 확인한다. 사람의 다짐이 아니라 종료 코드다.**"

---

# 72차 — 🔴 **원장 전수 측정: 게이트가 거꾸로 작동하고 있다**

운영 `pick_ledger` 660행(채점 598) 전수.

## 🔴🔴🔴 LED-A [최상] **우리가 버린 픽이 우리가 고른 픽보다 잘 맞는다**

```
게이트 결과      채점    적중    적중률
거부권탈락        80      50    62.5%   ← 확신도 '하'로 버린 것
보드만           466     244    52.4%
추천              37      19    51.4%   ← 우리가 고른 것
가치주의          15       6    40.0%
────────────────────────────────────
전체             598     319    53.3%   (목표 58~60%)
```

**추천(51.4%)이 거부권탈락(62.5%)보다 11.1%p 낮다.**
그리고 추천은 무작위(50%)와 사실상 구분되지 않는다.

확신도로 갈라도 같은 그림이다:
```
확신도 하   80건  62.5%
확신도 중  509건  52.1%
확신도 상    9건  44.4%
```

### 2026-09-07 커밋이 이 숫자를 절반만 읽었다

`markets.row_stars` 의 주석(d222bb0, 2026-09-07):
> ⚠️ **거부권은 그대로다.** 확신도 `하` → `거부권탈락` 은 **데이터상 잘
> 작동한다(62.5% n=16)**. 뺀 것은 `상/중` 의 표기이지 `하` 의 게이트가 아니다.

62.5% 는 "**확신도 하 픽이 잘 맞는다**"는 뜻이다. 그리고 거부권은
**그 잘 맞는 픽을 버리는 게이트**다. "잘 작동한다"고 읽을 수 없다.

표본은 그때 n=16 이었고 지금 **n=80** 이다. 다섯 배가 됐는데 값은 62.5% 로
그대로다 — 우연이 아니다.

> ⚠️ 이 해석에는 선택 편향이 있을 수 있다. 거부권탈락 픽은 발송되지 않으므로
> "걸었으면 벌었다"는 뜻이 아니라 "그 판정의 우세 지목이 맞았다"는 뜻이다.
> 다만 게이트의 목적이 **틀린 판정을 거르는 것**이라면, 지금 그것은
> 가장 잘 맞는 판정을 거르고 있다.

## 🔴🔴🔴 LED-B [최상] **NPB 추천은 10건 중 1건 맞았다**

```
추천 픽의 리그별 적중
  KBO   11/13 = 84.6%
  MLB    7/14 = 50.0%
  NPB    1/10 = 10.0%     ← 9건 연속 오답에 가깝다
```
전 픽(추천 아닌 것 포함)으로 넓혀도 같다:
```
KBO  92/158 = 58.2%
MLB 181/327 = 55.4%
NPB  46/113 = 40.7%      ← 동전던지기보다 9.3%p 낮다
```

이항검정으로 "NPB 추천 10건 중 ≤1 적중"이 p=0.5 아래 나올 확률은
**약 1.1%** 다. 표본 부족으로 넘길 수 없다.

### 그런데 NPB 는 "검증됨"으로 켜져 있다

```python
# form_card.rec_label
if sport == "npb" and not s.npb_last3_verified:
    return "NPB: 참고용"
```
운영값 `npb_last3_verified = True` — **참고용 딱지 없이 정상 추천된다.**

`config` 의 그 플래그가 무엇을 검증했다는 것인지 저장소에서 확인하지 못했다.
지금 원장이 말하는 것은 **NPB 판정이 방향을 반대로 잡고 있다**는 것이다.

## 🔴🔴🔴 LED-C [최상] **2026-09-07 부터 추천이 0건이다**

```
날짜        보드만  거부권탈락  추천  가치주의
09-01        51       11       6      -
09-02        67       17       4      -
09-03        26        8       4      3
09-04        59       13       4      3
09-05        63       21       8      4
09-06       166       14       5      5
09-07        34        5       0      0    ← 추천·가치주의 전멸
```

09-07 은 v1.4(`d222bb0`, "실력 축을 복원하고, **시장을 거스르는 확신을 잠근다**")
가 배포된 날이다. 그날 39행 중 추천이 하나도 없다.

내가 세 게이트를 그날 원장에 다시 적용해 봤다:
```
09-07 (39행)  ①확률하한 미달 35 · ②시장게이트 1 · ③거부권 0 · 나머지 3
09-06 (190행) ①확률하한 미달 170 · ②시장게이트 15 · ③거부권 1 · 나머지 4
```
세 게이트를 통과한 3건이 있는데도 원장에는 추천 0 이다 →
`qualifies()` 의 **나머지 조건**(라인업 확정 · 선발 표본)이 그 셋을 마저 잘랐다.

게이트가 넷 겹으로 쌓여 있고, 각 층이 자기 몫을 하는 사이 **출력이 0이 됐다.**
CLAUDE.md 의 발송 규율("조용한 0은 결함이다")이 발송에는 적용돼 있는데
**추천에는 적용돼 있지 않다.**

## 🔴🔴🔴 MON-A [최상] 감시 L2·L3 는 **수리한 뒤에도 0행**이다

```
judge_review   0행   (L2 검사역)
shadow_panel   0행   (L3 독립 판정)
```

수리 커밋이 있다 — `fe26660 2026-09-07 "감시 L2·L3 가 한 번도 돈 적이 없었다 —
스모크 하네스와 대상 선정 수리."` 그리고 그 커밋은 **배포돼 있다**(운영 7c0f9be).

운영에서 `pick_targets` 를 실제로 돌려 봤다:
```
shadow_max_per_slate=5 · prompt_keep_ttl_sec=86400 · shadow_diverge_pp=0.08
analysis:mlb:2026-09-07: 경기 4 → 대상 0
   game=4099 gate=None pick=샌디에이고 파드리스 승 p=0.56 프롬프트원문=있음
   game=4100 gate=None pick=세인트루이스 카디널스 승 p=0.43 프롬프트원문=있음
   game=4101 gate=None pick=LA 다저스 승        p=0.53 프롬프트원문=있음
   game=4102 gate=None pick=토론토 블루제이스 승 p=0.39 프롬프트원문=있음
보관된 프롬프트 원문 키: 11
```

**재료(프롬프트 원문)는 다 있다. 대상이 0이다.**

```python
ok = [g for g in games
      if _grade(g) in (GATE_EDGE, GATE_RECOMMENDED) …]
```
감시 대상을 **추천·엣지로만** 잡았는데, LED-C 대로 09-07 부터 추천이 0 이다.
그리고 `GATE_EDGE` 는 전 기간 원장에 **한 건도 없다**(보드만·거부권탈락·추천·
가치주의 넷뿐).

즉 **09-07 에 감시를 고쳤고, 같은 날 감시할 대상이 사라졌다.**

### 이 설계 자체에 문제가 있다

감시의 목적은 "판정이 틀렸는가"를 보는 것이다. 그런데 대상을
**우리가 이미 좋다고 판단한 픽**으로만 잡는다. LED-A 가 보여주듯
가장 틀리는 곳은 추천이 아니라 **거부권탈락(우리가 버린 것)** 이다.
감시가 가장 보고 싶어 할 표본을 정의상 제외한다.

## 🔴🔴 LED-D [상] `game_trace` 가 **판정의 3분의 1만** 발송까지 따라간다

```
재판정  603 · 딥서치 599 · 조립 429 · 판정 397 · 게이트 124 · 발송 124
```
`판정 397` → `발송 124`. 투명 리포트 ④·⑤절이 재구성해야 할 "게이트→발송"
줄이 판정의 31% 에만 있다. (리포트 자체가 안 돌지만 — ORP-1)

## 🔴 LED-E [중] `odds` 는 39/660 (5.9%) — 가치 게이트가 사실상 안 돈다

`market_prob` 은 518/660(78.5%)까지 올라왔다(`backfill_market` 이 돌았다).
그러나 `odds` 는 39행뿐이고, 그것이 없으면
```python
def passes_value(p, odds):
    v = value(p, odds)
    return None if v is None else v >= VALUE_MIN   # None = 게이트 건너뜀
```
**가치 게이트(VALUE_MIN=1.05)가 94% 의 픽에서 판정 불가**다.
`가치주의` 15건이 전부 09-03~09-06 에 몰려 있는 것이 그 흔적이다.

## ⛔ 정정 — `confidence_llm` 이 아니라 `confidence_probe` 다

내 첫 쿼리가 `confidence_llm` 을 찾아 `UndefinedColumnError` 를 냈다.
실제 컬럼 목록을 뽑으니 이름이 다르다:
```
id, game_id, sport, league, date, judged_at, p_home, favored, confidence,
lineup_status, gate_result, model, odds, market_prob, divergence_pp,
edge_status, rejudge_count, is_final, final_score, winner, hit, void,
graded_at, merged_from, trial, confidence_probe
```
`7c0f9be` "확신도 교체는 관문에서 떨어졌다 — **게이트는 두고 후보만 새긴다**"
가 만든 칸이다. 계획서(`agile-sparking-haven.md`)의 `confidence_llm` 이
구현에서 `confidence_probe` 로 바뀌었고, **계획서만 옛 이름으로 남아 있다.**

교체를 하지 않고 후보만 기록하기로 한 판단 자체는 옳다 — 배포 전에
게이트 분포 변화를 재라고 계획서가 요구했고, 그 관문에서 떨어뜨렸다.

## ✅ MON-B 정상 — L1 사실 감사는 **돌고 있다**

```
judgement_audit 1,156행 · 확인 9,693 · 미발견 1,462 · 불일치 414
```
불일치율 = 414 / (9,693+1,462+414) ≈ **3.6%**.
L1(`fact_audit`)만이 세 감시층 중 유일하게 작동한다. 다만 FA-1 에서 확인했듯
`elo` 패턴의 `\b` 결함으로 오탐이 섞여 있어, 414 를 액면 그대로 읽으면 안 된다.

---

# 73차 — CG-1 재확인: **같은 결함을 한 곳만 고쳤다**

## 🔴🔴🔴 CG-1 [최상] `provider.py` 는 아직 Anthropic 차단기를 **전 역할에** 건다

```python
# app/llm/provider.py:643~663
async def complete(role, messages, …):
    chain = provider_chain(role, settings)
    …
    from app.engine.credit_guard import abort_if_credit_gone
    abort_if_credit_gone(role)          # ← 무조건. 체인을 보기 전에.
    for p in chain:
        if s.is_disabled(p.name): continue
        if (why := _is_exhausted(p.name)): continue   # ← 여기는 provider 별로 옳다
```

```python
# app/engine/credit_guard.py
def abort_if_credit_gone(where: str = "") -> None:
    why = _is_exhausted("anthropic")     # ← **anthropic 만** 본다
    if not why: return
    raise ApiQuotaError("anthropic", f"잔액 소진으로 중단 ({loc}): {why}")
```

`provider.py` 를 지나는 역할은 **넷 다 무료 사슬**이다(운영 실효 설정):
```
INTERPRETER_PROVIDER = groq   (fallback gemini)
NARRATOR_PROVIDER    = groq   (fallback gemini)
INTENT_PROVIDER      = groq   (fallback gemini)
JUDGE_A_PROVIDER     = (빈 값)
```
**Anthropic 과 아무 관계가 없는데, Anthropic 이 소진되면 넷이 통째로 죽는다.**
루프 안의 per-provider 검사(`_is_exhausted(p.name)`)가 이미 올바르게 있는데,
그 앞에 전역 차단기가 하나 더 서 있다.

### 같은 결함을 `matchup.py` 에서는 고쳤다

```python
# app/engine/matchup.py — 0806b76 (2026-09-06)
# 🔴 [P0 2026-09-06] **Anthropic 차단기는 Anthropic 경로에만 걸린다.**
#    종전에는 경로를 보기 전에 무조건 불렀다. 그래서 축구 실험(`soccer_trial`)이
#    Anthropic 400 을 맞고 공용 차단기를 내리자, 무료 사슬(Gemini)로 도는
#    야구 판정이 **호출도 못 해보고** 죽었다.
#      실사고 2026-09-05~06: **MLB 발송 0/85 (0%)**. 오류 문자열이 구조를
#      그대로 보여준다 — "잔액 소진으로 중단 (matchup:SF@NYM): soccer-trial/claude-sonnet-5"
#      앞은 야구 호출부, 뒤는 축구가 남긴 사유다.
if final and not _free_primary(role):
    abort_if_credit_gone(f"matchup:{jg.get('away')}@{jg.get('home')}")
```

커밋 이력이 두 곳이 갈린 지점을 그대로 보여준다:
```
provider.py  abort_if_credit_gone 도입   cc5ea41  2026-08-29
matchup.py   경로별로 좁힘               0806b76  2026-09-06   ← 여기만 고쳤다
provider.py  (그 뒤로 손대지 않음)
```

**MLB 발송 0/85 를 낸 그 결함이 `provider.py` 에는 그대로 있다.**
지금 터지지 않는 이유는 `_EXHAUSTED` 가 **프로세스 메모리**라, 스케줄러가
Anthropic 400 을 맞은 그 프로세스 안에서만 유효하기 때문이다. 최종 판정이
잔액 소진으로 실패하는 순간, 같은 프로세스의 서술·해석·의도가 전부 함께 죽는다.

### 게다가 그 차단기는 **재기동으로만 풀린다**

```python
# credit_guard.trip_credit
# 🔴 **`api_guard.trip_credit` 을 부르지 않는다.** 그쪽은 Redis 에 영구 차단을
#    걸고 `clear_block()` 을 사람이 부르기 전까지 풀리지 않는다.
#    종전 동작은 프로세스 안의 `_EXHAUSTED` 플래그라 **재시작하면 풀렸다**
```
설계 의도는 옳다(충전하면 재시작으로 복구). 다만 그 사이 무료 역할까지
같이 죽는 것은 의도가 아니다.

## ✅ PRV-1 정상 — 소진 판정을 **실제 응답 문구로** 맞췄다

```python
# 하루치 소진을 뜻하는 문구 — 분당 제한(잠시 뒤 풀림)과 **구분해야 한다.**
#   ⚠️ **실제 응답 문구로 맞춘다.** "quota exceeded"로 적었더니 Gemini의
#      "You exceeded your current quota"가 안 걸렸다(어순이 다르다) — 추측한
#      문구는 안 맞는다. 새 provider를 붙이면 실제 429 본문을 보고 추가하라.
_DAILY_MARKERS = ("per day", "tpd", "daily", "quota exceeded", …)
```
추측한 문자열이 안 맞는다는 것을 실측으로 확인하고 규칙까지 남겼다.

## ✅ PRV-2 정상 — 조용한 폴백을 금지한다

```python
if tried:
    logger.warning("[llm:%s] 폴백 — %s 실패 후 %s 응답", role, "→".join(tried), p.name)
    return LLMResult(…, tuple(tried))
```
> ⚠️ 조용한 폴백 금지. 판정 품질이 provider마다 다를 수 있으므로
> "어느 모델이 이 판정을 했는가"가 리포트·DB까지 따라가야 한다.

`LLMBudgetError` 도 조용히 넘기지 않는다 —
"빈 응답으로 넘어가면 목 출력과 구분되지 않아 '판정 0건'의 원인을 영영 못 찾는다."

---

# 74차 — 문서가 세운 규율을 **같은 날 배포가 무너뜨렸다**

읽은 것: `docs/HANDOFF_2026-09-07.md`(124) `docs/BASELINE_PLAN_2026-09-08.md`(70).

## 🔴🔴🔴 DISC-1 [최상] **"1변경 1배포"가 하루 25커밋으로 무너졌다**

CLAUDE.md 코드 변경 절차:
> 영향 지도 5문 → 5대 반복 결함 체크 → 계약 테스트 → **1변경 1배포** →
> 첫 사이클 실측. **절차를 생략한 커밋은 반려 대상이다.**

일자별 커밋 수:
```
2026-09-04  35   2026-08-25  35   2026-09-03  32   2026-08-27  32
2026-08-30  29   2026-08-31  28   2026-09-07  25   2026-09-06  24
```
**하루 평균 25~35커밋**이다. "1변경 1배포"가 문자 그대로 지켜진 날은 없다.

### 그리고 그 결과가 지금 측정 불능으로 나타난다

`docs/BASELINE_PLAN_2026-09-08.md` 는 정확히 이 위험을 막으려고 쓰였다:

> **이 슬레이트는 배포하지 않은 상태로 돌린다.** 운영은 `63acfcb` 이고,
> 로컬에 미배포 커밋 2건(`049f01b`·`cfe2e13`)이 쌓여 있다. **그건 의도된 것이다.**
>
> 이유: `cfe2e13`(표본 하한 세 칸)이 **판정 입력**을 바꾼다. 자료12(v1.4)의
> 효과를 한 번도 측정하지 못한 상태에서 자료10·자료1까지 같이 바꾸면,
> 나중에 적중률이 움직였을 때 **무엇 때문인지 가를 수 없다.**

**그 계획은 지켜지지 않았다.**

```
계획서가 적은 운영     63acfcb
실제 운영             7c0f9be     ← 63acfcb 뒤로 12커밋 더
로컬 HEAD             21e84d2

그 사이에 들어간 것 (전부 09-07):
  fe26660 감시 L2·L3 대상 선정 수리
  60eecac 타순 0명 확정 오판
  5d3ab8a opus 후행 쉼표 파서
  bc40750 Anthropic 소진 시 grok 대체
  cff9a93 시장을 판정 원장에 붙임          ← 판정 원장 변경
  5681c8f 변수 지시어 해결 + 해결사 2종      ← 판정 입력 변경
  92b31a0 분기점 지시어                    ← 판정 입력 변경
  7c0f9be 확신도 후보 기록
  049f01b W-STALE-GAME
  cfe2e13 표본 하한 세 칸                  ← 계획서가 "따로 배포하라"고 한 그것
  … 외
```

계획서가 **"자료12 효과와 섞이면 안 된다"고 지목한 `cfe2e13` 이 같은 날
함께 배포됐다.**

### 그래서 LED-C 를 설명할 수 없다

09-07 부터 **추천이 0건**이 됐다(LED-C). 후보가 이만큼 있다:
- `d222bb0` v1.4 시장 동의 게이트
- `cfe2e13` 표본 하한 세 칸(자료10 분위수·리그 선발 기준선·자료1 상대 보정)
- `60eecac` 타순 0명 확정 판별 수정 → `lineup_status` 확정 판정이 엄격해짐
- `5681c8f`·`92b31a0` 판정 입력 변경

**절제 실험을 할 수 없다.** 그리고 CLAUDE.md 가 그 방법을 이미 적어 두었다 —
> **절제 실험(하나씩 빼보기) 한 번이 추론 세 번보다 정확하다.**

## 🔴🔴 DISC-2 [상] `BASELINE_PLAN` 의 7문에 지금 답할 수 있는 것과 없는 것

계획서가 09-08 KBO 슬레이트에서 재라고 한 7문. 내가 지금 답할 수 있는 만큼:

| # | 질문 | 지금 답 |
|---|---|---|
| 3 | 시장 동의 게이트가 추천을 몇 건 줄이는가 | **09-07 추천 0건**(LED-C). 다만 위 이유로 게이트 단독 효과는 아니다 |
| 4 | `p_market` 이 실제로 채워지는가 | ✅ **채워진다** — 09-05·09-06·09-07 전부 100%(96/96·190/190·39/39). 계획서가 걱정한 "MLB 09-07 판정 6건 전부 None" 은 해소됐다 |
| 5 | 자료6(라인업 의도)이 확정 재판정에서 채워지는가 | ✅ 채워진다 — `lineup_verdicts` 323행. 다만 **변경점의 39.7%가 유실된다**(LI-1) |
| 6 | 판정 승계가 캐시 재생성에서 도는가 | 미확인 |
| 1·2 | 자료12 인용률·역방향 건수 | 미확인 |
| 7 | NPB 일정 상태 수정 | 미확인 |
| — | v1.4 표본 `N/50` | **0/50 × 3리그**(FRZ-1). 09-07 표본 재시작 이후 다시 0 |

## 🔴🔴 SEC-1 [최상 · 보안] 키 유출은 **이미 알려져 있었고, 아직 회전되지 않았다**

`HANDOFF_2026-09-07.md` §3:
> | API 키 재발급 | **사용자 숙제** | GROQ·NVIDIA·OPENROUTER 3개.
> 오염된 `GROQ_API_KEY` 값에 나머지 둘이 들어 있었고 **그 문자열이 운영 로그에
> 평문으로 찍혀 왔다.** MISTRAL 은 **미사용**이라 삭제 가능 |

→ 59차 LLM-1·LLM-2 는 **새 발견이 아니다.** 이미 09-07 에 기록됐다.
내 몫으로 남는 것은 셋이다:

1. **유출 경로가 로그만이 아니다.** `llm_outage:*` **Redis 리스트에 211행**이
   같은 문자열을 담고 있고 **TTL 14일**이다. 로그는 회전되지만 이 키들은
   09-18 까지 조회 가능한 상태로 남는다.
2. **아직 회전되지 않았다.** 운영 env 의 `MISTRAL_API_KEY` 앞 4자(`xN5R`)와
   `NVIDIA_API_KEY` 접두사가 유출 문자열의 것과 **같다.**
   (핸드오프는 MISTRAL 을 "미사용이라 삭제 가능"이라 했는데 **아직 설정돼 있다.**)
3. **저장 시점 마스킹이 없다.** `ledger.record_outage` 가 `detail[:200]` 을
   원문 그대로 넣는다. 이번엔 헤더였고, 다음엔 URL 쿼리일 수 있다.

## ✅ HAND-1 정상 — 인수인계가 **모르는 것을 모른다고 적었다**

```
### 🔴 확정 스펙이 이 세션에 도착하지 않았다
지시서는 *"방금 내가 보낸 ①②③ 스펙 그대로 복사"* 라고 했으나, **이 대화에
그 스펙이 없다.** 지어내지 않고 빈칸으로 남긴다 — 다음 세션이 사용자에게
다시 받아야 한다.
```
그리고 자기 오판도 적었다:
```
⚠️ 나는 오늘 이것을 한 번 "17시간 정지 🔴" 로 오판했다 — 숫자만 보고
   일정을 안 읽었다. 다음 세션은 **일정을 먼저 조회할 것.**
```
(나도 같은 실수를 두 번 했다 — 63차 LLM-3, 66차 SCH-5.)

## ✅ HAND-2 정상 — 라인 번호가 밀릴 것을 미리 경고했다

```
⚠️ 위 라인 번호는 `63acfcb` 기준이고, 오늘 A 배선으로 `pipeline.py` 가
   늘어났다. 착수 시 **다시 확인할 것.**
```
좌표를 문서에 적는 것 자체가 사본이지만, 그것이 사본임을 알고 유효기간을
명시했다.

---

# 75차 — 🔴 **애리조나 한 팀이 Statcast 에서 통째로 빠져 있다** (실행으로 증명)

## 🔴🔴🔴 STC-1 [최상] 팀 코드 `AZ` 가 매핑에 없다 — `ARI` 로 적혀 있다

운영 컨테이너에서 실제 Statcast 응답을 받아 대조했다:

```
$ statcast(start_dt="2026-09-05", end_dt="2026-09-05")

statcast 실제 팀코드:
 ['ATH','ATL','AZ','BAL','BOS','CHC','CIN','CLE','COL','CWS','DET','HOU','KC',
  'LAA','LAD','MIA','MIL','MIN','NYM','NYY','PHI','PIT','SD','SEA','SF','STL',
  'TB','TEX','TOR','WSH']

매핑에 없는 코드:            ['AZ']       ← 실제로 오는데 사전에 없다
매핑에만 있고 안 오는 코드:   ['ARI','OAK'] ← 사전에 있는데 오지 않는다
```

```python
# app/collectors/statcast.py:32
TEAM_CODE_TO_NAME = {
    "LAA": …, "ARI": "Arizona Diamondbacks", …   ← 오지 않는 코드
    …, "OAK": "Athletics", "ATH": "Athletics", …  ← 개명은 둘 다 넣어 뒀다
}
```
```python
def _team_of_batter(row) -> str | None:
    code = row.get("away_team") if top.startswith("Top") else row.get("home_team")
    return TEAM_CODE_TO_NAME.get(str(code))     # 'AZ' → None
...
d = d[d["team"].notna()]                         # None 인 행은 통째로 버려진다
```

## 운영 캐시가 그대로 보여준다

```
statcast:offense:2026-09-07   캐시 팀 29 / 매핑 팀 30
빠진 팀: ['Arizona Diamondbacks']
  pitchers: 567 · bullpen: 29 · batters: 29 · league: 2
```

**타선·불펜·타자 랭킹 셋 다 29팀뿐이다.** 애리조나만 없다.

## 애리조나 경기에서 무엇이 사라지는가

`merge_into_research` 를 타고 들어가는 것들이 전부 빈다:
```
{side}_offense    xwoba_30d · barrel_pct · hardhit_pct · exit_velo · k_pct · bb_pct
                  · vs_lhp_woba · vs_rhp_woba        ← λ 타선 축 전체
bullpen_overused  불펜 과소모 판정                     ← 상대가 애리조나면 판정 불가
batters           타석 상위 20명                       ← `absences.from_lineup`·
                                                        `from_injured` 의 중요도 기준
```
`absences` 는 그 랭킹으로 "주포(-4%p) / 주전 타자(-2%p) / 선수"를 가른다.
애리조나는 **랭킹이 없으므로 모든 결장자가 `선수`** 로 떨어진다.

그리고 `league_baselines` 가 **29팀 평균**으로 계산된다 — 이 모듈이 상수 대신
데이터셋 평균을 쓰기로 한 바로 그 이유(0.011 차이가 λ 를 −4% 흔들었다)에
비추면, 한 팀 누락은 무시할 수 없는 축이다.

## 규모

```
전 기간 애리조나 경기      25건 (전부 최근 30일 안)
그중 판정 원장에 오른 픽    23건 (적중 20)
```

## 왜 안 잡혔나

이 파일은 팀 개명(OAK → ATH)을 이미 겪었고 **둘 다 넣어 두었다.**
즉 코드 변경 가능성을 아는 상태였다. 그런데 `ARI` 가 한 번도 오지 않는다는
사실을 **확인하는 장치가 없다.**

- `_team_of_batter` 는 모르는 코드를 `None` 으로 만들고 **조용히 버린다.**
- 로그는 `[statcast] … 갱신 — 팀 29개` 라고 정확히 찍지만, **29가 이상하다고
  말해 줄 것이 없다.** 30이어야 한다는 사실이 코드 어디에도 없다.
- 목 픽스처 주석에조차 그 숫자가 굳어 있다 —
  `2026-08-22 기준 1회 캡처(122,016행 → **팀 29**·투수 556)`.
  **결함이 픽스처에 화석으로 남아 정상값처럼 읽힌다.**

CLAUDE.md 의 5대 반복 결함 중 **"조용한 성공 — 분모가 사라지는 실패"** 의
교과서적 사례다. ENGINEERING.md 가 그 대응까지 적어 두었다:
> **④ 이 변경이 실패하면 "시끄럽게" 실패하는가?**
> **조용히 0건이 되는 경로가 하나라도 있으면** 경보 또는 대사를 함께 넣는다.

여기서는 0건이 아니라 **29/30** 이라 더 안 보였다.

---

# 76차 — 🔴 대소문자 하나로 자료10·자료1 의 한 축이 **항상 null** 이다

읽은 것: `variable_ref.py`(462) `provenance.py`(263) `naver_kbo.py`(428)
`npb_form.py`(250) `last3.py`(31) `statcast.py`(553 완독) — 1,987줄.

## 🔴🔴🔴 VR-1 [최상] `opp_starter_season_era` 는 **12/12 전부 null** — 키가 `ERA` 인데 `era` 로 읽는다

운영 컨테이너에서 수집기를 직접 불러 확인했다:

```
$ fetch_mlb(["Shohei Ohtani","Zack Wheeler"], 2026)
반환 키: ['BB', 'BB9', 'ERA', 'K', 'K9', 'WHIP', '선발', '이닝']
  .get('era') → {'Shohei Ohtani': None,   'Zack Wheeler': None}      ← 소비처가 읽는 키
  .get('ERA') → {'Shohei Ohtani': '1.79', 'Zack Wheeler': '3.23'}    ← 실제 키
```

```python
# app/collectors/starter_season.py:67  (생산)
out = {"선발": …, "이닝": ip, "ERA": _f("era"), "WHIP": …, "K": k, "BB": bb}
# :265  slim_asia 도 같다 — ("ERA", era)

# app/engine/variable_ref.py:307  (소비)
era = (get(name) or {}).get("era")          # ← 소문자
g["opp_starter_season_era"] = era
```

운영 캐시 실측:
```
game=4099  opp_starter_season_era = None  (6경기 전부)
game=4100  opp_starter_season_era = None  (6경기 전부)
```

### 로그가 사람을 엉뚱한 곳으로 보낸다

```python
if era is None:
    logger.info("[var-ref] 상대 선발 시즌 라인 미매칭 %s %s — null", sport, name)
```
매 행마다 **"미매칭"** 이 찍힌다. 읽는 사람은 이름 정규화(`lookup_asia`·
`norm_jp`·`strip_pos`)를 의심하게 되고, 실제 원인인 **키 대소문자**는
로그에 흔적이 없다. 그리고 요약 줄은 이렇게 나간다:
```
[var-ref] mlb 상대 선발 시즌 ERA 0/6 부착
```
"0/6" 이 정확한데도 그 0 이 무엇 때문인지 말하지 않는다.

### 무엇이 사라지는가

이 값은 **자료1(3경기 박스스코어) 안의 경기별 칸**이다.
모듈 머리말이 그 용도를 적었다:
> 1-c. 타선 침체 맥락 — **상대 선발 시즌 ERA**
> "그 3경기 득점이 누구를 상대로 낸 것인가"

`boxscore_payload` 가 `{side}_usage.games` 를 통째로 넘기므로 판정은
`"opp_starter_season_era": null` 을 12칸 받는다. 상대 수준 보정의 한 축이
**한 번도 채워진 적이 없다.**

(다른 축인 `opponent_rank`·`opponent_win_pct` 는 `last3.attach_opponent_context`
가 채우고 있어 살아 있다. 그리고 09-07 에 `opponent_adjust`(배율)가 새로
붙었다 — 같은 질문에 답하는 세 번째 시도다.)

## 🔴🔴 VR-2 [상] `form_gap` 도 같은 키를 읽는다 — **자료10의 "부진후회귀" 축이 죽어 있다**

```python
def form_gap(jg, side) -> float | None:
    season = ((r.get(f"{side}_starter_season") or {}).get("era"))   # ← 소문자
    if season is None:
        return None
```

여기는 원인이 **둘 겹쳐 있다**:

① 키 대소문자(위와 같다).
② `{side}_starter_season` 자체가 비어 있다 — 운영 실측 `{"home": {}, "away": {}}`.
   2026-09-04 대원칙 개정으로 `starter_season.attach` 호출이 삭제됐다:
   ```python
   # pipeline.py:2741
   # 🔴 [C2 2026-09-04] 선발 시즌 라인(자료7)·타선 시즌 라인(자료8)의
   #   부착을 **없앴다.** 대원칙: 시즌 누적은 판정 입력이 아니다.
   #   수집기 자체는 지우지 않았다: `variable_ref` 가 자료10 참조에 쓴다.
   ```
   주석이 "`variable_ref` 가 쓴다"고 남겨 뒀는데, `variable_ref` 가 쓰는 것은
   **`fetch_mlb` 직접 호출**(1-c)이고 `form_gap`(1-b)은 `attach` 가 채우던
   `research` 칸을 읽는다. **그 칸이 사라진 것을 1-b 는 모른다.**

### 결과 — 자료10 발동 조건의 절반이 죽었다

```python
async def attach_material10(pool, redis, jg):
    needed = any(needs_innings_profile(jg, sd) for sd in ("home","away"))   # ① 살아 있다
    gaps = [form_gap(jg, sd) for sd in ("home","away")]                     # ② 항상 [None, None]
    needed = needed or any(g is not None and g >= thr for g in gaps)
```
`build_material10` 도 마찬가지다:
```python
gap = form_gap(jg, side)
if gap is not None and gap >= thr:
    blk["부진후회귀"] = {...}          # ← 도달 불가
```

**자료10 은 "이닝분포"(표본 부재형) 하나로만 돈다.** 프롬프트는 두 축을
설명하고 있다:
```
`부진후회귀`: 같은 리그에서 직전 3등판이 부진했던 선발의 **다음 등판**
  평균 이닝·실점과 표본 수. `주의`에 "참조 불충분"이 있으면 …
```
판정은 존재하지 않는 칸의 사용법을 매번 읽는다.

그리고 `regression_reference`(SQL 윈도 함수로 리그 회귀를 계산하는 함수)는
**한 번도 호출되지 않는다.**

## 🔴 NPB-1 [중] `BANNED_KEYS` 를 손으로 베껴 두 개가 갈렸다

```python
# app/collectors/last3.py:5  (원본)
BANNED_KEYS = ("era","era_season","xwoba","woba","ops","obp","siera","xfip")

# app/collectors/npb_form.py:merge_into_research  (사본)
banned = ("era","era_season","xwoba","woba","ops","obp")      ← siera·xfip 없음
```
KBO(`kbo_usage.summarize`)는 원본 `strip_banned` 를 부르고, NPB 만 사본을
쓴다. 지금 Yahoo 가 siera·xfip 를 주지 않아 무해하지만, 같은 파일 안에
원본이 있는데 손으로 다시 적은 자리다.

## 🔴 PROV-1 [중] 게이트 ③ 은 야구에서 **대조할 상대가 없다**

운영 실측(MLB 2경기):
```
라벨 분포: {'확정': 30, '교차': 0, '단일': 12, '미확인': 0, '모순': 0, '대조됨': 0}
라벨 분포: {'확정': 30, '교차': 0, '단일': 17, '미확인': 0, '모순': 0, '대조됨': 0}
```
`대조됨`(2개 이상 소스가 본 값) = **0**. `모순` 도 0 이다.

파이프라인이 이것을 이미 구조로 인정해 두었다:
```python
# MLB·KBE·NPB는 공식 1소스다. 대조됨=0은 교차검증 실패가 아니라 구조다
_one_axis = sport in ("mlb", "kbo", "npb")
```
정직한 처리다. 다만 그 뜻은 **야구에서 게이트 ③은 라벨을 붙일 뿐 아무것도
거르지 않는다**는 것이다. `strip_unusable` 이 뺄 수 있는 것은 `미확인`·`모순`
인데 둘 다 0 이다. 모듈이 스스로 적은 경고가 그대로 성립한다:
> **단일이 압도적이면 교차검증이 실질적으로 작동하지 않는다는 신호다** —
> 소스가 사실상 하나뿐이라는 뜻이고, **그 소스가 틀리면 걸러낼 방법이 없다.**

## ✅ PROV-2 정상 — 모순에 **다수결을 쓰지 않는다**

```
⚠️ **모순에 다수결을 쓰지 않는다.** 오래된 소스 둘이 신선한 소스 하나를 이기게
   되고, 그것이 정확히 우리가 피하려는 실패다(선발이 경기 30분 전에 바뀌었는데
   낡은 기사 둘이 이겨서 옛 선발로 판정하는 상황).
   → 수집 시각을 비교해 신선한 쪽을 채택한다. 단, 시각 차가 작으면
     (`FRESHNESS_MARGIN` 이내) **어느 쪽도 믿지 않고 "모름"으로 버린다**
```
그리고 커뮤니티 관측을 검증 대상에서 **분리**한다 —
"신선하다는 이유만으로 목격담이 공식 발표를 이기면 안 된다."

## ✅ VR-3 정상 — 분위수를 **보간하지 않는다**

```python
def quantiles(vals):
    """p25/p50/p75. **보간하지 않는다** — 실제 등판 값 중 하나를 고른다.
    ⚠️ 보간하면 "실제로 던진 적 없는 이닝"이 참조가 된다. L1 사실 감시가
       그 값을 원문에서 못 찾아 환각으로 찍을 것이고, **그게 맞다.**"""
```
그리고 09-07 에 표본 하한을 붙이면서 **원시 배열은 남기고 추정만 지웠다**:
> `이닝` 배열은 사실이므로 그대로 남긴다 — 지우는 것은 추정뿐이다.

## ✅ NAV-1 정상 — 값이 같아도 **각인한다**

```python
# ⚠️ 값이 이미 같아도 **채운 목록에 넣는다.** 빼면 각인이 안 되고,
#    각인이 없으면 "두 소스가 일치했다"는 사실이 기록되지 않아
#    교차 라벨이 영원히 0%가 된다(실측 2026-08-27: 교차 0/405).
```
게이트 ③이 무엇을 필요로 하는지 이해하고 병합 쪽을 맞춘 사례다.

---

# 77차 — ⛔ **72차 LED-A·B·C 전면 정정** — 재판정 중복을 세었다

`app/engine/confidence.py` 를 읽다가 내 72차 측정이 틀렸다는 것을 알았다.
이 저장소가 **같은 실수를 이미 겪고 문서로 남겨 두었다**:

> ② 자기신고가 나쁘다는 근거도 확정되지 않았다. 절단을 바꾸면 방향이 뒤집힌다 —
>     134경기 전체    하 58.8%(17) > 중 53.9%(115)
>     100경기(시장O)  하 45.5%(11) < 중 52.9%( 87)
>   표본 11~17건으로는 방향조차 안 정해진다.
>   **"역정보"라고 단정했던 것을 여기 바로잡아 둔다.**
>                                        — `app/engine/confidence.py` 머리말

그리고 계획서(`agile-sparking-haven.md`)에도 같은 경고가 있다:
> ⚠️ 앞서 "시장과 동의하면 더 맞는다"고 보고했으나 **틀렸다.**
> **재판정 중복이 만든 착시**였고, 경기당 1행으로 접으니 차이가 사라진다.

## 무엇이 틀렸나

```
pick_ledger  전체 660행 · is_final 159행 · 고유 경기 149건
             → 경기당 평균 4.4행
```

`record_analysis` 는 판정이 바뀔 때마다 옛 행을 `is_final=false` 로 내리고
새 행을 넣는다. **재판정을 많이 받은 경기가 그만큼 여러 번 세어진다.**

재판정 횟수 분포(is_final 기준):
```
0회 11 · 1회 29 · 2회 41 · 3회 28 · 4회 20 · 5회 14 · 6회 4 · 7회 4
10회 1 · 11회 1 · 12회 2 · 13회 1 · 14회 2 · 16회 1
```
16번 재판정된 경기 하나가 17행으로 들어간다. 이것은 무작위 잡음이 아니라
**체계적 가중**이다 — 재판정이 잦은 경기(라인업이 자주 바뀐 경기)가
평균을 지배한다.

## 다시 잰 값 (`is_final` 만, 채점 144경기)

| | 전 행(틀림) | **is_final(맞음)** |
|---|---|---|
| 보드만 | 244/466 **52.4%** | 61/103 **59.2%** |
| 거부권탈락 | 50/80 **62.5%** | 13/20 **65.0%** |
| 추천 | 19/37 **51.4%** | **5/16 = 31.3%** |
| 가치주의 | 6/15 **40.0%** | 1/5 **20.0%** |
| 확신도 상 | 4/9 44.4% | 1/2 50.0% |
| 확신도 중 | 265/509 52.1% | 66/122 54.1% |
| 확신도 하 | 50/80 62.5% | 13/20 65.0% |
| KBO | 92/158 58.2% | **16/29 55.2%** |
| MLB | 181/327 55.4% | **55/94 58.5%** |
| NPB | 46/113 40.7% | **9/21 42.9%** |

## 정정 후에도 남는 것 · 사라지는 것

### 남는 것 (방향이 오히려 강해졌다)
- **추천이 가장 못 맞는다.** 5/16 = **31.3%**. 전 행 기준(51.4%)보다 더 나쁘다.
  보드만(59.2%)·거부권탈락(65.0%) 어느 쪽보다도 낮다.
- **거부권탈락이 가장 잘 맞는다.** 13/20 = 65.0%.
- MLB 58.5%(n=94)는 목표 구간(58~60%) 안이다. 여기는 정상이다.

### 사라지는 것 (표본이 근거가 되지 못한다)
- **추천 n=16 · 거부권탈락 n=20 · 가치주의 n=5.**
  이항검정으로 추천 5/16 이 p=0.5 아래일 확률은 약 10.5% — **우연을 못 배제한다.**
  내가 72차에서 "n=80 이면 우연이 아니다"라고 쓴 것은 **중복을 센 n** 이었다.
- **NPB 추천 0/4.** 72차에서 "10건 중 1건"이라고 쓴 것은 중복이다. 실제는
  **4건 중 0건** — 방향은 같지만 표본이 근거가 안 된다.
- 리그 전체도 NPB n=21 이다. "동전던지기보다 낮다"를 단정할 수 없다.

### LED-C(09-07 추천 0건)는 **그대로 성립한다**
`is_final` 기준 날짜별:
```
09-01 추천 3 · 09-02 추천 1 · 09-03 추천 4 · 09-04 추천 2
09-05 추천 3 · 09-06 추천 2 · 09-07 추천 0 · 가치주의 0
```
09-07 만 0 이다. (다만 그날 `is_final` 총 11건이라 슬레이트 자체가 작다 —
"0건"의 무게가 72차에서 쓴 것보다 가볍다.)

## 🔴 LED-F [중] `is_final` 이 **경기당 하나가 아니다** — 10경기가 2행

```sql
SELECT game_id, count(*) FROM pick_ledger WHERE is_final GROUP BY 1 HAVING count(*)>1
```
```
1855(09-01,09-02) · 1857 · 1853 · 2224(09-02,09-03) · 2888(09-04,09-05)
2889 · 2892 · 3238 · 3242(09-05,09-06) · 3722          — 10경기
```
전부 **인접한 두 날짜**다. 원인은 유니크 키에 `date` 가 들어 있기 때문이다:
```sql
WHERE game_id = $1 AND date = $2 AND is_final FOR UPDATE
```
슬레이트 날짜가 자정을 넘겨 바뀌면(MLB 는 ET, KBO·NPB 는 KST — 그리고
`analysis.get("date")` 가 회차마다 다를 수 있다) **같은 경기가 두 날짜로
갈려 각각 `is_final` 을 갖는다.**

159 `is_final` 행 / 149 고유 경기 = 10건 초과. 채점·캘리브레이션이
그 10경기를 두 번 센다.

## 내가 배운 것 — 그리고 이 저장소가 이미 알고 있던 것

72차에서 나는 "n=80 이면 우연이 아니다"라고 썼다. **그 80은 경기가 아니라
행이었다.** 원장이 이력 테이블이라는 사실을 알고도(`is_final`·`rejudge_count`
컬럼을 직접 읽었으면서) 집계에 반영하지 않았다.

CLAUDE.md 가 적어 둔 순서를 건너뛴 것이다 —
> 1. **해당 코드 본문을 연다.** 함수 시그니처·반환 키·컬럼명은 추측하지 않는다.

`record_analysis` 를 먼저 읽었으면 첫 쿼리에 `WHERE is_final` 이 들어갔을 것이다.

## ✅ CONF-1 정상 — 이 모듈은 **결론을 미루기로 한 기록**이다

`confidence.py` 는 사용자 승인까지 받은 교체를 **배포 전 관문에서 스스로
떨어뜨렸다.**

```
처음 설계한 재료-결측 방식은 57경기 **전부 `상`** 이 나와 변별력이 0이었고,
그대로 넣으면 거부권이 11건 → 0건으로 사라진다.
```

그리고 세 가지 이유로 판단을 2주 뒤로 미뤘다:
```
① 검증한 값이 게이트가 보는 값이 아니다 (CLOSE 백필 vs SEND)
② 자기신고가 나쁘다는 근거도 확정되지 않았다 (절단을 바꾸면 방향이 뒤집힌다)
③ 오늘 하루에 시장 적재·변수 해결·grok 대체가 다 들어갔다. 게이트까지
   얹으면 내일부터의 변화를 어느 것에도 귀속시킬 수 없다.
→ **2주 뒤 SEND 데이터 50~100경기로 결정한다.**
```

`by_market` 의 주석도 정확하다:
```python
🔴 수집 실패가 거부권이 되면 안 된다. 실측 2026-09-07: 시장 미수집
   34경기는 오히려 **61.8%** 로 가장 잘 맞았다. `None` 을 `하` 로
   읽는 호출자는 그 34경기를 통째로 버리게 된다.
```

그리고 변별력이 없다고 판명된 축(`by_materials`)을 **지우지 않고 남겼다**:
> 남겨 두는 것은 "안 되더라"를 계속 확인하기 위해서다 — 지우면 그 사실도 사라진다.

`material_gaps` 는 재료 목록을 손으로 적지 않고 **판정 조립 함수를 부른다**
(`boxscore_payload`·`lineups_payload`·`bullpen_payload`) —
"사본은 원본이 바뀔 때 따라가지 않고, 그 순간 이 기록이 거짓말이 된다."

---

# 78차 — CR-1 **운영 캐시에서 직접 확인** · NPB 수집기 통독

읽은 것: `yahoo_npb.py`(780) `bullpen_recent.py`(163) — 943줄.

## 🔴🔴🔴 CR-1 최종 — 자료9 **8/8 블록 전부**가 시즌 값을 싣고 있다

운영 `analysis:mlb:2026-09-07` 의 `research.{side}_bullpen` 전수:

```
자료9 블록 8개 · 키별 출현:
  최근3경기 8 · 가용성 8          ← bullpen_recent 가 만든 것(대원칙 준수)
  era 8 · whip 8 · k9 8 · bb9 8   ← **시즌 팀 투수 지표. 8/8 전부**
  fip 3 · ip_last3d 4 · closer_available 4   ← 딥서치가 준 것

  game=4099 home era=3.91 whip=1.29    away era=4.70 whip=1.39
  game=4100 home era=4.39 whip=1.36    away era=4.32 whip=1.35   (fip 4.18/4.31)
  game=4101 home era=3.70 whip=1.17    away era=4.68 whip=1.43
  game=4102 home era=5.40 whip=1.49    away era=3.92 whip=1.30   ← 내가 재현한 값과 일치
```

`game=4102 home era=5.40` 은 67차에서 두 `attach` 를 코드 순서대로 돌려
얻은 값과 **정확히 같다**(Toronto @ Athletics, 5.40 / 3.92).
재현이 아니라 **운영이 실제로 그렇게 돌고 있다.**

> ⚠️ 67차에서 나는 "운영 캐시에는 era 가 없다"고 한 번 적었다. 출력 300자
> 절단에 잘린 것이었다 — `dst.update(blk)` 로 최근3경기·가용성이 뒤에 붙고
> era 는 그보다 뒤에 있었다. **잘린 출력을 부재로 읽었다.**

### 그리고 새는 키가 넷이 아니라 다섯이다

```python
# bullpen_recent.attach
for stale in ("era", "whip", "k9", "bb9"):
    dst.pop(stale, None)
```
`fip` 은 **목록에 없다.** 딥서치 스키마가 `home_bullpen.fip` 를 요구하고
(`_SCHEMA_MLB`), `validate` 가 그것을 통과시키며, `bullpen_recent` 가 지우지
않는다. 운영 3블록에 시즌 FIP 가 실려 있다.

`ip_last3d`·`closer_available` 은 최근 3일 값이므로 대원칙에 맞다 — 남는 게 맞다.

### 프롬프트가 이 블록을 뭐라고 부르는지

```
prompts.py:83   9. 양팀 불펜 — **최근 폼만** (없으면 빈 객체): {{BULLPEN_JSON}}
```

## 🔴 NPB-2 [중] `roster` 문자열도 지우지 않는다 — NPB 자료9의 시즌 ERA 경로

```python
# yahoo_npb.merge_into_research
blk["roster"] = ", ".join(
    f"{x['name']}({x['era']:.2f}" + (f"·{x['condition']}" if …) + ")"
    for x in pen if x.get("era") is not None)[:400]
```
`x['era']` 는 야후 불펜표의 **시즌 방어율**이다. 결과는
`"清水 昇(2.16·매우 나쁨), 田口 麗斗(3.40·보통), …"` 같은 400자 문자열이고,
`bullpen_recent` 의 pop 목록(`era·whip·k9·bb9`)에 `roster` 가 없으므로
**그대로 자료9 에 실린다.**

⚠️ 지금 NPB 캐시가 비어 있어(`yahoo_npb:*` 0건, 월요일 휴식) 실측으로 확인하지
못했다. 코드 경로는 위와 같다.

그리고 `matchup.bullpen_payload` 는 블록을 **통째로** 넘긴다:
```python
blk = r.get(f"{side}_bullpen") or {}
if blk: out[side] = blk        # 키를 고르지 않는다
```
자료9 에 무엇이 실리는지는 **아무도 화이트리스트로 관리하지 않는다.**
`bullpen_recent` 의 블랙리스트 네 칸이 유일한 방어이고, 그것은 새 키가
생길 때마다 뒤처진다.

## ✅ YN-1 정상 — "시각이 없다 ≠ 예정"을 원문으로 증명했다

```python
#   실조회 2026-09-06 원문:
#     '甲子園 阪神 DeNA 1 - 4 試合終了 …'                → 종료
#     'エスコンF ライブ配信中 日本ハム ロッテ 0 - 2 1回表'  → 진행
#     '神宮 ヤクルト 中日 - 試合中止'                      → 중지
#     '神宮 ヤクルト 巨人 18:00'                          → 예정
_STARTED_MARKS = ("試合終了", "ライブ配信中", "回表", "回裏", "試合中")
```
> 🔴 [2026-09-07 실사고] 시각이 없다는 것은 "18:00 예정"이 아니라
> **"이미 시작했다"** 는 뜻이다. … 토요일 13:00 에 끝난 롯데@오릭스·
> 세이부@소프트뱅크가 "오늘 18:00 예정"으로 슬레이트에 들어와
> 판정·타순까지 만들어졌다.

그러면서 **타임스탬프 폴백은 남겼다** — "시각을 못 읽는다고 결과를 잃지
않는다"(`game_match.MATCH_WINDOW_HOURS = 20`). 상태와 시각을 분리해 다뤘다.

## ✅ YN-2 정상 — 1등판 ERA 189.00 을 **대체하지 않고 버린다**

```python
MIN_STARTER_APPEARANCES = 3
MAX_CREDIBLE_ERA = 15.0
#   실측(2026-08-26): 齋藤 響介가 **1등판 ERA 189.00**이었다.
#   0이닝대 대량 실점이면 산술적으로 이런 값이 나온다 — 데이터는 맞지만
#   λ의 선발 억제 계수에 넣으면 그 경기가 통째로 망가진다.
#   → 등판 수가 이 값 미만이면 `era_season`을 **버린다**(리그 평균으로
#     대체하지도 않는다. 없는 것을 있는 척하지 않는다).
```
"데이터는 맞지만 쓸 수 없다"를 구분했고, 대체값을 만들지 않았다.

## ✅ YN-3 정상 — 두 구조를 **둘 다** 지원한다

```python
⚠️ 실사고(2026-08-26): 종료 경기 구조만 보고 파서를 만들었더니 **오늘 경기
   6건이 전부 파싱 실패**했다. 경기 전에는 `予告先発` 블록이고, 종료 후에는
   `投手|位置|選手名|投|防御率|調子` 표다.
   → **개발 중 본 한 페이지가 전부라고 가정하면 안 된다.**
```
그리고 표 순서가 소스마다 반대라는 것까지 실측으로 못박았다 —
`/top` 打順은 홈 먼저, `/stats` 투수표는 원정 먼저. "섞지 않는다."

## 🔴 YN-4 [하] `_SCORE_RE` 가 **한 파일에서 두 번 정의**된다

```python
yahoo_npb.py:121   _SCORE_RE = re.compile(r"\d+\s*-\s*\d+")        ← _state_of 용
yahoo_npb.py:475   _SCORE_RE = re.compile(r"(\d+)\s*-\s*(\d+)")    ← parse_finals 용
```
뒤가 앞을 가린다. `_state_of` 는 `.search()` 만 쓰므로 지금은 동작이 같다.
그러나 **위쪽 정의는 죽은 코드**이고, 아래 패턴을 고치는 사람은
`_state_of` 가 같이 바뀐다는 것을 모른다.

## 🔴 BP-1 [중] `bullpen_recent` 의 방어가 **블랙리스트**다

```python
for stale in ("era", "whip", "k9", "bb9"):
    dst.pop(stale, None)
```
자료9 에 무엇이 들어가도 되는지는 **화이트리스트로 정의돼 있지 않다.**
새 소스가 새 키를 넣으면(딥서치 `fip`·야후 `roster`·`condition`) 조용히
프롬프트로 흘러간다. 대원칙("시즌 누적 금지")을 지키는 유일한 장치가
네 단어짜리 튜플이다.

`matchup.bullpen_payload` 가 블록을 통째로 넘기므로, **자료9 의 계약이
코드 어디에도 없다.**

---

# 79차 — ⛔ 72차·77차는 **이미 있는 문서를 다시 만든 것**이었다

`docs/ACCURACY_2026-09-07.md`(커밋 `21e84d2`, 로컬 최신)를 읽었다.
**내가 72~77차에서 도달한 결론이 거기 더 정확하게, 더 큰 표본으로,
더 깊은 인과와 함께 이미 적혀 있다.**

## 문서가 이미 갖고 있던 것

```
> 표본: 채점 완료 **134경기**(08-30~09-06). 재판정으로 부푼 621행을
> **경기당 1행**으로 접었다 — 접지 않으면 한 경기가 최대 4.3번 세어진다.
```

내가 77차에서 "정정"으로 발견한 방법론이 문서의 **첫 문단**이다.

### 게이트 역선택 — 같은 결론, 더 정확한 값

| | 문서(n=134) | 내 측정(is_final, n=144) |
|---|---|---|
| 보드만 | 57/97 **58.8%** | 61/103 **59.2%** |
| 거부권탈락 | 10/17 **58.8%** | 13/20 **65.0%** |
| 추천 | 5/15 **33.3%** | 5/16 **31.3%** |
| 가치주의 | 1/5 **20.0%** | 1/5 **20.0%** |

거의 같다. 다만 문서는 **왜 그런지**까지 갔고 나는 못 갔다.

### 문서가 찾은 인과 — 내가 못 찾은 것

```
확률 문턱 탓이 아니다. **같은 확률대(우세 p≥0.58) 안에서** 갈라보면:
  p≥0.58 전체      38/65 = 58.5%
    그중 추천        5/13 = 38.5%
    그중 추천 아님  33/52 = 63.5%

추천은 **라인업 확정**을 요구하고, 확정 후 판정이 나빠진다.
  mlb  확정 55.6%(72) vs 예상 66.7%(12)
  kbo  확정 42.1%(19) vs 미수집 80.0%(10)
```

**추천이 못 맞는 이유는 확률 게이트가 아니라 라인업 확정 요구다.**
확정 라인업을 받고 재판정하면 판정이 나빠진다. 나는 "게이트가 거꾸로 돈다"
까지만 갔고 그 원인을 찾지 못했다.

### 재판정이 판정을 나쁘게 만든다 — 나는 재지 않았다

```
판정이 실제로 움직인 89경기
  첫 판정   50/89 = 56.2%  Brier 0.2470
  최종 판정 49/89 = 55.1%  Brier 0.2496

방향 뒤집기 11건 중 5건 적중 (45.5%) — 동전던지기
확신 강화 44건 → 50.0% · 확신 약화 34건 → 64.7%
라인업 미확정→확정 80경기: Brier 0.2478 → 0.2528
```

### 확률의 크기에 정보가 없다 — 나는 재지 않았다

```
Brier    우리 0.2523 · 상수(기저) 0.2498 · 시장 0.2422
logloss  우리 0.6978 · 상수 0.6927      · 시장 0.6776
```
**상수보다 나쁘다.** "홈 48.5%"를 전 경기에 똑같이 적는 것이 우리 확률보다 낫다.
최적 수축 k=0.4 — 벌어짐의 60%가 잡음이다. 우리 sd 0.091 > 시장 sd 0.082 —
"**시장보다 더 자신 있게 말하면서 덜 맞는다.**"

### 유료 최종의 값어치 — 나는 재지 않았다

```
무료 예비(gemini)  10/15 = 66.7% · Brier 0.2487
유료 확정(opus)    10/15 = 66.7% · Brier 0.2639
```

### 그리고 문서가 스스로 건 제동

```
## 6. 🔴 그런데 — 이 표본은 처방 이전이다
자료12 실력 레이팅 배포  2026-09-07 00:18 UTC
마지막 판정              2026-09-07 00:02 UTC   ← 배포 16분 전
배포 이후 판정된 경기     0건
```
> ⚠️ 오늘 캐시에서 "elo 1/15"를 보고 **"자료12가 안 돌고 있다"고 잘못
> 보고했다.** 원인은 배포 이후 판정된 슬레이트가 없어서였다.

```
## 7. 권고 — 지금은 아무것도 바꾸지 않는다
내일 09-08 KBO 18:30 이 자료12·자료14·시장 원장이 **처음으로 실제 판정에
들어가는** 슬레이트다. 여기서 게이트를 만지면 내일부터의 변화를 무엇에도
귀속시킬 수 없다.
```

## 내 감사가 실제로 더한 것

문서가 이미 다룬 것을 빼면, 이 감사가 새로 낸 것은 **판정 품질이 아니라
배선·계약 쪽**이다:

| # | 발견 | 문서에 있었나 |
|---|---|---|
| CR-1 | 자료9 8/8 블록이 시즌 ERA·WHIP·K9·BB9 를 싣는다 (운영 재현+캐시 확인) | ❌ |
| VR-1 | `opp_starter_season_era` 12/12 null — `ERA` vs `era` | ❌ |
| VR-2 | 자료10 "부진후회귀" 축 도달 불가 · `regression_reference` 미호출 | ❌ |
| STC-1 | 애리조나가 Statcast 에서 통째로 빠짐 (`AZ` vs `ARI`, 25경기) | ❌ |
| SAN-2 | 봇 버튼이 자료1·3·4·6 을 지우고 공유 캐시에 저장 | ❌ |
| PGP-2 | "판정 불가 카드"가 5일 전 죽은 함수 안에 추가됨 (발송 0건) | ❌ |
| LI-1 | 라인업 의도 변경점 **39.7% 유실** (유형 키 충돌 ×2) | ❌ |
| DSP-1 | 발송률이 구조적으로 100% 불가 (`card_cap` 을 미발송으로 셈) | ❌ |
| RES-1 | 딥서치 무효율 60%(09-06)·46.7%(09-07) — 경고선 30% | ❌ |
| LLM-5 | `free_judge_model` 후보가 **1개** (설계 주석과 정반대) | ❌ |
| ENV-1 | `RUN_PREFETCH_ASIA=1` 이 배포마다 전체 프리페치 | ❌ |
| SCH-2 | `lineup_poll_30m` 이 5분·2분 잡과 겹쳐 돈다 | ❌ |
| SCH-3 | "1회성" 코드 넷이 재배포마다 동시 기동 (30h 축구 프로브 포함) | ❌ |
| BOT-1 | 폴링 워치독이 자기가 잡으려는 고장을 못 잡는다 | ❌ |
| WD-1 | 경보 코드 목록이 **네 벌**, 넷 다 다름 (2개는 라벨 없음) | ❌ |
| DEP-1~3 | 스케줄러 우선 배포 미보장 · `cmd` 미전달 · startCommand 저장소 밖 | ❌ |
| ORP-1 | `glass_report` 508줄 호출부 0 · `W-TRACE` 존재하지 않음 | ❌ |
| BP-1 | 자료9 의 계약이 네 단어 블랙리스트뿐 | ❌ |
| LED-C | 09-07 추천 0건 | ❌ (문서 작성 시점 이후) |
| LED-F | `is_final` 이 10경기에서 2행 | ❌ |
| SEC-1 | 유출 키가 Redis 에 211행 · TTL 14일 · 아직 회전 안 됨 | 로그만 알려져 있었음 |

판정 품질(적중률·Brier·게이트 역선택)은 **내가 다시 잰 것이지 새로 찾은 것이
아니다.** 그리고 내 것이 더 거칠었다.

## 🔴 그래도 남는 질문 — 문서의 §7 이 지켜지지 않았다

```
## 7. 권고 — 지금은 아무것도 바꾸지 않는다
```
이 문서가 커밋 `21e84d2` 다. 그런데 그 앞 커밋들(`5681c8f`·`92b31a0`·
`cff9a93`·`7c0f9be`)이 **같은 날 판정 입력을 여러 번 바꿨다**(74차 DISC-1).
그리고 `21e84d2` 는 **아직 배포되지 않았다** — 운영은 `7c0f9be` 다.

즉 "아무것도 바꾸지 않는다"고 쓴 문서는 이미 여러 변경이 배포된 **뒤**에
쓰였고, 그 자신은 배포되지 않았다.

## ✅ SMOKE-1 정상 — `smoke_e2e.py` 가 이 감사와 같은 진단에 도달했다

```
🔴 왜 (2026-09-07 사용자 지시): "구현돼 있다"를 코드 존재로 주장해 왔다.
   0단계 감사에서 실제로 드러난 것 —
     · 감시 L2·L3 가 **전 기간 0행**이었다.
     · `lineups` 표에 MLB 558행뿐, KBO·NPB 0행이었다.
     · 타순 0명인데 `confirmed` 로 올라가 유료 최종이 재료 없이 나갔다.
   셋 다 코드는 있었다. **돌려보지 않아서 몰랐다.**
```
그리고 10단계를 경기 1건마다 PASS/FAIL 로 판정하는 하네스를 만들었다.
격리는 `tools/rehearsal` 것을 재사용한다 — "두 벌 만들면 한 벌이 샌다."

## ✅ SS-1 정상 — 배포 게이트가 **조용히 SKIP 되던 것**을 잡았다

```python
# 🔴 [2026-09-07] 종전에는 주전이 유료면 **그냥 넘어갔다.** v1.4 로
#    2차 최종이 Opus 가 된 뒤로 이 게이트는 매 배포마다 SKIP 이었다 —
#    **게이트 하나가 조용히 사라진 상태였다.**
#    이제 유료면 **1차 예비 사슬(무료)** 로 잰다.
```
설정 변경(`JUDGE_PROVIDER=anthropic`)이 **다른 곳의 게이트를 껐다**는 것을
찾아낸 사례다. 이 감사에서 내가 여러 번 본 패턴(한쪽만 바뀌고 다른 쪽이
따라가지 않음)의 반대 — 따라가지 않은 쪽을 찾아 고쳤다.

---

# 80차 — 문서가 코드보다 뒤처진 자리 전수

읽은 것: `docs/DATAFLOW.md`(134) `app/engine/CLAUDE.md`(120)
`docs/SMOKE_E2E_2026-09-07.md`(86) `docs/ACCURACY_2026-09-07.md`(162)
`tools/stability_smoke.py`·`smoke_e2e.py` 머리부 · `game_match.py`(166)
`lineup_history.py`(159) — 약 850줄.

## 🔴🔴 DOC-1 [상] `DATAFLOW.md` 가 **없는 모듈·폐지된 자료·틀린 기본값**을 가리킨다

| 문서 문장 | 실제 |
|---|---|
| `collectors/mlb.py · kbo.py · **npb.py**` | **`app/collectors/npb.py` 는 없다.** NPB 는 `yahoo_npb.py`·`npb_stats.py`·`npb_form.py`·`npb_boxscore.py` 넷으로 갈려 있다 |
| ② 재료 조립: "자료1 … **8 타선 시즌** · 9 불펜" | **자료8 은 2026-09-04 폐지.** 그리고 자료10·11·12·14 가 목록에 없다 |
| ③ 판정: `MODEL_MATCHUP`(**기본 `claude-sonnet-5`**) | 운영 `claude-opus-5`. v1.4(09-07)에서 바뀌었다 |
| ④ 게이트: `engine/value_gate.py` · **`engine/market_edge.py`** | `market_edge.py` 는 **참조 0** — 테스트에서만 불린다(ORP-2) |
| 계측 M-2: "**자료8** 주입률" | 2026-09-04 에 **자료3(타순 9명)** 으로 옮겼다 — `monitor_metrics.note_materials` 주석이 그 사실을 적어 놓았다 |
| 선발 시즌 라인 `starter_season.py` 3리그 전부 | `attach` 호출은 2026-09-04 에 삭제됐다. 남은 사용처는 `variable_ref` 하나이고 그것도 키 오류로 죽어 있다(VR-1) |

DATAFLOW.md 는 **"어느 숫자가 어디서 와서 어디로 갔는가의 지도"** 를 자처한다.
지도의 여섯 칸이 현재 지형과 다르다.

⚠️ 다만 이 문서는 **자기가 사본이 되지 않으려고** 애쓴 흔적이 뚜렷하다:
```
⚠️ **주기를 이 표에 적지 않는다.** 트리거 객체(`_JOB_TRIGGERS`)가 원본이다 —
   여기 옮겨 적는 순간 사본이 되고, 사본이 어긋나면 워치독이 오탐을 낸다
```
주기는 안 적었는데 **모듈명·자료 목록·기본 모델명은 적었고**, 그것들이 어긋났다.

## 🔴🔴 FRZ-2 [상] "마지막 재시작"이라고 잠근 뒤 **또 재시작했다**

`app/engine/CLAUDE.md`:
```
카운터는 일일 요약의 `N/50` 줄에서 본다. `FREEZE_RESTART_IS_FINAL = True` —
**표본 재시작은 2026-09-05 슬레이트가 마지막이다.**
```

`app/engine/daily_summary.py` 실제 상수:
```python
FREEZE_START_DEFAULT = "2026-09-07"          ← 09-05 가 아니라 09-07
FREEZE_RESTART_REASON = "실력 축 복원(620행 분석 근거)"
#   ⚠️ 이것이 **마지막 재시작이다** — 아래 `FREEZE_RESTART_IS_FINAL` 이 잠근다.
FREEZE_RESTART_IS_FINAL = True
```

**같은 플래그가 두 번 "마지막"을 선언했다.** 09-05 에 한 번, 09-07 에 또 한 번.
그리고 `FREEZE_RESTART_IS_FINAL` 을 **읽는 코드가 없다**(38차에서 확인).
잠그는 척하는 상수다.

동결 기간을 다시 세면:
```
v1.3 동결 2026-09-03 → v1.4 동결 2026-09-05 → 표본 재시작 2026-09-07
해제 조건: 리그별 graded 50건
현재:      kbo 0 · mlb 0 · npb 0  (09-07 재시작 이후)
5일 동안 재시작 3회 · 폐기된 graded 누적 146건
```

## 🔴 FRZ-3 [중] 동결 선언이 **자료12·14 를 포함하지 않는다**

`app/engine/CLAUDE.md`:
```
동결 대상: **자료 1~11** 의 구성 · 판정 프롬프트 문구 · 확률 게이트 · 클립 ·
가치 게이트 · 트리거 정의 · 변수 대장의 축 구성과 prior 헤더 · 조정 폭 · 상한
```
자료12(ELO)·자료14(분기점)는 동결 뒤에 추가됐고 **목록에 없다.**
그래서 형식상 그 둘은 언제든 바꿔도 동결 위반이 아니다 — 그리고 실제로
09-07 에 자료14 가 두 번 바뀌었다(`558a00d` 신설 · `92b31a0` 지시어 해결).

동결의 목적("표본 50건을 같은 조건에서 모은다")에 비추면 자료12·14 야말로
**가장 최근에 들어온 변수**라 동결이 필요한 쪽이다.

## ✅ ECL-1 정상 — 대원칙 개정이 **경계선을 정의했다**

```
### 개정 (2026-09-07) — 실력 레이팅은 집계표가 아니다
⚠️ **경계선은 "집계표냐 상태값이냐"다.** 팀당 숫자 하나로 매 경기 갱신되면
   자료12 이고, 시즌 타율·ERA·좌우 스플릿·통산·상대전적은 여전히 금지다.
   **레이팅 옆에 집계표를 얹는 순간 위반이다.**
```
그리고 개정 근거를 상관계수로 남겼다:
```
시장 p ↔ 시즌 실력 r=+0.707 · 우리 p ↔ r=+0.279
괴리 ↔ 최근5 r=+0.099 ≈ 0 · 괴리 ↔ 시즌 실력 r=−0.408
→ 괴리는 "최근 폼을 본다"가 아니라 **"실력을 안 본다"** 였다.
```
예외를 만들면서 **예외의 경계와 근거를 함께** 적었고, 되살리지 않을 것
(자료7·8)을 명시적으로 잠갔다(`tests/test_season_ban.py`).

⚠️ 다만 이 개정이 CR-1 을 막지 못했다 — 자료9 에 **시즌 팀 투수 ERA 집계표**가
그대로 들어가고 있다. 경계선은 정의됐는데 **자료9 를 지키는 장치는
네 단어 블랙리스트뿐**이다(BP-1).

## ✅ ECL-2 정상 — 대체 못 한 것을 **못 했다고 적었다**

```
⚠️ **대체는 아직 못 했다.** 최근 5경기 타격은 MLB(statsapi `lastXGames`)만
   되고 KBO·NPB 는 경로가 없다. **경로가 생길 때 3리그 동시**에 넣는다.
```
자료8 을 폐지하면서 그 자리를 무엇으로 메울지, 왜 아직 못 메웠는지,
언제 메울지를 함께 적었다.

## ✅ GM-1 정상 — 새 표를 만들면 **이관 목록에 넣으라**고 못박았다

```python
# 🔴 pick_ledger도 옮긴다. 빠뜨리면 DELETE FROM games 의 ON DELETE CASCADE가
#    판정 기록을 **조용히 지운다** (실측 재현 2026-08-31: 병합 1건에 레저 1행 소멸).
#    2026-08-27에 predictions를 이관 대상에 넣었을 때 같은 이유였다 —
#    **새 표를 만들면 이 목록에 반드시 추가한다.**
```
그리고 유니크 인덱스 충돌을 **지우지 않고 이력으로 낮춰** 보존한다:
> 판정 기록을 지우지 않는 것이 이 표의 존재 이유다. 병합 출처는
> `merged_from` 에 남겨, 나중에 "이 이력 행이 재판정인지 병합인지"를
> 되물을 수 있게 한다.

⚠️ 그런데 `merge_duplicate_games` 는 `lineup_events`·`judgement_audit`·
`game_trace`·`variable_ledger`·`market_baseline_ledger`·`lineup_verdicts`·
`cell_verdicts` 는 **이관 목록에 없다.** 스스로 정한 규칙("새 표를 만들면
반드시 추가한다")이 그 뒤 만들어진 표 일곱에 적용되지 않았다.
(`ON DELETE CASCADE` 여부는 `db/schema.sql` 미확인 — 확인 필요)

## ✅ LH-1 정상 — 같은 유형의 사고를 **경계에서 흡수**하기로 했다

```python
def _as_dt(v):
    """⚠️ 이 프로젝트에서 같은 유형의 사고가 세 번 났다(`$4::timestamptz` 캐스트,
       `apply_result`, 그리고 여기). **호출부마다 고치지 말고 경계에서 흡수**한다."""
```
세 번째에 패턴을 인식하고 구조로 옮겼다.

---

# 81차 — 🔴 중복 병합이 **9개 표를 조용히 지운다** (`pitcher_appearances` 포함)

## 🔴🔴🔴 GM-2 [최상] `merge_duplicate_games` 가 3개 표만 이관하는데 CASCADE 는 12개다

`db/schema.sql` 전수 파싱:

```
games 삭제 시 ON DELETE CASCADE 로 함께 지워지는 표 — 12개
  cell_verdicts · expert_picks · game_trace · lineup_events · lineup_verdicts
  lineups · market_baseline_ledger · odds_snapshots · pick_ledger
  pitcher_appearances · predictions · variable_ledger

merge_duplicate_games 가 이관하는 표 — 3개
  predictions · expert_picks · pick_ledger

→ 이관하지 않고 **DELETE 로 함께 사라지는 표 9개**
  cell_verdicts · game_trace · lineup_events · lineup_verdicts · lineups
  market_baseline_ledger · odds_snapshots · pitcher_appearances · variable_ledger
```

`merge_duplicate_games` 는 마지막에 이렇게 끝난다:
```python
await pool.execute("DELETE FROM games WHERE id = ANY($1::int[])", dups)
```

### 가장 무거운 것 — `pitcher_appearances`

그 표는 이 시스템의 **판정 재료 넷의 원천**이다:
```
자료4  선발 최근 등판      starter_recent._FETCH / _FETCH_RELIEF
자료9  불펜 최근 3경기·가용성  bullpen_recent._RECENT_RUNS / _CORE / _LAST3D
자료10 이닝 분포·부진후회귀   variable_ref._APPEARANCES / _REGRESSION
자료14 분기점 조사(3갈래)     branch_resolve._OWN / _TEAM / _PEERS / _BULLPEN_*
       투수 맞대결            pitcher_matchup._FETCH_TEAM
```
병합으로 그 경기 행이 지워지면 **그 등판이 모든 투수의 이력에서 영구히
사라진다.** 다음 날 그 투수의 "최근 5등판"은 4등판이 되고, 리그 표본
(`_PEERS`·`_REGRESSION`)도 그만큼 줄어든다. 어디에도 로그가 남지 않는다.

### 실측 — 31번 일어났다

```
pick_ledger.merged_from 있는 행 : 31
현재 남아 있는 중복 그룹        : mlb 31개
```
`merged_from` 31행은 **이미 31번 병합했다**는 뜻이고, 그런데도 지금 MLB 에
중복 그룹이 **또 31개** 있다. 모듈 주석이 그것을 예고했다:
> **한 번 고쳐두면 끝나는 문제가 아니다** — 소스가 늘어날 때마다 같은 경기가
> 다른 ext_id 로 다시 갈라질 수 있다.

`finals_job` 이 매일 13:00 KST 에 `merge_duplicate_games` 를 돈다.

### 그리고 이 규칙을 **자기가 적어 두었다**

```python
# 🔴 pick_ledger도 옮긴다. 빠뜨리면 DELETE FROM games 의 ON DELETE CASCADE가
#    판정 기록을 **조용히 지운다** (실측 재현 2026-08-31: 병합 1건에 레저 1행 소멸).
#    2026-08-27에 predictions를 이관 대상에 넣었을 때 같은 이유였다 —
#    **새 표를 만들면 이 목록에 반드시 추가한다.**
```

2026-08-27 에 `predictions` 를, 08-31 에 `pick_ledger` 를 추가하며 규칙을
못박았다. 그 뒤 만들어진 표 아홉 중 **하나도 추가되지 않았다.**
`lineup_events`(08-30) · `variable_ledger`(09-05) · `game_trace`(09-05) ·
`market_baseline_ledger`(09-04) · `lineup_verdicts`(09-01) — 전부 그 뒤다.

이 저장소의 지배적 실패 패턴의 **일곱 번째 사례**이고, 형태가 가장 나쁘다 —
**규칙을 문장으로 적어 두었는데 그 문장이 강제력이 없다.** 기계가 검사하지
않으므로(계약 테스트 없음) 새 표를 만드는 사람이 그 주석을 읽을 이유가 없다.

### 구조적 해법이 이미 스키마에 있다

`ON DELETE CASCADE` 대신 병합 시 `UPDATE ... SET game_id = keep` 를 도는
방법도 있지만, 더 단순한 것은 **표 목록을 코드가 아니라 `information_schema`
에서 읽는 것**이다 — 지금 내가 그렇게 세었다. 사본을 만들지 않는 방법이
이미 손에 있는데 쓰지 않았다.

## 🔴 GM-3 [중] 병합 기준이 **UTC 날짜**라 MLB 야간경기를 못 묶는다

```sql
SELECT sport, home, away,
       date_trunc('day', starts_at AT TIME ZONE 'UTC') AS d
  FROM games GROUP BY 1,2,3,4 HAVING count(*) > 1
```
같은 파일의 `apply_result` 는 정확히 그 위험을 알고 **시각 근접(±20h)** 으로
찾는다:
```python
⚠️ 날짜가 아니라 **시각 근접**으로 찾는다. UTC 날짜로 맞추면 MLB 야간경기가
   다음 날로 넘어가 못 찾는다(19:00 ET = 23:00 UTC, 서머타임에 따라 02:00 UTC).
```
**`merge_duplicate_games` 는 같은 함정에 그대로 빠져 있다.** 자정을 사이에 두고
갈린 중복(23:50 UTC vs 00:10 UTC)은 그룹이 나뉘어 영원히 병합되지 않는다.

같은 파일 안에서 한 함수는 알고 다른 함수는 모른다.

---

# 82차 — `DISCIPLINE.md` 통독 · **파라미터 이력이 09-02 에서 멈췄다**

읽은 것: `docs/DISCIPLINE.md`(443 전량).

## 🔴🔴 DISC-3 [상] 파라미터 변경 이력이 **09-02 이후 한 줄도 없다**

문서가 스스로 정한 규칙:
> ## 부록: 파라미터 변경 이력
> **변경할 때마다 여기에 한 줄 남긴다** — 되돌릴 때 무엇을 되돌려야 하는지가
> 남아야 한다.

표의 마지막 날짜:
```
2026-08-28 · 2026-08-29 · 2026-08-30 · 2026-09-01 · **2026-09-02**
```

그 뒤 5일간 실제로 바뀐 것(코드·env 실측):

| 파라미터 | 값 | 이력에 있나 |
|---|---|---|
| `matchup_max_tokens` | 4000 → **12000** | ❌ |
| `MODEL_MATCHUP` | `claude-sonnet-5` → **`claude-opus-5`** | ❌ |
| `JUDGE_PROVIDER` | (무료 전환) → **`anthropic`** | ❌ |
| `FREE_JUDGE_MODEL` | (여러 후보) → **`gemini/gemini-3.7-flash`** 1개 | ❌ |
| `market_agree_required` | (신설) → **True** | ❌ |
| `market_divergence_pp` | (신설) → **4.0** | ❌ |
| `anthropic_daily_cap` | 10 → **80** | ❌ |
| `RUN_PREFETCH_ASIA` | (신설) → **1** | ❌ |
| `SCOUT_XSEARCH_DAILY_CAP` | 12 → **30** | ❌ |
| `var_ref_*` 9종 · `branch_*` 4종 · `m1_opp_*` 2종 · `bullpen_*` 4종 · `shadow_*` 4종 | 전부 신설 | ❌ |

`HANDOFF_2026-09-07.md` 는 env 변경을 각주로만 적었다:
```
환경변수 변경(저장소 밖): `JUDGE_PROVIDER=anthropic` · `MODEL_MATCHUP=claude-opus-5` ·
`FREE_JUDGE_MODEL=gemini/gemini-3.7-flash` · `GROQ_API_KEY` 오염 정리.
```
전후값·이유·영향(문서가 요구하는 3종)은 없다.

**이 이력표는 이 저장소에서 가장 값진 문서다** — 어떤 값이 왜 바뀌었고 결과가
어땠는지가 ✅/❌로 다 적혀 있다. `JUDGE_MAX_TOKENS 16000→32000` 실패와 롤백이
같은 표에 나란히 있다. 그것이 09-02 에 멈췄다.

## 🔴 DISC-4 [중] §2-3 이 **폐지된 개정을 현행으로** 적고 있다

```
### 2-3. LLM 수치는 API와 교차검증
- 야구 판정 입력에 xwOBA를 넣지 않는다 (1-A-1). **시즌 ERA는 선발 표본 보정
  전용으로 2026-09-01 개정, 시즌 타격은 정식 근거로 2026-09-02 개정**
```
그 두 개정은 **2026-09-04 대원칙으로 되돌려졌다** — 자료7(선발 시즌)·자료8
(타선 시즌)이 폐지됐고, `app/engine/CLAUDE.md` 가 "자료7·8 을 되살리려면
대원칙을 먼저 고쳐야 한다"고 잠갔다.

같은 표의 마지막 두 행도 그렇다:
```
| 2026-09-02 | 규율 개정 — "타선·팀의 시즌 지표 금지" | 금지 → **해제** …
| 2026-09-01 | 규율 개정 — "시즌 ERA/xwOBA 금지" | 전면 금지 → **선발 시즌 라인 허용** …
```
09-04 개정이 이 둘을 뒤집었는데 **이력표에 그 행이 없다.** 되돌린 사실이
되돌린 문서에 안 적혀 있으면, 다음 사람은 마지막 행을 현행으로 읽는다.

## 🔴 DISC-5 [중] `npb_last3_verified` 가 검증한 것은 **수집이지 적중이 아니다**

이력표:
```
| 2026-08-29 | npb_last3_verified | False → **True** | **사용자 승인** —
  standings 배선 후 라이브 36/36 부착, 타격표 대조 일치, 전 필드 누락 0 |
  NPB도 58%+라인업이면 추천 가능 |
```

즉 그 플래그는 **"3경기 수집이 온전한가"** 를 검증하고 켠 것이다.
"NPB 판정이 맞는가"는 그때 잴 수 없었다(표본 0).

지금 원장은 다르게 말한다(is_final 기준):
```
NPB 전체 9/21 = 42.9%  ·  NPB 추천 0/4
```
플래그 이름(`last3_verified`)과 그것이 통제하는 것(추천 자격)이 어긋난다.
**수집 검증으로 켠 스위치가 추천 자격을 열고 있다.**

⚠️ 표본이 얇다(n=21·n=4). "끄라"가 아니라 **"그 플래그가 무엇을 근거로
켜져 있는지"** 가 지금 근거와 다르다는 지적이다.

## ✅ DISC-6 정상 — 이 문서가 이 저장소의 가장 좋은 산물이다

- **모든 규칙에 "왜"가 붙어 있고**, 그 왜는 전부 실제 사고다.
- **코드 반영 여부를 3값으로 표기**한다: ✅ 코드로 강제 · ⚠️ 부분 · ❌ 사람이 지킴.
  그리고 ❌ 를 숨기지 않는다 — "5-1 파라미터 임의 변경 금지 | **코드로 강제 불가**".
- **부록: 코드-규율 불일치 현황** 이라는 절이 따로 있다. 어긋난 것을 목록으로 관리한다.
- **절제 실험** 표(1,496경기 λ 백테스트)가 규율의 근거로 실려 있다:
  ```
  항상 홈팀 52.67% · 현행 46.26% · 타선 제거 47.51% · **선발 제거 51.67%**
  절제 실험 한 번이 그날의 추론 세 번보다 정확했다.
  ```
- **8건 연속 틀린 추측**을 표로 남겼다. 그중 2번이 내가 65차에서 다시 찾은
  `fetch_expert_picks` 죽은 코드다 — **이미 알려져 있었다.**

## ✅ DISC-7 정상 — BvP 금지를 **테스트로 강제**한다

```
⚠️ 예외 하나: 오늘 선발의 **투구 손**은 싣는다. 그것은 오늘의 사실이지
   스플릿 성적이 아니다.
강제: 프롬프트 3줄 + `tests/test_c5_bvp_and_stub.py` 가 판정 경로 4파일에
`bvp`·`vs_pitcher`·`head_to_head`·`h2h`·`batter_vs` 유입 0건을 확인한다.
```
금지선과 예외를 함께 정의하고, 예외의 근거("오늘의 사실 vs 시즌 스플릿")를
밝히고, 기계로 잠갔다. 이 감사에서 본 금지 규칙 중 **유일하게 문자열 검사가
아니라 유입 검사**로 잠근 것이다.

---

# 83차 — 🔴 **닫힌 OPEN 항목의 수정이 아무 효과가 없었다** (운영 키로 증명)

읽은 것: `docs/AUDIT_OPEN_ITEMS.md`(191) + 운영 크롤러 키 실측.

## 🔴🔴🔴 CRW-6 [최상] 크롤러는 **여전히 60분 주기**다 — 09-01 에 "고쳤다"고 닫은 항목

### 문서가 기록한 결정

`docs/AUDIT_OPEN_ITEMS.md` §2:
```
**② 아직 모르는 것**
어느 쪽이 의도인지 확인되지 않았다. 60m이 의도였다면 문서가 낡은 것이고,
10m이 의도였다면 **공시 감지 주기가 문서보다 6배 느리게 돌고 있다.**
KBO 라인업 공시는 개시 약 1시간 전에 뜨므로(실측 T-54·T-51·T-48),
**60m 주기면 공시를 최대 한 시간 늦게 본다.**

**✅ 종결 2026-09-01 (사용자 지시).** `10m` 이 의도다 — CLAUDE.md 서비스 표가
맞고 `deploy.sh` 가 낡아 있었다. **`tools/deploy.sh` 2곳을 `crawler -interval 10m`
으로 고쳐 문서와 일치시켰다.**
```

### 그런데 그 수정은 **쓰이지 않는 문자열**을 고친 것이다

```bash
deploy_one() {
  local svc="$1" cmd="$2" path="${3:-.}"
  railway variables … --skip-deploys >/dev/null
  echo "▶ $svc 배포 ($cmd)"                       # ← cmd 는 여기서만 쓰인다
  ( cd "$path" && railway up … --detach )          # ← cmd 를 넘기지 않는다
}
crawler) deploy_one analystbot-crawler "crawler -interval 10m" crawler ;;
```
`--start-command` 도, `--set` 도 없다. **`cmd` 는 화면에 찍히고 버려진다**(DEP-2).

실제 실행 명령은 이미지의 `CMD` 다:
```dockerfile
# crawler/Dockerfile
# 평시 60분 — 타순 창에 들어선 종목만 2분.
CMD ["crawler", "-interval", "60m"]
```
`crawler/railway.json` 에도 `startCommand` 가 없다.

### 운영 키가 60분을 증명한다 (2026-09-08 실측)

```
crawl:* 키 30개
  crawl:kbo:2026-09-08:0003
  crawl:kbo:2026-09-08:0103
  crawl:kbo:2026-09-08:0203
  crawl:kbo:2026-09-08:0303
  crawl:kbo:2026-09-08:0403
  crawl:kbo:2026-09-08:0503
  crawl:kbo:2026-09-08:0603   …
```
**정시 3분(HH:03)에 한 번씩.** 10분 주기면 시간당 6개가 찍혀야 한다.

```
crawl:heartbeat = 2026-09-08T12:04:23+09:00
```

### 결론

```
2026-09-01  "10m 이 의도다" 결정 → deploy.sh 문자열 수정 → 항목 ✅ 종결
2026-09-08  운영은 여전히 60m
```

**일주일 동안 KBO 라인업 공시를 최대 1시간 늦게 봤다** — 그 위험을 문서가
정확히 적어 놓고, 그것을 막기로 결정하고, 효과 없는 수정으로 닫았다.

⚠️ 다만 문서가 완화 요인도 적었다:
> **가속 창이 실제로 이를 가려왔다** — 실측 2026-09-01: NPB 가속이
> 17:00~17:44 2분 간격으로 정상 동작했다(`pace.Fast`). 평시 주기는 창 밖
> 구간에만 적용된다.

`pace.KBOLead = 4h30m` 이라 KBO 는 T-4:30 부터 가속(2분)에 들어간다.
18:30 경기면 14:00 부터다 — **공시(T-1h)는 가속 창 안에 있다.**
그래서 실질 피해는 창 밖(오전·야간)의 편성 변경 감지뿐이다.

**그래도 결정과 현실이 일주일째 다르고, 그 사실을 아무도 몰랐다.**
그리고 지금 `10m` 을 주장하는 곳은 **CLAUDE.md 서비스 표 하나뿐**이다 —
사본이 원본을 이겼다고 문서가 판정했는데, 원본은 바뀌지 않았다.

## 🔴 CRW-2 재확인 — 하트비트 TTL 이 정지 감지를 막는다

```
crawl:heartbeat TTL = 5,856초 (≈ 1.63시간, 설정 2시간)
crawler_feed.STALE_MINUTES = 180 (3시간)
```
```python
async def is_alive(redis):
    raw = await redis.get(HEARTBEAT_KEY)
    if not raw:
        return False, "크롤러 하트비트 없음 — **미실행**"
    …
    if age > STALE_MINUTES:
        return False, f"크롤러 {age:.0f}분째 **멈춤**"
```
TTL(2h) < 임계(3h) 이므로 **"N분째 멈춤" 분기에 도달할 수 없다.**
크롤러가 멈추면 2시간 뒤 키가 사라지고 `/health` 는 "미실행"이라고만 말한다.
"한 번도 안 돌았다"와 "돌다가 멈췄다"가 같은 문장이 된다.

그리고 60분 주기에서 TTL 2시간은 **한 사이클 실패를 못 견딘다** — 두 번
연속 놓치면 키가 만료된다.

## 🔴 AUD-1 [중] §5 의 관측 항목이 **`pick_ledger` 하나만** 본다

```
> **관측 항목: 2026-08-31 배포 이후 "신규 소멸 0건"**
매일 `finals_job` 로그에서 다음을 대조한다:
- `[game_match] 중복 경기 N행 병합 — 예측 N건 · 레저 N건 이관`
- `[ledger-snapshot]` 또는 채점 건수가 병합 전후로 줄지 않는가
한 주 동안 소멸 0건이면 수정이 검증된 것으로 본다.
```

81차에서 확인한 대로 CASCADE 대상은 **12표**이고 이관은 **3표**다.
관측 항목은 `pick_ledger` 만 보므로, `pitcher_appearances`·`lineup_events`·
`variable_ledger`·`game_trace`·`market_baseline_ledger` 소멸은
**"소멸 0건"으로 통과한다.**

수정의 범위(1표)와 문제의 범위(9표)가 다른데 검증 기준이 수정의 범위에
맞춰져 있다.

## 🔴 AUD-2 [중] §4 "왜 계속 갈라지는가"는 **아직도 미측정**이다

```
**② 아직 모르는 것**
어느 소스 조합에서 ext_id가 갈리는지 특정하지 않았다.
**③ 어떻게 측정할지**
1. 병합 직전에 중복 그룹의 `(sport, ext_id, source)` 조합을 **로그로 남긴다.**
```
그 로그는 아직 없다. 그리고 오늘(09-08) 실측:
```
pick_ledger.merged_from 있는 행 : 31   (이미 31번 병합)
현재 남아 있는 중복 그룹        : mlb 31개
```
**병합한 만큼 또 생겼다.** 문서가 적은 대로 "병합은 사후 수습이지 원인
해결이 아니다"이고, 원인 조사는 8일째 착수되지 않았다.

## ✅ AUD-3 정상 — 이 문서의 형식이 옳다

```
각 항목은 ① 관측된 사실 ② 아직 모르는 것 ③ 어떻게 측정할지 를 갖춘다.
측정이 끝나면 이 문서에서 지우고 결론을 해당 문서로 옮긴다.
```
그리고 §1 은 마지막에 이렇게 적는다:
> **행이 실제로 일어난 적은 없다.** 이것은 가설이지 진단이 아니다.
> ⚠️ 측정 전에는 "실운영에도 이 버그가 있다"고 말하지 마라. 지금까지 나온
> 증거는 **테스트 환경 한정**이다.

가설과 진단을 문서 구조로 갈라 놓았다. 이 감사에서 내가 두 번(63차·77차)
어긴 규율이 여기 명문화돼 있다.

---

# 84차 — `MODEL.md` 통독 — **같은 문서가 자기와 모순된다**

## 🔴🔴 DOC-2 [상] §0 이 폐지한 것을 §1-B 가 "넣는다"고 적는다

`docs/MODEL.md` **§0** (문서 앞, 2026-09-04 대원칙):
```
| C1 | 자료9 불펜 — 시즌 ERA → 최근 3경기 실점 + 최근 3일 가용성 (**교체**) | 2026-09-04 |
| C2 | 자료7 선발 시즌 라인 · 자료8 타선 시즌 타격 (**폐지**) | 2026-09-04 |
```

같은 문서 **§1-B 「입력」 표** (문서 중간):
```
| 넣는다 |
| 선발 시즌 라인 — **표본 보정 전용** (2026-09-01)          |  ← C2 로 폐지됨
| 타순 9명 시즌 타격 · 팀 가중 OPS — **정식 근거** (2026-09-02) |  ← C2 로 폐지됨
| 불펜 팀 ERA · 등록 투수 개별 ERA·컨디션 (2026-09-02)      |  ← C1 로 교체됨
```

**한 문서 안에서 앞장은 "폐지"라 하고 뒷장은 "넣는다"고 한다.**
09-04 개정이 §0 에 이력으로 추가됐고 §1-B 표는 갱신되지 않았다.

⚠️ 그리고 §1-B 쪽이 지금 코드와 더 가깝다 — CR-1 대로 **불펜 팀 ERA 가
실제로 들어가고 있다**(자료9 8/8 블록). 즉 폐지를 선언한 쪽이 §0 이고
현실은 §1-B 이며, 둘 다 문서에 남아 있다.

## 🔴 DOC-3 [중] 모델명·토큰이 두 세대 낡았다

```
### 두 번의 Claude
2. **매치업** — **Sonnet 5**. `matchup_max_tokens=4000`. 라인업 확정·변경 시 경기당 1회.
> **왜 4000인가.** Claude Sonnet 5는 adaptive thinking이 기본이다. …
>   `claude-sonnet-5`에 temperature를 넣지 마라 (실측 400).
```
실제: `MODEL_MATCHUP = claude-opus-5` · `matchup_max_tokens = 12000`.
그리고 `team_form.py:_NO_SAMPLING` 은 `claude-opus-5` 도 temperature 금지
목록에 넣어 두었다(측정 전, 안전 쪽).

## 🔴🔴 FRZ-4 [상] MODEL.md 가 **"다시 끊지 마라"고 적은 그 일이 일어났다**

```
🔴 **표본은 다시 끊지 않았다.** `FREEZE_RESTART_IS_FINAL=True` 이고, 그날
   슬레이트를 새 재료로 다시 돌려 덮었으므로 2026-09-04 이후 표본은 전부
   같은 재료다. **재료를 바꿀 때마다 날짜를 미루면 영원히 50건에 도달하지 못한다.**
                                              — MODEL.md §0 (2026-09-05 작성)
```

3일 뒤:
```python
# app/engine/daily_summary.py
FREEZE_START_DEFAULT = "2026-09-07"
FREEZE_RESTART_REASON = "실력 축 복원(620행 분석 근거)"
```
**재료를 바꾸면서 날짜를 미뤘다.** 그리고 경고가 예언한 그대로다:
```
현재 카운터: kbo 0/50 · mlb 0/50 · npb 0/50
폐기된 graded 누적: 146건
5일간 재시작 3회 (09-03 → 09-05 → 09-07)
```

`FREEZE_RESTART_IS_FINAL` 은 두 번 "마지막"을 선언했고, **읽는 코드가 없다.**

## 🔴 CAP-1 [중] `prob_cap_alert_n = 3` 경보가 **연결돼 있지 않다**

MODEL.md §1:
```
| `prob_cap_alert_n` | 3 | 공통 | 하루 3건 초과 시 "모델 점검 필요" |
**상한 초과 시 동작 (야구)**: `p_home`을 [0.32, 0.68]로 절사 + 원값 표기 + 로그.
하루 `prob_cap_alert_n`건 이상이면 ERROR 로그로 "확률 계산 로직 점검 필요".
```

그 경보를 내는 함수 둘이 **전 저장소 참조 0**이다(65차 DEAD-1):
```
app/engine/scoring.py  record_cap_hit    참조 0
app/engine/scoring.py  cap_alert_count   참조 0
```
그리고 실제 절사는 `matchup.clip_p_home` 이 한다 — 그 함수는 `record_cap_hit`
을 부르지 않는다:
```python
def clip_p_home(p, settings=None) -> float:
    lo, hi = s.min_win_prob_mlb, s.max_win_prob_mlb
    return max(lo, min(hi, val))          # 세지 않는다
```

CLAUDE.md 가 "이 값을 넘는 산출은 **모델이 틀렸다는 신호**"라고 적은 그 신호를
**아무도 세지 않는다.**

## ✅ MOD-1 정상 — 기대치를 **학계보다 낮게** 잡았다

```
| 학계 최고 수준 MLB 예측 정확도 | **61.77%** | Wharton |
| MLB 단일 경기 예측의 물리적 상한 | **약 72%** | 운의 비중 27.8% |
| **우리 목표** | **58~60%** | 학계 최고보다 낮게 잡는다 |
| 세계 최고 조직의 시장 대비 엣지 | **1~2%** | Starlizard(분석가 200명) |

"승률 77%"는 강한 픽이 아니라 **모델이 틀렸다는 신호**다. …
축구에서 그 숫자가 나오면 우리가 Starlizard보다 5배 똑똑한 게 아니라
**데이터가 틀린 것**이다.
```
목표를 외부 기준으로 고정하고, 그 위로 나오는 값을 성과가 아니라 결함으로
읽기로 했다. 이 감사에서 본 가장 좋은 설계 판단이다.

## ✅ MOD-2 정상 — 아카이브를 **지우지 않고 격리**했다

```
> **2026-08-29 사용자 지시.** 야구 운영은 위 §1-B만 따른다. 아래 옛 §2~§8은
> 삭제하지 않고 학습·사고 기록으로 남긴다. **이 수치로 운영 임계·λ 경로를
> 되돌리지 마라.**
```
그리고 아카이브 안에서도 정직하다:
```
> ⚠️ **계수는 대부분 임의값이다.** 학술 근거가 있는 것은 *변수 중요도 순서*와
> *상한값*이고, 개별 계수(-2%p 등)는 아직 데이터로 학습되지 않았다.
```

## ✅ MOD-3 정상 — 플래툰을 **관문 불통과로 보류**하고 이유를 적었다

```
3리그 모두 "최근 10타석 × 상대 선발 손타입"을 못 만든다(2026-09-05 실측).
MLB 는 `sitCodes` 가 `lastXGames` 와 조합되지 않고, KBO 는 최근 창이 없고,
NPB 는 시즌표뿐이다. **MLB 만 넣으면 3리그 표본이 갈리므로 전체 보류한다.**
```
"되는 리그만 먼저"를 거부한 판단이 세 번 반복된다(자료8 대체·플래툰·최근 5경기
타격). 표본 일관성을 기능 추가보다 위에 뒀다.

---

# 85차 — ⛔ LLM-5 정정 · `JUDGE_STABILITY` 가 이미 답을 갖고 있었다

## ⛔ 63차 LLM-5 **정정** — 후보 1개는 실수가 아니라 **오디션 결과**다

내가 63차에서 이렇게 썼다:
> `free_judge_model = 'gemini/gemini-3.7-flash'` ← 후보 1개.
> 설계 주석("무료 후보를 **여럿** 둔다… 하나만 두면 그 경기는 카드가 못
> 나간다")과 **정반대**다.

`docs/JUDGE_STABILITY_2026-09-05.md` 를 읽고 그것이 틀렸음을 알았다.
**동일 프롬프트 10회 오디션**으로 후보를 떨어뜨린 것이다:

| 모델 | n | 최대-최소 | 우세 뒤집힘 | 판정 |
|---|---|---|---|---|
| nvidia/nemotron-3-ultra-550b | 10 | **10.00%p** | **4** | ❌ |
| groq/gpt-oss-120b | 10 | **12.00%p** | **3** | ❌ |
| groq/qwen3.8-27b | 10 | 0.00%p | 0 | ⚠️ **전량 0.500 — 판별 포기** |
| openrouter/minimax-m3:free | 10 | 0.00%p | 0 | ⚠️ 전량 0.500 |
| **gemini-3.7-flash** | 18 | 3.00%p | **0** | 상대적 최선 |

> 지시받은 합격선은 `산포 ≤2%p AND 뒤집힘 0` 이다. 이 기준은 **"항상 0.500 을
> 내는 모델"을 만점으로 통과시킨다.** 0.500 은 판정이 아니라 "모르겠다"이며,
> 안정성이 아니라 **판별 포기**다.

**후보를 줄인 것은 옳은 판단이다.** "카드가 나가는 것"과 "우세가 회차마다
뒤집히는 판정이 나가는 것"을 저울질해 후자를 뺐다.

## 🔴 LLM-8 [상] 그런데 문서가 정한 사슬은 **둘**이었다

`JUDGE_STABILITY` §3 「적용한 수정」:
```
| **주전 교체** | `gemini-3.7-flash` 를 사슬 provider 로 등록.
                 **사슬 = gemini → nemotron.** |
```
운영 실효값:
```
FREE_JUDGE_MODEL = gemini/gemini-3.7-flash        ← 하나뿐
```
`nemotron` 이 사라졌다. 09-05 에 "gemini → nemotron" 으로 정했는데 지금은
gemini 단독이다. 언제·왜 빠졌는지 저장소·이력에 근거가 없다
(`FREE_JUDGE_MODEL` 은 env 라 커밋에 안 남는다 — `config.py` 기본값은 `""`).

그리고 그 하나가 **09-04~09-07 에 quota 429 를 50회** 맞았다(59차 실측).
`soft_retries=1` · `hops=2` 인데 후보가 1개이므로 **한 번 실패하면 끝**이다.

⚠️ `nemotron` 을 되살리는 것이 답인지는 모르겠다 — 그것이 우세를 4/10 뒤집는
모델이다. 문서 자체가 그 딜레마를 인식하고 있다:
> **3회 중앙값은 우세 뒤집힘을 없앤다.** 무료 모델이라 호출 3배의 비용이 0이다.
> **아직 도입하지 않았다** — 모델 교체만으로 충분한지 먼저 본다.

§5 남은 것의 첫 줄이 그것이다:
```
- [ ] **3회 중앙값 도입** — 재검 결과 Gemini 단독은 3.00%p 로 합격선 밖이고,
      중앙값을 얹으면 2.00%p 로 들어온다. 근거가 생겼다.
```
**근거가 생겼다고 적고 3일이 지났다.**

## 🔴🔴 FA-2 [상] L1 불일치 414건은 **알려진 오탐 3종**을 포함한다

72차에서 나는 `judgement_audit` 을 이렇게 적었다:
```
1,156행 · 확인 9,693 · 미발견 1,462 · 불일치 414 → 불일치율 3.6%
```
`JUDGE_STABILITY` §6 이 그 414의 성격을 이미 밝혀 놓았다 —
**그날 경보 전건이 오탐이었다.**

| # | 결함 | 실례 |
|---|---|---|
| (a) | **판정의 산수를 검증 못 함** | "8.0이닝 6실점 **ERA 6.75**" → 감시 `era 주장 6.75 vs 원문 15.0`. **6×9÷8 = 6.75, 판정이 맞다** |
| (b) | **선발과 불펜을 한 풀에 섞음** | "원정 불펜 최근 3경기 0.67실점/11이닝(자료9)" → 감시가 **자료4(선발)** 이닝과 대조 |
| (c) | **비율의 분모를 값으로 오인** | "**9이닝** 4.4볼넷"(= BB/9) → 감시 `ip 주장 9.0 vs 원문 11.0` |

```
→ (a)는 `derived` 로 승격해야 하고, (b)는 자료 출처별로 풀을 분리해야 하며,
  (c)는 비율 표현을 추출에서 빼야 한다. **아직 고치지 않았다.**
```
여기에 내가 찾은 (d) `\b` 경계 결함(FA-1: `1475.6으로` → `1475`)을 더하면
**오탐 유형이 넷**이다. **414 를 불일치 건수로 읽으면 안 된다.**

L1 은 세 감시층 중 유일하게 도는 층인데, 그 출력의 신뢰도가 아직 정해지지 않았다.

## 🔴 MU-6 [중] 판정 이력이 **덮어써져** 소급 집계가 불가능하다

`JUDGE_STABILITY` §5:
```
- [ ] **판정 이력이 남지 않는다** — `persist_matchup_record` 가 SET 으로
      덮어써 재판정 이력이 사라진다. 그래서 **"9/4 이후 유령 수정카드 N건"을
      소급 집계할 수 없었다.** append 기록이 필요하다.
```
확인했다:
```python
# matchup.persist_matchup_record
await redis.set(analysis_game_key(sport, gid, date),
                json.dumps(blob, …), ex=FORM_TTL)     # SET — 덮어쓴다
```
`pick_ledger` 는 이력을 남기지만(`is_final` + `rejudge_count`), 그것은
**판정이 실제로 바뀌었을 때만** 행을 만든다(`_same_judgement`). 같은 값으로
반복된 재판정은 어디에도 안 남는다.

## 🔴 TOOL-1 [중] 도구 독스트링이 **틀렸다고 판명된 사용법**을 아직 안내한다

`JUDGE_STABILITY` 부록:
```
운영 DB·Redis 는 `.railway.internal` 이라 외부에서 닿지 않는다.
CLAUDE.md 가 안내하는 `railway run` 은 **로컬에서** 실행되므로 운영 상태를
읽지도 바꾸지도 못한다(**문서가 틀렸다**).
```
CLAUDE.md 는 09-05 에 고쳐졌다(`railway ssh` 안내로 교체). 그러나 도구들은 안 고쳐졌다:
```python
# tools/unblock.py
  railway run python -m tools.unblock --list  # 운영에서

# tools/resend.py
⚠️ **서버에서 돌린다.** … `railway run python -m tools.resend --sport mlb` 로 쓴다.
```
그 두 도구가 정확히 "운영 상태를 바꾸지 못했다"고 CLAUDE.md 에 실사고로
기록된 도구다(실측 2026-09-05). **사고를 겪고 루트 문서는 고쳤는데, 사고를
당한 도구 자신의 사용법은 그대로다.**

## ✅ JS-1 정상 — 가설 둘을 **둘 다 반증**하고 진짜 원인을 찾았다

```
| ① 사슬이 provider 를 회전시킨다 | ❌ 오늘 판정은 한 건 빼고 전부 nemotron —
                                    **산포가 같은 모델 안에서 났다** |
| ② temperature 가 0 이 아니다   | ❌ 이미 temperature:0 을 전송 중 |

**진짜 원인: `temperature=0` 은 결정성을 보장하지 않는다.** 대형 MoE 서빙은
배치 구성에 따라 부동소수 누산 순서가 달라진다.
```
그리고 자기 처방도 반증했다:
```
### 재검 — seed 는 답이 아니었다
| nemotron seed 없음 | 10.00%p | 뒤집힘 4 |
| nemotron seed 고정 |  8.00%p | 뒤집힘 **5** |
**`seed` 로는 잡히지 않는다.** 뒤집힘은 오히려 늘었다.
**모델 교체가 답이었고 seed 는 보조다.**
```
그래도 seed 를 남긴 이유까지 적었다 — "비용이 0이고, provider 가 나중에
진짜 결정성을 지원하면 그때 효과가 난다."

## ✅ JS-2 정상 — **자기 합격 판정을 스스로 취소했다**

```
### 🔴 정정 — Gemini 도 합격선을 넘지 못한다
1차(8회)에서 2.00%p 로 "유일한 합격"이라고 적었으나, 충전 후 재검(10/10 유효)은
**3.00%p** 였다. 합격선(≤2%p)을 **넘지 못한다.**
…
- 그러나 **엄밀히는 합격이 아니다.** 표본을 늘리니 산포가 늘었다 —
  **8회에서 멈췄으면 못 봤을 것이다.**
```
표본을 늘려 자기 결론을 뒤집고, 그 사실을 문서 안에 남겼다.
이 감사에서 내가 두 번 해야 했던 일(63차·77차)이다.

---

# 86차 — `deepsearch.py` · `config.py` · `WIRING_MAP` 통독

## ✅ DS-1 정상 — 상한 셋을 **코드가 강제**한다

```python
#: 확률 조정 상한. 클리핑과 같은 방식으로 코드가 강제한다.
ADJUST_CAP_PP = 4.0

def clamp_adjustment(p_before, p_after, favored):
    """조정 ±4%p 상한 + 우세 방향 단독 뒤집기 금지. **코드가 강제한다.**
    ⚠️ 프롬프트에 적는 것만으로는 부족하다. 모델이 규칙을 어겨도 값이 새어
       나가지 않아야 한다 — 클리핑과 같은 태도다."""
    p = max(p_before - 0.04, min(p_before + 0.04, float(p_after)))
    if favored == "home" and p_before >= 0.5 > p:
        p, note = 0.5, "우세 방향 단독 뒤집기 금지 — 0.50에서 멈춤"
```
이 감사에서 본 규칙 중 **프롬프트가 아니라 코드로 강제된** 몇 안 되는 것이다.
(대조: 자료9 시즌 유입은 네 단어 블랙리스트뿐 — BP-1)

## ✅ DS-2 정상 — 배당이 조사에 샌 사고를 **프롬프트에 박았다**

```
🔴 **배당·머니라인·스포츠북·시장 내재확률을 조사하지 마라. 근거로도 쓰지 마라.**
   실측 2026-09-01: 이 항목이 "시장이 아는 정보"를 묻고 있어, 조사가
   스포츠북 머니라인 내재확률 51~53%를 근거로 p_home 을 0.59→0.56 으로
   내렸다. 추천 1건이 그대로 보드만으로 떨어졌다 — **판정 숫자가 배당에
   좌우된 것이고, 이 저장소가 금지선으로 둔 바로 그 일이다.**
   시장과의 괴리는 판정이 **끝난 뒤** 4단계가 따로 잰다.
   여기서 미리 베끼면 그 괴리 측정 자체가 무의미해진다.
```

## ✅ DS-3 정상 — 같은 결함의 **절반만 고쳤던 것**을 다시 찾았다

```python
def _lineup_of(jg, side):
    """🔴 실측 2026-09-01: T5 가 야구에서 한 번도 발동하지 않았다.
       키가 어긋나 주전 교체 분기와 핵심선수 결장 분기가 **둘 다 죽어 있었다.**

       🔴 [2026-09-04] KBO·NPB 는 크롤러가 준 타순을 research 에 **문자열**로
          담는다. 종전에는 dict 만 보고 문자열은 통째로 흘려보냈다 —
          그래서 T5·T6 가 **야구에서 여전히 죽어 있었다.**
          2026-09-01 에 고쳤는데, 그때는 dict 경로만 열고 문자열 경로는 안 열었다.
          **같은 결함의 절반이 남아 있었던 것이다**(실측 2026-09-04 KBO 8건)."""
```
"고쳤다"의 범위가 좁아 절반이 남았던 사례를 스스로 찾아 기록했다.
내가 이 감사에서 여러 번 본 패턴(CG-1·GM-2·CRW-6)의 **인식된** 버전이다.

## ✅ CFG-1 정상 — `market_agree_required` 를 **한시 조치로 명시**했다

```python
#: 🔴 [임시 방어] 추천은 시장과 같은 방향일 때만 낸다.
#   근거: 2026-09-06 620행 분석 — 추천 게이트 통과분이 30.8%(n=13),
#   보드만이 59.7%(n=77). 우세팀이 갈린 경기는 시장 7승 우리 3승(n=8).
#   시장을 거스르는 확신이 데이터상 **안티 신호**였다.
#   ⚠️ **한시 조치다.** 이 조건은 **구조적으로 시장을 이길 수 없게 만든다** —
#      재캘리브레이션이 끝나면 꺼라. 끄면 종전 동작으로 돌아간다.
#   ⚠️ 임계값은 `market_divergence_pp`(4.0)를 그대로 쓴다(사본 금지).
market_agree_required: bool = True
```
게이트를 켜면서 **그것이 무엇을 포기하는지**를 함께 적었다. 그리고
LED-C(09-07 추천 0건)가 그 포기의 첫 결과다.

## ✅ CFG-2 정상 — 두 번 선언하면 뒤가 이긴다는 것을 실측으로 알았다

```python
#  ⚠️ `gemini_api_key` 는 아래 감시 절에 AliasChoices 와 함께 선언돼 있다.
#     여기에 또 적으면 **뒤가 이겨** 앞은 죽은 줄이 된다(실측). 적지 않는다.
```
`yahoo_npb._SCORE_RE` 가 정확히 그 실수를 하고 있다(78차 YN-4) — 같은
저장소가 한 곳에서는 알고 한 곳에서는 모른다.

## ✅ WM-1 정상 — 배선 지도가 자기 목적을 정확히 정의했다

```
> **읽기 전용 문서다.** … 계획·과거·희망은 적지 않는다 —
> **무엇이 무엇을 실제로 부르는가**만 그린다.
>
> 이번 주 사고 다수가 "코드는 있는데 배선이 안 된" 유형이었다:
> `ensure_analysis_cache` 호출처 0곳(09-01) · `p_market` 이 게이트보다 뒤(09-06) ·
> 평의회 심의가 사슬 1순위에 막혀 영구 빈 dict(09-06) ·
> L1 이 자료12 를 대조 안 함(09-06). **그래서 이 지도의 값은 §3 의 빈 칸에 있다.**
```

그 §3 매트릭스가 잡은 빈 칸 둘은 **다음 커밋에서 메워졌다**
(`63acfcb` "배선 지도가 잡은 빈 칸 둘을 메운다 — 자료6 야구 배선, 수동 재발송 감사").

**이 문서가 이 감사와 같은 방법을 쓴다** — 진입점 × 기능 매트릭스를 그리고
빈 칸을 읽는 것. 다만 지도는 09-07 코드 기준이고, 그 뒤 `lineup_poll_30m`
중복(SCH-2)·`ensure_game_fresh` 재료 파괴(SAN-2) 같은 것은 잡지 않았다.

## 🔴 WM-2 [하] 지도의 라인 번호가 **이미 밀렸다**

문서가 스스로 경고했다:
> ⚠️ 위 라인 번호는 `63acfcb` 기준이고, 오늘 A 배선으로 `pipeline.py` 가
>    늘어났다. **착수 시 다시 확인할 것.**

실제 밀림 폭(현재 `21e84d2` 기준):
```
문서            현재
pipeline.py:1995  →  2067   (_BB_SKIP_OLD)
pipeline.py:2625  →  2698   (_run_baseball_matchups)
pipeline.py:2664  →  2738   (attach_starter_recent)
pipeline.py:2679  →  2753   (bullpen_recent)
pipeline.py:2700  →  2774   (mlb_team_pitching)
matchup.py:527    →   666   (judge_matchup)
```
평균 +70~140줄. 지도가 쓰인 지 하루 만이다.

**좌표를 문서에 적는 방식 자체가 사본이다.** 이 문서는 그것을 알고
유효기간을 명시했지만, 유효기간이 하루였다.

---

# 87차 — ⛔ 1차 C-2 정정 · **이름이 같은 두 스위치를 하나로 읽었다**

문서 맨 앞(1차)에 이렇게 적혀 있다:
```
- **C-2 [상] 설정은 야구 딥서치를 끄고 있는데 야구 딥서치가 돈다.**
  324행 `deepsearch_sports = "soccer"` · `deepsearch_enabled()` 는 soccer 만 True.
```

**이것은 틀렸다.** `config.py` 를 다시 열어 확인하니 **이름이 비슷한 스위치가 둘**이다:

| 스위치 | 위치 | env | 무엇을 막는가 | 운영값 |
|---|---|---|---|---|
| `deepsearch_sports` → `deepsearch_enabled(sport)` | config.py:324 / :734 | `DEEPSEARCH_SPORTS` | **`app/research/deep.py`** — 퍼플렉시티 경기 심층 리서치 | `mlb,soccer` |
| `deepsearch_investigate` | config.py:354 | **`DEEPSEARCH_ENABLED`** | **`app/engine/deepsearch.py`** — 트리거형 조사(T1~T6) | `true` |

둘은 **다른 서브시스템**이다:
```
research/deep.py    유료 퍼플렉시티 · 경기당 1콜 · 전 경기 대상 · 일 상한 60콜
engine/deepsearch.py  무료 RSS + 무료 LLM · 트리거 걸린 경기만 · 슬레이트 30%
```

그래서 `run_for_slate` 가 `deepsearch_enabled(sport)` 를 **안 보는 것이 맞다** —
그건 다른 스위치의 소관이다. `DEEPSEARCH_SPORTS=mlb,soccer` 는 KBO·NPB 에서
**퍼플렉시티 리서치**를 끄는 것이고, 트리거형 조사는 세 리그 다 돈다(의도).

`SMOKE_E2E` 의 `딥서치 mlb 559 · kbo 4 · npb 8` 은 트리거형 조사 기록이고,
KBO·NPB 가 적은 것은 스위치가 아니라 **트리거가 잘 안 걸려서**다.

### 정정 이유

내가 71차에서 잰 **딥서치 무효율 60%(RES-1)** 는 `research_fill:*` 인데,
그것은 `research/deep.py`(퍼플렉시티) 쪽 계측이다. 그 대상은
`DEEPSEARCH_SPORTS=mlb,soccer` 이므로 **MLB·축구뿐**이라고 적은 것은 맞다.
두 스위치를 갈라 본 뒤에도 RES-1 은 유효하다.

### 그러나 남는 것 — 이름이 사고를 부른다

같은 저장소에서 `deepsearch` 라는 낱말이 두 시스템을 가리키고,
스위치 이름이 `deepsearch_sports` 와 `DEEPSEARCH_ENABLED` 다.
**필드명(`deepsearch_investigate`)과 env 이름(`DEEPSEARCH_ENABLED`)도 다르다.**

이 감사에서 내가 그 때문에 한 번 틀렸고, `DATAFLOW.md`·`DISCIPLINE.md` 의
"딥서치" 서술도 어느 쪽인지 문맥으로만 갈린다.

---

# ✅ 감사 종료 — 저장 상태

```
파일  /private/tmp/claude-501/…/scratchpad/FINDINGS.md
크기  555 KB · 10,7xx 줄 · 87차
등급  🔴 최상 48건 · ✅ 정상 확인 101건 · ⛔ 자기정정 8건
워크트리  변경 0건 (코드·설정·문서 일체 미수정)
운영      GIT_COMMIT_SHA 7c0f9be (로컬 HEAD 21e84d2 — 1커밋 미배포)
```
