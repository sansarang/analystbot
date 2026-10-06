"""v4 §4 유형표 · §5 규칙표를 읽는다 — `config/*.yaml` 이 원본이다.

🔴 **표를 코드에 베끼지 않는다.** 유형 13종·템플릿 9개·교차 규칙 6개는
   `config/variable_types.yaml`·`config/scenario_rules.yaml` 에 있고, 그 파일들이
   v4 §4·§5 의 구현이다. 계약(`tests/stage2/test_rules.py`)이 v4 표를 파싱해
   **yaml 이 빠뜨린 항목을 찾아낸다.**

🔴 **방향은 스코어에서 계산한다.** v4 §4: *"총점 방향은 스코어 기반이라 STEP 5
   에서 시나리오 스코어로부터 계산하고 변수엔 붙이지 않는다."* 그래서
   `direction_of()` 가 있고, 템플릿 표에는 `direction` 칸이 **없다** — 두 곳에
   적으면 갈리고, 갈리면 어느 쪽이 맞는지 아무도 모른다.
"""
from __future__ import annotations

import functools
import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
VARIABLE_TYPES = "config/variable_types.yaml"
SCENARIO_RULES = "config/scenario_rules.yaml"
#: 🔴 **리그 규정** — 플레이오프 경계와 무승부 가능 여부. 우리 자료에 **없는** 사실이다
#   (사용자 지시 2026-10-02). ⚠️ 자료가 알려 주는 리그(축구 fotmob `legend`)의 경계는
#   여기 적지 않는다 — 적으면 사본이 된다.
LEAGUE_RULES = "config/league_rules.yaml"
#: 🔴 **검색 라우팅** — 어느 엔진에 묻고 어느 페이지를 먼저 여나(실측 2026-10-02).
SEARCH_ROUTING = "config/search_routing.yaml"
#: 🔴 **현지 낱말표** — 사다리의 `{local_word_*}` 자리(사용자 기술 지시 2026-10-03).
SEARCH_WORDS = "config/search_words.yaml"
#: 🔴🔴 **v5 §6-2 — 시나리오 세트 자동 보강표.** 거짓 1.0 을 막는 자리다.
SCENARIO_REQUIRED = "config/scenario_required.yaml"
#: 🔴🔴 **v5 §7-2 — 유형마다 명단에서 확인할 기계 조건.**
TRIGGER_CONDITIONS = "config/trigger_conditions.yaml"
#: 🔴🔴 **v5 §10-4 — 단계 게이트.** 🔴 서명은 사용자다(내가 통과를 안 적는다).
STAGE_GATES = "config/stage_gates.yaml"


@functools.lru_cache(maxsize=None)
def _load(rel: str) -> dict:
    return yaml.safe_load((ROOT / rel).read_text(encoding="utf-8"))


def variable_types() -> dict[str, dict]:
    """§4 유형표. 키가 `Variable.type` 의 값 집합이다."""
    return _load(VARIABLE_TYPES)["types"]


def added_types() -> list[dict]:
    """🔴 **사용자 지시로 §4 표에 더한 유형.** 근거 문서까지 들고 있다.

    ⚠️ 유형을 조용히 더하면 §4 표와 yaml 이 갈린다. 계약이 이 목록만 여분으로
       허용하고, 각 항목의 `doc` 파일이 실재하는지까지 본다.
    """
    return list(_load(VARIABLE_TYPES).get("added_by_user_instruction") or [])


def catalog_policy() -> dict:
    """🔴 ② 재검색 루프의 **각도 상한**. 없으면 터진다 — 조용히 기본값을 쓰지 않는다.

    ⚠️ 숫자는 **실제 테스트로 정한다**(사용자 지시 2026-10-02). yaml 이 그것을 적어 둔다.
    """
    got = _load(VARIABLE_TYPES).get("catalog_policy")
    if not got or got.get("max_angles") is None:
        raise KeyError("variable_types.yaml 에 `catalog_policy.max_angles` 가 없다")
    return dict(got)


def types_for_sport(sport: str) -> list[str]:
    """🔴🔴 **그 종목의 유형만**(사용자 지시 2026-10-06 ③).

    > 카탈로그에 `sports: [soccer|baseball|basketball|…]` 선언을 추가하고, 요청마다
    > 그 종목 유형만 enum 에 넣는다.

    ⚠️ 실측 2026-10-06: 축구 경기 enum 에 `pitcher_state`(야구)가 있어 피로 기사가
       그 유형으로 붙고 방향이 **자기 쪽**이 됐다.
    🔴 선언이 **없는 유형은 넣지 않는다** — 빠뜨린 것을 조용히 통과시키면 그 유형이
       모든 종목에 다시 새어 든다(#3). 계약이 선언을 강제한다.
    """
    said = str(sport or "").strip()
    out: list[str] = []
    for name, spec in sorted(variable_types().items()):
        got = [str(x) for x in (spec.get("sports") or [])]
        if said and said in got:
            out.append(name)
    return out


def sport_words(sport: str) -> list[str]:
    """🔴 그 종목을 가리키는 **모든 언어의 낱말**(`search_words.yaml`).

    사용자 지시 2026-10-06 ②: *"`Doc` 단계에서 그 종목 낱말(축구/football/fútbol 등,
    `search_words.yaml`)이 본문에 없으면 버린다."*
    """
    box = (_load(SEARCH_WORDS).get("words") or {}).get("sport") or {}
    got = box.get(str(sport or "").strip()) or {}
    out: list[str] = []
    for words in got.values():
        out += [str(w) for w in (words or [])]
    return sorted(set(out))


def local_words(concept: str, lang: str) -> list[str]:
    """🔴 그 개념의 **그 언어 낱말들**. 없으면 빈 목록(그 단은 안 던진다).

    ⚠️ 유형 → 개념은 `variable_types.yaml` 의 `word:` 가 가리킨다 — 유형마다
       언어마다 템플릿을 적으면 **곱셈으로 늘어난다**(유형 19 × 언어 5).
    """
    box = (_load(SEARCH_WORDS).get("words") or {}).get(str(concept or "")) or {}
    return [str(x) for x in (box.get(str(lang or "")) or []) if str(x).strip()]




def sport_word(sport: str, lang: str) -> str:
    """🔴🔴 그 **종목의 그 언어 낱말** 하나(`soccer`+`en` → `football`).

    사용자 수정 ① (2026-10-04): *"검색어 ... {종목 낱말} ... 종목 낱말은 어댑터
    `SPORT` 에서."*

    ⚠️ `local_words` 를 못 쓴다 — 종목 낱말은 **두 단**(`sport → 종목 → 언어`)이다.
    🔴 그 언어에 없으면 **영어**로 떨어진다. ⚠️ 영어에도 없으면 **빈 문자열**이고,
       호출부는 그 자리를 비운다(지어내지 않는다 — `football` 을 아무 언어 질의에
       붙이면 그 질의가 죽는다).
    """
    box = ((_load(SEARCH_WORDS).get("words") or {}).get("sport") or {})
    got = box.get(str(sport or "")) or {}
    for key in (str(lang or ""), "en"):
        vals = [str(x) for x in (got.get(key) or []) if str(x).strip()]
        if vals:
            return vals[0]
    return ""


def word_concept(vtype: str) -> str:
    """🔴 그 §4 유형이 가리키는 **낱말 개념**. 없으면 빈 문자열."""
    return str((variable_types().get(str(vtype or "").strip()) or {})
               .get("word") or "")


def search_routing() -> dict:
    """🔴 검색 라우팅 표. 원본은 `config/search_routing.yaml` 이다."""
    return _load(SEARCH_ROUTING)


def news_engines() -> list[str]:
    """🔴 **산문 질문에 먼저 쓸 엔진.** 비면 지정하지 않는다(엔진 전부).

    ⚠️ 실측 2026-10-02: 지정 없이 쏘면 질의를 무시하는 엔진의 결과가 섞여 들어와
       **열기 예산을 전철 PDF·티켓 페이지에 태운다.** `google news` 로 지정하니
       사람이 읽은 기사가 그대로 나왔다(4개 질의 4/4).
    """
    return [str(x) for x in (search_routing().get("news_engines") or [])]


def tier_of_host(url: str, default: int) -> tuple[int, str]:
    """🔴🔴 **호스트로 출처 층을 매긴다**(사용자 기술 지시 2026-10-03 · 기술 5).

    > 협회·구단 공식 > 전국지 > 현지지 > 통신 재전재 > **베팅 팁 사이트**

    ⚠️ 층 상수는 전부터 있었는데 **소스가 선언한 층**을 그대로 썼다 — 즉 검색으로
       나온 기사는 전부 같은 층이었고 **인도네시아 팁 사이트와 전국지가 구분되지
       않았다**(실측 2026-10-03).
    🔴 표에 없는 호스트는 **`default`(그 소스가 선언한 층)로 간다** — 모르는 것을
       최하로 떨어뜨리면 멀쩡한 현지지가 죽는다.
    ⚠️ 번호는 `app/verify.py` 가 원본이다 — 여기서 숫자를 적지 않는다.
    """
    from app import verify
    u = str(url or "").lower()
    box = search_routing().get("source_tiers") or {}
    order = (("official", verify.TIER_OFFICIAL), ("primary", verify.TIER_PRIMARY),
             ("preview", verify.TIER_PREVIEW), ("forecast", verify.TIER_FORECAST))
    # 🔴 **팁·예측을 먼저 본다** — 그 호스트가 다른 목록에도 걸리면 **최하가 이긴다**
    #    (팁 사이트가 전국지 도메인을 흉내 내는 자리를 막는다).
    for name, tier in reversed(order):
        for pat in (box.get(name) or []):
            if str(pat).lower() in u:
                return tier, f"출처 등급 `{name}`({pat})"
    return default, "출처 등급표에 없다 — 소스가 선언한 층을 쓴다"


def banned_host(url: str) -> str:
    """🔴🔴 **이 주소를 열면 안 되나.** 막히면 **사유**를, 아니면 빈 문자열.

    절대규칙 6: *"배당은 `research` 스키마에만. **판정 경로·카드 렌더러 접근 0건**."*

    ⚠️ 실측 2026-10-03(LG 트윈스 vs 기아 타이거즈): `intent` 세포가
       `888starz.bet/…/lg-twins-kia-tigers` 를 **열었다**. 북메이커 경기 페이지다.
    🔴 `late_hosts`(뒤로 미룸)로는 못 막는다 — 예산이 남으면 결국 연다.
       배당은 **닿지 않아야** 한다.
    🔴 사유를 돌려주는 까닭: 조용히 지우면 *"왜 안 열었나"* 를 되짚을 수 없다(#3).
    """
    u = str(url or "").lower()
    for pat in (search_routing().get("banned_hosts") or []):
        if str(pat).lower() in u:
            return (f"배당 호스트라 **열지 않는다**(`{pat}`) — "
                    f"절대규칙 6: 판정 경로에 배당 접근 0건")
    return ""


def not_sport_host(url: str) -> str:
    """🔴🔴 **스포츠가 아닌 호스트인가.** 막히면 사유, 아니면 빈 문자열.

    사용자 수정 ③ (2026-10-04): *"도메인 등급표 — 스포츠 매체·협회·구단 공식만
    본문을 받는다. rottentomatoes·tripadvisor·법률·SMS 류는 거부 목록."*

    ⚠️ `late_hosts`(뒤로 미룸)와 **다르다** — 열기 예산이 20이면 미룬 것도 결국
       연다. 실측 2026-10-04 에 그래서 76건이 열렸고 LLM 예산이 다 탔다.
    🔴 원본은 `config/search_routing.yaml` 의 `not_sport_hosts` 다 — 목록을 여기
       적지 않는다(사본 금지).
    """
    u = str(url or "").lower()
    for pat in (search_routing().get("not_sport_hosts") or []):
        if str(pat).lower() in u:
            return (f"**스포츠 호스트가 아니다**(`{pat}`) — 열지 않는다 "
                    f"(사용자 수정 ③ 2026-10-04)")
    return ""


def other_sport(url: str, sport: str, *, title: str = "") -> str:
    """🔴🔴 **그 경기 종목이 아닌 페이지인가.** 막히면 사유, 아니면 빈 문자열.

    사용자 수정 ③: *"스포츠 도메인이라도 종목이 다르면(rugby.com.au) 제목에
    football/soccer 가 없으면 버린다."*

    ⚠️ 종목을 **모르면 막지 않는다** — `queries.asks` 와 같은 처분이다(모른다고
       전부 거부하면 새 종목이 아무것도 못 묻는다).
    🔴 **그 경기 종목의 낱말이 함께 있으면 버리지 않는다** — 종합 매체는 한 기사에
       `football` 과 `rugby` 를 같이 적는다. 그때 버리면 옳은 기사를 잃는다.
    """
    sp = str(sport or "").strip()
    if not sp:
        return ""
    words = [str(x).lower() for x in
             ((search_routing().get("other_sport_words") or {}).get(sp) or [])]
    if not words:
        return ""
    blob = f"{url} {title}".lower()
    hit = next((w for w in words if w in blob), "")
    if not hit:
        return ""
    # 🔴 우리 종목 낱말이 **함께** 있으면 그 기사는 우리 것도 말한다
    mine = [v.lower() for box in
            (((_load(SEARCH_WORDS).get("words") or {}).get("sport") or {})
             .get(sp) or {}).values() for v in (box or [])]
    if any(w and w in blob for w in mine):
        return ""
    return (f"**다른 종목이다**(`{hit}` 가 있고 `{sp}` 낱말은 없다) — "
            f"열지 않는다 (사용자 수정 ③ 2026-10-04)")


def host_rank(url: str) -> int:
    """🔴 **먼저 열 페이지인가.** 작을수록 먼저 — `0` 기사 · `1` 보통 · `2` 뒤로.

    ⚠️ 예산이 2~3건이므로 **순서가 결과를 정한다.** 실측 2026-10-02: 25건 중
       구단 홈 첫 화면·티켓·전철 PDF 를 먼저 열어 기사에 닿지 못했다.
    🔴 호스트와 **경로를 함께** 본다 — `npb.jp` 는 기사 호스트인데
       `/junior/2020/roster_h.html`(유소년 명단)이 열렸다.
    """
    u = str(url or "").lower()
    cfg = search_routing()
    # 🔴🔴 **첫 화면은 뒤로 미룬다** — 기사가 아니다.
    #
    #  ⚠️ 실측 2026-10-02 에서 가장 많이 열린 페이지가 `marines.co.jp/` **루트**였다
    #     (15회). 구단 홈 첫 화면에는 그날의 타순도 감독 발언도 없다. 호스트는
    #     기사 호스트와 같으므로 **경로로만** 가를 수 있다.
    path = u.split("://", 1)[-1]
    path = path[path.find("/"):] if "/" in path else "/"
    if path.split("?")[0].strip("/") == "":
        return 2
    for bad in (cfg.get("late_paths") or []):
        if str(bad).lower() in u:
            return 2
    for bad in (cfg.get("late_hosts") or []):
        if str(bad).lower() in u:
            return 2
    for good in (cfg.get("article_hosts") or []):
        if str(good).lower() in u:
            return 0
    return 1


# 🔴 **`type_templates`(문자열 목록)는 지웠다.** 템플릿은 이제 언어 꼬리표를 들고
#    다니고(`type_templates_tagged`), 꼬리표를 떼어 버리는 접근자를 남겨 두면 누군가
#    그것을 써서 **한국어 낱말을 일본어 질의에 섞는 그 버그를 되살린다**.
#    ⚠️ 실측 2026-10-02 가 바로 그 버그였다(`福岡ソフトバンクホークス 자선 경기`).
def type_templates_tagged(vtype: str) -> list[tuple[str, str]]:
    """🔴 템플릿 + **그 템플릿의 언어**. `(본문, 언어)` — 언어가 `""` 면 아무 언어나.

    ══════════════════════════════════════════════════════════════════
    🔴 왜 꼬리표가 필요한가 — 실측 2026-10-02 가 요구했다
    ══════════════════════════════════════════════════════════════════

    종전에는 템플릿이 그냥 문자열이었고, `catalog_variants` 가 **모든 언어로**
    같은 문자열을 던졌다. 그래서 NPB 경기에 이런 질의가 나갔다:

        福岡ソフトバンクホークス 자선 경기 10月2日
        福岡ソフトバンクホークス 수비 결장 Oct 2
        福岡ソフトバンクホークス 로테이션 10月2日

    🔴 일본어 기사에 *"자선 경기"* 라는 글자는 없다. 팀명은 일본어인데 **낱말이
       한국어**였다 — 그 질의는 구조적으로 0건이다.
    ⚠️ 낱말을 코드가 번역하지 않는다(번역기는 유료고 품질도 못 믿는다). yaml 이
       **언어마다 따로** 적고, 코드는 그 언어의 질의에만 쓴다.
    """
    got = (variable_types().get(str(vtype or "").strip()) or {}).get("templates")
    out: list[tuple[str, str]] = []
    for x in (got or []):
        if isinstance(x, dict):
            # 🔴 `{q: ..., lang: ja}` 꼴. `lang` 이 없으면 아무 언어나(빈 문자열)
            out.append((str(x.get("q") or ""), str(x.get("lang") or "")))
        else:
            out.append((str(x), ""))
    return [(q, lang) for q, lang in out if q]


def attaches_to(vtype: str) -> str:
    """🔴 그 변수가 **어느 시나리오에 붙나**(사용자 설계의 *"작동"*).

    `5c-1` 꼴이면 교차 규칙, `both`·`fold_win_markets`·`invalidate_recent_form` 은
    규칙 이름이다. ⚠️ 없으면 빈 문자열 — 방향 묶음에만 들어간다(§5-a 기본).
    """
    return str((variable_types().get(str(vtype or "").strip()) or {})
               .get("attaches_to") or "")


def premise_types() -> list[str]:
    """§4 — 기본 `is_premise=true` 인 유형. 틀리면 시나리오가 통째로 무효다."""
    return _load(VARIABLE_TYPES)["premise_types"]


def templates() -> dict[str, dict]:
    """§5-b 스코어 집합 배정 표."""
    return _load(SCENARIO_RULES)["templates"]


def required_forms() -> dict[str, dict]:
    """🔴🔴 **§6-2 필수형 표**(여섯 줄). 🔴 코드에 박지 않는다.

    ⚠️ `on_missing` 이 `추가` 면 코드가 템플릿으로 만들어 넣고, `실패` 면 그
       경기는 `scenario_incomplete` 다 — 두 값뿐이고 그 검사는 계약이 한다.
    """
    got = _load(SCENARIO_REQUIRED).get("forms")
    if not got:
        raise KeyError("`scenario_required.forms` 가 없다 — §6-2 표가 원본이다")
    return {str(k): dict(v or {}) for k, v in got.items()}




def llm_budget() -> dict:
    """🔴 §2 — LLM 예산(`config/llm.yaml`). 🔴 수는 **거기** 하나다.

    ⚠️ `app/solar.py` 가 같은 파일을 읽는다 — 이 함수는 **게이트 계약**이
       그 수를 대조하기 위한 창이다(두 곳이 갈리면 하나가 거짓이다).
    """
    from app import solar
    got = dict(solar.cfg().get("budget") or {})
    if "per_day_usd" not in got:
        raise KeyError("`llm.yaml` 의 `budget.per_day_usd` 가 없다(§2)")
    return got








def trigger_checks() -> dict[str, str]:
    """🔴🔴 **§7-2 — 유형 → 기계 조건 꼴.** 🔴 코드에 박지 않는다.

    ⚠️ `{…}` 는 빈 자리다 — 그 경기의 자료가 채운다(`check_for`).
    """
    got = _load(TRIGGER_CONDITIONS).get("checks")
    if not got:
        raise KeyError("`trigger_conditions.checks` 가 없다 — §7-2 표가 원본이다")
    return {str(k): str(v) for k, v in got.items()}


def v5_names() -> dict[str, str]:
    """🔴 **지시문 이름 → 우리 §4 이름.** ⚠️ 적지 않으면 그 줄이 조용히 죽는다.

    실측 2026-10-04: v5 가 `coach_crisis`·`lineup_rotation`·`regression`·
    `tactical_matchup` 을 쓰는데 §4 표에 **그 이름이 없다**.
    """
    return {str(k): str(v) for k, v in
            (_load(TRIGGER_CONDITIONS).get("v5_names") or {}).items()}






def required_min() -> int:
    """🔴 §6-2 *"시나리오는 최소 4개"*. ⚠️ 그 수를 코드에 박지 않는다."""
    got = _load(SCENARIO_REQUIRED).get("min_scenarios")
    if not isinstance(got, int) or got < 1:
        raise KeyError("`scenario_required.min_scenarios` 가 없다(§6-2)")
    return got


def required_fields() -> dict[str, str]:
    """🔴 §6-2 가 부른 이름 → **우리 `Draft` 의 칸**.

    ⚠️ 지시문은 `driver_vars`·`mechanism`·`outcomes` 라 부르고 우리는
       `variables`·`why`·`scores` 다. 🔴 그 대응을 **yaml 에 한 번** 적는다
       (§8-3 이 같은 방법을 쓴다) — 코드 두 곳에 적으면 한쪽이 늦는다.
    """
    got = _load(SCENARIO_REQUIRED).get("required_fields") or {}
    if not got:
        raise KeyError("`scenario_required.required_fields` 가 없다(§6-2)")
    return {str(k): str(v) for k, v in got.items()}


def direction_templates(sport: str) -> dict:
    """🔴 그 종목의 **방향 템플릿**(home·away·draw). 없으면 `{}`.

    ⚠️ 실측 2026-10-02: `_base` 가 `soccer_home_normal` 을 **이름으로 박아** 써서
       야구 경기에 축구 스코어(2-1·1-0)가 나갔다. 종목을 표가 정하게 한다.
    """
    got = _load(SCENARIO_RULES).get("direction_templates") or {}
    return dict(got.get(str(sport or "").strip()) or {})


def cross_rules() -> list[dict]:
    """§5-c 교차 규칙. 🔴 09-28~29 실패에서 나온 것 — 반드시 적용한다.

    ⚠️ id 는 `5c-1`~`5c-6` 이다. **`R` 은 §7 것이다** — v4 가 `R1~R12` 를 §7
       규칙 12개에 쓰고, §9 단계 6 이 그 번호로 `R3`·`R6` 을 지목한다.
       §7 에 짝이 있는 규칙은 `sec7_rule` 로 병기했다 → `by_sec7_rule()`.
    """
    return _load(SCENARIO_RULES)["cross_rules"]


def cross_rule(rule_id: str) -> dict:
    """§5-c 교차 규칙 하나. 🔴 없으면 터진다 — 조용히 빈 dict 를 주지 않는다."""
    for r in cross_rules():
        if str(r.get("id")) == rule_id:
            return r
    raise KeyError(f"§5-c 에 {rule_id} 가 없다")


def derived_shape() -> dict:
    """§5-b 템플릿이 **없는 종목**을 위한 모양. 🔴 **v4 표에서 읽는다.**

    ⚠️ 스코어 개수를 여기 적지 않는다 — v4 §5-b 의 축구 템플릿이 *방향마다 2개,
       난타전 3개* 를 쓰고, 그 수를 **그 표에서 세어** 쓴다. 그러면 표가 바뀌면
       파생 모양도 따라간다(사본 금지).
    """
    t = templates()
    def _n(name: str) -> int:
        got = t.get(name) or {}
        return len(got.get("scores") or [])
    direction = _n("soccer_home_normal") or _n("soccer_away_normal")
    openn = _n("soccer_open")
    if not direction or not openn:
        raise ValueError("§5-b 축구 템플릿에서 스코어 개수를 못 셌다")
    return {"direction": direction, "open": openn}


def playoff_cut(league: str) -> dict:
    """🔴 §4 `stakes` 가 묻는 **플레이오프 경계**. 리그 **규정**이 정한다.

    돌려주는 것: `{"rule":…, "division_top":…, …}` 또는 `{"unknown": 사유}`.
    ⚠️ **자료가 알려 주는 리그는 이 파일에 없다**(축구 fotmob 의 `legend`) — 적으면
       그 순간 사본이 된다. 모르는 리그는 `{}` 다.
    """
    got = league_rule(league)
    if got.get("division_top") is not None:
        return got
    unknown = (_load(LEAGUE_RULES).get("unknown_cut") or {})
    name = str(league or "").strip()
    if name in unknown:
        return {"unknown": str(unknown[name])}
    return {}


def league_rule(league: str) -> dict:
    """🔴 그 리그의 **규정** 묶음. 모르면 `{}` — 지어내지 않는다."""
    got = _load(LEAGUE_RULES).get("leagues") or {}
    return dict(got.get(str(league or "").strip()) or {})


def draw_possible(league: str) -> tuple[bool | None, str]:
    """🔴 **무승부가 최종 결과로 날 수 있나.** `(답, 사유)` — 모르면 `(None, 사유)`.

    ⚠️ 라이브 실측 2026-10-02: 격자에서 하키 시나리오를 뽑으니 무승부 `3-3` 이
       나왔다 — NHL 은 슛아웃으로 반드시 승자를 가린다. 모르는 채로 만들면 카드가
       **일어날 수 없는 결과**를 적는다.
    🔴 모르면 **만들지 않는다**(호출부가 사유를 남긴다) — 있는 척하지 않는다.
    """
    cfg = league_rule(league)
    if "draw_possible" not in cfg:
        return None, f"`{league}` 의 무승부 규정이 선언되지 않았다(config/league_rules.yaml)"
    return bool(cfg["draw_possible"]), str(cfg.get("draw_note") or "")


def neutral_venue(league: str) -> tuple[bool, str]:
    """🔴 **중립 구장 대회인가.** `(답, 사유)` — 선언이 없으면 `(False, 사유)`.

    ⚠️ 라이브 실측 2026-10-02(아시안게임, 시즈오카): 양 팀 다 홈이 아닌데 §4
       `home_field` 는 *"홈 팀 쪽"* 으로 방향을 민다 → **거짓 변수**다.
    🔴 모르면 중립이 아니라고 본다 — 리그 경기는 대개 홈/원정이 있다. 그러나 그
       판단의 **사유를 돌려준다**(조용히 가정하지 않는다).
    """
    cfg = league_rule(league)
    if cfg.get("neutral_venue"):
        return True, str(cfg.get("neutral_note") or "중립 구장 선언")
    return False, (f"`{league}` 에 중립 구장 선언이 없다 — 홈/원정이 있다고 본다"
                   if league else "리그를 모른다")


def scenario_weight() -> dict:
    """🔴 시나리오의 **무게** 규칙(사용자 지시 2026-10-02 3차 — 딥서치).

    *근거 개수는 확률이 아니다.* 무게는 포아송 스코어 격자의 확률 합이고, 격자를
    못 만들 때만 §5-d(변수 weight 합)로 내려간다.
    🔴 없으면 터진다 — 조용히 기본값을 쓰지 않는다.
    """
    got = _load(SCENARIO_RULES).get("scenario_weight")
    if not got:
        raise KeyError("scenario_rules.yaml 에 `scenario_weight` 가 없다")
    return got


def total_baseline_cfg() -> dict:
    """§6-c-3 보드 없는 총점 기준선 규칙(사용자 지시 2026-10-02 로 고쳤다)."""
    got = _load(SCENARIO_RULES).get("total_baseline_no_board")
    if not got:
        raise KeyError("`total_baseline_no_board` 가 없다")
    return got


def pick_one_cfg() -> dict:
    """🔴 **상관 추천 중 하나만 고르나**(사용자 규칙 2026-10-03). 없으면 빈 dict."""
    return dict(_load(SCENARIO_RULES).get("pick_one_when_disjoint") or {})


@functools.lru_cache(maxsize=None)
def type_patterns() -> tuple[tuple[str, tuple], ...]:
    """🔴🔴 **유형 규칙표** — 산문의 사건 낱말 → §4 유형(사용자 기술 지시 2026-10-03).

    > ② 유형 판정 (코드 규칙표) — 사건 단어 → 변수 유형. **LLM이 아니라 표로 정한다.**

    돌려주는 것: `((유형, (컴파일된 정규식, …)), …)` — **유형 이름 순서**로 고정한다.
    ⚠️ 순서가 들쭉날쭉하면 같은 글이 날마다 다른 유형이 된다(dict 순서에 기대지 않는다).
    🔴 원본은 `config/variable_types.yaml` 의 `match:` 다 — 여기서 글자를 적지 않는다.
    """
    import re as _re
    out = []
    for name in sorted(variable_types()):
        pats = (variable_types().get(name) or {}).get("match") or []
        got = []
        for raw in pats:
            try:
                got.append(_re.compile(str(raw), _re.I))
            except _re.error as exc:
                # 🔴 **조용히 빠뜨리지 않는다** — 깨진 정규식은 그 유형을 영영 0 으로
                #    만들고, 그 사실이 안 보이면 "자료가 없다"로 오진한다
                logger.warning("[rules] `%s.match` 정규식이 깨졌다: %r (%s)",
                               name, raw, exc)
        if got:
            out.append((name, tuple(got)))
    return tuple(out)


def xi_state_cap() -> dict:
    """🔴 **분석 과정 5단계** — 라인업 상태별 등급 상한(확정/예상/없음).

    사용자 분석 과정 10단계 그림 2026-10-03:

        5. 라인업 상태 → 상한   확정 1.0 / 예상 0.85 / 없음 0.8

    ⚠️ 종전은 두 칸이었다 — 라인업을 **아예 못 잡은 경기**와 **예상 XI 를 잡은
       경기**가 같은 상한을 받았다(모르는 양이 다른데).
    """
    got = dict(_load(SCENARIO_RULES).get("xi_state_cap") or {})
    if not got.get("caps"):
        raise KeyError("`xi_state_cap.caps` 가 없다")
    return got


def conclusion_cfg() -> dict:
    """🔴 **분석 과정 10단계** — *"같은 방향 3개까지, 확인 항목 첨부."*"""
    got = dict(_load(SCENARIO_RULES).get("conclusion") or {})
    if not got.get("max_same_direction"):
        raise KeyError("`conclusion.max_same_direction` 가 없다")
    return got


def common_total_lines(sport: str) -> list[float]:
    """🔴 **분석 과정 9단계** — *"보드 줄만, **없으면 일반 마켓**."*

    리그 평균을 못 구했을 때 쓰는 **관례 줄**이다. ⚠️ 우리 시나리오에서 나온 수가
    아니므로 `forbidden`(순환 식)에 해당하지 않는다 — 그 금지는 *"우리 수로 줄을
    만들지 마라"* 다.
    🔴 종목에 선언이 없으면 **빈 목록**이다 — 지어내지 않는다.
    """
    box = (total_baseline_cfg().get("common_lines") or {})
    return [float(x) for x in (box.get(str(sport or "")) or [])]


def draw_leagues(sport: str) -> list[str]:
    """🔴 v5 §6-4 — 그 종목에서 **무승부가 가능한 리그**.

    ⚠️ **빈 목록은 "리그를 가리지 않는다"** 다(축구는 늘 무승부가 있다) —
       *"무승부가 없다"* 가 아니다. 🔴 그 둘을 호출부가 가린다.
    """
    box = (total_baseline_cfg().get("draw_leagues") or {})
    return [str(x) for x in (box.get(str(sport or "")) or [])]


# 🔴🔴 **`draw_possible` 을 새로 만들지 않았다** — 이미 있다(위 367줄).
#
#  ⚠️ 내 첫 판은 같은 이름의 함수를 하나 더 지었다. 🔴 `ruff` 가 그 자리에서
#     `F811 Redefinition` 으로 잡았다 — **사본을 만들려던 것**이다(CLAUDE.md #1).
#  🔴 §6-4 의 *"KBO·NPB 만"* 은 **`config/league_rules.yaml` 의 `draw_possible`**
#     선언으로 적는다 — 그쪽이 원본이고 리그별로 이미 그 칸을 들고 있다.
def claim_strength() -> list[str]:
    """🔴 v5 §6-6 — **주장의 강도**(승 > 무패 > 핸디 > 총점). 앞이 강하다.

    ⚠️ `pick_one_when_disjoint.prefer`(선언 순서)와 **다른 것**이다 — §6-6 이
       *"**선언 순서로 고르지 않는다**"* 고 못 박았다.
    """
    got = [str(x) for x in (total_baseline_cfg().get("claim_strength") or [])]
    return got or ["win", "dc", "handicap", "btts", "total"]


def total_lines(base: float) -> list[float]:
    """🔴🔴 총점 **기준선 여러 줄**(사용자 지적 2026-10-03).

    > 사용자는 **언더 2.5 와 언더 3.5 를 둘 다** 대입했다.

    봇은 리그 평균에서 **한 줄**만 뽑아 그 줄만 셌다 — 보드는 그렇게 생기지 않았다
    (북메이커는 사다리로 여러 줄을 낸다).

    🔴 가운데(리그 평균 줄)에서 **양쪽으로 몇 칸** 펼치나는 yaml 이 정한다
       (`total_baseline_no_board.extra_lines`). 코드가 숫자를 박지 않는다.
    ⚠️ `X.5` 만 쓴다(정수 기준선은 밀어내기가 생긴다) — 간격은 `round_to × 2` 다.
    🔴 음수·0 은 내지 않는다 — 총점이 0.5 아래인 줄은 뜻이 없다.
    """
    cfg = total_baseline_cfg()
    step = float(cfg.get("round_to") or 0.5) * 2
    span = int(cfg.get("extra_lines") or 0)
    out = []
    for k in range(-span, span + 1):
        ln = round(float(base) + k * step, 1)
        if ln >= step / 2 and ln not in out:
            out.append(ln)
    return sorted(out)


def h2h_sample_cfg() -> dict:
    """§4 `h2h_pattern.sample_weight` — 창과 표본별 가중치."""
    got = (variable_types().get("h2h_pattern") or {}).get("sample_weight")
    if not got:
        raise KeyError("`h2h_pattern.sample_weight` 가 없다")
    return got


def by_sec7_rule(rule: str) -> dict | None:
    """v4 §7 의 R 번호 → 그것을 이행하는 §5-c 교차 규칙.

    🔴 **§9 단계 6 이 이 함수로 규칙을 찾는다** — 완료 조건이 *"교차 규칙 R3·R6
       포함"* 이라 §7 번호로 지목하기 때문이다. 종전에는 §5-c 규칙에 `R1~R6` 을
       붙여 놔서 `R3` 을 찾으면 **엉뚱한 규칙**(저득점 생성)이 나왔다.
    """
    for r in cross_rules():
        if r.get("sec7_rule") == rule:
            return r
    return None


def unimplemented_types() -> list[str]:
    """🔴 세포가 아직 없는 유형(#7). **조용히 두지 않는다.**

    ⚠️ 이름으로 돌려준다 — 개수만 세면 어느 유형이 안 되는지 사라진다.
       세포 신규 구현은 단계 5 다.
    """
    return sorted(k for k, v in variable_types().items()
                  if not v.get("implemented", False))


def parse_score(score: str) -> tuple[int, int] | None:
    """`"2-1"` → `(2, 1)`. 🔴 **홈-원정 순이다**(§5-b).

    읽을 수 없으면 `None` — 🔴 0 으로 때우지 않는다. `"0-0"` 과 "못 읽었다"는
    다르고, 0 으로 때우면 무승부로 세어진다(조용한 0 금지).
    """
    parts = score.split("-")
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def direction_of(scores: list[str]) -> str | None:
    """스코어 집합 → §1 `direction`. 한 방향이 아니면 `None`.

    🔴 **이것이 §3 STEP 5 계약의 근거다** — *"모든 시나리오가 같은 direction 이면
       실패(반대 방향 시나리오 최소 1개)."* 방향을 표에 적지 않고 여기서 계산하므로
       스코어를 고치면 방향이 따라온다.

    ⚠️ `None` 은 **두 가지**다: 스코어가 비었거나(전날 재사용 템플릿), 결과가
       섞였다(난타전 — 2-2·2-3·3-2 는 무승부·원정·홈이 섞인다). 섞인 것은
       총점 마켓으로 보는 시나리오이고 승패 방향이 없다. 둘 다 "한 방향이 아니다".
    """
    seen: set[str] = set()
    for s in scores:
        pair = parse_score(s)
        if pair is None:
            return None
        h, a = pair
        seen.add("home" if h > a else "away" if a > h else "draw")
    if len(seen) != 1:
        return None
    return seen.pop()


def all_one_direction(score_sets: list[list[str]]) -> bool:
    """🔴 §3 STEP 5 · §5-c-6 — 전부 한 방향이면 **실패**다.

    ⚠️ 방향이 `None` 인 시나리오(난타전·전날 재사용)가 하나라도 있으면 "전부 한
       방향"이 아니다 — 그것이 이미 반대 결과를 품고 있다.
    """
    dirs = [direction_of(s) for s in score_sets]
    if not dirs or None in dirs:
        return False
    return len(set(dirs)) == 1
