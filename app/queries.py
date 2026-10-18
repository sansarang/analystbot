"""§19-b-5 **"바꿔서 다시"** — 같은 검색어를 두 번 던지지 않는다.

§19-b-5 원문: *"같은 검색어 반복 금지. 언어(한→일→영), 표기(9月27日→27日, 팀
정식명→약칭), 매체명 추가(`西スポ`), 시점(오늘→전날 예고 기사) 순으로 변형.
변형 생성은 L5(LLM)이 하되 §12-b 규칙 정규식으로 걸러서 쓴다."*

그래서 이 파일은 **두 층**이다:

| 층 | 무엇 | 왜 |
|---|---|---|
| 규칙 변형 | 위 네 축을 코드가 돌린다 | 🔴 결정적이다 — 같은 질문이 같은 순서를 낸다(채점이 성립한다) |
| L5 변형 | Ollama 가 추가로 낸다 | 규칙이 못 만드는 표현. 🔴 **`query_ok` 를 통과한 것만** 쓴다 |

🔴 **LLM 출력이 `direction`·`weight`·`survival`·`verdict` 에 닿지 않는다**(§17-c).
   여기서 LLM 이 내는 것은 **검색어 문자열**뿐이다.
🔴 버린 L5 출력은 `extraction_rejected` 에 남긴다(§17-g-4) — 조용히 버리면
   프롬프트를 고칠 근거가 사라진다.
"""
from __future__ import annotations

import functools
import json
import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import yaml

from app import llm

logger = logging.getLogger(__name__)

#: 🔴 질문 이름의 **원본**은 `app/cells.Q_TYPES` 다. 여기 베끼지 않고 읽는다.
from app.cells import Q_TYPES as CELL_Q_TYPES

ROOT = Path(__file__).resolve().parents[1]
LINEUP_SOURCES = "config/lineup_sources.yaml"

#: §19-b-5 — 언어는 **현지어 먼저**, 그다음 영어. 🔴 리그가 현지어를 정한다.
#  ⚠️ 한국어를 모든 리그의 1순위로 두지 않는다(§12-b): 한국어로 NPB 를 검색하면
#     번역 기사만 나오고, 그 기사에는 타순이 없다(실측 2026-09-27).
LANGS: dict[str, tuple[str, ...]] = {
    "NPB": ("ja", "en"),
    "MLB": ("en",),
    "KBO": ("ko", "en"),
    "K리그1": ("ko", "en"),
    "CPBL": ("zh", "en"),
}
#: 🔴 **모르는 리그의 기본은 영어다.** 한국어가 아니다.
#
#  ⚠️ 실측 2026-10-01(USL 녹음): 기본이 `("ko","en")` 이라 미국 2부 축구팀을
#     **한국어로** 검색했다 — `Las Vegas Lights 감독 인터뷰 1일`. 결과 17건 중
#     대부분이 zhihu.com(중국어 Q&A)이었고, 열기 예산 17건을 거기 태웠다.
#     라인업·감독 교체·선발 전부 사실 0건.
#
#  🔴 이 파일이 이미 그 이유를 적어 뒀다(바로 위 §12-b 주석): *"한국어로 NPB 를
#     검색하면 번역 기사만 나오고, 그 기사에는 타순이 없다."* **모르는 리그도
#     같다** — 한국어 보도는 번역이거나 아예 없다. 그래서 기본을 영어로 돌린다.
#     한국어 1순위는 **한국 리그에서만** 맞고, 그 리그들은 위 표에 이름이 있다.
#
#  ⚠️ **이것이 끝이 아니다.** 해외축구 13개 대회(리그앙·세리에A·브라질)는 현지어가
#     따로 있고 영어만으로는 현지 소스를 놓친다. 대회→현지어 표가 필요하고,
#     그 표의 원본이 무엇인지는 아직 모른다 — 지어내지 않고 적어 둔다.
#     → `docs/fable/questions/2026-10-01_search_language.md`
DEFAULT_LANGS = ("en",)

#: 🔴 **팀별 검색 언어** — 리그보다 먼저 본다(사용자 지시 2026-10-02).
SEARCH_LANGS = "config/search_langs.yaml"
#: 🔴🔴 **v5 §4-2 — 다국어 나라만** 손으로 적는다. 나머지는 Babel 이 준다.
LANGS_OVERRIDE = "config/langs_override.yaml"


def lang_overrides() -> dict[str, list[str]]:
    """🔴 §4-2 — **다국어 나라만** 선언한다. ⚠️ 작아야 한다(계약이 센다)."""
    from app import rules
    got = rules._load(LANGS_OVERRIDE).get("countries") or {}
    return {str(k).upper(): [str(x) for x in (v or [])] for k, v in got.items()}


def babel_likely(country: object) -> str:
    """🔴🔴 **§4-2 — 나라 코드 → 언어**(Babel likely-subtag).

    ══════════════════════════════════════════════════════════════════
    🔴 왜 Babel 인가 — **손으로 적으면 늘 모자란다**
    ══════════════════════════════════════════════════════════════════

    사용자 지적 2026-10-04: *"C는 손으로 안 적어도 된다"* — 나라→언어는 **CLDR**
    이 이미 안다(`Locale.parse('und_HR')` → `hr`). 🔴 손으로 적은 표는 54개
    대표팀 중 몇 개만 덮는다.

    ⚠️ **모르면 빈 문자열**이다(지어내지 않는다 · #4). 🔴 Babel 이 없어도
       크래시하지 않는다 — 그때도 빈 문자열이고 호출부가 영어로 간다.
    """
    cc = country_code(country)
    if not cc:
        return ""
    try:
        from babel import Locale
    except ImportError:                                    # pragma: no cover
        logger.info("[queries] babel 이 없다 — 나라→언어를 못 얻는다")
        return ""
    try:
        got = Locale.parse(f"und_{cc}")
    except Exception:                                      # noqa: BLE001
        return ""
    lang = str(getattr(got, "language", "") or "")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **Babel 은 모르는 나라에 `en` 을 준다** — 그것은 거짓이다
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측 2026-10-04: `Locale.parse("und_ZZ")` → `en`. `ZZ` 는 **없는
    #     나라**이고 CLDR 의 기본값이 `und` → `en_Latn_US` 다.
    #  🔴 그것을 그대로 쓰면 *"그 나라 현지어는 영어다"* 라는 거짓이 된다 —
    #     그리고 영어는 **이미 맨 앞**이라 아무것도 더해지지 않는다. 호출부는
    #     *"현지어를 얻었다"* 로 읽는데 실제로는 아니다(조용한 0 · #3).
    #  ⚠️ 그래서 **나라가 CLDR 에 실제로 있나**를 함께 본다. 🔴 `ZZ` 는 목록에
    #     **있다** — 이름이 `Unknown Region` 이다(CLDR 이 그렇게 적는다).
    #     그 이름으로 가른다(손으로 코드 목록을 적지 않는다 · #1).
    said = str((Locale("en").territories or {}).get(cc) or "")
    if not said or "Unknown" in said or "Pseudo" in said:
        return ""
    return lang


def country_code(country: object) -> str:
    """🔴 이름표 꼴(`iso:HR`·`fa:SCO`)에서 **두 글자 코드**만. 못 읽으면 `""`.

    ⚠️ `fa:SCO` 는 FIFA **세 글자** 코드다 — Babel 은 두 글자만 안다. 🔴 그래서
       스코틀랜드 같은 팀은 이 길로 못 간다(그 사실이 사유에 남는다).
    """
    cc = str(country or "").strip().upper()
    if ":" in cc:
        cc = cc.split(":", 1)[1]
    return cc if len(cc) == 2 and cc.isalpha() else ""


def langs_from_country(country: object) -> tuple[list[str], str]:
    """🔴 §4-2 — `['en'] + babel_likely(country)`(+ 다국어 선언). `(언어들, 왜)`.

    ⚠️ 영어가 **늘 맨 앞**이다(§4-2 원문 · 사용자 지시 2026-10-02).
    """
    cc = country_code(country)
    if not cc:
        return ["en"], (f"나라 코드를 못 읽었다(`{country}`) — 영어만. "
                        f"⚠️ FIFA 세 글자 코드(`fa:SCO`)는 Babel 이 모른다")
    over = lang_overrides().get(cc)
    if over:
        out = ["en"] + [x for x in over if x != "en"]
        return out, f"§4-2 — `{cc}` 는 **다국어 나라** 선언이다({over})"
    one = babel_likely(cc)
    if not one:
        return ["en"], f"§4-2 — Babel 이 `{cc}` 의 언어를 모른다 — 영어만"
    if one == "en":
        return ["en"], f"§4-2 — Babel: `{cc}` → `en`"
    return ["en", one], f"§4-2 — Babel likely-subtag: `und_{cc}` → `{one}`"


def langs_for(league: str, *teams: str) -> tuple[tuple[str, ...], str]:
    """🔴 **무엇으로 찾나.** `(언어들, 왜)` — 사유를 돌려준다(조용히 고르지 않는다).

    ══════════════════════════════════════════════════════════════════
    🔴 **리그가 아니라 팀에 맞춘다** (라이브 실측 2026-10-02 가 그렇게 시켰다)
    ══════════════════════════════════════════════════════════════════

    실측 2026-10-01(USL): 기본이 한국어라 미국 팀을 한국어로 찾았다 → zhihu 홍수.
      그래서 기본을 영어로 바꿨다.
    🔴 실측 2026-10-02(아시안게임 한국 vs 중국): 그 영어 기본이 **한국 대표팀을
      깨뜨렸다** — 사실 0건이었는데 맞대결·휴식·감독 발언이 **한국어 매체에 다 있었다.**

    ⚠️ 리그로는 못 담는다: 대표팀 경기는 **상대에 따라** 언어가 달라진다.
       한국 vs 중국은 `ko+zh`, 한국 vs 일본은 `ko+ja` 다.
    🔴 **선언한 팀만** 이긴다. 없으면 리그 기본으로 가고 그 사실이 사유에 남는다.
    """
    from app import rules
    table = (rules._load(SEARCH_LANGS).get("teams") or {})
    # 🔴🔴 **영어가 맨 앞이다**(사용자 지시 2026-10-02):
    #
    #  > 한국어로 찾지 말고 영어로 찾으면 되잖아...공통으로 영어 그다음은 그나라 현지어..
    #
    #  영어가 **공통**이다 — 현지어는 그 나라 경기에만 듣고 영어는 거의 모든 경기에
    #  듣는다. 예산(검색 3회)을 쓰는 순서가 그 순서여야 한다.
    #  ⚠️ yaml 에는 **현지어만** 적는다 — `en` 을 거기 적으면 순서가 갈린다.
    local: list[str] = []
    named: list[str] = []
    for t in teams:
        got = table.get(str(t or "").strip())
        if not got:
            continue
        named.append(str(t))
        for lang in got:
            if lang != "en" and lang not in local:
                local.append(str(lang))
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **별칭이 선언된 언어도 검색 언어다** (사용자 기술 지시 2026-10-03)
    # ══════════════════════════════════════════════════════════════════
    #
    #  실측: 파라과이 별칭 `Albirroja` 를 `es` 로 선언했는데 검색 언어가 `en` 뿐이라
    #  **그 별칭이 한 번도 안 던져졌다.** 선언이 있는데 안 쓰이는 것이 가장 나쁘다.
    #
    #  🔴 별칭을 그 언어로 선언한 것 자체가 *"이 팀 기사는 그 언어로 나온다"* 는
    #     뜻이다 — 같은 사실을 `search_langs.yaml` 에 **또 적지 않는다**(사본 금지).
    # 🔴🔴 **별칭 언어는 맨 뒤로 옮겼다** — 실사고 2026-10-17(아래 `_alias_langs`).
    if local:
        return ("en", *local), f"영어 + 팀 현지어 {named} → {['en'] + local}"
    if league in LANGS:
        # 🔴 리그 표도 **영어를 앞으로** 돌린다 — 원본은 그대로 두고 순서만 맞춘다
        rest = [x for x in LANGS[league] if x != "en"]
        return ("en", *rest), f"영어 + 리그 `{league}` 현지어 → {['en'] + rest}"
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **리그 명부도 언어를 안다**(사용자 지시 2026-10-03)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 위 `LANGS` 는 **다섯 리그**뿐이다(NPB·MLB·KBO·K리그1·CPBL). J리그·NHL·
    #     해외축구는 거기 없어서 **영어로만** 갔다 — 실측 2026-10-03: 가시와 vs
    #     감바(J리그)가 `['en']` 으로 돌았고 일본 매체 기사를 못 집었다.
    #  🔴 `config/leagues.yaml` 이 리그마다 언어를 적고 있다 — **같은 사실을 두 곳에
    #     두지 않고** 그것을 본다(사본 금지). ⚠️ `LANGS` 가 **먼저**다(더 오래
    #     측정된 표다) — 명부는 그것이 모르는 리그를 메운다.
    from app import league_index as _LI
    got = _LI.langs_of(league)
    if got:
        rest = [x for x in got if x != "en"]
        return ("en", *rest), (f"영어 + **리그 명부** `{league}` 현지어 → "
                               f"{['en'] + rest}")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **자동 등록된 리그의 언어**(사용자 결정 2026-10-10 §3)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 나라 코드 → **CLDR 공식 언어**(그 언어 + 영어)로 검색 언어 세팅.
    #
    #  🔴 등록 파일이 그 언어를 **이미 들고 있다**(`data/leagues_auto/*.json` 의
    #     `langs`) — 여기서 나라→언어를 다시 계산하지 않는다(사본 금지).
    #  ⚠️ 손 표(`LANGS`·`leagues.yaml`)가 먼저다 — 더 오래 측정된 표다.
    from app.core import autoleague as _AL
    from app.core import competition as _CP
    _key, _ = _CP.key_of(competition=league)
    _auto = _AL.load(_key) if _key else {}
    if _auto.get("langs"):
        rest = [x for x in _auto["langs"] if x != "en"]
        return ("en", *rest), (f"영어 + **자동 등록** `{_key}`"
                               f"({_auto.get('ccode')}) 현지어 → {['en'] + rest}")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **별칭이 선언된 언어는 맨 마지막 퇴로다** — 실사고 2026-10-17
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 **거짓 수였다** — 이 검사는 `entities.yaml` 의 별칭 언어를
    #     *"이 팀 기사는 그 언어로 난다"* 로 읽었고, **리그보다 먼저** 썼다.
    #     ⚠️ 그런데 그 파일의 `ko` 별칭은 *"사용자가 한국어로 물었다"* 는
    #        기록이다(`source:` 칸이 그렇게 적혀 있다). 그래서
    #        **`Mito Hollyhock`(일본 J2)이 `ko`** 로 나왔고, 우라와 경기
    #        검색이 한국어로 갔다(실측 2026-10-17: `('en','ko')`).
    #        🔴 `Kashiwa Reysol` 은 `entities.yaml` 에 없어서 리그 경로로
    #           떨어져 **`ja`** 가 맞게 나왔다 — 그 차이가 증거다.
    #  🔴 그래서 **순서만 바꿨다**(검사를 지우지 않았다) — 파라과이 별칭
    #     `Albirroja`(es)가 생긴 까닭은 대표팀 친선이라 **리그가 없는** 경기
    #     였다. 그 경기는 여기까지 내려와 그대로 `es` 를 받는다.
    from app import entities
    for t in teams:
        for lang in entities.langs_of(str(t or "")):
            # ══════════════════════════════════════════════════════════
            # 🔴🔴 **`ko` 별칭은 현지어 증거가 아니다** — 지시 2026-10-18
            # ══════════════════════════════════════════════════════════
            #
            #  ⚠️ 실사고 2026-10-18(캔자스 vs 솔트레이크): MLS 질의가 **전부
            #     한국어**로 나가 ③ 문서가 1~2건이었다(영어권인데).
            #     🔴 까닭 — `config/entities.yaml` 의 `Sporting Kansas City` 에
            #     `ko: [스포팅 캔자스시티, …]` 가 있어 `langs_of` 가 `ko` 를
            #     돌려줬다. 그 별칭은 **한국 사용자가 한글로 물어서** 붙은
            #     것이고 *"그 팀 기사가 한국어로 나온다"* 는 뜻이 아니다.
            #  🔴 그래서 **`ko` 만 뺀다** — 우리 사용자 언어라서 어느 팀에나
            #     붙는다. ⚠️ 한국 리그는 **리그·나라 표**가 `ko` 를 준다(아래
            #     `league_of_team` 길) — 그 길은 그대로다.
            if lang == "ko":
                continue
            if lang != "en" and lang not in local:
                local.append(lang)
                if str(t) not in named:
                    named.append(str(t))
    if local:
        return ("en", *local), (f"영어 + **별칭 선언** 현지어 {named} → "
                                f"{['en'] + local}(리그 쪽은 몰랐다)")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **리그를 모르면 팀으로 되묻는다**(사용자 지시 2026-10-03)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 세포는 `league` 로 **대회 이름**을 받는다(`League Cup`·`Friendlies`).
    #     그 이름은 어느 표에도 없어서 **영어로만** 갔다 — 실측 2026-10-03:
    #     가시와 vs 감바가 `League Cup` 으로 들어와 일본어가 안 붙었다.
    #  🔴 그런데 **팀 이름은 안다.** 리그 색인(`config/leagues.yaml` + 받아 둔
    #     명단)이 `Kashiwa Reysol → J리그 → ['ja','en']` 을 들고 있다.
    #  ⚠️ **캐시만 본다** — 이 함수는 동기이고, 여기서 통신하면 질의마다 멈춘다.
    from app import league_index as _LI2
    for t in teams:
        key = _LI2.league_of_team(str(t or ""))
        if not key:
            continue
        rest = [x for x in _LI2.langs_of(key) if x != "en"]
        if rest:
            return ("en", *rest), (f"영어 + **팀으로 되물은 리그** `{key}` 현지어 "
                                   f"→ {['en'] + rest} (대회 `{league}` 는 표에 없다)")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **§4-2 — 선언이 없으면 Babel 이 나라에서 언어를 준다**
    # ══════════════════════════════════════════════════════════════════
    #
    #  > `langs = ['en'] + babel_likely(team.country)` … 다국어 나라만
    #  > `config/langs_override.yaml`.
    #
    #  ⚠️ 종전에 이 자리는 **영어만**으로 끝났다 — 그 팀 기사가 현지어로만
    #     나오면 **못 찾는다**고 사유에 적고 끝이었다. 🔴 그런데 **나라는 안다**
    #     (`entities` 가 이름표에서 코드를 읽는다). 나라→언어는 **CLDR** 이
    #     이미 아는 것이고, 손으로 적을 일이 아니다(사용자 지적 2026-10-04).
    #  🔴 **54개 대표팀**이 이 길로 한꺼번에 덮인다.
    from app import entities as _ENT
    for t in teams:
        # 🔴 **`profile` 을 본다** — `field_of` 는 **선언된 것만** 돌려준다.
        #    ⚠️ 나라 코드는 선언이 아니라 **이름표에서 자란다**(`iso:HR`) —
        #       실측 2026-10-04: `field_of("Croatia","country")` 가 `None` 이었다.
        cc = _ENT.profile(str(t or "")).get("country")
        got2, why2 = langs_from_country(cc)
        if len(got2) > 1:
            return tuple(got2), (f"{why2} (팀 `{t}` · 대회 "
                                 f"`{league or '미상'}` 선언 없음)")
    return DEFAULT_LANGS, (
        f"`{league or '리그 미상'}`·팀 {list(teams)} 둘 다 선언이 없고 "
        f"**나라도 모른다**(클럽이다) — 영어만. "
        f"⚠️ 그 팀 기사가 현지어로만 나오면 **못 찾는다**")


#: 🔴 **종목마다 없는 질문이 있다.** 그 질문을 던지면 엉뚱한 것을 묻는다.
#
#  ⚠️ 실측 2026-10-01: 축구 경기에 `starter_recent`(예고 선발) 세포를 돌렸더니
#     검색어가 `Las Vegas Lights 선발 등판 1일` 이 됐다 — **야구 용어**다.
#     §4 `pitcher_state` 가 *"예고 선발 최근 4~5등판·이닝"* 이라 야구 전용이고,
#     어댑터가 이미 그렇게 적어 뒀다:
#       · `app/collect/fdorg.py` — *"축구에는 예고 선발이 없다"*
#       · `app/collect/nhl.py`   — *"하키에는 예고 선발(투수)이 없다"*
#  🔴 **없는 질문은 묻지 않고, 묻지 않았다고 사유를 남긴다**(§19-b-6).
#
#  🔴🔴 **열쇠는 `cells.Q_TYPES` 어휘다 — 지어내지 않는다.**
#     ⚠️ 실측 2026-10-01: 첫 판에서 `"coach_change"`·`"live"` 라고 적었다. 둘 다
#        **없는 이름**이다(감독 교체 세포는 `intent` 를 쓰고 라이브는 `live_score`
#        다). 그래서 녹음이 감독 교체 세포를 **"축구에 없는 질문"으로 건너뛰었다** —
#        §4 `coach_change` 의 보기가 *"조지아 사뇰 사임"*(축구!)인데도.
#        내가 막으려던 "조용한 0"을 **내 가드가 만들었다.**
#     → `tests/stage4/test_intent_attribution.py` 가 어휘를 `Q_TYPES` 와 대조한다.
SPORT_QUESTIONS: dict[str, frozenset[str]] = {
    # 🔴 `starter_recent`(예고 선발)만 야구 전용이다. 나머지는 모든 종목에 있다.
    "baseball": frozenset(CELL_Q_TYPES),
    "soccer": frozenset(CELL_Q_TYPES) - {"starter_recent"},
    "hockey": frozenset(CELL_Q_TYPES) - {"starter_recent"},
    "basketball": frozenset(CELL_Q_TYPES) - {"starter_recent"},
    "volleyball": frozenset(CELL_Q_TYPES) - {"starter_recent"},
}


def asks(sport: str, qtype: str) -> tuple[bool, str]:
    """이 종목에 이 질문이 있나. 🔴 없으면 **사유를 함께** 돌려준다.

    ⚠️ 모르는 종목은 **막지 않는다** — 표에 없는 종목을 조용히 전부 거부하면
       새 종목이 아무 질문도 못 한다. 모른다고 적고 통과시킨다.
    🔴 **모르는 질문 이름도 막지 않는다** — 막으면 오타 하나가 세포를 조용히
       없앤다(2026-10-01 에 실제로 그랬다). 대신 이름으로 남긴다.
    """
    if qtype not in CELL_Q_TYPES:
        return True, (f"질문 이름 `{qtype}` 이 `cells.Q_TYPES` 에 없다 — "
                      f"막지 않고 적어 둔다 (있는 것: {sorted(CELL_Q_TYPES)})")
    have = SPORT_QUESTIONS.get(sport)
    if have is None:
        return True, f"종목 `{sport}` 이 질문표에 없다 — 막지 않고 적어 둔다"
    if qtype in have:
        return True, ""
    return False, f"`{qtype}` 은 {sport} 에 없는 질문이다 — 묻지 않았다"


@dataclass(frozen=True)
class Variant:
    """던질 검색어 하나. `axis` 는 §19-b-5 의 어느 축에서 나왔나다.

    🔴 `axis` 를 들고 다니는 이유: unknown 사유에 *"어떤 변형까지 썼는지"* 를
       적어야 한다(§19-b-6). 문자열만 남기면 "언어를 바꿔 봤나"를 알 수 없다.
    """

    text: str
    lang: str
    axis: str
    source: str = "rule"        # rule | L5
    #: 🔴🔴 **v5 §4-1 — 이 질의에 무엇을 넣었나.** 문지기가 이것으로 센다.
    #  ⚠️ 글에서 짐작하면 상대·대회를 **못 센다**(이름을 모르니까) → 거짓 거부.
    parts: dict | None = None


# ══════════════════════════════════════════════════════════════════
# §13-b 라인업 1차 소스 — 🔴 표는 yaml 이 원본이다
# ══════════════════════════════════════════════════════════════════


@functools.lru_cache(maxsize=None)
def _lineup() -> dict:
    return yaml.safe_load((ROOT / LINEUP_SOURCES).read_text(encoding="utf-8"))


def lineup_teams() -> dict[str, dict]:
    """§13-b 표. 키는 표의 **첫 칸 그대로**다(여섯 팀 묶음 행 포함)."""
    return _lineup()["teams"]


def lineup_opens_before_min() -> int:
    """§13-b 머리글 — 라인업이 경기 몇 분 전에 공개되나."""
    return int(_lineup()["opens_before_min"])


def banned_for_lineup() -> list[str]:
    """§13-a 가 **라인업 소스로 쓰지 말라고 이름을 댄** 곳.

    🔴 *"스포츠나비 경기 페이지(JS)·baseball-data 스타멘 표(**하루 지연**)·야후
       뉴스 본문(robots 거부)은 라인업 소스로 쓰지 않는다."*

    ⚠️ 표에 안 넣는 것만으로는 부족하다 — 이 셋은 **검색 결과 1순위로 나온다.**
       세포가 그 URL 을 열면 같은 자료를 쓰는 것이다(실측 2026-09-30: 하루 지연
       표에서 뽑은 타순에 겐다가 선발로 들어 있었다 — §19-g-5 와 반대 사실).
    """
    return list(_lineup().get("banned_for_lineup") or [])


def lineup_for(team: str, league: str = "", local: str = "") -> dict | None:
    """팀 → §13-b 행. 🔴 **팀 이름이 먼저, 리그 단위 행이 나중이다.**

    §13-b 표에는 세 꼴의 행이 있다:
      · 팀 하나 (`소프트뱅크`)
      · 여섯 팀 묶음 (`야쿠르트·라쿠텐·…`)
      · **리그 전체** (`MLB 전 구단`·`KBO 전 구단`·`K리그 전 구단`·`CPBL`)

    ⚠️ 실측 2026-09-30: 종전 이 함수는 팀 이름만 봤고, 그래서 `Houston Astros`·
       `인천` 은 **§13-b 검색어를 영영 못 받았다**(리그 단위 행이 안 잡혔다).
       §19-g 5·6번이 바로 그 행을 쓴다 — 게이트가 못 돌 자리였다.

    🔴 팀 전용 행이 리그 행을 **이긴다.** 소프트뱅크는 `MLB 전 구단` 같은 넓은
       행이 아니라 자기 행(西スポ)을 써야 한다.
    ⚠️ 못 찾으면 `None` — 아무 행이나 돌려주지 않는다. 남의 팀 검색어로 던지면
       엉뚱한 라인업이 그 경기에 붙는다(실사고 M14 의 귀속 오류와 같은 꼴).
    """
    teams = lineup_teams()
    if team in teams:
        return teams[team]
    for key, row in teams.items():
        if "·" in key and team in key.split("·"):
            return row
    # 🔴 **현지 표기로도 찾는다.** 표 키는 한국어(`히로시마`)인데 수집기의 팀명은
    #    소스의 표기(`広島東洋カープ`)다. 호출부가 리그 어댑터의 약칭 표
    #    (`npb.TEAMS` — 원본은 거기 하나다)로 `local` 을 넘기면 표의 검색어 틀
    #    맨 앞 토큰과 맞는다. 🔴 대응표를 여기 **베끼지 않는다.**
    if local:
        for key, row in teams.items():
            token = local_name(row)
            if token and (token == local or token in local or local in token):
                return row
            if "·" in key and local in key.split("·"):
                return row
    if league:
        # 🔴 정본 첫 칸이 리그를 이름으로 댄 행이 먼저(`MLB 전 구단`),
        #    그다음 그 리그의 **기본 행**(NPB 묶음 행). 순서를 섞으면 팀 전용
        #    소스가 있는데도 넓은 행이 이긴다.
        for field in ("league", "default_for_league"):
            for row in teams.values():
                name = str(row.get(field) or "")
                # `K리그1` 이 `K리그` 행에 걸리게 — 표는 리그 계열을 이름으로 댄다
                if name and (league == name or league.startswith(name)):
                    return row
    return None


def local_name(row: dict | None) -> str:
    """§13-b 검색어 틀의 **맨 앞 현지 팀명**. 없으면 빈 문자열.

    🔴 실측 2026-09-30: 언어 변형이 `소프트뱅크 スタメン 9月27日` 를 냈다 —
       핵심어만 일본어로 바꾸고 **팀명은 한국어로 남았다.** 일본 매체는 그
       표기로 안 쓰므로 그 검색은 구조적으로 0건이다. §19-b-5 의 "언어" 축은
       질문 **전체**를 현지어로 바꾸는 것이다.

    ⚠️ 이름을 여기 적지 않는다 — 정본 표의 검색어 틀에서 **읽는다**. 틀이
       `{team} lineup {date}` 처럼 자리표로 시작하면 현지명이 없는 것이다.
    """
    q = str((row or {}).get("query") or "").strip()
    if not q or q.startswith("{"):
        return ""
    head = q.split()[0]
    return "" if head.startswith("{") else head


# ══════════════════════════════════════════════════════════════════
# 규칙 변형 — §19-b-5 네 축
# ══════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **모르는 언어에 한국어 날짜를 붙이던 자리**(실측 2026-10-04)
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 아래 둘은 `ja`·`zh`·`en` 만 알고 **나머지는 전부 한국어**로 떨어졌다. 리그
#     언어가 ko/ja/zh/en/es 뿐일 때는 그 떨어짐이 우연히 맞았다.
#  🔴 사다리가 Babel 로 `mk`(마케도니아어)를 알게 되자 그 우연이 깨졌다:
#
#       `North Macedonia состав Scotland фудбал 3일`
#                                            ^^^ 🔴 **한국어다**
#
#  🔴 **같은 Babel 이 날짜도 준다** — `format_skeleton('MMMd', d, locale='mk')`
#     → `'3 окт.'`(순서까지 그 언어의 것이다 · 실측 2026-10-04).
#  ⚠️ 그런데 **실측한 네 언어는 바꾸지 않는다.** ko·ja·zh·en 의 꼴은 검색엔진에
#     실제로 던져 고른 것이다(`10月3日`·`Oct 3`). Babel 이 주는 `3. окт`류 약칭이
#     그 네 언어에서 더 좋다는 측정은 **없다** — 측정 없이 바꾸면 그것이 추측이다.
#  🔴 그래서 Babel 은 **구멍만 메운다**(§19-b-4 와 같은 결: 선언 먼저, 대체 나중).

#: 🔴 실측으로 고른 날짜 꼴. ⚠️ 여기 있는 언어는 Babel 로 **안 간다**.
MEASURED_DATES = {
    "ja": (lambda d: f"{d.month}月{d.day}日", lambda d: f"{d.day}日"),
    "zh": (lambda d: f"{d.month}月{d.day}日", lambda d: f"{d.day}日"),
    "en": (lambda d: f"{d:%b} {d.day}", lambda d: str(d.day)),
    "ko": (lambda d: f"{d.month}월 {d.day}일", lambda d: f"{d.day}일"),
}


def _babel_date(day: date, lang: str, skeleton: str) -> str:
    """🔴 그 언어의 날짜. 못 만들면 **빈 문자열** — 한국어로 떨어지지 않는다."""
    try:
        from babel.dates import format_skeleton
        return str(format_skeleton(skeleton, day, locale=str(lang)))
    except Exception as exc:                                # noqa: BLE001
        logger.info("[queries] 날짜를 `%s` 로 못 적었다(%r) — 그 칸을 비운다",
                    lang, exc)
        return ""


def month_day(day: date, lang: str) -> str:
    """🔴 **연도를 붙이지 않는다**(§12-b) — 붙이면 지난 시즌 기사가 섞인다.

    ⚠️ 모르는 언어는 **Babel** 이 적고, 그것도 못 하면 **빈 문자열**이다.
       🔴 빈 칸이면 `_compose` 가 그 조각을 그냥 안 넣는다 — 한국어 날짜가 외국어
          질의에 붙는 것보다 **날짜가 없는 것이 낫다**.
    """
    got = MEASURED_DATES.get(str(lang))
    if got:
        return got[0](day)
    return _babel_date(day, lang, "MMMd")


def day_only(day: date, lang: str) -> str:
    """§19-b-5 표기 변형 — `9月27日` → `27日`. 월을 떼면 검색이 넓어진다."""
    got = MEASURED_DATES.get(str(lang))
    if got:
        return got[1](day)
    return _babel_date(day, lang, "d")


#: §12-b 질의 낱말 상한. 🔴 **원본은 `llm.query_ok` 다** — 여기 숫자를 또 적지
#  않는다(사본 금지). 아래 `_compose` 가 그 함수에 **물어본다**.

#: 🔴🔴 **질의 조각의 우선순위** — 사용자 수정 ① (2026-10-04) + 실측
#
#  > 검색어 구성 규칙: `{팀} {상대} {대회명} {종목 낱말} {날짜}` — 나라 이름
#  > 하나짜리 검색어는 **계약으로 금지**.
#
#  ⚠️ 그 다섯을 다 넣으면 **9낱말**이고 §12-b 상한(6)을 넘는다. 넘겨 던져 봤다:
#
#  | 꼴 | 대표팀(en) 스포츠 매체 | 클럽(KBO ko) |
#  |---|---|---|
#  | 팀 + what + 날짜 (지금) | ✅ 20/48 | ✅ 9/31 |
#  | **+ 상대** | ✅ 25/51 (+25%) | 🔴 **18/38 (+100%)** |
#  | + 상대 + **종목** | 🔴 **31/52 (+24%)** | ⚠️ 14/30 (**−22%**) |
#  | 9낱말 전부 | ⚠️ 19/51 (**나빠진다**) | — |
#
#  🔴 그래서 실측이 정한 규칙은 셋이다:
#
#    ① **상대는 늘 넣는다** — 양쪽에서 가장 크게 올랐다(+25% · +100%)
#    ② 🔴 **종목 낱말은 대표팀만** — 클럽은 이름이 이미 종목을 뜻한다
#       (`LG 트윈스` 는 럭비가 될 수 없다). 대표팀은 **나라 이름**이라 필요하다.
#    ③ **날짜는 자리가 남을 때만** — 상대보다 약하다(9 vs 18)
#
#  ⚠️ **대회명은 안 넣는다.** 9낱말 꼴이 가장 나빴고, 대회명을 넣은 ⑥번 꼴
#     (22/53)도 상대+종목(31/52)보다 낮았다. 🔴 측정이 사용자 규칙의 이 칸을
#     고쳤다 — 그 사실을 여기 남긴다(§11 *"측정이 계약보다 많이 잡는다"*).
PIECE_ORDER = ("team", "what", "opponent", "sport", "day")


def _compose(pieces: dict[str, str], *, order=PIECE_ORDER) -> tuple[str, list[str]]:
    """🔴 조각들을 **우선순위대로** 넣다가 §12-b 상한에 닿으면 멈춘다.

    반환은 `(질의, 버린 조각 이름들)`. ⚠️ **버린 것을 이름으로** 돌려준다 —
    조용히 자르면 *"왜 날짜가 없나"* 를 다음 사람이 못 찾는다(#3 조용한 0 금지).

    🔴 상한을 여기 숫자로 적지 않는다 — `llm.query_ok` 에 **물어본다**. 그러면
       §12-b 를 고칠 때 한 곳만 고친다(사본 금지).
    """
    out: list[str] = []
    dropped: list[str] = []
    for name in order:
        piece = " ".join(str(pieces.get(name) or "").split())
        if not piece:
            continue
        trial = " ".join([*out, piece])
        if llm.query_ok(trial):
            out.append(piece)
        else:
            dropped.append(name)
    return " ".join(out), dropped


def variants(*, team: str, league: str, day: date, what: str | dict,
             local: str = "", venue: str = "", use_table: bool = True,
             aliases: list[str] | None = None,
             # 🔴 사용자 수정 ① (2026-10-04) — 신원을 질의에 **싣는다**
             opponent: str = "", opponent_local: str = "",
             sport: str = "", langs: tuple[str, ...] = ()) -> list[Variant]:
    """§19-b-5 순서대로 검색어를 만든다. 🔴 **같은 것을 두 번 넣지 않는다.**

    `what` 은 질문의 핵심어다(`スタメン`·`lineup`·`선발 라인업`). §13-b 에 그 팀
    행이 있으면 **그 검색어가 1번**이다 — 표가 실측으로 정한 순서다.

    ══════════════════════════════════════════════════════════════════
    🔴🔴 `what` 은 **언어마다 다르다** — dict 를 받는다(실측 2026-10-03)
    ══════════════════════════════════════════════════════════════════

    ⚠️ 종전에는 핵심어를 **하나** 골라 모든 언어 변형에 그대로 붙였다. 그래서
       영어 질의에 한국어 낱말이 들어갔다:

    ```
    [lang:en] LG Twins 선발 라인업 Oct 3      🔴 영어 매체는 이 글자를 안 쓴다
    [lang:en] Jamaica 순위 매직넘버 Oct 3      🔴 같은 병
    ```
    🔴 이 저장소는 **팀 이름**에서 같은 병을 이미 고쳤다(*"현지 약칭은 그 나라
       언어 질의에 붙는다"*). 핵심어는 그때 안 고쳤다 — 같은 줄에 있는데도.
    ⚠️ 문자열 하나를 주면 종전대로 **모든 언어에 같은 낱말**이 붙는다(뒤로 호환).

    🔴 `use_table=False` 면 §13-b 표를 쓰지 않는다. **§13-b 는 라인업 표다** —
       선발 최근 창·감독 의도 질문에 `{team} lineup {date}` 를 던지면 엉뚱한 것을
       묻는다(실측 2026-09-30: `search_sources` 가 모든 질문에 표를 붙였다).

    🔴 `venue` 는 §13-b 히로시마 행이 요구한다(`広島 スタメン {月日} {球場}`) —
       구장이 들어가면 그날 그 경기 기사로 좁혀진다. 모르면 그 칸은 지운다.

    🔴 반환 순서가 곧 시도 순서다. `axis` 로 무엇을 바꿨는지 남는다.
    """
    # 🔴 **팀을 먼저 본다** — 리그 기본이 대표팀 경기를 깨뜨렸다(위 `langs_for`)
    # ⚠️ 호출부가 언어를 **이미 알면** 그것이 이긴다 — 대표팀은 리그가 없어
    #    `langs_for` 가 `('en',)` 로 떨어지지만 사다리 ②가 Babel 로 `mk` 를 안다
    #    (2026-10-04 보기 C). 🔴 같은 사실을 두 번 계산하면 한쪽이 늘 늦는다.
    if langs:
        _why = "호출부가 준 언어(사다리 ②가 정했다)"
    else:
        langs, _why = langs_for(league, team, *(aliases or []))
    out: list[Variant] = []
    seen: set[str] = set()

    def add(text: str, lang: str, axis: str, source: str = "rule",
            parts: dict | None = None) -> None:
        t = " ".join((text or "").split())
        if not t or _norm(t) in seen:
            return                       # 🔴 §19-b-5 "같은 검색어 반복 금지"
        seen.add(_norm(t))
        # 🔴 §4-1 — **무엇을 넣었나**를 싣는다(문지기가 짐작하지 않게)
        out.append(Variant(t, lang, axis, source, parts=parts))

    # ① §13-b 표의 검색어가 먼저 — 실측이 정한 1차 소스다
    row = lineup_for(team, league, local) if use_table else None
    if row and row.get("query"):
        lang = str(row.get("lang") or langs[0])
        # 🔴 자리표에는 **현지 표기**를 넣는다. 정본이 `{球団}`(일본어)·`{隊}`
        #    (중국어)라고 쓴 것은 그 언어의 표기를 기대한다는 뜻이다 — 정식명을
        #    넣으면 `千葉ロッテマリーンズ スタメン …` 가 되고 기사는 `ロッテ` 를 쓴다
        #    (실측 2026-09-30: 절제가 이 자리를 드러냈다).
        # 🔴 §4-1 — 이 축도 **조각을 싣는다**(문지기가 짐작하지 않게).
        #    ⚠️ 표의 검색어는 `{team} {what} {date} {venue}` 꼴이다.
        add(_fill(row["query"], team=local or team, day=day, lang=lang,
                  venue=venue), lang, "§13-b",
            parts={"team": local or team, "when": month_day(day, lang),
                   "competition": venue or str(row.get("media_token") or ""),
                   "sport": ""})

    # ② 언어 (현지어 → 영어). 🔴 **팀명도 현지어로 바꾼다** — 핵심어만 바꾸면
    #    `소프트뱅크 スタメン` 처럼 아무 매체도 안 쓰는 표기가 된다(실측).
    lang0 = langs[0]
    # 🔴 현지 표기는 **표에서 읽거나 호출부가 준 것**이다 — 지어내지 않는다.
    native = local_name(row) or local
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **별칭 사전도 현지 표기의 원본이다**(실측 2026-10-03)
    # ══════════════════════════════════════════════════════════════════
    #
    #  §13-b 표에 행이 없는 리그(KBO 등)는 `native` 가 비고 **정식명(영문)** 으로
    #  떨어진다. 실측(LG 트윈스 vs 기아 타이거즈)에서 그 결과가 이랬다:
    #
    #      LG Twins 선발 라인업 10월 3일      ← 🔴 반쯤 한국어인 질의
    #      → www.kia.com(자동차)·solutions.lg.com·nba.com·golf.com
    #        kare11.com "Gardenhire out as **Twins** manager"(미네소타)
    #
    #  🔴 `config/entities.yaml` 이 **이미 그 표기를 들고 있다** — 사다리(기술 1)가
    #     쓰는 바로 그 선언이다. 여기서 또 적지 않고 **같은 접근자**를 부른다.
    #  ⚠️ 표(§13-b)·호출부가 준 것이 **먼저**다 — 그쪽이 더 구체적이다.
    _native_lang = next((x for x in langs if x != "en"), lang0)
    if not native:
        from app import entities as _ent
        got = _ent.aliases_of(team, lang=_native_lang)
        native = got[0] if got else ""
    if not native:
        # 🔴 **리그 색인이 받아 둔 현지 표기**(`Kashiwa Reysol` → `柏レイソル`).
        #    ⚠️ 선언(`entities.yaml`)이 **먼저**다 — 사용자가 적은 것이 받아 온
        #       것보다 낫다. 이것은 선언이 없을 때의 **대체**다(§19-b-4 와 같은 결).
        from app import league_index as _LI3
        native = _LI3.local_of_team(team)
    # 🔴🔴 **현지 약칭은 "첫 언어"가 아니라 "현지어"에 붙는다.**
    #
    #  ⚠️ 전 판은 `lang == lang0`(첫 언어)로 봤다. 그때는 첫 언어가 곧 현지어였기
    #     때문에 우연히 맞았다. 사용자 지시 2026-10-02 로 **영어가 맨 앞**이 되자
    #     그 우연이 깨졌고 — 영어 변형에 `広島`, 일본어 변형에 `広島東洋カープ` 가
    #     붙었다. **거꾸로다.** 계약(`test_현지어_변형이_팀명까지_바꾼다`)이 잡았다.
    #  🔴 현지 약칭은 **그 나라 매체가 쓰는 표기**다 — 그 나라 언어 질의에 붙어야 한다.
    def _what(lang: str) -> str:
        """🔴 그 언어의 핵심어. 없으면 영어, 그것도 없으면 아무거나 하나."""
        if not isinstance(what, dict):
            return str(what)
        got = what.get(lang) or what.get("en")
        if got:
            return str(got)
        return str(next((v for v in what.values() if v), ""))

    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **신원을 질의에 싣는다** — 사용자 수정 ① (2026-10-04)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 종전 이 자리는 `{팀} {what} {날짜}` 였다. 대표팀은 그것이 **나라 이름
    #     하나짜리 질의**가 되고, 검색엔진이 나라 기사를 준다(실측: 드라마 출연진·
    #     럭비·위키 경제 문서·SMS 판매). 🔴 사용자가 그것을 **계약으로 금지**했다.
    #  🔴 조각의 우선순위·까닭은 `PIECE_ORDER` 머리글의 측정표에 있다.
    from app import rules as _rules
    # 🔴 **종목 낱말은 대표팀만**(측정: 클럽은 −22%). 나라 코드가 있으면 대표팀이다.
    sport_w: dict[str, str] = {}
    if sport:
        from app import resolve as _rs
        nat, _ = _rs.nation_langs(team)
        if nat:
            sport_w = {lg: _rules.sport_word(sport, lg) for lg in langs}
        elif not opponent:
            # ══════════════════════════════════════════════════════════
            # 🔴🔴 **v5 §4-1 — 상대가 없으면 종목 낱말이 그 자리를 채운다**
            # ══════════════════════════════════════════════════════════
            #
            #  ⚠️ `starter_recent`(지난 등판)는 **상대를 안 싣는다** — 그 투수는
            #     오늘 상대와 지난주에 안 붙었다. 🔴 그래서 요소가 둘(팀·핵심어)
            #     뿐이고 §4-1 문지기가 **막는다**(실측 2026-10-04).
            #  🔴 클럽에 종목 낱말을 붙이면 측정에서 −22% 였지만, **막히는 것보다
            #     낫다** — 0건과 −22% 는 비교가 안 된다.
            #  ⚠️ 상대가 **있으면** 안 붙인다(그때는 요소가 셋이고, 측정대로
            #     종목 낱말이 해롭다).
            sport_w = {lg: _rules.sport_word(sport, lg) for lg in langs}

    def _opp(lang: str) -> str:
        """🔴 상대 표기도 **그 언어로**. 없으면 영문명, 그것도 없으면 빈 값."""
        if lang != "en" and opponent_local:
            return opponent_local
        return opponent

    for lang in langs:
        who = native if (native and lang != "en") else team
        text, cut = _compose({"team": who, "what": _what(lang),
                              "opponent": _opp(lang),
                              "sport": sport_w.get(lang, ""),
                              "day": month_day(day, lang)})
        add(text, lang, f"lang:{lang}"
            + (f"(버림:{'·'.join(cut)})" if cut else ""),
            parts={"team": who, "opponent": _opp(lang),
                   "sport": sport_w.get(lang, ""), "when": _what(lang)})

    # ③ 표기 — 월을 떼고, 팀 약칭으로. 🔴 **현지어 자리다**(영어가 아니다)
    native_lang = _native_lang
    text, cut = _compose({"team": native or team, "what": _what(native_lang),
                          "opponent": _opp(native_lang),
                          "sport": sport_w.get(native_lang, ""),
                          "day": day_only(day, native_lang)})
    add(text, native_lang, "표기:일자" + (f"(버림:{'·'.join(cut)})" if cut else ""),
        parts={"team": native or team, "opponent": _opp(native_lang),
               "sport": sport_w.get(native_lang, ""),
               "when": _what(native_lang)})
    for alias in aliases or []:
        text, cut = _compose({"team": alias, "what": _what(native_lang),
                              "opponent": _opp(native_lang),
                              "sport": sport_w.get(native_lang, ""),
                              "day": month_day(day, native_lang)})
        add(text, native_lang,
            "표기:약칭" + (f"(버림:{'·'.join(cut)})" if cut else ""),
            parts={"team": alias, "opponent": _opp(native_lang),
                   "sport": sport_w.get(native_lang, ""),
                   "when": _what(native_lang)})

    # ④ 매체명 추가 — §13-b 가 **이름을 댄 매체만**. 🔴 지어내지 않는다.
    #    ⚠️ `1차 소스` 칸에서 첫 토큰을 기계로 뽑으면 `구단` 이 나온다(실측) —
    #       그래서 yaml 의 `media_token` 을 쓰고, 계약이 그 값이 정본 칸에 실제로
    #       있는지 대조한다. 정본이 구체 매체를 안 대는 행은 이 축을 **건너뛴다.**
    media = str((row or {}).get("media_token") or "").strip()
    if media:
        mlang = str(row.get("lang") or lang0)
        # 🔴 §4-1 — 매체명이 **한 요소**다(그 매체가 그 경기를 쓴다)
        add(f"{native or team} {_what(mlang)} {media}", mlang, "매체명",
            parts={"team": native or team, "when": _what(mlang),
                   "competition": media})

    # ⑤ 시점 — 오늘 → 전날 예고 기사
    # 🔴 **전날 축도 현지어다** — 그 기사는 현지 매체가 쓴다
    text, cut = _compose({"team": native or team, "what": _what(native_lang),
                          "opponent": _opp(native_lang),
                          "sport": sport_w.get(native_lang, ""),
                          "day": month_day(_yesterday(day), native_lang)},
                         # 🔴 이 축은 **날짜가 요점이다**(전날 예고 기사) — 날짜를
                         #    상대보다 먼저 넣는다. ⚠️ 날짜를 버리면 이 축이
                         #    `lang:` 축과 똑같아지고 중복으로 사라진다.
                         order=("team", "what", "day", "opponent", "sport"))
    add(text, native_lang, "시점:전날" + (f"(버림:{'·'.join(cut)})" if cut else ""),
        parts={"team": native or team, "opponent": _opp(native_lang),
               "when": month_day(_yesterday(day), native_lang),
               "competition": _what(native_lang)})
    return out


def _yesterday(day: date) -> date:
    return day - timedelta(days=1)


def _fill(template: str, *, team: str, day: date, lang: str,
          venue: str = "") -> str:
    """§13-b 검색어 틀을 채운다. 🔴 **못 채운 칸은 지운다** — `{球場}` 를 그대로
    던지면 중괄호가 검색어에 들어가 0건이 된다.

    ⚠️ 구장·날짜 형식은 리그마다 다르므로 **정본 표의 낱말을 그대로** 키로 쓴다
       (`{月日}`·`{date}`·`{날짜}`) — 이름을 바꿔 적으면 그것이 사본이다.
    """
    md = month_day(day, lang)
    out = template
    for key, val in (("{月日}", md), ("{date}", md), ("{날짜}", md),
                     ("{team}", team), ("{팀}", team), ("{球団}", team),
                     ("{隊}", team)):
        out = out.replace(key, val)
    # 🔴 구장은 **알 때만** 채운다. 모르면 아래에서 지운다 — 지어내지 않는다.
    if venue:
        out = out.replace("{球場}", venue).replace("{구장}", venue)
    # 남은 칸(`{球場}` 등)은 아직 모른다 — 지우고 넓게 던진다(§19-b-1)
    out = _BRACE.sub(" ", out)
    return " ".join(out.split())


def admissible(items: list[Variant]) -> tuple[list[Variant], list[str]]:
    """§12-b 규칙으로 **규칙 변형까지** 걸러 낸다. 반환은 `(쓸 것, 버린 사유)`.

    🔴 L5 출력만 거르면 안 된다 — §13-b 표의 검색어나 긴 팀명이 6낱말을 넘길 수
       있고, 그것을 그대로 던지면 0건이 난다. 0건은 "없음"이 아니라 unknown 이므로
       (§7-5e) 사유가 남아야 한다.
    ⚠️ 버린 것을 **이름으로** 돌려준다 — 개수만 세면 어느 축이 막혔는지 사라진다.
    """
    kept: list[Variant] = []
    dropped: list[str] = []
    for v in items:
        if llm.query_ok(v.text):
            kept.append(v)
        else:
            dropped.append(f"{v.axis}: §12-b 위반 {v.text!r}")
    return kept, dropped


def _norm(text: str) -> str:
    return "".join(text.split()).lower()


_BRACE = re.compile(r"\{[^}]*\}")


# ══════════════════════════════════════════════════════════════════
# L5 변형 — 🔴 `query_ok` 를 통과한 것만 쓴다
# ══════════════════════════════════════════════════════════════════

_L5_PROMPT = """반증 조건을 웹 검색어로 바꾼다.

조건: {condition}
언어: {langs}

규칙(어기면 버려진다):
- 1~6 낱말
- 연도를 쓰지 않는다
- site: · 따옴표 · 마이너스 연산자를 쓰지 않는다
- 조건에 없는 사실을 넣지 않는다
"""


async def from_llm(condition: str, *, league: str = "", pool=None,
                   budget: llm.Budget | None = None, n: int = 4
                   ) -> tuple[list[Variant], list[str]]:
    """🔴🔴 **L5 변형(Ollama)을 지웠다** — 사용자 지시 2026-10-06(2차) ⑤.

    🔴 실측 2026-10-06: v6 가 이 경로를 **한 번도 부르지 않는다**(질의는
       `s3_docs.queries_for` 가 코드로 만든다 · 문지기는 `llm.query_ok` 하나다).
    ⚠️ 사유를 남기고 빈손으로 돌아간다 — 조용히 `[]` 를 내지 않는다(#3).
    """
    said = ("🔴 옛 L5 변형(Ollama) 경로를 지웠다(2026-10-06 ⑤) — "
            "질의는 v6 `s3_docs.queries_for` 가 코드로 만든다")
    logger.info("[L5] %s · condition=%s", said, condition)
    return [], [said]


async def _reject(pool, stage: str, reason: str, raw) -> None:
    """§17-g-4 — 버린 LLM 출력을 `extraction_rejected` 에 남긴다.

    ⚠️ **적재 실패가 수집을 멈추지 않는다.** 기록은 진단이고, 진단을 못 남긴
       것이 수집 실패보다 가벼운 사고다. 🔴 대신 로그에는 남는다.
    """
    if pool is None:
        return
    try:
        await pool.execute(
            "INSERT INTO extraction_rejected (task, stage, reason, raw, model) "
            "VALUES ('L5', $1, $2, $3::jsonb, $4)",
            stage, reason,
            json.dumps(raw, ensure_ascii=False) if raw is not None else None,
            llm.MODEL)
    except Exception as exc:                    # noqa: BLE001
        logger.warning("[L5] extraction_rejected 적재 실패: %s", exc)


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **카탈로그 검색어** — 유형이 자기 템플릿을 들고 있다
# ══════════════════════════════════════════════════════════════════
#
# 사용자 설계 2026-10-02: *"유형마다 템플릿 3~4개를 순서대로, 관련 0건이면 다음 템플릿"*.
#
# 🔴 **무엇을 찾을지는 코드가 정한다.** 모델에게 묻지 않는다 — 8B 가 가장 못하는 판단이
#    그것이다(사용자 진단). 원본은 `config/variable_types.yaml` 의 `templates` 다.
# ⚠️ 템플릿 **개수·상한은 실제 테스트로 정한다**(사용자 지시) — 여기 숫자를 박지 않는다.


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **§2 질의 생성 규칙** — 지시서 2026-10-06
# ══════════════════════════════════════════════════════════════════
#
# 실측 질의(카드 원문):
#
#     §12-b 위반 'Georgia squad 2 UEFA Nations League B Grp. 2'
#     §12-b 위반 'Northern Ireland national team return Oct 5'
#
# 🔴 템플릿 변수에 **대회 전체명(조 포함)과 날짜**가 그대로 들어가 문지기에
#    걸렸다. ⚠️ **문지기는 안 바꾼다** — 맞게 막았다. 고칠 곳은 만드는 쪽이다.

#: 🔴 템플릿에 쓸 수 있는 **전부**다(지시서 §2). ⚠️ 날짜·숫자·조 번호·라운드는
#   **금지** — `time_range=week` 가 날짜를 대신한다.
TEMPLATE_SLOTS: tuple[str, ...] = ("team", "opp", "comp", "coach", "player",
                                   "word")

#: 🔴 대회명에서 **걷어 내는 꼬리** — 조·라운드·시즌·리그 등급.
#   ⚠️ 매핑 표가 필요하면 `config/competition_short.yaml` 이 든다(데이터).
#      표에 없으면 **꼬리 제거 규칙만** 적용한다(지시서 §2).
_COMP_TAIL = re.compile(
    r"\s*(?:"
    r"grp\.?\s*[a-z0-9]*"            # Grp. 2 · Grp A
    r"|group\s*[a-z0-9]*"            # Group A
    r"|round\s+of\s+\d+"            # Round of 16
    r"|matchday\s*\d*"
    r"|quarter[- ]?finals?|semi[- ]?finals?|finals?"
    r"|playoffs?|play-?offs?"
    r"|\d{4}[-/]\d{2,4}"             # 2026-27
    r"|\d{4}"                        # 2026
    r"|premier\s+division|division\s*[a-z0-9]*"
    r"|리그|시즌"
    r")\s*$", re.I)

#: 🔴 **리그 등급 한 글자**(`Nations League B`) — 꼬리를 걷은 뒤에 본다.
_COMP_TIER = re.compile(r"\s+(?:league\s+)?[A-D]\s*$")

#: 🔴 그 뒤에도 남는 **머리 수식** — `UEFA` 처럼 기구 이름. ⚠️ 전부 걷지 않는다:
#   `CONCACAF Nations League` 는 `Nations League` 와 **다른 대회**다(지시서 예시가
#   `UEFA …` 만 걷었다). 그래서 **UEFA 하나만** 선언으로 걷는다.
_COMP_HEAD: tuple[str, ...] = ("UEFA",)


def competition_short(full: object) -> str:
    """🔴🔴 **대회 짧은 이름** — 정본 하나다(사본 금지 · 지시서 §2).

    ```
    UEFA Nations League B Grp. 2      → Nations League
    CONCACAF Nations League A Grp. 2  → CONCACAF Nations League
    FIFA ASEAN Cup Premier Division   → FIFA ASEAN Cup
    KBO 리그                           → KBO
    ```

    ⚠️ 표가 먼저다(`config/competition_short.yaml`) — 없으면 꼬리 제거 규칙만.
    🔴 **빈 글자를 돌려주지 않는다** — 다 걷혀 비면 원래 이름을 쓴다(그것이
       질의를 못 만드는 것보다 낫고, §12-b 가 그 뒤를 다시 본다).
    """
    said = " ".join(str(full or "").split())
    if not said:
        return ""
    from app import rules as _R
    table = dict((_R._load("config/competition_short.yaml") or {}).get(
        "short") or {})
    if said in table:
        return str(table[said])
    out = said
    for _ in range(4):                      # 🔴 꼬리가 겹쳐 붙는다(`B Grp. 2`)
        cut = _COMP_TAIL.sub("", out).strip()
        cut = _COMP_TIER.sub("", cut).strip()
        if cut == out:
            break
        out = cut
    for head in _COMP_HEAD:
        if out.lower().startswith(head.lower() + " "):
            out = out[len(head) + 1:].strip()
    return out or said


def slot_value(raw: object) -> str:
    """🔴🔴 **자리표에 넣을 값을 질의에 쓸 수 있게** 다듬는다(지시서 §2 뒤 실측).

    ⚠️ 실측 2026-10-06: `Michael O'Neill` 이 든 질의가 **전부** §12-b 에 걸렸다 —
       `llm._BAD_QUERY` 가 `["\'()]` 를 막기 때문이다. 🔴 그래서 감독 이름에
       어깻점이 있는 팀(북아일랜드·아일랜드…)은 `coach_conflict`·
       `squad_rotation` 질의가 **구조적으로 0건**이었다.

    🔴 **문지기를 완화하지 않는다**(§8 금지) — 어깻점이 연산자가 아닌 것은 맞지만,
       그 판단은 문지기 몫이다. 여기서는 **값을 질의에 쓸 수 있는 글자로** 바꾼다.
    ⚠️ 지우지 않고 **공백으로** 바꾼다 — 검색 엔진은 `O'Neill` 을 `o neill` 로
       쪼개므로 `O Neill` 이 같은 기사를 찾는다. 🔴 `ONeill` 로 붙이면 아무
       기사에도 없는 글자가 된다.
    """
    said = str(raw or "")
    for ch in "\"'()":
        said = said.replace(ch, " ")
    return " ".join(said.split())


def slots_in(tpl: object) -> list[str]:
    """🔴 그 템플릿이 쓰는 자리표들 — `{team}` → `team`."""
    return [m.strip("{}") for m in re.findall(r"\{[a-z_]+\}", str(tpl or ""))]


#: 🔴🔴 **사전 검사용 고정물 3경기**(지시서 §2) — 실측에서 걸린 경기들이다.
PRECHECK_GAMES: tuple[dict, ...] = (
    {"team": "Indonesia", "opp": "Thailand",
     "comp": "FIFA ASEAN Cup Premier Division",
     "coach": "Patrick Kluivert", "player": "Ole Romeny", "word": "결장"},
    {"team": "Northern Ireland", "opp": "Georgia",
     "comp": "UEFA Nations League B Grp. 2",
     "coach": "Michael O'Neill", "player": "Conor Bradley", "word": "결장"},
    {"team": "KIA Tigers", "opp": "LG Twins", "comp": "KBO 리그",
     "coach": "이범호", "player": "양현종", "word": "선발"},
)


def template_precheck(extra: object = None) -> list[str]:
    """🔴🔴 **M129 — 모든 템플릿을 고정물 3경기로 렌더링해 문지기에 넣는다.**

    > 봇 시작 시 … §12-b 문지기와 길이 규칙(3~10단어)을 통과하는지 확인한다.
    > 하나라도 걸리면 **시작 실패**(조용히 건너뛰지 않는다).

    돌려주는 것은 **걸린 것들의 사유 줄**이다 — 비면 통과다.
    ⚠️ 자리표가 허용 목록 밖이면 그것도 걸린 것이다(날짜·숫자 금지).
    """
    from app import llm as _llm
    from app import rules as _R
    rows: list[tuple[str, str, str]] = []
    for vtype in sorted(_R.variable_types()):
        for tpl, lang in _R.type_templates_tagged(vtype):
            rows.append((vtype, tpl, lang))
    for row in (extra or ()):
        rows.append((str(row[0]), str(row[1]),
                     str(row[2]) if len(row) > 2 else ""))
    bad: list[str] = []
    for vtype, tpl, _lang in rows:
        off = [x for x in slots_in(tpl) if x not in TEMPLATE_SLOTS]
        if off:
            bad.append(f"{vtype}: 금지된 자리표 {off} — {tpl!r} "
                       f"(날짜·숫자·조 번호는 `time_range=week` 가 대신한다)")
            continue
        for game in PRECHECK_GAMES:
            box = dict(game)
            box["comp"] = competition_short(box["comp"])
            said = tpl
            for k, v in box.items():
                said = said.replace("{" + k + "}", slot_value(v))
            said = " ".join(said.split())
            # ══════════════════════════════════════════════════════
            # 🔴🔴 **문지기는 하나다** — 사용자 지시 2026-10-06 ⑧
            # ══════════════════════════════════════════════════════
            #
            #  > 삭제 후 `app/` 전체 정적 검사(**문지기 하나** · `llm.py` 밖 HTTP 금지) 켜기
            #
            #  ⚠️ 종전엔 둘을 **둘 다** 봤다(`querygate.gate` 10낱말 · `llm.query_ok`
            #     1~6낱말). 🔴 실제로 거르는 것은 **`llm.query_ok`** 이고(v6 §6 이
            #     *"남길 쪽 기준: 오픈월드 ⑥-2 와 s3 질의 모두 통과시키는 쪽"* 이라
            #     적었다), s3 의 `gate_ok` 도 그 하나를 지난다.
            #  🔴 그래서 `querygate` 를 지웠다 — 두 번째 문지기는 없다.
            n = len(said.split())
            if not _llm.query_ok(said):
                bad.append(f"{vtype}: {said!r} — 🔴 §12-b(`llm.query_ok`) 가 "
                           f"막는다(낱말 {n}개 · 1~6 · 연도·연산자 금지)")
    return bad


def assert_templates_ok(extra: object = None) -> None:
    """🔴 걸리면 **터진다** — 지시서 §2: *"하나라도 걸리면 시작 실패."*"""
    bad = template_precheck(extra)
    if bad:
        raise ValueError(
            "🔴 질의 템플릿 사전 검사 실패(지시서 §2 · M129) — 조용히 건너뛰지 "
            "않는다:\n  " + "\n  ".join(bad))




def _alias_rows(vtype: str, tpls: list, slots: dict, langs, day) -> list[Variant]:
    """🔴🔴 **검색 사다리 ②③④** (사용자 기술 지시 2026-10-03 · 기술 1·2).

    ══════════════════════════════════════════════════════════════════
    > ② `{alias_local} {opp} {local_word_xi}`      현지어+별칭
    > ③ `{coach} {opp} {local_word_presser}`       감독 회견
    > ④ `{alias} {local_word_injury} site:{outlet}` 현지 매체 지정
    ══════════════════════════════════════════════════════════════════

    ① (일반 영어)은 `templates` 가 이미 한다. 여기는 **그 뒤의 세 단**이다.

    🔴 **이름 × 낱말 × 언어**로 만든다 — 유형마다 언어마다 템플릿을 적으면 곱셈으로
       늘어나므로, 낱말은 `search_words.yaml` 에 **개념 한 번**만 적고 유형이
       그것을 가리킨다(`variable_types.yaml` 의 `word:`).
    ⚠️ 별칭은 **그 언어의 것만** 쓴다 — `ホークス` 를 영어 질의에 넣으면 영어 매체에
       없는 글자가 된다.
    🔴 선언이 없으면(별칭·감독·매체 어느 것도) **빈 목록**이다 — 종전 경로 그대로다.
    """
    del tpls                      # 🔴 이 단들은 템플릿을 쓰지 않는다
    from app import entities, rules
    team = str(slots.get("team") or "")
    if not team:
        return []
    concept = rules.word_concept(vtype)
    if not concept:
        return []
    opp = str(slots.get("opponent") or "")
    coach, _why = entities.coach_of(team)
    outlets = entities.outlets_of(team)
    out: list[Variant] = []
    seen: set[str] = set()

    def _add(text: str, lang: str, rung: str, src: str) -> None:
        got = " ".join(str(text).split())
        if not got or _norm(got) in seen:
            return
        seen.add(_norm(got))
        out.append(Variant(text=got, lang=lang,
                           axis=f"사다리{rung}:{vtype}", source=src))

    for lang in langs:
        for word in rules.local_words(concept, lang):
            # ② 현지어 + **별칭**(없으면 공식명) + 상대
            for name in (entities.aliases_of(team, lang=lang) or [team]):
                _add(f"{name} {opp} {word}", lang, "②", f"alias:{name}")
            # ③ **감독 회견** — 감독 이름이 검색어가 된다(사용자: `Speid` 로 찾았다)
            if coach:
                for pw in rules.local_words("presser", lang) or [word]:
                    _add(f"{coach} {opp} {pw}", lang, "③", f"coach:{coach}")
            # ④ **현지 매체 지정** — `site:` 로 그 매체 안만 본다
            for site in outlets[:2]:
                name = (entities.aliases_of(team, lang=lang) or [team])[0]
                _add(f"{name} {word} site:{site}", lang, "④", f"outlet:{site}")
    return out
