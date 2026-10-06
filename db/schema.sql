-- AnalystBot v4 스키마. 시간은 전부 UTC(timestamptz) 저장, KST 변환은 표시 계층에서만.
-- 멱등: CREATE TABLE IF NOT EXISTS / CREATE OR REPLACE VIEW 만 사용.
--
-- 🔴 v4 §0: 판정 입력에 배당 숫자는 없다. 이 스키마에 가격이 들어오면 결함이다.
--
-- 🔴 **v4 단계 1(폐기 코드 제거)에서 판정 표를 지웠다** — motivation ·
--    hypotheses · counters · verdicts · grades · triggers · cards · ledger.
--    v4 §8 이 동기 등급·lean·확신·등급·방아쇠를 전부 폐기했다.
--    그 자리에 들어갈 표는 **variables · scenarios · survival · ledger** 이고
--    **단계 2(타입·스키마)** 에서 세운다(§9). 지금 비어 있는 것이 맞다.

-- ── STEP 0 슬레이트 ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS games (
    id          BIGSERIAL PRIMARY KEY,
    sport       TEXT        NOT NULL,              -- 'baseball' | 'soccer'
    league      TEXT        NOT NULL,              -- 'MLB' 'NPB' 'KBO' 'CPBL' 'K리그1' …
    ext_id      TEXT        NOT NULL,              -- 외부 일정 id
    home        TEXT        NOT NULL,
    away        TEXT        NOT NULL,
    venue       TEXT,
    starts_utc  TIMESTAMPTZ NOT NULL,
    -- 🔴🔴 **이름이 거짓말하는 칸 둘** (실측 2026-10-05)
    --
    --  `TIMESTAMPTZ` 는 **순간**을 담는다 — 포스트그레스는 늘 UTC 로 보관하고
    --  오프셋을 **버린다.** 그래서 수집기가 `.astimezone(KST)` 를 넣어도
    --  아무 일도 일어나지 않는다: 라이브 52행 **전부** `starts_kst =
    --  starts_utc` 였다. ⚠️ 종전 이 자리 주석이 *"§2 현지·KST 둘 다 저장"* 이라
    --  적혀 있었고, 질의 여섯 자리가 그 말을 믿고 `starts_kst::date` 로 날짜를
    --  뽑았다 — 그 캐스트는 **세션 시간대**(운영 `Etc/UTC`)로 돈다. 52행 중
    --  **16행**이 어긋났다(유럽 저녁·북미 경기 전부).
    --
    --  🔴 지금은: 넣는 값은 `timefmt.db_instant`(UTC), 보이는 KST 는
    --     `timefmt.kst_label`, KST 날짜 질의는 `timefmt.sql_kst_day` —
    --     셋 다 **한 곳**이고 계약이 그것을 센다(`tests/test_time_contract.py`).
    --  ⚠️ **절대규칙 2 의 "현지 시각도 저장한다" 는 아직 못 지킨다** — 벽시계를
    --     담으려면 `TIMESTAMP`(naive) + 시간대 이름이어야 하고, 그것은 스키마
    --     변경이라 사용자 결정이다
    --     → `docs/fable/questions/2026-10-05_starts_kst_is_an_instant.md`
    starts_kst  TIMESTAMPTZ NOT NULL,              -- = starts_utc 와 **같은 순간**
    starts_local TIMESTAMPTZ,                      -- 같은 병(벽시계가 아니다)
    status      TEXT        NOT NULL DEFAULT 'scheduled',
        -- scheduled | delayed | postponed | inprogress | final
    round_note  TEXT,                              -- §2 순연 경기: 라운드·원래 날짜
    home_score  INT,
    away_score  INT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (sport, ext_id)
);
CREATE INDEX IF NOT EXISTS idx_games_starts ON games (starts_utc);
CREATE INDEX IF NOT EXISTS idx_games_league_day ON games (league, starts_kst);

-- ── 1b 선수 식별 (§7-3) ────────────────────────────────────────────
-- player_id 는 **봇이 발급한다.** 자연키 = 리그+팀+등번호+이름(+생년월일).
CREATE TABLE IF NOT EXISTS players (
    player_id   BIGSERIAL PRIMARY KEY,
    league      TEXT NOT NULL,
    team        TEXT NOT NULL,
    jersey      TEXT,                              -- 🔴 TEXT — '00' 과 '0' 은 다른 사람이다
    name        TEXT NOT NULL,                     -- 원문 표기 그대로
    name_key    TEXT NOT NULL,                     -- 대조용 정규화 키
    birth_date  DATE,
    role        TEXT,                              -- batter | pitcher | field | gk
    first_seen  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen   TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- 등번호가 있으면 그것이 동명이인을 가른다. 없으면 생년월일로.
CREATE UNIQUE INDEX IF NOT EXISTS uq_players_jersey
    ON players (league, team, jersey, name_key) WHERE jersey IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_players_nojersey
    ON players (league, team, name_key, birth_date) WHERE jersey IS NULL;
CREATE INDEX IF NOT EXISTS idx_players_lookup ON players (league, team, name_key);

CREATE TABLE IF NOT EXISTS player_alias (
    player_id   BIGINT NOT NULL REFERENCES players (player_id) ON DELETE CASCADE,
    source      TEXT NOT NULL,                     -- statsapi | npb_jp | fotmob | kbo
    external_id TEXT NOT NULL,
    linked_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source, external_id)                   -- 같은 외부 id 가 두 선수에 붙으면 실패
);
CREATE INDEX IF NOT EXISTS idx_alias_player ON player_alias (player_id);

-- ── STEP 1 동기 (§3) ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS standings (
    league      TEXT NOT NULL,
    team        TEXT NOT NULL,
    as_of       DATE NOT NULL,
    w           INT, l INT, d INT,
    pct         NUMERIC,
    remaining   INT,
    games_back  NUMERIC,
    clinched    BOOLEAN,
    eliminated  BOOLEAN,
    tiebreaker  TEXT,
    note        TEXT,
    source_url  TEXT,
    published_at TIMESTAMPTZ,
    PRIMARY KEY (league, team, as_of)
);

-- ── STEP 2 결장 원장 (§4) ──────────────────────────────────────────
-- 🔴 "최근 타순 diff" 가 아니라 **열린 상태의 원장**이다.
CREATE TABLE IF NOT EXISTS absences (
    id          BIGSERIAL PRIMARY KEY,
    league      TEXT NOT NULL,
    team        TEXT NOT NULL,
    player_id   BIGINT REFERENCES players (player_id) ON DELETE SET NULL,
    player_name TEXT NOT NULL,                     -- 매칭 실패 시에도 남긴다(미상)
    basis       TEXT NOT NULL,
        -- injury | national_team | suspension | deregistered | rest | gone | personal
    line        TEXT NOT NULL,
        -- midfield | defense | lineup_core | starter | bullpen
    confidence  TEXT NOT NULL,                     -- hard | likely | soft
    since       DATE,
    until_expected DATE,
    replacement TEXT,
    replacement_form TEXT,
    source_url  TEXT,
    published_at TIMESTAMPTZ,
    extracted_by TEXT,                             -- §17-e qwen3:8b@v
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_absences_team ON absences (league, team, created_at DESC);
-- 🔴 **같은 결장을 매 주기 다시 적지 않는다.** 수집은 20분마다 돌고, 유일키가
--    없으면 하루에 같은 행이 72번 쌓인다 — 그러면 "근거 3건"이 실제로는 한 건인데
--    3배로 세어져 자료 충분성(STEP 4)이 거짓이 된다(§12-c-4 가 막으려는 것과 같은
--    병이 DB 층에서 난다). 실측 2026-09-30: 단계 3 적재를 붙이며 발견했다.
-- ⚠️ `player_name` 을 열쇠에 쓴다 — `player_id` 는 **미상일 수 있고**(§7-3 은
--    거짓 매칭보다 미상을 택한다), NULL 은 유일키에서 서로 다른 값으로 취급된다.
CREATE UNIQUE INDEX IF NOT EXISTS uq_absences_open
    ON absences (league, team, player_name, basis)
 WHERE resolved_at IS NULL;

-- 🔴 §17-g-4 거절된 추출도 전부 보관한다 — "뉴스가 없던 날"과 "추출기가 고장난
--    날"을 채점에서 구분하려면 이 표가 있어야 한다.
CREATE TABLE IF NOT EXISTS extraction_rejected (
    id          BIGSERIAL PRIMARY KEY,
    task        TEXT NOT NULL,                     -- L1 | L2 | L3 | L4 | L5 | L6
    stage       TEXT NOT NULL,                     -- extract | judge | match
    reason      TEXT NOT NULL,
    raw         JSONB,
    source_url  TEXT,
    model       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_rejected_day ON extraction_rejected (created_at DESC);

-- ── STEP 3 선발·폼 (§5) ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS starters (
    game_id     BIGINT NOT NULL REFERENCES games (id) ON DELETE CASCADE,
    side        TEXT   NOT NULL,
    player_id   BIGINT REFERENCES players (player_id) ON DELETE SET NULL,
    name        TEXT,
    status      TEXT   NOT NULL DEFAULT 'probable', -- probable | confirmed | unknown
    recent      JSONB,                              -- [{date, ip, er, pitches}] 최근 3~5
    vs_opponent JSONB,                              -- {games, era} — 3경기 이상만 판정 입력
    flags       TEXT[],                             -- bullpen_dependent | return_first |
                                                    -- bulk_unknown | opener
    source_url  TEXT,
    PRIMARY KEY (game_id, side)
);

CREATE TABLE IF NOT EXISTS team_form (
    game_id     BIGINT NOT NULL REFERENCES games (id) ON DELETE CASCADE,
    side        TEXT   NOT NULL,
    recent5     JSONB,                              -- [{date, result, gf, ga, comp}]
    bullpen_3d  JSONB,                              -- [{name, ip, pitches}]
    midweek     BOOLEAN,
    note        TEXT,
    PRIMARY KEY (game_id, side)
);

-- ── STEP 4 감독 의도 (§6) ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS intent (
    game_id     BIGINT NOT NULL REFERENCES games (id) ON DELETE CASCADE,
    side        TEXT   NOT NULL,
    type        TEXT   NOT NULL,                    -- §6 유형 8종
    quote       TEXT,                               -- 🔴 본문에 실재할 때만 hard
    speaker     TEXT,
    hardness    TEXT   NOT NULL DEFAULT 'soft',     -- hard | soft
    source_url  TEXT,
    published_at TIMESTAMPTZ,
    extracted_by TEXT,
    PRIMARY KEY (game_id, side)
);

-- ── v4 STEP 2~8 의 표는 **단계 2 에서 세운다** ────────────────────
--    variables · scenarios · survival · ledger (§3 입출력 계약).
--    🔴 지금 비어 있는 것이 맞다 — v4 §0 "세포망이 게이트를 통과하기 전에는
--       시나리오 엔진을 한 줄도 짓지 않는다".

-- ── 증거 카드 (v3 §12-e 유지) ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS evidence (
    id          BIGSERIAL PRIMARY KEY,
    game_id     BIGINT REFERENCES games (id) ON DELETE CASCADE,
    claim       TEXT NOT NULL,
    step        INT  NOT NULL,                      -- 0~9
    team        TEXT,
    player_id   BIGINT REFERENCES players (player_id) ON DELETE SET NULL,
    value       TEXT,
    source_url  TEXT,
    publisher   TEXT,
    published_at TIMESTAMPTZ,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now(), -- 🔴 코드가 기록한다
    hardness    TEXT NOT NULL DEFAULT 'soft',       -- hard | likely | soft
    used_in     TEXT,                               -- lean | counter | trigger
    extracted_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_evidence_game ON evidence (game_id, step);

-- ── 실행 추적 ──────────────────────────────────────────────────────
-- 🔴 §5 파이프라인이 온전하지 않으면 그 예측은 쓸모없다 — 못 잰 칸을 센다.
CREATE TABLE IF NOT EXISTS runs (
    id          BIGSERIAL PRIMARY KEY,
    game_id     BIGINT REFERENCES games (id) ON DELETE CASCADE,
    slate_date  DATE NOT NULL,
    steps_done  INT[]   NOT NULL DEFAULT '{}',
    unknowns    TEXT[]  NOT NULL DEFAULT '{}',      -- 못 잰 칸 이름
    llm_calls   INT     NOT NULL DEFAULT 0,         -- §17-e 경기당 L1~L5 합 20 상한
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_runs_slate ON runs (slate_date, game_id);
-- ══════════════════════════════════════════════════════════════════
-- v4 단계 2 — §1 용어 · §3 STEP 스키마의 DB 면
--
-- 🔴 **배선은 단계 3 이다.** 여기 만든 표를 지금 읽는 코드는 없고, 그 사실이
--    `tests/test_wiring.py` 의 표 `NOT_WIRED` 에 이름으로 적혀 있다.
-- 🔴 **배당 숫자 칸이 없다**(§0 · §11-9). 가격은 `research` 스키마에만 있고
--    판정 경로·카드 렌더러에 닿지 않는다.
-- ⚠️ 10표다. `NEXT.md` 는 "9표"라 적었는데 §3 STEP 1~3 이 *"direction 없는
--    항목은 background[] 로 분리 저장"* 이라 못 박아 `background` 가 따로 필요하다.
-- ══════════════════════════════════════════════════════════════════

-- ① §1 마켓 — 사용자가 준 보드. 🔴 **배당 숫자는 없다.**
CREATE TABLE IF NOT EXISTS board (
    id          BIGSERIAL PRIMARY KEY,
    game_id     BIGINT NOT NULL REFERENCES games (id) ON DELETE CASCADE,
    market_type TEXT NOT NULL,                      -- home|draw|away|home_dc|away_dc|handicap|total
    team        TEXT,                               -- handicap 일 때만
    line        NUMERIC,                            -- handicap·total 일 때만 (기준선, 가격 아님)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (game_id, market_type, team, line)
);

-- ② §1 변수 — 🔴 direction 이 NOT NULL 이다. 방향 없는 사실은 ③ 으로 간다.
CREATE TABLE IF NOT EXISTS variables (
    id          BIGSERIAL PRIMARY KEY,
    game_id     BIGINT NOT NULL REFERENCES games (id) ON DELETE CASCADE,
    var_key     TEXT NOT NULL,                      -- app 쪽 Variable.id
    type        TEXT NOT NULL,                      -- §4 유형 13종 (variable_types.yaml)
    direction   TEXT NOT NULL,                      -- 🔴 §9 게이트: 없으면 저장 실패
    hardness    TEXT NOT NULL,                      -- hard|likely|soft
    weight      NUMERIC NOT NULL,                   -- 🔴 hardness 가 정한다 (§4)
    text        TEXT NOT NULL,
    source_url  TEXT NOT NULL,                      -- 🔴 §3: 없으면 저장 실패
    published_at TIMESTAMPTZ NOT NULL,              -- 🔴 경기 이후면 저장 실패 (§3)
    is_premise  BOOLEAN NOT NULL DEFAULT false,
    collected_at_step SMALLINT NOT NULL DEFAULT 1,  -- 1|2|3
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (game_id, var_key),
    CONSTRAINT variables_direction_ck
        CHECK (direction IN ('home','away','draw','over','under')),
    CONSTRAINT variables_hardness_ck
        CHECK (hardness IN ('hard','likely','soft')),
    -- 🔴 §4 가중치 — hardness 와 어긋난 weight 는 저장되지 않는다
    CONSTRAINT variables_weight_ck CHECK (
        (hardness = 'hard'   AND weight = 1.0) OR
        (hardness = 'likely' AND weight = 0.7) OR
        (hardness = 'soft'   AND weight = 0.4)),
    CONSTRAINT variables_step_ck CHECK (collected_at_step IN (1,2,3)),
    CONSTRAINT variables_source_ck CHECK (btrim(source_url) <> '')
);
CREATE INDEX IF NOT EXISTS idx_variables_game ON variables (game_id, direction);

-- ③ §3 STEP 1~3 — 방향 없는 사실. 🔴 **버리지 않는다**(조용한 0 금지).
CREATE TABLE IF NOT EXISTS background (
    id          BIGSERIAL PRIMARY KEY,
    game_id     BIGINT NOT NULL REFERENCES games (id) ON DELETE CASCADE,
    bg_key      TEXT NOT NULL,
    text        TEXT NOT NULL,
    source_url  TEXT NOT NULL,
    published_at TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (game_id, bg_key),
    CONSTRAINT background_source_ck CHECK (btrim(source_url) <> '')
);

-- ④ §3 STEP 2 — 전제 재검증. 🔴 is_premise 변수마다 한 행. 0건이면 STEP 5 불가.
CREATE TABLE IF NOT EXISTS premise_check (
    id          BIGSERIAL PRIMARY KEY,
    game_id     BIGINT NOT NULL REFERENCES games (id) ON DELETE CASCADE,
    premise_key TEXT NOT NULL,
    query_used  TEXT[] NOT NULL DEFAULT '{}',       -- 🔴 무엇으로 찾았나 — 이름으로 남긴다
    result      TEXT NOT NULL,                      -- kept|replaced
    replacement_var_key TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (game_id, premise_key),
    CONSTRAINT premise_result_ck CHECK (result IN ('kept','replaced')),
    -- 🔴 replaced 와 대체 변수는 함께 간다
    CONSTRAINT premise_replacement_ck CHECK (
        (result = 'replaced' AND replacement_var_key IS NOT NULL) OR
        (result = 'kept'     AND replacement_var_key IS NULL))
);

-- ⑤ §3 STEP 4 — 자료 충분성. 🔴 verdict 는 **수가 정한다**(§1 자료 부족).
CREATE TABLE IF NOT EXISTS sufficiency (
    game_id     BIGINT PRIMARY KEY REFERENCES games (id) ON DELETE CASCADE,
    n_directional INT NOT NULL,
    n_opposite  INT NOT NULL,
    verdict     TEXT NOT NULL,                      -- pass|insufficient
    reason      TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT sufficiency_verdict_ck CHECK (verdict IN ('pass','insufficient')),
    -- 🔴 §1 — 방향 3 미만 또는 반대 0 이면 insufficient 다. 사람이 고를 수 없다.
    CONSTRAINT sufficiency_follows_counts_ck CHECK (
        ((n_directional < 3 OR n_opposite = 0) AND verdict = 'insufficient') OR
        ((n_directional >= 3 AND n_opposite > 0) AND verdict = 'pass')),
    -- 🔴 조용한 0 금지 — 부족하면 왜인지 적는다
    CONSTRAINT sufficiency_reason_ck CHECK (
        verdict = 'pass' OR btrim(reason) <> '')
);

-- ⑥ §1 시나리오 — 🔴 스코어 없으면 총점·핸디 생존을 셀 수 없다.
CREATE TABLE IF NOT EXISTS scenarios (
    id          BIGSERIAL PRIMARY KEY,
    game_id     BIGINT NOT NULL REFERENCES games (id) ON DELETE CASCADE,
    scenario_id TEXT NOT NULL,                      -- A~E
    var_keys    TEXT[] NOT NULL DEFAULT '{}',
    scores      TEXT[] NOT NULL,                    -- 홈-원정 순 (§5-b)
    strength    NUMERIC NOT NULL,                   -- 🔴 변수 weight 합 (§5-d)
    template_id TEXT NOT NULL,                      -- §5-b scenario_rules.yaml
    narrative   TEXT NOT NULL DEFAULT '',           -- LLM L6 만 쓴다 (§5-e)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (game_id, scenario_id),
    CONSTRAINT scenarios_id_ck CHECK (scenario_id IN ('A','B','C','D','E','F','G','H')),
    CONSTRAINT scenarios_scores_ck CHECK (cardinality(scores) > 0),
    CONSTRAINT scenarios_strength_ck CHECK (strength >= 0)
);

-- ⑦ §3 STEP 6 — 마켓 생존. 🔴 verdict 는 survival 이 정한다(§6).
CREATE TABLE IF NOT EXISTS survival (
    id          BIGSERIAL PRIMARY KEY,
    game_id     BIGINT NOT NULL REFERENCES games (id) ON DELETE CASCADE,
    market_type TEXT NOT NULL,
    team        TEXT,
    line        NUMERIC,                            -- 기준선. 🔴 가격 아님
    alive_scenarios TEXT[] NOT NULL DEFAULT '{}',
    dead_scenarios  TEXT[] NOT NULL DEFAULT '{}',
    survival    NUMERIC NOT NULL,
    verdict     TEXT NOT NULL,                      -- name|small|none
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (game_id, market_type, team, line),
    CONSTRAINT survival_range_ck CHECK (survival >= 0 AND survival <= 1),
    CONSTRAINT survival_verdict_ck CHECK (verdict IN ('name','small','none')),
    -- 🔴 §6 · §12 — 생존 1.0 만 이름을 적는다. 아르메니아 +0.5 가 이 실수였다.
    CONSTRAINT survival_name_ck CHECK (
        verdict <> 'name' OR survival >= 1.0),
    CONSTRAINT survival_small_ck CHECK (
        verdict <> 'small' OR survival >= 0.8)
);

-- ⑧ §3 STEP 8 — 채점 원장. 🔴 결과 후 survival 을 고치지 않는다(불변).
CREATE TABLE IF NOT EXISTS ledger (
    game_id     BIGINT PRIMARY KEY REFERENCES games (id) ON DELETE CASCADE,
    realized_scenario_id TEXT,                      -- A~E, 모르면 NULL
    missed_variables TEXT[] NOT NULL DEFAULT '{}',  -- 🔴 경기 후 드러난 미수집 변수
    card_verdicts_result JSONB NOT NULL DEFAULT '[]'::jsonb,
    premise_failures TEXT[] NOT NULL DEFAULT '{}',
    graded_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ledger_scenario_ck CHECK (
        realized_scenario_id IS NULL
        OR realized_scenario_id IN ('A','B','C','D','E','F','G','H'))
);

-- ⑨ 소스 상태 (#10) — 🔴 robots 거부·죽은 호스트는 **dead 처리뿐**(§14-3).
--    프록시·UA 위장 금지. 배선은 단계 3.
CREATE TABLE IF NOT EXISTS source_state (
    host        TEXT PRIMARY KEY,
    dead_since  TIMESTAMPTZ,
    reason      TEXT NOT NULL DEFAULT '',           -- 🔴 왜 죽었나 — 이름으로 남긴다
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT source_state_reason_ck CHECK (
        dead_since IS NULL OR btrim(reason) <> '')
);

-- ⑩ 소스 점수표 (#10) — 질문 유형·리그별로 어느 소스가 맞혔나. 배선은 단계 3.
CREATE TABLE IF NOT EXISTS source_score (
    id          BIGSERIAL PRIMARY KEY,
    source      TEXT NOT NULL,
    question_type TEXT NOT NULL,                    -- §4 유형
    league      TEXT NOT NULL,
    hit         INT NOT NULL DEFAULT 0,
    miss        INT NOT NULL DEFAULT 0,
    lag_min     INT,                                -- 🔴 못 재면 NULL — 0 으로 때우지 않는다
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source, question_type, league)
);

-- ── #6 마이그레이션 — `evidence.used_in` 값 교체 (사용자 지시 2026-09-30) ──
-- 🔴 종전 값 `lean`·`counter`·`trigger` 는 v4 §8 폐기 어휘다.
--    새 값: variable | premise_check | opposite | lineup_rerun | grading
-- 🔴 **원값을 버리지 않는다** — `legacy_used_in` 에 남긴다. 무엇이 무엇으로
--    바뀌었는지 못 되짚으면 과거 판정을 다시 읽을 수 없다.
ALTER TABLE evidence ADD COLUMN IF NOT EXISTS legacy_used_in TEXT;
UPDATE evidence SET legacy_used_in = used_in
 WHERE legacy_used_in IS NULL AND used_in IS NOT NULL;
UPDATE evidence SET used_in = CASE used_in
        WHEN 'lean'    THEN 'variable'
        WHEN 'counter' THEN 'opposite'
        WHEN 'trigger' THEN 'lineup_rerun'
        ELSE used_in END
 WHERE used_in IN ('lean','counter','trigger');
-- 🔴 새 값만 들어온다. 멱등: 이미 있으면 건너뛴다.
ALTER TABLE evidence DROP CONSTRAINT IF EXISTS evidence_used_in_ck;
ALTER TABLE evidence ADD CONSTRAINT evidence_used_in_ck CHECK (
    used_in IS NULL OR used_in IN
    ('variable','premise_check','opposite','lineup_rerun','grading'));

-- ── §4 유형 enum 을 DB 에도 세운다 (리뷰 B2) ──
-- 🔴 **두 겹이다** — pydantic 이 `rules.variable_types()` 로 막고, psql 로 넣는
--    길도 여기서 막는다. ⚠️ 이 목록은 `config/variable_types.yaml` 의 사본이므로
--    `test_DB_의_type_enum_이_yaml_과_같다` 가 둘을 대조한다.
-- 🔴 **`home_field` 는 사용자 지시 2026-10-02 로 더했다**(v4 §4 표에는 없다).
--    선언은 yaml 의 `added_by_user_instruction` 에 있고 근거 문서까지 적혀 있다.
--    실측: MLS 홈 승률 +16.8%p·득점 +0.46골 · USL +18.3%p·+0.50골.
ALTER TABLE variables DROP CONSTRAINT IF EXISTS variables_type_ck;
-- 🔴 **카탈로그 5종을 더했다**(사용자 설계 2026-10-02 · 선언은
--    `variable_types.yaml` 의 `added_by_user_instruction`).
--    ⚠️ 여기 안 더하면 적재가 CheckViolation 으로 터진다 — `home_field` 때 실측했다.
-- 🔴 **`lineup_value` 를 더했다**(딥서치 2026-10-03 · 사용자 지시 *"축구 라인업
--    시장가치 소스를 쓰나 — 딥서치해서 찾아서 넣어라"*).
--    자료는 fotmob 라인업의 `marketValue` 다(새 소스 없음). ⚠️ λ 에는 안 넣는다 —
--    가치를 골 단위로 바꾸는 계수가 발표된 적이 없다(선언 문서에 근거가 있다).
ALTER TABLE variables DROP CONSTRAINT IF EXISTS variables_type_ck;
-- 🔴 **유형 여섯을 더했다**(사용자 지시 2026-10-06 ③ · 선언은
--    `variable_types.yaml` 의 `added_by_user_instruction`):
--    `absence_att`·`coach_intent`·`individual_title`·`team_stats`·`regression`·`fatigue`.
--    ⚠️ 여기 안 더하면 적재가 CheckViolation 으로 터진다(`home_field` 때 실측했다).
ALTER TABLE variables ADD CONSTRAINT variables_type_ck CHECK (
    type IN ('absence','absence_att','coach_change','coach_conflict','coach_intent','def_absence','emotion','event_match','fatigue','h2h_pattern','home_field','individual','individual_title','lineup_intent','lineup_value','match_type','national_duty_return','pitcher_state','recent_pattern','regression','returning','squad_rotation','stakes','strength_gap','suspension','team_stats','travel_schedule','venue_weather'));
-- ── §19-a 세포 질문 타입 enum (수정 2026-09-30) ──
-- 🔴 **단계 2 가 여기에 §4 변수 유형 13종을 걸었다. 그것은 틀렸다.**
--    `source_score.question_type` 은 §19-e 원문의 세 번째 열이고, §19-a 가 정의한
--    **세포 질문 타입**이다: *"question: 구조화된 질문(type: lineup/absence/
--    starter_recent/standings/intent/live_score/counter …)"*. §4 유형(`emotion`·
--    `h2h_pattern`·`stakes` …)은 **변수**의 어휘이지 질문의 어휘가 아니다.
--    두 어휘가 겹치는 것은 `absence` 하나뿐이다.
-- ⚠️ 실측 2026-09-30: 단계 3 이 점수표 적재를 이으니 `question_type='lineup'` 이
--    바로 `CheckViolationError` 로 튕겼다 — 표만 세우고 **쓰는 코드가 없어서**
--    단계 2 에서는 아무도 몰랐다(CLAUDE.md §배선: 안 이어진 코드는 없는 코드보다
--    나쁘다). 계약도 제약의 *존재*만 봤고 **어휘가 맞는지는 안 봤다.**
-- 🔴 이 8개는 `app/cells.Q_TYPES` 의 사본이므로 계약이 둘을 대조한다.
ALTER TABLE source_score DROP CONSTRAINT IF EXISTS source_score_qtype_ck;
ALTER TABLE source_score ADD CONSTRAINT source_score_qtype_ck CHECK (
    question_type IN ('slate','lineup','absence','starter_recent','standings','intent','live_score','counter'));

-- ── §1 마켓 종류 enum 을 DB 에도 세운다 (리뷰 M1) ──
-- 🔴 **두 겹 중 한 겹이 비어 있었다** — pydantic 은 `MarketType` Literal 7종으로
--    닫았는데 `board.market_type`·`survival.market_type` 은 `TEXT NOT NULL` 뿐이라
--    psql 로는 아무 문자열이나 들어갔다.
-- ⚠️ 이 7개는 `app/types.py` 의 `MarketType` 사본이므로
--    `test_DB_의_market_type_enum_이_타입과_같다` 가 둘을 대조한다.
-- 🔴 **`btts` 를 더했다**(사용자 지적 2026-10-03: 보드에 *"양팀득점"* 이 있었다).
--    ⚠️ v4 §1 에 없는 마켓이다 — `app/types.py` 의 `MarketType` 과 계약이 대조한다.
ALTER TABLE board DROP CONSTRAINT IF EXISTS board_market_type_ck;
ALTER TABLE board ADD CONSTRAINT board_market_type_ck CHECK (
    market_type IN ('home','draw','away','home_dc','away_dc','handicap','total','btts'));
ALTER TABLE survival DROP CONSTRAINT IF EXISTS survival_market_type_ck;
ALTER TABLE survival ADD CONSTRAINT survival_market_type_ck CHECK (
    market_type IN ('home','draw','away','home_dc','away_dc','handicap','total','btts'));


-- ══════════════════════════════════════════════════════════════════
-- 🔴 #7 마이그레이션 — **날짜 없는 변수**(사용자 결정 2026-10-02 안 A)
-- ══════════════════════════════════════════════════════════════════
--
-- 🔴 **배선이 이 구멍을 찾았다**(사용자 지시 2026-10-02 *"배선해라"*).
--    `app/types.py` 는 2026-10-02 에 `published_at` 을 `None` 허용으로 열었다 —
--    순위표에는 발행 시각이 **없고** `stakes`·`home_field` 가 거기서 나온다.
--    그런데 이 표는 `published_at TIMESTAMPTZ **NOT NULL**` 이었다.
--    → 즉 그 변수들은 **스키마는 통과하고 DB 적재에서 터진다.** 배선 전에는
--      적재하는 코드가 없어서 아무도 몰랐다.
--
-- ⚠️ 그냥 NULL 을 허용하면 §12-c-2(경기 후 기사 배제)가 쓰는 칸이 비어
--    **날짜 없는 기사가 무게 1.0 을 갖는다.** `types.py` 와 **같은 조건 둘**을 건다:
--      ① 날짜가 없으면 `dateless_reason` 이 **반드시** 있어야 한다
--      ② 날짜가 없으면 hardness 는 **soft** 여야 한다(§12-c-1)
--      ③ 날짜가 **있는데** 사유가 적혀 있으면 거부 — 둘 중 하나다
ALTER TABLE variables ALTER COLUMN published_at DROP NOT NULL;
ALTER TABLE variables ADD COLUMN IF NOT EXISTS dateless_reason TEXT NOT NULL DEFAULT '';
ALTER TABLE variables DROP CONSTRAINT IF EXISTS variables_dateless_ck;
ALTER TABLE variables ADD CONSTRAINT variables_dateless_ck CHECK (
    (published_at IS NOT NULL AND btrim(dateless_reason) = '') OR
    (published_at IS NULL AND btrim(dateless_reason) <> '' AND hardness = 'soft'));

ALTER TABLE background ALTER COLUMN published_at DROP NOT NULL;
ALTER TABLE background ADD COLUMN IF NOT EXISTS dateless_reason TEXT NOT NULL DEFAULT '';
ALTER TABLE background DROP CONSTRAINT IF EXISTS background_dateless_ck;
ALTER TABLE background ADD CONSTRAINT background_dateless_ck CHECK (
    (published_at IS NOT NULL AND btrim(dateless_reason) = '') OR
    (published_at IS NULL AND btrim(dateless_reason) <> ''));


-- ══════════════════════════════════════════════════════════════════
-- 🔴 #8 마이그레이션 — **무엇을 쌓는가** (사용자 지시 2026-10-02 *"뭘쌓는데???"*)
-- ══════════════════════════════════════════════════════════════════
--
-- 🔴 물음이 구멍을 찾았다. `ledger` 가 쌓는 것이 **너무 얇았다**:
--      · 결과 스코어가 없다        → "무엇이 났는지" 를 원장만 보고는 모른다
--      · 그 결과의 확률이 없다     → `survive.grade` 가 계산해 놓고 **버렸다**
--      · 등급·생존이 없다          → *"'낸다' 가 '소액' 보다 더 맞았나"* 를 못 센다
--      · 결과를 덮었나가 없다      → `realized IS NULL` 로 유추해야 했다
--
-- 🔴 그리고 **확률을 되살릴 길**이 필요하다. 격자(64칸)를 다 저장하지 않는다 —
--    `λ` 두 수만 있으면 격자를 **다시 만들 수 있다**(포아송). 그래서 `sufficiency`
--    (경기당 한 줄)에 `λ` 를 적는다. ⚠️ 카드를 만든 **그때의** λ 여야 한다.
ALTER TABLE ledger ADD COLUMN IF NOT EXISTS result_score TEXT;
ALTER TABLE ledger ADD COLUMN IF NOT EXISTS result_probability NUMERIC;
ALTER TABLE ledger ADD COLUMN IF NOT EXISTS covered BOOLEAN;
-- 🔴 덮었다면 어느 시나리오인지 있어야 한다 — 둘이 어긋나면 기록이 거짓이다
ALTER TABLE ledger DROP CONSTRAINT IF EXISTS ledger_covered_ck;
ALTER TABLE ledger ADD CONSTRAINT ledger_covered_ck CHECK (
    covered IS NULL
    OR (covered = true AND realized_scenario_id IS NOT NULL)
    OR (covered = false AND realized_scenario_id IS NULL));

ALTER TABLE sufficiency ADD COLUMN IF NOT EXISTS lam_home NUMERIC;
ALTER TABLE sufficiency ADD COLUMN IF NOT EXISTS lam_away NUMERIC;

-- 🔴 시나리오마다 **그때 준 확률**. 채점이 *"0.11 이라고 한 것이 났나"* 를 묻는다.
--    ⚠️ `strength`(§5-d 근거 합)와 **다른 수다** — 한 칸에 담지 않는다.
ALTER TABLE scenarios ADD COLUMN IF NOT EXISTS probability NUMERIC;
ALTER TABLE scenarios DROP CONSTRAINT IF EXISTS scenarios_probability_ck;
ALTER TABLE scenarios ADD CONSTRAINT scenarios_probability_ck CHECK (
    probability IS NULL OR (probability >= 0 AND probability <= 1));

-- ══════════════════════════════════════════════════════════════════
-- 🔴🔴 **v5 §7-1 — T-60 재실행을 한 번만 했다는 기억**
-- ══════════════════════════════════════════════════════════════════
--
-- > 가져오면 `lineup_state` 를 `confirmed` 로 올리고 §5~§6 을 재실행,
-- > **카드 1회 갱신**(R10).
--
-- ⚠️ 그 기억이 **메모리에만** 있으면 프로세스가 죽을 때 사라지고 카드를 또
--    바꾼다. 🔴 두 번 바꾸면 *"예측을 언제 했나"* 가 흐려지고 채점이 거짓이
--    된다(§3 불변: 맞았나를 예측이 끝난 뒤에 고치지 않는다).
-- 🔴 경기당 한 줄인 `sufficiency` 에 둔다 — 새 표를 만들지 않는다.
ALTER TABLE sufficiency ADD COLUMN IF NOT EXISTS rerun_at TIMESTAMPTZ;
-- 🔴 무엇으로 받았나 — `adapter`/`official`/`agent`(§7-1 순서) 또는 `none`.
--    ⚠️ 적지 않으면 *"에이전트 검색으로 받은 확정 XI"* 와 *"공식 API"* 가
--       한 글자가 된다 — 그 둘의 신뢰도는 다르다(§4-3 도메인 등급).
ALTER TABLE sufficiency ADD COLUMN IF NOT EXISTS rerun_via TEXT;

-- ══════════════════════════════════════════════════════════════════
-- 🔴🔴 **v5 §7-4 — 실패 유형과 비용**
-- ══════════════════════════════════════════════════════════════════
--
-- > **실패 유형을 둘로 가른다**: *없던 시나리오가 터짐*(규칙 결함 → M 계약
-- > 후보) / *죽는 시나리오가 터짐*(무게 보정 대상). … **비용**을 원장에 적는다.
--
-- 🔴 섞으면 *"시나리오를 안 만들었다"* 와 *"만들었는데 낮게 봤다"* 가 한 글자가
--    되고 어느 쪽도 안 고쳐진다.
-- ⚠️ `unknown` 은 **못 쟀다**는 뜻이고 `NULL`(실패 아님)과 다르다.
ALTER TABLE ledger ADD COLUMN IF NOT EXISTS failure_kind TEXT;
ALTER TABLE ledger DROP CONSTRAINT IF EXISTS ledger_failure_kind_ck;
ALTER TABLE ledger ADD CONSTRAINT ledger_failure_kind_ck CHECK (
    failure_kind IS NULL
    OR failure_kind IN ('uncovered', 'underweighted', 'unknown'));
-- 🔴 비용(USD). ⚠️ `NULL` 은 **안 쟀다**이고 `0` 은 **공짜로 했다**다 — 다르다.
ALTER TABLE ledger ADD COLUMN IF NOT EXISTS cost_usd NUMERIC;
