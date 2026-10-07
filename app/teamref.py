"""🔴🔴 **이름표는 ID 밑에 붙는다** — 1단계(사용자 지시 2026-10-03).

══════════════════════════════════════════════════════════════════
🔴 병의 정체 — *"이름을 신원으로 쓴다"*
══════════════════════════════════════════════════════════════════

사용자 진단 2026-10-03:

> 봇은 팀과 경기를 **이름 문자열로 식별**한다. 단계를 넘어갈 때마다 이름을 다시
> 비교하고, 비교하는 쪽과 저장한 쪽의 **언어가 다르면 자기가 찾은 걸 버린다.**

| 사례 | 저장한 이름 | 다시 찾은 이름 | 결과 |
|---|---|---|---|
| J리그 | `柏レイソル` | `가시와 레이솔` | 찾은 페이지 **폐기** |
| 자동완성 | `크로아티아` | `Croatia` | 정확한 경기를 집고도 **폐기** |
| `slate.find` | `Croatia`(표) | `크로아티아`(검색) | *"창 밖"* 이라는 **거짓 사유** |

🔴 **이 파일이 그 뿌리를 고친다**: 이름은 **ID 에 붙는 라벨**이고, 신원은 ID 다.

══════════════════════════════════════════════════════════════════
🔴 어디서 이름을 받나 — **지어내지 않는다**
══════════════════════════════════════════════════════════════════

| 출처 | 무엇 | 비용 |
|---|---|---|
| **CLDR**(`babel`) | 나라 294개 × ko·en·ja·es·zh | 🔴 **네트워크·robots·키 0** |
| `config/nations.yaml` | ISO 가 없는 **축구협회 넷**(잉글랜드·스코틀랜드·웨일스·북아일랜드) | 손으로 — **그 넷뿐이다** |
| `league_index` 캐시 | 클럽의 외부 id·현지 표기(`柏レイソル`) | 받아 둔 것 |
| `app/bot/aliases.py` | 사용자가 쓰는 한국어 별칭 | 저장소에 있던 것 |
| `config/entities.yaml` | 사용자가 직접 준 별칭 | 사용자 |

⚠️ 모든 이름이 **어디서 왔는지**를 함께 들고 다닌다(`by`). 출처 없는 이름은
   담지 않는다 — 그래야 *"지어냈나"* 를 나중에 되짚을 수 있다(CLAUDE.md #4).

🔴 **합치지 않는 것**: 리그가 다르면 다른 팀이다. `Tigers` 는 KBO(기아)·MLB
   (디트로이트)·NPB(한신)에 다 있다 — 이름이 같다고 묶으면 **남의 경기를 분석한다**.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
NATIONS = "config/nations.yaml"
TEAMS54 = "config/teams_54.yaml"
#: 🔴 만든 이름표를 두는 곳. ⚠️ 저장소에 커밋하지 않는다(`var/` 는 ignore 다).
#: 🔴🔴 **발급한 번호를 못 박는 자리.** ⚠️ 번호는 **한 번 주고 안 바꾼다**.
#
#  ⚠️ 번호를 메모리에서만 세면 **표가 자랄 때마다 밀린다** — 어제 `team:000273`
#     이던 팀이 오늘 `team:000274` 가 되고, 그러면 저장된 카드·원장이 **다른
#     팀의 것**이 된다(그것이 이름 열쇠와 똑같은 병이다).
#  🔴 그래서 **외부 id → 번호**를 파일에 적어 둔다. 다음 실행은 그것을 읽는다.
#  ⚠️ `var/` 는 ignore 다 — 지워지면 번호가 다시 발급된다. 🔴 영구 저장은
#     `db` 로 옮길 자리이고(선수가 `player_alias` 표를 쓰듯), 그 전까지는
#     **이 파일이 그 역할**이다. 그 한계를 숨기지 않는다.
KEYS = ROOT / "var" / "team_keys.json"


def norm(name: str) -> str:
    """🔴 대조용 꼴. **지우기만 한다** — 글자를 바꾸거나 음차하지 않는다.

    ⚠️ `app/league_index.norm` 과 **같은 규칙**이어야 한다. 두 곳이 다르게
       정규화하면 같은 이름이 서로 다른 열쇠가 되고, 그것이 이 병의 모양이다.
       🔴 그래서 **그 함수를 부른다** — 여기서 다시 적지 않는다(사본 금지).
    """
    from app import league_index
    return league_index.norm(name)


#: 🔴 **글자가 언어를 말한다.** ⚠️ 출처가 붙여 준 언어 꼬리표를 믿지 않는다 —
#   실측 2026-10-03: 리그 명단이 `柏レイソル` 을 그 리그의 "현지어"라며 넣었는데
#   KBO 명단의 한글 별칭도 같은 길로 들어와 **한글 칸에 일본어가 섞였다.**
#   🔴 비라틴은 글자로 갈린다 — 가나·한자는 `ja`, 한글은 `ko`, 나머지 라틴은 `en`.
_SCRIPT = (
    ("ko", lambda c: "\uac00" <= c <= "\ud7a3"),
    ("ja", lambda c: "\u3040" <= c <= "\u30ff"),
    ("zh", lambda c: "\u4e00" <= c <= "\u9fff"),
)


def lang_of(name: str, said: str = "") -> str:  # noqa: D401
    """🔴 그 표기의 언어. **글자가 꼬리표를 이기되, 라틴은 꼬리표를 믿는다.**

    ⚠️ 비라틴은 글자로 확실히 갈린다(한글·가나·한자). 🔴 **라틴은 못 가른다** —
       `England`·`Inglaterra`·`Inghilterra` 가 전부 라틴이다. 실측 2026-10-03:
       라틴을 전부 `en` 으로 뭉갰더니 `잉글랜드` 의 영어 표기가 **`Inglaterra`**
       (스페인어)로 나왔다 — 그 질의는 영어 매체에서 죽는다.
    🔴 그래서 라틴이면 **출처가 말한 언어**(`said`)를 그대로 쓴다. 출처가 없으면
       `en` 이다(가장 흔한 쪽이고, 틀려도 영어 질의는 대개 듣는다).
    """
    s = str(name or "")
    if any(_SCRIPT[1][1](c) for c in s):
        return "ja"
    for tag, hit in _SCRIPT:
        if any(hit(c) for c in s):
            return tag
    # ══════════════════════════════════════════════════════════════════
    # 🔴 **라틴 글자에 비라틴 꼬리표를 붙이지 않는다**(실측 2026-10-04)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 리그 명단 경로가 *"이 리그의 현지어는 `ko`"* 라며 `LG Twins`(라틴)에
    #     `ko` 를 붙였다. 그러자 한국어 칸의 대표가 **`LG Twins`** 가 되어
    #     한국어 질의가 영어로 나갔다.
    #  🔴 꼬리표를 믿는 것은 **라틴끼리 가를 때**(en/es/pt)뿐이다. 꼬리표가
    #     비라틴을 가리키면 그것은 **그 이름의 언어가 아니다.**
    want = str(said or "en")
    if want in ("ko", "ja", "zh"):
        return "en"
    return want


#: 🔴🔴 **조직 표시** — 팀 이름의 앞뒤에 붙는 법인·구단 표기(사용자 지시 2026-10-04).
#
#  > (a) 조직 표시(FC·CF·AFC·SC·AC·SK·BK·Club·Calcio)는 **앞뒤 어디 붙어도** 걷는다
#
#  ⚠️ 실측 2026-10-03: 별칭표는 `Manchester City`·`Barcelona` 로 적고 자료는
#     `Manchester City FC`·`FC Barcelona` 로 준다. 한 토막 차이로 **55개가
#     안 풀렸다**(맨시티·바르셀로나·뮌헨·고베·대구 …).
#  🔴 **걷은 뒤 둘 이상이 겹치면 그 이름은 안 쓴다**(아래 `build`) — 걷기가
#     서로 다른 팀을 하나로 만들면 그것이 **남의 경기를 분석하는** 길이다.
ORG_MARKS = frozenset({
    "fc", "cf", "afc", "sc", "ac", "sk", "bk", "cd", "ud", "rc", "ss",
    "club", "calcio", "fk", "if", "aik", "sv", "vfl", "vfb", "tsv", "bsc",
})


def bare(name: str) -> str:
    """🔴🔴 **조직 표시를 걷은 꼴.** 대조에만 쓴다 — 표시용 이름이 아니다.

    걷는 것 셋(사용자 지시 2026-10-04 ①):
      (a) **조직 표시**(`FC`·`CF`·`AFC`·`SC`·`AC`·`Club`·`Calcio` …) — 앞뒤 어디든
      (b) **분음 부호·대소문자·공백** — `_plain` 이 한다
      (c) 🔴 **창단 연도**(`1. FSV Mainz **05**` · `Bayer **04** Leverkusen`)와
          `&`↔`and` — 실측 2026-10-03 에 그 둘이 여덟 개를 막고 있었다

    ⚠️ 걷는 것은 **독립된 토막**뿐이다. `Barcelona` 안의 글자를 건드리지 않는다.
    🔴 전부 걷으면 빈 문자열이 된다(`FC`) — 그때는 **안 걷은 것**을 돌려준다.
       빈 열쇠는 모든 이름과 겹쳐 이름표를 통째로 망가뜨린다.
    """
    flat = _plain(name).replace("&", " and ").replace(".", " ")
    toks = [t for t in flat.split() if t]
    kept = []
    for t in toks:
        low = t.lower().strip(".")
        if low in ORG_MARKS:
            continue
        # 🔴 **창단 연도·순번**은 걷는다(`05`·`04`·`1`). ⚠️ 이름에 섞인 숫자가
        #    뜻을 가지는 경우(`FC Schalke 04`)도 **같은 처분**이다 — 그 숫자는
        #    팀을 가르는 데 쓰이지 않는다(같은 도시에 둘이 없다).
        if low.isdigit():
            continue
        kept.append(low)
    return "".join(kept) if kept else "".join(t.lower() for t in toks)


#: 🔴 **코드 별칭의 꼴** — `iso:HR` · `fa:ENG` · `tsdb:137708` · `team:000273`.
#   ⚠️ 대조에는 쓰지만 **표기로는 안 쓴다**(검색어가 되면 아무것도 안 나온다).
_CODE = re.compile(r"^(?:iso|fa|tsdb|fdorg|fotmob|team|name):", re.I)


def is_code(name: str) -> bool:
    """🔴 그 글자가 **사람이 부르는 이름이 아니라 코드**인가."""
    return bool(_CODE.match(str(name or "").strip()))


def _plain(s: str) -> str:
    """🔴 **라틴 발음부호만** 벗긴다(`Mónaco` → `Monaco`).

    ══════════════════════════════════════════════════════════════════
    🔴 이 저장소가 **같은 사고를 두 번** 겪었다
    ══════════════════════════════════════════════════════════════════

    `app/ids.py` 가 적어 둔 실사고 2026-09-21: *"`NFKD → ascii ignore` 를 쓰는
    정규화가 한글을 통째로 지워 한국 선수 이름이 **전부 서로 일치**했다."*

    ⚠️ 실측 2026-10-03: 내가 `NFKD` 를 그대로 써서 `크로아티아` 가 **자모로
       분해된 꼴**(10글자)로 한 번 더 담겼다 — 같은 이름이 둘이 됐다.
    🔴 그래서 **라틴 글자에만** NFD 를 적용하고, 결과는 **NFC 로 되돌린다.**
    """
    out = []
    for ch in str(s or ""):
        if ch.isascii() or unicodedata.category(ch) != "Lo":
            # 라틴·기호·공백 — 발음부호를 벗긴다
            for c in unicodedata.normalize("NFD", ch):
                if not unicodedata.combining(c):
                    out.append(c)
        else:
            # 🔴 한글·가나·한자는 **그대로** 둔다
            out.append(ch)
    return unicodedata.normalize("NFC", "".join(out))


#: 🔴 **출처 등급** — 앞일수록 매체가 실제로 쓰는 표기다. `TeamRef.label` 과
#   `Registry.add` 가 **같은 표**를 본다(두 곳에 적으면 한쪽이 조용히 틀린다).
#   ⚠️ `app/bot/aliases.py`(사용자가 쓸 법한 말)가 **맨 뒤**다 — 거기에는 짧은
#      꼴과 옛 이름이 섞여 있다(`엘지` · `해태 타이거즈`).
SOURCE_ORDER = (
    # ── 🔴 **공식**이 맨 위다(사용자 지적 2026-10-04)
    #
    #  > 54팀 표는 `jleague.jp`·`npb.jp` **공식 사이트**에서 받은 것이다. 공식이
    #  > tsdb(제3자 DB)보다 낮을 수 없다. `KIA Tigers`(공식) vs `Kia Tigers`(tsdb)
    #  > 에서 *"어댑터가 원본"* 이라며 tsdb 를 택한 것도 같은 뒤집힘이다.
    #
    #  ⚠️ 종전엔 `리그 명단`(tsdb)이 맨 위였다 — **거꾸로였다.**
    "jleague.jp",              # 공식 — 실조회
    "npb.jp",                  # 공식 — 실조회
    "kleague.com",             # 공식 — 실조회(301 을 따라가 404=허용 확인)
    # 🔴 **대표팀 표기가 CLDR 보다 먼저다**(실측 2026-10-04): CLDR 은 행정 단위
    #    이름을 준다(`Palestinian Territories`)고, 축구 자료는 `Palestine` 을 쓴다.
    #    ⚠️ 행정 단위 이름도 **지우지 않는다** — 둘 다 그 나라를 가리킨다.
    "실측 2026-10-04 — fotmob",
    "손으로 적음 — CLDR 은",
    "CLDR",                    # 유니코드 컨소시엄 — 표준
    "nations.yaml", "손으로 적음",
    # ── 어댑터가 선언한 것(그 리그를 실제로 수집하는 코드가 쓰는 표기)
    "app/collect/kbo.py",
    # ── 제3자 DB·사용자 별칭
    "리그 명단", "한국어 표기 사전", "config/entities.yaml",
    "외부 id",                  # 🔴 `tsdb:137708` 같은 별명은 **표기가 아니다**
    # ── 🔴 **배운 것은 맨 아래다**(③ 자가 성장). 사람이 적은 것보다 낮다 —
    #    오염이 섞일 수 있고, 섞이면 대표 표기부터 흔들리기 때문이다.
    "학습",
)


def _src_rank(src: str) -> int:
    s = str(src or "")
    return next((i for i, o in enumerate(SOURCE_ORDER) if s.startswith(o)),
                len(SOURCE_ORDER))


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **열쇠는 봇이 발급한다 — 뜻 없는 번호다**(사용자 지적 2026-10-04)
# ══════════════════════════════════════════════════════════════════
#
# > `tsdb:137708` 이던 가시와의 열쇠가 `name:J리그:…` 로 바뀌었다. 이건 *"이름을
# > 신원으로 쓰지 말라"* 는 원칙을 **열쇠 자체에 다시 들여온 것**이다. 이름이 들어간
# > 열쇠는 **표기가 하나만 바뀌어도 ID 가 죽는다** — 실제로 시험에서 저장된 ID 가
# > 죽었고, 나는 *"시험이 옛 열쇠를 박아 둔 것"* 이라며 시험을 고쳤다.
# > 🔴 **틀린 쪽은 시험이 아니라 열쇠다.**
#
# v4 §8 이 선수에 대해 이미 적어 뒀다: *"player_id 는 봇이 발급 … 외부 id 는
# `player_alias` 표에 붙인다."* 🔴 **팀도 같다.**
#
#   열쇠      `team:000731`  — 뜻이 없다. 한 번 발급하고 **절대 안 바꾼다**
#   별칭      `tsdb:137708` · `fdorg:…` · 모든 언어의 이름 — 전부 그 번호 밑
#
# ⚠️ 종전 `name:{리그}:{bare}` 는 **표기가 열쇠**였다. 그러면 자료가 표기를 바꾸는
#    날 그 팀의 모든 기록(카드·원장)이 **다른 팀의 것이 된다.**
TEAM_KEY_PREFIX = "team:"


def _load_keys() -> dict[str, str]:
    """🔴 못 박아 둔 **외부 id → 번호**. 없으면 빈 표(그때 새로 발급된다)."""
    try:
        return {str(k): str(v)
                for k, v in json.loads(KEYS.read_text(encoding="utf-8")).items()}
    except (OSError, ValueError):
        return {}


def _save_keys(reg: "Registry") -> None:
    """🔴 발급한 번호를 못 박는다. ⚠️ 못 쓰면 **사유만 남기고 넘어간다** —
    쓰기 실패로 분석이 죽으면 안 된다(그 다음 실행에 다시 발급될 뿐이다)."""
    try:
        KEYS.parent.mkdir(parents=True, exist_ok=True)
        KEYS.write_text(json.dumps(reg.ext, ensure_ascii=False, indent=0),
                        encoding="utf-8")
    except OSError as exc:                              # pragma: no cover
        logger.info("[teamref] 번호를 못 박지 못했다: %s", exc)


def _new_key(reg: "Registry") -> str:
    """🔴 다음 번호. ⚠️ **뜻을 담지 않는다** — 리그도 이름도 들어가지 않는다.

    🔴🔴 **이미 쓰인 번호를 건너뛴다**(실사고 2026-10-07). ⚠️ 종전엔 `_seq+1` 을
       그냥 줬다 — 그래서 못 박아 둔 번호(`var/team_keys.json`)와 **충돌**했다:
       `USA` 에 발급한 번호가 어제 시카고 파이어에 준 `team:000573` 이었다.
       🔴 그 충돌은 *"한 팀의 기록이 다른 팀 것이 되는"* 바로 그 병이다.
    """
    taken = set(reg.teams) | set(reg.ext.values())
    while True:
        reg._seq += 1
        got = f"{TEAM_KEY_PREFIX}{reg._seq:06d}"
        if got not in taken:
            return got


@dataclass
class TeamRef:
    """팀 하나. 🔴 **열쇠는 ID 이고 이름은 라벨이다.**"""

    key: str
    #: 언어별 이름들. 🔴 **순서가 뜻이다** — 앞이 그 언어의 대표 표기다
    names: dict[str, list[str]] = field(default_factory=dict)
    #: 🔴 이름마다 **어디서 왔나**(`정규화 이름 → 출처`). 출처 없는 이름은 안 담는다
    by: dict[str, str] = field(default_factory=dict)
    league: str = ""
    sport: str = ""

    def label(self, lang: str) -> str:
        """그 언어의 **대표 표기**. 🔴 그 언어가 없으면 **영어**, 그것도 없으면 빈 값.

        ══════════════════════════════════════════════════════════════
        🔴 세 가지를 실측이 고치게 했다 (2026-10-03)
        ══════════════════════════════════════════════════════════════

        ① **다른 언어로 떨어뜨리지 않는다.** `크로아티아` 의 `en` 을 물었는데
           한글이 돌아왔다 — 영어 질의에 한글이 들어가면 그 질의는 죽는다.
           🔴 `lang` → `en` 까지만 본다. 없으면 **빈 문자열**이다(지어내지 않는다).
        ② **출처가 좋은 쪽을 먼저.** 리그 명단·CLDR 이 사람 별칭표보다 낫다.
        ③ **짧은 별칭을 대표로 쓰지 않는다.** `엘지`·`해태 타이거즈` 가 대표가 되면
           매체 표기와 안 맞는다. ⚠️ 그렇다고 긴 쪽이 늘 맞는 것도 아니다
           (`해태 타이거즈` 는 옛 이름이라 **더 길다**) — 그래서 **출처가 먼저**이고
           길이는 같은 출처 안에서만 가른다.
        """
        def _rank(n: str) -> tuple:
            # 🔴 출처 등급이 **먼저**, 같은 등급 안에서만 길이·대소문자로 가른다
            return (_src_rank(self.by.get(norm(n)) or ""), -len(n),
                    0 if n != n.lower() else 1)

        for want in (lang, "en"):
            # 🔴🔴 **코드는 이름이 아니다**(실측 2026-10-04).
            #
            #  ⚠️ `iso:HR`·`fa:ENG`·`tsdb:137708` 은 **대조용 별칭**이다. 그것이
            #     표기 후보에 섞이면 `England` 의 영어 표기가 **`fa:ENG`** 로
            #     나오고, 그 글자로 검색하면 아무것도 안 나온다.
            #  🔴 대조에는 쓰고 **표기로는 안 쓴다** — 두 쓰임이 다르다.
            got = [n for n in (self.names.get(want) or []) if not is_code(n)]
            if got:
                return sorted(got, key=_rank)[0]
        return ""

    def all_names(self) -> list[str]:
        out: list[str] = []
        for got in self.names.values():
            for x in got:
                if x not in out:
                    out.append(x)
        return out


@dataclass
class Registry:
    """이름표 전체. 🔴 **이름 → 열쇠**는 여럿일 수 있다(모호하면 고르지 않는다)."""

    teams: dict[str, TeamRef] = field(default_factory=dict)
    #: 정규화 이름 → 열쇠들. ⚠️ **목록이다** — `Tigers` 는 세 리그에 있다
    index: dict[str, list[str]] = field(default_factory=dict)
    #: 🔴🔴 **조직 표시를 걷은** 열쇠(사용자 지시 2026-10-04 ①).
    #
    #  `Manchester City` ↔ `Manchester City FC` 를 같게 본다.
    #  ⚠️ **겹치면 안 쓴다** — 걷기가 서로 다른 팀을 하나로 만들면 그것이 남의
    #     경기를 분석하는 길이다. `collide` 가 그 이름들을 들고 있다.
    bare_index: dict[str, list[str]] = field(default_factory=dict)
    #: 🔴 걷었더니 **둘 이상**이 된 꼴 — 그 이름은 대조에 안 쓴다(사유로 남는다)
    collide: dict[str, list[str]] = field(default_factory=dict)
    #: 🔴 발급 번호(`team:000731`). ⚠️ 뜻이 없다 — 한 번 주고 안 바꾼다
    _seq: int = 0
    #: 🔴 **외부 id → 우리 열쇠**(`tsdb:137708` → `team:000012`).
    #   ⚠️ 같은 외부 id 가 두 팀에 붙으면 그것은 결함이다(`player_alias` 의
    #      `UNIQUE(source, external_id)` 와 같은 규율) — 로그에 남긴다.
    ext: dict[str, str] = field(default_factory=dict)

    def key_for(self, *, ext: str = "", name: str = "", league: str = "",
                sport: str = "") -> str:
        """🔴🔴 **그 팀의 열쇠를 찾거나 새로 발급한다.**

        찾는 순서: ① 외부 id ② (같은 리그 안) 걷은 이름 ③ 이름 그대로.
        ⚠️ 셋 다 없으면 **새 번호**를 발급한다 — 그 번호는 뜻이 없고 안 바뀐다.
        🔴 외부 id 가 이미 다른 팀에 붙어 있으면 **그 팀을 쓴다**(새로 만들지
           않는다) — 같은 id 가 둘이 되면 신원이 갈린다.
        """
        if ext and ext in self.ext:
            return self.ext[ext]
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **이름으로 먼저 찾고, 그 팀에 외부 id 를 붙인다**(실측 2026-10-04)
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 종전엔 *"외부 id 가 처음 보는 것이면 **새 팀**"* 으로 갔다. 그러면
        #     54팀 표가 먼저 만든 팀(`Kyoto Sanga F.C.`)과 명단이 주는 같은 팀
        #     (`Kyoto Purple Sanga` · `tsdb:139888`)이 **둘로 갈린다.**
        #  🔴 외부 id 는 **그 팀의 별명**이다 — 별명이 처음 보인다고 새 팀이 되는
        #     것이 아니다. 같은 리그에 같은 bare 가 있으면 **그 팀의 별명**이다.
        for cand in (self.bare_index.get(bare(name)) if name else None,
                     self.index.get(norm(name)) if name else None):
            for k in (cand or []):
                ref = self.teams.get(k)
                # ⚠️ **같은 리그 안에서만** 합친다 — `Tigers` 는 세 리그에 있다
                if ref is not None and (not league or not ref.league
                                        or ref.league == league):
                    if ext:
                        self.ext.setdefault(ext, k)
                    return k
        k = _new_key(self)
        self.teams[k] = TeamRef(key=k, league=league, sport=sport)
        if ext:
            self.ext[ext] = k
        return k

    def merge(self, keep: str, drop: str) -> None:
        """🔴🔴 **두 열쇠가 같은 팀이면 합친다**(실측 2026-10-04).

        ⚠️ 한 팀이 두 열쇠로 갈리면 *"어느 쪽으로 가느냐"* 가 **운**에 달린다.
           실측: `Kyoto Sanga F.C.`(54팀 표)와 `Kyoto Purple Sanga`(명단)가
           갈렸고, bare 가 달라(`kyotosangafc` ≠ `kyotopurplesanga`) 이름으로도
           안 묶였다. 🔴 **같은 외부 id** 가 그 둘을 잇는 고리였다.
        🔴 **먼저 발급된 번호가 남는다** — 그래야 못 박아 둔 번호가 안 바뀐다.
        """
        if keep == drop or drop not in self.teams:
            return
        a, b = self.teams[keep], self.teams.pop(drop)
        for lang, names in b.names.items():
            for nm in names:
                a.names.setdefault(lang, [])
                if nm not in a.names[lang]:
                    a.names[lang].append(nm)
        for k, v in b.by.items():
            if _src_rank(v) < _src_rank(a.by.get(k, "")):
                a.by[k] = v
            else:
                a.by.setdefault(k, v)
        a.league = a.league or b.league
        a.sport = a.sport or b.sport
        for box in (self.index, self.bare_index):
            for k, keys in box.items():
                if drop in keys:
                    box[k] = [keep if x == drop else x for x in keys]
                    box[k] = list(dict.fromkeys(box[k]))
        for e, k in list(self.ext.items()):
            if k == drop:
                self.ext[e] = keep
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **사라지는 번호를 지우지 않는다 — 별칭으로 남긴다**
        # ══════════════════════════════════════════════════════════════
        #
        #  사용자 지적 2026-10-04:
        #  > 사라지는 번호는 지우지 말고 **남는 번호를 가리키는 별칭**으로 둬라.
        #  > 열쇠를 바꾼 날 옛 열쇠를 안 지우면 다음 주에 *"경기를 저장했는데
        #  > 못 찾는다"* 가 또 나온다.
        #
        #  🔴 이미 저장된 행이 옛 번호를 들고 있을 수 있다. 그 번호로 물어도
        #     **같은 팀**이 나와야 한다.
        #  ⚠️ `ext` 에 넣으므로 `key_for(ext=옛번호)` 가 바로 새 번호를 준다.
        self.ext[drop] = keep
        self.add(keep, drop, "en", "합쳐진 옛 번호",
                 league=a.league, sport=a.sport)
        logger.info("[teamref] 같은 팀을 합쳤다 — %s ← %s (%s) · 옛 번호는 "
                    "별칭으로 남긴다", keep, drop, a.label("en"))

    def add(self, key: str, name: str, lang: str, by: str, *,
            league: str = "", sport: str = "") -> None:
        """🔴 이름 하나를 ID 밑에 붙인다. **출처(`by`)가 없으면 안 담는다.**"""
        name = " ".join(str(name or "").split())
        k = norm(name)
        if not key or not name or not k or not by:
            return
        ref = self.teams.get(key)
        if ref is None:
            ref = self.teams[key] = TeamRef(key=key, league=league, sport=sport)
        if league and not ref.league:
            ref.league = league
        if sport and not ref.sport:
            ref.sport = sport
        # 🔴 **비라틴은 글자가 꼬리표를 이기고, 라틴은 꼬리표를 쓴다**(위 주석)
        box = ref.names.setdefault(lang_of(name, lang), [])
        if name not in box:
            box.append(name)
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **더 좋은 출처가 오면 올린다**(실측 2026-10-03)
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ `setdefault` 로 두면 **먼저 들어온 출처가 영구히 이긴다.** 실측:
        #     `KIA 타이거즈` 가 별칭표(사용자가 쓸 법한 말)로 먼저 들어와, 뒤에 온
        #     **표기 사전**(매체가 쓰는 정식 표기)으로 안 올라갔다. 그래서 대표가
        #     `해태 타이거즈`(옛 이름)로 남았다.
        #  🔴 출처에도 **등급**이 있다(`TeamRef.label` 의 `order`). 등급이 더 좋으면
        #     덮는다. ⚠️ 같은 등급이면 **먼저 온 것을 지킨다**(뒤에 온 것이 더 낫다는
        #     근거가 없다).
        if _src_rank(by) < _src_rank(ref.by.get(k, "")):
            ref.by[k] = by
        else:
            ref.by.setdefault(k, by)
        keys = self.index.setdefault(k, [])
        if key not in keys:
            keys.append(key)
        # 🔴 조직 표시를 걷은 꼴도 함께 담는다(①). ⚠️ 쓸지 말지는 `find` 가
        #    정한다 — 겹치면 안 쓴다.
        bk = bare(name)
        if bk and bk != k:
            box2 = self.bare_index.setdefault(bk, [])
            if key not in box2:
                box2.append(key)

    def find(self, text: str, *, sport: str = "",
             league: str = "") -> tuple[list[str], str]:
        """🔴🔴 이름 → **열쇠들**과 사유. ⚠️ 하나로 줄이지 않는다.

        *"거짓 매칭보다 미상이 낫다"*(`app/ids.py` 의 규율) — 둘 이상이면 둘 다
        돌려주고, **고르는 것은 부르는 쪽**이 조건을 더 줘서 한다.
        """
        k = norm(text)
        got = list(self.index.get(k) or [])
        why_bare = ""
        if not got:
            # ══════════════════════════════════════════════════════════
            # 🔴🔴 **조직 표시를 걷고 한 번 더**(사용자 지시 2026-10-04 ①)
            # ══════════════════════════════════════════════════════════
            #
            #  실측 2026-10-03: 별칭표 한국어 188개 중 **55개**가 안 풀렸고
            #  대부분이 `Manchester City` ↔ `Manchester City FC` 꼴이었다.
            #  ⚠️ 걷은 뒤 **둘 이상**이면 안 쓴다 — 걷기가 서로 다른 팀을 하나로
            #     만들면 그것이 남의 경기를 분석하는 길이다(모호하면 안 고른다).
            bk = bare(text)
            cand = list(self.bare_index.get(bk) or [])
            if len(cand) == 1:
                got, why_bare = cand, " (조직 표시를 걷고 맞췄다)"
            elif len(cand) > 1:
                return [], (f"🔴 `{text}` 는 조직 표시를 걷으면 **{len(cand)}곳**에 "
                            f"맞는다 {cand} — 걷기로는 못 가린다")
        if not got:
            return [], f"이름표에 `{text}` 가 없다"
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **빈 칸을 "아무거나 맞음"으로 쓰지 않는다**(실측 2026-10-03)
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 처음엔 `not self.teams[x].league or ... == league` 로 짰다. 그러면
        #     리그를 **모르는 항목**(나라는 리그가 없다)이 어느 조건에도 통과해
        #     `Monaco` 를 `iso:MC`(나라)와 `해외축구`(AS 모나코)로 **끝까지 갈라
        #     놓지 못했다** — 조건을 줘도 안 갈렸다.
        #  🔴 조건을 주면 **그 조건을 아는 항목만** 남긴다. 그래도 하나로 안 줄면
        #     **고르지 않는다**(거짓 매칭보다 미상이 낫다).
        for want, pick in ((sport, lambda r: r.sport),
                           (league, lambda r: r.league)):
            if not want:
                continue
            exact = [x for x in got if pick(self.teams[x]) == want]
            if exact:
                got = exact
        if len(got) == 1:
            return got, f"`{text}` → `{got[0]}`{why_bare}"
        return got, (f"🔴 `{text}` 가 **{len(got)}곳**에 있다 {got} — "
                     f"종목·리그를 주면 갈린다(하나를 고르면 추측이다)")


# ══════════════════════════════════════════════════════════════════
# 짓기 — 🔴 출처마다 따로, 그리고 **어디서 왔는지 적는다**
# ══════════════════════════════════════════════════════════════════


def _from_cldr(reg: Registry) -> str:
    """🔴 나라 이름을 **CLDR**(babel)에서. ⚠️ 네트워크·robots·키가 없다.

    사용자 지시 2026-10-03: *"손으로 만들지 말고 CLDR."*
    """
    from babel import Locale
    from app import rules
    langs = [str(x) for x in (rules._load(NATIONS).get("cldr_langs") or [])]
    n = 0
    for lang in langs:
        try:
            box = Locale(lang).territories
        except Exception as exc:                        # noqa: BLE001
            logger.info("[teamref] CLDR `%s` 를 못 읽었다: %r", lang, exc)
            continue
        for code, label in box.items():
            # 🔴 **나라만** 담는다 — 대륙(`002`)·지역(`EU`)은 팀이 아니다
            if not (len(code) == 2 and code.isalpha()):
                continue
            # 🔴 대표팀은 **리그가 없다**(대회만 있다) — `league` 는 비워 두고
            #    `sport` 만 적는다. ⚠️ 빈 칸은 좁히기에서 **안 맞는 것**으로 센다.
            key = reg.key_for(ext=f"iso:{code}", sport="soccer")
            reg.add(key, label, lang, "CLDR", sport="soccer")
            # 🔴 ISO 코드도 **별칭으로** 담는다 — 열쇠가 아니라 별명이다
            reg.add(key, f"iso:{code}", "en", "CLDR(ISO 코드)", sport="soccer")
            # ⚠️ 악센트를 벗긴 꼴도 같은 ID 에 붙인다 — 검색 결과가 그렇게 온다
            plain = _plain(label)
            if plain != label:
                reg.add(key, plain, lang, "CLDR(악센트 제거)", sport="soccer")
            n += 1
    return f"CLDR {len(langs)}개 언어 · 이름 {n}개"


def _from_fifa(reg: Registry) -> str:
    """🔴 **CLDR 이 행정 단위 이름을 주는 자리**(실측 2026-10-04).

    `PS` 는 CLDR 에서 `Palestinian Territories` 인데 대표팀은 **`Palestine`** 이다.
    ⚠️ 그래서 ③ 자가 성장의 첫 수확에서 `중국 vs 팔레스타인` 이 막혔다 —
       조건 ②가 제 일을 한 것이고, 막힌 까닭이 **이름표의 구멍**이었다.
    🔴 ISO 코드가 **같으므로** 같은 번호 밑에 붙는다(새 팀이 안 생긴다).
    """
    from app import rules
    rows = rules._load(NATIONS).get("fifa_names") or []
    n = 0
    for row in rows:
        code = str(row.get("code") or "")
        key = reg.key_for(ext=f"iso:{code}", sport="soccer")
        src = str(row.get("source") or NATIONS)
        for lang, names in (row.get("names") or {}).items():
            for name in (names or []):
                reg.add(key, str(name), str(lang), src, sport="soccer")
                n += 1
    return f"대표팀 표기 {len(rows)}곳 · 이름 {n}개"


def _from_nations(reg: Registry) -> str:
    """🔴 ISO 가 없는 **축구협회 넷**. ⚠️ 손으로 적는 것은 이것뿐이다."""
    from app import rules
    rows = rules._load(NATIONS).get("nations") or []
    n = 0
    for row in rows:
        ext = str(row.get("key") or "")
        src = str(row.get("source") or "")
        key = reg.key_for(ext=ext, sport="soccer")
        reg.add(key, ext, "en", "nations.yaml(협회 코드)", sport="soccer")
        for lang, names in (row.get("names") or {}).items():
            for name in (names or []):
                reg.add(key, str(name), str(lang), src or "nations.yaml",
                        sport="soccer")
                n += 1
    return f"축구협회 {len(rows)}곳 · 이름 {n}개"


def _from_54(reg: Registry) -> str:
    """🔴🔴 **네 리그 54팀** — 명단 API 가 열에서 자르는 자리(사용자 지시 2026-10-04).

    > 한국어·현지어·영어 세 줄짜리 YAML 을 손으로 쓰면 한 시간이고, **시즌 중엔
    > 안 바뀐다.** 명단 API 를 고치려고 호스트를 더 붙이는 것보다 **더 정확하고
    > 더 빠르다.**

    🔴 **명단보다 먼저** 돈다. 그래야 이 54팀이 열쇠를 **먼저 잡고**, 뒤에 오는
       명단(열에서 잘린 것)이 같은 팀을 **또 다른 열쇠로** 만들지 않는다.
    ⚠️ 열쇠는 `name:{리그}:{bare}` 꼴이라 명단이 같은 이름을 줘도 **같은 열쇠**다.
    """
    from app import rules
    rows = rules._load(TEAMS54).get("teams") or []
    n = 0
    for row in rows:
        lg = str(row.get("league") or "")
        names = row.get("names") or {}
        en = str(names.get("en") or "")
        if not en:
            continue
        sport = "baseball" if lg in ("KBO", "NPB") else "soccer"
        key = reg.key_for(name=en, league=lg, sport=sport)
        src = str(row.get("source") or TEAMS54)
        for lang, name in names.items():
            # 🔴 `ko_short` 는 **공식 약칭**이다(`울산`·`포항`) — 사용자가 그렇게
            #    부른다. ⚠️ 언어는 `ko` 이고, 대표 표기는 **정식명**이 이긴다
            #    (`label` 이 같은 출처 안에서 긴 쪽을 고른다).
            reg.add(key, str(name), str(lang).split("_")[0], src,
                    league=lg, sport=sport)
            n += 1
    return f"54팀 표 {len(rows)}팀 · 이름 {n}개"


def _from_eu(reg: Registry) -> str:
    """🔴 유럽 빅클럽 한국어 별칭 — **명단 뒤에** 돈다(실측 2026-10-04).

    ⚠️ `_from_54` 안에 뒀더니 그때는 유럽 클럽이 **아직 이름표에 없어** 하나도
       못 붙었다. 🔴 붙일 대상이 들어온 **뒤에** 붙여야 한다.
    """
    from app import rules
    # ══════════════════════════════════════════════════════════════════
    # 🔴 **유럽 빅클럽 한국어 별칭** — 이름표에 **실재하는 표기에만** 붙인다
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 정식명을 못 찾으면 **새 팀을 만들지 않는다.** 만들면 `뮌헨` 이
    #     `FC Bayern München` 과 **다른 팀**이 되어 이 병을 그대로 재현한다.
    eu = rules._load(TEAMS54).get("aliases_eu") or []
    src2 = str(rules._load(TEAMS54).get("aliases_eu_source") or TEAMS54)
    m, miss = 0, []
    for row in eu:
        formal = str(row.get("formal") or "")
        keys, _why = reg.find(formal)
        if len(keys) != 1:
            miss.append(formal)
            continue
        for ko in (row.get("ko") or []):
            reg.add(keys[0], str(ko), "ko", src2)
            m += 1
    if miss:
        logger.info("[teamref] 유럽 별칭을 못 붙였다(정식명 미상): %s", miss)
    return f"유럽 별칭 {m}개" + (f" · 못 붙임 {len(miss)}: {miss}" if miss else "")





def _from_league_index(reg: Registry) -> str:
    """🔴 클럽 — 받아 둔 명단에서. 외부 id 가 있으면 **그것이 열쇠**다."""
    from app import league_index as LI
    idx = LI.cached_index()
    if not idx:
        return "리그 명단 캐시가 없다 — 클럽 이름표가 비었다"
    n = 0
    banned = 0                      # 🔴 §8-4 금지 출처라 걷은 이름 수
    unverifiable: list[str] = []    # ⚠️ `by` 가 없어 **가릴 수 없는** 리그
    for lg in LI.leagues():
        key_lg = str(lg.get("key"))
        p = LI._cache_path(key_lg)
        if not p.exists():
            continue
        try:
            box = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        sport = LI.sport_of(key_lg)
        langs = LI.langs_of(key_lg)
        local_lang = next((x for x in langs if x != "en"), "en")
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **금지 출처에서 온 이름은 걷는다**(§8-4 · 실측 2026-10-04)
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 실측: `var/leagues/mlb.json` 이 *"공식 API 30팀 · TheSportsDB
        #     10팀"* 을 들고 **7일 동안 그대로** 냈다. 🔴 `_fresh` 는 그것을
        #     막지만 **이 함수는 `_fresh` 를 안 본다** — 캐시 파일을 바로 읽는다.
        #  🔴 통째로 버리지 않는다 — 그러면 공식 API 30팀까지 버린다(과잉 교정).
        #     캐시가 적어 둔 **이름마다의 출처**(`by`)로 **금지 것만** 걷는다.
        #  ⚠️ `by` 가 없는 **옛 캐시**는 가릴 수 없다 — 걷지 않고 **사유만**
        #     남긴다(#3). 도장이 안 맞아 다음 온라인 판에 다시 받고, 그때부터
        #     가려진다. 🔴 못 가리는 것을 "없다"로 적지 않는다.
        src_of = {str(k): str(v) for k, v in (box.get("by") or {}).items()}
        if not src_of:
            unverifiable.append(key_lg)
        for name in (box.get("teams") or []):
            said = LI.spec_banned(src_of.get(LI.norm(name), "")) \
                if src_of else ""
            if said:
                banned += 1
                continue
            ext = (box.get("ext") or {}).get(norm(name), "")
            # 🔴 **열쇠는 발급기가 준다** — 외부 id·이름으로 찾고, 없으면 새 번호.
            #    ⚠️ 여기서 열쇠 문자열을 짓지 않는다(그것이 이름을 신원으로
            #       쓰는 길이다 · 사용자 지적 2026-10-04).
            # ⚠️ 명단은 한 팀의 **대체 표기**를 평평하게 준다(`Kyoto Sanga F.C.`
            #    와 `Kyoto Purple Sanga`). 🔴 외부 id 가 같으면 **같은 팀**이다 —
            #    그래서 id 를 먼저 보고, id 가 없을 때만 이름으로 찾는다.
            key = reg.key_for(ext=ext, name=name, league=key_lg, sport=sport)
            reg.add(key, name, lang_of(name, local_lang), f"리그 명단({key_lg})",
                    league=key_lg, sport=sport)
            if ext:
                # 🔴 외부 id 는 **별칭**이다 — 열쇠가 아니다
                reg.add(key, ext, "en", f"외부 id({key_lg})",
                        league=key_lg, sport=sport)
                # ══════════════════════════════════════════════════════
                # 🔴🔴 **같은 id 를 단 다른 표기들을 함께 묶는다**(실측 2026-10-04)
                # ══════════════════════════════════════════════════════
                #
                #  ⚠️ `tsdb:139888` 에 `kyotosanga`·`kyotopurplesanga`·`京都サンカfc`
                #     셋이 달려 있는데, 명단이 그 셋을 **따로 넘긴다**. 54팀 표가
                #     이미 `Kyoto Sanga F.C.` 로 한 팀을 만들어 둔 상태라
                #     bare 가 달라(`kyotosangafc` ≠ `kyotopurplesanga`) **둘로 갈렸다.**
                #  🔴 같은 외부 id 가 가리키는 이름은 **같은 팀**이다 — 그 셋을
                #     전부 이 열쇠 밑으로 넣는다. 그러면 어느 표기로 와도 하나다.
                for other, oid in (box.get("ext") or {}).items():
                    if oid != ext or other == norm(name):
                        continue
                    for k2 in list(reg.index.get(other) or []):
                        # 🔴 **먼저 발급된 번호가 남는다**(못 박은 번호가 안 바뀐다)
                        a, b = sorted((key, k2))
                        reg.merge(a, b)
                        if b == key:
                            key = a
            n += 1
    said = f"클럽 이름 {n}개"
    if banned:
        said += f" · 🔴 §8-4 금지 출처 **{banned}개 걷었다**"
    if unverifiable:
        # 🔴 **조용한 0 금지** — 못 가린 것을 이름으로 남긴다
        said += (f" · ⚠️ 출처를 **가릴 수 없는** 옛 캐시 "
                 f"{len(unverifiable)}개({', '.join(unverifiable[:4])}) — "
                 f"도장이 안 맞아 다음 온라인 판에 다시 받는다")
    return said


def _from_learned(reg: Registry) -> str:
    """🔴 **배운 별칭**(③ 자가 성장). ⚠️ **새 팀을 만들지 않는다.**

    배운 줄은 `{정규화 이름: {name, key, from_match}}` 다. 그 `key` 가 지금
    이름표에 **없으면 버린다** — 열쇠가 바뀌었거나 그 팀이 사라진 것이고,
    그때 새로 만들면 반쪽짜리 팀이 생긴다.
    """
    from app import learn_names
    box = learn_names.load()
    n, stale = 0, 0
    for row in box.values():
        key = str(row.get("key") or "")
        if key not in reg.teams:
            stale += 1
            continue
        reg.add(key, str(row.get("name") or ""), str(row.get("lang") or "en"),
                f"{learn_names.SOURCE}(경기 {row.get('from_match')})")
        n += 1
    return (f"배운 별칭 {n}개"
            + (f" · 열쇠가 사라져 버린 것 {stale}개" if stale else ""))


def _from_aliases(reg: Registry) -> str:
    """🔴 저장소의 한국어 별칭표 — **정식명이 이미 이름표에 있을 때만** 붙인다.

    ⚠️ 정식명을 모르면 새 열쇠를 만들지 않는다. 그러면 `가시와 레이솔` 이
       `Kashiwa Reysol` 과 **다른 팀**이 되어 이 병을 그대로 재현한다.
    """
    from app.bot.aliases import KR_TEAM_NAMES, TEAM_ALIASES
    n, miss = 0, 0
    for ko, (tag, formal) in TEAM_ALIASES.items():
        sport = {"mlb": "baseball", "kbo": "baseball"}.get(tag, tag)
        keys, _why = reg.find(formal, sport=sport)
        if len(keys) != 1:
            miss += 1
            continue
        reg.add(keys[0], ko, "ko", "app/bot/aliases.py")
        n += 1
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **대표 한국어 표기는 따로 있다**(실측 2026-10-03)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ `TEAM_ALIASES` 는 *"사용자가 쓸 법한 말"* 이라 **짧은 꼴과 옛 이름**이
    #     섞여 있다(`엘지` · `해태 타이거즈`). 그것이 대표가 되면 검색어가
    #     매체 표기와 안 맞는다 — 실측: `기아 타이거즈` 의 대표가 `해태 타이거즈`.
    #  🔴 같은 파일에 **표기 사전**(`KR_TEAM_NAMES`: 영문 → 한국어 정식 표기)이
    #     따로 있다. 그것이 대표다 — 출처 등급을 더 높게 준다.
    kr = 0
    for formal, ko in KR_TEAM_NAMES.items():
        keys, _why = reg.find(formal)
        if len(keys) != 1:
            continue
        reg.add(keys[0], ko, "ko", "한국어 표기 사전")
        kr += 1
    return (f"한국어 별칭 {n}개 · 표기 사전 {kr}개 붙임 · "
            f"정식명을 못 찾아 건너뜀 {miss}개")


def _from_entities(reg: Registry) -> str:
    """🔴 사용자가 직접 준 별칭(`config/entities.yaml`)."""
    from app import entities
    n, miss = 0, 0
    for team in entities._table():
        keys, _why = reg.find(team)
        if len(keys) != 1:
            miss += 1
            continue
        for lang in entities.langs_of(team):
            for name in entities.aliases_of(team, lang=lang):
                reg.add(keys[0], name, lang, "config/entities.yaml")
                n += 1
    return f"사용자 별칭 {n}개 붙임 · 정식명을 못 찾아 건너뜀 {miss}개"


def _from_pins(reg: Registry) -> str:
    """🔴🔴 **못 박아 둔 번호**(`var/team_keys.json`)를 이름표에 되살린다.

    🔴 `name:<정규화 이름>` 꼴 못은 **오픈월드가 발급한 팀**이다(미등록 리그). 그
       이름을 아는 팀이 이미 있으면 **그 팀을 쓴다**(새로 만들지 않는다) — 없으면
       그 번호로 팀을 되살린다. ⚠️ 그래야 다음 실행도 **같은 번호**를 쓴다.
    ⚠️ 이 출처는 **맨 끝**이다 — 진짜 출처(CLDR·명단·별칭)가 먼저 이긴다.
    """
    pins = _load_keys()
    back, kept = 0, 0
    for ext, key in pins.items():
        if not ext.startswith("name:"):
            reg.ext.setdefault(ext, key)
            continue
        name = ext.split(":", 1)[1]
        got = reg.index.get(name) or reg.bare_index.get(name)
        if got:
            # 🔴 그 이름을 **이미 아는 팀**이 있다 — 못을 그 팀으로 옮긴다
            reg.ext[ext] = got[0]
            kept += 1
            continue
        reg.ext.setdefault(ext, key)
        if key not in reg.teams:
            reg.teams[key] = TeamRef(key=key)
        reg.index.setdefault(name, [])
        if key not in reg.index[name]:
            reg.index[name].append(key)
        back += 1
    # 🔴 **번호 자리를 비워 둔다** — 다음 발급이 못 박힌 번호를 덮지 않게
    for key in list(reg.teams) + list(reg.ext.values()):
        try:
            num = int(str(key).split(":", 1)[1])
        except (IndexError, ValueError):
            continue
        reg._seq = max(reg._seq, num)
    return f"못 박은 번호 {len(pins)}개(오픈월드 되살림 {back} · 진짜 팀으로 {kept})"


def build() -> tuple[Registry, list[str]]:
    """🔴 이름표를 만든다. 돌려주는 것은 `(이름표, 출처마다의 사유)`.

    ⚠️ **통신하지 않는다** — CLDR 은 라이브러리이고 클럽은 `league_index` 가 이미
       받아 둔 캐시다. 🔴 이 함수가 네트워크를 때리면 질문마다 멈춘다.
    """
    reg = Registry()
    # 🔴 **54팀 표가 명단보다 먼저다** — 잘린 명단이 같은 팀을 다른 열쇠로
    #    만들지 않게(위 `_from_54` 주석).
    whys = [_from_cldr(reg), _from_fifa(reg), _from_nations(reg), _from_54(reg),
            _from_league_index(reg), _from_eu(reg), _from_aliases(reg),
            _from_entities(reg), _from_learned(reg),
            # 🔴🔴 **못 박아 둔 오픈월드 팀을 되살린다**(실사고 2026-10-07)
            #    ⚠️ `_load_keys` 는 **아무도 안 부르는 죽은 코드**였다 — 그래서
            #       미등록 리그 팀의 번호가 실행마다 **다시 발급**됐다(그 파일
            #       머리말이 경고하는 "번호가 돈다"가 실제로 일어나고 있었다).
            _from_pins(reg)]
    _save_keys(reg)
    logger.info("[teamref] 팀 %d개 · 이름 %d개 · 못 박은 번호 %d개 — %s",
                len(reg.teams), len(reg.index), len(reg.ext), " · ".join(whys))
    return reg, whys


_REG: Registry | None = None


def registry() -> Registry:
    """🔴 한 번만 짓고 재사용한다(프로세스 안에서)."""
    global _REG
    if _REG is None:
        _REG, _ = build()
    return _REG


def key_of(text: str, *, sport: str = "", league: str = "") -> tuple[str, str]:
    """🔴🔴 **이름 → 열쇠 하나**. 모호하거나 모르면 `("", 사유)`.

    ⚠️ 하나로 못 줄이면 **빈 문자열**이다 — *"거짓 매칭보다 미상이 낫다"*.
    """
    keys, why = registry().find(text, sport=sport, league=league)
    return (keys[0] if len(keys) == 1 else ""), why


def label_of(key: str, lang: str) -> str:
    """🔴 그 팀을 **그 언어로** 뭐라고 부르나. 검색어를 만들 때 쓴다.

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **미리 굽지 않은 언어는 CLDR 에서 그때 꺼낸다**(2026-10-04)
    ══════════════════════════════════════════════════════════════════

    ⚠️ 이름표는 `nations.yaml` 의 `cldr_langs`(ko·en·ja·es·zh) 만 미리 굽는다 —
       전부 구우면 나라 294개 × 언어 수십이고, 쓰지 않는 이름이 오탐을 늘린다.
    🔴 그런데 사다리가 Babel 로 **그 경기의 언어**(`mk`·`hr`·`sr`)를 알게 되자
       그 언어의 이름이 **없어서** 질의가 섞였다(실측 2026-10-04):

           `North Macedonia состав Scotland фудбал`
            ^^^^^^^^^^^^^^^ 🔴 영어다. 마케도니아 매체는 `Северна Македонија` 다

    🔴 **같은 CLDR 한 번 더 부르면 된다** — `Locale('mk').territories['MK']`.
       네트워크·robots·키가 없고, 나라 코드는 이름표가 **이미 담고 있다**.
    ⚠️ 구워 둔 것이 **먼저**다 — 사용자 선언(`fifa_names`)이 CLDR 행정 단위
       이름보다 낫다(`Palestine` vs `Palestinian Territories`).
    """
    ref = registry().teams.get(key)
    if ref is None:
        return ""
    # 🔴 **그 언어가 실제로 있나**를 먼저 본다. ⚠️ `ref.label()` 은 없으면
    #    **영어로 떨어뜨린다** — 그 떨어짐이 CLDR 대체를 가로막았다(실측 2026-10-04:
    #    `label_of(북마케도니아, 'mk')` 가 `'North Macedonia'` 를 돌려줬다).
    if [x for x in (ref.names.get(str(lang)) or []) if not is_code(x)]:
        return ref.label(lang)
    got = _cldr_label(ref, lang)
    return got or ref.label(lang)


def _cldr_label(ref: "TeamRef", lang: str) -> str:
    """🔴 나라 코드 → 그 언어의 CLDR 이름. 대표팀이 아니면 **빈 문자열**."""
    codes = [nm.split(":", 1)[-1] for box in ref.names.values() for nm in box
             if is_code(nm) and nm.startswith("iso:")]
    if not codes or not lang:
        return ""
    try:
        from babel import Locale
        box = Locale(str(lang)).territories
    except Exception:                                       # noqa: BLE001
        return ""
    for code in sorted(set(codes)):
        got = str(box.get(code.upper()) or "").strip()
        if got:
            return got
    return ""


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 ④ **후보 제시** — 보여 주기만 한다(사용자 설계 2026-10-04)
# ══════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **오픈월드 — 이름표에 없는 팀에 열쇠를 발급한다**(실측 2026-10-07)
# ══════════════════════════════════════════════════════════════════
#
# ⚠️ 실사고 2026-10-07: MLS(시카고–밴쿠버)는 **등록 리그가 아니다**. 봇이 ⑥단으로
#    경기 페이지를 찾아 `fotmob:5071211` 까지 쥐었는데, `ref_from_row` 가
#    `key_of(이름)` 으로 **빈 열쇠**를 받아 `adapt.ref_of` 가 그 경기를 **거부했다**
#    (*"열쇠나 킥오프가 비었다"*). 🔴 카드는 이미 *"오픈월드 — 팀 열쇠 임시 발급"*
#    이라고 적고 있었는데 **그 발급이 어디에도 없었다**(없는 코드를 말하는 글이었다).
#
# 🔴 그래서 **여기서 발급한다.** 발급한 번호는 `name:<정규화 이름>` 꼴의 외부 id 로
#    `var/team_keys.json` 에 못 박는다 — 다음 실행이 **같은 번호**를 쓴다(번호가 돌면
#    쌓인 카드·원장이 다른 팀 것이 된다 · 그 파일 머리말이 경고하는 바로 그 병).
# ⚠️ 발급은 **이름표가 모를 때만**이다. 알면 그 열쇠를 쓴다(새 팀을 만들지 않는다).


def key_or_issue(text: str, *, sport: str = "", league: str = ""
                 ) -> tuple[str, str]:
    """🔴 이름 → 열쇠. 이름표가 모르면 **임시 열쇠를 발급**한다. `(열쇠, 사유)`.

    ⚠️ 이름이 비면 발급하지 않는다(빈 이름에 번호를 주면 그 번호가 쓰레기가 된다).
    """
    name = str(text or "").strip()
    if not name:
        return "", "이름이 비었다 — 발급하지 않는다"
    got, why = key_of(name, sport=sport, league=league)
    if got:
        return got, why
    reg = registry()
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **짧은 이름은 코드로 찾아본다**(실사고 2026-10-07)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ fotmob 은 대표팀을 `USA`·`KOR` 처럼 **FIFA 세 글자**로 적는 자리가 있다.
    #     그걸 모르는 이름으로 보고 발급하면 **United States 가 두 열쇠로 갈린다**
    #     (실측: `USA` 가 새 번호를 받았고 그 번호는 어제 시카고 파이어 것이었다).
    #  🔴 코드는 **이름표에 이미 있다**(`fa:USA`·`iso:US`) — 그것으로 찾는다.
    said = name.strip().upper()
    if 2 <= len(said) <= 3 and said.isalpha():
        # 🔴 **세 글자 코드는 CLDR 이 두 글자로 바꿔 준다**(`USA`→`US`·`KOR`→`KR`).
        #    ⚠️ 손으로 적지 않는다 — `babel` 의 `territory_aliases` 가 원본이다
        #       (실측 2026-10-07: `CHI` 는 **없다** — 칠레 약칭을 지어내지 않는다).
        codes = [said]
        try:
            from babel.core import get_global
            codes += [str(x) for x in (get_global("territory_aliases").get(said)
                                       or [])]
        except Exception:                                   # noqa: BLE001
            pass
        for code in codes:
            for pre in ("iso", "fa"):
                keys = reg.index.get(norm(f"{pre}:{code}")) or []
                if len(keys) == 1:
                    return keys[0], (f"`{name}` → 코드 `{pre}:{code}` 로 찾았다"
                                     f"(CLDR 가 세 글자를 두 글자로 바꿨다)")
    ext = f"name:{norm(name)}"
    key = reg.key_for(ext=ext, name=name, league=league, sport=sport)
    ref = reg.teams.get(key)
    if ref is not None:
        # 🔴 **이름을 그 팀에 붙인다** — 안 붙이면 같은 실행 안에서도 다시 못 찾는다
        lang = lang_of(name)
        said = ref.names.setdefault(lang, [])
        if name not in said:
            said.append(name)
        ref.by.setdefault(norm(name), "openworld")
        reg.index.setdefault(norm(name), [])
        if key not in reg.index[norm(name)]:
            reg.index[norm(name)].append(key)
        reg.bare_index.setdefault(bare(name), [])
        if key not in reg.bare_index[bare(name)]:
            reg.bare_index[bare(name)].append(key)
    _save_keys(reg)
    return key, (f"🔴 이름표에 `{name}` 이 없다 — **임시 열쇠 `{key}` 발급**"
                 f"(오픈월드 · `{ext}` 로 못 박았다)")
