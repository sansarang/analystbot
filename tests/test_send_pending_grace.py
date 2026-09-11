"""W-SEND-PENDING — 발송 창 진입 직후의 유예 계약 (SP-1).

🔴 결함: `check_pending_sends` 는 창이 **열리는 순간부터** 경보 대상으로 셌다.
   발송은 폴링 틱(5분)이 와야 실제로 나가는데 워치독도 5분 주기라, 워치독
   틱이 폴링 틱보다 먼저 오면 **정상 경기가 항상 걸린다.**
   실측 2026-09-10 (docs/TIMING_2026-09-11.md §2-A): 경보 3건 전부 경보
   1분 안에 카드가 나갔다 — Texas 는 T-177 발송으로 `SEND_OPEN_MIN` 180
   바로 뒤였다. **오탐 100%.**

🔴 반대 위험도 같이 잰다: 유예가 커지면 진짜 미발송을 놓친다. 창이 가장 좁은
   NPB(T-40)에서 사각이 유예(5분)만큼만인지, 보장선 부근에서는 여전히 우는지
   아래가 계약으로 못 박는다.

⚠️ 이 유예는 **감시 전용**이다. `in_send_window`(발송 경로)는 건드리지 않는다 —
   카드는 종전대로 창이 열리는 즉시 나간다.
"""

from datetime import UTC, datetime, timedelta

import pytest

# ⚠️ 새 심볼(`SEND_WATCH_GRACE_MIN`·`send_overdue`)은 **모듈 최상단에서
#    임포트하지 않는다.** 그러면 수정 전 코드에서 이 파일이 통째로
#    ImportError 로 죽어, "결함을 겨눈 단언"이 아니라 "심볼이 없다"로
#    통과해 버린다. 필요한 테스트 안에서만 가져온다.
from app.engine.pregame_push import SEND_OPEN_MIN, card_sig_key, in_send_window
from app.pipeline import mlb_slate_date, today_kst
from app.watchdog import check_pending_sends

WATCH = open("app/watchdog.py", encoding="utf-8").read()


def _segment() -> str:
    i = WATCH.index("async def check_pending_sends")
    return WATCH[i:WATCH.index("\nasync def ", i + 10)]


class _Pool:
    def __init__(self, rows=()):
        self.rows = list(rows)

    async def fetch(self, sql, *args):
        return self.rows


class _Redis:
    """`analysis:*` 는 있고 카드 서명은 없는 상태 — "판정은 됐는데 안 나갔다"."""

    def __init__(self, sent=(), judged=True):
        self.sent = {card_sig_key(g) for g in sent}
        self.judged = judged

    async def get(self, key):
        if key in self.sent:
            return "sig"
        if key.startswith("analysis:"):
            return "{}" if self.judged else None
        return None


def _g(gid, sport="kbo", left=60.0, away="A팀", home="B팀"):
    """`left` 분 뒤에 시작하는 경기 행."""
    return {"id": gid, "sport": sport, "home": home, "away": away,
            "starts_at": datetime.now(UTC) + timedelta(minutes=left)}


# ═══════════════ ① 오탐 — 창에 막 들어온 경기는 울리지 않는다

@pytest.mark.asyncio
async def test_창에_막_들어온_경기는_울리지_않는다():
    """🔴 이 결함의 본체. KBO 창은 T-70 이고 T-69 는 폴링 한 틱도 안 지났다."""
    out = await check_pending_sends(_Pool([_g(1, "kbo", left=69)]), _Redis())
    assert out == [], f"폴링이 아직 한 번도 안 돌았는데 울었다: {out}"


@pytest.mark.asyncio
async def test_MLB도_같다_실측_Texas_T_177():
    """실측된 오탐 그대로 — 창(T-180) 3분 뒤."""
    assert await check_pending_sends(
        _Pool([_g(2, "mlb", left=177, away="Texas", home="Seattle")]),
        _Redis()) == []


# ═══════════════ ② 반대 위험 — 진짜 미발송은 여전히 잡는다

@pytest.mark.asyncio
async def test_유예를_넘기면_운다():
    out = await check_pending_sends(
        _Pool([_g(3, "kbo", left=60, away="키움", home="두산")]), _Redis())
    assert len(out) == 1
    code, target, detail = out[0]
    assert (code, target) == ("W-SEND-PENDING", "1경기")
    assert "키움@두산" in detail


@pytest.mark.asyncio
async def test_보장선_부근의_진짜_미발송은_반드시_운다():
    """T-30 을 넘겨 카드가 없는 것은 유예로 덮이면 안 된다."""
    out = await check_pending_sends(_Pool([_g(4, "npb", left=10)]), _Redis())
    assert len(out) == 1 and out[0][0] == "W-SEND-PENDING"


@pytest.mark.asyncio
async def test_NPB_사각은_유예만큼만이다():
    """창이 가장 좁은 NPB(T-40). 유예 2.0분 — T-39 조용 · T-36 경보.

    🔴 [GRC-1] 유예가 5분 고정일 때 이 값은 T-38/T-34 였다. 창 비례(5%)로
       바뀌며 NPB 유예가 **줄었다** — 감시가 더 빨리 운다.
    """
    assert await check_pending_sends(_Pool([_g(5, "npb", left=39)]), _Redis()) == []
    assert len(await check_pending_sends(
        _Pool([_g(5, "npb", left=36)]), _Redis())) == 1


# ═══════════════ ③ 종전 계약은 그대로

@pytest.mark.asyncio
async def test_이미_나간_카드는_세지_않는다():
    assert await check_pending_sends(
        _Pool([_g(6, "kbo", left=60)]), _Redis(sent=[6])) == []


@pytest.mark.asyncio
async def test_판정_캐시가_없으면_다른_경보_소관이다():
    assert await check_pending_sends(
        _Pool([_g(7, "kbo", left=60)]), _Redis(judged=False)) == []


@pytest.mark.asyncio
async def test_이미_시작한_경기는_세지_않는다():
    assert await check_pending_sends(_Pool([_g(8, "kbo", left=-1)]), _Redis()) == []


# ═══════════════ ④ 발송 경로는 건드리지 않았다

def test_발송_창은_종전대로_즉시_열린다():
    """유예는 **감시 전용**이다. 카드는 창이 열리는 순간부터 나가야 한다."""
    from app.engine.pregame_push import send_overdue

    just_open = datetime.now(UTC) + timedelta(minutes=SEND_OPEN_MIN["kbo"] - 1)
    assert in_send_window("kbo", just_open) is True
    assert send_overdue("kbo", just_open) is False


def test_유예는_창의_5퍼센트다():
    """🔴 [GRC-1] 종목별 숫자를 적지 않는다 — 창 하나에서 파생시킨다."""
    from app.engine.pregame_push import SEND_WATCH_GRACE_RATIO

    from app.engine.pregame_push import grace_min

    assert SEND_WATCH_GRACE_RATIO == 0.05
    for sp, open_m in SEND_OPEN_MIN.items():
        assert grace_min(sp) == open_m * 0.05, sp


def test_사각_비율이_종목마다_같다():
    """고정 5분이던 시절의 사각은 npb 12.5% · kbo 7.1% · mlb 2.8% 였다."""
    from app.engine.pregame_push import grace_min

    ratios = {sp: grace_min(sp) / open_m for sp, open_m in SEND_OPEN_MIN.items()}
    assert len(set(round(v, 6) for v in ratios.values())) == 1, ratios


def test_MLB_유예가_늘어_정상_발송에_덜_운다():
    """실측 2026-09-10 Rays@Braves: T-177 경보 → T-161 발송(운영상 정상).

    창 T-180 에 유예 9분이면 T-171 까지는 조용하다. 종전 5분(T-175)보다
    4분 더 참는다 — 그래도 16분 걸린 그 건은 여전히 운다. **완전히
    없애지 못한다는 사실을 숨기지 않는다.**
    """
    from app.engine.pregame_push import grace_min

    assert grace_min("mlb") == 9.0


# ═══════════════ ⑤ 사본 금지 — 워치독은 숫자를 갖지 않는다

def test_워치독은_창_산술을_스스로_하지_않는다():
    """🔴 실사고 2026-09-02: 손으로 옮긴 주기가 오탐 4건을 냈다.

    창·유예의 원본은 `pregame_push` 하나다. 워치독은 판정을 import 한다.
    """
    seg = _segment()
    assert "send_overdue" in seg, "워치독이 원본 판정을 쓰지 않는다"
    assert "SEND_OPEN_MIN" not in seg, "창 상수가 워치독으로 새어 나왔다"
    assert "GRACE" not in seg, "유예 값이 워치독에 사본으로 생겼다"
