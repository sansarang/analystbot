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

from app import ids, llm, verify
from app.bot import main as B

ROOT = Path(__file__).resolve().parents[1]
















def test_발송_스위치가_기본_꺼짐이다():
    """🔴 사용자만 켠다."""
    from app.config import Settings
    assert Settings().send_enabled is False




def test_검증기가_수집기보다_먼저_있다():
    """🔴 §16-b 단계 1 — 검색기는 검증기 뒤에 붙인다."""
    assert (ROOT / "app" / "verify.py").is_file()
    assert not list((ROOT / "app").glob("collectors*")), \
        "수집기가 검증기보다 먼저 들어왔다"






def test_health가_못_잰_칸을_드러낸다():
    from app import main as M
    assert "unknowns" in inspect.getsource(M.health)










# ══════════════════════════════════════════════════════════════════
# §19 수집기 배선
# ══════════════════════════════════════════════════════════════════









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
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **설정표가 이름을 드는 것도 "읽는 것"이다**(2026-10-06)
    # ══════════════════════════════════════════════════════════════════
    #
    #  네 층 지시서 §2-1 은 피드 이름·키 이름을 **코드에 박지 말고 표에** 두라고 했다:
    #  `config/odds_sources.yaml` 의 `key_env: ODDS_API_KEY` 를 `odds.feed_key()` 가
    #  `os.getenv(feed["key_env"])` 로 읽는다. 🔴 그래서 **표의 `key_env` 값**도
    #  읽는 이름으로 센다 — 손 목록을 늘리지 않고 **원본에서 자라게** 한다(#1).
    for path in sorted((ROOT / "config").glob("*.yaml")):
        said = path.read_text(encoding="utf-8")
        read |= set(re.findall(r"key_env:\s*([A-Z_0-9]+)", said))
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
    # 🔴🔴 **`ODDS_API_KEY` 는 걷혔다** — 네 층 지시서 §2(사용자 결정 2026-10-06):
    #    *"배당은 봇이 스스로 가져온다"*. 🔴 the-odds-api **무료 등급**이고 사용자가
    #    **카드 등록 없이** 발급해 줬다(실측: 월 500 크레딧 · `/events` 0 크레딧).
    #    ⚠️ 종전 금지는 **유료** 배당 API(odds-api.net 유료 등급) 때문이었다 — 그
    #       까닭이 사라졌으므로 이름만 목록에서 뺀다. 나머지 일곱은 그대로 금지다.
    for bad in ("ANTHROPIC_API_KEY", "PPLX_API_KEY", "XAI_API_KEY",
                "APIFOOTBALL_KEY", "GROQ_API_KEY",
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
    # 🔴 배당 키 **셋만** 예외다(네 층 §2-1 · 무료 등급) — 그것들
    #    말고 `ODDS` 가 든 이름이 새로 생기면 **그때는 빨개진다**(유료 피드 방지).
    ALLOW_ODDS = {"ODDS_API_KEY", "ODDSPAPI_KEY", "ODDS_API_IO_KEY"}
    for bad in ("ANTHROPIC", "PPLX", "PERPLEXITY", "XAI", "ODDS",
                "APIFOOTBALL", "OPENROUTER", "GROQ", "NVIDIA", "GEMINI",
                "JUDGE_MODEL", "MODEL_MATCHUP", "NARRATOR_MODEL"):
        hit = [d for d in declared if bad in d and d not in ALLOW_ODDS]
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




def test_env가_없어도_크래시하지_않는다(tmp_path):
    from app import config as Cfg
    assert Cfg.load_env(tmp_path / "없는파일") == 0




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

# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **되살렸다** — §8 5단계 삭제 작업이 이 계약을 함께 떼어 냈다(2026-10-06)
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 지워진 모듈을 보는 조항을 기계로 떼어 내다가 **이 조항까지** 떼어 냈다 —
#     `NOT_WIRED` 목록이 그 함수 안에 살았기 때문이다.
#  🔴 이 보장은 v6 에서 **더 중요하다**: 4단계에서 `app.core` 제외를 걷었으므로
#     v6 의 안 이어진 공개 함수가 이 계약에서 빨개진다.
#  🔴 지워진 모듈의 미배선 항목은 함께 걷었다(그 코드가 없으니 셀 것도 없다).

# 🔴 **도움함수도 되살렸다** — `_credits` 는 "이름이 아니라 **귀속**으로"
#    호출을 센다(그 설명이 그 함수 독스트링에 있다).




# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **고아 공개함수 계약** — §8 5단계 뒤 다시 세운다(2026-10-06)
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 삭제 작업이 이 조항을 두 번 떼어 냈다(미배선 목록이 그 함수 안에 살았고,
#     목록의 항목들이 지워진 모듈 이름을 들고 있었다). 🔴 그래서 **손으로** 다시
#     적는다 — 목록은 **선언 창 셋**뿐이다.

#: 🔴 **계약이 읽는 선언 창** — 코드가 부르는 자리가 아니다(지우면 선언이 사라진다).
#   ⚠️ 늘면 `tests/stage4/test_analyze.py::test_미배선_목록은_선언_창_셋뿐이다` 가
#      빨개진다 — 적는 대신 **잇거나 지우는 것**이 규칙이다(지시 2026-10-02).
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


NOT_WIRED: set[str] = {
    "app.rules.added_types",          # 카탈로그에 사용자 지시로 더한 유형 선언
    "app.rules.unimplemented_types",  # 옛 세포가 못 하는 유형 선언
    "app.window.set_clock",           # 계약이 시계를 고정하는 자리
}
# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **부르는 곳이 `tools/` 인 함수** — 안 이어진 것이 아니다
# ══════════════════════════════════════════════════════════════════
#
#  🔴 이 검사는 **`app/` 안에서만** 센다(테스트가 부르는 것은 배선이 아니다).
#     그래서 **도구가 부르는** 함수가 고아로 보인다. ⚠️ `NOT_WIRED`(아직 안 이은
#     것)와 뜻이 다르므로 **따로** 적는다 — 그리고 아래 검사가 *"그 도구가 정말
#     부르나"* 를 센다(이름만 적어 두고 비는 것을 막는다).
TOOL_ONLY: dict[str, str] = {
    # 🔴🔴 **확률 경로 재구성**(사용자 지시 2026-10-12 적중률 1번).
    #    🔴 운영 ⑯ 은 **이어졌다**(사용자 결정 (a) 2026-10-12): `pipeline` 이
    #    `base_p.probs`(Elo 바닥)를 `probmodel.run(floor=)` 에 넘기고, 그 안에서
    #    `probfloor.solve_move`·`RESIDUAL_AXES` 를 쓴다 — 그 둘은 **배선된 것**이라
    #    여기 없다.
    #    ⚠️ 아래 셋은 **백필 채점기 전용**이다(바닥·잔차를 승무패 수준에서 직접
    #    섞는 길 · 운영은 λ 수준에서 섞는다).
    "app.core.probfloor.floor_of": "tools/backfill_score.py",
    # 🔴🔴 **§1 평가 지표**(지시서 2026-10-12 엔진 교체) — 지표는 `app/` 에 한 곳에
    #    두고 **도구들이** 부른다(사본 금지). ⚠️ 운영 카드 채점이 같은 지표를 써야
    #    하므로 `app/` 에 있고, 운영 확률 경로는 이것을 **안 부른다**(검증 전용).
    # 🔴🔴 **§2 바닥 점수 후보**(지시서 2026-10-12 엔진 교체) — 지금은 **후보 판**
    #    이다(§0: *"운영 확률은 현 새 구조 그대로 두고, 백필 판정을 통과한 판만
    #    운영으로 승격"*). 🔴 적합·비교는 도구가 부른다.
    #    ⚠️ 운영 ③ 에 잇는 것은 **§2 판정이 끝난 뒤**다.
    # 🔴🔴 **§0 얼린 옛 경로**(비교 시험 지시서 2026-10-12) — **비교 도구만**
    #    부른다. ⚠️ 운영이 부르면 그것은 *"옛 경로로 돌아간 것"* 이다(§7 판정 전).
    "app.core.legacy.old_engine.sides_move": "tools/compare_paths.py",
    # 🔴 모듈째 — `compare_paths` 가 `old_engine` 을 부른다(위 설명)
    # ⚠️ 나머지 공개 함수(`run`·`league_mean`·`home_mul` …)는 **그 파일 안에서**
    #    쓰인다 — 얼린 코드라 고아 검사에서 빠질 수 없다. 🔴 그래서 모듈째
    #    `LEGACY_FROZEN` 으로 센다(아래).
    # 🔴🔴 **§7 공변량**(지시서 2026-10-12(둘째)) — ⑬ 이 **관찰값으로** 싣고, λ 에
    #    들어가는 것은 **§9 전진 선택이 채택한 뒤**다(계약 S1). 지금 부르는 곳은
    #    전진 선택 도구다.
    "app.core.context.covariates": "tools/forward_terms.py",
    # 🔴 §12 그룹 보정표 — **검증 전용**이라 운영이 안 부른다(직접 보정 금지).
    "app.core.groups.group_of": "tools/forward_terms.py",
    "app.core.groups.bias": "tools/forward_terms.py",
    "app.core.groups.verdict_of": "tools/forward_terms.py",
    # 🔴🔴 **§8 결장의 무게·벤치**(지시서 2026-10-12(둘째)) — 후보 판이다.
    #    ⚠️ ⑪ 에 잇는 것은 §5(선수 점수 판)·§9 채택 뒤다(§15 승격 순서).
    "app.core.ratings.lineup_strength.usual_xi": "tools/fit_player_pm.py",
    "app.core.ratings.lineup_strength.absence_loss": "tools/fit_player_pm.py",
    "app.core.ratings.lineup_strength.bench_mean": "tools/fit_player_pm.py",
    # 🔴 §5 선수 ± — 적합 도구가 부른다(운영 ⑪ 은 §9 채택 뒤다)
    "app.core.ratings.player_pm.fit": "tools/fit_player_pm.py",
    # 🔴🔴 **§2 구간 ±**(라인업 지시서 2026-10-13) — 벌은 **시즌 교차**로 고르고
    #    판은 `.parquet` 다. ⚠️ 운영 ⑪ 에 잇는 것은 §6 판정 뒤다(§8 배선).
    "app.core.ratings.player_pm.pick_lam": "tools/fit_pm.py",
    "app.core.ratings.player_pm.stability": "tools/fit_pm.py",
    "app.core.ratings.player_pm.save": "tools/fit_pm.py",
    "app.core.ratings.player_pm.load": "tools/fit_pm.py",
    "app.core.ratings.player_pm.value_of": "tools/fit_player_pm.py",
    # 🔴🔴 **§3 새 λ 식**(지시서 2026-10-12 §3) — 적합 도구가 부른다. ⚠️ 운영 ⑯ 에
    #    잇는 것은 **§3 판정이 끝난 뒤**다(§0 승격 절차 · §10).
    "app.core.probfloor.lambdas": "tools/fit_probfloor.py",
    # 🔴 §4 `compute` — **전진 선택 도구**가 채택 목록을 바꿔 가며 부른다.
    #    ⚠️ 운영 ⑯ 에 잇는 것은 §9 가 채택을 끝낸 뒤다(§15 승격 순서).
    "app.core.probfloor.compute": "tools/forward_terms.py",
    "app.core.probfloor.load_coef": "tools/fit_probfloor.py",
    "app.core.probfloor.score_grid": "tools/compare_engines.py",
    "app.core.probfloor.markets_of": "tools/compare_engines.py",
    "app.core.ratings.load_params": "tools/fit_ratings.py",
    "app.core.ratings.elo.rate": "tools/fit_ratings.py",
    "app.core.ratings.elo.prob_input": "tools/fit_ratings.py",
    "app.core.ratings.elog.rate": "tools/fit_ratings.py",
    "app.core.ratings.elog.prob_input": "tools/fit_ratings.py",
    "app.core.ratings.pi.rate": "tools/fit_ratings.py",
    "app.core.ratings.pi.prob_input": "tools/fit_ratings.py",
    # 🔴🔴 **§1 출전 시간**(라인업 지시서 2026-10-13 §1) — 백필 도구가 부른다.
    #    ⚠️ 운영 ⑪ 에 잇는 것은 §5 `lineupfix` 가 **판정을 통과한 뒤**다(§8 배선).
    "app.collect.minutes.sides_of_jleague": "tools/minutes_backfill.py",
    "app.collect.minutes.intervals_by_number": "tools/minutes_backfill.py",
    "app.collect.minutes.pick_card": "tools/minutes_backfill.py",
    "app.collect.minutes.learn_names": "tools/minutes_backfill.py",
    "app.collect.minutes.intervals": "tools/minutes_backfill.py",
    "app.collect.minutes.before": "tools/minutes_backfill.py",
    # 🔴 **둘째 통로**(fotmob `playerStats` 의 뛴 분) — 같은 백필이 부른다
    "app.collect.minutes.intervals_from_minutes": "tools/minutes_backfill.py",
    # 🔴🔴 **§5 라인업 보정 경계**(라인업 지시서 2026-10-13) — 지금은 **후보 판**
    #    이라 비교 도구가 부른다. ⚠️ 운영 ⑯ 뒤에 잇는 것은 **§6 판정이 채택한
    #    뒤**다(§8 배선) — 그때 이 줄들을 **지운다**.
    "app.core.lineupfix.raw_of": "tools/lineup_trial2.py",
    "app.core.lineupfix.ortho": "tools/lineup_trial2.py",
    "app.core.lineupfix.apply": "tools/lineup_trial2.py",
    "app.core.lineupfix.check": "tools/lineup_trial2.py",
    "app.core.lineupfix.plate_of": "tools/lineup_trial2.py",
    "app.core.lineupfix.bench_shift_of": "tools/lineup_trial2.py",
    "app.core.metrics.bands": "tools/judge_models.py",
    "app.core.metrics.calib": "tools/backfill_score.py",
    "app.core.metrics.check_split": "tools/judge_models.py",
    "app.core.metrics.paired": "tools/backfill_score.py",
    "app.core.metrics.verdict_of": "tools/backfill_score.py",
    "app.core.metrics.rps": "tools/backfill_score.py",
    "app.core.metrics.brier": "tools/backfill_score.py",
    "app.core.metrics.logloss": "tools/backfill_score.py",
    "app.core.metrics.boot_ci": "tools/backfill_score.py",
    "app.core.metrics.direction_hit": "tools/judge_models.py",
    "app.core.backfill.features": "tools/fit_matchup_model.py",
    "app.core.backfill.score_of": "tools/fit_matchup_model.py",
    # 🔴 사용자 지시 2026-10-11 ① — 리그 홈 이점을 **그 리그 결과로** 잰다.
    #    ⚠️ 측정은 **실행 중에 안 한다**(적합과 같은 규율) — 도구가 표에 적고
    #       봇은 그 표를 **읽기만** 한다.
    "app.collect.fotmob.league_matches_url": "tools/measure_fotmob_baselines.py",
    "app.collect.fotmob.league_results": "tools/measure_fotmob_baselines.py",
    "app.collect.fotmob.league_seasons": "tools/measure_fotmob_baselines.py",
}


def test_남은_모듈에_고아_공개함수가_없다():
    """🔴🔴 **만든 것은 부르는 곳이 있어야 한다** — 안 이어진 코드는 없는 코드보다 나쁘다.

    🔴 §8 4단계에서 `app.core` 제외를 걷었다 — v6 의 안 이어진 공개 함수도 여기서
       빨개진다. ⚠️ 세는 방법은 `_credits` 가 든다(이름이 아니라 **귀속**으로 센다).
    """
    # 🔴 **목록이 원본에서 자란다** — 손으로 적은 목록은 늘 한 발 늦는다(#1)
    mods = {}
    for path in sorted((ROOT / "app").rglob("*.py")):
        parts = list(path.relative_to(ROOT).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        name = ".".join(parts)
        if name.endswith("__main__"):
            continue                 # 진입점 — 부르는 곳은 `python -m` 이다
        mods[name] = importlib.import_module(name)
    # 🔴 **`app/` 안에서만 센다** — 테스트가 부르는 것은 배선이 아니다
    used = _credits(mods)
    orphans = []
    for name, mod in mods.items():
        for fn, obj in inspect.getmembers(mod, inspect.isfunction):
            if fn.startswith("_") or obj.__module__ != name:
                continue
            key = f"{name}.{fn}"
            # 🔴🔴 **얼린 옛 경로는 모듈째 센다**(비교 시험 §0 · 계약 K0):
            #    그 파일은 **고치지 않는다**. 그 안의 함수를 하나씩 이으라고
            #    요구하면 얼린 코드를 손대야 하고, 그러면 기준이 움직인다.
            #    ⚠️ 대신 `tools/compare_paths.py` 가 그 모듈을 부르는지 아래에서 센다.
            if name.startswith("app.core.legacy"):
                continue
            if used.get(key, 0) == 0 and key not in NOT_WIRED \
                    and key not in TOOL_ONLY:
                orphans.append(key)
    assert orphans == [], f"부르는 곳이 없다: {sorted(orphans)}"
    # 🔴 반대 위험 — 이어 놓고 목록에 남기면 목록이 거짓이 된다
    stale = [k for k in NOT_WIRED if used.get(k, 0) > 0]
    assert stale == [], f"이어졌으니 NOT_WIRED 에서 빼라: {stale}"
    # 🔴 `TOOL_ONLY` 는 **그 도구가 정말 부르는지** 센다(이름만 적는 것을 막는다)
    for key, tool in TOOL_ONLY.items():
        said = (ROOT / tool).read_text(encoding="utf-8")
        fn = key.rsplit(".", 1)[1]
        assert fn in said, f"🔴 `{key}` 를 `{tool}` 이 안 부른다"
