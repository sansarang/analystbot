"""🔴🔴 **대회 식별 — 한 곳**. 사용자 지시 2026-10-09(4차) §1.

> 입력이 어떤 꼴이든(ESPN 슬러그 `jpn.1`·`kor.1`…, fotmob 리그 id, football-data
> 코드 `PL`·`PD`·`PPL`…, 사람 이름 `"J1 League"`·`"K League 1"`) → **하나의
> `competition_key`**(예: `league:J1`·`league:KL1`·`league:PPL`)로 바꾼다.

🔴 **왜 한 곳인가** — 실사고 2026-10-09(가시마–감바): ESPN 이 대회명을 `jpn.1` 로
   줬고 이름표가 그 글자를 몰라 `league:jpn.1` 로 떨어졌다. 그러자 **자체 Elo·기준
   모델·홈 이점 표·리그 평균이 한꺼번에** 비었고 카드는 변수 **1개**로 나갔다.
   ⚠️ 별칭 하나를 더하는 것으로는 다음 출처에서 또 터진다 — 그래서 **판정을 한
   함수로 모으고**, 모르면 **크게 실패**한다(§2).

🔴 표는 `config/competitions.yaml` **하나**다(사본 금지 · #1). 코드에 표기를 안 적는다.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

CONF = "config/competitions.yaml"

#: 🔴 §2 — 못 알아봤을 때 카드 머리에 찍는 글자. ⚠️ 받은 표기를 **그대로** 보인다
UNKNOWN_HEAD = "🔴 대회를 알아보지 못했다"
#: 🔴 대표팀 유형 — 리그가 아니다(`comp_kind` 가 쓰는 두 글자)
NATIONAL = ("national_friendly", "national_official")

#: 🔴 **못 알아본 표기는 여기 모으지 않는다** — `app/auditlog.py` 가 **한 곳**에서
#  파일로 남기고 운영자 `/상태` 가 그것을 적는다(지시 2026-10-09(4차) §2).
#  ⚠️ 두 곳에 모으면 한 곳만 비워져 *"없다"* 가 거짓이 된다(#1 사본 금지).


def table() -> dict:
    """🔴 설정표 — `config/competitions.yaml`. ⚠️ 코드에 표기를 안 적는다."""
    from app import rules
    return dict(rules._load(CONF) or {})


def rows() -> dict[str, dict]:
    """🔴 `{competition_key: 줄}` — 키는 `league:J1` 처럼 **접두사를 포함**한다."""
    return {str(k): dict(v or {}) for k, v in (table().get("keys") or {}).items()}


def _norm(said: object) -> str:
    """🔴 대조용 꼴 — 낮춰 쓰고 공백을 줄인다. ⚠️ 글자를 **지어내 바꾸지 않는다**."""
    return " ".join(str(said or "").strip().lower().split())


def key_of(*, competition: str = "", league_id: object = None,
           code: str = "") -> tuple[str, str]:
    """🔴🔴 **어떤 꼴이든 → `competition_key`**. `(키, 사유)`.

    못 정하면 `("", 사유)` 이고 호출부가 **크게 실패**한다(§2).

    | 입력 | 어디서 오나 |
    |---|---|
    | `competition` | `MatchRef.competition` — 출처가 준 글자(`jpn.1`·`K-League 1`) |
    | `league_id` | fotmob `parentLeagueId`/`leagueId` |
    | `code` | football-data 대회 코드(`PL`) |

    🔴 **셋 중 하나만 맞아도** 키가 선다 — 출처마다 다른 칸을 주기 때문이다.
    ⚠️ 긴 표기부터 본다(`serie a` 가 `serie a - brazil` 을 가로채지 않게).
    """
    box = rows()
    said = _norm(competition)
    lid = str(league_id or "").strip()
    cd = _norm(code)
    # ① football-data 코드 — 가장 좁다(표의 키와 1:1 이다)
    if cd:
        for key, row in box.items():
            if _norm((row.get("sources") or {}).get("football_data")) == cd:
                return key, f"football-data 코드 `{code}`"
    # ② fotmob 리그 id — 숫자라 애매하지 않다
    if lid:
        for key, row in box.items():
            ids = [str(x) for x in
                   ((row.get("sources") or {}).get("fotmob_ids") or [])]
            if lid in ids:
                return key, f"fotmob 리그 id `{lid}`"
    # ③ 글자 표기 — **긴 것부터** 본다
    if said:
        cand: list[tuple[int, str, str]] = []
        for key, row in box.items():
            for word in _words(row):
                low = _norm(word)
                if not low:
                    continue
                # 🔴 ESPN 슬러그처럼 **점이 든 짧은 글자**는 전체가 같아야 한다
                #    ⚠️ `jpn.1` 을 부분 일치로 보면 `jpn.10` 도 걸린다
                if _is_slug(low):
                    if said == low:
                        cand.append((len(low) + 100, key, word))
                elif low in said:
                    cand.append((len(low), key, word))
        if cand:
            cand.sort(key=lambda x: -x[0])
            _n, key, word = cand[0]
            # ⚠️ **확인 안 된 표기**로 섰으면 그 사실을 사유에 남긴다(#3)
            un = [str(x) for x in ((box[key].get("sources") or {})
                                   .get("espn_slugs_unverified") or [])]
            if _norm(word) in {_norm(x) for x in un}:
                why = str((box[key].get("sources") or {})
                          .get("espn_unverified_why") or "")
                return key, (f"표기 `{word}` — ⚠️ **출처에서 확인 못 한 표기**"
                             + (f"({why})" if why else ""))
            return key, f"표기 `{word}`"
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **자동 등록된 리그도 "아는 대회"다** — 사용자 결정 2026-10-10 §1
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 리그 **수동 선언·상한 방식을 자동 등록으로 바꾼다.**
    #
    #  ⚠️ 종전엔 `config/competitions.yaml` 에 없으면 곧바로 `UNKNOWN_HEAD` 였다
    #     — 그러면 봇이 **자기가 등록한 리그를 모른다**고 말한다(실사고가 될
    #     자리). 🔴 `data/leagues_auto/` 를 본다.
    #  🔴 손 표(`competitions.yaml`)가 **먼저**다 — 거기엔 기준 모델·분할 규칙이
    #     달려 있고 자동 등록은 그만큼 못 안다.
    if lid:
        from app.core import autoleague
        key = f"league:fotmob{lid}"
        if autoleague.load(key):
            return key, f"**자동 등록** 리그 — fotmob 리그 id `{lid}`"
    got = str(competition or code or lid or "")
    return "", f"{UNKNOWN_HEAD} — 받은 표기 `{got or '없음'}`"


def _is_slug(low: str) -> bool:
    """🔴 `jpn.1`·`eng.2` 꼴인가 — 그러면 **전체 일치**만 받는다."""
    return bool(re.fullmatch(r"[a-z]{2,4}\.[0-9a-z]+", low))


def _words(row: dict) -> list[str]:
    """🔴 그 줄의 **모든 출처 표기**를 한 목록으로. ⚠️ 종류를 섞어도 되는 까닭:
    키를 정하는 데는 어느 출처의 글자든 **같은 답**을 가리킨다(그게 이 표의 뜻이다).
    """
    src = dict(row.get("sources") or {})
    out: list[str] = [*(row.get("names") or [])]
    # 🔴 `*_unverified` 도 **알아본다** — 사용자 지시 2026-10-09(4차) §1 이
    #    *"kor.1 포함"* 이라 못 박았다. ⚠️ **확인 여부는 칸이 가른다**(그 칸에
    #    `_why` 가 왜 못 확인했는지 적는다) — 아는 것과 확인한 것은 다르다.
    #    🔴 모르는 채로 두면 `jpn.1` 실사고가 그 리그에서 되풀이된다.
    for k in ("espn_slugs", "espn_slugs_unverified", "fotmob_names",
              "football_data_names"):
        out += [str(x) for x in (src.get(k) or [])]
    for k in ("football_data",):
        if src.get(k):
            out.append(str(src[k]))
    return [str(x) for x in out if str(x).strip()]


def kind_of(*, competition: str = "", league_id: object = None,
            code: str = "", friendly: bool = False,
            national: bool = False) -> tuple[str, str]:
    """🔴🔴 **대회 유형**(`comp_kind` 가 돌려주던 것) — `(유형, 사유)`.

    대표팀이면 `national_friendly`·`national_official`, 리그면 `competition_key`
    (`league:J1`), 못 알아보면 `("", 사유)`.

    🔴 **여기가 유일한 판정점**이다 — `s5_verify.comp_kind` 는 이 함수를 부른다.
    """
    if national:
        return (NATIONAL[0] if friendly else NATIONAL[1],
                "대표팀 경기(이름표에 나라 코드가 있다)")
    return key_of(competition=competition, league_id=league_id, code=code)


def row_of(key: str) -> dict:
    """🔴 그 키의 줄 — 리그 형식·기준 모델·동률 규칙이 들어 있다. 없으면 빈 표."""
    return dict(rows().get(str(key or "")) or {})


def fd_code(key: str) -> str:
    """🔴 그 키의 football-data 코드(`league:PL` → `PL`). 없으면 `""`."""
    return str((row_of(key).get("sources") or {}).get("football_data") or "")


def elo_source(key: str) -> dict:
    """🔴 그 키의 **기준 모델**(Elo 출처·적합 이름). ⚠️ 없으면 빈 표 → 기준 없음."""
    return dict(row_of(key).get("baseline") or {})


def split_of(key: str) -> dict:
    """🔴 그 키의 **리그 형식**(분할·플레이오프 컷). ⚠️ 없으면 분할이 없다."""
    return dict(row_of(key).get("split") or {})


def tiebreak_of(key: str) -> dict:
    """🔴 그 키의 **동률 규칙**. ⚠️ 없으면 호출부가 가정을 쓰고 카드에 표시한다."""
    return dict(row_of(key).get("tiebreak") or {})


def source_rank(ext_id: object) -> int:
    """🔴 그 `ext_id` 의 **출처 순위**(작을수록 먼저). 표에 없으면 맨 뒤.

    🔴 순서는 `config/competitions.yaml` 의 `source_priority` 가 든다(사본 금지).
    ⚠️ 같은 경기가 두 출처로 들어왔을 때 **무엇을 남기나**를 이 수가 정한다.
    """
    said = str(ext_id or "")
    head = said.split(":", 1)[0].strip().lower()
    order = [str(x).strip().lower() for x in (table().get("source_priority") or [])]
    return order.index(head) if head in order else len(order)


def pick_one(rows: list[dict]) -> tuple[list[dict], list[str]]:
    """🔴🔴 **같은 경기를 하나로** — `(남긴 줄들, 묶은 사유들)`.

    같은 경기인지는 **두 팀과 킥오프 순간**이 말한다(대회 글자가 아니다 — 출처마다
    다르다). 남길 줄은 ① **대회를 알아보는** 줄 ② `source_priority` 가 고른다.

    🔴 왜 필요한가 — 실사고 2026-10-09(가시마–감바): `games` 표에 같은 경기가 두
       줄(`fotmob`·`espn`)이라 `ambiguous` 로 멈춰 **카드가 안 나왔다**.
    ⚠️ 시각이나 팀을 못 재는 줄은 **묶지 않는다**(모르는 것을 같다고 하지 않는다).
    """
    def _sig(r: dict):
        pair = tuple(sorted(_norm(r.get(k)) for k in ("home", "away")))
        when = str(r.get("starts_utc") or r.get("starts_kst") or "")[:16]
        return (pair, when) if all(pair) and when else None

    def _score(r: dict) -> tuple[int, int]:
        key, _why = key_of(competition=str(r.get("league") or ""))
        return (0 if key else 1, source_rank(r.get("ext_id")))

    best: dict[object, dict] = {}
    loose: list[dict] = []
    notes: list[str] = []
    for row in rows:
        sig = _sig(row)
        if sig is None:
            loose.append(row)
            continue
        got = best.get(sig)
        if got is None:
            best[sig] = row
            continue
        keep, drop = ((row, got) if _score(row) < _score(got) else (got, row))
        best[sig] = keep
        notes.append(f"같은 경기를 묶었다 — `{drop.get('ext_id')}`"
                     f"(`{drop.get('league')}`) 를 빼고 `{keep.get('ext_id')}`"
                     f"(`{keep.get('league')}`) 를 남겼다")
    return [*best.values(), *loose], notes


def outlook_gate() -> dict:
    """🔴 §1 — **경우의 수를 언제 판정하나**. 표는 `competitions.yaml` 하나다."""
    return dict(table().get("outlook_gate") or {})


def outlook_open(*, rounds_left: int, is_group: bool,
                 cut_rounds_left: int | None = None) -> tuple[bool, str]:
    """🔴🔴 §1 — 경우의 수를 **판정해도 되나**. `(열렸나, 사유)`.

    | 무엇 | 문턱 |
    |---|---|
    | 리그 남은 라운드 | `league_rounds_left_at` 이하 |
    | 분할·플레이오프 컷까지 | `split_rounds_left_at` 이하 |
    | 조별 리그 | `group_rounds_left_at` 이하 |

    🔴 실사고 2026-10-09(가시마–감바 8라운드): 남은 라운드 30경기에 `must_win` 이
       찍혔다 — 그 글자가 이유 문단과 ③ 이동까지 흔들었다.
    ⚠️ 라운드를 **못 세면 닫는다**(모르는 것으로 상태를 말하지 않는다 · #3).
    """
    box = outlook_gate()
    if rounds_left is None or int(rounds_left) < 0:
        return False, "남은 라운드를 못 셌다 — 경우의 수를 판정하지 않는다"
    left = int(rounds_left)
    if is_group:
        at = int(box.get("group_rounds_left_at") or 2)
        if left <= at:
            return True, f"조별 리그 마지막 {at}라운드 안(남은 {left})"
        return False, (f"조별 리그인데 남은 라운드가 {left} 다 — 마지막 {at}라운드"
                       f"부터 판정한다")
    at = int(box.get("league_rounds_left_at") or 5)
    if left <= at:
        return True, f"리그 남은 라운드 {left} ≤ {at}"
    cut_at = int(box.get("split_rounds_left_at") or 3)
    if cut_rounds_left is not None and int(cut_rounds_left) <= cut_at:
        return True, (f"분할 컷까지 남은 라운드 {int(cut_rounds_left)} ≤ {cut_at}")
    return False, (f"**시즌 초** — 남은 라운드 {left}(판정은 {at} 이하부터"
                   + (f" · 분할 컷까지 {cut_at} 이하부터" if cut_rounds_left
                      is not None else "") + ")")


def short_key(key: str) -> str:
    """🔴 `league:J1` → `J1`. ⚠️ 대표팀 유형은 그대로 돌려준다."""
    said = str(key or "")
    return said.split(":", 1)[1] if said.startswith("league:") else said

