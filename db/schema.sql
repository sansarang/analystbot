-- AnalystBot schema. 시간은 전부 UTC(timestamptz) 저장, KST 변환은 표시 계층에서만.
-- 멱등: CREATE TABLE IF NOT EXISTS / CREATE OR REPLACE VIEW 만 사용.

CREATE TABLE IF NOT EXISTS games (
    id            BIGSERIAL PRIMARY KEY,
    sport         TEXT        NOT NULL,              -- 'mlb' | 'soccer'
    league        TEXT        NOT NULL,              -- 'MLB', 'EPL', ...
    ext_id        TEXT        NOT NULL,              -- 외부 API 경기 ID (gamePk, fixture id)
    starts_at     TIMESTAMPTZ NOT NULL,
    home          TEXT        NOT NULL,
    away          TEXT        NOT NULL,
    home_pitcher  TEXT,
    away_pitcher  TEXT,
    status        TEXT        NOT NULL DEFAULT 'scheduled',  -- scheduled | live | final
    home_score    INT,
    away_score    INT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (sport, ext_id)
);

CREATE INDEX IF NOT EXISTS idx_games_starts_at ON games (starts_at);

-- [2] 라인업 확정 상태 — 예상(predicted)과 확정(confirmed)을 반드시 구분한다.
--     예상을 확정으로 취급하면 픽이 뒤집힐 정보를 놓친다.
ALTER TABLE games ADD COLUMN IF NOT EXISTS lineup_status TEXT NOT NULL DEFAULT 'none';
    -- none | predicted | confirmed | conflict (소스 불일치)
ALTER TABLE games ADD COLUMN IF NOT EXISTS lineup_confirmed_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS lineups (
    id           BIGSERIAL PRIMARY KEY,
    game_id      BIGINT      NOT NULL REFERENCES games (id) ON DELETE CASCADE,
    side         TEXT        NOT NULL,              -- 'home' | 'away'
    status       TEXT        NOT NULL,              -- 'predicted' | 'confirmed'
    source       TEXT        NOT NULL,              -- 'statsapi' | 'research' | 'grok'
    starter      TEXT,                              -- 실제 등판 선발 (probablePitcher가 아님)
    batting_order JSONB,                            -- 타순 9명 (이름 배열)
    scratches    JSONB,                             -- 결장자 이름 배열
    captured_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (game_id, side, source, status)
);

CREATE INDEX IF NOT EXISTS idx_lineups_game ON lineups (game_id);

CREATE TABLE IF NOT EXISTS odds_snapshots (
    id          BIGSERIAL PRIMARY KEY,
    game_id     BIGINT      NOT NULL REFERENCES games (id) ON DELETE CASCADE,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    book        TEXT        NOT NULL,               -- 'draftkings', 'fanduel', ...
    market      TEXT        NOT NULL,               -- 'h2h' | 'spreads' | 'totals'
    side        TEXT        NOT NULL,               -- 팀명 | 'Over' | 'Under'
    line        NUMERIC,                            -- 핸디캡/토탈 라인 (h2h는 NULL)
    odds        NUMERIC     NOT NULL                -- decimal odds
);

CREATE INDEX IF NOT EXISTS idx_odds_snapshots_game ON odds_snapshots (game_id, captured_at);

CREATE TABLE IF NOT EXISTS expert_picks (
    id         BIGSERIAL PRIMARY KEY,
    game_id    BIGINT      NOT NULL REFERENCES games (id) ON DELETE CASCADE,
    expert     TEXT        NOT NULL,
    site       TEXT        NOT NULL,                -- 'Covers', 'RotoWire', ...
    source_url TEXT,
    pick       TEXT        NOT NULL,                -- 'h2h:New York Yankees' 등 정규화 포맷
    reasoning  TEXT,
    record     TEXT,                                -- 소스가 밝힌 전적 문자열 (예: '61-42')
    odds       NUMERIC,                             -- 픽 수집 시점의 decimal 배당 (ROI 계산용)
    result     TEXT,                                -- NULL | 'win' | 'loss' | 'push'
    picked_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_expert_picks_game ON expert_picks (game_id);
-- 파이프라인 재실행 시 같은 픽 중복 적재 방지 (저장은 ON CONFLICT DO NOTHING)
CREATE UNIQUE INDEX IF NOT EXISTS uq_expert_picks
    ON expert_picks (game_id, expert, site, pick);

CREATE TABLE IF NOT EXISTS predictions (
    id         BIGSERIAL PRIMARY KEY,
    game_id    BIGINT      NOT NULL REFERENCES games (id) ON DELETE CASCADE,
    pick       TEXT        NOT NULL,                -- 'h2h:팀' | 'spreads:팀:-1.5' | 'totals:Over:8.5'
    model_p    NUMERIC     NOT NULL,                -- 앙상블 최종 확률 p_final
    odds       NUMERIC     NOT NULL,
    ev         NUMERIC     NOT NULL,
    kelly      NUMERIC     NOT NULL,                -- 하프 켈리, 뱅크롤 5% 상한
    p_market   NUMERIC,                             -- 픽 시점 시장 확률 (λ 재추정용)
    p_ensemble NUMERIC,                             -- 수축 전 앙상블 확률 (λ 재추정용)
    result     TEXT,                                -- NULL | 'win' | 'loss' | 'push'
    pnl        NUMERIC,                             -- 1유닛 기준 손익 (win: odds-1, loss: -1, push: 0)
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_predictions_game ON predictions (game_id);

-- [2] 픽 시점의 라인업 상태 — 예비 픽과 최종 픽을 구분해 채점한다
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS lineup_status TEXT NOT NULL DEFAULT 'none';
-- [6] 병렬 채점: 경기력 기반(model_p)과 시장 반영(p_legacy) 두 방식을 함께 기록해
--     2~3주 뒤 어느 쪽이 실제로 맞히는지 판별한다.
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS p_legacy NUMERIC;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS method TEXT NOT NULL DEFAULT 'performance';

-- [§6-4] 세 방식의 확률을 한 행에 함께 기록해 실전 결과로 비교한다.
--   p_heuristic = 임의 계수 λ 모델 / p_learned = 학습 계수 λ 모델 / p_claude = 판정
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS p_heuristic NUMERIC;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS p_learned NUMERIC;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS p_claude NUMERIC;

-- [§8-11] CLV(마감 배당 대비 가치). 장기 수익성의 **가장 이른 신호**다 —
--   적중률은 표본 200~300건 전에는 잡음이지만, CLV는 픽마다 즉시 측정된다.
--   우리가 잡은 배당이 마감 배당보다 좋았다면(= 시장이 우리 쪽으로 움직였다면)
--   그 픽은 결과와 무관하게 '시장보다 먼저 봤다'는 증거다.
--   closing_odds는 킥오프 **직전 마지막 스냅샷**에서 채점 시점에 역산한다
--   (별도 잡 불필요 — odds_snapshots에 이미 시계열이 쌓인다).
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS closing_odds NUMERIC;

-- [§8-18] 예상 총득점(λ 합계). **점수 오차(MAE)를 재는 유일한 근거다.**
--   승패 적중률만으로는 "몇 점이나 날지"를 우리가 맞히는지 알 수 없다.
--   돈·시장 지표를 전부 뺀 뒤 남은 평가 축이 ①방향 적중률 ②점수 MAE 두 개다.
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS lam_total NUMERIC;

-- [§8-38] 배당 의존을 제거(§8-18)했으므로 **배당 없이도 예측을 기록**할 수 있어야
--   한다. odds/ev/kelly가 NOT NULL이면 배당 미수집 마켓이 통째로 기록에서 빠지고,
--   그러면 임계값을 실측으로 정할 표본이 반쪽이 된다.
ALTER TABLE predictions ALTER COLUMN odds  DROP NOT NULL;
ALTER TABLE predictions ALTER COLUMN ev    DROP NOT NULL;
ALTER TABLE predictions ALTER COLUMN kelly DROP NOT NULL;

-- CLV 원장: 마감 대비 우리 배당의 우위. beat_close = 마감보다 좋은 값을 잡은 픽.
--   clv_pct = 확률 환산 차이 (1/odds - 1/closing) — 양수면 우리가 유리한 가격을 잡았다.
CREATE OR REPLACE VIEW clv_ledger AS
SELECT
    p.method,
    count(*)                                                          AS picks_with_close,
    count(*) FILTER (WHERE p.odds > p.closing_odds)                   AS beat_close,
    round(avg(1.0 / p.closing_odds - 1.0 / p.odds)::numeric, 5)       AS clv_avg,
    round((count(*) FILTER (WHERE p.odds > p.closing_odds))::numeric
          / NULLIF(count(*), 0), 4)                                   AS beat_close_rate,
    round(avg(p.pnl)::numeric, 4)                                     AS pnl_avg
FROM predictions p
WHERE p.closing_odds IS NOT NULL AND p.closing_odds > 0 AND p.odds > 0
GROUP BY p.method;

-- 전문가별 적중률·ROI 집계. ROI는 1유닛 플랫 베팅 기준, 배당 없으면 -110(1.91) 가정.
CREATE OR REPLACE VIEW expert_ledger AS
SELECT
    expert,
    count(*)                                                        AS picks_total,
    count(*) FILTER (WHERE result = 'win')                          AS wins,
    count(*) FILTER (WHERE result = 'loss')                         AS losses,
    count(*) FILTER (WHERE result = 'push')                         AS pushes,
    CASE WHEN count(*) FILTER (WHERE result IN ('win', 'loss')) > 0
         THEN round(count(*) FILTER (WHERE result = 'win')::numeric
              / count(*) FILTER (WHERE result IN ('win', 'loss')), 4)
    END                                                             AS hit_rate,
    CASE WHEN count(*) FILTER (WHERE result IN ('win', 'loss')) > 0
         THEN round(sum(CASE WHEN result = 'win'  THEN coalesce(odds, 1.91) - 1
                             WHEN result = 'loss' THEN -1
                             ELSE 0 END)
              / count(*) FILTER (WHERE result IN ('win', 'loss')), 4)
    END                                                             AS roi,
    count(*) FILTER (WHERE result IN ('win', 'loss')
                     AND picked_at >= now() - interval '90 days')   AS graded_90d,
    CASE WHEN count(*) FILTER (WHERE result IN ('win', 'loss')
                               AND picked_at >= now() - interval '90 days') > 0
         THEN round(sum(CASE WHEN picked_at < now() - interval '90 days' THEN 0
                             WHEN result = 'win'  THEN coalesce(odds, 1.91) - 1
                             WHEN result = 'loss' THEN -1
                             ELSE 0 END)
              / count(*) FILTER (WHERE result IN ('win', 'loss')
                                 AND picked_at >= now() - interval '90 days'), 4)
    END                                                             AS roi_90d
FROM expert_picks
GROUP BY expert;

-- ─────────────────────────────────────────────────────────────────────────
-- [#63] 칸별 사후 채점 — 2단 해석봇의 ▲▼를 경기 결과와 대조한다.
--
--   목적은 하나: **"▲를 준 팀이 실제로 이겼는가"를 칸별로 집계**해
--   5칸 중 어느 칸이 진짜 신호이고 어느 칸이 잡음인지 2주 뒤에 판별하는 것.
--
--   ⚠️ predictions에 넣지 않는다. 저 표는 픽 단위(마켓·배당·손익)이고
--      이건 (경기 × 팀 × 칸) 단위다. 억지로 합치면 둘 다 못 쓴다.
CREATE TABLE IF NOT EXISTS cell_verdicts (
    id          BIGSERIAL PRIMARY KEY,
    game_id     BIGINT      NOT NULL REFERENCES games (id) ON DELETE CASCADE,
    side        TEXT        NOT NULL,          -- 'home' | 'away'
    team        TEXT,                          -- 표시용 팀명(한글)
    cell        TEXT        NOT NULL,          -- bullpen | starter | batting | recent3 | weight
    symbol      TEXT        NOT NULL,          -- ▲ | ▼ | =
    reason      TEXT,                          -- 인용 근거 (칸 사실 인용 강제 통과분)
    fact_count  INT         NOT NULL DEFAULT 0,-- 그 칸이 몇 개의 사실 위에 서 있었나
    model       TEXT,                          -- 판정에 쓰인 provider/model
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (game_id, side, cell)               -- 재판정하면 최신 판정으로 덮는다
);

CREATE INDEX IF NOT EXISTS idx_cell_verdicts_game ON cell_verdicts (game_id);

-- 칸별 적중률. ▲를 준 쪽이 이겼으면 hit, 졌으면 miss, 무승부는 push.
--   '=' 판정은 방향을 걸지 않았으므로 적중률 분모에서 뺀다(따로 센다).
CREATE OR REPLACE VIEW cell_ledger AS
WITH graded AS (
    SELECT v.cell, v.symbol, g.sport,
           CASE WHEN g.home_score = g.away_score THEN 'push'
                WHEN (v.side = 'home') = (g.home_score > g.away_score)
                     THEN CASE v.symbol WHEN '▲' THEN 'hit'
                                        WHEN '▼' THEN 'miss' END
                ELSE      CASE v.symbol WHEN '▲' THEN 'miss'
                                        WHEN '▼' THEN 'hit'  END
           END AS outcome
    FROM cell_verdicts v
    JOIN games g ON g.id = v.game_id
    WHERE g.status = 'final'
      AND g.home_score IS NOT NULL AND g.away_score IS NOT NULL
)
SELECT cell, sport,
       count(*) FILTER (WHERE outcome IN ('hit', 'miss'))          AS decided,
       count(*) FILTER (WHERE outcome = 'hit')                     AS hits,
       count(*) FILTER (WHERE outcome = 'push')                    AS pushes,
       count(*) FILTER (WHERE symbol = '=')                        AS neutrals,
       CASE WHEN count(*) FILTER (WHERE outcome IN ('hit', 'miss')) > 0
            THEN round(count(*) FILTER (WHERE outcome = 'hit')::numeric
                 / count(*) FILTER (WHERE outcome IN ('hit', 'miss')), 4)
       END                                                          AS hit_rate
FROM graded
GROUP BY cell, sport;

-- [§9-6번째 칸] 득점 환경 채점 — **승패 칸과 분리해서 센다.**
--   "다득점 예상"이 실제로 오버였는지는 "▲를 준 팀이 이겼는지"와 다른 질문이고,
--   같은 표에 섞으면 어느 쪽이 맞았는지 알 수 없다.
--
--   ⚠️ 기준선은 **그 경기의 카드 기준 총득점**(expected_total)이다. 시장 라인이
--      아니다 — KBO·NPB는 배당을 수집하지 않으므로 시장 라인이 없다.
--      비교 대상이 없으면 채점하지 않는다(ref_total IS NULL).
ALTER TABLE cell_verdicts ADD COLUMN IF NOT EXISTS ref_total NUMERIC;

CREATE OR REPLACE VIEW scoring_ledger AS
WITH graded AS (
    SELECT v.symbol AS level, g.sport, v.ref_total,
           (g.home_score + g.away_score)::numeric AS actual,
           CASE
             WHEN v.ref_total IS NULL THEN NULL
             WHEN (g.home_score + g.away_score) = v.ref_total THEN 'push'
             WHEN v.symbol = '다득점 예상'
                  THEN CASE WHEN (g.home_score + g.away_score) > v.ref_total
                            THEN 'hit' ELSE 'miss' END
             WHEN v.symbol = '저득점 예상'
                  THEN CASE WHEN (g.home_score + g.away_score) < v.ref_total
                            THEN 'hit' ELSE 'miss' END
           END AS outcome
    FROM cell_verdicts v
    JOIN games g ON g.id = v.game_id
    WHERE v.cell = 'scoring'
      AND g.status = 'final'
      AND g.home_score IS NOT NULL AND g.away_score IS NOT NULL
)
SELECT sport, level,
       count(*) FILTER (WHERE outcome IN ('hit', 'miss'))  AS decided,
       count(*) FILTER (WHERE outcome = 'hit')             AS hits,
       count(*) FILTER (WHERE outcome = 'push')            AS pushes,
       count(*) FILTER (WHERE ref_total IS NULL)           AS ungradable,
       round(avg(actual), 2)                               AS avg_actual,
       round(avg(ref_total), 2)                            AS avg_ref,
       CASE WHEN count(*) FILTER (WHERE outcome IN ('hit', 'miss')) > 0
            THEN round(count(*) FILTER (WHERE outcome = 'hit')::numeric
                 / count(*) FILTER (WHERE outcome IN ('hit', 'miss')), 4)
       END                                                  AS hit_rate
FROM graded
GROUP BY sport, level;

-- ─────────────────────────────────────────────────────────────────────────
-- [§9-라인업 의도] 라인업 **변경 이력** — 언제 무엇이 바뀌었는가.
--
--   `lineups`는 (game_id, side, source, status) 유일 제약이라 **최종 상태 1행**만
--   남는다. "18:05에 4번 타자가 빠졌다"는 그 자체로 신호인데, 덮어쓰면 사라진다.
--   → 관측할 때마다 append 한다. 같은 내용이 반복되면 넣지 않는다(폴링 잡음 제거).
CREATE TABLE IF NOT EXISTS lineup_events (
    id           BIGSERIAL PRIMARY KEY,
    game_id      BIGINT      NOT NULL REFERENCES games (id) ON DELETE CASCADE,
    side         TEXT        NOT NULL,          -- 'home' | 'away'
    team         TEXT,                          -- 표시용
    batting_order JSONB      NOT NULL,          -- ["이름(포지션)", ...]
    starter      TEXT,
    source       TEXT        NOT NULL DEFAULT 'crawler',
    is_final     BOOLEAN     NOT NULL DEFAULT false,  -- 경기 30분 전 확정본인가
    observed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (game_id, side, batting_order)       -- 같은 라인업을 두 번 적지 않는다
);

CREATE INDEX IF NOT EXISTS idx_lineup_events_game ON lineup_events (game_id, side);
CREATE INDEX IF NOT EXISTS idx_lineup_events_team ON lineup_events (team, observed_at DESC);

-- [§9-라인업 의도] 변경 유형별 채점.
--   ⚠️ **유형별로 나눠 센다.** "라인업 변경"을 한 덩어리로 세면 주전 결장과
--      타순 강등이 섞여, 무엇이 실제로 승패를 설명하는지 영영 알 수 없다.
CREATE TABLE IF NOT EXISTS lineup_verdicts (
    id          BIGSERIAL PRIMARY KEY,
    game_id     BIGINT      NOT NULL REFERENCES games (id) ON DELETE CASCADE,
    side        TEXT        NOT NULL,
    team        TEXT,
    change_type TEXT        NOT NULL,   -- regular_out | order_demote | bullpen_out | new_starter | dh_rest | position_change
    cell        TEXT        NOT NULL,   -- 어느 칸에 반영됐나
    symbol      TEXT        NOT NULL,   -- ▲ | ▼ | =
    scoring_dir TEXT,                   -- 다득점 | 저득점 | 중립 (득점 환경 방향)
    detail      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (game_id, side, change_type)
);

-- 유형별 승패 적중률 — ▼로 읽은 팀이 실제로 졌는가.
CREATE OR REPLACE VIEW lineup_type_ledger AS
WITH graded AS (
    SELECT v.change_type, v.cell, v.symbol, g.sport,
           CASE WHEN g.home_score = g.away_score THEN 'push'
                WHEN (v.side = 'home') = (g.home_score > g.away_score)
                     THEN CASE v.symbol WHEN '▲' THEN 'hit' WHEN '▼' THEN 'miss' END
                ELSE      CASE v.symbol WHEN '▲' THEN 'miss' WHEN '▼' THEN 'hit' END
           END AS outcome
    FROM lineup_verdicts v
    JOIN games g ON g.id = v.game_id
    WHERE g.status = 'final'
      AND g.home_score IS NOT NULL AND g.away_score IS NOT NULL
)
SELECT sport, change_type, cell,
       count(*) FILTER (WHERE outcome IN ('hit', 'miss')) AS decided,
       count(*) FILTER (WHERE outcome = 'hit')            AS hits,
       count(*) FILTER (WHERE outcome = 'push')           AS pushes,
       CASE WHEN count(*) FILTER (WHERE outcome IN ('hit', 'miss')) > 0
            THEN round(count(*) FILTER (WHERE outcome = 'hit')::numeric
                 / count(*) FILTER (WHERE outcome IN ('hit', 'miss')), 4)
       END                                                AS hit_rate
FROM graded
GROUP BY sport, change_type, cell;

-- [9] 득점 방향 적중률 — 저득점 신호로 읽었을 때 실제로 언더였는가.
--   ⚠️ 승패 채점과 **완전히 분리**한다. 라인업 의도가 승패보다 총득점을 더 잘
--      설명한다면 그것이 이 시스템에서 가장 값진 발견이므로, 섞어서 흐리면 안 된다.
CREATE OR REPLACE VIEW lineup_scoring_ledger AS
WITH graded AS (
    SELECT v.change_type, v.scoring_dir, g.sport,
           s.ref_total,
           CASE
             WHEN s.ref_total IS NULL THEN NULL
             WHEN (g.home_score + g.away_score) = s.ref_total THEN 'push'
             WHEN v.scoring_dir = '다득점'
                  THEN CASE WHEN (g.home_score + g.away_score) > s.ref_total
                            THEN 'hit' ELSE 'miss' END
             WHEN v.scoring_dir = '저득점'
                  THEN CASE WHEN (g.home_score + g.away_score) < s.ref_total
                            THEN 'hit' ELSE 'miss' END
           END AS outcome
    FROM lineup_verdicts v
    JOIN games g ON g.id = v.game_id
    LEFT JOIN cell_verdicts s
           ON s.game_id = v.game_id AND s.cell = 'scoring'
    WHERE v.scoring_dir IN ('다득점', '저득점')
      AND g.status = 'final'
      AND g.home_score IS NOT NULL AND g.away_score IS NOT NULL
)
SELECT sport, change_type, scoring_dir,
       count(*) FILTER (WHERE outcome IN ('hit', 'miss')) AS decided,
       count(*) FILTER (WHERE outcome = 'hit')            AS hits,
       count(*) FILTER (WHERE outcome = 'push')           AS pushes,
       count(*) FILTER (WHERE ref_total IS NULL)          AS ungradable,
       CASE WHEN count(*) FILTER (WHERE outcome IN ('hit', 'miss')) > 0
            THEN round(count(*) FILTER (WHERE outcome = 'hit')::numeric
                 / count(*) FILTER (WHERE outcome IN ('hit', 'miss')), 4)
       END                                                AS hit_rate
FROM graded
GROUP BY sport, change_type, scoring_dir;

-- [§9-투수 맞대결] 등판 단위 로그. 타석 단위(누가 누구에게)는 소스에 없다.
--   실측 2026-08-28: KBO 공식 arrPitcher · 네이버 pitchersBoxscore 경기값
--   (inn/pa/hit/er/r) · NPB Yahoo /stats (投球回/打者/自責点).
--   시즌 ERA(평균자책점·防御率)는 이 표에 넣지 않는다 — last5 오표기 사고와 같다.
CREATE TABLE IF NOT EXISTS pitcher_appearances (
    id          BIGSERIAL PRIMARY KEY,
    game_id     BIGINT      NOT NULL REFERENCES games (id) ON DELETE CASCADE,
    sport       TEXT        NOT NULL,
    team        TEXT        NOT NULL,
    opponent    TEXT        NOT NULL,
    pitcher     TEXT        NOT NULL,
    is_starter  BOOLEAN     NOT NULL,
    innings     DOUBLE PRECISION,
    batters     INT,          -- 그 경기 상대 타자 수 (TBF)
    hits        INT,
    hr          INT,
    k           INT,
    bb          INT,
    r           INT,
    er          INT,
    source      TEXT        NOT NULL,
    UNIQUE (game_id, team, pitcher)
);

CREATE INDEX IF NOT EXISTS idx_pitcher_appearances_lookup
    ON pitcher_appearances (sport, pitcher);


-- ─────────────────────────────────────────────────────────── 픽 레저 (v1.1 0단계)
--
-- 판정 전건을 영구 보존한다. **TTL 없는 DB 테이블이어야 한다** — Redis 키로
-- 만들면 캘리브레이션 표본이 조용히 증발한다.
--
-- ⚠️ 이 표는 **측정용이며 판정 입력이 아니다.** 어떤 판정 경로도 이 표를 읽지
--    않는다. 임계값 재검토는 표본이 쌓인 뒤 사용자 지시로만 한다.
--
-- 발송 여부와 무관하게 기록한다 — 보드만·거부권 탈락 경기가 캘리브레이션
-- 데이터의 절반이다. 그 경기들의 원판정이 맞았는지를 봐야 거부권이 옳은지 안다.
--
-- 컬럼명은 ASCII로 둔다(지시문의 `우세`→favored, `확신도`→confidence).
-- 한글 식별자는 따옴표 없이는 못 쓰고 도구 호환도 나쁘다.
CREATE TABLE IF NOT EXISTS pick_ledger (
    id            BIGSERIAL PRIMARY KEY,
    game_id       BIGINT      NOT NULL REFERENCES games (id) ON DELETE CASCADE,
    sport         TEXT        NOT NULL,
    league        TEXT,
    date          TEXT        NOT NULL,   -- 슬레이트 날짜 (표시 기준)
    judged_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- 판정
    p_home        DOUBLE PRECISION,       -- 홈 승률 (클립 후 최종값)
    favored       TEXT,                   -- 우세: home | away | 박빙
    confidence    TEXT,                   -- 확신도: 상 | 중 | 하
    lineup_status TEXT,
    gate_result   TEXT,                   -- 엣지/추천/가치주의/보드만/거부권탈락/가치탈락/재량
    model         TEXT,

    -- 시장 (4·5단계 전에는 전부 NULL — 0단계를 위해 배당 수집을 앞당기지 않는다)
    odds          DOUBLE PRECISION,
    market_prob   DOUBLE PRECISION,
    divergence_pp DOUBLE PRECISION,
    edge_status   TEXT,                   -- none | candidate | confirmed | rejected

    -- 이력
    rejudge_count INT         NOT NULL DEFAULT 0,
    is_final      BOOLEAN     NOT NULL DEFAULT TRUE,
    trial         BOOLEAN     NOT NULL DEFAULT FALSE,  -- 시범 운영 등급(축구)
    -- 중복 경기 병합으로 옮겨온 행이면 원래 game_id. 캘리브레이션이 이력 행을
    -- 어떻게 다룰지 판단하는 근거다 — "왜 is_final=false인가"가 재판정 때문인지
    -- 병합 때문인지 구분되지 않으면 표본을 어떻게 셀지 정할 수 없다.
    merged_from   BIGINT,

    -- 채점 (finals 적재 잡이 채운다)
    final_score   TEXT,
    winner        TEXT,                   -- home | away | draw
    hit           BOOLEAN,
    void          BOOLEAN     NOT NULL DEFAULT FALSE,
    graded_at     TIMESTAMPTZ
);

-- 경기·날짜당 최종 판정은 하나뿐이다. 재판정은 옛 행을 is_final=false로 내리고
-- 새 행을 올린다 — 이 부분 유니크 인덱스가 그 규칙을 DB에서 강제한다.
CREATE UNIQUE INDEX IF NOT EXISTS idx_pick_ledger_final
    ON pick_ledger (game_id, date) WHERE is_final;

CREATE INDEX IF NOT EXISTS idx_pick_ledger_grade
    ON pick_ledger (graded_at) WHERE graded_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_pick_ledger_calib
    ON pick_ledger (sport, date);

-- 🔴 **이미 만들어진 표에는 CREATE TABLE 의 컬럼 변경이 반영되지 않는다.**
--    새 컬럼은 반드시 ALTER 로 따로 적는다 (이 파일의 games·predictions 관례).
--    실사고 2026-08-31: merged_from 을 CREATE TABLE 안에만 넣고 배포했더니
--    운영에서 "column merged_from does not exist" 가 났고, 그 컬럼을 쓰는
--    중복 병합 이관이 조용히 죽을 뻔했다.
ALTER TABLE pick_ledger ADD COLUMN IF NOT EXISTS merged_from BIGINT;

-- 시범 운영 등급 판정(축구 trial mode). 캘리브레이션에서 야구와 **분리 집계**한다 —
-- 검증된 파이프라인과 시범 경로의 성적을 한 표에 섞으면 둘 다 못 믿게 된다.
ALTER TABLE pick_ledger ADD COLUMN IF NOT EXISTS trial BOOLEAN NOT NULL DEFAULT FALSE;

-- [운영 안정화 0a · 2026-09-02] 하이픈 실명이 타순을 쪼갠 오염 행 표시.
--   `Pete Crow-Armstrong` 같은 이름이 `order.split("-")` 에 두 조각으로 갈려
--   저장된 배열이 10칸이 됐다. 슬롯이 통째로 밀려 라인업 의도·T5 가 없는
--   '타순 이동'을 신호로 읽었다 (실측 2026-09-02: MLB 153건).
--   재파싱으로 9명이 복원되면 고치고, 안 되면 여기에 표시해 **판정에서 뺀다.**
ALTER TABLE lineup_events ADD COLUMN IF NOT EXISTS contaminated BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE lineups       ADD COLUMN IF NOT EXISTS contaminated BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS idx_lineup_events_clean ON lineup_events (game_id, side) WHERE NOT contaminated;

-- [무과금 전환 · 2026-09-02] 배당 소스 구분. The Odds API 폐기 후 무료 3원 체계:
--   'espn'    ESPN Core API (MLB, 무인증·무제한)      1순위
--   'sharp'   SharpAPI 무료 티어 (MLB 교차검증·폴백)   2순위
--   'betman'  배트맨 프로토 (KBO·NPB·MLB, 국내 합법)   아시아
--   'theodds' The Odds API (유료, 비활성 — 코드 보존)
-- 가치 게이트는 소스를 구분하지 않는다. 같은 로직이다.
ALTER TABLE odds_snapshots ADD COLUMN IF NOT EXISTS provider TEXT NOT NULL DEFAULT 'theodds';
CREATE INDEX IF NOT EXISTS idx_odds_snapshots_provider
    ON odds_snapshots (provider, captured_at DESC);
