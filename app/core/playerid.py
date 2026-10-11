"""🔴🔴 **선수 신원표** — 사용자 지시 2026-10-11(라인업 신원 통일) ①②.

> 선수 id 하나에 별칭 여럿(영문·한글·일본어/현지어·등번호·**이전 번호**).
> 출처: fotmob 명부 + 최근 경기 라인업 + `names_ko.yaml`.
> 모든 라인업 출처(fotmob·캡처·리그 공식·기사)는 이 표로 id 를 푼다.
> **비교·집계는 id 로만 한다 — 이름 문자열 비교 금지.**

⚠️ 왜 이 파일이 생겼나 — 실사고 2026-10-11(가와사키–나고야 캡처): 같은 선수가
   **선발이면서 결장·교체·무기 꺼짐**으로 동시에 들어갔다.

       확정 XI: 브로더센(49) · 와키자카(14)        ← 캡처가 한글로 줬다
       결장/교체: Svend Brodersen · Yasuto Wakizaka  ← fotmob 은 로마자다
       → 글자가 다르니 **다른 사람**으로 셌다. 깃발·r 가중·무기 꺼짐이 전부 틀렸다.

🔴 그래서 **이름을 비교하지 않는다.** 표를 한 번 만들고(그 안에서만 글자를 본다)
   그 뒤의 모든 비교는 **id** 로 한다.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

#: 🔴 ② 사다리 2칸 — **로마자 유사도** 문턱. ⚠️ 높게 둔다(틀린 짝이 더 나쁘다).
SIM_MIN = 0.86
#: 🔴 ② 사다리 3칸 — 번호가 이만큼 가까우면 **근접 후보**로 본다(0 이면 같은 번호)
NEAR_NUM = 0
#: 🔴 한글·가나·한자 글자
_CJK = re.compile(r"[가-힣ぁ-んァ-ヴー一-龥]")


@dataclass
class Who:
    """🔴 선수 한 명 — **id 하나에 별칭 여럿**. ⚠️ 못 받은 칸은 비어 있다."""

    id: str
    names: set[str] = field(default_factory=set)
    #: 🔴 등번호 — **이전 번호도 쌓는다**(지시서의 그 말)
    numbers: set[int] = field(default_factory=set)
    pos: str = ""
    sources: set[str] = field(default_factory=set)

    def keys(self) -> set[str]:
        """🔴 맞출 때 쓰는 **정규화한 별칭**들."""
        return {norm(x) for x in self.names if norm(x)}

    def parts(self) -> set[str]:
        """🔴 ② 유사도용 — 별칭의 **토막**(성·이름)도 넣는다.

        ⚠️ 실측 2026-10-11: 캡처가 `Wakisaka`(성만, 표기 흔들림)로 오는데 표의
           열쇠는 `yasutowakizaka`(성+이름)라 유사도가 0.6 대로 떨어졌다.
        🔴 토막은 **두 글자 이상**만 쓴다(한 글자는 아무 이름과도 닮는다).
        """
        out: set[str] = set()
        for nm in self.names:
            for tok in re.split(r"[\s·.-]+", str(nm or "")):
                key = norm(tok)
                if len(key) >= 2:
                    out.add(key)
        return out


def norm(said: object) -> str:
    """🔴 대조용 꼴 — 분음 부호·대소문자·공백·점을 지운다. **음차하지 않는다.**"""
    low = unicodedata.normalize("NFKD", str(said or ""))
    low = "".join(c for c in low if not unicodedata.combining(c))
    low = unicodedata.normalize("NFC", low).lower()
    return re.sub(r"[^0-9a-z가-힣ぁ-んァ-ヴー一-龥]+", "", low)


def _num(said: object) -> int | None:
    try:
        got = int(str(said).strip())
    except (TypeError, ValueError):
        return None
    return got if 0 < got < 100 else None


def build(*, rows: list[dict], ko: dict | None = None) -> dict[str, Who]:
    """🔴🔴 ① — 출처 줄들 → **`{id: Who}`**.

    한 줄 꼴: `{"name", "number", "pos", "player_id", "source"}` — 있는 칸만 쓴다.
    🔴 **id 는 `player_id` 가 있으면 그것**이다(fotmob 선수 번호 · 안정된 열쇠).
       없으면 `p:{정규화 이름}` 으로 민다. ⚠️ 두 줄이 같은 `player_id` 면 **한 사람**
       이고, 같은 정규화 이름이어도 한 사람이다(그 둘로만 합친다 — 번호로는 합치지
       않는다: 번호는 시즌마다 돌아다닌다).
    `ko` 는 `rules.names_ko()["players"]` 꼴(`{영문: [한글…]}`).
    """
    out: dict[str, Who] = {}
    by_name: dict[str, str] = {}
    for raw in (rows or []):
        one = dict(raw)
        nm = str(one.get("name") or "").strip()
        pid = str(one.get("player_id") or "").strip()
        key = norm(nm)
        if not pid and not key:
            continue
        ident = f"fm:{pid}" if pid else by_name.get(key) or f"p:{key}"
        # 🔴 같은 이름이 먼저 `p:` 로 들어왔고 이제 `player_id` 가 왔으면 **합친다**
        if pid and key and by_name.get(key) and by_name[key] != ident:
            old = out.pop(by_name[key], None)
            if old is not None:
                got = out.setdefault(ident, Who(id=ident))
                got.names |= old.names
                got.numbers |= old.numbers
                got.sources |= old.sources
                got.pos = got.pos or old.pos
            for k, v in list(by_name.items()):
                if v == old.id if old else False:
                    by_name[k] = ident
        got = out.setdefault(ident, Who(id=ident))
        if nm:
            got.names.add(nm)
            by_name[key] = ident
        num = _num(one.get("number"))
        if num is not None:
            got.numbers.add(num)
        said_pos = str(one.get("pos") or "").strip()
        if said_pos and not got.pos:
            got.pos = said_pos
        said_src = str(one.get("source") or "").strip()
        if said_src:
            got.sources.add(said_src)
    # 🔴 한글 별칭을 얹는다 — 원본은 `config/names_ko.yaml` 하나다(사본 금지)
    for en, rows_ko in dict(ko or {}).items():
        want = norm(en)
        for who in out.values():
            if want in who.keys():
                who.names |= {str(x) for x in (rows_ko or []) if str(x).strip()}
                break
    return out


def resolve(box: dict, *, said: str = "", number: object = None,
            pos: str = "") -> tuple[str, str]:
    """🔴🔴 ② **캡처 풀기 사다리** — `(id, 사유)`. 못 풀면 `("", 사유)`.

    > 번호 → 실패 시 이름 별칭(한글·현지어·로마자 유사도) → 실패 시 그 팀 최근
    > 경기 출전자 중 번호·이름 근접 후보.

    🔴 **못 풀면 짓지 않는다**(#4) — 빈 id 와 사유를 돌려주고, 부르는 쪽이 운영자
       알림과 카드 🔴 를 만든다.
    """
    want = norm(said)
    num = _num(number)
    # ── 1칸 — 번호(언어가 없다)
    if num is not None:
        hit = [w for w in box.values() if num in w.numbers]
        if len(hit) == 1:
            return hit[0].id, f"번호 {num} 로 맞췄다"
        if len(hit) > 1 and want:
            same = [w for w in hit if want in w.keys()]
            if len(same) == 1:
                return same[0].id, f"번호 {num} + 이름으로 맞췄다"
    # ── 2칸 — 이름 별칭(한글·현지어 글자 그대로)
    if want:
        hit = [w for w in box.values() if want in w.keys()]
        if len(hit) == 1:
            return hit[0].id, "이름 별칭으로 맞췄다"
        # ── 2칸-b — 로마자 유사도(표기 흔들림). ⚠️ CJK 는 유사도를 쓰지 않는다
        if not _CJK.search(said or ""):
            rows = []
            for who in box.values():
                for key in (who.keys() | who.parts()):
                    if _CJK.search(key):
                        continue
                    rows.append((SequenceMatcher(None, want, key).ratio(),
                                 who.id, key))
            rows.sort(reverse=True)
            if rows and rows[0][0] >= SIM_MIN:
                top = [r for r in rows if r[0] >= SIM_MIN]
                if len({r[1] for r in top}) == 1:
                    return rows[0][1], (f"로마자 유사도 {rows[0][0]:.2f}"
                                        f"(≥{SIM_MIN}) — `{rows[0][2]}`")
    # ── 3칸 — 번호 근접 후보(그 팀 최근 출전자 중)
    if num is not None:
        near = [w for w in box.values()
                if any(abs(n - num) <= NEAR_NUM for n in w.numbers)]
        if len(near) == 1:
            return near[0].id, f"번호 근접({num})으로 맞췄다"
    return "", (f"🔴 **못 풀었다** — 글자 `{said or '없다'}`"
                f" · 번호 `{number if number is not None else '없다'}`"
                f"(표 {len(box)}명)")


def said_of(box: dict, ident: str) -> str:
    """🔴 그 id 를 **사람이 읽는 이름**으로(카드·보고가 적는다)."""
    who = dict(box or {}).get(str(ident))
    if who is None:
        return str(ident)
    rows = sorted(who.names, key=lambda x: (0 if not _CJK.search(x) else 1, x))
    said = rows[0] if rows else str(ident)
    num = min(who.numbers) if who.numbers else None
    return said + (f"({num})" if num is not None else "")
