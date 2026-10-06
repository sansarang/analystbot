"""단계 2 계약 — `config/*.yaml` 이 v4 §4·§5 표를 다 담았나. [§4 · §5]

🔴 **이 파일의 요지는 하나다: 목록이 원본에서 자란다.**
   유형·템플릿 이름을 여기 베끼지 않는다 — v4 §4·§5 표를 **파싱해서** yaml 과
   대조한다. v4 에 항목이 생기면 여기가 빨개져 "따라가라"고 말한다.

⚠️ **표를 파싱하는 정규식이 행을 조용히 빠뜨리는 것**이 이 방식의 유일한 위험이다.
   실측 2026-09-30: 첫 판이 `[a-z_]+` 였고 `h2h_pattern` 을 **숫자 때문에**
   빠뜨려 13종을 12종으로 셌다. 그래서 `_rows()` 가 **표의 데이터 행 수와 뽑은
   수를 대조**한다 — 정규식이 놓치면 그 자리에서 터진다.
"""
from __future__ import annotations

import re
from pathlib import Path

from app import rules as R

ROOT = Path(__file__).resolve().parents[2]
INBOX = "docs/fable/inbox/2026-09-29_v4.md"


def _section(start: str, end: str) -> str:
    """v4 의 한 절. 🔴 밑줄 이스케이프(`coach\\_change`)를 푼다."""
    text = (ROOT / INBOX).read_text(encoding="utf-8").replace("\\_", "_")
    return text.split(start)[1].split(end)[0]


def _rows(section: str, header_word: str) -> list[tuple[str, ...]]:
    """표의 첫 칸이 식별자인 행들.

    🔴 **정규식이 행을 빠뜨리면 터진다.** 데이터 행을 따로 세어 대조한다 —
       "원본에서 자란다"는 파싱이 **완전할 때만** 참이다.
    """
    data = [ln for ln in section.splitlines()
            if ln.startswith("|")
            and not re.match(r"^\|\s*-", ln)
            and not re.match(rf"^\|\s*{header_word}\s*\|", ln)]
    got = re.findall(r"^\|\s*([a-z0-9_]+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|",
                     section, re.M)
    assert len(got) == len(data), (
        f"표 데이터 행 {len(data)}개 중 {len(got)}개만 뽑았다 — 정규식이 "
        f"행을 빠뜨린다. 뽑은 것: {[g[0] for g in got]}")
    return got


# ══════════════════════════════════════════════════════════════════
# §4 변수 유형표
# ══════════════════════════════════════════════════════════════════

def test_variable_types_가_v4_4절_표를_전부_담았다():
    """🔴 사본 금지 — 유형 이름을 여기 적지 않는다. v4 §4 표에서 읽는다. [§4]"""
    want = {k for k, _, _ in _rows(_section("## 4. 변수 유형표",
                                            "## 5. 시나리오"), "유형")}
    have = set(R.variable_types())
    # 🔴 **사용자 지시로 더한 유형만** 여분으로 허용한다 — 선언과 근거 문서가 있어야
    #    한다(사용자 지시 2026-10-02 로 `home_field` 를 더했다).
    #    ⚠️ 선언 없이 더하면 아래 `have - want - added` 가 남아 빨개진다.
    added = {str(a.get("type")) for a in R.added_types()}
    assert have - want <= added, (
        f"선언 없이 더한 유형 {sorted(have - want - added)} — "
        f"`added_by_user_instruction` 에 지시 날짜·근거 문서와 함께 적어라")
    assert want - have == set(), f"빠진 유형 {sorted(want - have)}"
    # 🔴 선언한 것마다 **근거 문서가 실재해야** 한다 — 없으면 "지시였다"는 말만 남는다
    for a in R.added_types():
        assert a.get("date") and a.get("instruction") and a.get("why"), a
        doc = ROOT / str(a.get("doc") or "")
        assert doc.is_file(), f"{a.get('type')}: 근거 문서가 없다 — {a.get('doc')}"
    # 🔴 선언했는데 yaml 에 없으면 목록이 거짓이다
    assert added <= have, f"선언만 있고 유형이 없다: {sorted(added - have)}"
    assert len(want) == 13, f"§4 는 13유형이다 (표에서 {len(want)}종을 읽었다)"


def test_유형마다_세포_질문과_방향_규칙이_있다():
    """§4 — *"각 유형은 어디서 나오는가(세포 질문)와 보통 어느 방향을 미는가를
    갖는다."* 🔴 빈 칸을 두면 그 유형은 영영 구현되지 않는다. [§4]
    """
    for name, spec in R.variable_types().items():
        assert spec.get("cell_question", "").strip(), f"{name}: 세포 질문이 없다"
        assert spec.get("direction_rule", "").strip(), f"{name}: 방향 규칙이 없다"


def test_전제_유형_셋이_v4_4절과_같다():
    """🔴 §4 — *"match_type, lineup_intent, travel_schedule 유형은 기본
    `is_premise=true`."* 이 셋이 틀리면 시나리오가 통째로 무효다. [§4]
    """
    # 🔴 **정본에서 뽑는다**(리뷰 M2). 종전 판은 yaml 키를 정본 줄로 **거르는**
    #    것이라 방향이 반쯤 뒤집혀 있었다 — 정본에 유형이 추가돼도 yaml 에
    #    없으면 조용히 빠졌다(13유형 계약이 겹쳐 막아 줬을 뿐이다).
    line = next(ln for ln in _section("## 4. 변수 유형표",
                                      "## 5. 시나리오").splitlines()
                if "is_premise" in ln)
    head = line.split("**:")[1].split("유형은")[0]
    want = {t.strip() for t in head.replace("`", "").split(",") if t.strip()}
    assert want, f"정본 줄에서 전제 유형을 못 뽑았다: {line!r}"
    assert set(R.premise_types()) == want, \
        f"전제 유형이 v4 §4 와 다르다: {sorted(R.premise_types())} ≠ {sorted(want)}"
    assert len(want) == 3


def test_구현_안_된_유형이_이름으로_남는다():
    """🔴 조용한 0 금지 (#7) — 세포가 없는 유형을 **이름으로** 남긴다. [§4]

    ⚠️ **전 판은 *"13종 전부 미구현"* 을 단정했다.** 2026-10-02 에 아홉 유형이
       구현되자 그 단정이 거짓이 됐고, 더 나쁜 것은 yaml 의 `implemented` 가
       `false` 로 남아 **카드가 "recent_pattern 은 세포가 없다"는 거짓을 적을
       참이었다**(배선이 찾았다).
    🔴 그래서 수를 단정하지 않고 **구현 + 미구현 = 표 전체**만 본다. 어느 쪽인지는
       `app/classify.py` 가 정하고 `tests/stage4/test_analyze.py` 가 대조한다.
    """
    todo = R.unimplemented_types()
    done = [k for k in R.variable_types() if k not in todo]
    assert sorted(todo + done) == sorted(R.variable_types()), \
        "구현 + 미구현이 유형표 전체가 아니다 — 한 유형이 사라졌다"
    assert todo, "미구현이 0 이라면 그 사실을 다른 계약이 증명해야 한다"
    # 🔴 **수를 손으로 적지 않는다** — v4 §4 표 + 사용자 지시로 더한 것이 원본이다.
    #    ⚠️ 비교 대상이 `todo` 가 아니라 **유형표 전체**다 — 구현 여부와 무관하게
    #       표의 모든 행이 yaml 에 있어야 한다는 것이 이 줄의 뜻이다.
    v4_types = {k for k, _, _ in _rows(_section("## 4. 변수 유형표",
                                               "## 5. 시나리오"), "유형")}
    expect = len(v4_types) + len(R.added_types())
    assert len(R.variable_types()) == expect, \
        f"유형표 {len(R.variable_types())}종 · 기대 {expect}종"


# ══════════════════════════════════════════════════════════════════
# §5 시나리오 규칙표
# ══════════════════════════════════════════════════════════════════

def test_템플릿이_v4_5b_표를_전부_담았다():
    """🔴 사본 금지 — 템플릿 이름을 여기 적지 않는다. [§5-b]"""
    want = {k for k, _, _ in _rows(_section("## 5. 시나리오 생성 규칙표",
                                            "## 6."), "템플릿")}
    have = set(R.templates())
    assert have == want, (f"빠진 템플릿 {sorted(want - have)} · "
                          f"v4 에 없는 템플릿 {sorted(have - want)}")
    assert len(want) == 9, f"§5-b 는 템플릿 9개다 ({len(want)}개를 읽었다)"


def test_템플릿마다_종목과_조건과_스코어가_있다():
    """🔴 스코어 없는 템플릿은 생존을 셀 수 없다(§1). [§5-b]

    ⚠️ **예외는 이름으로 남는다** — `baseball_repeat_yesterday` 는 전날 스코어를
       재사용하므로 고정 스코어가 없다. 빈 목록을 조용히 두지 않고
       `reuse_yesterday: true` 로 적는다.
    """
    for name, spec in R.templates().items():
        assert spec.get("sport") in ("soccer", "baseball"), f"{name}: 종목이 없다"
        assert spec.get("condition", "").strip(), f"{name}: 조건이 없다"
        if spec.get("scores"):
            continue
        assert spec.get("reuse_yesterday") or spec.get("opponent_wins"), \
            f"{name}: 스코어가 비었는데 왜인지 적히지 않았다 — 조용한 0 금지"


def test_교차_규칙_여섯_개가_실패_사례를_들고_있다():
    """🔴 §5-c — *"반드시 적용, 09-28~29 실패에서 나온 것."* [§5-c]

    ⚠️ 규칙마다 **어느 경기에서 놓쳤나**가 적혀야 한다. 그것이 없으면 다음 세션이
       "왜 이 규칙이 있나"를 모르고 지운다.
    """
    rs = R.cross_rules()
    assert len(rs) == 6, f"§5-c 는 교차 규칙 6개다 ({len(rs)}개)"
    # 🔴 **`R` 을 쓰지 않는다** — v4 는 `R1~R12` 를 §7 규칙 12개에 쓴다.
    assert [r["id"] for r in rs] == [f"5c-{i}" for i in range(1, 7)]
    assert not any(str(r["id"]).startswith("R") for r in rs), \
        "§5-c 규칙에 R 접두를 붙이면 §7 의 이름 공간을 덮는다"
    for r in rs:
        for key in ("name", "when", "then", "miss"):
            assert str(r.get(key, "")).strip(), f"{r['id']}: {key} 가 비었다"


def test_교차_규칙이_v4_5c_의_실패_경기를_가리킨다():
    """🔴 사본이 낡지 않게 — v4 §5-c 본문에 적힌 경기 이름이 yaml 에도 있나. [§5-c]

    ⚠️ 규칙 번호만 맞추면 내용이 딴 것으로 바뀌어도 초록이다.
    """
    body = _section("## 5. 시나리오 생성 규칙표", "## 6.")
    misses = " ".join(str(r["miss"]) for r in R.cross_rules())
    for team in ("아르메니아", "르방컵", "레온", "세이부", "돗토리"):
        assert team in body, f"v4 §5-c 에 {team} 이 없다 — 절을 잘못 잘랐다"
        assert team in misses, f"yaml 의 실패 사례에 {team} 이 빠졌다"


# ══════════════════════════════════════════════════════════════════
# 방향은 **스코어에서 계산한다** (§4 · §3 STEP 5)
# ══════════════════════════════════════════════════════════════════

def test_템플릿_표에_direction_칸이_없다():
    """🔴 §4 — *"총점 방향은 스코어 기반이라 STEP 5 에서 계산한다."*

    표에 또 적으면 두 값이 갈리고, 갈리면 어느 쪽이 맞는지 아무도 모른다. [§4]
    """
    for name, spec in R.templates().items():
        assert "direction" not in spec, \
            f"{name}: 방향을 표에 적었다 — 스코어에서 계산해야 한다"


def test_스코어에서_방향을_계산한다():
    """🔴 §5-b 스코어는 **홈-원정** 순이다. [§4 · §5-b]"""
    assert R.direction_of(["2-1", "1-0"]) == "home"
    assert R.direction_of(["0-1", "1-2"]) == "away"
    assert R.direction_of(["0-0", "1-1"]) == "draw"
    # 🔴 난타전은 결과가 섞인다 — 승패 방향이 없다(총점 마켓으로 본다)
    assert R.direction_of(["2-2", "2-3", "3-2"]) is None
    # 🔴 못 읽는 스코어는 0 으로 때우지 않는다 — "0-0" 과 "못 읽었다"는 다르다
    assert R.direction_of(["전날 스코어"]) is None
    assert R.direction_of([]) is None
    assert R.parse_score("2-1") == (2, 1)
    assert R.parse_score("망가진") is None
    assert R.parse_score("1-2-3") is None


def test_v4_의_템플릿_스코어가_그_조건과_맞는다():
    """🔴 **표와 계산이 어긋나지 않나** — yaml 의 스코어가 조건대로 방향을 내나.

    ⚠️ 이것이 §5-b 표를 실제로 검산하는 유일한 계약이다. 조건 글에 "홈 승"이라
       적혀 있는데 스코어가 원정 승이면 여기가 빨개진다. [§5-b]
    """
    want = {"soccer_home_normal": "home", "soccer_home_dominant": "home",
            "soccer_away_normal": "away", "soccer_lock": "draw"}
    for name, direction in want.items():
        got = R.direction_of(R.templates()[name]["scores"])
        assert got == direction, f"{name}: 스코어가 {got} 방향이다 (조건은 {direction})"
    # 난타전·슬러그페스트는 총점 시나리오다 — 승패 방향이 하나로 모이지 않는다
    assert R.direction_of(R.templates()["soccer_open"]["scores"]) is None


def test_모든_시나리오가_한_방향이면_실패다():
    """🔴 §3 STEP 5 · §5-c-6 — *"반대 방향 시나리오 최소 1개."* [§3 · §5-c]"""
    assert R.all_one_direction([["2-1"], ["1-0", "3-0"]]) is True
    assert R.all_one_direction([["2-1"], ["0-1"]]) is False
    assert R.all_one_direction([["2-1"], ["0-0"]]) is False
    # 🔴 난타전이 끼면 "전부 한 방향"이 아니다 — 이미 반대 결과를 품는다
    assert R.all_one_direction([["2-1"], ["2-2", "2-3"]]) is False
    assert R.all_one_direction([]) is False


def test_2골차_패_시나리오는_근거가_없어도_없애지_않는다():
    """🔴 §5-c-5 — *"근거 변수가 없으면 strength 0.3 으로 두되 없애지 않는다."*

    09-29 돗토리·후쿠시마 +1.5 가 이 시나리오를 빠뜨렸다가 1.0→0.85 로 내려갔다.
    ⚠️ 함수 이름에서 `R5` 를 뺐다 — **정본에서 이 규칙은 §7 `R6` 이다**(§5-c 안의
       번호는 5 다). `R` 을 §5-c 번호로 쓰면 읽는 사람이 §7 과 헷갈린다. [§5-c · §7]
    """
    rule = R.by_sec7_rule("R6")
    assert rule is not None and rule["id"] == "5c-5"
    assert rule["floor_strength"] == 0.3
    assert "0-2" in rule["then"], "2골 차 스코어가 규칙에 없다"


def test_축구_무승부는_바닥값을_갖는다():
    """🔴 §5-a — *"축구는 C 가 비어도 최소 strength 0.4 로 생성 — 무승부는 항상
    살아 있는 결과."* [§5-a]
    """
    from app.rules import _load
    assert _load(R.SCENARIO_RULES)["base"]["soccer_draw_floor"] == 0.4


def test_전제가_replaced_면_strength_가_0_이_된다():
    """🔴 §5-d — 전제가 틀리면 그 위 시나리오가 통째로 무효다. [§5-d]"""
    from app.rules import _load
    st = _load(R.SCENARIO_RULES)["strength"]
    assert st["sum_of"] == "variable_weight"
    assert st["premise_replaced_to_zero"] is True


def test_narrative_는_새_사실을_더할_수_없다():
    """🔴 §5-e · §14-5 — LLM L6 이 서술만 쓴다. 스코어·strength 는 코드 값. [§5-e]"""
    from app.rules import _load
    n = _load(R.SCENARIO_RULES)["narrative"]
    assert n["llm_slot"] == "L6"
    assert n["may_add_facts"] is False
    assert n["sentences"] == [2, 3]


# ══════════════════════════════════════════════════════════════════
# 배선 — 🔴 만든 것은 부르는 곳이 있어야 한다
# ══════════════════════════════════════════════════════════════════



def test_단계2_계약마다_v4_조항이_적혀_있다():
    """🔴 **#13** — 계약 독스트링에 근거 조항을 붙인다. 없으면 `[infra]`.

    ⚠️ **손으로 챙기면 다음에 또 빠진다.** 실측 2026-09-30: 단계 2 계약 4건에
       조항이 없었고 기계로 재서야 보였다. 그래서 이 계약이 **단계 2 디렉터리
       전체를 훑는다** — 새 계약을 조항 없이 넣으면 그 자리에서 빨개진다. [#13]
    """
    import ast

    clause = re.compile(r"§\s*\d|\[infra\]|#\d+|v3 §")
    missing: list[str] = []
    for f in sorted((ROOT / "tests" / "stage2").glob("test_*.py")):
        for node in ast.parse(f.read_text(encoding="utf-8")).body:
            if (isinstance(node, ast.FunctionDef)
                    and node.name.startswith("test_")
                    and not clause.search(ast.get_docstring(node) or "")):
                missing.append(f"{f.name}::{node.name}")
    assert missing == [], f"v4 조항이 안 적힌 계약: {missing}"


def test_단계_6_이_지목한_7절_규칙에_닿는다():
    """🔴 **§9 단계 6 완료 조건** — *"§5 규칙표 구현, 교차 규칙 **R3·R6** 포함."*

    그 `R3`·`R6` 은 **§7 규칙 12개**의 번호다(§5-c 자체는 번호만 1~6 이다).
    ⚠️ 종전 판이 §5-c 규칙에 `R1~R6` 을 붙여 **정본의 이름 공간을 덮었다** —
       단계 6 이 `R3` 을 찾으면 `저득점 생성`(엉뚱한 규칙)을 집었다. 실측
       2026-09-30 에 리뷰어가 B1 로 잡았다.
    🔴 이 계약은 **v4 §7 표에서 자란다** — 번호와 규칙 글을 파싱해, 그 규칙을
       이행하는 §5-c 항목이 실제로 붙어 있는지 본다. [§9 · §7 · §5-c]
    """
    sec7 = _section("## 7. 이번 주 실전에서 확정된 규칙 12개", "## 8.")
    table = dict(re.findall(r"^\|\s*(R\d+)\s*\|\s*([^|]+?)\s*\|", sec7, re.M))
    assert len(table) == 12, f"§7 은 규칙 12개다 ({len(table)}개를 읽었다)"

    # §9 단계 6 이 이름 댄 둘
    stage6 = _section("## 9. 단계별", "## 10.")
    named = re.findall(r"교차 규칙 (R\d+)·(R\d+)", stage6)
    assert named, "§9 단계 6 이 교차 규칙을 지목한 줄을 못 찾았다"
    for rule in named[0]:
        got = R.by_sec7_rule(rule)
        assert got is not None, f"§9 단계 6 이 지목한 {rule} 에 닿는 §5-c 규칙이 없다"
        # 🔴 **내용이 맞나** — 번호만 맞추면 딴 규칙이 붙어도 초록이다
        want = table[rule]
        key = "난타전" if "난타전" in want else "2골" if "2골" in want else None
        assert key and (key in got["name"] or key in str(got["then"])), \
            (f"{rule}({want}) 에 붙은 §5-c 규칙이 딴 것이다: "
             f"{got['id']} {got['name']}")


# ══════════════════════════════════════════════════════════════════
# 🔴 사용자 지시 2026-10-02 로 고친 두 규칙 — 되돌아가지 않게 잠근다
# ══════════════════════════════════════════════════════════════════
#
# > 4,5 수정해라 … 모르면 딥서치해서 수정해라
#
# 손으로 네 경기를 돌려 찾은 결함이다.
#   ④ `5c-1` 난타전이 `lineup_intent` 없이는 **세 경기 연속 미발동**
#   ⑤ §6-c-3 기준선이 **순환** — 언더가 정의상 1.00


def test_5c1_에_리그평균_기준_OR_조건이_있다():
    """★ 🔴 §5-c-1 이 감독 인용 없이도 난타전을 만들 수 있어야 한다.

    실측 2026-10-02 — 자료가 난타전을 가리키는데 규칙이 안 받았다:
    키프로스–아르메니아 맞대결 평균 4.5 · 시애틀–KC 의 KC 최근 5경기 평균 4.6.
    ⚠️ §10 정답지의 **유일한 ✘ 사례**가 *"난타전 D 미생성"* 이다.

    🔴 사용자 지시 2026-10-02 로 고친 규칙이다. [§5-c · §7]
    """
    r = next(x for x in R.cross_rules() if x["id"] == "5c-1")
    ors = r.get("or_when") or []
    assert len(ors) >= 2, f"`5c-1` 에 OR 조건이 {len(ors)}개다"
    blob = " ".join(str(x) for x in ors)
    assert "h2h_pattern" in blob and "recent_pattern" in blob, blob
    # 🔴 **리그 평균 기준이어야 한다** — 절대 숫자는 리그마다 틀린다
    assert "리그 평균" in blob, "문턱이 리그 평균 기준이 아니다"
    assert isinstance(r.get("league_avg_margin"), (int, float)), \
        "여유 값이 숫자로 선언돼 있지 않다"
    assert r.get("league_avg_source"), "리그 평균을 어디서 구하는지 안 적혀 있다"
    assert r.get("league_avg_scope"), "어느 범위로 세는지 안 적혀 있다"


def test_절대_숫자_문턱을_쓰지_않는다():
    """★ 🔴 **딥서치가 첫 제안을 무너뜨렸다.** 실측 리그 평균:

    ```
    MLS 3.22 · USL Championship 2.73 · UEFA NL C 2그룹 2.50
    ```

    처음 제안한 *"평균 총득점 ≥ 3.0"* 은 **MLS 에서 평균 이하 경기에도 발동한다.**
    리그가 0.7골 차로 갈리므로 절대 숫자는 어느 리그에서든 틀린다.

    🔴 사용자 지시 2026-10-02 로 고친 규칙이다. [§5-c]
    """
    r = next(x for x in R.cross_rules() if x["id"] == "5c-1")
    blob = " ".join(str(x) for x in (r.get("or_when") or []))
    # 🔴 OR 조건 문장에 **고정 골 수**가 박혀 있으면 실패
    assert not re.search(r"≥\s*[0-9]+(\.[0-9]+)?\s*골", blob), \
        f"절대 골 수가 문턱에 박혀 있다: {blob}"
    # 🔴 리그 평균을 못 구하면 **발동하지 않는다** — 절대 숫자로 때우지 않는다
    assert "발동하지 않는다" in str(r.get("no_league_avg") or ""), \
        "리그 평균이 없을 때의 처리가 없다(친선·A매치)"


def test_보드_없는_총점_기준선이_순환이_아니다():
    """★ 🔴 v4 §6-c-3 원문은 *"시나리오 스코어 **최대합 + 0.5**"* 다 — **순환이다.**

    기준선을 우리 시나리오에서 뽑으면 어떤 시나리오도 넘을 수 없고 **언더가
    정의상 1.00** 이 된다. 실측 2026-10-02(시애틀–캔자스시티):

    ```
    고치기 전  시나리오 최대합 3 → 기준선 3.5 → 언더 3.5 **1.00 "낸다"**
    같은 시나리오를 실제 보드 줄에: 언더 2.5 0.55 · 언더 3.0 0.55
    고친 뒤    리그 평균 3.22 → 기준선 3.5 → 언더 3.5 **0.96 "소액"**
    ```

    🔴 사용자 지시 2026-10-02 로 고친 규칙이다. [§6-c · §6-f]
    """
    cfg = R._load("config/scenario_rules.yaml").get("total_baseline_no_board")
    assert cfg, "보드 없는 기준선 규칙이 없다"
    assert "리그 평균" in str(cfg.get("source") or ""), \
        f"기준선을 자료에서 뽑지 않는다: {cfg.get('source')}"
    # 🔴 **순환 식을 금지로 박아 둔다** — 되돌아가면 여기가 빨개진다
    assert "최대합" in str(cfg.get("forbidden") or ""), \
        "순환 식(시나리오 최대합 + 0.5)이 금지로 적혀 있지 않다"
    assert cfg.get("round_to") == 0.5 and cfg.get("only_half_lines") is True
    # 🔴 리그 평균이 없으면 **이름을 적지 않는다** — 지어낸 기준선으로 등급 금지
    assert "이름" in str(cfg.get("no_league_avg") or ""), \
        "리그 평균을 못 구할 때의 처리가 없다"


def test_5c1_시나리오_strength_가_선언돼_있다():
    """🔴 고치다 **새 결함을 찾았다** — `5c-1` 이 만든 시나리오의 strength 를
    규칙이 정하지 않는다.

    §5-d 는 *"strength = 소속 변수 weight 합"* 인데, 난타전을 띄우는 근거(평균
    총득점)는 **총점 패턴이라 방향이 없어 배경**이고 배경에는 weight 가 없다.
    ⚠️ 문서의 유일한 선례가 §5-c-5 의 `floor_strength: 0.3` 이다. 그것을 쓰되
       **사용자 결정 대기임을 표시**한다 — 조용히 지어낸 값으로 두지 않는다.

    🔴 고치다 발견한 새 결함이다. [§5-c · §5-d]
    """
    cfg = (R._load("config/scenario_rules.yaml")
           .get("cross_rule_strength") or {}).get("5c-1")
    assert cfg, "`5c-1` 시나리오 strength 가 선언돼 있지 않다"
    # 🔴 **지어낸 값이 아니라 §5-d 에서 나와야 한다** — 사용자 지시 2026-10-02.
    #    종전 판은 §5-c-5 의 바닥값 0.3 을 빌려 썼고 그것은 고른 값이었다.
    assert "weight 합" in str(cfg.get("strength") or ""), \
        f"strength 가 §5-d(weight 합)에서 나오지 않는다: {cfg.get('strength')}"
    assert "5-d" in str(cfg.get("strength") or "")
    # 🔴 바닥값은 **남기되 조건을 밝힌다** — 0 이 되면 시나리오가 사라진다(§5-c-5)
    assert isinstance(cfg.get("floor_strength"), (int, float))
    assert cfg.get("floor_when"), "바닥값을 언제 쓰는지 안 적혀 있다"
    assert cfg.get("user_decision_pending") is None, \
        "결정이 끝났는데 대기 표시가 남아 있다"
