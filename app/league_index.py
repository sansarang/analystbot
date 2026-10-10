"""🔴🔴 **팀 → 리그 색인** — *"이 팀이 어느 리그인가"* 를 아는 유일한 자리.

사용자 지시 2026-10-03:

> 팀을 찾지도 못하고... **매번 할 때마다 이러는 근본 원인**을 찾아라...
> 사용자가 경기 질문을 하면 **어느 리그부터 검색을 해야 하는지 단계별로 세세하게**
> 봇이 찾아야 한다. **러프하게 코드 작성을 하지 말아라.**

══════════════════════════════════════════════════════════════════
🔴 근본 원인 (측정 2026-10-03)
══════════════════════════════════════════════════════════════════

```
aliases.find_team("감바 오사카")  →  ('soccer', 'Gamba Osaka')
                                     ^^^^^^^^ 🔴 **종목**이다. 리그가 아니다
```
별칭표 195항목이 `mlb:37 · kbo:24 · soccer:151` 로만 갈려 있고 **팀 → 리그** 표가
저장소 어디에도 없었다. 그래서 질문마다 `리그 미상` → 언어 영어 고정 → 어댑터
못 고름 → 엉뚱한 호스트(`kia.com` 자동차 · `nba.com` · `golf.com`) → 사실 0~5건.

🔴 **이 파일이 그 구멍이다.** 리그 명부(`config/leagues.yaml`)가 *"어디서 받나"* 를
   말하고, 여기서 **받아서** 색인을 만든다.

⚠️ **팀 이름을 손으로 적지 않는다.** 이적·승강 때마다 손 목록은 한 발 늦고, 그
   목록이 거짓이 되면 봇이 **조용히 틀린 리그**를 고른다(그것이 0건보다 나쁘다).
🔴 받은 것은 파일로 캐시한다 — 질문 하나가 리그 일곱 개를 네트워크로 묻게 두지
   않는다. ⚠️ 캐시는 저장소에 커밋하지 않는다(`var/` 는 ignore 다).
"""
from __future__ import annotations

import hashlib
import inspect
import json
import logging
import time
import unicodedata
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
LEAGUES = "config/leagues.yaml"

#: 🔴 팀 명단을 받는 유일한 통로. 키·카드가 없다(§11-7 유료 API 0건 정의 안).
#   ⚠️ 어느 소스를 쓰는지와 그 경위는 `app/collect/kbo.py` 머리글에 적혀 있다.
# 🔴 **§8-4 로 지웠다**(2026-10-04) — `search_all_teams` 는 열 팀에서
#    잘리고 거짓 명단을 준다. 명단 출처는 `ROSTER_SOURCES` 다. [#7]

#: 🔴 **정규화된 이름 → 그 팀의 현지 표기**(`kashiwareysol` → `柏レイソル`).
#   ⚠️ 받는 동안 채워지고 **캐시에 함께 저장된다** — 다시 받지 않으려고.
_LOCALS: dict[str, str] = {}
#: 🔴 캐시 파일을 **한 번은** 훑었나 — `_LOCALS` 가 일부만 찬 경우와 가른다
_LOCALS_READ: set[int] = set()

#: 🔴 **정규화된 이름 → 외부 id**(`kashiwareysol` → `tsdb:137708`).
#   ⚠️ 받아 놓고 **버리던** 칸이다(실측 2026-10-03). 이름은 언어마다 달라지지만
#      id 는 안 변한다 — 신원의 열쇠가 그것이다.
#   🔴 읽는 곳은 `app/teamref.py` 다(캐시 파일에서 직접 읽는다) — 여기에 조회
#      함수를 따로 두지 않는다(부르는 곳이 없는 공개 함수는 없는 코드보다 나쁘다).
_EXT_IDS: dict[str, str] = {}


def _cfg() -> dict:
    from app import rules
    return rules._load(LEAGUES)


def leagues() -> list[dict]:
    """🔴 명부 순서 그대로. **이 순서가 '어느 리그부터'** 다."""
    return [dict(x) for x in (_cfg().get("leagues") or [])]


def ladder() -> list[dict]:
    """🔴 팀 이름 → 리그를 좁히는 **단계들**. 순서가 곧 사다리다."""
    return [dict(x) for x in (_cfg().get("ladder") or [])]


def langs_of(key: str) -> tuple[str, ...]:
    """🔴 그 리그 기사의 언어. **원본은 명부 하나다** — 여기서 짓지 않는다."""
    for lg in leagues():
        if str(lg.get("key")) == str(key):
            return tuple(str(x) for x in (lg.get("langs") or []))
    return ()


def sport_of(key: str) -> str:
    for lg in leagues():
        if str(lg.get("key")) == str(key):
            return str(lg.get("sport") or "")
    return ""


def adapter_of(key: str) -> str:
    """그 리그의 `ADAPTERS` 열쇠. 🔴 없으면 빈 문자열 — 있는 척하지 않는다."""
    for lg in leagues():
        if str(lg.get("key")) == str(key):
            return str(lg.get("adapter") or "")
    return ""


# ══════════════════════════════════════════════════════════════════
# 이름 맞추기 — 🔴 **한 곳에서** 정규화한다
# ══════════════════════════════════════════════════════════════════


def norm(name: str) -> str:
    """🔴 비교용 꼴. 대소문자·공백·악센트·점을 걷는다.

    ⚠️ 실측 2026-10-03: `Júbilo Iwata` 와 `Jubilo Iwata`, `Kyoto Sanga F.C.` 와
       `Kyoto Sanga` 가 **다른 문자열**이라 색인이 못 맞췄다.
    🔴 **지우기만 한다** — 글자를 바꾸거나 음차하지 않는다(그것은 추측이다).
    """
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return "".join(c for c in s.lower() if c.isalnum())


# ══════════════════════════════════════════════════════════════════
# 팀 명단 받기 — 🔴 **받아서** 캐시한다
# ══════════════════════════════════════════════════════════════════


def _cache_path(key: str) -> Path:
    box = _cfg().get("cache") or {}
    return ROOT / str(box.get("dir") or "var/leagues") / f"{norm(key)}.json"


def cache_stamp(key: str) -> str:
    """🔴🔴 **그 리그 캐시의 도장** — `teams_from` 선언 + 그 꼴 함수의 코드.

    ══════════════════════════════════════════════════════════════════
    🔴 왜 도장인가 — 실측 2026-10-04
    ══════════════════════════════════════════════════════════════════

    `var/leagues/mlb.json` 이 이런 사유를 들고 있었다:

        why  공식 API `mlb` 30팀 · TheSportsDB `MLB` 10팀 🔴 **열 팀에서 잘린다**

    ⚠️ `leagues.yaml` 의 MLB 줄에는 **`url:` 하나뿐**이다 — tsdb 대체는 §8-4 를
       적용할 때 걷어 냈다. 🔴 그런데 캐시가 **옛 선언으로 받은 것을 7일 동안
       그대로 냈다.** 같은 병으로 `_SHAPES["mlb"]` 를 고친 것도 안 불릴
       참이었다(캐시가 신선해서).

    🔴 **사람이 `rm -rf var/leagues` 를 기억하는 것에 기대지 않는다** — 손으로
       유지하는 것은 언제나 한 발 늦는다(CLAUDE.md #1).
    ⚠️ 꼴 **함수의 코드**까지 넣는다: 선언만 보면 *꼴을 고친 것*을 못 잡는다.
    """
    row = next((x for x in leagues() if str(x.get("key")) == str(key)), None)
    if not row:
        return ""
    specs = row.get("teams_from") or []
    if isinstance(specs, str):
        specs = [specs]
    parts: list[str] = [str(x) for x in specs]
    for spec in specs:
        head, _, body = str(spec).partition(":")
        shape = body.rpartition("|")[2] if head == "url" else head
        fn = _SHAPES.get(shape)
        if fn is None:
            parts.append(f"{shape}:함수없음")
            continue
        try:
            parts.append(inspect.getsource(fn))
        except (OSError, TypeError):            # pragma: no cover
            # 🔴 코드를 못 읽으면 **도장을 포기하지 않는다** — 그 사실을 넣는다
            parts.append(f"{shape}:코드못읽음")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _fresh(p: Path, key: str = "") -> bool:
    """🔴 신선한가 — **날짜와 도장을 함께** 본다.

    ⚠️ 날짜만 보면 선언·꼴을 고쳐도 7일을 버틴다(바로 그 일이 났다).
    """
    box = _cfg().get("cache") or {}
    ttl = float(box.get("ttl_days") or 0) * 86400
    if ttl <= 0 or not p.exists():
        return False
    if (time.time() - p.stat().st_mtime) >= ttl:
        return False
    if not key:
        return True
    # 🔴 **도장이 다르면 묵은 것**이다 — 도장 없는 옛 캐시도 묵은 것이다
    try:
        said = str(json.loads(p.read_text(encoding="utf-8")).get("stamp") or "")
    except (OSError, ValueError):
        return False
    now = cache_stamp(key)
    if said == now:
        return True
    logger.info("[league_index] %s 캐시 도장이 다르다(`%s` ≠ `%s`) — "
                "선언이나 꼴이 바뀌었다. **다시 받는다**",
                key, said[:12] or "없음", now[:12])
    return False


def _from_adapter(spec: str) -> tuple[list[str], str]:
    """`adapter:<속성>` — 어댑터가 **스스로 선언한** 팀 명단. 🔴 가장 확실하다."""
    from app.collect.ingest import ADAPTERS
    attr = spec.split(":", 1)[1]
    for mod in ADAPTERS.values():
        got = getattr(mod, attr, None)
        if got:
            names = list(got.keys()) if isinstance(got, dict) else list(got)
            return [str(x) for x in names], f"어댑터 선언 `{attr}` {len(names)}팀"
    return [], f"어댑터에 `{attr}` 가 없다"


def short_name_ok(short: str, *, mine: str,
                  taken: dict[str, str]) -> tuple[bool, str]:
    """🔴🔴 **그 짧은 이름을 담아도 되나.** `(된다, 사유)`.

    ══════════════════════════════════════════════════════════════════
    🔴 왜 문이 필요한가 — 짧은 이름은 **부딪친다**
    ══════════════════════════════════════════════════════════════════

    ⚠️ `Giants` 는 SF 자이언츠·요미우리 자이언츠·롯데 자이언츠가 다 쓰고,
       `Tigers` 는 디트로이트·한신·기아가 쓴다. 🔴 영어 기사 속 `Tigers` 를
       디트로이트로 **귀속**하면 그것은 0건보다 나쁘다 — **거짓 변수**를 만든다
       (`config/entities.yaml` 머리글이 적은 그 위험이다).
    🔴 CLAUDE.md 가 같은 사고를 이미 적어 뒀다 — *"맨이름 `롯데` 는 넣지
       않는다 — NPB 지바 롯데와 갈린다."*

    ⚠️ **조용히 버리지 않는다**(#3) — 버린 사유를 글로 돌려준다.
    """
    key = norm(short)
    if not key:
        return False, "빈 이름"
    owner = str(taken.get(key) or "")
    if owner and owner != str(mine):
        return False, (f"🔴 짧은 이름 `{short}` 은 이미 `{owner}` 가 쓴다 — "
                       f"**부딪친다**. 담으면 기사를 엉뚱한 팀으로 귀속한다")
    return True, f"짧은 이름 `{short}` → `{mine}`"


def _shape_mlb(d: dict) -> list[str]:
    """statsapi.mlb.com/api/v1/teams?sportId=1 — 실측 2026-10-03: 30팀.

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **짧은 이름도 받는다**(실측 2026-10-04 · 게이트 2)
    ══════════════════════════════════════════════════════════════════

    종전은 `name` **하나만** 받았다. ⚠️ 그래서 이름표에 `Milwaukee Brewers` 는
    있고 **`Brewers` 는 없었고**, 에이전트 질의의 절반이 거부됐다:

    ```
    queries 탈락: query_too_bare 26
    'Brewers Padres NLDS Game 1 2026 MLB.com recap' → 요소 1개 → 🔴 거부
    ```

    🔴 공식 응답이 **이미 준다** — `teamName`·`clubName` 이 `Padres` 다.
    ⚠️ `abbreviation`(`SD`)·`teamCode`(`sdn`)는 **안 담는다**: 세 글자가 다른
       리그 팀과 부딪친다(바로 아래 `_from_fdorg` 가 `tla` 를 뺀 그 까닭이다).
    🔴 같은 `id` 를 **`_EXT_IDS` 로 묶는다** — 안 묶으면 `San Diego Padres` 와
       `Padres` 가 **다른 두 팀**이 된다(실측 2026-10-03 교토 사고와 같은 모양).
    """
    out: list[str] = []
    for t in (d.get("teams") or []):
        tid = str(t.get("id") or "").strip()
        ext = f"mlb:{tid}" if tid else ""
        full = str(t.get("name") or "").strip()
        if full:
            out.append(full)
            if ext:
                _EXT_IDS.setdefault(norm(full), ext)
        # 🔴 짧은 이름 — **부딪치면 버리고 사유를 남긴다**
        for field in ("teamName", "clubName"):
            short = str(t.get(field) or "").strip()
            if not short or norm(short) == norm(full):
                continue
            ok, why = short_name_ok(short, mine=ext, taken=dict(_EXT_IDS))
            if not ok:
                _SHORT_DROPPED.append(why)
                continue
            out.append(short)
            if ext:
                _EXT_IDS.setdefault(norm(short), ext)
    return out


#: 🔴 **버린 짧은 이름들** — 조용한 0 금지(#3). 사유가 캐시 설명에 들어간다.
_SHORT_DROPPED: list[str] = []

#: `url:<주소>|<꼴>` 의 **꼴**마다 이름을 어디서 뽑나. 🔴 받아서 확인한 모양이다.
_SHAPES = {
    "mlb": _shape_mlb,
    # api-web.nhle.com/v1/standings/now — 실측 2026-10-03: 32팀
    # ⚠️ 🔴 **짧은 이름을 아직 안 쟀다** — 이 응답이 `placeName`·`teamAbbrev`
    #    말고 무엇을 들고 있는지 받아서 확인한 적이 없다. 추측으로 칸을
    #    파헤치지 않는다(#4). MLB 와 같은 손질이 필요하면 **재고 나서** 한다.
    "nhl": lambda d: [str((t.get("teamName") or {}).get("default") or "")
                      for t in (d.get("standings") or [])],
}


async def _from_url(spec: str, net=None) -> tuple[list[str], str]:
    """`url:<주소>|<꼴>` — 공식 API 를 받아 이름만 뽑는다.

    🔴 **자르지 않는 길**이다(실측: MLB 30팀 · NHL 32팀). ⚠️ 꼴을 모르면 **빈
       목록과 사유** — 추측으로 칸을 파헤치지 않는다.
    """
    from app.net import Net
    body = spec.split(":", 1)[1]
    url, _, shape = body.rpartition("|")
    fn = _SHAPES.get(shape)
    if not fn:
        return [], f"모르는 응답 꼴 `{shape}`"
    got = await (net or Net()).get(url)
    if not getattr(got, "ok", False):
        return [], f"{url[:48]} 응답 실패 — {getattr(got, 'reason', '사유 없음')}"
    try:
        data = json.loads(got.text)
    except ValueError:
        return [], f"{url[:48]} 가 JSON 을 안 줬다"
    out = [x for x in fn(data) if x]
    return out, f"공식 API `{shape}` {len(out)}팀"


async def _from_fdorg(spec: str, net=None) -> tuple[list[str], str]:
    """`fdorg:<대회코드>` — football-data.org. 🔴 **안 자른다**(실측 EPL 20팀).

    ⚠️ 키가 없으면 **빈 목록과 사유**다 — 없는 것을 있는 척하지 않는다.
    🔴 분당 10회 상한이 있다(어댑터 머리글) — 대회 열 개를 한 번에 받으면 그
       상한에 닿는다. 그래서 **캐시가 필수**이고 TTL 이 그 역할을 한다.
    """
    from app.config import get_settings
    from app.net import Net
    code = spec.split(":", 1)[1]
    key = (get_settings().football_data_key or "").strip()
    if not key:
        return [], "football-data 키가 없다 — 이 대회 명단은 비운다"
    got = await (net or Net()).get(
        f"https://api.football-data.org/v4/competitions/{code}/teams",
        headers={"X-Auth-Token": key})
    if not getattr(got, "ok", False):
        return [], f"fdorg {code} 응답 실패 — {getattr(got, 'reason', '사유 없음')}"
    try:
        data = json.loads(got.text)
    except ValueError:
        return [], f"fdorg {code} 가 JSON 을 안 줬다"
    out: list[str] = []
    for t in (data.get("teams") or []):
        # 🔴🔴 **팀 id 를 기록한다**(실측 2026-10-04). ⚠️ fdorg 가 `name` 과
        #    `shortName` 을 따로 주므로, id 가 없으면 `Manchester City FC` 와
        #    `Man City` 가 **다른 두 팀**이 된다(실제로 그랬다).
        tid = str(t.get("id") or "").strip()
        for k in ("name", "shortName", "tla"):
            v = str(t.get(k) or "").strip()
            # ⚠️ `tla`(세 글자 약어)는 **안 담는다** — `ARS` 같은 세 글자가
            #    다른 리그 팀과 부딪친다. 이름·짧은 이름만 쓴다.
            if v and k != "tla":
                out.append(v)
                if tid:
                    _EXT_IDS.setdefault(norm(v), f"fdorg:{tid}")
    return out, f"fdorg `{code}` {len(data.get('teams') or [])}팀"


#: 🔴🔴 **§8-4 가 이름 댄 명단 출처** — 이것만이다. ⚠️ `tsdb` 는 **없다.**
#
#  v5 §8-4: *"TheSportsDB 는 **명단·리그 판정에 쓰지 않는다**(잘림·거짓 명단).
#  팀 검색(`searchteams.php?t=`)**만** 별칭 보조. 명단은 MLB statsapi·NHL·
#  football-data·공식 사이트·54팀 YAML."* [#7]
#
#  🔴 실측 2026-10-03 이 **거짓 명단**을 받았다:
#      search_all_teams.php?l=Japanese J1 League → **10팀**(J1 은 20팀)
#      lookup_all_teams.php?id=4633·4830·4424    → 🔴 **셋 다 영국 2부 24팀**
#  ⚠️ 24팀이 돌아온다는 사실만 보고 썼다면 거짓 명단으로 리그를 판정했을 것이다.
ROSTER_SOURCES: tuple[str, ...] = ("adapter", "url", "fdorg", "fotmob")


async def _from_fotmob(spec: str, net=None) -> tuple[list[str], str]:
    """🔴🔴 `fotmob:<리그번호>` — **리그 표 페이지의 팀 명단**(지시 2026-10-10).

    > 목표: **모든 경기에서** 봇이 … 확정 라인업으로 판정한다.

    🔴 왜 이 꼴이 필요한가 — 실사고 2026-10-10(우니온–데펜사): 아르헨티나
       `Liga Profesional` 이 명부에 없어 팀 이름이 안 풀렸고, `findgame` 이
       *"리그 미상 · 나라도 모른다(클럽이다) — 영어만"* 으로 떨어져 **카드가 아예
       안 나왔다**. ⚠️ 같은 병으로 터키컵·이탈리아 세리에D·애들레이드·라이언시티가
       전부 실패했다(2026-10-07~08).
    🔴 번호는 **받아서 확인한 값**만 쓴다(`config/competitions.yaml` 의
       `fotmob_ids`). ⚠️ 추측한 번호를 적으면 다른 리그가 온다(실사고: J1 을
       `9134` 로 적었는데 그 번호는 **NWSL** 이었다).
    """
    from app.collect import fotmob as fm
    lid = spec.split(":", 1)[1].strip() if ":" in spec else ""
    if not lid:
        return [], f"🔴 `{spec}` 에 리그 번호가 없다"
    url = f"{fm.BASE}/leagues/{lid}/table/x"
    got = await (net.get(url) if net is not None else _plain_get(url))
    j = fm.payload(getattr(got, "text", "") or "")
    if not j:
        return [], f"fotmob {lid} 표 페이지를 못 받았다(HTTP {getattr(got, 'status', '?')})"
    ids = fm.team_ids(j)
    if not ids:
        return [], f"fotmob {lid} 표에 팀 줄이 없다"
    for name, tid in ids.items():
        # 🔴 **번호를 버리지 않는다** — 이름은 언어마다 달라지지만 번호는 안 변한다
        _EXT_IDS.setdefault(norm(name), f"fotmob:{tid}")
    return sorted(ids), f"fotmob `{lid}` {len(ids)}팀"


async def _plain_get(url: str):
    """🔴 `net` 을 안 받았을 때의 길 — ⚠️ robots 는 `app.net` 이 본다(여기 아니다)."""
    from app import net as _net
    return await _net.Net().get(url)


async def _from_tsdb(spec: str, net=None) -> tuple[list[str], str]:
    """🔴 **§8-4 — 거부한다.** 명단을 tsdb 에서 받지 않는다. [#7]

    ⚠️ 이 문을 **지우지 않고 남긴다** — 선언(`leagues.yaml`)에 옛 `tsdb:` 줄이
       남아 있을 때 *"모르는 꼴"* 이 아니라 **왜 거부하는지**를 말해야 한다
       (#3 조용한 0 금지 · 그 사실이 캐시 사유에 적힌다).
    """
    name = spec.split(":", 1)[1] if ":" in spec else spec
    return [], (f"🔴 **§8-4 — tsdb 명단을 쓰지 않는다**(`{name}`): 열 팀에서 "
                f"잘리고 `lookup_all_teams` 는 id 를 무시해 **영국 2부 24팀**을 "
                f"매번 준다(실측 2026-10-03). 명단 출처는 {list(ROSTER_SOURCES)} 다")


async def roster_from(spec: str, net=None) -> tuple[list[str], str]:
    """🔴 `teams_from:` 한 줄 → `(이름들, 사유)`. **§8-4 가 허용한 꼴만.**

    ⚠️ 모르는 꼴·거부된 꼴도 **사유를 남긴다** — 조용히 0 이 되면 그 리그가
       명단 없이 도는 것을 아무도 모른다.
    """
    spec = str(spec or "")
    head = spec.split(":", 1)[0]
    if head == "adapter":
        return _from_adapter(spec)
    if head == "url":
        return await _from_url(spec, net=net)
    if head == "fdorg":
        return await _from_fdorg(spec, net=net)
    if head == "tsdb":
        return await _from_tsdb(spec, net=net)
    if head == "fotmob":
        return await _from_fotmob(spec, net=net)
    return [], (f"🔴 모르는 `teams_from` 꼴: {spec} — §8-4 가 허용한 것은 "
                f"{list(ROSTER_SOURCES)} 다")

def spec_banned(spec: str) -> str:
    """🔴 그 `teams_from` 선언이 **§8-4 가 금지한 것**인가. 사유 또는 빈 글.

    ⚠️ 금지 목록을 **여기 손으로 적지 않는다**(사본 금지) — `roster_from` 이
       이미 꼴마다 판정한다. 🔴 그 판정과 **같은 머리글자**를 쓴다:
       `ROSTER_SOURCES` 에 없는 머리는 금지이거나 모르는 것이다.
    """
    head = str(spec or "").split(":", 1)[0]
    if not head:
        return "빈 선언"
    if head in ROSTER_SOURCES:
        return ""
    return (f"🔴 §8-4 가 허용하지 않는 출처 `{head}` — 허용은 "
            f"{list(ROSTER_SOURCES)} 다")


async def teams_of(key: str, *, net=None) -> tuple[list[str], str]:
    """🔴 그 리그의 **팀 이름들**(대체 표기 포함)과 **어디서 왔나**.

    `teams_from` 은 **목록**이다 — 위에서부터 전부 받아 **합친다**. ⚠️ 첫 성공에서
    멈추지 않는다: 한 길이 잘리면(tsdb) 다른 길이 메워야 하고, 합쳐도 같은 이름은
    한 번만 센다.
    🔴 못 받으면 `([], 사유)` 다 — 빈 목록을 "팀이 없다"로 읽지 않게 사유를 준다.
    """
    row = next((x for x in leagues() if str(x.get("key")) == str(key)), None)
    if not row:
        return [], f"명부에 `{key}` 가 없다"
    specs = row.get("teams_from") or []
    if isinstance(specs, str):
        specs = [specs]
    if not specs:
        return [], f"`{key}` 에 `teams_from` 이 없다"
    p = _cache_path(key)
    if _fresh(p, key):
        try:
            box = json.loads(p.read_text(encoding="utf-8"))
            for k, v in (box.get("locals") or {}).items():
                _LOCALS.setdefault(str(k), str(v))
            for k, v in (box.get("ext") or {}).items():
                _EXT_IDS.setdefault(str(k), str(v))
            return [str(x) for x in box.get("teams") or []], \
                f"{box.get('why') or '캐시'}(캐시)"
        except (OSError, ValueError):
            pass            # 🔴 깨진 캐시는 **조용히 무시하고 다시 받는다**
    names: list[str] = []
    whys: list[str] = []
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **이름마다 어디서 왔나를 적는다**(실측 2026-10-04)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 캐시가 `why` 로 *"공식 API 30팀 · TheSportsDB 10팀"* 만 적어서, **어느
    #     이름이 금지 출처에서 왔는지** 가릴 수 없었다. 🔴 그래서 §8-4 를 적용할
    #     때 **통째로 지우는 수밖에** 없었고 그러면 공식 API 30팀까지 버린다.
    #  🔴 이름마다 출처를 적으면 **금지 출처 것만** 걷을 수 있다.
    by: dict[str, str] = {}
    # 🔴 **이 리그에서 버린 짧은 이름만** 센다(다른 리그 것이 섞이지 않게)
    mark = len(_SHORT_DROPPED)
    for spec in specs:
        # 🔴 꼴을 고르는 자리는 **`roster_from` 하나**다(§8-4 · 사본 금지)
        got, why = await roster_from(str(spec), net=net)
        names += got
        whys.append(why)
        # ⚠️ **먼저 들어온 길이 이긴다** — 같은 이름이면 앞선(더 확실한) 출처다
        for n in got:
            by.setdefault(norm(n), str(spec))
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **버린 짧은 이름을 사유에 적는다** — 조용한 0 금지(#2·#3)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ `short_name_ok` 를 만들고 **부르는 곳만** 두면, 버린 사실이 아무 데도
    #     안 남는다. 🔴 안 이어진 코드는 없는 코드보다 나쁘다(CLAUDE.md #2).
    #  🔴 사유는 캐시에 함께 저장된다 — 다음 세션이 *"왜 `Tigers` 가 없나"* 를
    #     물을 때 답이 **거기 있어야** 한다.
    dropped = _SHORT_DROPPED[mark:]
    if dropped:
        whys.append(f"🔴 짧은 이름 {len(dropped)}개를 **버렸다**(부딪친다): "
                    + " · ".join(dropped[:3])
                    + (f" … 그리고 {len(dropped) - 3}개" if len(dropped) > 3
                       else ""))
    # 🔴 **순서를 지키며** 중복을 지운다 — 앞선 길(더 확실한 길)이 이긴다
    seen, uniq = set(), []
    for n in names:
        k = norm(n)
        if k and k not in seen:
            seen.add(k)
            uniq.append(n)
    why = " · ".join(whys)
    if uniq:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            # 🔴 현지 표기도 함께 저장한다 — 이 리그에서 나온 것만 담는다
            keys = {norm(x) for x in uniq}
            mine = {k: v for k, v in _LOCALS.items() if norm(v) in keys}
            exts = {k: v for k, v in _EXT_IDS.items() if k in keys}
            # 🔴 **도장을 찍는다** — 안 찍으면 다음 판도 같은 병이다
            p.write_text(json.dumps({"teams": uniq, "why": why, "locals": mine,
                                     "ext": exts, "stamp": cache_stamp(key),
                                     # 🔴 이름마다 **어느 선언에서 왔나**
                                     "by": by},
                                    ensure_ascii=False), encoding="utf-8")
        except OSError as exc:                          # pragma: no cover
            logger.info("[league_index] 캐시를 못 썼다: %s", exc)
    return uniq, why


async def build(*, net=None, only: list[str] | None = None) -> dict[str, str]:
    """🔴 **팀(정규화) → 리그** 색인. 명부 순서대로 채운다.

    ⚠️ **먼저 들어온 리그가 이긴다** — 명부 순서가 곧 우선순위다. 같은 이름이
       두 리그에 있으면(예: `Tigers`) 위에 적힌 리그가 가져간다. 🔴 그 충돌을
       조용히 넘기지 않고 로그에 남긴다.
    """
    out: dict[str, str] = {}
    for lg in leagues():
        key = str(lg.get("key"))
        if only and key not in only:
            continue
        names, why = await teams_of(key, net=net)
        if not names:
            logger.info("[league_index] %s 팀 명단 0건 — %s", key, why)
            continue
        dup = 0
        for n in names:
            k = norm(n)
            if not k:
                continue
            if k in out:
                dup += 1
                continue
            out[k] = key
        logger.info("[league_index] %s %d팀 (%s)%s", key, len(names), why,
                    f" · 겹쳐서 건너뛴 이름 {dup}개" if dup else "")
    return out


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **캐시만 보는 조회** — 통신 없이, 어디서든
# ══════════════════════════════════════════════════════════════════


def cached_index() -> dict[str, str]:
    """🔴 디스크에 받아 둔 명단으로 만든 **팀 → 리그** 색인. 통신하지 않는다.

    ⚠️ 캐시가 없으면 **빈 dict** 다 — 그러면 부르는 쪽이 종전 길로 간다.
       있는 척하지 않는다.
    🔴 명부 순서를 지킨다(먼저 적힌 리그가 이긴다) — `build` 와 같은 규율이다.
    """
    out: dict[str, str] = {}
    for lg in leagues():
        key = str(lg.get("key"))
        p = _cache_path(key)
        if not p.exists():
            continue
        try:
            box = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for n in (box.get("teams") or []):
            k = norm(str(n))
            if k and k not in out:
                out[k] = key
    return out


def league_of_team(name: str) -> str:
    """🔴 그 팀의 리그(캐시만 본다). 모르면 빈 문자열.

    ⚠️ 통신하지 않는다 — `langs_for` 같은 **동기 함수**가 부르는 자리다.
       그 자리에서 네트워크를 때리면 질의 하나가 몇 초씩 멈춘다.
    """
    return cached_index().get(norm(name), "")


def local_of_team(name: str) -> str:
    """🔴 그 팀의 **현지 표기**(`Kashiwa Reysol` → `柏レイソル`). 모르면 빈 문자열.

    ⚠️ 캐시만 본다 — 통신하지 않는다. 캐시가 없으면 빈 문자열이고, 부르는 쪽이
       종전 길(`entities.yaml` 선언)로 간다.
    🔴 `entities.yaml` 선언이 **먼저**다 — 사용자가 적은 것이 받아 온 것보다 낫다.
       이것은 선언이 없을 때의 **대체**다.
    """
    # 🔴🔴 **파일 훑기를 "비었을 때"로 가르지 않는다** — 실측 2026-10-06: 다른 호출이
    #    `_LOCALS` 를 **일부만** 채워 두면(`build` 가 한 리그만 돌 때) 이 함수가
    #    *"이미 있다"* 고 보고 파일을 안 읽어 `柏レイソル` 을 잃었다(전체 스위트에서만
    #    빨개지는 흔들림이었다). 🔴 **못 찾았을 때 한 번 더 훑는다.**
    got = _LOCALS.get(norm(name), "")
    if not got and not _LOCALS_READ:
        _LOCALS_READ.add(1)
        # 캐시 파일을 한 번 훑어 채운다(없으면 비어 있다)
        for lg in leagues():
            p = _cache_path(str(lg.get("key")))
            if not p.exists():
                continue
            try:
                box = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for k, v in (box.get("locals") or {}).items():
                _LOCALS.setdefault(str(k), str(v))
        got = _LOCALS.get(norm(name), "")
    return got
