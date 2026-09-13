"""ADJ-1 — 조정 변수를 DB 원자료에서 계산한다 (결정 A).

사용자 결정 2026-09-13(2차 결정 A): `prob.py` 는 순수 함수로 두고,
`adjust.attach(jg, pool)` 가 `_attach_market_spine` **직전**에 `jg` 에 키만
세팅한다. 수집기(`gather`·`bullpen_recent`)는 건드리지 않는다.

🔴 **실측 2026-09-13**: 결정 1 구현 직후 오늘 MLB 8경기의 `adj_pp` 가 전부
   `{}` 였다 — `p_code == p_market`, 즉 코드가 시장을 그대로 베꼈다.
   조정 변수를 읽는 키를 아무도 채우지 않았기 때문이다.

⚠️ **적용 시점 규칙**: 라인업/타순이 `confirmed`(=official)가 아니면 결장·
   선발변경 변수를 계산하지 않고 `adj_pending=True`. 잠정 상태에서 조정하지 않는다.
⚠️ 계산 불가(원자료 없음)는 0이 아니라 **미계산**(`adj_missing`)이다.
"""
import pytest

from app.engine import adjust as A


def test_임계값이_한_곳에_있다():
    """⚠️ 사본 금지 — 숫자를 함수 안에 흩어 적지 않는다."""
    for k in ("regular_window", "regular_min", "pen_top_n",
              "pen_window_days", "trip_min"):
        assert k in A.ADJ_DEFS, k


def test_official이_아니면_계산하지_않는다():
    """🔴 잠정 타순으로 조정하면 확정 뒤 뒤집힌다."""
    jg = {"sport": "mlb", "lineup_status": "predicted"}
    assert A.gate(jg) is False
    jg2 = {"sport": "mlb", "lineup_status": "confirmed"}
    assert A.gate(jg2) is True


def test_official_상태값을_손으로_적지_않는다():
    import inspect

    from app.collectors.lineups import STATUS_CONFIRMED

    src = inspect.getsource(A)
    assert "STATUS_CONFIRMED" in src, "상태 상수를 원본에서 가져오지 않았다"
    assert A.gate({"lineup_status": STATUS_CONFIRMED}) is True


# ── 주전 결장

def test_주전결장을_최근10경기_7선발_기준으로_센다():
    regulars = {"A", "B", "C", "D"}
    today = ["A", "B", "X", "Y"]
    assert A.count_out(regulars, today) == 2          # C·D 빠짐


def test_오늘_타순이_비면_미계산이다():
    assert A.count_out({"A"}, []) is None


# ── 불펜 연투

def test_연투는_직전_2일_연속_등판이다():
    from datetime import date

    d = date(2026, 9, 13)
    apps = {"P1": [date(2026, 9, 12), date(2026, 9, 11)],   # 2일 연속 → 연투
            "P2": [date(2026, 9, 12)],                       # 하루만
            "P3": [date(2026, 9, 10), date(2026, 9, 9)]}     # 오래됨
    assert A.count_b2b(apps, d) == 1


def test_연투는_상위_3명만_본다():
    assert A.ADJ_DEFS["pen_top_n"] == 3


# ── 이동 연전

@pytest.mark.parametrize("streak,expect", [(0, 0), (2, 0), (3, 1), (7, 1)])
def test_이동연전은_3연전_이상에서만_발생한다(streak, expect):
    assert A.trip_flag(streak) == expect


# ── 축구

def test_축구_주전은_최근10경기_8선발이다():
    assert A.ADJ_DEFS["soccer_regular_min"] == 8


@pytest.mark.parametrize("days,expect", [(2, True), (3, True), (4, False), (None, False)])
def test_짧은휴식은_3일_이하다(days, expect):
    assert A.short_rest(days) is expect


def test_대항전_소스가_없으면_미계산이다():
    """⚠️ 소스가 없으면 0 이 아니라 unknown 이다 — 0 은 '조사했는데 없었다'다."""
    jg = {"sport": "soccer"}
    assert A.midweek_away(jg) is None


# ── 붙이기

@pytest.mark.asyncio
async def test_미계산은_adj_missing에_남는다():
    class _Pool:
        async def fetch(self, *a, **k): return []
        async def fetchval(self, *a, **k): return None

    jg = {"sport": "mlb", "game_id": 1, "home": "H", "away": "A",
          "lineup_status": "confirmed"}
    await A.attach(jg, _Pool())
    assert "adj_missing" in jg
    # 🔴 T-24h 선발 스냅샷 테이블이 없다 — starter_changed 는 미계산이어야 한다
    assert "starter_changed" in jg["adj_missing"], jg["adj_missing"]
    assert jg.get("starter_changed") in (None, 0, False)


@pytest.mark.asyncio
async def test_잠정이면_adj_pending이_선다():
    class _Pool:
        async def fetch(self, *a, **k): return []
        async def fetchval(self, *a, **k): return None

    jg = {"sport": "mlb", "game_id": 1, "lineup_status": "predicted"}
    await A.attach(jg, _Pool())
    assert jg.get("adj_pending") is True
    assert not jg.get("out_starters")


@pytest.mark.asyncio
async def test_원자료_요약을_남긴다():
    """서술 규격의 `reason_vars` 가 여기서 나온다."""
    class _Pool:
        async def fetch(self, *a, **k): return []
        async def fetchval(self, *a, **k): return None

    jg = {"sport": "mlb", "game_id": 1, "lineup_status": "confirmed"}
    await A.attach(jg, _Pool())
    assert isinstance(jg.get("adj_inputs"), dict)


def test_수집기를_건드리지_않는다():
    """⚠️ 결정 A — gather·bullpen_recent 는 그대로 둔다."""
    import inspect

    src = inspect.getsource(A)
    for bad in ("gather.collect", "bullpen_recent", "attach_starter_recent"):
        assert bad not in src, bad


# ── 결정 B: 축소 계수

def test_조정_크기를_절반으로_시작한다():
    from app.engine import prob as P

    assert P.ADJ_SHRINK == 0.5


def test_합계_절사가_6퍼센트포인트다():
    from app.engine import prob as P

    assert P.ADJ_SUM_CAP == 6.0
    big = {"a": -5.0, "b": -5.0, "c": -5.0}
    assert abs(sum(P.shrink_and_cap(big).values())) == pytest.approx(6.0)


def test_축소가_p_code에_반영된다():
    from app.engine import prob as P

    # 표 -1.5/명 × 2명 = -3.0 → 축소 0.5 → -1.5%p
    adj = P.adjustments({"sport": "mlb", "out_starters": 2})
    assert adj["주전결장"] == -3.0                      # 표 그대로 기록
    assert P.p_code(0.55, adj, "mlb") == pytest.approx(0.535, abs=1e-9)


def test_뼈대_직전에_배선돼_있다():
    """🔴 결정 A — `_attach_market_spine` **직전**이어야 한다."""
    import inspect

    from app import pipeline as PL

    src = inspect.getsource(PL._attach_market_spine)
    i, j = src.index("_adjust.attach"), src.index("_market_probs(")
    assert i < j, "조정 부착이 시장 확률 계산보다 뒤에 있다"


def test_원장에는_축소_전_값을_남긴다():
    """사후 검증의 재료는 '어떤 변수가 얼마로 발생했나'다."""
    from app.engine import prob as P

    adj = P.adjustments({"sport": "mlb", "out_starters": 2})
    assert adj["주전결장"] == -3.0            # 표 그대로
    assert P.shrink_and_cap(adj)["주전결장"] == -1.5   # 적용은 절반


# ── [ADJ-2] 이동연전이 구조적으로 발생할 수 없었다

@pytest.mark.asyncio
async def test_오늘_경기를_이동연전_계산에서_제외한다():
    """🔴 실측 2026-09-13: 오늘 KBO·NPB 9경기 전부 `연속원정 = 0` 이었다.

    `_TRIP` 이 `starts_at <= $3` 라 **오늘 경기 자신이 첫 행**으로 잡히고,
    홈팀은 오늘 홈경기이므로 첫 바퀴에서 `break` — `streak` 는 영원히 0 이다.
    3연전 이상 원정을 돌고 돌아온 홈팀이어도 조정이 붙지 않는다.

    ⚠️ 가짜 풀이 **SQL 의 부등호를 실제로 지킨다** — 문자열만 보는 계약은
       DB 가 어떻게 읽는지를 재지 못한다.
    """
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 9, 13, 8, 0, tzinfo=timezone.utc)
    me = "Doosan Bears"
    # 오늘: 홈경기. 그 전 3경기는 연속 원정.
    history = [
        {"home": me, "away": "NC Dinos", "starts_at": now},                       # 오늘
        {"home": "KT Wiz", "away": me, "starts_at": now - timedelta(days=1)},
        {"home": "KT Wiz", "away": me, "starts_at": now - timedelta(days=2)},
        {"home": "KT Wiz", "away": me, "starts_at": now - timedelta(days=3)},
        {"home": me, "away": "LG Twins", "starts_at": now - timedelta(days=4)},
    ]

    class _Pool:
        async def fetchval(self, *a, **k): return None

        async def fetch(self, sql, *a):
            if "pa.pitcher" in sql:          # 불펜
                return []
            if "g.home, g.away" not in sql:  # 주전
                return []
            cutoff = a[2]
            # 🔴 SQL 이 `<=` 면 오늘 경기가 들어온다. `<` 면 빠진다.
            strict = "g.starts_at < $3" in sql
            rows = [r for r in history
                    if (r["starts_at"] < cutoff if strict else r["starts_at"] <= cutoff)]
            return sorted(rows, key=lambda r: r["starts_at"], reverse=True)[:8]

    jg = {"sport": "kbo", "game_id": 1741, "home": me, "away": "NC Dinos",
          "starts_at": now, "lineup_status": "confirmed"}
    await A.attach(jg, _Pool())
    assert jg["adj_inputs"]["이동연전"]["연속원정"] == 3, jg["adj_inputs"]
    assert jg["trip_day"] == 1


@pytest.mark.asyncio
async def test_원정을_돌지_않았으면_이동연전은_0이다():
    """반대 위험 — 부등호를 고치다 멀쩡한 홈팀에 벌점을 주면 안 된다."""
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 9, 13, 8, 0, tzinfo=timezone.utc)
    me = "Kia Tigers"
    history = [{"home": me, "away": "X", "starts_at": now - timedelta(days=i)}
               for i in range(5)]

    class _Pool:
        async def fetchval(self, *a, **k): return None

        async def fetch(self, sql, *a):
            if "g.home, g.away" not in sql or "pa.pitcher" in sql:
                return []
            return [r for r in history if r["starts_at"] < a[2]][:8]

    jg = {"sport": "kbo", "game_id": 1743, "home": me, "away": "Y",
          "starts_at": now, "lineup_status": "confirmed"}
    await A.attach(jg, _Pool())
    assert jg["adj_inputs"]["이동연전"]["연속원정"] == 0
    assert jg["trip_day"] == 0


# ── [ADJ-3] 원정 팀 피로가 구조적으로 반영되지 않았다

@pytest.mark.asyncio
async def test_원정_불펜이_더_지쳤으면_홈에_유리하게_잡힌다():
    """🔴 실측 2026-09-13 롯데@KT: 원정 3명 연투 · 홈 1명인데 조정 0.

    `max(0, home - away)` 라 **원정 팀 피로는 영원히 0** 이었다. 제미나이는
    글에 "롯데 불펜 연투 피로 누적"이라고 썼는데 코드 축은 비어 있었다.
    차이를 **부호 있는 값**으로 남긴다 — 음수면 원정이 더 지친 것이다.
    """
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 9, 13, 8, 0, tzinfo=timezone.utc)
    # 홈 1명 연투 · 원정 3명 연투
    pen = {"KT Wiz": {"h1": 2},
           "Lotte Giants": {"a1": 2, "a2": 2, "a3": 2}}

    class _Pool:
        async def fetchval(self, *a, **k): return None

        async def fetch(self, sql, *a):
            if "pa.pitcher" not in sql:
                return []
            team = a[0]
            rows = []
            for name, days in pen.get(team, {}).items():
                for i in range(1, days + 1):
                    rows.append({"pitcher": name, "d": (now - timedelta(days=i)).date()})
            return rows

    jg = {"sport": "kbo", "game_id": 1744, "home": "KT Wiz", "away": "Lotte Giants",
          "starts_at": now, "lineup_status": "confirmed"}
    await A.attach(jg, _Pool())
    assert jg["adj_inputs"]["필승조연투"] == {"home": 1, "away": 3}
    assert jg["bullpen_b2b"] == -2, jg["bullpen_b2b"]

    from app.engine import prob as P

    assert P.adjustments(jg)["필승조연투"] == 2.0     # 홈에 유리


@pytest.mark.asyncio
async def test_홈이_더_지쳤을_때는_종전과_같다():
    """반대 위험 — 부호를 열다 기존 방향이 바뀌면 안 된다."""
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 9, 13, 8, 0, tzinfo=timezone.utc)
    pen = {"Samsung Lions": {"h1": 2, "h2": 2}, "LG Twins": {}}

    class _Pool:
        async def fetchval(self, *a, **k): return None

        async def fetch(self, sql, *a):
            if "pa.pitcher" not in sql:
                return []
            return [{"pitcher": n, "d": (now - timedelta(days=i)).date()}
                    for n, d in pen.get(a[0], {}).items() for i in range(1, d + 1)]

    jg = {"sport": "kbo", "game_id": 1742, "home": "Samsung Lions", "away": "LG Twins",
          "starts_at": now, "lineup_status": "confirmed"}
    await A.attach(jg, _Pool())
    assert jg["bullpen_b2b"] == 2

    from app.engine import prob as P

    assert P.adjustments(jg)["필승조연투"] == -2.0   # 실측 2026-09-13 과 같은 값


# ── [ADJ-4] 주전결장 배선 — `lineups` 가 아니라 `lineup_events` 다

def test_타순_원소에서_포지션을_떼어낸다():
    """🔴 실측 2026-09-13: 포지션이 2가지 이상인 선수가 **KBO 30% · NPB 18%**.

    `"양의지(포수)"` 와 `"양의지(지명타자)"` 를 다른 사람으로 세면
      (a) 주전 판정에서 누락되고(원문 67명 → 이름만 78명)
      (b) 오늘 포지션이 바뀐 주전이 **결장으로 오인된다** ← 반대 위험
    """
    assert A._arr('["양의지(포수)", "김민석(좌익수)"]') == ["양의지", "김민석"]
    assert A._arr('["赤羽 由紘(三)"]') == ["赤羽 由紘"]
    assert A._arr('[{"이름": "오지환(유격수)"}]') == ["오지환"]
    # 포지션이 없으면 그대로
    assert A._arr('["홍창기"]') == ["홍창기"]


def test_포지션이_바뀐_주전은_결장이_아니다():
    regulars = {"양의지", "김민석", "박찬호"}
    today = A._arr('["양의지(지명타자)", "김민석(우익수)", "박찬호(3루수)"]')
    assert A.count_out(regulars, today) == 0


@pytest.mark.asyncio
async def test_주전결장을_lineup_events에서_읽는다():
    """🔴 `lineups` 는 KBO 0행 · NPB 2행뿐이었다(실측 2026-09-13).
       타순 본문은 `lineup_events` 에 있다 — 매일 KBO 4경기 8행.
    """
    import json
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 9, 13, 8, 0, tzinfo=timezone.utc)
    home, away = "Samsung Lions", "LG Twins"
    # 홈 주전 9명이 10경기 내내 나왔고, 오늘은 그중 둘이 빠졌다.
    hist = ["디아즈(1루수)", "강민호(포수)", "김지찬(중견수)", "김성윤(우익수)",
            "최형우(지명타자)", "류지혁(2루수)", "김영웅(3루수)",
            "심재훈(유격수)", "박승규(좌익수)"]
    today_home = ["디아즈(지명타자)", "강민호(포수)", "김지찬(중견수)",
                  "김성윤(우익수)", "류지혁(2루수)", "김영웅(3루수)",
                  "심재훈(유격수)"]                       # 최형우·박승규 빠짐(2명)
    seen = {}

    class _Pool:
        async def fetch(self, sql, *a):
            if "pa.pitcher" in sql or "g.home, g.away" in sql:
                return []
            seen["regulars_sql"] = sql
            # 🔴 팀 기준으로 조회해야 한다 — side 기준이면 상대 라인업이 섞인다
            team = a[0]
            bo = hist if team == home else ["x%d(포수)" % i for i in range(9)]
            return [{"batting_order": json.dumps(bo, ensure_ascii=False)}
                    for _ in range(10)]

        async def fetchval(self, sql, *a):
            seen["today_sql"] = sql
            side = a[1]
            bo = today_home if side == "home" else ["x%d(포수)" % i for i in range(9)]
            return json.dumps(bo, ensure_ascii=False)

    jg = {"sport": "kbo", "game_id": 1742, "home": home, "away": away,
          "starts_at": now, "lineup_status": "confirmed"}
    await A.attach(jg, _Pool())

    assert "lineup_events" in seen["regulars_sql"], seen["regulars_sql"]
    assert "lineup_events" in seen["today_sql"], seen["today_sql"]
    assert "out_starters" not in (jg.get("adj_missing") or []), jg.get("adj_missing")
    assert jg["adj_inputs"]["주전결장"] == {"home": 2, "away": 0}
    assert jg["out_starters"] == 2

    from app.engine import prob as P

    assert P.adjustments(jg)["주전결장"] == -3.0      # 2명 × −1.5


@pytest.mark.asyncio
async def test_원정이_더_빠지면_홈에_유리하게_잡힌다():
    """ADJ-3 와 같은 비대칭 — `max(0, …)` 이면 원정 결장은 영원히 0 이다."""
    import json
    from datetime import datetime, timezone

    now = datetime(2026, 9, 13, 8, 0, tzinfo=timezone.utc)
    hist = [f"p{i}(포수)" for i in range(9)]

    class _Pool:
        async def fetch(self, sql, *a):
            if "pa.pitcher" in sql or "g.home, g.away" in sql:
                return []
            return [{"batting_order": json.dumps(hist)} for _ in range(10)]

        async def fetchval(self, sql, *a):
            # 홈은 전원 출전, 원정은 3명 결장
            bo = hist if a[1] == "home" else hist[:6]
            return json.dumps(bo)

    jg = {"sport": "kbo", "game_id": 1, "home": "H", "away": "A",
          "starts_at": now, "lineup_status": "confirmed"}
    await A.attach(jg, _Pool())
    assert jg["adj_inputs"]["주전결장"] == {"home": 0, "away": 3}
    assert jg["out_starters"] == -3
    assert jg.get("out_starters_away") is None, "아무도 안 읽는 죽은 키다"

    from app.engine import prob as P

    assert P.adjustments(jg)["주전결장"] == 4.5       # 3명 × +1.5 (상한 5)
