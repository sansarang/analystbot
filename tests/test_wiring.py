"""배선 계약 — 🔴 **만든 것은 반드시 부르는 곳이 있어야 한다.**

함수가 옳은지가 아니라 **호출부가 그것을 부르는지**를 검사한다. 안 이어진
코드는 없는 코드보다 나쁘다 — 있는 줄 알고 아무도 다시 안 본다.
"""
from __future__ import annotations

import ast
import importlib
import inspect
import os
import re
from pathlib import Path

import pytest

from tests._helpers import strip_docs

from app import card, ids, judge, llm, run, sources, tg, verify
from app import scheduler as S
from app.bot import main as B

ROOT = Path(__file__).resolve().parents[1]


def test_스케줄러가_수집만_돈다():
    """🔴 v4 단계 1 — 판정·발송·채점 주기를 걷어냈다."""
    src = inspect.getsource(S)
    assert "collect_slate" in src
    assert "run_slate" not in src
    assert "score_finals" not in src
    assert "send_card" not in src


def test_수집이_판정보다_먼저_돈다():
    """🔴 순서가 바뀌면 첫 사이클이 빈 DB 를 읽는다."""
    src = inspect.getsource(S.run_once)
    assert src.index("collect(") < src.index("collect_slate(")


def test_수집_나열을_발송하지_않는다():
    """🔴 v4 §11-11 — 발송 스위치는 단계 9 전까지 off.

    지금 나가는 것은 수집 나열이다 — 보내면 근거 없는 카드가 된다.
    """
    src = inspect.getsource(S.run_once)
    assert "tg.send" not in src


def test_흐름이_수집_소스를_부른다():
    """★ 만든 공급 메서드가 안 불리면 그 자료는 영영 안 쓰인다."""
    src = (inspect.getsource(run.collect_game)
           + inspect.getsource(run.collect_slate))
    for name in ("slate", "absences", "starters", "intents"):
        assert f".{name}(" in src, f"흐름이 {name} 을 안 부른다"


def test_봇이_흐름을_부른다():
    """★ 봇 명령이 수집 흐름을 안 부르면 사용자에게 아무것도 안 간다.

    🔴 **단계 1 이 이 배선을 직접 고쳐 놓고 계약은 지웠다**(리뷰 A3·A5).
       `run_slate` → `collect_slate` 로 호출부를 바꾼 것이 `d0c6000` 인데,
       같은 커밋이 그것을 잠그던 계약을 함께 지웠다. `from app.bot import
       main as B` 만 남고 **B 를 쓰는 테스트가 하나도 없었다.**
       사용자 결정 2026-09-30: *"봇 배선만 지금, 나머지 4건은 단계 2."*

    ⚠️ **문자열로 보면 안 된다.** `from app.run import collect_slate` 라는
       import 줄이 소스에 있어서, 호출을 지워도 `"collect_slate" in src` 는
       참이다(실측 2026-09-30 — 절제가 통과해 버렸다). **부르는 자리**를 본다.
    """
    tree = ast.parse(inspect.getsource(B))
    called = {n.func.id if isinstance(n.func, ast.Name) else
              getattr(n.func, "attr", "")
              for n in ast.walk(tree) if isinstance(n, ast.Call)}
    assert "collect_slate" in called, "봇이 수집 흐름을 **부르지** 않는다"


def test_스케줄러가_기동시_스키마를_적용한다():
    """🔴 그래서 배포는 스케줄러가 먼저다."""
    assert "apply_schema" in inspect.getsource(S.main)


def test_발송이_금지_어구를_막는다():
    assert "has_banned" in inspect.getsource(tg.send)


def test_발송_스위치가_기본_꺼짐이다():
    """🔴 사용자만 켠다."""
    from app.config import Settings
    assert Settings().send_enabled is False


def test_DbSources가_인터페이스를_전부_구현한다():
    base = {n for n, _ in inspect.getmembers(run.Sources,
                                             inspect.isfunction)
            if not n.startswith("_")}
    impl = {n for n, _ in inspect.getmembers(sources.DbSources,
                                             inspect.isfunction)
            if not n.startswith("_")}
    assert base <= impl, base - impl


def test_검증기가_수집기보다_먼저_있다():
    """🔴 §16-b 단계 1 — 검색기는 검증기 뒤에 붙인다."""
    assert (ROOT / "app" / "verify.py").is_file()
    assert not list((ROOT / "app").glob("collectors*")), \
        "수집기가 검증기보다 먼저 들어왔다"


def test_LLM_예산이_흐름에_배선돼_있다():
    """§17-e — 경기당 L1~L5 합 20 상한."""
    assert "Budget" in inspect.getsource(run)
    assert "budget.used" in inspect.getsource(sources.persist)


def test_못_잰_칸이_원장에_적힌다():
    """🔴 §5 — 개수만이 아니라 **이름**을 남긴다."""
    assert "unknowns" in inspect.getsource(sources.persist)
    assert "g.unknowns" in inspect.getsource(sources.persist)


def test_health가_못_잰_칸을_드러낸다():
    from app import main as M
    assert "unknowns" in inspect.getsource(M.health)


def _credits(mods: dict) -> dict[str, int]:
    """`app/**` 안의 호출을 **정규화된 이름**(`app.모듈.함수`)으로 센다.

    🔴 **이름으로 세지 않는다.** 이름만 세면 다른 모듈의 같은 이름이 배선을
       대신 채워 준다. 실측으로 두 번 걸렸다:

       | 숨은 고아 | 누가 가려 줬나 |
       |---|---|
       | `app.cassette.index` | `app/collect/npb.py` 의 `cells.index(pos)` — **리스트 메서드**(리뷰 B2) |
       | `app.extract.run` | 다른 모듈의 `run(` — 흔한 함수 이름이다(2026-10-01) |

       첫 번째는 *파이썬 기본 자료형의 메서드 이름*을 가려 막았다. 그 방어는
       **두 번째를 못 막았다** — `run` 은 기본 자료형 메서드가 아니다.
       🔴 그래서 **이름 가리기를 버리고, 들여온 곳으로 호출을 귀속시킨다.**
       그것이 원본이다 — 손으로 유지할 목록이 0 이다.

    귀속 규칙(파일 하나 안에서):

    1. `from app.X import fn` → 그 파일의 맨 `fn` 은 **`app.X.fn`** 에 센다
    2. `from app import X` · `import app.X` → `X.fn` 은 **`app.X.fn`** 에 센다
    3. 그 파일이 스스로 정의한 이름 → **자기 모듈**에 센다(모듈 안 호출도 배선이다)
    4. **표를 거친 호출**(`mod = ADAPTERS[league]` → `mod.sources_slate(...)`)은
       그 파일이 **들여온 모듈 중 그 이름을 정의한 것**에 센다. 🔴 넓히는 폭이
       *그 파일이 실제로 들여온 모듈*로 묶여 있다 — `app/collect/ingest.py` 가
       다섯 어댑터를 표로 부르는 것이 그 꼴이고, 그것은 **진짜 배선이다**.
    5. **`getattr(모듈, "이름")`** — 문자열로 부르는 것도 호출부다. 그 파일이
       들여온 모듈 중 그 이름을 정의한 것에 센다(4 와 같은 폭).
       ⚠️ 실측 2026-10-01: `ingest` 가 `getattr(ADAPTERS[league], "sources_context")`
          로 종목별 깊이를 부르는데, 문자열이라 **고아로 잡혔다.** 동적 디스패치는
          배선이다 — 못 보면 "안 이어졌다"고 거짓 보고를 한다.
    6. 어느 것도 아니면 **아무 데도 안 센다** — 모르는 것을 배선으로 세지 않는다

    ⚠️ 데코레이터로 등록된 핸들러(`@dp.message(...)`)는 이름이 어디서도 *참조*되지
       않는다 — 그것은 **등록이 곧 호출부**이므로 자기 모듈에 센다(실측 2026-09-30:
       `cmd_slate`·`cmd_health`·`main.health` 가 거짓 고아로 잡혔다).
    """
    got: dict[str, int] = {}

    def bump(fqn: str) -> None:
        got[fqn] = got.get(fqn, 0) + 1

    #: 모듈마다 **정의된 함수 이름**. 표를 거친 호출을 귀속시킬 때 쓴다.
    defs_of = {
        n: {f.name for f in ast.walk(ast.parse(
            Path(m.__file__).read_text(encoding="utf-8")))
            if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for n, m in mods.items()}

    for mod_name, mod in mods.items():
        src = Path(mod.__file__)
        tree = ast.parse(src.read_text(encoding="utf-8"))
        local_defs = {n.name for n in ast.walk(tree)
                      if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        bind: dict[str, str] = {}       # 들여온 함수 이름 → 정규화된 이름
        alias: dict[str, str] = {}      # 들여온 모듈 별칭 → 모듈 이름
        imported: set[str] = set()      # 들여온 `app.*` 모듈 (표 호출 귀속용)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) \
                    and (node.module or "").startswith("app"):
                for a in node.names:
                    target = f"{node.module}.{a.name}"
                    if target in mods:
                        alias[a.asname or a.name] = target
                        imported.add(target)
                    else:
                        bind[a.asname or a.name] = target
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.startswith("app") and a.name in mods:
                        alias[a.asname or a.name.split(".")[-1]] = a.name
                        imported.add(a.name)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and node.decorator_list:
                bump(f"{mod_name}.{node.name}")
            elif isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name) and node.value.id in alias:
                    bump(f"{alias[node.value.id]}.{node.attr}")
                else:
                    # 🔴 표를 거친 호출 — **들여온 모듈 중 그 이름을 가진 것**에만
                    for m in imported:
                        if node.attr in defs_of.get(m, ()):
                            bump(f"{m}.{node.attr}")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id == "getattr" and len(node.args) >= 2 \
                    and isinstance(node.args[1], ast.Constant) \
                    and isinstance(node.args[1].value, str):
                # 🔴 문자열로 부르는 것도 호출부다 — 들여온 모듈 중 그 이름을 가진 것에
                attr = node.args[1].value
                for m in imported:
                    if attr in defs_of.get(m, ()):
                        bump(f"{m}.{attr}")
            elif isinstance(node, ast.Name):
                if node.id in bind:
                    bump(bind[node.id])
                elif node.id in local_defs:
                    bump(f"{mod_name}.{node.id}")
    return got


def test_배선_세기_자체가_동작한다():
    """★ 🔴 **계약의 계약.** 세는 장치가 망가지면 위 계약이 공허한 참이 된다.

    ⚠️ 리뷰 B1 이 잡은 병이 그것이다 — 계약이 아무것도 검사하지 않은 채 초록이었다.
    🔴 여기서 잠그는 것은 **같은 이름이 모듈별로 갈리나**다. 그것이 2026-10-01 에
       `app.extract.run` 을 숨겼던 바로 그 구멍이다.
    """
    mods = {}
    for path in sorted((ROOT / "app").rglob("*.py")):
        parts = list(path.relative_to(ROOT).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        name = ".".join(parts)
        if name.endswith("__main__"):
            continue
        mods[name] = importlib.import_module(name)
    used = _credits(mods)
    assert len(used) > 100, f"귀속된 호출이 {len(used)}건뿐이다 — 세는 장치를 보라"

    # 🔴 **이름이 같고 모듈이 다른 함수가 갈려야 한다.**
    same_name = {}
    for key in used:
        same_name.setdefault(key.rsplit(".", 1)[1], set()).add(key)
    split = [n for n, keys in same_name.items() if len(keys) > 1]
    assert split, "같은 이름이 여러 모듈에 귀속된 사례가 0건이다 — 이름으로 세고 있다"

    # 🔴 **알려진 배선은 잡히고**, 들여오지 않은 모듈의 같은 이름은 **안 잡힌다**
    assert used.get("app.verify.quote_grounded", 0) > 0, \
        "본문 대조가 어디서도 안 불린다 — 그럴 리 없다"
    # 🔴 **2026-10-02 에 이어졌다**(사용자 지시 *"핵심은 '검색'이 아니라 '읽기'다"*).
    #    `Cell._extracted` 가 규칙 파서 0건 뒤에 §17-b L1~L3 을 부른다.
    #    ⚠️ 전 판은 *"귀속이 0 이어야 한다"* 로 **배선이 없음을 자가 검사**에 썼다 —
    #       이으면 그 검사가 거짓이 된다. 이제 **1 이상**인지를 본다.
    assert used.get("app.extract.run", 0) >= 1, (
        "`app.extract.run` 이 안 불린다 — 이어 놓고 끊겼는지 보라")


def test_남은_모듈에_고아_공개함수가_없다():
    """★ 공개 함수가 어디서도 안 불리면 배선이 끊긴 것이다.

    ⚠️ 예외는 진입점(`main`)과 자료형·상수뿐이다.
    🔴 **아직 안 이어진 것은 이름을 적어 남긴다** — 조용히 두면 "있는 줄" 알고
       아무도 다시 안 본다. 그 단계가 오면 목록에서 빼고 이 계약을 고친다.
    """
    #: (함수, 이어질 단계) — 🔴 목록이 비는 것이 목표다
    #
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **2026-10-02 — 목록이 비었다** (사용자 지시)
    # ══════════════════════════════════════════════════════════════════
    #
    # > 배선 안 된 거도 마무리 지어라 … 사유를 남기는 거는 좋지만 … 문제 해결을
    # > 반드시 해라 … **사유만 남기고 나중에 하지 않으면 안 하는 이보다 못하다**
    #
    # 그 말이 맞다. 마지막 다섯을 **전부 이었다**:
    #
    #   app.tg.send               → `analyze.deliver` · `scheduler card`
    #                               🔴 스위치(§11-11)가 꺼져 있으면 **만들고 멈춘다**.
    #                                  길을 안 이어 두면 단계 9 에서 **처음 돌리는
    #                                  코드가 진짜 발송 경로**가 된다 — 그게 더 위험하다
    #   app.rules.by_sec7_rule    → `survive._r6_missing` 가 §7 번호로 규칙을 찾는다
    #                               (`1.5`·`2` 를 코드에서 뺐다)
    #   app.rules.added_types     → 카드 블록 1 이 *"v4 표에 없는 유형"* 을 밝힌다
    #   app.bot.aliases.find_team → `analyze.answer` — 사용자가 `다저스` 라고 물어도 찾는다
    #   app.bot.aliases.kr_team   → `analyze.render` — 카드에 한국어 표기로 적는다
    #
    # 🔴 그 과정에서 **죽은 코드를 찾았다**: `kr_team` 의 퍼지 경로가
    #    `app.collectors.football`(**삭제된 모듈**)을 불렀다. 정확 일치로 끝나는
    #    호출만 돌았고 퍼지로 내려가면 ImportError 였다 — 아무도 안 불러서 아무도
    #    몰랐다. *"안 이어진 코드는 없는 코드보다 나쁘다"* 가 그 자리다.
    NOT_WIRED = {
        # ── 단계 2 가 만든 것 (2026-09-30). 🔴 표는 만들었고 **읽는 곳은 뒤 단계다.**
        # ⚠️ `app.rules.premise_types` 는 **빠졌다** — 2026-10-02 에 이어졌다.
        #    `app/classify.Classified.to_variable` 이 `is_premise` 를 §4 전제
        #    유형에서 배정한다(사용자 지시 ⑧). 🔴 되감기 계약이 그 자리에서
        #    "빼라"고 말했다 — 목록이 거짓이 되기 전에 기계가 먼저 알렸다.
        # ⚠️ `app.rules.templates` 는 **빠졌다** — 2026-10-02 에 이어졌다.
        #    `app/scenarios.py` 가 §5-b 스코어 집합을 거기서 읽는다(사용자 지시 ⑥).
        #    🔴 되감기 계약이 그 자리에서 "빼라"고 말했다.
        # ⚠️ `app.rules.cross_rules` 는 여기 없다 — `by_sec7_rule` 이 부르므로
        #    되감기 계약이 "빼라"고 했다. 🔴 **그 호출자 자신이 미배선이다**(아래
        #    줄) — 그러니 실제 정보는 `by_sec7_rule` 항목이 들고 있다. 전이로
        #    보면 `cross_rules` 도 아직 안 이어졌다.
        # ══════════════════════════════════════════════════════════════
        # 🔴 **2026-10-02 배선** (사용자 지시 *"배선해라"*) — 다섯이 빠졌다
        # ══════════════════════════════════════════════════════════════
        #
        #  `app/analyze.py` 가 *질문 한 줄 → 카드 한 장* 을 잇는다:
        #    classify_facts → hypotheses → scenarios → survive → triggers → render
        #  그리고 `app/bot/main.py` 의 `/analyze` 가 그것을 부른다.
        #
        #    app.classify.classify_facts   app.classify.hypotheses
        #    app.triggers.run              app.triggers.render
        #    app.rules.unimplemented_types (카드 블록 1 — 세포 없는 유형을 이름으로)
        #
        #  🔴 되감기 계약이 **그 자리에서** "빼라"고 말했다 — 다섯 전부 한 번에.
        # ⚠️ `app.rules.by_sec7_rule` 도 **빠졌다** — `survive._r6_missing` 가 §7
        #    번호로 §5-c 규칙을 찾아 핸디 기준선을 읽는다(`1.5`·`2` 를 코드에서 뺐다).
        #    🔴 그러면 `cross_rules` 의 전이 미배선도 함께 풀린다.
        # ⚠️ `app.rules.all_one_direction` 은 여기 없다 — `types.Scenarios` 검증기가
        #    부른다(리뷰 M8 을 고치며 이어졌다). 🔴 **되감기 계약이 그 자리에서
        #    "빼라"고 말했다** — 목록이 거짓이 되기 전에 기계가 먼저 알렸다.
        # ⚠️ `app.survive.run` 은 **빠졌다** — 2026-10-02 에 이어졌다.
        #    `app/triggers.py` 가 반사실 재계산으로 §6 을 다시 돌린다(사용자 지시 ⑫).
        # ⚠️ `app.scenarios.generate` 도 **빠졌다** — 같은 이유다. 방아쇠의 상한은
        #    *"변수를 빼고 §5·§6 을 다시 돌린 값"* 이라 둘을 모두 부른다.
        #    🔴 되감기 계약이 그 자리에서 "빼라"고 말했다 — 목록이 거짓이 되기 전에.
        # ── 팀 별칭 2건. **단계 1 이전부터** 안 이어져 있었다(기존 빚, 리뷰 M4).
        #    🔴 같은 묶음의 [infra] 4건(로그 키 가리기·값 가리기·기동 줄·가동시간)은
        #       **단계 3 에서 이었다** — 사용자 결정 2026-09-30:
        #       `docs/fable/questions/2026-09-30_stage3_not_wired_scope.md`
        #       ("단계 3 것 + 안전장치 4건"). 라이브 검색을 처음 돌리는 단계에서
        #       로그 필터가 안 걸려 있으면 그때 키가 샌다.
        # ── 🔴 **2026-10-01 에 비로소 보였다.** 이름으로 세던 계약이 다른 모듈의
        #    `run(` 에 가려 이것을 고아로 잡지 못했다(`_credits` 주석의 표).
        # ⚠️ `app.extract.run` 은 **빠졌다** — 2026-10-02 에 이어졌다.
        #    §17-b L1~L3 은 *"규칙 파서가 못 읽는 형식의 대체"*(§19-b-5)이고 그 자리가
        #    `Cell._open_hits` 의 *"열었는데 사실 0건"* 줄이다.
        #    🔴 미뤄 둔 조건(*"측정 전에 붙이는 것은 추측이다"*)이 채워졌다 —
        #       실측 2026-10-02(여자 아시안게임): 변수 4개가 전부 산문에 있었는데
        #       가져온 것은 0건이었다.
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **v5 §2 Solar 통로** (2026-10-04) — 이어질 자리는 **§3 에이전트**다
        # ══════════════════════════════════════════════════════════════
        #
        #  사용자 지시 2026-10-04: *"solar api 키 … **한도 정하고** 테스트 해라."*
        #  🔴 그래서 **지금 만든 것은 통로와 예산 가드**다. 그것을 부르는 것은
        #     v5 §3 의 **에이전트 루프**이고, 적용 순서가
        #     §8 → §2 → §3·§4 → §5 → §6 → §7 → §9 → §10 이므로 §3 이 다음이다.
        #
        #  ⚠️ **그래서 지금은 고아다** — 그 사실을 여기 이름으로 적어 둔다.
        #     🔴 §3 에서 `app/agent.py` 가 `solar.chat` 을 부르면 되감기 계약이
        #        *"목록에서 빼라"* 고 빨개진다. 그때 이 두 줄을 지운다.
        #  🔴 **가드는 이미 산다** — `tests/contracts/test_v5_solar_budget.py`
        #     17개가 돌연변이 12개로 확인됐다(§9-5). 안 이어진 것은 **호출**뿐이고
        #     한도 자체는 비어 있지 않다.
        # ══════════════════════════════════════════════════════════════
        # 🔴 **v5 §8-2 엔티티** (2026-10-04) — 이어질 자리는 **§3 에이전트**다
        # ══════════════════════════════════════════════════════════════
        #
        #  §8-2: *"감독 이름은 공식 명단에서 채우고, 비어 있으면 **에이전트가 첫
        #  검색에서 채워** `learned_from:<경기ID>` 로 적는다."*
        #  🔴 그 *"에이전트"* 가 §3 이다 — 지금은 없다.
        #  ⚠️ `profile` 은 **이어졌다**(`analyze.gather` 가 카드에 못 채운 칸을
        #     이름으로 적는다) — 그래서 여기 없다.
        "app.entities.learn_coach",   # → §3 에이전트가 첫 검색에서 부른다
        "app.entities.field_of",      # → §3 AgentInput 이 칸을 꺼낸다
        # ══════════════════════════════════════════════════════════════
        # 🔴 **v5 §3·§5** (2026-10-04) — 이어질 자리는 **게이트 2** 다
        # ══════════════════════════════════════════════════════════════
        #
        #  §10-4 게이트 2: *"§2~§4 에이전트+도구 → 정답지 5경기에서 깔때기
        #  `verified_vars` ≥ 6"*. 🔴 그때 `agentloop.run` 이 실제 검색·열기
        #  통로에 꽂히고 아래 넷이 함께 이어진다.
        #
        #  ⚠️ `_agent_note` 는 **이어졌다** — 카드가 *"도구 미배선"* 을 적는다.
        #     🔴 그 줄이 없으면 에이전트가 안 도는 것을 아무도 모른다(#3).
        # ⚠️ `app.trigcond.rerun_ok` 는 **빠졌다** — 2026-10-04 에 이어졌다.
        #    §7-1 T-60 재실행(`rerun.check_scenarios` → `scheduler.rerun_once`)이
        #    그 호출자다. 🔴 되감기 계약이 **그 자리에서** "빼라"고 말했다 —
        #    목록이 거짓이 되기 전에 기계가 먼저 알렸다.
        # ══════════════════════════════════════════════════════════════
        # 🔴 **§7-3 라이브 재판정** — 규칙은 다 있고 **입구가 없다**
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 라이브는 **스코어·경과 분·지표 캡처**를 받아야 돈다(§7-3). 보드
        #     캡처를 받는 통로도 라이브 피드 어댑터도 **아직 없다**.
        #  🔴 그래서 규칙만 먼저 짰다(계약이 전부 물린다). 이을 자리는 **그 입구를
        #     만드는 단계**다 — 그때 `analyze` 가 이 다섯을 부른다.
        #  ⚠️ `live.may_judge` 는 여기 없다 — `live.cap_verdict` 등이 그것을
        #     부르지 않으므로 각각 따로 적는다.
        "app.live.may_judge",               # → 라이브 입구(§7-3)
        "app.live.effect_of",               # → 같다
        "app.live.metrics_ok",              # → 같다
        "app.live.reads_as_no_shots",       # → 같다
        "app.live.keep_markets",            # → 같다
        "app.live.cap_verdict",             # → 같다
        # ⚠️ 셋이 **빠졌다** — 2026-10-04 에 이어졌다(**게이트 2** · 사용자 지시
        #    *"게이트2 켜라 에이전트 돌려봐라"*):
        #      `agentloop.run`        → `analyze._run_agent` 가 `to_thread` 로
        #      `agentloop.tool_specs` → `run` 의 도구 루프가 턴마다 넘긴다
        #      `verifylayer.hardness_for` → `classify.from_agent_var`(§5-5 무게)
        #    🔴 되감기 계약이 **그 자리에서** "빼라"고 말했다.
        # ══════════════════════════════════════════════════════════════
        # 🔴 **v5-A DeepSeek** — 클라이언트는 섰고 **부르는 단계가 아직 없다**
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 작업지시 §4 가 순서를 못 박았다: 클라이언트(§4-2) → 단계 3
        #     (`app/hypo.py` · §4-3) → 단계 4(`app/redteam.py` · §4-4).
        #  🔴 그 둘이 서면 `NOT_WIRED` 에서 빠진다(되감기 계약이 말해 준다).
        # ⚠️ `app.deepseek.ask` 는 **빠졌다** — §4-3 `hypo.run` 이 부른다.
        #    🔴 되감기 계약이 그 자리에서 말했다.
        # ⚠️ `to_payload`·`known_names`·`deepseek_cost` 는 **여기 없다** —
        #    그 셋은 이미 다른 함수가 부른다(되감기 계약이 말했다).
        # ⚠️ `hypo.run`·`redteam.*` 다섯은 **빠졌다** — 2026-10-04 에
        #    이어졌다(§4-7 판정 순서 · `app/judgeorder.py` → `analyze`).
        #    🔴 되감기 계약이 **그 자리에서** "빼라"고 말했다.
        "app.deepseek.now_utc",             # → 같다(시각 주입 자리)
        "app.agentloop.stop_note",          # → §3-7 중단 때
        "app.verifylayer.independent_sources",  # → §5-7 독립 출처 세기
        # ✅ `app.solar.chat` 은 **빠졌다** — 2026-10-04 에 `agentloop.run` 이
        #    이었다. 🔴 되감기 계약이 그 자리에서 *"목록에서 빼라"* 고 말했다 —
        #    목록이 거짓이 되기 전에 기계가 먼저 알렸다.
        "app.solar.env_key_present",  # → §10 측정 스크립트가 키 유무로 건너뛴다
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **`window.set_clock` 은 운영이 부르면 안 된다** (2026-10-04)
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 창이 *"지금부터 36시간"* 이므로 기록해 둔 고정물(지난 날짜)은 전부
        #     창 밖이다 — **시계를 고정하지 않으면 창을 시험할 수가 없다**
        #     (실측 2026-10-04: 고정물 58건이 창 밖으로 떨어졌다).
        #  🔴 그래서 이 함수는 **시험만** 부른다. 운영이 시계를 바꾸면 그 순간
        #     모든 날짜 판단이 거짓이 된다 — 아래 계약이 그것을 막는다
        #     (`test_w36_운영은_시계를_고정하지_않는다`).
        "app.window.set_clock",             # → 시험만 (운영 호출은 계약 위반)
        # ══════════════════════════════════════════════════════════════
        # 🔴 **오픈월드 ⑥-2·⑥-3·⑥-4** — 지시서 §3 에서 잇는다 (2026-10-05)
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ ⑥-1(`read_names`)·⑥ 문(`may_run`)은 **이었다**(`resolve.
        #     _by_openworld`). 🔴 ⑥-2 후보 검색과 ⑥-3 경기 페이지 확인은
        #     **지시서 §3** 이 *"기존 fotmob/ESPN 파서를 재사용한다 — 새 파서를
        #     짓지 않는다"* 고 했으므로 그 단계에서 잇는다.
        #  🔴 이으면 되감기 계약이 *"목록에서 빼라"* 고 빨개진다.
    }
    # 🔴 **목록이 원본에서 자란다** — 손으로 적은 14개 목록은 `app/search.py`·
    #    `config.py`·`db.py`·`bot/**`·`scheduler.py` 를 **검사에서 통째로
    #    빠뜨렸다**(리뷰 M4). 이 저장소가 "손으로 유지하는 목록은 언제나 한 발
    #    늦는다"고 적어 둔 바로 그 병이다.
    mods = {}
    for path in sorted((ROOT / "app").rglob("*.py")):
        parts = list(path.relative_to(ROOT).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        name = ".".join(parts)
        if name.endswith("__main__"):
            continue  # 진입점 — 부르는 곳은 `python -m` 이다
        mods[name] = importlib.import_module(name)
    # 🔴 **`app/` 안에서만 센다.** 테스트가 부르는 것은 배선이 아니다 —
    #    그것을 배선으로 세면 "테스트만 있는 함수"가 이어진 것처럼 보인다.
    #    세는 방법은 `_credits` 가 들고 있다(이름이 아니라 **귀속**으로 센다).
    used = _credits(mods)

    orphans = []
    for name, mod in mods.items():
        for fn, obj in inspect.getmembers(mod, inspect.isfunction):
            if fn.startswith("_") or obj.__module__ != name:
                continue
            key = f"{name}.{fn}"
            if used.get(key, 0) == 0 and key not in NOT_WIRED:
                orphans.append(key)
    assert orphans == [], f"부르는 곳이 없다: {orphans}"
    # 🔴 반대 위험 — 이어 놓고 목록에 남겨 두면 목록이 거짓이 된다
    stale = [k for k in NOT_WIRED if used.get(k, 0) > 0]
    assert stale == [], f"이어졌으니 NOT_WIRED 에서 빼라: {stale}"
    # 🔴 세 번째 위험 — 지운 함수 이름이 목록에 남으면 목록이 거짓이 된다.
    #    위의 두 계약은 "이어졌나"만 보고 "아직 있나"는 안 봤다(리뷰 A4).
    ghosts = []
    for k in NOT_WIRED:
        mod_name, fn = k.rsplit(".", 1)
        obj = getattr(mods.get(mod_name), fn, None)
        # 고아 검사와 **같은 기준**이다 — 그 모듈에서 정의된 함수만 센다
        if not inspect.isfunction(obj) or obj.__module__ != mod_name:
            ghosts.append(k)
    assert ghosts == [], f"없는 함수가 NOT_WIRED 에 남았다: {ghosts}"


def test_스키마_표를_코드가_전부_쓴다():
    """★ 표를 만들고 아무도 안 읽으면 그 칸은 영영 안 찬다.

    ⚠️ 아직 수집기가 없어 못 채우는 표는 **여기 이름을 적어** 남긴다 —
       조용히 두면 "있는 줄" 알고 아무도 다시 안 본다.
    """
    sql = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
    tables = {ln.split("CREATE TABLE IF NOT EXISTS ")[1].split()[0]
              for ln in sql.splitlines()
              if ln.startswith("CREATE TABLE IF NOT EXISTS ")}
    # 🔴 **표 이름이 코드에 있는 것과 코드가 그 표를 읽는 것은 다르다.**
    #    실측 2026-09-30: 단계 2 가 10표를 세운 뒤 이 계약이 8개를 "읽는다"고
    #    통과시켰다. 전부 거짓이었다 —
    #      · `variables`·`scenarios`·`survival` → `app/run.py` **독스트링** (D46)
    #      · `board` → `class Blackboard` 의 부분문자열
    #      · `premise_check` → `blackboard.USED_IN` 튜플의 값
    #      · `sufficiency`·`ledger`·`background` → `app/types.py` 독스트링
    #    → 독스트링을 걷고 **SQL 문맥**(FROM/INTO/UPDATE/JOIN/TABLE 뒤)에서만 센다.
    code = "\n".join(strip_docs(p.read_text(encoding="utf-8"))
                     for p in (ROOT / "app").rglob("*.py"))

    def _reads(table: str) -> bool:
        return re.search(rf"(?:FROM|INTO|UPDATE|JOIN|TABLE)\s+{re.escape(table)}\b",
                         code, re.I) is not None

    # 🔴 아직 배선되지 않은 표 — 단계가 오면 이 목록에서 빼고 계약을 고친다
    # 🔴 **표마다 "몇 단계에서 이어지나"를 적는다.** 단계 2 는 10표에 한 줄로
    #    *"배선은 단계 3 이다(§9)"* 라고 달았는데 **틀렸다** — §9 는 STEP 1~3 을
    #    단계 5, STEP 4·5 를 단계 6, STEP 6 을 단계 7, STEP 8 을 단계 8 에
    #    배정한다. 한 줄 주석이 열 표를 뭉갠 것이다(사용자 결정 2026-09-30:
    #    `docs/fable/questions/2026-09-30_stage3_not_wired_scope.md`).
    # ══════════════════════════════════════════════════════════════
    # 🔴🔴 **2026-10-02 — 이 목록도 비었다** (사용자 지시)
    # ══════════════════════════════════════════════════════════════
    #
    # > 사유만 남기고 나중에 하지 않으면 안 하는 이보다 못하다
    #
    #   team_form      → `analyze.persist` 가 `:form` 사실을 표에 적는다
    #                    ⚠️ `midweek` 는 **못 세서 `None`** 이다 — 0 으로 때우지 않는다
    #   premise_check  → `analyze.persist` 가 전제 변수(§4 `is_premise`)를 적는다
    #                    🔴 `kept` 만 적힌다 — `replaced` 는 **반대 검색**이 있어야
    #                       쓸 수 있고 그것은 아직 없다. 그 사실을 코드 주석에 남겼다.
    NOT_WIRED: set[str] = set()
    # ⚠️ `ledger` 는 **빠졌다** — 2026-10-02 에 이어졌다.
    #    `analyze.score_finished()` 가 끝난 경기를 **실제 결과로** 채점해 쌓는다.
    #    🔴 사용자 지시: *"정답지는 없다 … 데이타가 쌓이고 그걸로 분석을 하고"*.
    #       정답지를 지웠으니 기준은 **경기 결과** 하나다.
    # ══════════════════════════════════════════════════════════════
    # 🔴 **2026-10-02 배선** (사용자 지시 *"배선해라"*) — 여섯이 빠졌다
    # ══════════════════════════════════════════════════════════════
    #
    #   variables · background · sufficiency · scenarios · board · survival
    #
    #  `app/analyze.persist()` 가 §3 산출을 그 여섯 표에 적는다(멱등).
    #  🔴 그 과정에서 **표가 코드와 어긋난 것을 찾았다**:
    #     ① 칸 이름 — 코드가 `var_type`·`claim`, 표는 `type`·`text`
    #     ② `variables.published_at` 이 **NOT NULL** 이었다 — 사용자 결정 2026-10-02
    #        안 A(날짜 없는 변수 허용)가 `app/types.py` 에만 반영돼 있었다.
    #        즉 순위표에서 나온 `stakes`·`home_field` 는 **적재에서 터진다.**
    #        적재하는 코드가 없어서 아무도 몰랐다 — 배선이 그것을 드러냈다.
    #  → `db/schema.sql` #7 마이그레이션이 `types.py` 와 **같은 조건 둘**을 건다.
    # 🔴 단계 3 에서 이은 것: `source_state`(죽은 호스트+사유) · `source_score`
    #    (§19-e 점수표) · `extraction_rejected`(§17-g-4 LLM 거부 기록).
    # 🔴 목록이 **없는 표**를 들고 있으면 거짓이다 — `ledger` 가 그랬다(리뷰 A4).
    #    v4 단계 2 가 그 표를 세우면 그때 다시 여기 적는다.
    ghosts = sorted(NOT_WIRED - tables)
    assert ghosts == [], f"스키마에 없는 표가 NOT_WIRED 에 남았다: {ghosts}"
    missing = sorted(t for t in tables
                     if not _reads(t) and t not in NOT_WIRED)
    assert missing == [], f"코드가 안 읽는 표: {missing}"
    # 🔴 반대 위험 — 이어 놓고 목록에 남기면 목록이 거짓이 된다
    stale = sorted(t for t in NOT_WIRED if _reads(t))
    assert stale == [], f"이제 읽으니 NOT_WIRED 에서 빼라: {stale}"


# ══════════════════════════════════════════════════════════════════
# §19 수집기 배선
# ══════════════════════════════════════════════════════════════════

def test_스케줄러가_수집을_부른다():
    """★ 수집기를 만들고 안 부르면 DB 가 비고, 판정이 전부 미확인이 된다."""
    src = inspect.getsource(S)
    assert "collect(" in src
    assert "COLLECT_INTERVAL_SEC" in src


def test_수집_상태가_하루를_산다():
    """🔴 §19-e — 점수표가 매 주기 초기화되면 소스 순서를 영영 못 고친다."""
    src = inspect.getsource(S)
    assert "_SCORES = SourceScores()" in src
    assert "scores=_SCORES" in src


def test_어댑터가_표로_갈린다():
    """🔴 분기 말고 표다 — 리그가 늘면 행이 는다(§모든 종목).

    ⚠️ 종전 이 계약은 `== {"MLB", "NPB"}` 를 **손으로** 들고 있었다. 리그를 하나
       늘리자 정상 동작인데 빨개졌다 — 이 저장소가 *"손으로 유지하는 목록은 언제나
       한 발 늦는다"* 고 적어 둔 바로 그 병이다(2026-09-30, K리그 추가 때).
       🔴 그래서 **목록을 세지 않고 규약을 검사한다**: 표에 든 어댑터는 전부 같은
       문(`sources_slate`)을 가져야 하고, 흐름에 리그 이름 분기가 없어야 한다.
    """
    from app.collect import ingest
    assert ingest.ADAPTERS, "어댑터 표가 비었다"
    # ① 표에 든 것은 전부 같은 규약이다 — 규약이 갈리면 호출부에 분기가 생긴다
    broken = [lg for lg, mod in ingest.ADAPTERS.items()
              if not callable(getattr(mod, "sources_slate", None))]
    assert broken == [], f"`sources_slate` 가 없는 어댑터: {broken}"
    # ② 🔴 리그 이름으로 분기하지 않는다. **표에 있는 이름 전부**를 검사한다 —
    #    두 개만 적어 두면 세 번째 리그의 분기를 놓친다.
    src = strip_docs(inspect.getsource(ingest.collect))
    for league in ingest.ADAPTERS:
        assert f'league == "{league}"' not in src, f"{league} 분기가 있다"
        assert f"league == '{league}'" not in src, f"{league} 분기가 있다"


def test_어댑터_없는_리그는_사유가_남는다():
    """🔴 조용한 0 금지 — KBO·K리그는 아직 소스가 없다."""
    from app.collect import ingest
    src = inspect.getsource(ingest.collect)
    assert "어댑터 없음" in src


def test_수집이_players와_alias를_잇는다():
    """1b — 예고 선발이 들어오면 그 자리에서 id 가 발급되고 alias 가 붙는다."""
    from app.collect import ingest
    src = inspect.getsource(ingest._starters)
    for fn in ("resolve_by_alias", "upsert_player", "link_alias"):
        assert fn in src, fn


def test_예고_선발이_없으면_행을_만들지_않는다():
    """🔴 빈 행은 "모른다"를 숨긴다."""
    from app.collect import ingest
    src = inspect.getsource(ingest._starters)
    assert 'not pp.get("name")' in src and "continue" in src


def test_수집이_evidence에_쌓는다():
    """§12-e — 증거 카드. NOT_WIRED 에서 `evidence` 쓰기가 빠졌다."""
    from app.collect import ingest
    assert "bb.flush" in inspect.getsource(ingest.collect)


def test_수집이_판정하지_않는다():
    """🔴 §19-f — lean·확신·등급은 judge.py 다. **수집기는 사실만 낸다.**

    ⚠️ 종전 이 계약은 문자열로 `"confidence ="` 를 찾았고, 그래서 SQL 의
       `SET confidence = EXCLUDED.confidence` 에 **거짓 실패**했다(실측
       2026-09-30). 그 줄은 등급을 *계산*하는 것이 아니라 이미 있는 `hardness`
       를 **옮겨 적는** 것이다. 이 저장소가 다섯 번 만든 병이라 적어 둔다
       (`docs/fable/stages/NEXT.md` §2-1).

    🔴 **처방: 구조로 본다.** `ast` 로 (a) 부르는 함수 이름과 (b) 대입 대상
       이름만 본다 — 문자열 안의 SQL·독스트링은 애초에 후보가 아니다.
    """
    from app import queries, searchcells
    from app.collect import ingest

    #: 🔴 **검사 범위가 원본에서 자란다**(리뷰 2026-09-30). 종전에는
    #   `(ingest, kleague, mlb, npb)` 를 손으로 적어 놨고, 단계 3 이 만든
    #   **`searchcells`(사실을 만드는 새 모듈)·`queries`** 가 빠져 있었다.
    #   → 리그 어댑터는 `ADAPTERS` 표에서 가져온다. 리그가 늘면 따라온다.
    mods = (ingest, searchcells, queries, *dict.fromkeys(
        ingest.ADAPTERS.values()))

    #: 🔴 **부르면 안 되는 것**(v4 §8 폐기 + 판정 함수)
    BANNED_CALLS = {"build_lean", "apply_counters", "decide", "grade",
                    "regrade", "evaluate_triggers"}
    #: 🔴 **수집기가 값을 지어내선 안 되는 칸**(§19-f · §17-c)
    BANNED_TARGETS = {"confidence", "verdict", "survival", "weight",
                      "strength", "direction"}
    for mod in mods:
        tree = ast.parse(inspect.getsource(mod))
        called = {n.func.id if isinstance(n.func, ast.Name)
                  else getattr(n.func, "attr", "")
                  for n in ast.walk(tree) if isinstance(n, ast.Call)}
        assert not (called & BANNED_CALLS), \
            f"{mod.__name__} 가 판정 함수를 부른다: {called & BANNED_CALLS}"
        targets = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Assign):
                for t in n.targets:
                    targets.add(t.id if isinstance(t, ast.Name)
                                else getattr(t, "attr", ""))
            elif isinstance(n, (ast.AnnAssign, ast.AugAssign)):
                targets.add(n.target.id if isinstance(n.target, ast.Name)
                            else getattr(n.target, "attr", ""))
            elif isinstance(n, ast.keyword) and n.arg in BANNED_TARGETS:
                # `Fact(hardness=...)` 는 사실의 층이라 괜찮지만, 아래 칸에
                # **수집기가 값을 넣는 것**은 §17-c 위반이다
                if not isinstance(n.value, (ast.Attribute, ast.Name)):
                    targets.add(n.arg)
        assert not (targets & BANNED_TARGETS), \
            f"{mod.__name__} 가 판정 칸에 값을 넣는다: {targets & BANNED_TARGETS}"


def test_env_example_이_코드와_맞는다():
    """🔴 사본 금지 — `.env.example` 이 **지워진 코드의 키**를 가리키면
    다음 세션이 없는 것을 설정한다.

    실측 2026-09-27: Anthropic·PPLX·XAI·ODDS·APIFOOTBALL 키와 모델 이름 8개가
    남아 있었고 그 코드는 전부 지워진 상태였다.
    """
    import re
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    declared = set(re.findall(r"^([A-Z_0-9]+)=", env, re.M))
    code = "\n".join(p.read_text(encoding="utf-8")
                     for p in (ROOT / "app").rglob("*.py"))
    read = set(re.findall(r'os\.getenv\(\s*"([A-Z_0-9]+)"', code))
    read |= set(re.findall(r'os\.environ\[\s*"([A-Z_0-9]+)"', code))
    # 🔴 `os.getenv(CONST)` 처럼 **상수를 거쳐** 읽는 것도 읽는 것이다.
    #    이름을 문자열로만 찾으면 그 경로를 놓치고, 계약이 거짓으로 빨개진다
    #    (실측 2026-09-28: `CSE_OPERATIONAL` 이 그렇게 빠졌다).
    import ast
    for path in (ROOT / "app").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        consts = {t.id: n.value.value
                  for n in tree.body if isinstance(n, ast.Assign)
                  for t in n.targets
                  if isinstance(t, ast.Name) and isinstance(n.value, ast.Constant)
                  and isinstance(n.value.value, str)}
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and n.args and isinstance(n.args[0], ast.Name):
                got = consts.get(n.args[0].id)
                if got and got.isupper():
                    read.add(got)
    # 배포 플랫폼이 주입하는 것은 우리가 안 적는다 — 주석으로만 남는다
    platform = {"RAILWAY_GIT_COMMIT_SHA", "RAILWAY_GIT_COMMIT_MESSAGE",
                "GIT_COMMIT_SHA", "SOURCE_COMMIT"}
    assert declared - read == set(), f"코드가 안 읽는 키: {declared - read}"
    assert (read - platform) - declared == set(), \
        f"코드가 읽는데 문서에 없는 키: {(read - platform) - declared}"


def test_env_키가_example_의_부분집합이다():
    """🔴 **C9** (사용자 결정 2026-09-29 · v4 §8 추가 판정).

    > "유료 키 전부 `.env.legacy`(gitignore)로 이동, `.env` 는 .env.example
    >  키만. 계약 확장: `.env` 키 집합 ⊆ `.env.example` 키 집합."

    ⚠️ 종전 계약은 `.env.example` ↔ 코드만 대조하고 **`.env` 자체는 검사하지
       않았다**(상태 덤프 `10_open_issues` #2). 그 사이 `.env` 에 유료 키 23개가
       남아 있었다. [infra]
    """
    import re as _re

    def keys(name):
        f = ROOT / name
        return set(_re.findall(r"^([A-Z_0-9]+)=",
                               f.read_text(encoding="utf-8"), _re.M)) \
            if f.is_file() else set()

    env, example = keys(".env"), keys(".env.example")
    assert env, ".env 가 비었다"
    assert env <= example, f".env 에만 있는 키: {sorted(env - example)}"
    # 🔴 반대 방향 — 예시에 있는데 `.env` 가 비어 있으면 그 설정은 기본값으로 돈다
    assert example - env == set(), f"값이 안 채워진 키: {sorted(example - env)}"


def test_유료_키가_env에_없고_legacy에_있다():
    """🔴 옮긴 것이 **사라지지 않았는지**도 본다 — 지우는 것은 사용자 몫이다. [infra]"""
    import re as _re
    env = (ROOT / ".env").read_text(encoding="utf-8")
    lg = ROOT / ".env.legacy"
    for bad in ("ANTHROPIC_API_KEY", "PPLX_API_KEY", "XAI_API_KEY",
                "ODDS_API_KEY", "APIFOOTBALL_KEY", "GROQ_API_KEY",
                "OPENROUTER_API_KEY", "NVIDIA_API_KEY"):
        assert not _re.search(rf"^{bad}=", env, _re.M), f".env 에 {bad}"
    assert lg.is_file(), ".env.legacy 가 없다 — 옮긴 것이 사라졌다"


def test_legacy_env가_gitignore다():
    """🔴 유료 키가 커밋되면 옮긴 뜻이 없다. [infra]"""
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env.legacy" in gi


def test_env_example에_유료_키가_없다():
    """🔴 §14-13.

    ⚠️ **선언된 변수만** 본다 — 주석이 실사고를 설명하는 것과 변수가 실재하는
       것은 다르다(D46). 종전엔 "PPLX 키가 남아 있었다"는 설명 문장에 걸렸다.
    """
    import re
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    declared = set(re.findall(r"^([A-Z_0-9]+)=", env, re.M))
    for bad in ("ANTHROPIC", "PPLX", "PERPLEXITY", "XAI", "ODDS",
                "APIFOOTBALL", "OPENROUTER", "GROQ", "NVIDIA", "GEMINI",
                "JUDGE_MODEL", "MODEL_MATCHUP", "NARRATOR_MODEL"):
        hit = [d for d in declared if bad in d]
        assert hit == [], hit


def test_env를_읽는_곳이_있다():
    """🔴 실사고 2026-09-27 — `.env` 를 읽는 코드가 **0곳**이었다.

    `.env.example` 은 그것을 설정하라고 하는데 아무도 읽지 않았다. 파일에
    `GOOGLE_CSE_CX` 를 넣어도 봇은 못 봤다 — 설정이 **조용히 기본값**으로 돌았다.
    """
    from app import config as Cfg
    assert callable(Cfg.load_env)
    # 🔴 패키지 진입점에서 불려야 한다 — `app.config` 안에만 두면 그 모듈을
    #    import 하지 않는 경로가 조용히 기본값으로 돈다.
    init = (ROOT / "app" / "__init__.py").read_text(encoding="utf-8")
    assert "load_env" in init and "_load_env()" in init


def test_env가_기존_환경변수를_덮지_않는다(tmp_path, monkeypatch):
    """⚠️ 컨테이너·`railway run` 이 주입한 값이 파일보다 세다 — 그쪽이 운영이다."""
    from app import config as Cfg
    f = tmp_path / ".env"
    f.write_text("AB_TEST_ONE=from_file\nAB_TEST_TWO=from_file\n")
    monkeypatch.setenv("AB_TEST_ONE", "from_env")
    monkeypatch.delenv("AB_TEST_TWO", raising=False)
    n = Cfg.load_env(f)
    assert os.environ["AB_TEST_ONE"] == "from_env", "환경변수를 덮었다"
    assert os.environ["AB_TEST_TWO"] == "from_file"
    assert n == 1, n


def test_env가_없어도_크래시하지_않는다(tmp_path):
    from app import config as Cfg
    assert Cfg.load_env(tmp_path / "없는파일") == 0


def test_의존이_코드와_맞는다():
    """🔴 사본 금지 — 지워진 코드의 의존을 남기면 무엇이 살아 있는지 알 수 없다.

    실측 2026-09-27: `anthropic`·`pybaseball`·`soccerdata`·`scikit-learn`·
    `socksio` 가 남아 있었고 그 코드는 전부 지워진 상태였다.
    ⚠️ `socksio` 는 **SOCKS 프록시 전송**이다 — §14-12 가 막는 것을 설치만
       해 두고 있었다.
    """
    import ast
    import re
    import sys
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **선언 목록은 파서로 읽는다** — 글자로 자르면 주석에 속는다
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 종전엔 `dependencies = [` 부터 **첫 `]`** 까지를 잘라 따옴표 안을
    #     셌다. 실측 2026-10-03: 주석에 적은 `territories['HR']` 의 대괄호가
    #     목록을 **중간에서 끊어** `babel`·`trafilatura` 가 선언에서 **사라졌고**,
    #     그 둘이 *"import 하는데 선언 없음"* 으로 빨개졌다 — 선언은 있었다.
    #  🔴 계약이 **거짓 실패**를 내면 사람이 계약을 믿지 않게 된다. 그것이 계약을
    #     지우는 첫걸음이다. ⚠️ D46 의 같은 뿌리 — **글자가 아니라 구조를 본다.**
    import tomllib
    toml = (ROOT / "pyproject.toml").read_bytes()
    rows = tomllib.loads(toml.decode("utf-8"))["project"]["dependencies"]
    declared = {re.split(r"[><=~!\[; ]", m)[0].strip().lower() for m in rows}

    tops: set[str] = set()
    for p in list((ROOT / "app").rglob("*.py")):
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Import):
                tops |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
                tops.add(n.module.split(".")[0])
    used = {t for t in tops if t not in sys.stdlib_module_names and t != "app"}
    # 배포판 이름이 import 이름과 다른 것
    alias = {"dotenv": "python-dotenv", "yaml": "pyyaml"}
    used = {alias.get(t, t) for t in used}
    # 진입점으로만 쓰는 것(코드가 import 하지 않는다)
    runners = {"uvicorn"}
    assert used - declared == set(), f"import 하는데 선언 없음: {used - declared}"
    assert declared - used - runners == set(), \
        f"선언했는데 import 0곳: {declared - used - runners}"


def test_프록시_의존이_없다():
    """🔴 §14-12 — 우회 설계 금지. 설치만 해 두는 것도 금지다.

    ⚠️ **선언된 의존만** 본다 — 주석이 "그것을 지웠다"고 설명하는 것과 의존이
       실재하는 것은 다르다. D46 이 이 파일에서 세 번째다.
    """
    import re
    toml = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    block = toml[toml.index("dependencies = ["):]
    declared = {m.lower() for m in re.findall(r'"([^"]+)"', block[:block.index("]")])}
    for bad in ("socksio", "pysocks", "socks", "stem", "torpy"):
        hit = [d for d in declared if bad in d]
        assert hit == [], hit


# ══════════════════════════════════════════════════════════════════
# 비용 잠금 · Gemini 0건 (사용자 지시 2026-09-28)
# ══════════════════════════════════════════════════════════════════

def test_gemini가_전수_0건이다():
    """🔴 사용자 지시 2026-09-28 — *"같은 프로젝트에 있는 Gemini API 키는 이 봇이
    읽지도 호출하지도 않는다."*

    CSE 와 같은 Google 프로젝트에 Gemini 키가 있다. 코드가 그 이름을 **읽지
    않으면** 호출이 0건이다(§14-13 과 같은 논리).
    ⚠️ 독스트링이 "Gemini 는 쓰지 않는다"고 **설명하는** 것은 허용한다 — 코드가
       그것을 **부르는** 것과 다르다(D46). 그래서 코드만 본다.
    """
    import ast
    import re

    # ① `.env`·`.env.example` 에 변수 이름이 없다
    for name in (".env", ".env.example"):
        f = ROOT / name
        if not f.is_file():
            continue
        declared = set(re.findall(r"^([A-Z_0-9]+)=", f.read_text(encoding="utf-8"),
                                  re.M))
        hit = [d for d in declared if "GEMINI" in d or "GOOGLE_AI" in d]
        assert hit == [], (name, hit)

    # ② 코드(독스트링·주석 제외)에 이름이 없다
    for path in (ROOT / "app").rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        lines = src.splitlines()
        kill: set[int] = set()
        for n in ast.walk(ast.parse(src)):
            if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) \
                    and isinstance(n.value.value, str):
                kill.update(range(n.lineno - 1, (n.end_lineno or n.lineno)))
        code = re.sub(r"#.*", "",
                      "\n".join("" if i in kill else ln
                                for i, ln in enumerate(lines))).lower()
        for bad in ("gemini", "generativelanguage", "google_ai"):
            assert bad not in code, (path.name, bad)


def test_CSE가_운영_스케줄러에_기본으로_안_붙는다():
    """🔴 **비용 잠금**(사용자 지시 2026-09-28) — *"결제 계정 미연결 또는 할당량
    100/일 고정을 확인했다는 답을 받기 전엔 CSE를 운영 스케줄러에 연결하지
    않는다."*

    기본이 꺼짐이고, 켜는 것은 사용자 몫이다(`CSE_OPERATIONAL`).
    """
    from app import search as Sr
    assert Sr.cse_operational() is False or os.getenv("CSE_OPERATIONAL")
    chain = Sr.build_chain(operational=False)
    assert chain.google is None, "잠금이 꺼졌는데 CSE 가 붙었다"
    assert chain.searx is not None, "1순위까지 같이 죽었다"


def test_스케줄러가_잠금을_건너뛰지_않는다():
    """🔴 `operational=True` 는 **실측·게이트 전용**이다."""
    src = inspect.getsource(S)
    assert "build_chain()" in src
    assert "operational=True" not in src, "스케줄러가 비용 잠금을 건너뛴다"


def test_할당량은_태평양_시간으로_센다():
    """🔴 구글 할당량은 **PT 자정**에 돌아온다 — KST 로 세면 하루가 어긋나고,
    그 어긋남이 상한 초과(=요금)로 나타난다.

    실측 2026-09-28 09시 KST: PT 는 아직 09-27 이다.
    """
    from datetime import datetime, timezone
    from app import search as Sr
    assert str(Sr.QUOTA_TZ) == "America/Los_Angeles"
    # KST 2026-09-28 09:00 = PT 2026-09-27 17:00
    t = datetime(2026, 9, 28, 0, 0, tzinfo=timezone.utc)
    assert Sr.quota_day(t).isoformat() == "2026-09-27"


# ══════════════════════════════════════════════════════════════════
# #1 운영 DB 분리 (사용자 결정 2026-09-29)
# ══════════════════════════════════════════════════════════════════

LEGACY_DB = "analystbot_legacy_v14"


def test_legacy_DB_이름을_코드가_참조하지_않는다():
    """🔴 사용자 결정 — *"`analystbot` → `analystbot_legacy_v14` 로 이름을 바꾸고,
    `analystbot` 을 db/schema.sql 로 새로 만든다. odds_snapshots·decision_ledger
    는 legacy 안에 그대로(= research 격리). 계약: app/** 에서 legacy DB 이름
    참조 0건."*

    legacy 에는 v1.4 표 24개가 있고 `odds_snapshots` 18,015행이 그대로다.
    코드가 그 이름을 **읽지 않으면** 격리가 성립한다.
    [infra]
    """
    for path in (ROOT / "app").rglob("*.py"):
        assert LEGACY_DB not in strip_docs(path.read_text(encoding="utf-8")), path


def test_legacy_DB_이름이_설정에도_없다():
    """⚠️ `.env`·`.env.example`·compose 에도 없어야 한다 — 설정으로 새면 같다. [infra]"""
    for name in (".env", ".env.example", "docker-compose.yml"):
        f = ROOT / name
        if f.is_file():
            assert LEGACY_DB not in f.read_text(encoding="utf-8"), name


def test_배당_표_이름이_코드에_없다():
    """🔴 v4 §11-9 — 배당은 research 스키마(=legacy)에만. app/** 접근 0건. [infra]"""
    code = "\n".join(strip_docs(p.read_text(encoding="utf-8"))
                     for p in (ROOT / "app").rglob("*.py"))
    for t in ("odds_snapshots", "decision_ledger", "pick_ledger",
              "history_prices", "market_baseline_ledger"):
        assert t not in code, t


def test_DB_기본값이_실재하는_DB를_가리킨다():
    """🔴 실사고 2026-09-29 — 기본값이 **없는 DB**(`analyst`)를 가리켰다.

    compose 가 만드는 것은 `analystbot` 이다. 기본값으로 돌린 적이 없어 아무도
    몰랐다 — 실측은 늘 임시 DB 로 했다. [infra]
    """
    from app.config import Settings
    import re
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    made = re.search(r"POSTGRES_DB:\s*(\w+)", compose).group(1)
    default = Settings().database_url.rsplit("/", 1)[-1]
    assert default == made, f"기본값 {default} ≠ compose {made}"


# ══════════════════════════════════════════════════════════════════
# #5 contract-reviewer — 읽기 전용 (사용자 결정 2026-09-29)
# ══════════════════════════════════════════════════════════════════

REVIEWER = ".claude/agents/contract-reviewer.md"
INBOX = "docs/fable/inbox/2026-09-29_v4.md"  # 🔴 정본 — rev 는 여기 2행에서 읽는다


def test_리뷰어가_읽기_전용이다():
    """🔴 사용자 결정 — *"허용 도구 Read·Grep·Glob만, Bash·Edit·Write 없음."*

    v4 §11-4: *"리뷰 에이전트는 읽기 전용. 절제는 주 세션이 …"*

    🔴 **D69 가 이 계약의 이유다.** 종전 정의가 절제 주입을 *시켰고*, 4차 리뷰어가
       `narrate.py` 에 `raise RuntimeError("ABLATION")` 를 넣은 직후 세션 한도로
       죽어 작업 트리가 깨진 채 남았다(12 failed). 도구를 회수해 **불가능하게**
       만든다 — 규율로 부탁하지 않는다. [infra]
    """
    import re as _re
    f = ROOT / REVIEWER
    assert f.is_file(), f"{REVIEWER} 가 없다"
    fm = f.read_text(encoding="utf-8").split("---")[1]
    tools = {t.strip() for t in
             _re.search(r"^tools:\s*(.+)$", fm, _re.M).group(1).split(",")}
    assert tools == {"Read", "Grep", "Glob"}, tools
    for banned in ("Bash", "Edit", "Write", "NotebookEdit", "Task", "Agent"):
        assert banned not in tools, banned


def test_리뷰어가_절제를_시키지_않는다():
    """🔴 D69 재발 방지 — 주입을 **시키는 문장**이 다시 들어오면 막는다.

    ⚠️ **인용 블록(`>`)은 뺀다.** 그 파일은 D69 실사고를 인용해서 설명한다 —
       사고를 *인용하는* 것과 그것을 *시키는* 것은 다르다. D46 이 이 저장소에서
       **다섯 번째**다(2026-09-29 에도 이 계약이 내 인용문에 걸렸다). [infra]
    """
    lines = (ROOT / REVIEWER).read_text(encoding="utf-8").splitlines()
    text = "\n".join(ln for ln in lines if not ln.lstrip().startswith(">"))
    for bad in ("넣은 뒤 되돌려라", "예외를 넣어 테스트가", "주입하라"):
        assert bad not in text, bad
    assert "읽기 전용" in text
    assert "주입하지 마라" in text or "주입하지 않는다" in text


def test_리뷰어가_규칙을_베끼지_않는다():
    """🔴 사본 금지 — 정본(v4 inbox)을 **가리켜야** 한다. 옮겨 적으면 낡는다. [infra]"""
    text = (ROOT / REVIEWER).read_text(encoding="utf-8")
    assert "docs/fable/inbox/2026-09-29_v4.md" in text
    assert "rev" in text, "rev 대조(§13-6)를 안 적었다"


def test_CLAUDE_md_의_rev_가_정본과_같다():
    """🔴 사본 금지 — `CLAUDE.md` 가 정본 rev 를 **손으로** 들고 있다.

    ⚠️ 리뷰 M3(2026-09-30): 정본이 rev 15 로 올라갔는데 `CLAUDE.md:3` 은
       `(**rev 14**)` 인 채였다. §13-6 대조는 inbox 2행으로 하므로 단계 잠금이
       풀리지는 않았지만, 다음 세션이 **포인터의 rev 를 믿을** 위험이 남았다.
       `CLAUDE.md` 자신이 §사본 금지에서 경고하는 바로 그 형태다.
    🔴 그래서 이 계약은 **원본에서 자란다** — inbox 2행의 `<!-- rev: N -->` 을
       읽어 대조한다. 정본이 올라가면 여기가 빨개져 "따라가라"고 말한다. [infra]
    """
    inbox = (ROOT / INBOX).read_text(encoding="utf-8")
    m = re.search(r"<!--\s*rev:\s*(\d+)\s*-->", inbox)
    assert m, f"{INBOX} 의 rev 주석을 못 읽었다 — §13-6 대조 경로가 끊겼다"
    rev = m.group(1)
    # ⚠️ **정본을 가리키는 줄만 본다.** CLAUDE.md 는 v3 얘기로 `rev 24`·`rev 29`
    #    도 적는다(실사고 기록·archive 포인터) — 전부 긁으면 거짓으로 빨개진다.
    #    그것이 D46 과 같은 병이다: *설명하는* 수와 *가리키는* 수는 다르다.
    line = next((ln for ln in (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
                 .splitlines() if INBOX in ln and "rev" in ln), None)
    assert line, "CLAUDE.md 에 정본을 가리키며 rev 를 적은 줄이 없다"
    found = re.findall(r"rev\s*\**\s*(\d+)", line)
    assert found == [rev], f"CLAUDE.md 가 가리키는 rev {found} ≠ 정본 rev {rev}"


def test_리뷰어가_못_잰_것을_밝히게_한다():
    """🔴 도구가 셋뿐이라 스위트·DB·git diff 를 못 잰다 — 안 재고 PASS 가 가장 나쁘다.
    [infra]
    """
    text = (ROOT / REVIEWER).read_text(encoding="utf-8")
    assert "미검사" in text


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 원장은 **검증에만** 쓴다 (사용자 지시 2026-10-02)
# ══════════════════════════════════════════════════════════════════


def test_원장으로_규칙을_고치지_않는다():
    """🔴🔴 사용자 지시 2026-10-02:

    > 쌓이는거는 우리 로직이 맞냐 틀렸냐만 **검증하는 방법으로만** 사용한다..

    원장으로 **계수를 맞추거나 문턱을 조정하거나 가중치를 학습하지 않는다.**
    ⚠️ 이것을 기계로 막는다 — 규율로만 두면 다음 사람이 "쌓였으니 써 보자"고 한다.
       나 자신이 이미 *"원장이 쌓이면 λ 보정 계수를 측정해서 짓는다"* 고 적었다.

    🔴 검사 방법: `ledger` 를 **읽는 곳**은 하나여야 하고(채점 보고), 그 함수가
       설정·규칙을 **쓰지** 않아야 한다.
    """
    code = {p: strip_docs(p.read_text(encoding="utf-8"))
            for p in (ROOT / "app").rglob("*.py")}
    readers = sorted(p.relative_to(ROOT).as_posix() for p, src in code.items()
                     if re.search(r"(?:FROM|JOIN)\s+ledger\b", src, re.I))
    # ⚠️ 읽는 곳이 늘면 **여기서 먼저 멈춘다** — 어디서 읽는지 보고 판단한다
    assert readers == ["app/analyze.py"], (
        f"`ledger` 를 읽는 곳이 늘었다: {readers} — 검증 말고 무엇에 쓰는지 적어라")

    # 🔴 규칙·설정을 **쓰는** 길이 분석 쪽에 없어야 한다
    src = code[ROOT / "app" / "analyze.py"]
    for bad in ("write_text", "yaml.dump", "safe_dump", "os.environ["):
        assert bad not in src, f"분석이 `{bad}` 로 설정을 고친다"
    # 🔴 원장을 읽어 **문턱·가중치 이름**을 건드리지 않는다
    for bad in ("WEIGHT_OF[", "NAME_AT =", "SMALL_AT =", "BREAK_EVEN ="):
        assert bad not in src, f"분석이 문턱(`{bad}`)을 고친다"


def test_설정_yaml_을_코드가_쓰지_않는다():
    """🔴 설정은 **사람이 고친다.** 코드가 쓰면 그 순간 학습이 되고, 원장을 검증에만
    쓴다는 규약이 깨진다.

    ⚠️ `config/*.yaml` 은 전부 **읽기**만 한다(`rules._load`).
    """
    code = "\n".join(strip_docs(p.read_text(encoding="utf-8"))
                     for p in (ROOT / "app").rglob("*.py"))
    for bad in ("config/", "SCENARIO_RULES", "VARIABLE_TYPES", "LEAGUE_RULES"):
        for verb in ("write_text", "open(", "dump"):
            assert f"{bad}\", \"w" not in code, bad
    # 🔴 쓰기 함수 자체가 없어야 한다
    assert "yaml.dump" not in code and "yaml.safe_dump" not in code
