"""🔴🔴 **리그 자동 등록** — 사용자 결정 2026-10-10 §1·§3.

> 모든 경기를 찾아 분석까지 해야 한다. **리그 수동 선언·상한 방식을 자동 등록으로
> 바꾼다.**

🔴 쓰는 자리는 `data/leagues_auto/{competition_key}.json` **하나**다 — 코드도
   config 도 아니다(§1 둘째 줄). ⚠️ `config/leagues.yaml` 은 *"기준 모델·분할
   규칙·특수 처리가 필요한 리그"* 만 남는다(지금 7개 그대로).

🔴 **필수 칸이 하나라도 없으면 등록 실패**다(§1 셋째 줄):
   출처(fotmob 리그 id·URL) · 확인일 · 나라(ccode) · 팀 목록 출처 · 언어(CLDR).
⚠️ 언어는 **CLDR 에서 받는다**(`babel`) — 손으로 적지 않는다(사용자 지시 2026-10-03).
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
#: 🔴 저장 자리 — `data/` 다(코드·config 아님 · §1)
STORE = ROOT / "data" / "leagues_auto"
#: 🔴 §1 — **이 칸이 다 있어야** 등록이다. 하나라도 없으면 실패.
NEED: tuple[str, ...] = ("competition_key", "source", "checked_at", "ccode",
                         "teams_from", "langs", "teams")
#: 🔴 §3 — 기준을 *"약하다"* 고 적는 경기 수(사용자가 적은 30)
WEAK_AT = 30


def path_of(key: str) -> Path:
    """🔴 그 리그의 파일 — 열쇠의 `:` 를 `_` 로 바꾼다(파일 이름이 된다)."""
    said = str(key or "").replace(":", "_").replace("/", "_")
    return STORE / f"{said or 'unknown'}.json"


def load(key: str) -> dict:
    """🔴 등록된 리그. ⚠️ 없으면 **빈 표**다(지어내지 않는다)."""
    p = path_of(key)
    if not p.is_file():
        return {}
    try:
        return dict(json.loads(p.read_text(encoding="utf-8")))
    except (ValueError, OSError):
        return {}


def langs_of(ccode: str) -> list[str]:
    """🔴🔴 §3 — 나라 → **CLDR 공식 언어** + 영어. 손으로 적지 않는다.

    🔴 실측 2026-10-10(babel CLDR `territory_languages`):
       `AR→es` · `TR→tr` · `IT→it` · `AU→en` · `SG→en,zh,ms` · `VN→vi` · `TH→th`
       — 사용자가 적은 것과 **그대로 맞는다**.
    ⚠️ fotmob 은 세 글자(`ARG`)를 준다 — CLDR 은 두 글자(`AR`)다. 🔴 그 변환도
       **표에서** 한다(`pycountry` 가 없으면 앞 두 글자로 떨어지지 않는다 — 그러면
       빈 목록이고 등록이 실패한다 · 조용히 틀리지 않는다).
    """
    cc = str(ccode or "").strip().upper()
    if not cc:
        return []
    two = cc
    if len(cc) == 3:
        two = _alpha2(cc)
        if not two:
            return []
    try:
        import babel.core as bc
        box = (bc.get_global("territory_languages") or {}).get(two) or {}
    except Exception:                                       # noqa: BLE001
        return []
    off = sorted(((k, float(v.get("population_percent") or 0))
                  for k, v in box.items() if v.get("official_status")),
                 key=lambda x: -x[1])
    out = [k for k, _p in off][:3]
    if "en" not in out:
        out.append("en")       # 🔴 영어는 늘 더한다(§3: "그 언어 + 영어")
    return out


def _alpha2(cc3: str) -> str:
    """🔴🔴 ISO 3글자 → 2글자 — **CLDR 이 그 표를 들고 있다**(손으로 안 적는다).

    🔴 실측 2026-10-10: `babel.core.get_global("territory_aliases")` 에
       `ARG → ['AR']` · `TUR → ['TR']` · `SGP → ['SG']` 가 있다(640줄).
    ⚠️ **앞 두 글자를 떼지 않는다** — `AUS`→`AU` 는 맞지만 `CHE`→`CH`(스위스)는
       그 방식으로 틀린다(`CH` 가 아니라 `CHE` 가 따로 있다). 표가 답이다.
    ⚠️ 표에 없으면 **빈 글자**다 → 등록이 실패하고 그 사실이 사유에 남는다.
    """
    try:
        import babel.core as bc
        box = (bc.get_global("territory_aliases") or {}).get(str(cc3).upper())
    except Exception:                                       # noqa: BLE001
        return ""
    for x in (box or []):
        said = str(x).strip().upper()
        if len(said) == 2:
            return said
    return ""


def baseline_of(rows: list[dict]) -> dict:
    """🔴🔴 §3 — 그 리그 **이번 시즌 결과**로 기준 출발점.

    > 자체 Elo 가 없으면 … 홈승·무·원정승 비율과 **경기당 총골**을 계산해
    > 출발점으로. 경기 수가 **30경기 미만이면 "기준 약함"** 표시.
    """
    n = len(rows or [])
    if not n:
        return {"n": 0, "weak": True, "why": "끝난 경기가 0건이다"}
    home = sum(1 for r in rows if int(r["home_score"]) > int(r["away_score"]))
    draw = sum(1 for r in rows if int(r["home_score"]) == int(r["away_score"]))
    goals = sum(int(r["home_score"]) + int(r["away_score"]) for r in rows)
    return {"n": n,
            "share_home_draw_away": [round(home / n, 4), round(draw / n, 4),
                                     round((n - home - draw) / n, 4)],
            "goals_per_match": round(goals / n, 3),
            "weak": n < WEAK_AT,
            "why": (f"이번 시즌 끝난 경기 {n}건으로 셌다"
                    + (f" — 🔴 **기준 약함**({WEAK_AT}경기 미만)" if n < WEAK_AT
                       else ""))}


def build(*, competition_key: str, meta: dict, teams: list[str],
          baseline: dict, when: date | None = None) -> tuple[dict, str]:
    """🔴🔴 §1 — 등록할 표를 **만든다**. `(표, 사유)` · 필수 칸이 없으면 `({}, 사유)`.

    ⚠️ **실패를 조용히 넘기지 않는다** — 사유에 무엇이 없는지 이름으로 적는다.
    """
    lid = meta.get("league_id")
    ccode = str(meta.get("ccode") or "")
    said = {
        "competition_key": str(competition_key or ""),
        # 🔴 출처 — **리그 id 와 주소 둘 다**(§1 셋째 줄)
        "source": {"fotmob_league_id": lid, "url": str(meta.get("url") or "")},
        "checked_at": str((when or datetime.now(timezone.utc).date()).isoformat()),
        "ccode": ccode,
        # 🔴 팀 목록 출처 — 이미 만든 통로 이름 그대로(§3 첫 줄)
        "teams_from": f"fotmob:{lid}" if lid else "",
        "langs": langs_of(ccode),
        "teams": sorted(set(str(x) for x in (teams or []) if str(x).strip())),
        "name": str(meta.get("name") or ""),
        "season": str(meta.get("season") or ""),
        # 🔴 §3 — 대회 형식(조가 여럿이면 조별) · 분할은 순위표 구역이 말한다
        "format": ("group" if int(meta.get("groups") or 0) > 1 else "league"),
        "zones": dict(meta.get("zones") or {}),
        "baseline": dict(baseline or {}),
    }
    miss = [k for k in NEED if not said.get(k)]
    if miss:
        return {}, f"🔴 등록 실패 — 필수 칸이 없다: {miss}"
    return said, (f"등록 준비 — `{said['competition_key']}` · {ccode} · "
                  f"언어 {said['langs']} · 팀 {len(said['teams'])} · "
                  f"{said['baseline'].get('why')}")


def save(box: dict) -> tuple[Path | None, str]:
    """🔴 파일로 쓴다. ⚠️ 필수 칸을 **다시 본다** — 만든 쪽을 믿지 않는다."""
    miss = [k for k in NEED if not dict(box).get(k)]
    if miss:
        return None, f"🔴 등록 실패 — 필수 칸이 없다: {miss}"
    STORE.mkdir(parents=True, exist_ok=True)
    p = path_of(str(box["competition_key"]))
    p.write_text(json.dumps(box, ensure_ascii=False, indent=2, sort_keys=True)
                 + "\n", encoding="utf-8")
    return p, f"등록했다 — {p.relative_to(ROOT)}"


def registered() -> list[str]:
    """🔴 등록된 리그 열쇠들 — 계약이 *"자동 등록 경로를 통과했나"* 를 본다(§1)."""
    if not STORE.is_dir():
        return []
    out: list[str] = []
    for p in sorted(STORE.glob("*.json")):
        try:
            got = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        key = str(dict(got).get("competition_key") or "")
        if key:
            out.append(key)
    return out


def short_of(key: str) -> str:
    """🔴 자동 등록 열쇠 → **짧은 이름**(`league:KL1` → `KL1`).

    계약이 *"자동 등록한 리그가 손 선언에도 있나"* 를 볼 때 쓴다(§1) — 두 쪽의
    이름 모양이 다르므로 한 곳에서 맞춘다.
    """
    said = str(key or "")
    return said.split(":", 1)[1] if ":" in said else said


def line(key: str) -> str:
    """🔴🔴 §4 — 카드·보고가 적는 **등록 한 줄**: 나라·언어·팀 수·기준 상태.

    > 각 경기마다: 자동 등록 파일 · 검색 언어 · 라인업 출처 · 기준 상태를 적는다.

    ⚠️ 등록이 없으면 **그 사실**을 적는다 — 빈 글자로 조용히 넘기지 않는다(#3).
    """
    box = load(key)
    if not box:
        return f"🆕 자동 등록 없음 — `{short_of(key)}`"
    base = dict(box.get("baseline") or {})
    return (f"🆕 **자동 등록** `{short_of(key)}` · {box.get('ccode')} · "
            f"언어 {box.get('langs')} · 팀 {len(box.get('teams') or [])} · "
            f"확인일 {box.get('checked_at')} · 기준 "
            + ("🔴 **약함**" if base.get("weak") else "✅")
            + f"({base.get('n')}경기)")


def report() -> str:
    """🔴 `/상태` 가 적는 **등록된 리그 전부** — 상한이 없어졌으니 수가 보여야 한다.

    ⚠️ 수동 선언 상한(7개)을 걷은 뒤로는 **이 목록이 유일한 눈**이다(§1).
    """
    keys = registered()
    if not keys:
        return "🆕 자동 등록된 리그 0개 — 아직 아무 경기도 새 리그를 안 열었다"
    return (f"🆕 자동 등록된 리그 {len(keys)}개\n"
            + "\n".join(line(k) for k in keys))
