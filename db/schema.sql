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


-- ─────────────────────────────────────────── 타자 개인 성적 (BAT-1 2026-09-08)
--
-- 🔴 **판정 재료의 절반이 비어 있었다.** 투수는 자료4·9·10·14 에 개인 경기별
--    로그가 있는데, 타자는 자료1(팀 3경기 합계)과 자료3(**이름·포지션뿐, 숫자 0**)
--    이 전부였다. 프롬프트가 그 빈자리를 "순서가 곧 정보다"로 메운다.
--    실측 2026-09-08 (경기 단위, 157경기, 기준 54.8%):
--      잠정(투수 재료만으로 낸 1차)  27경기  70.4%
--      확정(라인업 받고 재판정)     130경기  51.5%
--    이름 아홉 개가 도착해 재판정을 촉발하고, 그 재판정이 예측을 나쁘게 했다.
--
-- 🔴 수집원이 없는 게 아니라 **이미 손에 들어오는 것을 버리고 있었다** —
--    MLB statsapi 는 선수별 batting 을 응답에 담아 보내는데 투수만 읽었다.
--
-- ⚠️ `pitcher_appearances` 와 **같은 모양**으로 둔다. 그래야 `starter_recent` 와
--    같은 규약으로 읽을 수 있다(사본 금지).
-- ⚠️ `ON DELETE CASCADE` 다 — GM-2 가 이관 목록을 카탈로그에서 읽으므로
--    코드를 고치지 않아도 병합 때 옮겨진다.
CREATE TABLE IF NOT EXISTS batter_appearances (
    id          BIGSERIAL PRIMARY KEY,
    game_id     BIGINT      NOT NULL REFERENCES games (id) ON DELETE CASCADE,
    sport       TEXT        NOT NULL,
    team        TEXT        NOT NULL,
    opponent    TEXT        NOT NULL,
    batter      TEXT        NOT NULL,
    slot        INT,          -- 타순 1~9 (교체는 선발 슬롯으로 읽는다)
    pos         TEXT,
    ab          INT,          -- 타수. **없으면 행을 만들지 않는다** (대주자·투수)
    h           INT,
    r           INT,
    rbi         INT,
    hr          INT,
    bb          INT,
    so          INT,
    source      TEXT        NOT NULL,
    UNIQUE (game_id, team, batter)
);

CREATE INDEX IF NOT EXISTS idx_batter_appearances_lookup
    ON batter_appearances (sport, batter);


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
-- 🔴 [LED-1 2026-09-10] 한 경기에 최종 판정은 **하나**다.
--    종전 `(game_id, date)` 는 같은 경기가 다른 슬레이트 날짜로 들어오면
--    통과시켰다 — 실측 잉여 10건, 그중 방향이 반대인 쌍도 있었다.
--    ⚠️ 이 인덱스는 중복이 남아 있으면 **생성에 실패한다.** 백필
--       (tools/backfill_ledger.py --led1)이 먼저 돌아야 한다.
-- [CLV-1 2026-09-13] 판정의 값어치를 재는 유일한 지표. **저장 전용이다.**
--   🔴 §4-1 "배당은 판정·폼·서술의 입력에 절대 넣지 않는다" 는 그대로다.
--      여기 담긴 값을 판정 경로가 읽으면 안 된다(계약이 전수 grep 으로 막는다).
--   실측(운영 원장 178경기): 판정 확률 AUC 0.5122 · 브라이어 0.2537
--   (50%로 찍는 것보다 나쁘다) / 시장 확률 AUC 0.6421 — 유일하게 유의.
--   적중률만으로는 판정이 시장보다 나은지 알 수 없다.
--   ⚠️ 기존 odds·market_prob 는 **한 시점**의 값이다(_fill_market 이 나중에
--      채운다). 판정 시각과 마감 시각을 나눠 두 번 남겨야 차이가 계산된다.
ALTER TABLE pick_ledger ADD COLUMN IF NOT EXISTS odds_at_verdict DOUBLE PRECISION;
ALTER TABLE pick_ledger ADD COLUMN IF NOT EXISTS odds_closing    DOUBLE PRECISION;
ALTER TABLE pick_ledger ADD COLUMN IF NOT EXISTS clv             DOUBLE PRECISION;

CREATE UNIQUE INDEX IF NOT EXISTS idx_pick_ledger_final
    ON pick_ledger (game_id) WHERE is_final;

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

-- [확신도 후보 2026-09-07] 확신도를 무엇으로 정할지 **아직 정하지 않았다.**
--   자기신고(`confidence`)는 그대로 게이트를 움직이고, 이 칸은 후보들을
--   나란히 새기기만 한다 — 2주 뒤 SEND 데이터로 대조해 고른다.
--   🔴 게이트는 이 칸을 읽지 않는다. 계약 테스트가 강제한다.
ALTER TABLE pick_ledger ADD COLUMN IF NOT EXISTS confidence_probe JSONB;

-- [BLD-1 2026-09-11] PL-1 섀도 앙상블. **기록 전용** — 카드·게이트가 읽지 않는다.
--   판정 AUC 0.470~0.519 vs 단순 Elo 0.558(2026-09-08 실측). 섞는 것이 나은지
--   재려면 매 판정에 섞은 값이 남아 있어야 한다. 가중 0.3/0.5/0.7 세 값.
ALTER TABLE pick_ledger ADD COLUMN IF NOT EXISTS shadow_blend JSONB;
-- [ORD-3 2026-09-11] 새 순서 판정의 출력은 **승자 하나**다(확률 없음).
--   확률이 없는 판정도 원장에 남아야 채점이 된다 — 없으면 이 방식이 맞는지
--   영영 못 잰다. 종전 경로는 이 칸이 NULL 이고 아무것도 바뀌지 않는다.
-- ⚠️ `winner` 가 아니라 `predicted_side` 다 — `winner` 는 채점 때 채우는
--    **실제 승자**(home|away|draw)로 이미 쓰이고 있다. 같은 칸에 두 뜻을
--    담으면 채점이 제 예측을 정답으로 덮어쓴다.
ALTER TABLE pick_ledger ADD COLUMN IF NOT EXISTS predicted_side TEXT;

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

-- [감시 3층 · 2026-09-03] 판정 산출물을 **사후에** 읽는 기록 테이블.
--   🔴 판정 경로는 이 테이블을 읽지 않는다 — 감시가 판정에 되먹임되면
--      그 순간 감시가 아니라 입력이 된다.
CREATE TABLE IF NOT EXISTS judgement_audit (
    id            BIGSERIAL PRIMARY KEY,
    game_id       BIGINT      NOT NULL,
    sport         TEXT        NOT NULL,
    judged_at     TIMESTAMPTZ,
    verified_n    INT         NOT NULL DEFAULT 0,
    derived_n     INT         NOT NULL DEFAULT 0,
    not_found_n   INT         NOT NULL DEFAULT 0,   -- 환각 후보 (확정 아님)
    mismatch_n    INT         NOT NULL DEFAULT 0,   -- 같은 단위 값이 다름
    mismatch_detail JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- [FA-2 2026-09-11] 변수 조건절(가정값)은 감사하지 않는다. 다만 **몇 개였는지**
--   남긴다 — 전후 측정에서 verified 가 17 줄었고 그 전부가 이 자리였다.
--   칸이 없으면 다음 사람은 그 감소를 설명할 수 없다(조용한 손실 금지).
ALTER TABLE judgement_audit ADD COLUMN IF NOT EXISTS condition_n INT NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_judgement_audit_sport
    ON judgement_audit (sport, judged_at DESC);

CREATE TABLE IF NOT EXISTS judge_review (
    id           BIGSERIAL PRIMARY KEY,
    game_id      BIGINT      NOT NULL,
    sport        TEXT        NOT NULL,
    objections   JSONB,
    objection_n  INT         NOT NULL DEFAULT 0,
    valid_n      INT         NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_judge_review_sport ON judge_review (sport, created_at DESC);

CREATE TABLE IF NOT EXISTS shadow_panel (
    id          BIGSERIAL PRIMARY KEY,
    game_id     BIGINT      NOT NULL,
    sport       TEXT        NOT NULL,
    p_main      NUMERIC,
    p_shadow    NUMERIC,
    divergence  NUMERIC,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_shadow_panel_sport ON shadow_panel (sport, created_at DESC);


-- ── [C3 2026-09-03] 변수 정량화 원장 ─────────────────────────────
-- 🔴 변수가 "서술"이던 동안에는 맞았는지 틀렸는지 **셀 수 없었다.**
--    정량 형식(§변수 형식)으로 바뀐 뒤부터 주장(N·M)과 실측을 대조한다.
-- ⚠️ 파싱 실패도 행으로 남긴다 — `현실화='unverifiable'` + 원문 보존.
--    버리면 형식 위반이 얼마나 되는지 영영 모른다.
CREATE TABLE IF NOT EXISTS variable_ledger (
    id            BIGSERIAL PRIMARY KEY,
    game_id       BIGINT      NOT NULL REFERENCES games (id) ON DELETE CASCADE,
    sport         TEXT        NOT NULL,
    ledger_id     BIGINT      REFERENCES pick_ledger (id) ON DELETE SET NULL,
    raw           TEXT        NOT NULL,          -- 변수 원문 (형식 위반도 그대로)
    subject       TEXT,                          -- 주체: 선수명 | 팀명 | NULL
    subject_kind  TEXT,                          -- 'pitcher' | 'team' | NULL
    direction     TEXT,                          -- 'home' | 'away'
    claimed_n     NUMERIC,                       -- 발생 시 이동 %p
    claimed_m     NUMERIC,                       -- 현재 p 에 기반영 %p
    source_ref    TEXT,                          -- 근거 자료 번호
    realized      TEXT,                          -- NULL | 'true' | 'false' | 'unverifiable'
    actual        JSONB,                         -- 실측치
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    graded_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_variable_ledger_game
    ON variable_ledger (game_id);
CREATE INDEX IF NOT EXISTS idx_variable_ledger_pending
    ON variable_ledger (sport, graded_at) WHERE graded_at IS NULL;


-- ── [시장 기준선 2026-09-04] 우리 판정 vs 시장. **사후 전용.** ──────────
-- 🔴 배당은 판정 입력에 흐르지 않는다(CLAUDE.md 금지선). 이 표는 판정이
--    확정된 **뒤에** 시장과 나란히 놓고 나중에 누가 맞았는지 세기 위한 것이다.
-- ⚠️ 분모 정의: **발송된 경기만** 행이 생긴다. 취소·판정불가로 카드가 안 나간
--    경기는 행이 없다 — 시장과 우리를 같은 경기 집합에서 비교하기 위해서다.
CREATE TABLE IF NOT EXISTS market_baseline_ledger (
    id              BIGSERIAL PRIMARY KEY,
    game_id         BIGINT      NOT NULL REFERENCES games (id) ON DELETE CASCADE,
    sport           TEXT        NOT NULL,
    slate_date      TEXT        NOT NULL,
    provider        TEXT,
    p_market_send   NUMERIC,        -- 발송 시점 시장 확률(홈)
    p_market_close  NUMERIC,        -- 시작 직전 마지막 스냅샷 = 마감 근사
    market_favored  TEXT,           -- 'home' | 'away' | 'even'
    our_p           NUMERIC,        -- 그 시점 우리 p_home
    our_favored     TEXT,
    divergence      NUMERIC,        -- our_p - p_market_close
    market_hit      BOOLEAN,        -- 시장 우세가 맞았는가 (even/무승부는 NULL)
    our_hit         BOOLEAN,        -- pick_ledger 에서 **복사**한다 (재계산 금지)
    void            BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    graded_at       TIMESTAMPTZ,
    UNIQUE (game_id)
);
CREATE INDEX IF NOT EXISTS idx_market_baseline_pending
    ON market_baseline_ledger (sport, graded_at) WHERE graded_at IS NULL;

-- [투명 리포트 G1 2026-09-04] 경기 서사 원장.
--   경기 하나가 파이프라인을 어떻게 통과했는지 **시간순 한 테이블**로 남긴다.
--   🔴 **원장은 로그보다 많이 알면 안 된다.** 각 행의 `summary` 는 그 자리에서
--      이미 찍히는 로그 문자열을 **그대로 복사**한 것이다. 새 계측을 추가해
--      원장에만 있는 사실을 만들면, 리포트가 로그로 검증 불가능해진다.
--   ⚠️ 이 테이블은 **기록·표시 층**이다. 판정·게이트·발송은 이것을 읽지 않는다.
CREATE TABLE IF NOT EXISTS game_trace (
    id         BIGSERIAL   PRIMARY KEY,
    game_id    BIGINT      NOT NULL REFERENCES games (id) ON DELETE CASCADE,
    sport      TEXT        NOT NULL,
    slate_date TEXT        NOT NULL,          -- 슬레이트 날짜(표시용 KST 기준)
    stage      TEXT        NOT NULL,          -- 수집|조립|판정|재판정|딥서치|게이트|발송
    at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    summary    TEXT        NOT NULL,          -- 그 자리 로그 문자열 원문
    ref        JSONB                          -- 원문 참조(prompt_sha·캐시키 등)
);

CREATE INDEX IF NOT EXISTS idx_game_trace_game ON game_trace (game_id, at);
CREATE INDEX IF NOT EXISTS idx_game_trace_slate ON game_trace (sport, slate_date);
