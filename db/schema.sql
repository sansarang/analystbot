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
