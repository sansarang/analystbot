"""[DS-2a] 변경 감지 — **정해진 페이지가 바뀐 순간**을 잡는다. 비용 0.

🔴 **왜.** 2026-09-21 에 우리가 늦게 안 셋이 전부 **타이밍 실패**였다:
     08:30 마린스 세이부전 중지(태풍) · 11:06 라쿠텐 등록 공시 ·
     12:40경 라쿠텐-소프트뱅크 우천 중지.
   페이지는 그 자리에 있었고 우리가 그 순간에 안 봤을 뿐이다.
   **검색 API 를 사도 이건 안 고쳐진다.**

🔴 그리고 그날 나는 11:50 기사("예정대로 개장")를 보고 "개최"라고 보고했다.
   그 뒤 스포츠나비가 `試合中止 降雨のため` 를 띄웠다. 상태 사실에 **시각이
   없어서 낡은 사실이 새 사실을 이겼다.** 그래서 `StatusFact` 는 `as_of` 를
   **필수**로 받고, 최신이 이기고, 30분 지나면 stale 이다.

⚠️ 여기서 **요청을 직접 만들지 않는다.** 전부 DS-1 런타임(`runtime.Runtime`)
   을 지난다 — 그래야 robots·간격·상한·서킷이 이 경로에도 붙는다.
   계약 `test_모든_외부_요청이_런타임을_지난다` 가 이 방향을 잠근다.
⚠️ 주기·문턱은 `config/deepsearch.yaml` 하나에서 온다(사본 금지).
⚠️ `ignore_selectors` 의 원본은 `config/source_map.yaml` 이다. 여기서 목록을
   갖지 않는다 — 받아 쓸 뿐이다.
"""
from __future__ import annotations

import hashlib
import logging
import re
import statistics
from dataclasses import dataclass
from datetime import datetime

from app.deepsearch.runtime import load_config

logger = logging.getLogger(__name__)

_WS = re.compile(r"\s+")


def _w(key, default=None):
    return ((load_config().get("watch") or {}).get(key, default))


# ── 정규화·해시 (순수 함수) ───────────────────────────────────────
def normalize(html: str, ignore_selectors=None) -> str:
    """잡음을 뺀 본문 텍스트.

    🔴 **잡음을 안 빼면 매 주기가 오탐이다.** 광고·조회수·갱신시각은 내용이
       그대로여도 매번 바뀐다. 그러면 "바뀜"이 아무 뜻도 없어진다.
    ⚠️ 어떤 영역이 잡음인지는 페이지마다 다르다 — 그래서 `source_map` 이
       정하고 여기는 받아만 쓴다.
    """
    text = html or ""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(text, "lxml")
        for sel in (ignore_selectors or []):
            for node in soup.select(sel):
                node.decompose()
        text = soup.get_text(" ")
    except Exception as exc:          # 파서가 죽어도 감지는 돌아야 한다
        logger.debug("[watch] 정규화 실패 — 원문으로 해시한다: %s", exc)
    return _WS.sub(" ", text).strip()


def content_hash(html: str, ignore_selectors=None) -> str:
    return hashlib.sha256(
        normalize(html, ignore_selectors).encode("utf-8")).hexdigest()


# ── 주기 (순수 함수) ──────────────────────────────────────────────
def interval_min(*, now: datetime, kickoff: datetime | None,
                 kind: str = "game") -> int:
    """다음에 언제 볼까(분). 🔴 값은 config 가 원본이다.

    ⚠️ 공시·중지 공지는 **경기 시각과 무관하게** 자주 본다 — 그것이 늦으면
       경기 자체가 없어진 걸 모른 채 카드를 만든다(09-21 에 실제로 그랬다).
    """
    iv = _w("intervals") or {}
    if kind == "notice":
        return int(iv.get("notice_min") or 10)
    if kind != "game" or kickoff is None:
        return int(iv.get("default_min") or 60)
    mins = (kickoff - now).total_seconds() / 60.0
    for ph in (iv.get("game_phases") or []):
        if mins > float(ph.get("gt_min", 0)):
            return int(ph.get("every_min") or 60)
    return int(iv.get("default_min") or 60)


# ── 상태 사실 ─────────────────────────────────────────────────────
@dataclass(frozen=True)
class StatusFact:
    """개최·중지·지연 같은 **뒤집히는 사실**.

    🔴 `as_of` 없이 만들 수 없다. 시각 없는 상태는 사실이 아니라 소문이다 —
       09-21 에 내가 11:50 기사를 근거로 "개최"라고 보고했고, 그 뒤 중지
       공지가 떴다. 시각이 있었다면 코드가 최신을 골랐을 것이다.
    """

    value: str
    as_of: datetime | None

    def __post_init__(self):
        if self.as_of is None:
            raise ValueError("상태 사실에는 as_of 가 있어야 한다")

    def is_stale(self, *, now: datetime) -> bool:
        limit = float(_w("status_stale_min") or 30)
        return (now - self.as_of).total_seconds() / 60.0 > limit

    def beats(self, other: "StatusFact | None") -> bool:
        """더 최신이면 이긴다. ⚠️ 같은 시각이면 **이기지 않는다** —
        동점일 때 뒤집으면 순서에 따라 결과가 달라진다."""
        return other is None or self.as_of > other.as_of


# ── 인지 지연 ─────────────────────────────────────────────────────
def lag_minutes(events) -> dict:
    """"공지 게시 → 봇 인지" 지연(분).

    ⚠️ 게시 시각을 모르는 건 **0분으로 세지 않는다.** 그러면 지연이 작아
       보이고, 작아 보이는 수치는 고칠 이유를 없앤다. `unknown` 으로 센다.
    """
    vals, unknown = [], 0
    for e in (events or []):
        pub, seen = e.get("published_at"), e.get("changed_at")
        if pub is None or seen is None:
            unknown += 1
            continue
        vals.append(round((seen - pub).total_seconds() / 60.0, 1))
    if not vals:
        return {"n": 0, "median": None, "max": None, "unknown": unknown}
    return {"n": len(vals), "median": float(statistics.median(vals)),
            "max": float(max(vals)), "unknown": unknown}


# ── 감시기 ────────────────────────────────────────────────────────
class Watcher:
    """해시가 바뀐 때만 파서를 돌린다.

    🔴 `store` 는 Redis 를 그대로 받는다(`get`/`set`). 테스트는 dict 대역을
       넣는다 — 계약이 진짜 Redis 없이 돌아야 한다.
    """

    _PREFIX = "ds2a:watch:"

    def __init__(self, *, runtime, store, parse=None, on_event=None):
        self._rt, self._store = runtime, store
        self._parse = parse
        self._on_event = on_event
        self._strikes: dict[str, int] = {}
        self._excluded: dict[str, str] = {}

    def is_watched(self, url: str) -> bool:
        return url not in self._excluded

    def excluded_reason(self, url: str) -> str | None:
        return self._excluded.get(url)

    async def _mem(self, url: str) -> dict:
        import json

        raw = await self._store.get(self._PREFIX + url)
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except Exception:
            return {}

    async def _save(self, url: str, mem: dict) -> None:
        import json

        await self._store.set(self._PREFIX + url,
                              json.dumps(mem, ensure_ascii=False))

    async def check(self, row: dict) -> dict:
        """한 번 본다. 반환은 무슨 일이 있었나 — **조용히 넘어가지 않는다.**"""
        url = row.get("url") or ""
        if not self.is_watched(url):
            return {"changed": False, "skipped": "excluded",
                    "reason": self._excluded.get(url)}

        mem = await self._mem(url)
        got = await self._rt.fetch(url, etag=mem.get("etag"),
                                   last_modified=mem.get("last_modified"))
        if getattr(got, "not_modified", False):
            # 🔴 304 는 본문이 안 왔다는 뜻이다 — 파서를 돌리면 빈 것을 판다.
            return {"changed": False, "not_modified": True}

        html = (got.body or b"").decode("utf-8", "replace")
        h = content_hash(html, row.get("ignore_selectors"))
        first = "hash" not in mem
        changed = first or h != mem.get("hash")

        if changed and not first:
            n = self._strikes[url] = self._strikes.get(url, 0) + 1
            limit = int(_w("noise_strikes") or 5)
            if n >= limit:
                # ⚠️ 잡음을 빼고도 매번 바뀌면 **이 페이지는 감지 대상이
                #    아니다.** 계속 두면 파서를 매 주기 돌려 비용만 쓴다.
                self._excluded[url] = (
                    f"잡음 제거 후에도 연속 {n}회 **매번** 바뀐다 — "
                    f"ignore_selectors 를 손보기 전에는 감지가 무의미하다")
                logger.warning("[watch] 제외 %s — %s", url, self._excluded[url])
        elif not changed:
            self._strikes[url] = 0

        mem.update({"hash": h, "etag": got.etag,
                    "last_modified": got.last_modified})
        await self._save(url, mem)

        parsed = None
        if changed and self._parse is not None:
            parsed = self._parse(html, row)
        if changed and self._on_event is not None:
            await self._on_event({"url": url, "kind": row.get("kind"),
                                  "parsed_ok": parsed is not None})
        return {"changed": changed, "hash": h, "first": first,
                "parsed": parsed}


# ── 대상 목록 · 잡 (DS-2) ─────────────────────────────────────────
_MAP_PATH = (__import__("pathlib").Path(__file__).resolve().parents[2]
             / "config" / "source_map.yaml")


def watch_rows() -> list[dict]:
    """감시 대상. 🔴 **원본은 `config/source_map.yaml`** 하나다(사본 금지).

    🔴 `blocked` 이거나 `robots` 가 거짓인 행은 **뺀다** — 차단을 우회하지
       않는다. 지금 빠지는 것: koreabaseball 4행 · 네이버 1행 · fotmob 1행.
    """
    try:
        import yaml

        doc = yaml.safe_load(_MAP_PATH.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.error("[watch] %s 를 못 읽었다 — 감시 0건: %s", _MAP_PATH, exc)
        return []
    out = []
    for r in (doc.get("sources") or []):
        if not r.get("watch"):
            continue
        if r.get("blocked") or r.get("robots") is False:
            logger.warning("[watch] 차단된 행이 watch 로 표시돼 있다 — 뺀다: %s",
                           r.get("url"))
            continue
        out.append({"url": str(r.get("url") or ""),
                    "kind": str(r.get("watch_kind") or "notice"),
                    "ignore_selectors": list(r.get("ignore_selectors") or []),
                    "league": r.get("league"), "fact": r.get("fact")})
    return out


def fill_url(url: str, values: dict) -> str | None:
    """`{yahoo_id}` 같은 자리를 채운다. **못 채우면 None** — 건너뛴다.

    ⚠️ 빈 자리를 빈 문자열로 채우지 않는다. 그러면 엉뚱한 주소를 친다 —
       `scout_config.queries` 가 같은 이유로 같은 규칙을 쓴다.
    """
    import re as _re

    u = str(url or "")
    need = _re.findall(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", u)
    if not need:
        return u
    for k in need:
        v = (values or {}).get(k)
        if not v:
            return None
        u = u.replace("{" + k + "}", str(v))
    return u


#: 어느 주소를 어느 파서가 읽나. 🔴 **주소 조각으로 고른다** — 목록을 길게
#  만들지 않는다. 없으면 `None` 이고, 그때 감시는 "바뀐 것만 세고" 끝난다.
_PARSERS: tuple = (
    ("npb.jp/announcement/", "parse_npb_scoreboard"),
)


def parser_for(row: dict):
    """이 행을 읽을 파서. 없으면 None.

    ⚠️ 파서가 없다고 감시를 멈추지 않는다 — 변화 이벤트만으로도
       **인지 지연**은 잴 수 있다.
    """
    url = str((row or {}).get("url") or "")
    for frag, name in _PARSERS:
        if frag in url:
            from app.deepsearch import parsers as P

            return getattr(P, name, None)
    return None


async def run_watch(pool, redis, *, runtime=None, parse=None) -> dict:
    """[DS-2] 감시 1회. 🔴 **조회만 한다** — 판정·발송에 닿지 않는다.

    ⚠️ 경기 페이지 행은 오늘 경기의 `ext_id`(`yahoo:2021039443`)에서 id 를
       꺼내 채운다. 못 채우면 건너뛴다.
    ⚠️ 변화는 `watch_events` 에 남긴다 — **언제 알았는지**가 없으면 인지 지연을
       못 잰다.
    """
    from app.deepsearch.runtime import Runtime

    rt = runtime or Runtime()
    rows = watch_rows()
    if not rows:
        logger.info("[watch] 감시 대상 0건")
        return {"rows": 0, "changed": 0, "skipped": 0, "failed": 0}

    ids: list[str] = []
    if any("{" in r["url"] for r in rows) and pool is not None:
        try:
            got = await pool.fetch(
                "SELECT ext_id FROM games WHERE sport='npb' "
                "AND (starts_at AT TIME ZONE 'Asia/Seoul')::date "
                "= (now() AT TIME ZONE 'Asia/Seoul')::date")
            ids = [str(x["ext_id"]).split(":", 1)[-1] for x in got
                   if str(x["ext_id"] or "").startswith("yahoo:")]
        except Exception as exc:
            logger.warning("[watch] 오늘 경기 조회 실패 — 경기 페이지는 건너뛴다: %s",
                           exc)

    async def _event(ev):
        if pool is None:
            return
        try:
            await pool.execute(
                "INSERT INTO watch_events (url, changed_at, kind, parsed_ok) "
                "VALUES ($1, now(), $2, $3)",
                ev.get("url"), ev.get("kind"), bool(ev.get("parsed_ok")))
        except Exception as exc:
            logger.warning("[watch] 원장 적재 실패: %s", exc)

    # 🔴 [DS-2P] **파서를 붙인다.** 없으면 변화만 센다(그것만으로도 인지
    #    지연은 잴 수 있다).
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo as _Z

    def _parse(html, row):
        fn = parse or parser_for(row)
        if fn is None:
            return None
        try:
            got = fn(html, as_of=_dt.now(_Z("Asia/Seoul")),
                     url=row.get("url") or "")
        except Exception as exc:
            logger.warning("[watch] 파서 실패 %s: %s",
                           str(row.get("url"))[:60], exc)
            return None
        if got:
            logger.info("[watch] %s — 사실 %d건", str(row.get("url"))[:50], len(got))
        return got or None

    w = Watcher(runtime=rt, store=redis, parse=_parse, on_event=_event)
    out = {"rows": 0, "changed": 0, "skipped": 0, "failed": 0}
    for r in rows:
        targets = ([fill_url(r["url"], {"yahoo_id": i}) for i in ids]
                   if "{" in r["url"] else [r["url"]])
        for u in targets:
            if not u:
                out["skipped"] += 1
                continue
            out["rows"] += 1
            try:
                got = await w.check({**r, "url": u})
            except Exception as exc:
                out["failed"] += 1
                logger.info("[watch] %s 실패 — 계속: %s", u[:60], exc)
                continue
            if got.get("changed"):
                out["changed"] += 1
    logger.info("[watch] %s", out)
    return out
