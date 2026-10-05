"""FastAPI — `/health` 만. 배포 커밋 해시를 대조하는 자리다."""
from __future__ import annotations

from fastapi import FastAPI

from app import cassette, timefmt
from app.config import get_settings
from app.db import get_pool
from app.secrets_mask import mask_field
from app.version import boot_info, staleness_line, uptime_text

app = FastAPI(title="AnalystBot v3")


@app.get("/health")
async def health() -> dict:
    """🔴 로컬과 서버가 같은 코드인지 여기서 대조한다(실사고 2026-08-25·27)."""
    s = get_settings()
    info = boot_info()
    out = {"commit": info.short, "subject": info.subject,
           "uptime": uptime_text(),
           "stale": staleness_line(), "send_enabled": s.send_enabled,
           "llm": {"base_url": s.ollama_base_url, "model": s.ollama_model},
           # 🔴 **설정을 드러내되 자격증명은 가린다**(실사고 2026-09-09: 설정
           #    객체 repr 하나에 키 11종이 평문으로 나갔다). `mask_field` 가
           #    필드 **이름**으로 가르고, 이름은 지우지 않는다 — 무엇이 있었는지가
           #    남아야 진단이 된다.
           "config": {k: mask_field(k, getattr(s, k))
                      for k in ("database_url", "redis_url",
                                "telegram_bot_token", "football_data_key")},
           # 🔴 **운영이 카세트로 돌고 있나.** `off` 가 아니면 이 프로세스는
           #    저장된 응답을 쓰고 있다 — 그것을 밖에서 못 보면 "성공처럼 보이는
           #    실패"가 된다(`app/cassette.py` 머리글). 담긴 건수까지 낸다.
           "cassette": _cassette_state(),
           "db": "unknown"}
    try:
        pool = await get_pool(s.database_url)
        out["db"] = "ok" if await pool.fetchval("SELECT 1") == 1 else "bad"
        # 🔴 **KST 날짜**로 센다 — 조각은 `timefmt` 하나다(사본 금지).
        #    ⚠️ 종전 `starts_kst::date` 는 세션 시간대(UTC)로 돌아, 유럽 저녁
        #       경기를 **어제 칸**에 넣었다(실측 2026-10-05: 52행 중 16행).
        out["slate_today"] = int(await pool.fetchval(
            f"SELECT count(*) FROM games "
            f"WHERE {timefmt.sql_kst_day()} = {timefmt.SQL_TODAY_KST}")
            or 0)
        # 🔴 못 잰 칸을 드러낸다 — 조용한 0 을 밖에서 보이게 한다(§5)
        out["unknowns_today"] = int(await pool.fetchval(
            "SELECT COALESCE(sum(cardinality(unknowns)), 0) FROM runs "
            f"WHERE slate_date = {timefmt.SQL_TODAY_KST}") or 0)
    except Exception as exc:                      # noqa: BLE001
        out["db"] = f"error: {type(exc).__name__}"
    return out


def _cassette_state() -> dict:
    """🔴 카세트 모드와 **담긴 건수**. `off` 면 그 사실만 낸다.

    ⚠️ 목록 읽기가 실패해도 `/health` 를 죽이지 않는다 — 진단이 본 동작을 막으면
       다음 사람이 이 기록을 안 보게 된다.
    """
    mode = cassette.mode()
    out = {"mode": mode}
    if mode == cassette.OFF:
        return out
    out["day"] = str(cassette.day())
    try:
        rows = cassette.index()
    except OSError as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out
    out["count"] = len(rows)
    # 🔴 **무엇이 담겼는지 종류별로** — 조용한 0 금지
    kinds: dict[str, int] = {}
    for r in rows:
        kinds[str(r.get("kind"))] = kinds.get(str(r.get("kind")), 0) + 1
    out["kinds"] = kinds
    return out
