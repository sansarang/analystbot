"""PA-16 계약 — U9 시장 흐름을 원장까지 잇는다.

🔴 종전 `record_move` 는 `classify(move_pp, news)` 만 불러 **steam 이 영원히
   안 떴다**(5분류가 4분류로 남음). `market_flow`·`book_disagree`·
   `adj_confirm` 도 호출 0건이었다.
"""
import inspect
import pathlib

from app.engine import odds_move as M
from app.engine import pick_ledger as PL

SRC = inspect.getsource(PL.record_move)


def test_n_books를_넘긴다():
    assert "n_books=n_books" in SRC, "steam 이 영원히 안 뜬다"


def test_같은_시점의_북만_센다():
    """🔴 반대 위험 — 시점이 다른 값을 섞으면 '동시에 밀렸다'가 거짓이 된다."""
    assert 'snap_tag") == now.get("snap_tag")' in SRC


def test_북수를_모르면_4분류다():
    """없는 정보로 더 센 라벨을 붙이지 않는다."""
    assert M.classify(move_pp=4.0, news=None, n_books=None).label != M.STEAM
    assert M.classify(move_pp=4.0, news=None, n_books=3).label == M.STEAM


def test_market_flow가_원장에_남는다():
    led = pathlib.Path("app/engine/pick_ledger.py").read_text(encoding="utf-8")
    assert "market_flow = $5::jsonb" in led
    for k in ('"class"', '"n_books"', '"book_disagree"', '"action"'):
        assert k in SRC, f"흐름 JSON 에 {k} 가 없다"


def test_adj_confirm을_부른다():
    assert "M.adj_confirm(" in SRC


def test_book_disagree를_부른다():
    assert "M.book_disagree(" in SRC


def test_저장_전용이다_취소를_실행하지_않는다():
    """🔴 반대 위험 — cancel·stake_mult 는 **발송 규칙**의 몫이다.

    여기서 픽을 지우거나 판돈을 바꾸면 측정 장치가 판정을 움직인다.
    """
    for banned in ('predicted_side =', 'confidence =', 'p_code =',
                   'stake', 'watch_state ='):
        assert banned not in SRC, f"저장 전용인데 {banned} 를 건드린다"


def test_move_class는_안_바뀐다():
    """🔴 반대 위험 — 종전 소비자는 move_class 를 읽는다."""
    led = pathlib.Path("app/engine/pick_ledger.py").read_text(encoding="utf-8")
    assert "move_class = $3" in led
    assert "flow_class = $3" in led, "같은 값이어야 한다"


def test_흐름_라벨을_손으로_안_적었다():
    """🔴 사본 금지 — 라벨은 odds_move 가 원본이다."""
    for lit in ('"steam"', '"contra"', '"money"', '"news"'):
        assert lit not in SRC, f"라벨을 손으로 적었다: {lit}"
