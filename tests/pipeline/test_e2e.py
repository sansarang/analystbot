"""[v1.4 §6] E2E 드라이런 — **지시문 픽스처 2건의 기대값을 그대로 잠근다.**

🔴 두 픽스처 모두 기대값이 **보드·발송 0건**이다. 값이 없는 날 침묵하는 것이
   이 봇의 기본이고, 픽이 나오면 그게 버그다.
🔴 6-2(축구)는 파생 모델(포아송 λ)이 아직 없으므로 **구조 후보가 0** 이다.
   추측 확률로 픽을 만들면 실패다(지시문 §6 원문).
⚠️ 바깥은 전부 `ctx.inject` 로 갈아끼운다 — 네트워크·DB·LLM 을 타지 않는다.

🔴 **[2026-09-18 페이블 검토] §6-1 기대값이 개정됐다.**
   초판은 `⑦ +2.0 → ⑧ 0.707 → ⑪ ml_edge −3.4` 였는데, §1.2 표
   (`starter_recent3.max_abs = 3.0`)와 §8 규칙(`max_abs × strength(0.5|1.0)`)
   으로는 **2.0 이 나올 수 없다**(1.5 또는 3.0). 지시문 내부가 어긋났다.
   개정판(페이블 확인): `⑦ +3.0/+2.0 → Σ +5.0 → p_code 0.7375 → 확신 A → 보드`.
   **코드를 유지하고 기대값을 고쳤다** — 숫자를 맞추려 규칙을 비틀지 않는다.
"""
from __future__ import annotations

import pytest

from app.flow import run as RUN
from app.flow.ctx import Ctx
from app.flow.labels import AGREE, OVER, PICK_BOARD


class _Pool:
    """스냅샷을 메모리에 모은다 — `analysis_runs` 행 수를 세기 위해."""

    def __init__(self):
        self.rows: list = []
        self.updates: list = []

    async def execute(self, sql, *a):
        # ⚠️ [STOP-1] **스냅샷은 INSERT 뿐이다.** `finish` 가 멈춤 칸을 쓰는
        #    UPDATE 까지 행으로 세면 "노드당 1행"이 거짓으로 깨진다.
        if not str(sql).lstrip().upper().startswith("INSERT"):
            self.updates.append((sql, a))
            return
        self.rows.append({"run_id": a[0], "game_id": a[1], "node": a[2]})

    async def fetch(self, sql, *a):
        return []


# ── 6-1. 야구: 2026-09-18 KBO 대전, 삼성(원정) @ 한화(홈)

KBO_GAME = {"game_id": "kbo_20260918_HH_SS", "sport": "baseball",
            "league": "KBO", "home": "한화", "away": "삼성",
            "starts_at": "2026-09-18T09:30:00Z"}

KBO_ODDS = [
    {"market": "h2h", "side": "한화", "line": None, "odds": 2.97},
    {"market": "h2h", "side": "삼성", "line": None, "odds": 1.35},
    {"market": "totals", "side": "Over", "line": 9.5, "odds": 1.78},
    {"market": "totals", "side": "Under", "line": 9.5, "odds": 1.90},
    {"market": "team_totals", "side": "삼성 Over", "line": 4.5, "odds": 1.43},
    {"market": "team_totals", "side": "삼성 Under", "line": 4.5, "odds": 2.58},
    {"market": "spreads", "side": "삼성", "line": -2.5, "odds": 1.84},
    {"market": "spreads", "side": "한화", "line": 2.5, "odds": 1.84},
]

#: 🔴 사전값 픽스처 상수 — 삼성 0.69 (지시문 §6-1). elo 로 그 값을 만든다.
#   `p_away = 0.69` ⇔ elo 차 ≈ 139.4 (HFA 25 포함).
KBO_ELO = {"한화": 1450.0, "삼성": 1614.4}


@pytest.mark.asyncio
async def test_6_1_야구_대전은_보드로_끝난다():
    pool = _Pool()
    ctx = Ctx(pool=pool, inject={
        "elo": KBO_ELO,
        "odds_rows": KBO_ODDS,
        # 🔴 지시문 §6-1 evidence — 한화(홈, 상대) 선발 박준영 ERA 6.10 ·
        #    4⅓이닝 한도. 픽은 삼성(원정)이므로 **상대 악재 = 유리(+)** 다.
        "evidence": [
            {"var": "starter_recent3", "value": ["박준영 ERA 6.10 · 4⅓이닝"],
             "raw_excerpt": "박준영 ERA 6.10 · 4⅓이닝 한도",
             "sides": {"home": 1}, "source_url": "http://fixture/1"},
            {"var": "bullpen_3d", "value": ["한화 불펜 3일 6이닝"],
             "raw_excerpt": "한화 불펜 최근 3일 6이닝", "sides": {"home": 1},
             "source_url": "http://fixture/2"},
            # ⚠️ `lineup_out` 은 **주지 않는다** → `unknown`.
            #    빈 목록을 주면 `refuted` 이고, 핵심 변수의 반증은 규칙상
            #    **픽 철회**(⑥ 반박됨)라 ⑪까지 가지 않는다. 지시문 §6-1 은
            #    그 변수를 언급하지 않았으므로 "안 봤다"가 맞다.
            # 🔴 [F-17 + HYC-3 2026-09-23] 질문이 사전값에서 나오면서 `동의`
            #    도 전 변수를 묻는다. 운영에서는 ⑤가 소스 없는 변수에
            #    **미실행** 행을 남기고 ⑥이 그것을 분모에서 뺀다 — 주입
            #    경로는 그 자리를 지나지 않으므로 여기서 같은 모양을 준다.
            #    ⚠️ 목록을 손으로 고른 것이 아니라 운영 실측 그대로다
            #       (weather·travel_backtoback 은 ⑤에 분기가 없다).
            {"var": "weather", "value": None, "status": "미실행",
             "raw_excerpt": "이 변수는 아직 수집 경로가 없다 — 미실행"},
            {"var": "travel_backtoback", "value": None, "status": "미실행",
             "raw_excerpt": "이 변수는 아직 수집 경로가 없다 — 미실행"},
            {"var": "park_factor", "value": ["대전 1.153"],
             "raw_excerpt": "대전 파크팩터 1.153"},
        ],
        "absences": [],
        "rejudge_signals": {},
    })
    s = await RUN.run_game(KBO_GAME, ctx)

    # ② 시장값
    assert abs(s.n02_market["p"]["away"] - 0.687) <= 0.002, s.n02_market
    # ③ 게이트 — 사전값 0.69 vs 시장 0.687 → 동의
    assert s.n03_gate["gate"] == AGREE, s.n03_gate
    assert abs(s.n03_gate["gap_pp"]) < 4.0
    # ④ 가설 — 동의는 파생만
    # 🔴 [F-17 2026-09-23 사용자 지시] 질문이 게이트에서 안 나온다 —
    #    게이트가 `동의` 여도 묻는 것은 "우리 사전 판단을 무너뜨릴 근거"다.
    #    ⚠️ 게이트가 정하는 것은 **해석과 걸 대상**이다(사용자 결정 (가)).
    assert s.n04_hyp[0]["id"] == "H_break"
    assert s.n04_hyp[0]["refuted_means"] == "중립"
    assert s.n04_hyp[0]["market"] == "total"
    # ⑦⑧⑨ — 개정된 §6-1 기대값을 **중간값까지** 고정한다.
    #   상대(한화=홈) 선발·불펜 악재이므로 픽(삼성=원정)에게 유리하다.
    # 🔴 [SIDE-2 2026-09-23] ⑦은 이제 **홈 기준**으로 낸다 — 홈이 악재이므로
    #    음수다. 뜻은 그대로고 표현만 표준화됐다. 픽 기준 합(`sum_adj_pp`)과
    #    최종 확률은 **한 자리도 안 바뀐다** — 그것이 이 표준화의 전제다.
    assert {a["var"]: a["pp"] for a in s.n07_adjust} == {
        "starter_recent3": -3.0, "bullpen_3d": -2.0}, s.n07_adjust
    assert s.pick_side == "away", "⑧이 픽을 못 정했다"
    assert s.n08_pcode["p_home"] == 0.2625
    assert s.n08_pcode["sum_adj_pp"] == 5.0
    assert s.n08_pcode["p_code_pick"] == 0.7375
    assert s.n09_conf["grade"] == "A", s.n09_conf
    # ⑪ 값 판정 — 파생 모델이 없으므로 구조 후보 0 → 보드
    assert s.n11_value["pick_type"] == PICK_BOARD, s.n11_value
    assert s.n11_value["n_candidates"] == 0
    # ⑫⑬ 미호출 · 발송 0건
    assert s.stop_reason == "n11_no_value"
    assert "n12_text" not in s.trace and "n13_send" not in s.trace
    # 🔴 [STOP-1 / STEP 1-b 2026-09-20] ⑬ 에 **도달하지 못한 것도 적는다.**
    #    종전에는 `n13_send is None` 이라 "안 보냈다"와 "거기까지 못 갔다"가
    #    구분되지 않았다(실측: 32경기 ⑬ why 전건 null).
    assert s.n13_send == {"sent": False, "message_id": None,
                          "why": f"미도달:{s.stopped_at}"}, s.n13_send
    assert s.stopped_at == s.trace[-2], (s.stopped_at, s.trace)


@pytest.mark.asyncio
async def test_6_1_스냅샷이_노드마다_1행이다():
    pool = _Pool()
    ctx = Ctx(pool=pool, inject={"elo": KBO_ELO, "odds_rows": KBO_ODDS,
                                 "evidence": [], "absences": [],
                                 "rejudge_signals": {}})
    s = await RUN.run_game(KBO_GAME, ctx)
    nodes = [r["node"] for r in pool.rows]
    assert nodes == s.trace, (nodes, s.trace)
    assert len(nodes) == len(set(nodes)), nodes      # 노드당 1행
    assert all(r["run_id"] == s.run_id for r in pool.rows)


# ── 6-2. 축구: 2026-09-17 UEL, 크리스탈 팰리스(홈) vs 레흐 포즈난

UEL_GAME = {"game_id": "uel_20260917_CP_LP", "sport": "soccer",
            "league": "UEL", "home": "Crystal Palace", "away": "Lech Poznan",
            "starts_at": "2026-09-17T19:00:00Z"}

UEL_ODDS = [
    {"market": "h2h", "side": "Crystal Palace", "line": None, "odds": 1.32},
    {"market": "h2h", "side": "Draw", "line": None, "odds": 5.06},
    {"market": "h2h", "side": "Lech Poznan", "line": None, "odds": 7.29},
    {"market": "spreads", "side": "Lech Poznan", "line": 1.5, "odds": 1.83},
    {"market": "spreads", "side": "Crystal Palace", "line": -1.5, "odds": 1.87},
]

#: 🔴 사전값 픽스처 상수 — 팰리스 0.60 (지시문 §6-2).
#   3-way 는 무승부 질량(0.26)을 먼저 뺀다: 0.60 = raw × 0.74 → raw ≈ 0.8108.
#   그 raw 를 만드는 elo 차 ≈ 251.6.
UEL_ELO = {"Crystal Palace": 1700.0, "Lech Poznan": 1448.4}


@pytest.mark.asyncio
async def test_6_2_축구는_시장과대이고_보드로_끝난다():
    pool = _Pool()
    ctx = Ctx(pool=pool, inject={
        "elo": UEL_ELO,
        "odds_rows": UEL_ODDS,
        # 🔴 지시문 §6-2 evidence — 마테타·헨더슨(팰리스=홈=우리 픽) 결장.
        #    우리 픽 쪽 악재이므로 **불리(−)** 다.
        "evidence": [
            {"var": "xi_confirmed", "value": ["Mateta 결장", "Henderson 결장"],
             "raw_excerpt": "Mateta · Henderson 결장", "sides": {"home": 2},
             "source_url": "http://fixture/3"},
            {"var": "rotation_risk", "value": ["3일 내 리그 원정"],
             "raw_excerpt": "3일 내 리그 원정", "sides": {"home": 1}},
            {"var": "form_recent5", "value": ["W", "D", "L"],
             "raw_excerpt": "최근 W D L", "sides": {"home": 3}},
            # 🔴 [NWS-D 2026-09-23] 주입 경로는 ⑤의 실제 분기를 **건너뛴다**.
            #    운영에서는 기사 소스가 없으면 ⑤가 `미실행` 행을 내고 ⑥이
            #    분모에서 뺀다(계약 `test_기사가_없으면_미실행이다`). 주입에
            #    빼 두면 `미상` 으로 세어져 분모가 늘고 모름과반이 된다 —
            #    운영이 만드는 모양을 그대로 준다.
            {"var": "news_injury", "value": [], "status": "미실행",
             "raw_excerpt": "기사 소스가 없다 — 미실행"},
        ],
        "absences": [],
        "rejudge_signals": {},
    })
    s = await RUN.run_game(UEL_GAME, ctx)

    # ② 3-way 마진 제거
    assert abs(s.n02_market["p"]["home"] - 0.693) <= 0.003, s.n02_market
    assert abs(sum(v for v in s.n02_market["p"].values() if v) - 1.0) < 1e-9
    # ③ 사전값 0.60 vs 시장 0.693 → 약 −9.3%p → 시장 과대
    assert s.n03_gate["gate"] == OVER, s.n03_gate
    assert -12.0 < s.n03_gate["gap_pp"] <= -4.0
    # ④ 가설 — 시장 반대편을 세울 근거
    # 🔴 [F-17] `시장과대` 여도 질문은 같다. 다만 **해석은 철회**다 —
    #    시장이 우리보다 훨씬 높게 보는데 반대 근거가 없으면 시장이 맞다.
    assert s.n04_hyp[0]["id"] == "H_break"
    assert s.n04_hyp[0]["refuted_means"] == "철회"
    # ⑪ — 승패 금지(게이트 ≠ 동의) · 파생 모델 없음 → 보드
    assert s.n11_value["pick_type"] == PICK_BOARD, s.n11_value
    assert s.stop_reason == "n11_no_value"
    # 🔴 [STOP-1 / STEP 1-b] ⑬ 에 도달하지 못한 것도 적는다.
    assert s.n13_send == {"sent": False, "message_id": None,
                          "why": f"미도달:{s.stopped_at}"}, s.n13_send


@pytest.mark.asyncio
async def test_6_2_축구는_1빼기_p_home_을_쓰지_않는다():
    """🔴 무승부 질량이 있어 `1 - p_home` 은 원정 확률이 아니다."""
    ctx = Ctx(inject={"elo": UEL_ELO, "odds_rows": UEL_ODDS,
                      "evidence": [], "absences": [], "rejudge_signals": {}})
    s = await RUN.run_game(UEL_GAME, ctx)
    p = s.n02_market["p"]
    assert abs(p["away"] - (1 - p["home"])) > 0.05, p     # 확연히 다르다
    pri = s.n01_prior
    assert abs(pri["p_away"] - (1 - pri["p_home"])) > 0.05, pri


# ── 두 픽스처 공통: **발송 0건**

@pytest.mark.asyncio
@pytest.mark.parametrize("game,elo,odds", [
    (KBO_GAME, KBO_ELO, KBO_ODDS),
    (UEL_GAME, UEL_ELO, UEL_ODDS),
])
async def test_드라이런은_카드를_한_장도_만들지_않는다(game, elo, odds):
    sent: list = []
    ctx = Ctx(inject={"elo": elo, "odds_rows": odds, "evidence": [],
                      "absences": [], "rejudge_signals": {},
                      "send": lambda t: sent.append(t) or True})
    s = await RUN.run_game(game, ctx)
    assert sent == [], sent
    assert s.stop_reason is not None
