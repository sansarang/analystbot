"""[§8-23] Go 크롤러가 Redis에 남긴 결과를 읽는다.

왜 별도 서비스인가:
  - 크롤러가 죽어도 봇은 계속 응답한다(프로세스 분리).
  - Go는 동시 수집에 강하다 — 11경기를 goroutine으로 병렬 조회한다.
  - **LLM 0회**라 실패해도 쿼터·비용이 0이다.

⚠️ 크롤러는 **Redis에만 쓴다.** Postgres를 직접 건드리지 않으므로, 검증을 통과한
   값만 파이썬이 DB에 반영한다. 크롤러가 DB를 쓰면 미검증 값이 λ로 흘러간다.

⚠️ **크롤러가 없어도 파이프라인은 돈다.** 파이썬 쪽 naver_kbo·yahoo_npb가 같은
   소스를 직접 긁는다 — 크롤러는 그것을 **더 자주**(평시 60분, 타순 창 2분)
   돌려 변화를 잡는 역할이다.
"""

import json
import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

HEARTBEAT_KEY = "crawl:heartbeat"
STALE_MINUTES = 180     # 평시 60분 × 3 — 이보다 오래되면 죽은 것으로 본다
SNAPSHOT_TTL_SEC = 6 * 3600


def snapshot_key(away: str, home: str, game_id=None) -> str:
    """더블헤더는 away@home#id. id 없으면 옛 키."""
    if game_id:
        return f"{away}@{home}#{game_id}"
    return f"{away}@{home}"


def _hhmm_of(starts_at) -> str:
    if starts_at is None:
        return ""
    if hasattr(starts_at, "strftime"):
        try:
            from zoneinfo import ZoneInfo

            dt = starts_at
            if getattr(dt, "tzinfo", None) is None:
                return dt.strftime("%H:%M")
            return dt.astimezone(ZoneInfo("Asia/Seoul")).strftime("%H:%M")
        except Exception:
            return ""
    s = str(starts_at)
    if "T" in s and len(s) >= 16:
        return s[11:16]
    if len(s) >= 5 and s[2] == ":":
        return s[:5]
    return ""


def snapshot_keys_for(row: dict) -> list[str]:
    away, home = row.get("away"), row.get("home")
    if not away or not home:
        return []
    keys: list[str] = []
    ext = row.get("ext_id")
    if ext:
        keys.append(snapshot_key(away, home, ext))
        s = str(ext)
        if ":" in s:
            keys.append(snapshot_key(away, home, s.rsplit(":", 1)[-1]))
    gid = row.get("game_id")
    if gid and str(gid) != str(ext or ""):
        keys.append(snapshot_key(away, home, gid))
    keys.append(snapshot_key(away, home))
    # 순서 유지한 채 중복 제거
    seen: set[str] = set()
    out = []
    for k in keys:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


def snapshot_for_game(snap: dict | None, row: dict) -> dict:
    """스냅샷에서 그 경기만. 더블헤더는 game_id·시각으로 고른다."""
    snap = snap or {}
    for k in snapshot_keys_for(row):
        hit = snap.get(k)
        if hit:
            return hit
    away, home = row.get("away"), row.get("home")
    if not away or not home:
        return {}
    prefix = f"{away}@{home}"
    hits = [v for k, v in snap.items() if k == prefix or k.startswith(prefix + "#")]
    if len(hits) == 1:
        return hits[0]
    want = _hhmm_of(row.get("starts_at"))
    if want and len(hits) > 1:
        matched = [v for v in hits if _hhmm_of(v.get("starts_at")) == want]
        if len(matched) == 1:
            return matched[0]
    return {}


def _key(sport: str, date: str, suffix: str) -> str:
    return f"crawl:{sport}:{date}:{suffix}"


async def load_snapshot(redis, sport: str, date: str) -> dict:
    """최신 스냅샷 {"원정@홈": {field: value}}. 없으면 빈 dict."""
    raw = await redis.get(_key(sport, date, "latest"))
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("[crawler_feed] 손상된 스냅샷 %s %s", sport, date)
        return {}


async def write_snapshot(redis, sport: str, date: str, games: dict) -> None:
    """스냅샷 전체 저장. Go 크롤러와 같은 키."""
    if redis is None or not date:
        return
    await redis.set(
        _key(sport, date, "latest"),
        json.dumps(games or {}, ensure_ascii=False),
        ex=SNAPSHOT_TTL_SEC,
    )


async def upsert_snapshot_game(redis, sport: str, date: str, jg: dict) -> None:
    """한 경기를 스냅샷에 얹는다. 빈 값으로 있는 타순을 지우지 않는다."""
    if redis is None or not date:
        return
    away, home = jg.get("away"), jg.get("home")
    if not away or not home:
        return
    key = snapshot_key(away, home, jg.get("ext_id") or jg.get("game_id"))
    res = jg.get("research") or {}
    lu_h = ((res.get("home_lineup") or {}).get("order") or "").strip(" -")
    lu_a = ((res.get("away_lineup") or {}).get("order") or "").strip(" -")
    hp = ((res.get("home_pitcher") or {}).get("name")
          or jg.get("home_pitcher") or "")
    ap = ((res.get("away_pitcher") or {}).get("name")
          or jg.get("away_pitcher") or "")
    status = jg.get("lineup_status") or ""
    starter_status = "확정" if status == "confirmed" else (
        (res.get("starter_status") or "").strip())
    fields = {
        "home_pitcher": (hp or "").strip(),
        "away_pitcher": (ap or "").strip(),
        "lineup_home": lu_h,
        "lineup_away": lu_a,
        "starter_status": starter_status,
        "status": jg.get("status") or "scheduled",
    }
    if jg.get("ext_id"):
        fields["game_id"] = str(jg["ext_id"])
    snap = await load_snapshot(redis, sport, date)
    prev = snap.get(key) or {}
    merged = dict(prev)
    for k, v in fields.items():
        if v:
            merged[k] = v
    snap[key] = merged
    await write_snapshot(redis, sport, date, snap)


async def load_changes(redis, sport: str, date: str, limit: int = 50) -> list[dict]:
    """오늘 누적된 변화 목록 (오래된 것부터).

    선발 교체·라인업 변경이 여기 쌓인다. **언제 바뀌었는지**가 정보다 —
    경기 직전 교체는 시장이 늦게 반영하는 몇 안 되는 신호다.
    """
    rows = await redis.lrange(_key(sport, date, "changes"), -limit, -1)
    out = []
    for r in rows or []:
        try:
            out.append(json.loads(r))
        except (TypeError, ValueError):
            continue
    return out


async def is_alive(redis) -> tuple[bool, str]:
    """크롤러가 살아 있는가. 반환 (살아있음, 사람이 읽을 설명).

    ⚠️ 조용한 정지가 가장 위험하다 — 데이터가 어제 값으로 굳어도 아무도 모른다.
    """
    raw = await redis.get(HEARTBEAT_KEY)
    if not raw:
        return False, "크롤러 하트비트 없음 — 미실행"
    try:
        at = datetime.fromisoformat(raw)
    except ValueError:
        return False, f"하트비트 형식 오류: {raw[:40]}"
    age = (datetime.now(UTC) - at.astimezone(UTC)).total_seconds() / 60
    if age > STALE_MINUTES:
        return False, f"크롤러 {age:.0f}분째 멈춤 (마지막 {at:%H:%M})"
    return True, f"크롤러 정상 (마지막 {at:%H:%M})"


# 사람이 즉시 알아야 할 필드. ⚠️ 여기서 **중요도를 점수화하지 않는다** —
# "무엇이 바뀌었다"만 사실로 전하고, 영향 판단은 판정이 한다.
_NOTABLE_LABEL = {"home_pitcher": "홈 선발", "away_pitcher": "원정 선발",
                  "lineup_home": "홈 라인업", "lineup_away": "원정 라인업",
                  "starter_status": "선발 발표", "status": "경기 상태"}


def notable_rows(changes: list[dict]) -> list[dict]:
    """[A-1단계] 사람이 읽을 문장 **과 함께 경기 키를 유지**한 변화 목록.

    ⚠️ `notable_changes()`는 걸러낸 문장만 돌려주므로 원본 목록과 **짝이 맞지
       않는다.** 둘을 zip하면 다른 경기의 변화가 엉뚱한 경기에 붙는다.
       변화 감지가 재판정을 트리거하므로 이 오배치는 조용한 오판이 된다.
    """
    out = []
    for c in changes or []:
        f = c.get("field")
        if f not in _NOTABLE_LABEL:
            continue
        at = (c.get("at") or "")[11:16]
        frm, to = c.get("from") or "없음", c.get("to") or "없음"
        out.append({"game": c.get("game", "?"),
                    "change": f"{at} {_NOTABLE_LABEL[f]}: {frm} → {to}"})
    return out


def notable_changes(changes: list[dict]) -> list[str]:
    """[§8-23] 사람이 즉시 알아야 할 변화만 한국어 한 줄로.

    ⚠️ 중요도를 점수화하지 않는다 — "무엇이 바뀌었다"만 사실로 전하고,
       경기에 어떤 영향인지는 판정이 결정한다.
    """
    out = []
    for c in changes:
        f = c.get("field")
        if f not in _NOTABLE_LABEL:
            continue
        at = (c.get("at") or "")[11:16]
        frm, to = c.get("from") or "없음", c.get("to") or "없음"
        out.append(f"{at} {c.get('game','?')} {_NOTABLE_LABEL[f]}: {frm} → {to}")
    return out


_LINEUP_FIELDS = ("lineup_home", "lineup_away")
_STARTER_FIELDS = ("home_pitcher", "away_pitcher")

# 크롤러 status 필드. 빈 값은 정상(미시작). 값이 있는데 취소 표시면 DB를 맞춘다.
# 실측 2026-08-28: 네이버 `경기취소`가 Redis에만 있고 games.status는 scheduled
# 로 남아 발송이 취소 경기를 카드로 보낼 뻔했다.
_CANCEL_MARKERS = (
    "취소", "中止", "キャンセル", "cancelled", "canceled", "연기",
    "서스펜디드", "중단", "suspended", "postponed", "サスペンデッド",
)


def is_cancelled_game(game: dict | None) -> bool:
    """크롤러 스냅샷 한 경기가 취소·연기인가."""
    if not game:
        return False
    status = str(game.get("status") or "")
    return any(m in status for m in _CANCEL_MARKERS)


async def mark_cancelled_games(pool, rows, snap: dict) -> list[int]:
    """크롤러가 취소로 표시한 경기를 DB `cancelled`로 맞춘다.

    크롤러는 Postgres를 안 건드린다. 파이썬이 반영하지 않으면 발송·채점이
    예정 경기를 계속 본다. 반환: 갱신한 game id.
    """
    ids: list[int] = []
    for r in rows or []:
        game = snapshot_for_game(snap, r if isinstance(r, dict) else dict(r))
        if not is_cancelled_game(game):
            continue
        await pool.execute(
            "UPDATE games SET status = 'cancelled', updated_at = now() "
            "WHERE id = $1 AND status = 'scheduled'",
            r["id"])
        ids.append(int(r["id"]))
        logger.info("[crawler_feed] 취소 반영 game=%s %s", r["id"],
                    snapshot_key(r["away"], r["home"], r.get("ext_id")))
    return ids


def _hhmm(at: str) -> str:
    """RFC3339 → "HH:MM" (KST). 크롤러가 KST로 찍으므로 변환하지 않는다."""
    return (at or "")[11:16]


def lineup_timeline(changes: list[dict], jg: dict) -> dict:
    """[§8-35] 이 경기의 라인업·선발 **변화 이력**. 카드 ②칸의 시각 정보.

    **언제 바뀌었는지가 정보다.** "18:05에 4번 타자가 빠졌다"는 그 자체로 신호이며,
    경기 직전 교체는 다른 소스가 늦게 반영하는 몇 안 되는 사실이다.
    스냅샷 하나만 보는 구조로는 영원히 볼 수 없다.

    ⚠️ 중요도를 매기지 않는다 — "무엇이 언제 바뀌었다"만 사실로 낸다.
       그것이 경기에 어떤 영향인지는 해석 단계가 정한다.
    """
    keys = set(snapshot_keys_for(jg))
    pair = f"{jg.get('away')}@{jg.get('home')}"
    out: dict = {}
    lineup_changes, starter_changes = [], []
    for c in changes or []:
        gkey = c.get("game") or ""
        if gkey not in keys and not gkey.startswith(pair + "#"):
            continue
        f, kind, at = c.get("field"), c.get("kind"), _hhmm(c.get("at"))
        if f in _LINEUP_FIELDS:
            side = "홈" if f.endswith("home") else "원정"
            if kind == "added":
                # 첫 등장 = 발표 시각. 이미 있으면 더 이른 것을 남긴다.
                prev = out.get("lineup_announced_at")
                if not prev or (at and at < prev):
                    out["lineup_announced_at"] = at
            elif kind == "changed":
                lineup_changes.append(f"{at} {side} 라인업 변경")
        elif f in _STARTER_FIELDS and kind == "changed":
            side = "홈" if f.startswith("home") else "원정"
            starter_changes.append(
                f"{at} {side} 선발 {c.get('from') or '없음'} → {c.get('to') or '없음'}")
    if lineup_changes:
        out["lineup_changes"] = lineup_changes
    if starter_changes:
        out["starter_changes"] = starter_changes
    return out


def merge_into_research(research: dict, jg: dict, snap: dict,
                        changes: list[dict] | None = None) -> list[str]:
    """크롤러 스냅샷을 research에 얹는다. 반환: 채운 필드 목록.

    ⚠️ 선발 **이름만** 넘긴다. 성적(ERA·WHIP)은 파이썬 수집기가 공식 소스에서
       받은 것을 쓴다 — 크롤러는 '누가 나오나'를 가장 빨리 아는 역할이다.
    """
    game = snapshot_for_game(snap, jg)
    if not game:
        return []
    filled = []
    for side in ("home", "away"):
        name = (game.get(f"{side}_pitcher") or "").strip()
        if not name:
            continue
        blk = research.setdefault(f"{side}_pitcher", {})
        if blk.get("name") != name:
            blk["name"] = name
            # 이름이 바뀌면 이전 소스의 성적은 그 투수 것이 아니다
            for k in ("era_season", "whip", "ip_avg_recent", "era_vs_opponent"):
                blk.pop(k, None)
            filled.append(f"{side}_pitcher.name")
    # [§8-32] 라인업은 **홈·원정을 나눠서** 얹는다.
    #   실사고(2026-08-27): 크롤러가 `"lineup": 홈 | 원정` 합본을 보냈고 키는
    #   `원정@홈` 순이라 **어느 쪽이 어느 팀인지 알 수 없었다.** 게다가 이 값을
    #   읽는 코드가 앱 전체에 하나도 없어 타순 정보가 통째로 버려지고 있었다.
    #   NPB는 예전엔 타순이 없는데도 같은 `lineup` 키에 "확정"/"예상"이라는
    #   **상태값**을 넣고 있어, 파이썬이 그것을 라인업으로 착각해 저장했다.
    #   지금은 타순이 `lineup_home`/`lineup_away`로, 발표 상태는 `starter_status`로
    #   갈라져 있다. 빈 타순은 정상(시작 ~30분 전 발표)이다.
    for side in ("home", "away"):
        order = (game.get(f"lineup_{side}") or "").strip(" -")
        if not order:
            continue
        blk = research.setdefault(f"{side}_lineup", {})
        if blk.get("order") != order:
            blk["order"] = order
            blk["source"] = "크롤러"
            filled.append(f"{side}_lineup.order")
    # 선발 발표 상태(NPB 予告/확정) — 라인업과 **다른 것**이므로 다른 키에 넣는다.
    status = (game.get("starter_status") or "").strip()
    if status and status != "미상":
        if research.get("starter_status") != status:
            research["starter_status"] = status
            filled.append("starter_status")
    for k, v in (lineup_timeline(changes or [], jg) or {}).items():
        if research.get(k) != v:
            research[k] = v
            filled.append(k)
    return filled
