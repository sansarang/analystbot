"""🔴🔴 **이름표가 스스로 자란다** — ③(사용자 설계 2026-10-04).

> ③ 자가 성장이 핵심이라는 판단에 동의한다. **조건 셋**:
>   ① 팀 ID 밑에만 적는다(이름끼리 연결 금지)
>   ② **경기 페이지가 양 팀을 함께 확인한 경우만** 적는다
>   ③ 출처(경기 ID)를 남겨서 **되짚어 지울 수 있게** 한다

══════════════════════════════════════════════════════════════════
🔴 어떻게 배우나 — **짝이 하나뿐일 때만**
══════════════════════════════════════════════════════════════════

사용자가 `맨시티 vs 아스날` 을 물었다 하자. `아스날` 은 이름표가 알고 `맨시티` 는
모른다. 봇이 경기 페이지를 열었고 거기에 두 팀이 있다:

```
페이지:  ['Arsenal FC', 'Manchester City FC']   ← 둘 다 이름표가 안다
물은 것: 아스날(안다) · 맨시티(모른다)
→ 아스날 = Arsenal FC 이므로 **맨시티는 나머지 하나**다
→ `맨시티` 를 `Manchester City FC` 의 **번호 밑에** 적는다
```

🔴 **짝이 하나뿐일 때만** 적는다. 둘 다 모르면 어느 쪽인지 알 수 없고, 거기서
   고르면 그것이 추측이다(`app/ids.py`: *"거짓 매칭보다 미상이 낫다"*).
⚠️ **새 팀을 만들지 않는다.** 페이지의 이름이 이름표에 없으면 배울 것이 없다 —
   그 팀 자체를 모르는 것이고, 그때 만들면 **반쪽짜리 팀**이 생긴다.

🔴 **오염은 조용히 쌓인다.** 그래서 ① 출처 경기 id 를 줄마다 남기고 ② 적은 것을
   로그에 원문으로 찍고 ③ 되짚어 지울 수 있게 파일 하나에 모은다.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def why_not_learned(key_a: object, key_b: object) -> str:
    """🔴 **왜 안 배웠나** — 두 경우를 가른다(⑯ · 실측 2026-10-05).

    ⚠️ 종전엔 둘 다 *"짝이 하나로 안 정해진다"* 로 찍혔다. 🔴 그런데
       **둘 다 아는 것**은 정상이고(배울 것이 없다) **둘 다 모르는 것**은
       고칠 것이 있다(열쇠를 못 가렸다) — 고칠 곳이 다르면 글이 달라야 한다(#3).
    """
    a, b = str(key_a or "").strip(), str(key_b or "").strip()
    if a and b:
        return "두 이름을 **둘 다 이미 안다** — 배울 것이 없다(정상)"
    if not a and not b:
        return "🔴 두 이름의 **열쇠를 둘 다 못 가렸다** — 짝을 못 정한다"
    return "⚠️ 한쪽 열쇠가 이 경기의 두 팀과 안 맞는다 — 짝을 못 정한다"

ROOT = Path(__file__).resolve().parents[1]
#: 🔴 배운 별칭이 사는 곳. ⚠️ `var/` 는 ignore 다 — **되짚어 지울 수 있게** 한 파일에.
STORE = ROOT / "var" / "learned_aliases.json"

#: 🔴 출처 꼬리표. 이름표의 **출처 등급에서 맨 아래**다(사람이 적은 것보다 낮다).
SOURCE = "학습"


def load() -> dict[str, dict]:
    """배운 별칭 전부. `{정규화 이름: {name, key, from_match, lang}}`."""
    try:
        got = json.loads(STORE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): dict(v) for k, v in got.items() if isinstance(v, dict)}


def _save(box: dict[str, dict]) -> None:
    try:
        STORE.parent.mkdir(parents=True, exist_ok=True)
        STORE.write_text(json.dumps(box, ensure_ascii=False, indent=0),
                         encoding="utf-8")
    except OSError as exc:                              # pragma: no cover
        logger.info("[learn] 못 적었다: %s", exc)


def forget(name: str) -> bool:
    """🔴 **되짚어 지운다.** 틀린 것이 들어오면 이 한 줄로 뺀다."""
    from app import teamref
    box = load()
    k = teamref.norm(name)
    if k not in box:
        return False
    got = box.pop(k)
    _save(box)
    logger.info("[learn] 지웠다 — %r (경기 %s)", got.get("name"),
                got.get("from_match"))
    return True


def learn(*, asked: tuple[str, str], page_names: list[str],
          match_key: str) -> list[dict]:
    """🔴🔴 **그 경기에서 배운 별칭들.** 돌려주는 것은 적은 줄들.

    `asked` 는 사용자가 쓴 두 이름(팀, 상대), `page_names` 는 **경기 페이지가
    확인해 준** 두 팀 이름, `match_key` 는 그 경기(`games.ext_id`).

    ⚠️ 조건을 하나라도 못 채우면 **아무것도 안 적는다** — 그 사실을 로그에 남긴다.
    """
    from app import teamref
    if len(page_names) != 2 or not match_key:
        return []
    kA, kB = (teamref.key_of(page_names[0])[0],
              teamref.key_of(page_names[1])[0])
    if not (kA and kB):
        # 🔴 **양 팀을 함께 확인하지 못했다** — 조건 ②가 안 찼다
        logger.info("[learn] 안 배운다 — 경기 페이지의 두 팀 중 모르는 쪽이 있다 "
                    "(%s)", page_names)
        return []
    if kA == kB:
        logger.info("[learn] 안 배운다 — 두 이름이 같은 팀으로 풀린다 (%s)",
                    page_names)
        return []
    t, o = (str(asked[0] or "").strip(), str(asked[1] or "").strip())
    kT, kO = teamref.key_of(t)[0], teamref.key_of(o)[0]
    out: list[dict] = []
    pairs = []
    # 🔴 **아는 쪽이 하나일 때만** 짝이 정해진다
    if kT and not kO and o and kT in (kA, kB):
        pairs.append((o, kB if kT == kA else kA))
    if kO and not kT and t and kO in (kA, kB):
        pairs.append((t, kB if kO == kA else kA))
    if not pairs:
        # 🔴 **두 경우를 가른다**(⑯ · 실측 2026-10-05) — 종전엔 한 글이었다.
        #    ⚠️ *"둘 다 이미 안다"* 는 **정상**이고(배울 것이 없다),
        #       *"둘 다 모른다"* 는 **고칠 것이 있다**(열쇠를 못 가렸다).
        logger.info("[learn] 안 배운다 — %s (물은 것 %r/%r · 아는 열쇠 %r/%r)",
                    why_not_learned(kT, kO), t, o, kT, kO)
        return []
    box = load()
    for name, key in pairs:
        k = teamref.norm(name)
        if not k or k in box:
            continue
        # 🔴 **번호 밑에만** 적는다 — 이름끼리 잇지 않는다(조건 ①)
        row = {"name": name, "key": key, "from_match": match_key,
               "lang": teamref.lang_of(name)}
        box[k] = row
        out.append(row)
        # 🔴 **원문으로 찍는다** — 자가 성장은 오염이 조용히 쌓이는 자리다
        logger.info("[learn] 🔴 배웠다 — %r → %s (%s · 경기 %s)",
                    name, key, teamref.label_of(key, "en"), match_key)
    if out:
        _save(box)
    return out
