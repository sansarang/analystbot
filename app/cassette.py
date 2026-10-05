"""카세트 — **저장된 응답으로 같은 결과를 다시 낸다**(v4 §9 단계 3 게이트).

§19-g 원문: *"일곱 건이 실제 네트워크 없이 저장된 응답(cassette)으로 재현되고,
그다음 카세트 없이 라이브로 같은 결과가 나와야 단계 통과."*

그래서 같은 코드가 **세 모드**로 돈다:

| `CASSETTE_MODE` | 무엇을 하나 | 어디 쓰나 |
|---|---|---|
| `off` (기본) | 그냥 네트워크 | 운영 · 라이브 재현 |
| `record` | 네트워크로 가고 **응답을 저장** | 카세트 만들 때(사람이 한 번) |
| `replay` | 네트워크에 **가지 않는다** | §19-g 7건 재현 · CI |

🔴 **`replay` 에서 카세트가 없으면 "없다"고 적는다.** 네트워크로 몰래 넘어가지
   않는다 — 그러면 CI 가 조용히 라이브를 때리고, 그 실패가 "코드 결함"으로
   읽힌다. 없는 것은 없다고 하는 것이 이 파일의 값어치다(§19-b-6).

🔴 **열쇠는 `sha256(kind + url + 질의)` 다**(§9 원문: `sha(url+query)`). 날짜는
   경로에 들어간다 — 같은 URL 이 날마다 다른 답을 주므로 날짜가 열쇠의 일부다.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from app.secrets_mask import mask_secrets

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent

OFF = "off"
RECORD = "record"
REPLAY = "replay"
MODES = (OFF, RECORD, REPLAY)

MODE_ENV = "CASSETTE_MODE"
DAY_ENV = "CASSETTE_DAY"
DIR_ENV = "CASSETTE_DIR"
#: 🔴 **측정용 시계.** 검증기가 "지금"으로 삼을 날짜를 **명시적으로** 못 박는다.
#
#  왜 필요한가(실측 2026-09-30, 단계 4): §9 는 *"**경기 전 시점** 웹에서 재현"* 을
#  요구한다. 그런데 오늘 웹에서 09-28 사실을 찾으면 그 기사는 **3일 지난 기사**이고
#  §12-c-1 은 "오늘 또는 어제"만 허용한다 — 즉 **목표 기사가 구조적으로 전부
#  거부된다.** 봇의 결함이 아니라 **시계가 틀린 것**이다.
#
#  🔴 **기본은 비어 있다. 비면 진짜 지금이다.** 운영이 과거 시각으로 도는 일은
#     없어야 하므로, 이 값은 측정 스크립트가 **한 건씩 명시적으로** 넣는다.
#     ⚠️ 이것으로 날짜 검증을 느슨하게 만드는 것이 아니다 — 기준 시각만 옮기고,
#        그 시각에서 오래된 기사는 **여전히 거부된다**(계약이 그것을 잠근다).
AS_OF_ENV = "CASSETTE_AS_OF"

#: 🔴 §9 원문의 경로다. 여기 하나가 원본이고 계약이 이것을 읽는다.
DEFAULT_DIR = "tests/fixtures/cassettes"


class CassetteMiss(RuntimeError):
    """`replay` 인데 저장된 응답이 없다. 🔴 **네트워크로 넘어가지 않는다.**"""


def mode() -> str:
    """지금 어느 모드인가. 🔴 모르는 값은 `off` 다 — 몰래 replay 로 가지 않는다."""
    got = (os.getenv(MODE_ENV) or "").strip().lower()
    if got in MODES:
        return got
    if got:
        logger.warning("[cassette] %s=%r 를 모른다 — off 로 본다", MODE_ENV, got)
    return OFF


def day() -> date:
    """카세트가 어느 날 것인가. 기본은 **오늘(KST)**.

    🔴 `CASSETTE_DAY` 로 고정한다 — §19-g 는 **2026-09-27 실측**이고, 그 날짜를
       오늘로 삼지 않으면 픽스처를 영영 못 찾는다.
    """
    raw = (os.getenv(DAY_ENV) or "").strip()
    if raw:
        try:
            return date.fromisoformat(raw)
        except ValueError:
            logger.warning("[cassette] %s=%r 를 못 읽었다 — 오늘로 본다",
                           DAY_ENV, raw)
    return datetime.now(KST).date()


def reference_now() -> datetime:
    """검증기가 **"지금"으로 삼을 시각.**

    🔴 **재현에는 시계가 필요하다.** §12-c-1 은 *"발행이 오늘 또는 어제"* 를
       요구하므로, 2026-09-27 카세트를 2026-09-30 에 재생하면 그날의 기사가 전부
       *"3일 지난 기사"* 로 거부된다 — 실측 2026-09-30: §19-g 게이트가 그것으로
       터졌고, 그것은 코드 결함이 아니라 **시계를 안 고정한 결함**이다.

    시계를 정하는 순서:

    | 무엇 | 언제 |
    |---|---|
    | `CASSETTE_AS_OF` (명시) | 측정이 *"그날 시점"* 을 못 박을 때 — 단계 4 |
    | 카세트 날짜 23:59 KST | `replay` — 저장된 응답이 그날 것이므로 |
    | **진짜 지금** | 그 밖 전부 (`off`·`record`) — 🔴 **운영이다** |

    ⚠️ 그날의 **끝**(23:59 KST)을 쓴다 — 그 날 아침에 나온 기사를 "미래 발행"으로
       읽지 않게 한다(§12-c-1 은 미래 발행도 거부한다).
    🔴 시계를 옮기는 것은 **검증을 느슨하게 하는 것이 아니다.** 그 시각 기준으로
       오래된 기사는 여전히 거부된다 — 계약이 양쪽을 잠근다.
    """
    raw = (os.getenv(AS_OF_ENV) or "").strip()
    if raw:
        try:
            d = date.fromisoformat(raw)
            return datetime(d.year, d.month, d.day, 23, 59, tzinfo=KST)
        except ValueError:
            logger.warning("[cassette] %s=%r 를 못 읽었다 — 무시한다",
                           AS_OF_ENV, raw)
    if mode() != REPLAY:
        return datetime.now(KST)
    d = day()
    return datetime(d.year, d.month, d.day, 23, 59, tzinfo=KST)


def root() -> Path:
    raw = (os.getenv(DIR_ENV) or "").strip()
    base = Path(raw) if raw else ROOT / DEFAULT_DIR
    return base if base.is_absolute() else ROOT / base


def key(kind: str, url: str, query: str = "") -> str:
    """🔴 `sha(url+query)` — §9 원문 그대로. `kind` 로 열기와 검색을 가른다.

    같은 문자열이 열기 응답과 검색 응답을 동시에 가리키면 한쪽이 다른쪽을
    덮는다(`searxng.local/search` 를 열어 본 적이 있으면 실제로 겹친다).
    """
    raw = f"{kind}\n{url}\n{query}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def path(kind: str, url: str, query: str = "", *, when: date | None = None
         ) -> Path:
    return root() / str(when or day()) / f"{key(kind, url, query)}.json"


def _short_path(p: Path) -> str:
    """로그에 쓸 짧은 경로. 🔴 **저장소 밖이어도 터지지 않는다.**

    ⚠️ 실측 2026-09-30: `relative_to(ROOT)` 가 `CASSETTE_DIR` 을 저장소 밖으로
       둔 순간 `ValueError` 로 터졌다 — 계약이 임시 폴더를 쓰자마자 드러났다.
       로그 한 줄을 예쁘게 만드는 코드가 본 동작을 죽이면 안 된다.
    """
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def query_string(params: dict | None) -> str:
    """질의를 열쇠에 넣을 한 줄로. 🔴 **정렬한다** — dict 순서가 열쇠를 바꾸면
    같은 요청이 두 카세트가 된다.

    ⚠️ **키는 열쇠에서 뺀다.** `?key=AIza…` 가 들어가면 열쇠가 기계마다 달라지고,
       무엇보다 그 값이 **파일 이름의 재료**가 된다. 값을 안 쓰고 이름만 남긴다
       (`secrets_mask` 가 로그를 막는 것과 같은 이유다).
    """
    if not params:
        return ""
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **`engines` 는 열쇠에서 뺀다** (2026-10-02)
    # ══════════════════════════════════════════════════════════════════
    #
    #  카세트는 *"그 질의에 웹이 준 것"* 의 기록이고, `engines` 는 **그것을 어느
    #  엔진에 물을지**라는 라우팅이다. 열쇠에 넣으면 **녹음해 둔 모든 고정물이
    #  한꺼번에 미스**가 된다(실측: §19-g-2 게이트가 그렇게 빨개졌다) — 그 녹음은
    #  2026-09-27 의 웹이라 다시 녹음할 수 없다.
    #  ⚠️ 숨기는 것이 아니다: 엔진을 바꿨을 때 **라이브 결과는 당연히 달라지고**,
    #     그 차이는 라이브 실측으로만 잴 수 있다(그렇게 쟀다). 카세트는 파서·판정
    #     경로를 고정하는 도구이고 엔진 선택을 재는 도구가 아니다.
    params = {k: v for k, v in params.items() if k != "engines"}
    if not params:
        return ""
    # 🔴 `urlencode` 를 쓰지 않는다 — 한글·일본어 질의를 퍼센트로 바꿔서 열쇠
    #    문자열을 사람이 못 읽게 만들고, 가림 표시(`가림`)까지 인코딩해 버린다
    #    (실측 2026-09-30: 계약이 `"가림" in q` 로 그것을 잡았다).
    #    ⚠️ 열쇠는 **해시의 재료**일 뿐 URL 이 아니므로 인코딩할 이유가 없다.
    return "&".join(
        f"{k}=" + (MASKED if _is_secret(k) else str(params[k]))
        for k in sorted(params))


#: 🔴 가려진 자리에 남는 표시. **값은 빼고 이름은 남긴다** — 무엇이 있었는지가
#  남아야 진단이 된다(`secrets_mask.mask_field` 와 같은 규약).
MASKED = "…가림"

_SECRET_PARAMS = ("key", "api_key", "apikey", "token", "access_token", "cx")


def _is_secret(name: str) -> bool:
    return str(name).strip().lower() in _SECRET_PARAMS


# ══════════════════════════════════════════════════════════════════
# 읽기·쓰기
# ══════════════════════════════════════════════════════════════════


def load(kind: str, url: str, query: str = "", *, when: date | None = None
         ) -> dict:
    """저장된 응답. 🔴 없으면 `CassetteMiss` — **네트워크로 가지 않는다.**"""
    p = path(kind, url, query, when=when)
    if not p.is_file():
        raise CassetteMiss(
            f"카세트 없음 — {_short_path(p)} ({kind} {url} {query[:80]})")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise CassetteMiss(f"카세트가 JSON 이 아니다 — {p.name}: {exc}") from exc


def save(kind: str, url: str, query: str, payload: dict, *,
         when: date | None = None) -> Path:
    """응답을 저장한다. 🔴 무엇을 저장했는지 **경로를 로그에 남긴다.**

    🔴 **URL 의 비밀도 가린다**(리뷰 2026-09-30). 가림은 `query_string` 의
       `params` 에만 걸려 있었고, `?key=…` 를 URL 에 직접 실은 호출부가 생기면
       그 값이 **저장소에 커밋되는 파일 본문**으로 들어간다.
       ⚠️ 지금 그런 호출부는 없다(`app/search.py` 는 키를 `params` 로 넘긴다) —
          그래서 이것은 **다음 호출부**를 막는 장치다. 계약이 잠근다.
    """
    p = path(kind, url, query, when=when)
    p.parent.mkdir(parents=True, exist_ok=True)
    body = {"kind": kind, "url": mask_secrets(url), "query": query,
            "recorded_at": datetime.now(timezone.utc).isoformat(), **payload}
    p.write_text(json.dumps(body, ensure_ascii=False, indent=1),
                 encoding="utf-8")
    logger.info("[cassette] 저장 %s ← %s %s", _short_path(p), kind,
                mask_secrets(url))
    return p


def index(when: date | None = None) -> list[dict]:
    """그 날 카세트 목록. 🔴 **무엇이 담겼는지 이름으로** 보여 준다(조용한 0 금지)."""
    d = root() / str(when or day())
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("*.json")):
        try:
            got = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            out.append({"file": p.name, "error": "JSON 아님"})
            continue
        out.append({"file": p.name, "kind": got.get("kind"),
                    "url": got.get("url"), "query": got.get("query"),
                    "recorded_at": got.get("recorded_at")})
    return out
