"""🔴🔴 **v5 §0·§2 — Solar 예산 가드.** 사용자 지시 2026-10-04 *"한도 정하고"*.

§9-3: *"이 문서의 모든 계약은 `tests/contracts/` 에 하나씩 파일로 존재해야 하고,
문서 조항 번호를 테스트 이름에 적는다."*

══════════════════════════════════════════════════════════════════
🔴 왜 가드가 알맹이인가
══════════════════════════════════════════════════════════════════

§0 이 유료 0건 규칙을 **하나만** 열었고, §2 가 *"봇은 예산 가드로 **그 한도
안에서만** 돈다"* 고 했다. 🔴 한도를 yaml 에 적어 두고 **세는 코드가 없으면 그
한도는 없는 것**이다(CLAUDE.md #2 배선 · M18 이 문서에만 있던 그 꼴).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app import solar

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)

#: 🔴 **실측 꼴 그대로**(2026-10-04 · 한국어 결장 추출 1회). 통신하지 않는다.
#   ⚠️ `reasoning_tokens` 1001 이 `completion_tokens` 1014 **안에** 있다.
REAL_USAGE = {
    "prompt_tokens": 93, "completion_tokens": 1014, "total_tokens": 1107,
    "prompt_tokens_details": {"cached_tokens": 0},
    "completion_tokens_details": {"reasoning_tokens": 1001},
}


# ══════════════════════════════════════════════════════════════════
# §2 — 한도가 yaml 에 **선언돼 있나**
# ══════════════════════════════════════════════════════════════════


def test_v5_2_한도가_yaml에_선언돼_있다():
    """🔴 §2 표의 다섯 칸이 전부 있어야 한다 — 하나라도 없으면 그것은 무한이다."""
    b = solar.budget_cfg()
    pm = b.get("per_match") or {}
    # 🔴 **사용자 결정 ② 2026-10-04** — 입력 300k · 출력 40k 로 올렸다.
    #    ⚠️ 종전 수는 150k/20k 였다. 돈 상한($3/$40)은 **그대로다**(아래).
    assert pm.get("input_tokens") == 300_000, pm
    assert pm.get("output_tokens") == 40_000, pm
    assert (pm.get("tool_calls") or {}).get("search") == 24, pm
    assert (pm.get("tool_calls") or {}).get("fetch") == 16, pm
    # ⚠️ 수를 박지 않는다 — 사용자가 2026-10-05 에 $3 → $5 로 올렸다.
    #    🔴 계약이 보는 것은 *"그 칸이 있고 월 상한보다 작다"* 다.
    assert float(b.get("per_day_usd") or 0) > 0, b
    assert float(b["per_day_usd"]) < float(b["per_month_usd"]), b
    assert b.get("per_month_usd") == 40.0, b


def test_v5_2_단가가_출처와_날짜를_들고_있다():
    """🔴 §2: *"공식 콘솔 pricing 페이지를 읽어 **날짜와 함께** 적고, 매체·중개
    사이트 수치는 쓰지 않는다."*

    ⚠️ 2026-10-04 에 공식 페이지를 **기계로 못 읽었다**(주소 셋 전부 값 없음).
       그래서 지시문 §2 수치를 **출처와 함께** 적고 `verified_by_user: false` 로
       뒀다. 🔴 사용자가 콘솔로 확인하면 그 칸이 `true` 가 된다.
    """
    p = solar.price()
    for k in ("input", "cached_input", "output"):
        assert isinstance(p.get(k), (int, float)) and p[k] > 0, (k, p)
    assert p.get("source"), "🔴 단가의 출처가 없다"
    assert p.get("as_of"), "🔴 단가의 날짜가 없다"
    assert "verified_by_user" in p, "🔴 확인 여부 칸이 없다"
    # 🔴 매체·중개 사이트를 출처로 적지 않았나
    low = str(p["source"]).lower()
    for bad in ("blog", "medium", "artificialanalysis", "openrouter",
                "reddit", "news"):
        assert bad not in low, f"🔴 매체·중개 출처: {p['source']}"


def test_v5_2_미확인_단가는_카드에_표시된다():
    """#3 조용한 0 금지 — 확인 못 한 단가로 센 비용임을 **숨기지 않는다.**"""
    mb = solar.MatchBudget()
    mb.took(REAL_USAGE)
    line = mb.line()
    if not solar.price().get("verified_by_user"):
        assert "단가 미확인" in line, line


# ══════════════════════════════════════════════════════════════════
# §2 — 비용 계산. 🔴 **추론 토큰을 두 번 세지 않는다**
# ══════════════════════════════════════════════════════════════════


def test_v5_2_추론_토큰을_두_번_세지_않는다():
    """🔴 실측: `completion_tokens` 1014 **안에** `reasoning_tokens` 1001 이 있다.

    ⚠️ 따로 더하면 비용이 거의 두 배로 보인다 — 그러면 월 상한이 절반에서 멈춘다.
    """
    p = solar.price()
    want = round((93 * p["input"] + 1014 * p["output"]) / 1_000_000, 6)
    assert solar.cost_usd(REAL_USAGE) == want, solar.cost_usd(REAL_USAGE)


def test_v5_2_캐시_적중은_싼_단가로_센다():
    """🔴 §2 — 고정 시스템 프롬프트로 **캐시 입력 단가**를 받는다."""
    p = solar.price()
    u = {"prompt_tokens": 1000, "completion_tokens": 0,
         "prompt_tokens_details": {"cached_tokens": 800}}
    want = round((200 * p["input"] + 800 * p["cached_input"]) / 1_000_000, 6)
    assert solar.cost_usd(u) == want
    # ⚠️ 캐시가 **싸다** — 전부 생입력으로 세면 더 비싸게 나온다
    assert solar.cost_usd(u) < round(1000 * p["input"] / 1_000_000, 6)


# ══════════════════════════════════════════════════════════════════
# §2 — 경기당 상한
# ══════════════════════════════════════════════════════════════════


def test_v5_2_경기당_출력_상한에서_멈춘다():
    """🔴 초과 → `budget_cut`. ⚠️ 실측상 호출 ~20회에 닿는다."""
    mb = solar.MatchBudget()
    n = 0
    while mb.can_call()[0] and n < 200:
        mb.took(REAL_USAGE)
        n += 1
    assert mb.blocked.startswith(solar.BUDGET_CUT), mb.blocked
    assert "출력" in mb.blocked, mb.blocked
    # 🔴 실측 1014 토큰/회 · 상한 **40,000**(결정 ② 2026-10-04) → 마흔 번쯤.
    #    ⚠️ 상한을 **손으로 적지 않는다** — 설정에서 끌어 그 수로 센다.
    cap = int((solar.budget_cfg().get("per_match") or {})["output_tokens"])
    want = cap / 1014
    assert want * 0.75 <= n <= want * 1.25, (n, cap)


def test_v5_2_도구_호출_상한():
    """🔴 §2 — search 24 · fetch 16."""
    mb = solar.MatchBudget()
    for _ in range(24):
        assert mb.can_tool("search")[0]
        mb.took_tool("search")
    ok, why = mb.can_tool("search")
    assert not ok and "search" in why and why.startswith(solar.BUDGET_CUT), why
    # 🔴 fetch 는 **따로** 센다(한쪽이 남의 몫을 먹지 않는다)
    assert mb.can_tool("fetch")[0]
    for _ in range(16):
        mb.took_tool("fetch")
    assert not mb.can_tool("fetch")[0]


def test_v5_2_모르는_도구는_막지_않는다():
    """⚠️ 선언 없는 도구에 상한 0 을 적용하면 그 도구가 영영 못 돈다."""
    mb = solar.MatchBudget()
    assert mb.can_tool("done")[0]


# ══════════════════════════════════════════════════════════════════
# §2 — 하루·월 상한. 🔴 **원장에서 읽는다**(메모리가 아니다)
# ══════════════════════════════════════════════════════════════════


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    """🔴 원장을 임시 자리로 옮긴다 — 진짜 원장을 건드리지 않는다."""
    monkeypatch.setattr(solar, "ROOT", tmp_path)
    return tmp_path


def _spend(path_root, usd: float, day: str = "2026-10-04"):
    p = path_root / "ledger" / "cost_202610.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"at": f"{day}T01:00:00+00:00", "usd": usd}) + "\n")


def test_v5_2_하루_상한을_넘으면_막는다(ledger):
    """🔴 **수를 박지 않는다** — 상한에서 자라게 짠다.

    ⚠️ 종전엔 `2.9 + 0.2` 로 $3 을 넘긴다고 썼다. 사용자가 2026-10-05 에
       하루 상한을 **$5** 로 올리자 그 계약이 빨개졌다 — 설정이 바뀔 때
       따라가지 않는 **사본**이었다(#1).
    """
    cap = float(solar.budget_cfg()["per_day_usd"])
    assert solar.gate(now=NOW)[0]
    _spend(ledger, cap - 0.1)
    assert solar.gate(now=NOW)[0], f"상한 {cap} 의 0.1 아래다"
    _spend(ledger, 0.2)
    ok, why = solar.gate(now=NOW)
    assert not ok and why.startswith(solar.DAY_STOP), why
    assert "자료 부족" in why, why


def test_v5_2_월_상한을_넘으면_봇을_정지한다(ledger):
    """🔴 §2 — *"봇 정지, 사용자 승인 전 재개 금지."* 하루 상한보다 **센 말**이다."""
    for _ in range(14):
        _spend(ledger, 2.9, day="2026-10-01")   # 🔴 다른 날 — 하루 상한은 안 걸린다
    mo, day = solar.spent(now=NOW)
    assert mo > 40.0 and day == 0.0, (mo, day)
    ok, why = solar.gate(now=NOW)
    assert not ok and why.startswith(solar.MONTH_STOP), why
    assert "봇 정지" in why and "승인" in why, why


def test_v5_2_원장이_없으면_0원이다(ledger):
    assert solar.spent(now=NOW) == (0.0, 0.0)
    assert solar.gate(now=NOW)[0]


def test_v5_2_원장은_더하기만_한다(ledger):
    """🔴 고치지 않는다 — 한 호출 한 줄(§2)."""
    # 🔴 **M49**(작업 지시서 §1) — `in`·`cache`·`out`·`usd` 가 필수다.
    #    ⚠️ 없으면 `write_ledger` 가 **터진다**(조용히 빈 줄을 쌓지 않는다).
    solar.write_ledger({"match": "x", "usd": 0.01, "in": 10, "cache": 0,
                        "out": 5}, now=NOW)
    solar.write_ledger({"match": "y", "usd": 0.02, "in": 20, "cache": 8,
                        "out": 7}, now=NOW)
    p = ledger / "ledger" / "cost_202610.jsonl"
    rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2 and [r["match"] for r in rows] == ["x", "y"]
    assert all(r["at"].startswith("2026-10-04") for r in rows)


def test_v5_2_상한을_넘으면_호출_자체를_막는다(ledger, monkeypatch):
    """🔴 **가드가 통로 앞에** 있다 — 넘고 나서 세면 이미 쓴 것이다."""
    called = []

    def _never(*a, **kw):
        called.append(a)
        return {"usage": {}}

    monkeypatch.setenv("UPSTAGE_API_KEY", "up_test")
    from app import config as Cfg
    Cfg.get_settings.cache_clear()
    for _ in range(14):
        _spend(ledger, 2.9, day="2026-10-01")
    with pytest.raises(solar.SolarUnavailable) as e:
        solar.chat([{"role": "user", "content": "x"}], now=NOW, _net=_never)
    assert solar.MONTH_STOP in str(e.value)
    assert called == [], "🔴 상한을 넘었는데 통로를 불렀다"
    Cfg.get_settings.cache_clear()


def test_v5_2_키가_없으면_llm_unavailable(monkeypatch):
    """🔴 §2 — 키 부재로 크래시하지 않는다. 사유는 §8-6 enum 이다."""
    monkeypatch.delenv("UPSTAGE_API_KEY", raising=False)
    from app import config as Cfg
    Cfg.get_settings.cache_clear()
    with pytest.raises(solar.SolarUnavailable) as e:
        solar.chat([{"role": "user", "content": "x"}], now=NOW,
                   _net=lambda *a, **kw: {"usage": {}})
    assert solar.LLM_UNAVAILABLE in str(e.value)
    Cfg.get_settings.cache_clear()


# ══════════════════════════════════════════════════════════════════
# §0 — **다른** 유료 키는 여전히 0건
# ══════════════════════════════════════════════════════════════════


def test_v5_0_유료_예외는_둘뿐이다():
    """🔴 §0 + **v5-A §0**: *"유료 API 예외는 Solar 하나에서 **Solar(Upstage)와
    DeepSeek 둘**로 늘어난다. 그 외 유료 서비스는 **여전히 0건**이다."*

    ⚠️ 종전 이 시험은 `DEEPSEEK` 를 **금지 목록**에 뒀다 — v5-A 가 그것을
       뒤집었다. 🔴 그래도 **그 둘뿐**이다(셋째가 들어오면 빨개진다).

    ⚠️ 기존 계약(`test_env_example에_유료_키가_없다`)이 이름 목록으로 막는다 —
       이 계약은 **Solar 가 그 목록에 들어가지 않았는지**를 본다(열어 둔 하나다).
    """
    import pathlib
    import re
    root = pathlib.Path(__file__).resolve().parents[2]
    ex = (root / ".env.example").read_text(encoding="utf-8")
    declared = set(re.findall(r"^([A-Z_0-9]+)=", ex, re.M))
    for need in ("UPSTAGE_API_KEY", "DEEPSEEK_API_KEY"):
        assert need in declared, f"🔴 `{need}` 이름이 `.env.example` 에 없다"
        # 🔴 **값은 없다**(§2 *"이름은 .env.example 에만(값 금지)"*)
        assert re.search(rf"^{need}=\s*$", ex, re.M), \
            f"🔴 `.env.example` 에 `{need}` **값**이 들어갔다"
    # ⚠️ 다른 유료 이름이 새로 들어오지 않았나(기존 목록과 같은 결)
    # ⚠️ `DEEPSEEK` 는 **빠졌다**(v5-A §0 이 허용했다). 🔴 나머지는 그대로 0건.
    for bad in ("ANTHROPIC", "OPENAI", "GEMINI", "PPLX", "XAI",
                "GROQ", "OPENROUTER", "NVIDIA"):
        assert not [d for d in declared if bad in d], bad


def test_v5_2_키가_커밋되지_않는다():
    """🔴 값은 `.env` 에만 — `.gitignore` 가 그것을 막는다."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    gi = (root / ".gitignore").read_text(encoding="utf-8")
    assert any(x.strip() == ".env" for x in gi.splitlines()), gi[:200]


def test_v5_2_수를_코드에_적지_않았다():
    """🔴 §2: *"값은 `config/llm.yaml` 에 두고 사용자만 바꾼다."* (사본 금지)"""
    import pathlib
    src = (pathlib.Path(solar.__file__)).read_text(encoding="utf-8")
    import ast
    tree = ast.parse(src)
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
                and node.value in (300_000, 40_000, 40.0, 3.0, 0.30, 1.20,
                                   0.06):
            # ⚠️ `20_000` 기본값 하나는 허용한다 — yaml 이 비었을 때의 대체다
            bad.append(f"line {node.lineno}: {node.value}")
    assert len(bad) <= 1, (
        "🔴 §2 의 수를 코드에 박았다 — yaml 이 원본이다:\n  " + "\n  ".join(bad))


def test_v5_2_캐시된_입력을_제값으로_세지_않는다():
    """🔴🔴 **실측 2026-10-04 — 예산이 도구 루프를 막았다.**

    게이트 2 를 켜고 돌리니:

    ```
    budget_cut: 경기당 입력 162946/150000 토큰 · 밟은 턴 18
    ```

    원장을 읽어 보니(호출 20회):

        입력 합  179,344 토큰
        캐시 합  120,768 토큰   🔴 **67%가 캐시다**
        비용 합  $0.0448         ⚠️ 하루 상한 $3 의 **1.5%**

    🔴 도구 루프는 턴마다 대화를 **다시 보낸다** — 그 앞부분은 §2 가 노린
       **캐시**다(`cached_input: 0.06` vs `input: 0.30` · 다섯 배 싸다).
    ⚠️ 그것을 제값으로 세면 *"150k 입력"* 상한이 **열여덟 턴**에서 끝난다 —
       조사가 아니라 **세는 방법**이 막은 것이다.

    🔴 그래서 예산은 **새로 보낸 입력**(`prompt_tokens - cached_tokens`)을 센다.
       ⚠️ 비용(`usd`)은 그대로 둔다 — 캐시도 돈을 내므로 그쪽은 제값이다.
    """
    from app import solar
    b = solar.MatchBudget()
    b.took({"prompt_tokens": 18_692, "completion_tokens": 1_791,
            "prompt_tokens_details": {"cached_tokens": 16_320}})
    # 🔴 **새로 보낸 것만** 센다
    assert b.input_tokens == 18_692 - 16_320, b.input_tokens
    # 🔴 캐시도 **수로 남긴다**(조용히 빼지 않는다 · #3)
    assert b.cached_tokens == 16_320, b.cached_tokens
    # ⚠️ 비용은 캐시를 포함한 제값이다
    assert b.usd > 0
    assert "캐시" in b.line(), b.line()


def test_v5_2_상한에_근거가_있다():
    """🔴 §5-6 — 그 수가 **왜 그 수인가**가 적혀 있어야 한다."""
    from app import rules
    per = rules.llm_budget().get("per_match") or {}
    assert int(per.get("input_tokens") or 0) >= 300_000
    basis = str(rules.llm_budget().get("basis") or "")
    assert "캐시" in basis and "2026-10-04" in basis, basis


def test_v5_2_하루와_월_상한은_그대로다():
    """🔴🔴 **진짜 가드는 건드리지 않았다** — 하루 $3 · 월 $40.

    ⚠️ 경기당 토큰 상한은 **세는 방법**의 문제였고, 돈 상한은 사용자가 정한
       것이다(§2). 🔴 그것을 올리는 것은 **내 일이 아니다**.
    """
    from app import rules
    b = rules.llm_budget()
    assert float(b["per_day_usd"]) > 0
    assert float(b["per_month_usd"]) == 40.0
