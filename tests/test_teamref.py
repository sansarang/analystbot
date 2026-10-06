"""🔴🔴 **이름표는 ID 밑에 붙는다** — 1단계(사용자 지시 2026-10-03).

══════════════════════════════════════════════════════════════════
🔴 병의 정체 — *"이름을 신원으로 쓴다"*
══════════════════════════════════════════════════════════════════

> 비교하는 쪽과 저장한 쪽의 **언어가 다르면 자기가 찾은 걸 버린다.**

| 사례 | 저장 | 재조회 | 결과 |
|---|---|---|---|
| J리그 | `柏レイソル` | `가시와 레이솔` | 찾은 페이지 **폐기** |
| 자동완성 | `크로아티아` | `Croatia` | 정확한 경기를 집고도 **폐기** |
| `slate.find` | `Croatia` | `크로아티아` | *"창 밖"* 이라는 **거짓 사유** |

🔴 **불변식**: 같은 팀을 어느 언어로 넣어도 `key_of` 가 **같은 열쇠**를 줘야 한다.
"""
from __future__ import annotations

import pytest

from app import teamref

#: 🔴 같은 팀의 여러 언어 표기. ⚠️ **실측에서 실제로 나온 글자만** 적는다 —
#   지어낸 표기로 시험을 맞추면 그 이름표가 거짓이 된다.
SAME_TEAM = [
    ("나라(CLDR)", ["크로아티아", "Croatia", "クロアチア", "Croacia"]),
    ("축구협회(손)", ["잉글랜드", "England", "イングランド"]),
    ("클럽(받아 옴)", ["가시와 레이솔", "Kashiwa Reysol", "柏レイソル"]),
    ("클럽(어댑터)", ["LG 트윈스", "LG Twins"]),
]


@pytest.mark.parametrize("what,names", SAME_TEAM, ids=[x[0] for x in SAME_TEAM])
def test_어느_언어로_넣어도_같은_열쇠다(what, names):
    keys = {}
    for n in names:
        k, why = teamref.key_of(n)
        assert k, f"{what}: `{n}` 를 못 풀었다 — {why}"
        keys[n] = k
    assert len(set(keys.values())) == 1, f"{what}: 열쇠가 갈렸다 {keys}"


def test_모호하면_고르지_않는다():
    """🔴 *"거짓 매칭보다 미상이 낫다"*(`app/ids.py` 의 규율).

    ⚠️ 한 이름이 여러 팀에 있으면 하나를 고르는 것이 추측이다. 🔴 **빈 문자열과
       사유**를 돌려주고, 부르는 쪽이 조건을 더 줘서 가른다.

    ══════════════════════════════════════════════════════════════════
    🔴 **실제 겹침에 기대지 않는다**(사용자 지적 2026-10-04)
    ══════════════════════════════════════════════════════════════════

    ⚠️ 종전엔 *"이름표 안에서 겹치는 것을 찾아 쓰고, 없으면 skip"* 이었다. 그래서
       겹침을 0으로 만들자 **계약이 공허해졌다**(skip 으로 넘어갔다). 🔴 계약이
       건너뛰면 그것은 없는 계약이다 — **겹침을 시험이 직접 만든다.**
    """
    reg = teamref.registry()
    a = teamref.key_of("Kashiwa Reysol")[0]
    b = teamref.key_of("Gamba Osaka")[0]
    assert a and b and a != b
    k = teamref.norm("겹치는이름시험")
    reg.index[k] = [a, b]
    try:
        got, why = teamref.key_of("겹치는이름시험")
        assert got == "", f"모호한데 골랐다 → {got}"
        assert "곳**에 있다" in why, why
        # 🔴 **조건을 주면 갈린다** — 같은 리그라 리그로는 못 가르고, 종목도 같다.
        #    ⚠️ 그래서 여기서는 *"못 가린다"* 가 맞는 답이다.
        assert teamref.key_of("겹치는이름시험", league="J리그")[0] == ""
    finally:
        reg.index.pop(k, None)
    # 🔴 **다른 종목이면 갈린다**
    base = teamref.key_of("LG Twins")[0]
    reg.index[k] = [a, base]
    try:
        assert teamref.key_of("겹치는이름시험")[0] == ""
        assert teamref.key_of("겹치는이름시험", sport="baseball")[0] == base
        assert teamref.key_of("겹치는이름시험", sport="soccer")[0] == a
    finally:
        reg.index.pop(k, None)


def test_출처_없는_이름은_안_담는다():
    """🔴 CLAUDE.md #4 — 지어낸 이름이 섞이면 봇이 **조용히 틀린 팀**을 고른다.

    ⚠️ 모든 이름에 **어디서 왔는지**가 붙어 있어야 되짚을 수 있다.
    """
    reg = teamref.registry()
    bad = []
    for ref in reg.teams.values():
        for lang, names in ref.names.items():
            for n in names:
                if not ref.by.get(teamref.norm(n)):
                    bad.append((ref.key, lang, n))
    assert not bad, f"출처 없는 이름: {bad[:6]}"


def test_손으로_적는_것은_축구협회_넷뿐이다():
    """🔴🔴 사용자 지시 2026-10-03:

    > 국가대표 이름표 — **손으로 만들지 말고 CLDR**... ISO 코드가 없는
    > **4개 축구협회**만 손으로 넣으면 된다.

    ⚠️ 손 목록이 자라면 이적·개명 때마다 한 발 늦고, 늦은 목록은 **조용히 틀린
       팀**을 고르게 한다. 🔴 그 수가 넷에 묶여 있는지 계약이 지킨다.
    """
    from app import rules
    rows = rules._load(teamref.NATIONS).get("nations") or []
    assert len(rows) == 4, f"손으로 적은 협회가 {len(rows)}곳이다 — 넷이어야 한다"
    for row in rows:
        assert str(row.get("source") or "").strip(), row
        assert str(row.get("key") or "").startswith("fa:"), row




def test_리그가_다르면_합치지_않는다():
    """🔴 `Tigers` 는 KBO·MLB·NPB 에 다 있다 — 이름이 같다고 묶으면 **남의 경기**다."""
    reg = teamref.registry()
    kia, _ = teamref.key_of("Kia Tigers")
    det, _ = teamref.key_of("Detroit Tigers")
    han, _ = teamref.key_of("Hanshin Tigers")
    got = [x for x in (kia, det, han) if x]
    assert len(set(got)) == len(got), f"서로 다른 팀이 한 열쇠로 묶였다: {got}"


def test_정규화는_한_곳이다():
    """🔴 두 곳이 다르게 정규화하면 **같은 이름이 서로 다른 열쇠**가 된다 —
    그것이 이 병의 모양이다(사본 금지)."""
    import ast
    import inspect
    import textwrap
    code = ast.unparse(ast.parse(textwrap.dedent(inspect.getsource(teamref.norm))))
    assert "league_index.norm" in code




def test_돌연변이가_통과하지_못한다():
    """🔴🔴 **계약의 계약** — 사용자 지시 2026-10-03:

    > 돌연변이 검사: `resolve()` 가 일부러 **엉뚱한 언어 이름을 넘기게** 바꿨을 때
    > 1번 테스트가 빨개지는지 확인. 로그에서 *"돌연변이가 또 통과했다"* 가 **두 번**
    > 나왔다 — **이 검사가 실제로 물리는지가 핵심이다.**

    여기서는 이름표의 **언어 꼬리표를 망가뜨려** 불변식이 깨지는지 본다.
    ⚠️ 깨지지 않으면 위 `test_어느_언어로_넣어도_같은_열쇠다` 가 **공허한 참**이다.
    """
    reg = teamref.registry()
    k_ja, _ = teamref.key_of("柏レイソル")
    k_en, _ = teamref.key_of("Kashiwa Reysol")
    assert k_ja == k_en and k_ja

    # 🔴 **돌연변이**: 일본어 표기를 다른 팀에 붙인다(= 저장·조회 언어가 갈린 꼴)
    other = next(x for x in reg.teams if x != k_ja and reg.teams[x].names)
    hurt = teamref.norm("柏レイソル")
    reg.index[hurt] = [other]
    try:
        got, _ = teamref.key_of("柏レイソル")
        assert got != k_en, "🔴 돌연변이가 통과했다 — 불변식 계약이 공허한 참이다"
    finally:
        reg.index[hurt] = [k_ja]
    # 원복됐나
    assert teamref.key_of("柏レイソル")[0] == k_en


#: 🔴 **언어마다 그 언어의 표기**가 나와야 한다. ⚠️ 실측에서 전부 한 번씩 틀렸다.
LABELS = [
    ("LG Twins", {"ko": "LG 트윈스", "en": "LG Twins"}),
    ("Kia Tigers", {"ko": "KIA 타이거즈", "en": "Kia Tigers"}),
    ("Kashiwa Reysol", {"ko": "가시와 레이솔", "ja": "柏レイソル",
                        "en": "Kashiwa Reysol"}),
    ("Croatia", {"ko": "크로아티아", "ja": "クロアチア", "en": "Croatia",
                 "es": "Croacia"}),
    ("England", {"ko": "잉글랜드", "ja": "イングランド", "en": "England"}),
]






def test_출처_등급이_한_곳이다():
    """🔴 `add`(덮을까)와 `label`(고를까)이 **같은 표**를 봐야 한다.

    ⚠️ 두 곳에 적으면 한쪽이 조용히 틀리고, 그러면 *"왜 이 이름이 대표인가"* 를
       설명할 수 없다(사본 금지).
    """
    import ast
    import inspect
    import textwrap
    for fn in (teamref.Registry.add, teamref.TeamRef.label):
        code = ast.unparse(ast.parse(textwrap.dedent(inspect.getsource(fn))))
        assert "_src_rank(" in code, fn.__qualname__
    # 🔴 **공식이 맨 위, 코드 별칭이 맨 아래**(사용자 지적 2026-10-04:
    #    *"공식이 tsdb(제3자 DB)보다 낮을 수 없다"*)
    assert teamref.SOURCE_ORDER[0] == "jleague.jp"
    # 🔴 맨 아래는 **배운 것**이다(③) — 사람이 적은 것보다 낮다
    from app import learn_names
    assert teamref.SOURCE_ORDER[-1] == learn_names.SOURCE
    assert teamref.SOURCE_ORDER[-2] == "외부 id"
    assert teamref.SOURCE_ORDER.index("npb.jp") < \
        teamref.SOURCE_ORDER.index("리그 명단")


def test_글자가_언어를_말한다():
    """🔴 비라틴은 **글자로** 갈린다 — 출처가 틀린 꼬리표를 붙여도 바로잡는다.

    ⚠️ 실측: 리그 명단이 `柏レイソル` 을 그 리그 현지어라며 넣었고, KBO 의 한글
       별칭도 같은 길로 들어와 **한글 칸에 일본어가 섞였다.**
    🔴 라틴은 글자로 못 가른다(`England`/`Inglaterra`) — 그때는 출처를 믿는다.
    """
    assert teamref.lang_of("柏レイソル") == "ja"
    assert teamref.lang_of("가시와") == "ko"
    assert teamref.lang_of("Inglaterra", "es") == "es"
    assert teamref.lang_of("England") == "en"


def test_한글을_자모로_쪼개지_않는다():
    """🔴🔴 이 저장소가 **같은 사고를 두 번** 겪었다.

    `app/ids.py` 의 실사고 2026-09-21: *"`NFKD → ascii ignore` 정규화가 한글을
    통째로 지워 한국 선수 이름이 **전부 서로 일치**했다."*

    ⚠️ 실측 2026-10-03: 내가 `NFKD` 를 그대로 써서 `크로아티아` 가 **자모로
       분해된 꼴**(10글자)로 한 번 더 담겼다 — 같은 이름이 둘이 됐고 대표 표기가
       그 쪽으로 갔다.
    🔴 라틴 발음부호만 벗기고 결과를 **NFC 로 되돌린다.**
    """
    assert teamref._plain("크로아티아") == "크로아티아"
    assert len(teamref._plain("크로아티아")) == 5
    assert teamref._plain("Mónaco") == "Monaco"
    assert teamref._plain("柏レイソル") == "柏レイソル"
    # 🔴 **이름표 안에 중복이 없다** — 같은 글자가 두 꼴로 들어가면 대표가 흔들린다
    reg = teamref.registry()
    for ref in reg.teams.values():
        for lang, names in ref.names.items():
            assert len(names) == len(set(names)), (ref.key, lang, names)
