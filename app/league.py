"""리그 파생 측정 — **규칙이 요구하는 숫자를 자료에서 계산한다.**

## 왜 이 파일이 생겼나

사용자 지시 2026-10-02 로 규칙 네 개가 바뀌었고(`questions/2026-10-02_rule_defects.md`),
그 규칙들이 **코드에 없는 숫자**를 요구한다:

| 규칙 | 요구하는 숫자 |
|---|---|
| §5-c-1 난타전(결함 4) | **리그 평균 총득점** + 여유 |
| §6-c-3 총점 기준선(결함 5) | **리그 평균 총득점** → 가장 가까운 `X.5` |
| §4 `home_field`(결함 2) | **홈/원정 쪼갠 승률·득점 차** |
| §4 `h2h_pattern`(결함 6) | **맞대결 최근 N경기 창** + 표본 수별 weight |

🔴 **값을 여기 적지 않는다.** 문턱·창·가중치는 `config/*.yaml` 이 원본이고 이 파일은
   **읽어서 계산만** 한다 — 두 곳에 적으면 갈린다(CLAUDE.md §사본 금지).

## 🔴 공통 꼴 — 종목마다 칸 이름이 달랐다

실측 2026-10-02: 같은 "순위" 질문인데 `fotmob` 은 `wins/draws/losses`, `mlb` 는
`w/d/l` 을 냈다. 그러면 단계 5~7 이 **종목별 분기**를 써야 하고, 분기는 한 종목이
바뀔 때 다른 종목을 조용히 깨뜨린다. 그래서 **한 꼴로 모은다.**

⚠️ 야구·하키에는 `draws` 가 없거나 뜻이 다르다(하키는 `ot_losses`). 없는 칸은
   **`None` 으로 남긴다** — 0 으로 때우면 "무승부가 0회"라는 거짓이 된다.
"""
from __future__ import annotations

import logging
import re

from app import rules

logger = logging.getLogger(__name__)

#: 🔴 순위표 한 줄의 **공통 꼴**. 종목 어댑터가 이 이름으로 낸다.
#   ⚠️ 없는 칸은 `None` — 0 으로 때우지 않는다(조용한 0 금지).
TABLE_FIELDS = ("team", "table", "rank", "played", "wins", "draws", "losses",
                "points", "goals_for", "goals_against", "goal_diff")


def avg_goals(rows: list[dict]) -> float | None:
    """리그 **경기당 평균 총득점**. 🔴 못 구하면 `None` — 지어내지 않는다.

    식: Σ 팀 득점 ÷ (Σ 팀 경기수 ÷ 2). 한 경기가 두 팀에 세어지므로 2 로 나눈다.

    실측 2026-10-02: MLS 3.22(동부 3.32·서부 3.13) · USL 2.73 · UEFA NL C2 2.50.
    ⚠️ **리그가 0.7골 차로 갈린다** — 그래서 문턱을 절대 숫자로 두면 어느 리그에서든
       틀린다(그 실수를 한 번 했다).
    """
    gf = gp = 0
    for r in rows or []:
        f, p = r.get("goals_for"), r.get("played")
        if f is None or not p:
            continue
        # 🔴 `int()` 로 깎지 않는다 — 실측값이 소수로 올 수 있다(평균을 미리 넣는 등)
        gf += float(f)
        gp += float(p)
    if gp < 2:
        return None
    return round(gf / (gp / 2), 3)


def baseline_total(rows: list[dict]) -> float | None:
    """§6-c-3 — 보드 없는 경기의 **총점 기준선.**

    🔴 **리그 평균에서 뽑는다.** v4 원문은 *"시나리오 스코어 최대합 + 0.5"* 였고
       그것은 **순환**이었다(기준선을 우리 시나리오에서 뽑으면 언더가 정의상 1.00).
    ⚠️ `X.5` 만 쓴다 — 정수 기준선은 밀어내기(push)가 생긴다.
    🔴 리그 평균을 못 구하면 `None` — 호출부가 **총점 마켓을 이름으로 적지 않는다**.
    """
    avg = avg_goals(rows)
    if avg is None:
        return None
    cfg = rules.total_baseline_cfg()
    step = float(cfg.get("round_to") or 0.5)
    # 🔴 가장 가까운 `X.5`. ⚠️ **파이썬 `round` 를 쓰지 않는다** — `round(2.5)` 가
    #    `2` 다(짝수 반올림). 그러면 평균이 딱 `3.00` 인 리그가 기준선 **2.5** 를
    #    받고, 그 선택이 코드에 숨는다(실측 2026-10-02 에 그렇게 걸렸다).
    #  🔴 동점 처리를 **yaml 이 정한다.** 기본은 `아래` — 결함 5 가 *"언더가 공짜로
    #     1.00 을 받는다"* 였으므로, 동점이면 언더가 **더 어려운** 쪽으로 둔다.
    import math
    k = (avg - step) / (2 * step)
    # 🔴 **동점 판정은 `k` 의 소수부가 정확히 0.5 인가**로 한다.
    #    ⚠️ `abs(k - round(k))` 로 재면 안 된다 — `round(2.5)` 가 `2` 라서(짝수
    #       반올림) 동점을 "동점 아님"으로 읽는다. 실측 2026-10-02 에 걸렸다.
    is_tie = abs((k % 1) - 0.5) < 1e-9
    if is_tie:
        n = math.floor(k) if str(cfg.get("tie_goes") or "아래") == "아래" \
            else math.ceil(k)
    else:
        n = math.floor(k + 0.5)
    return round(n * (2 * step) + step, 1)


def home_advantage(home: list[dict], away: list[dict]) -> dict | None:
    """§4 `home_field` — **홈/원정 쪼갠 표에서 홈 우위를 잰다.**

    실측 2026-10-02: MLS 동부 승률 **+16.8%p**·득점 **+0.46골**(홈 200경기) ·
    USL 동부 **+18.3%p**·**+0.50골**(169경기).

    🔴 쪼갠 표가 없으면 `None` — 그때는 `home_field` 변수를 **만들지 않는다**.
       (하키 `standings/now` 는 홈/원정을 안 준다. 있는 척하지 않는다.)
    """
    def agg(rows):
        w = p = gf = ga = 0
        # 🔴 **득점이 아예 없는 표가 있다**(야구 순위표 — 실측 2026-10-02).
        #    그때 `gf` 를 0 으로 합하면 `goals_delta` 가 **0.0** 이 되고, 그것은
        #    *"홈과 원정 득점이 같다"* 는 **거짓**이다. 못 잰 것은 `None` 으로 센다.
        seen_goals = False
        for r in rows or []:
            if not r.get("played"):
                continue
            w += int(r.get("wins") or 0)
            p += int(r.get("played") or 0)
            if r.get("goals_for") is not None:
                seen_goals = True
                gf += int(r.get("goals_for") or 0)
                ga += int(r.get("goals_against") or 0)
        return (w, p, gf if seen_goals else None,
                ga if seen_goals else None) if p else None

    h, a = agg(home), agg(away)
    if not (h and a):
        return None
    hw, hp, hgf, _ = h
    aw, ap, agf, _ = a
    return {
        "home_games": hp,
        "home_win_pct": round(100 * hw / hp, 1),
        "away_win_pct": round(100 * aw / ap, 1),
        # 🔴 **이 둘이 §4 `home_field` 의 근거다**
        "win_pct_delta": round(100 * (hw / hp - aw / ap), 1),
        # 🔴 득점을 못 잰 표면 **`None`** — 0.0 은 "같다"는 거짓이다
        "goals_delta": (round(hgf / hp - agf / ap, 2)
                        if (hgf is not None and agf is not None) else None),
    }


def h2h_window(matches: list[dict]) -> list[dict]:
    """§4 `h2h_pattern` — **최근 N경기만** 본다. N 은 yaml 이 정한다.

    ⚠️ 실측 2026-10-02: 시애틀–캔자스시티 맞대결 30경기를 전부 쓰면 경기당 총득점이
       **2.73** 인데 최근 10경기는 **3.40** 이다 — 옛 시대가 섞인다. 그래서 창을 둔다.
    🔴 입력이 **최신순**이라고 가정하지 않는다 — 날짜로 정렬한다. 순서를 가정하면
       조용히 가장 오래된 경기를 "최근"으로 읽는다.
    """
    cfg = rules.h2h_sample_cfg()
    n = _window_n(cfg)
    dated = [m for m in (matches or []) if m.get("date")]
    undated = [m for m in (matches or []) if not m.get("date")]
    if undated:
        logger.info("[league] 날짜 없는 맞대결 %d건 — 창에서 뺀다", len(undated))
    return sorted(dated, key=lambda m: str(m["date"]), reverse=True)[:n]


def h2h_tally(matches: list[dict], home: str) -> tuple[int, int, int] | None:
    """🔴🔴 맞대결 전적을 **경기 목록에서 직접 센다**(사용자 지시 2026-10-09 ①).

    > 맞대결 집계 불일치일 때 버리지 말고, 경기 페이지의 맞대결 경기 목록
    > (날짜·스코어)을 **직접 세어 다시 만든다.**

    `home` 기준 `(승, 무, 패)`. ⚠️ 스코어 없는 줄은 **안 센다**(합이 표본보다
    작으면 호출부가 그 수로 센 경기 수를 쓴다 — 0 으로 때우지 않는다).

    🔴 왜 필요한가 — 실측 2026-10-09(대전–전북): fotmob `summary` 는 `[3, 9, 13]`
       로 **전체 25경기**의 전적인데 `count` 는 창을 자른 **10경기**였다. 두 창이
       한 줄에 섞여 종전 코드는 그 변수를 **통째로 버렸다**(`CONFLICT`). 🔴 목록에
       날짜·스코어가 다 있으므로 **세면 된다** — 버릴 이유가 없었다.
    """
    key = norm_team(home)
    if not key:
        return None
    w = d = lose = 0
    seen = 0
    for m in (matches or []):
        hs, as_ = m.get("home_score"), m.get("away_score")
        if hs is None or as_ is None:
            continue
        a, b = norm_team(str(m.get("home") or "")), norm_team(str(m.get("away") or ""))
        if key == a:
            mine, theirs = int(hs), int(as_)
        elif key == b:
            mine, theirs = int(as_), int(hs)
        else:
            continue
        seen += 1
        if mine > theirs:
            w += 1
        elif mine == theirs:
            d += 1
        else:
            lose += 1
    return (w, d, lose) if seen else None


def h2h_season(matches: list[dict], *, when: str,
               comp: str = "") -> tuple[list[dict], int]:
    """🔴 **올 시즌 맞대결만**(같은 지시 ① 둘째 줄). `(줄들, 시즌)` — 오래된 것부터.

    > 올 시즌 맞대결은 **따로 표시**(이 경우 0-1·0-0).

    🔴 시즌 경계는 **표**가 든다 — `variable_types.yaml` `h2h_pattern.
       season_boundary`(기본 역년 · 유럽 대회만 8월). 코드에 달을 안 박는다.
    ⚠️ 날짜 없는 줄은 뺀다(어느 시즌인지 모른다 · #3 조용한 0 금지).
    """
    cut = season_cut_month(comp)
    want = _season_of(str(when), cut)
    if want is None:
        return [], 0
    out = [m for m in (matches or [])
           if m.get("date") and _season_of(str(m["date"]), cut) == want]
    return sorted(out, key=lambda m: str(m["date"])), want


def season_cut_month(comp: str = "") -> int:
    """🔴 그 대회 시즌이 **몇 월에 시작하나**. 표가 없으면 **역년**(1)이다."""
    box = dict((rules.variable_types().get("h2h_pattern") or {})
               .get("season_boundary") or {})
    default = int(box.get("default_month") or 1)
    said = dict(box.get("starts_month") or {})
    key = str(comp or "").strip()
    if key and key in said:
        return int(said[key])
    return default


def _season_of(day: str, cut_month: int) -> int | None:
    """`"2026-03-21"` → 시즌. 🔴 `cut_month` 가 1 이면 **역년**이다."""
    m = re.match(r"\s*(\d{4})-(\d{2})", str(day or ""))
    if not m:
        return None
    year, month = int(m.group(1)), int(m.group(2))
    if cut_month > 1 and month < cut_month:
        return year - 1
    return year


def norm_team(name: str) -> str:
    """🔴 팀 이름 대조용 꼴 — 맞대결 목록과 `MatchRef` 표기를 잇는다.

    ⚠️ 목록은 fotmob 표기(`Jeonbuk Hyundai Motors FC`)이고 우리 열쇠도 같은
       출처에서 왔지만, 공백·대소문자가 갈린다. 🔴 **이름을 지어내지 않는다** —
       낮춰 쓰고 공백만 줄인다.
    """
    return " ".join(str(name or "").strip().lower().split())


def _window_n(cfg: dict) -> int:
    """`window: 최근 10경기` 에서 숫자를 뽑는다. 🔴 못 읽으면 터진다 — 조용히 때우지 않는다."""
    import re
    m = re.search(r"\d+", str(cfg.get("window") or ""))
    if not m:
        raise ValueError(f"h2h 창을 못 읽었다: {cfg.get('window')!r}")
    return int(m.group())


def h2h_weight(n_games: int) -> float:
    """§4 `h2h_pattern.sample_weight` — **표본 수가 가중치를 정한다.**

    🔴 실측 2026-10-02 가 이 규칙을 만들었다. 같은 맞대결을 창만 바꿔 재니:

    ```
     3경기  시애틀 승 66.7% · KC 승 **0.0%** · 경기당 4.67골
    30경기            46.7% ·      36.7%   ·        2.73골
    ```

    3경기 창은 *"상대가 한 번도 못 이겼다"* 고 말한다 — 실제는 36.7% 다.
    ⚠️ 2026-10-01 에 그 함정에 빠져 맞대결 3경기로 언더에 0.9 를 걸고 낙첨했다.
    """
    cfg = rules.h2h_sample_cfg()
    lo = float(cfg.get("<5", 0.4))
    mid = float(cfg.get("5~9", 0.7))
    hi = float(cfg.get(">=10", 1.0))
    if n_games >= _window_n(cfg):
        return hi
    if n_games >= 5:
        return mid
    return lo


def open_game_threshold(rows: list[dict]) -> float | None:
    """§5-c-1 난타전 문턱 = **리그 평균 + 여유.** 여유는 yaml 이 정한다.

    🔴 **절대 숫자를 쓰지 않는다.** 처음 제안한 `3.0` 은 MLS(평균 3.22)에서 평균
       이하 경기에도 발동했다 — 리그가 0.7골 차로 갈린다.
    ⚠️ 리그 평균을 못 구하면 `None` → 그 OR 조건은 **발동하지 않는다**(친선·A매치).
       절대 숫자로 때우지 않는다.
    """
    avg = avg_goals(rows)
    if avg is None:
        return None
    margin = rules.cross_rule("5c-1").get("league_avg_margin")
    if margin is None:
        raise ValueError("§5-c-1 의 league_avg_margin 이 없다")
    return round(avg + float(margin), 3)


# ══════════════════════════════════════════════════════════════════
# 🔴 §5-c-1 ① — **포아송 기대 총득점** (사용자 지시 2026-10-02 2차)
# ══════════════════════════════════════════════════════════════════
#
# 지시 원문: *"난타전(5c-1)이 안 섰고 심층서치 찾아서 해결해라"*
#
# 🔴 **원인은 문턱이 아니라 입력이었다.** 전 판은 맞대결·최근 **평균 총득점**으로
#    물었다. 딥서치가 그 둘을 가장 약한 예측자로 지목한다:
#      ① 맞대결 평균은 8경기 미만이면 신뢰할 수 없고 한 경기가 평균을 왜곡한다
#      ② 둘 다 **홈/원정을 섞는다** — 실측 USL 홈 1.526 · 원정 1.206 (0.32골 차)
#
#    실측(실측 경기(새크라멘토 vs 라스베이거스)): 맞대결 2.5 · 최근 2.2 → 미발동.
#    **그 경기는 5골이 났다.**
#    같은 경기를 홈/원정 쪼갠 표로 다시 계산하니 기대 2.844(리그 2.732) → 발동.
#
# ⚠️ 식·출처·`open_goals`·`prob_ratio` 는 **yaml 이 원본이다**(사본 금지).
#    여기는 계산만 한다.


def venue_averages(home: list[dict], away: list[dict]) -> dict | None:
    """리그의 **홈 팀당 평균 득점**과 **원정 팀당 평균 득점**.

    🔴 포아송 모형의 기준값(`H`·`A`)이다. **장소를 섞으면 안 된다** — 딥서치가
       못 박은 조건이고(*"same venue context"*), 실측으로도 0.32골 차가 난다.
    ⚠️ 한쪽이라도 못 구하면 **`None`** — 반쪽으로 모형을 돌리지 않는다.
    """
    out: dict[str, float] = {}
    for key, rows in (("home", home), ("away", away)):
        gf = gp = 0.0
        for r in rows or []:
            f, p = r.get("goals_for"), r.get("played")
            if f is None or not p:
                continue
            gf += float(f)
            gp += float(p)
        if gp < 1:
            return None
        out[key] = round(gf / gp, 3)
    return out


def _rate(row: dict, field: str) -> float | None:
    """한 줄의 경기당 값. 🔴 못 구하면 `None` — 0 으로 때우지 않는다."""
    v, p = (row or {}).get(field), (row or {}).get("played")
    if v is None or not p:
        return None
    return float(v) / float(p)


#: 야구 한 경기의 정규 이닝. 🔴 ERA 의 분모가 9 이닝이다(정의).
INNINGS = 9.0


def starter_factor(*, era_starter: float | None = None,
                   era_team: float | None = None,
                   innings: float | None = None,
                   season_innings: float | None = None,
                   ) -> tuple[float | None, str]:
    """🔴🔴 **선발 투수가 상대 득점을 얼마로 바꾸나.** `(배수, 사유)`.

    ══════════════════════════════════════════════════════════════════
    🔴 왜 이 함수가 생겼나 — 딥서치 2026-10-03 (사용자 지시)
    ══════════════════════════════════════════════════════════════════

    > ① 무게를 확률로 둘지 근거와 곱할지(A/B/C) 이거는 **딥서치 해서 찾아라**

    갈림길은 2026-10-02 에 **D(그대로 둔다)** 로 닫혀 있었다. 닫은 근거는
    *"변수가 λ 를 움직이려면 보정 계수가 필요한데 발표된 계수가 없다"* 였다.
    🔴 다시 재니 **그 전제는 절반만 맞았다**(`questions/2026-10-03_weight_deepsearch.md`).

    - 축구 **결장 계수**는 지금도 없다 — 심지어 부호가 안정적이지 않다(대표팀
      차출로 주전이 빠진 팀이 오히려 공격 산출이 올랐다는 연구가 있다).
    - 🔴 **야구 선발은 다르다 — 계수가 필요 없다.** `ERA` 의 정의가 *"9이닝당
      자책점"* 이므로, 선발 품질 → 기대 실점 변환에 **맞출 모수가 없다.**
      공표된 방법도 같은 꼴이다(`Pitching Performance Score`: 리그 평균 투수가
      같은 이닝에 내줄 실점과의 차).

    ```
    배수 = (E_ip/9) × (ERA_선발 / ERA_팀)  +  (1 − E_ip/9) × 1
            └ 선발이 던지는 구간 ┘            └ 남은 이닝은 팀 평균 ┘
    ```

    🔴 **ERA_선발 = ERA_팀 이면 배수가 정확히 1 이다** — 즉 자료가 평범하다고
       말할 때 모형을 **건드리지 않는다**. 그것이 이 꼴을 고른 까닭이다.
    ⚠️ 남은 이닝을 **팀 ERA** 로 둔다 — npb.jp 는 불펜만의 ERA 를 따로 주지 않는다.
       팀 ERA 에는 선발이 섞여 있으므로 그 구간은 **약간 끌려간다.** 지어내지 않고
       그 사실을 사유로 돌려준다.
    🔴 셋 중 하나라도 없으면 **`None`** — 반쪽으로 모형을 돌리지 않는다.
    ⚠️ 기본값이 `None` 인 까닭: 한쪽 선발만 아는 판이 있고, 그때 호출부가
       `starter_factor(**{})` 로 부른다. 필수 인수로 두면 **거기서 터진다**
       (실측 2026-10-03: 계약이 그 자리를 잡았다).
    """
    if era_starter is None or era_team is None or innings is None:
        miss = [n for n, v in (("선발 ERA", era_starter), ("팀 ERA", era_team),
                               ("기대 이닝", innings)) if v is None]
        return None, f"선발 보정을 못 한다 — {', '.join(miss)} 가 없다"
    if float(era_team) <= 0:
        return None, "팀 ERA 가 0 이하다 — 비율을 만들 수 없다"
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **표본이 모자라면 건드리지 않는다**(실측 2026-10-03)
    # ══════════════════════════════════════════════════════════════════
    #
    #  라이브: 唐川(은퇴 등판)의 그 해 성적이 **1경기 5이닝 ERA 7.20** 이었고, 그
    #  수로 보정하니 상대 기대 득점이 **4.66 → 6.92**(+48%) 로 튀었다.
    #  🔴 한 경기 ERA 는 실력이 아니다 — `min_venue_games` 가 막는 것과 같은 병이다.
    #  ⚠️ 표본으로 줄이는(shrinkage) 방법은 **사전 분포의 세기**라는 맞출 모수를
    #     요구한다 — 금지다(CLAUDE.md). 그래서 **문턱**으로 막는다.
    floor = (rules.variable_types().get("pitcher_state") or {}).get("min_innings")
    if floor is not None:
        if season_innings is None:
            return None, (f"그 해 투구 이닝을 모른다 — 문턱 {floor}이닝을 "
                          f"확인할 수 없다(보정하지 않는다)")
        if float(season_innings) < float(floor):
            return None, (f"그 해 {season_innings}이닝뿐이다(문턱 {floor}) — "
                          f"한 경기 ERA 는 실력이 아니다(보정하지 않는다)")
    ip = max(0.0, min(float(innings), INNINGS))
    share = ip / INNINGS
    ratio = float(era_starter) / float(era_team)
    f = share * ratio + (1.0 - share)
    return round(f, 4), (
        f"선발 ERA {era_starter} ÷ 팀 ERA {era_team} = {ratio:.3f} · "
        f"기대 {ip:.1f}이닝({share:.0%}) → 배수 {f:.4f}"
        + ("" if ip < INNINGS else " (완투 가정)"))


def expected_goals(home_row: dict, away_row: dict,
                   avgs: dict | None, starters: dict | None = None) -> dict | None:
    """§5-c-1 ① — **기대 득점 λ.** 공격비 × 수비비 × 장소 기준값.

    `home_row` 는 홈팀의 **홈 표** 줄, `away_row` 는 원정팀의 **원정 표** 줄이다.
    🔴 뒤바꿔 넣으면 조용히 틀린 답이 나온다 — 그래서 이름이 `home_`·`away_` 다.

    실측 2026-10-02(새크라멘토 vs 라스베이거스, **경기 전** 값):
        SAC 홈 12경기 20득 9실 · LV 원정 12경기 18득 21실
        → λ 홈 1.911 · 원정 0.933 · 합 **2.844** (리그 2.732) · 실제 3-2
    """
    if not avgs:
        return None
    h, a = avgs.get("home"), avgs.get("away")
    if not h or not a:
        return None
    att_h, con_h = _rate(home_row, "goals_for"), _rate(home_row, "goals_against")
    att_a, con_a = _rate(away_row, "goals_for"), _rate(away_row, "goals_against")
    if None in (att_h, con_h, att_a, con_a):
        return None
    # 🔴 **표본이 모자라면 서지 않는다**(사용자 지시 2026-10-02).
    #    실측: NHL 개막 직후 디트로이트 홈 **0경기** · 레인저스 원정 **1경기**.
    #    0 이면 위에서 `None` 이 되어 막히지만 2~3경기는 **막히지 않고 쓰레기 λ** 가
    #    나온다. 문턱은 yaml 이 정한다(`h2h_min_games` 와 같은 까닭·같은 값).
    need = (rules.cross_rule("5c-1").get("model") or {}).get("min_venue_games")
    if need is not None:
        for row in (home_row, away_row):
            if float(row.get("played") or 0) < float(need):
                return None
    # 🔴 홈팀 공격비는 **리그 홈 평균**으로, 원정팀 수비비도 **리그 홈 평균**으로
    #    나눈다 — 둘 다 "홈에서 난 골"을 세는 자리다.
    lam_h = (att_h / h) * (con_a / h) * h
    lam_a = (att_a / a) * (con_h / a) * a
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **선발 보정 — 변수가 λ 에 닿는 유일한 자리**(딥서치 2026-10-03 · A)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ **누가 누구를 막나**: 홈팀 득점(`lam_h`)을 누르는 것은 **원정 선발**이고,
    #     원정팀 득점(`lam_a`)을 누르는 것은 **홈 선발**이다. 바꿔 넣으면 조용히
    #     반대로 틀린다 — 그래서 아래 두 줄에 교차를 명시한다.
    notes: list[str] = []
    if starters:
        f_h, why_h = starter_factor(**(starters.get("away") or {}))
        f_a, why_a = starter_factor(**(starters.get("home") or {}))
        if f_h is not None:
            lam_h *= f_h
            notes.append(f"홈 득점 ← 원정 선발: {why_h}")
        elif why_h:
            notes.append(f"홈 득점: {why_h}")
        if f_a is not None:
            lam_a *= f_a
            notes.append(f"원정 득점 ← 홈 선발: {why_a}")
        elif why_a:
            notes.append(f"원정 득점: {why_a}")
    return {"home": round(lam_h, 3), "away": round(lam_a, 3),
            "total": round(lam_h + lam_a, 3),
            "league_total": round(h + a, 3),
            # 🔴 **무엇으로 셌는지 남긴다** — 조용히 틀린 줄을 쓰면 못 찾는다
            "home_games": home_row.get("played"),
            "away_games": away_row.get("played"),
            # 🔴 선발 보정이 걸렸나·왜 안 걸렸나 — 카드가 그대로 적는다
            "starter_notes": notes}


def total_at_least(lam: float | None, n: int) -> float | None:
    """P(총득점 ≥ `n`) — 포아송. 🔴 `lam` 이 없으면 `None`.

    ⚠️ `math.exp`·팩토리얼만 쓴다. 외부 라이브러리를 들이지 않는다.
    """
    if lam is None or lam <= 0 or n < 0:
        return None
    import math
    under = 0.0
    term = math.exp(-float(lam))        # k=0 항
    for k in range(int(n)):
        if k:
            term = term * float(lam) / k
        under += term
    return round(1.0 - under, 4)


def open_game_ratio(home_row: dict, away_row: dict,
                    avgs: dict | None) -> dict | None:
    """§5-c-1 ① 의 **발동 판정값** — `P(총 ≥ n) ÷ 리그 기준 P`.

    🔴 **비율로 묻는다.** 절대 확률을 쓰면 리그마다 틀린다 — 리그 평균 2.5 면
       기준 P(≥4)=0.242 고 3.2 면 0.397 이다. 같은 0.30 이 한쪽에선 평균 이상,
       다른 쪽에선 평균 이하를 뜻한다.
    ⚠️ `n`(`open_goals`)·문턱(`prob_ratio`)은 **yaml 이 정한다.**
    """
    exp = expected_goals(home_row, away_row, avgs)
    if exp is None:
        return None
    cfg = (rules.cross_rule("5c-1") or {}).get("model") or {}
    n = cfg.get("open_goals")
    if n is None:
        raise ValueError("§5-c-1 model.open_goals 가 없다")
    p = total_at_least(exp["total"], int(n))
    base = total_at_least(exp["league_total"], int(n))
    if p is None or not base:
        return None
    return {**exp, "goals": int(n), "p": p, "league_p": base,
            "ratio": round(p / base, 3)}


# ══════════════════════════════════════════════════════════════════
# 🔴 시나리오 **확률** — 사용자 지시 2026-10-02 (3차)
# ══════════════════════════════════════════════════════════════════
#
# 지시 원문: *"① 비율 문턱 … ② D 의 strength 를 확률로 … 이것도 딥서치해서 바꿔라"*
#
# 🔴 딥서치의 답: **근거 개수는 확률이 아니다.**
#    적정 채점 규칙(Brier·log score)은 *예측 분포가 참 분포와 같을 때* 최적이 된다 —
#    즉 "무게"가 확률이어야 그 수가 뜻을 가진다. 근거 개수를 세어 정규화한 값은
#    적정 규칙이 아니고, 교정(calibration)되지도 않는다.
#
#    실측 2026-10-02 가 그것을 눈으로 보여 줬다(실측 경기(새크라멘토 vs 라스베이거스)):
#      strength 순  A B C D E
#      확률 순      A C E B D      ← 🔴 **순서가 다르다**
#      무승부 C 는 **두 번째로 그럴듯한 결과(16.2%)** 인데 strength 정규화로는 5.1% 다
#
# ⚠️ **이 모형의 알려진 한계를 적어 둔다**(딥서치):
#    ① 독립 포아송은 **낮은 스코어의 상관**을 못 담는다 — 0-0·1-0·0-1·1-1 이 모형보다
#       실제로 더 자주 난다. Dixon–Coles 가 그 네 칸만 τ 로 고친다.
#       🔴 **τ 를 쓰지 않는다** — ρ 를 맞출 경기별 자료가 없다. 지어내지 않는다.
#       (v4 §5-a 의 무승부 하한 0.4 가 같은 편향을 다른 방식으로 막고 있다)
#    ② **과대분산** — 분산이 평균을 넘는 리그에서는 포아송이 **극단값을 낮게 본다.**
#       즉 난타전 확률은 아래 값보다 **더 높을 수** 있다. 문턱을 조일 이유가 아니다.
#
# 출처: https://statsultra.com/dixon-coles-model/ ·
#       https://www.footballhacking.com/p/why-poisson-models-work-better-in ·
#       https://en.wikipedia.org/wiki/Brier_score

#: 🔴 스코어 격자의 상한. 딥서치: 0-0~5-5 가 경기의 약 99% 를 덮는다.
#   ⚠️ 그래도 남는 꼬리는 **버리지 않고 이름으로** 남긴다(`tail` 칸).
SCORE_CAP = 7


def score_probabilities(lam_home: float | None, lam_away: float | None,
                        cap: int = SCORE_CAP) -> dict | None:
    """스코어별 확률 격자. 🔴 **못 구하면 `None`** — 지어내지 않는다.

    돌려주는 것: `{"scores": {"2-1": 0.14, …}, "tail": 0.003}`.
    `tail` 은 격자 밖(한쪽이 `cap` 초과)의 확률이다 — **조용히 버리지 않는다.**
    """
    if lam_home is None or lam_away is None:
        return None
    if lam_home <= 0 or lam_away <= 0:
        return None
    import math
    def _p(k: int, lam: float) -> float:
        return math.exp(-float(lam)) * float(lam) ** k / math.factorial(k)
    grid: dict[str, float] = {}
    for h in range(int(cap) + 1):
        for a in range(int(cap) + 1):
            grid[f"{h}-{a}"] = _p(h, lam_home) * _p(a, lam_away)
    got = sum(grid.values())
    return {"scores": {k: round(v, 6) for k, v in grid.items()},
            "tail": round(max(0.0, 1.0 - got), 6),
            # 🔴 **λ 를 함께 돌려준다** — 격자 64칸을 저장하지 않고 이 두 수만 적으면
            #    채점이 그때의 격자를 **다시 만들 수 있다**(사용자 지시 2026-10-02).
            "lam": {"home": round(float(lam_home), 6),
                    "away": round(float(lam_away), 6)}}


def scores_mass(probs: dict | None, scores: list[str]) -> float | None:
    """스코어 집합의 확률 합 = **그 시나리오의 확률**. 🔴 모르면 `None`.

    ⚠️ 격자에 없는 스코어는 **0 으로 세지 않는다** — `None` 을 돌려 호출부가
       *"못 쟀다"* 와 *"확률이 0 이다"* 를 구분하게 한다(조용한 0 금지).
    """
    if not probs or not scores:
        return None
    grid = probs.get("scores") or {}
    out = 0.0
    for s in scores:
        v = grid.get(str(s).strip())
        if v is None:
            return None
        out += float(v)
    return round(out, 6)


def top_scores(probs: dict | None, side: str, n: int) -> list[str]:
    """격자에서 **그 방향의 가장 그럴듯한 스코어 `n` 개**.

    🔴 §5-b 에 템플릿이 없는 종목(하키·농구·배구)을 위한 문이다. 스코어를 **손으로
       적지 않는다** — 적으면 그것이 지어낸 값이 되고, 리그가 바뀌면 따라가지 않는다.
    ⚠️ `side` 는 `"home"`·`"away"`·`"draw"`·`"open:N"` 이다. `open:N` 은 총득점이
       `N` 이상인 구간(난타전)이다.
    🔴 격자가 없으면 **빈 목록** — 호출부가 사유를 남기고 멈춘다.
    """
    grid = (probs or {}).get("scores") or {}
    if not grid or n < 1:
        return []
    need = 0
    if str(side).startswith("open:"):
        need = int(str(side).split(":", 1)[1])

    def _ok(h: int, a: int) -> bool:
        if need:
            return (h + a) >= need
        if side == "home":
            return h > a
        if side == "away":
            return a > h
        return h == a

    rows = []
    for k, v in grid.items():
        try:
            h, a = (int(x) for x in k.split("-"))
        except ValueError:
            continue
        if _ok(h, a):
            # 🔴 확률이 같으면 **총득점이 적은 쪽**을 먼저 — 순서가 기계마다
            #    달라지면 계약이 흔들린다(정렬이 유일해야 한다)
            rows.append((-v, h + a, k))
    rows.sort()
    return [k for _, _, k in rows[:n]]
