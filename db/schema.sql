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
