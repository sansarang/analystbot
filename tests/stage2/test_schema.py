"""단계 2 계약 — DB 스키마가 §1 용어·§3 스키마를 **제약으로** 집행하나.

🔴 **pydantic 과 DB 가 같은 규칙을 두 번 말한다.** 그것은 사본이 아니라 **두 겹**
   이다 — 앱을 거치지 않고 psql 로 넣는 길이 있고, 그 길에도 규칙이 있어야 한다.
   ⚠️ 다만 **두 겹이 어긋나면 사본의 병이 돌아온다.** 그래서
   `test_DB_제약이_pydantic_과_같은_값을_쓴다` 가 둘을 대조한다.

⚠️ 여기서는 **SQL 문자열**을 본다. 실제 DB 에 적용해 제약이 무는지는 주 세션이
   `psql` 로 절제했고 보고서 §2-③ 에 원문이 있다 — 이 스위트는 DB 없이 돈다.
"""
from __future__ import annotations

import re
from pathlib import Path

from app import blackboard as B
from app import types as T

ROOT = Path(__file__).resolve().parents[2]
SQL = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")

#: 🔴 SQL 의 단따옴표 토큰. **숫자를 포함한다** — `h2h_pattern` 이
#:    정확히 이 병으로 행을 빠뜨렸다(2-② 실측 · 리뷰 Q3).
#:    두 창이 서로 다른 정규식을 쓰던 것을 한 모양으로 묶었다.
TOKEN = re.compile(r"'([a-z0-9_]+)'")


def _tables() -> set[str]:
    return {ln.split("CREATE TABLE IF NOT EXISTS ")[1].split()[0]
            for ln in SQL.splitlines()
            if ln.startswith("CREATE TABLE IF NOT EXISTS ")}


def _block(table: str) -> str:
    """한 표의 정의 + 뒤따르는 제약. 🔴 다음 CREATE 까지."""
    i = SQL.index(f"CREATE TABLE IF NOT EXISTS {table} ")
    rest = SQL[i:]
    j = rest.find("CREATE TABLE IF NOT EXISTS ", 10)
    return rest if j < 0 else rest[:j]


#: 🔴 `--` 주석을 걷은 SQL. **파이썬 `strip_docs` 의 SQL 짝**이다.
#: ⚠️ 리뷰 Q1: 창이 앵커를 찾을 때 **앞선 주석이 그것을 품으면** 창이 산문을
#:    잡는다. 주석이 13유형을 단따옴표로 정확히 나열하면 **거짓 초록**이 된다 —
#:    D46 계열이고, `db/schema.sql` 의 주석은 제약을 길게 설명하는 문체다.
SQL_CODE = "\n".join(ln for ln in SQL.splitlines()
                     if not ln.lstrip().startswith("--"))


def _stmt(anchor: str) -> str:
    """`anchor` 로 시작하는 **한 SQL 문장**(다음 `;` 까지).

    🔴 **고정폭 창을 쓰지 않는다**(리뷰: `[:900]` 결함). 실측 2026-09-30:
       `variables_type_ck CHECK` 부터 이웃 `source_score_qtype_ck` 까지 **338자**
       뿐인데 창이 900자였다 — 이웃 제약의 13유형 목록이 통째로 들어와,
       `variables_type_ck` 에서 유형 하나를 빼도 이웃에서 주워 **초록이었다.**
       🔴 놓치는 방향이 위험한 방향이다: DB 가 그 유형을 더 엄격히 거부해
       단계 5 의 적재가 터지거나 조용히 버려진다.
    ⚠️ 내가 보고한 절제("DB 겹에서 한 유형 빼기")는 `replace()` 가 **양쪽 목록을
       동시에** 지워 엉뚱한 이유로 빨개진 것이었다 — 절제가 구멍을 못 봤다.
    """
    # 🔴 주석을 걷은 본문에서 찾는다(리뷰 Q1) — 주석이 창을 가로채지 못한다.
    # 🔴 **사유 없는 실패를 만들지 않는다**(리뷰 Q2). 종전 판은 제약이 사라지면
    #    `ValueError: substring not found` 만 떴고 *어느* 제약인지 말하지 않았다
    #    — 조용한 0 의 사촌이다.
    assert anchor in SQL_CODE, (
        f"SQL 에 `{anchor}` 가 없다 — 제약이 사라졌거나 이름이 바뀌었다. "
        f"주석에만 있고 코드에 없는 경우도 여기서 걸린다")
    i = SQL_CODE.index(anchor)
    j = SQL_CODE.find(";", i)
    assert j > 0, f"`{anchor}` 뒤에 문장 끝(;)이 없다 — SQL 이 잘렸나"
    return SQL_CODE[i:j]


# ══════════════════════════════════════════════════════════════════
# §9 단계 2 완료 조건 — DB 표
# ══════════════════════════════════════════════════════════════════

def test_단계_2_가_세울_표가_전부_있다():
    """🔴 §9 완료 조건 — *"DB 에 variables/scenarios/survival/ledger 표."*

    ⚠️ §3 STEP 1~3 이 *"direction 없는 항목은 background[] 로 분리 저장"* 이라
       못 박아 `background` 가 따로 필요하고, #10 이 `source_state`·
       `source_score` 를 더한다. 그래서 **10표다** — `NEXT.md` 의 "9표"는 수가
       하나 적었다. [§9 · §3 · #10]
    """
    want = {"board", "variables", "background", "premise_check", "sufficiency",
            "scenarios", "survival", "ledger", "source_state", "source_score"}
    missing = sorted(want - _tables())
    assert missing == [], f"단계 2 표가 없다: {missing}"


def test_스키마는_멱등하다():
    """🔴 `db/schema.sql` 2행의 약속 — 두 번 돌려도 깨지지 않는다.

    ⚠️ `ALTER TABLE ... ADD CONSTRAINT` 는 멱등이 아니므로 앞에
       `DROP CONSTRAINT IF EXISTS` 가 있어야 한다(#6 마이그레이션). [infra]
    """
    for stmt in re.findall(r"^CREATE TABLE(?! IF NOT EXISTS)", SQL, re.M):
        raise AssertionError(f"멱등하지 않은 문장: {stmt}")
    for stmt in re.findall(r"^ALTER TABLE .+ ADD COLUMN(?! IF NOT EXISTS)",
                           SQL, re.M):
        raise AssertionError(f"멱등하지 않은 문장: {stmt}")
    for m in re.finditer(r"^ALTER TABLE (\S+) ADD CONSTRAINT (\S+)", SQL, re.M):
        table, name = m.group(1), m.group(2)
        assert f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}" in SQL, \
            f"{name} 을 더하기 전에 DROP IF EXISTS 가 없다 — 두 번 돌리면 터진다"


# ══════════════════════════════════════════════════════════════════
# 🔴 두 겹이 어긋나지 않나 — pydantic 과 DB 가 같은 값을 쓰나
# ══════════════════════════════════════════════════════════════════

def test_DB_제약이_pydantic_과_같은_값을_쓴다():
    """🔴 **두 겹은 어긋나면 사본의 병이 된다.** 값 집합을 대조한다. [§1]

    ⚠️ 이 계약이 없으면 `types.py` 에서 값을 하나 더해도 DB 는 그것을 거부하고,
       그 어긋남은 **운영에서 적재가 터질 때**야 보인다.
    """
    blk = _block("variables")
    for d in T.Direction.__args__:
        assert f"'{d}'" in blk, f"DB 의 direction 집합에 {d} 가 없다"
    for h in T.Hardness.__args__:
        assert f"'{h}'" in blk, f"DB 의 hardness 집합에 {h} 가 없다"
    # 🔴 §4 가중치 — DB 도 hardness 가 weight 를 정한다
    for h, w in T.WEIGHT_OF.items():
        assert re.search(rf"hardness = '{h}'\s+AND weight = {w}", blk), \
            f"DB 가 {h}→{w} 를 강제하지 않는다"

    sv = _block("survival")
    for v in T.Verdict.__args__:
        assert f"'{v}'" in sv, f"DB 의 verdict 집합에 {v} 가 없다"
    # 🔴 §6 문턱이 두 곳에서 같아야 한다
    assert f"survival >= {T.NAME_AT}" in sv, "DB 의 name 문턱이 §6 과 다르다"
    assert f"survival >= {T.SMALL_AT}" in sv, "DB 의 small 문턱이 §6 과 다르다"

    su = _block("sufficiency")
    assert f"n_directional < {T.MIN_DIRECTIONAL}" in su, \
        "DB 의 자료 부족 문턱이 §1 과 다르다"

    sc = _block("scenarios")
    for sid in T.ScenarioId.__args__:
        assert f"'{sid}'" in sc, f"DB 의 시나리오 id 집합에 {sid} 가 없다"


def test_DB_가_핵심_규칙을_제약으로_막는다():
    """🔴 앱을 거치지 않는 길(psql)에도 규칙이 있어야 한다. [§9 게이트 · §3 · §6]

    ⚠️ 주 세션이 실제 DB 에 넣어 **일곱 제약이 전부 무는 것**을 봤다(보고서 §2-③).
       여기서는 그 제약이 **파일에 남아 있는지**를 지킨다 — 지워지면 빨개진다.
    """
    v = _block("variables")
    # ⚠️ 정렬 공백을 고정하지 않는다(리뷰 M3) — 스키마를 재정렬하면 제약이
    #    온전한데도 빨개진다.
    assert re.search(r"direction\s+TEXT NOT NULL", v), \
        "🔴 §9 게이트: direction 이 NULL 가능하다"
    assert "variables_weight_ck" in v
    assert "variables_source_ck" in v, "출처 없는 변수를 막지 않는다"
    assert re.search(r"source_url\s+TEXT NOT NULL", v)

    assert "survival_name_ck" in _block("survival"), \
        "🔴 §12 — 생존 1.0 아닌데 이름을 적는 것을 막지 않는다(아르메니아 +0.5)"
    assert "sufficiency_follows_counts_ck" in _block("sufficiency")
    assert "scenarios_scores_ck" in _block("scenarios")
    assert "premise_replacement_ck" in _block("premise_check")


def test_배당_숫자_칸이_스키마에_없다():
    """🔴 §0 · §11-9 — 가격은 `research` 스키마에만. 판정 경로 접근 0건.

    ⚠️ `line` 은 **기준선**이지 가격이 아니다(§1 마켓). 이름으로 구분한다. [§0]
    """
    # ⚠️ `"stake"` 를 부분문자열로 보면 **§4 유형 `stakes`** 에 걸린다(리뷰 M4).
    #    그 블록 주석에 13유형을 나열하는 순간 거짓 빨강이다 — 낱말 경계로 본다.
    for table in ("board", "survival", "variables", "scenarios", "ledger"):
        blk = _block(table).lower()
        for bad in ("odds", "price", "payout", "decimal", "배당"):
            assert bad not in blk, f"{table} 에 가격 칸이 있다: {bad}"
        assert not re.search(r"\bstake\b", blk), f"{table} 에 stake 칸이 있다"


# ══════════════════════════════════════════════════════════════════
# #6 — `evidence.used_in` 값 교체
# ══════════════════════════════════════════════════════════════════

def test_used_in_이_폐기_어휘를_거부한다():
    """🔴 #6 · §8 — `lean` 은 폐기 어휘다. DB 가 거부해야 한다.

    사용자 결정 2026-09-30: 다섯 값으로 교체하고 **원값은 `legacy_used_in` 에
    보존**한다. [§8 · #6]
    """
    assert "legacy_used_in" in SQL, "🔴 원값을 보존하는 칸이 없다 — 되짚을 수 없다"
    ck = _stmt("ADD CONSTRAINT evidence_used_in_ck CHECK")
    allowed = set(re.findall(r"'([a-z_]+)'", ck))
    assert allowed == set(B.USED_IN), \
        (f"DB 가 허용하는 값 {sorted(allowed)} ≠ "
         f"`blackboard.USED_IN` {sorted(B.USED_IN)}")
    # 🔴 폐기 어휘가 허용 집합에 없다. (위 등호가 이미 보장하지만, 왜 그래야
    #    하는지를 이름으로 남긴다 — `lean` 은 v4 §8 폐기 목록이다.)
    assert not {"lean", "counter", "trigger"} & allowed, \
        f"폐기 어휘가 아직 허용된다: {sorted({'lean','counter','trigger'} & allowed)}"
    assert "legacy_used_in = used_in" in SQL, "원값을 옮기는 마이그레이션이 없다"




def test_counter_와_trigger_는_폐기_대상이_아니다():
    """⚠️ **정본을 확인해 적는다** — 다음 세션이 "같이 지워야 하나" 헷갈리지 않게.

    ⚠️ **이유를 정확히 적는다**(리뷰 M6 — 첫 판이 느슨했다):
    - `counter` → `opposite` 는 **폐기가 아니라 §8 이관의 이행**이다. §8 이
      *"judge.py 의 '반증 1:1' → STEP 3 세포 생성"* 으로 이관을 지시했고,
      폐기된 것은 *"반증 추적의 '확신 갱신' 로직"* 이며 **반대 방향 변수 검색은
      남는다.**
    - `trigger` → `lineup_rerun` 도 마찬가지다. 🔴 `v3 §9 방아쇠 유형표`는
      **폐기 목록에 있다**(재실행으로 대체) — 그러니 *"폐기 목록에 없다"* 고
      뭉뚱그리면 틀린다. 폐기된 것은 **유형표와 등급 상향/하향**이고, §1 이
      *"방아쇠 재실행 … 등급 상향/하향 개념은 없다"* 로 **재실행 자체는 유지**한다.
      살아남은 개념의 이름을 쓴 것이다. [§8 · §1]
    """
    inbox = (ROOT / "docs/fable/inbox/2026-09-29_v4.md").read_text(encoding="utf-8")
    dead = inbox.split("**폐기 (코드·문서에서 제거, 흔적 없이)**")[1][:400]
    assert "lean" in dead, "§8 폐기 목록에 lean 이 없다 — 절을 잘못 잘랐다"
    assert "방아쇠 재실행" in inbox, "§1 이 방아쇠 재실행을 유지한다"
    # 🔴 질문 유형 이름은 그대로다 — `used_in` 값과 다른 것이다
    assert B._used_in("counter:x") == "opposite"
    assert B._used_in("lineup:x") == "lineup_rerun"


def test_DB_의_type_enum_이_yaml_과_같다():
    """🔴 **두 겹이 사본 관계를 만든다 — 그 대조가 이 계약이다.** [§4 · §1]

    `variables_type_ck` 의 13유형은 `config/variable_types.yaml` 의 사본이다.
    ⚠️ 종전 판은 `type: str` 에 *"값 검사는 yaml 이 한다"* 는 **주석만** 달고
       실제 대조가 없었다(리뷰 B2) — `type="오타"` 가 저장됐다. 두 겹을 세웠으니
       이제 **두 겹이 어긋나는 것**이 새 위험이고, 그것을 여기서 막는다.
    """
    from app import rules as R

    want = set(R.variable_types())
    got = set(re.findall(TOKEN,
                         _stmt("ADD CONSTRAINT variables_type_ck CHECK")))
    assert got == want, (f"variables_type_ck 의 유형 {sorted(got - want)} 여분 · "
                         f"{sorted(want - got)} 누락 — yaml 과 어긋났다")

    # 🔴 **`source_score_qtype_ck` 는 여기 없다.** 단계 2 가 그 제약에도 §4 유형
    #    13종을 걸고 이 계약으로 잠갔는데, **전제가 틀렸다**: 그 열은 §19-e 의
    #    `question_type` 이고 §19-a 가 정의한 **세포 질문 타입**이다
    #    (`slate`·`lineup`·`counter` …). 겹치는 것은 `absence` 하나뿐이다.
    #    ⚠️ 실측 2026-09-30: 단계 3 이 점수표 적재를 잇자 `question_type='lineup'`
    #       이 바로 `CheckViolationError` 로 튕겼다. **표만 세우고 쓰는 코드가
    #       없어서** 단계 2 에서는 드러날 수 없었다(CLAUDE.md §배선: 안 이어진
    #       코드는 없는 코드보다 나쁘다).
    #    → 그 제약의 대조는 `tests/stage3/test_timeline.py` 의
    #      `test_DB_제약이_세포_질문_타입과_같다` 가 `cells.Q_TYPES` 로 한다.


def test_pydantic_이_유형표에_없는_type_을_거부한다():
    """🔴 §1 변수 행의 `type`(**§4 enum**) — 자유 문자열이면 오타가 통과한다. [§1 · §4]

    ⚠️ 오타는 단계 5·6 의 §5-c 유형 매칭에서 **조용히 안 걸린다** — R1 난타전이
       `absence` 를 찾는데 `absense` 로 저장돼 있으면 시나리오가 안 생긴다.
       v4 §12 M6(아르메니아 난타전 누락)의 재발 경로다.
    """
    import pytest
    from datetime import datetime, timedelta, timezone
    from pydantic import ValidationError

    kst = timezone(timedelta(hours=9))
    ok = dict(id="v1", direction="home", hardness="hard", weight=1.0,
              text="x", source_url="https://a",
              published_at=datetime(2026, 9, 28, tzinfo=kst))
    T.Variable(type="stakes", **ok)                      # 표에 있는 것
    for bad in ("stake", "absense", "오타든뭐든", ""):
        with pytest.raises(ValidationError, match="유형표에 없는"):
            T.Variable(type=bad, **ok)


def test_DB_의_market_type_enum_이_타입과_같다():
    """🔴 **두 겹 중 한 겹이 비어 있었다**(리뷰 M1). [§1]

    pydantic 은 `MarketType` Literal 7종으로 닫았는데 `board.market_type`·
    `survival.market_type` 은 `TEXT NOT NULL` 뿐이라 **psql 로는 아무 문자열이나
    들어갔다.** §11-9 의 격리는 앱 경로만이 아니다.
    ⚠️ SQL 의 7개는 `types.MarketType` 의 사본이므로 여기서 등호로 묶는다.
    """
    want = set(T.MarketType.__args__)
    for name in ("board_market_type_ck", "survival_market_type_ck"):
        got = set(re.findall(TOKEN, _stmt(f"ADD CONSTRAINT {name} CHECK")))
        assert got == want, (f"{name}: {sorted(got - want)} 여분 · "
                             f"{sorted(want - got)} 누락")
