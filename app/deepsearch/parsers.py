"""[DS-2P] 변화 감지의 **파서들.** 바뀐 페이지에서 사실을 뽑는다.

🔴 **키워드로 짜지 않는다 — 측정이 그걸 막았다(2026-09-21).**
   구단 공지 페이지의 `中止` 는 **메뉴 문구**였다:
     라쿠텐  `中止` 9회 → 전부 「地方主催試合中止時の払い戻し」(환불 안내)
     마린스  `中止` 0회 → 오늘 중지가 그 페이지에 아예 없다
   키워드 매처를 만들었으면 매 주기 오탐이 났을 것이다.
   진짜는 **npb.jp 스코어보드 띠**에 **구조로** 들어 있다.

🔴 **왜 필요한가 — 지연이 숫자로 나왔다(2026-09-21):**
     마린스 vs 세이부     시작 18:00 · 공지 08:30 · DB 반영 14:00  → 5h30m 늦음
     라쿠텐 vs 소프트뱅크 시작 13:00 · 중지 12:40 · DB 반영 14:00  → 시작을 지나서
   오늘 NPB 5행이 **전부 `updated_at` 14:00** — 배치라 사건이 아니라 시각에
   맞춰 돈다. 사실은 있었고, 없던 것은 **시각**이다.

⚠️ 팀 이름표를 만들지 않는다 — `alt` 속성에서 읽는다(사본 금지).
⚠️ 모양이 예상과 다르면 **빈 목록**이다. 억지로 짜내지 않는다.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)

#: `/scores/2026/0921/e-h-23/` → 날짜
_HREF_DATE = re.compile(r"/scores/(\d{4})/(\d{2})(\d{2})/")
#: 상태 문구 → 우리 어휘. 🔴 `games.status` 와 **같은 말**을 쓴다(사본 금지의 뜻).
_STATE = (("中止", "cancelled"), ("延期", "postponed"), ("試合終了", "final"),
          ("ノーゲーム", "cancelled"), ("サスペンデッド", "suspended"))


def _int_or_none(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def parse_npb_scoreboard(html: str, *, as_of: datetime, url: str = "") -> list:
    """npb.jp 머리의 스코어보드 띠 → 경기별 사실.

    돌려주는 칸: `event_date`·`as_of`(둘 다 **필수**) · `home`·`away` ·
    `venue` · `status` · `home_score`·`away_score` · `source_url`.

    🔴 **`logo_left` 가 홈이다.** 추측이 아니라 우리 DB 와 **4/4 대조**해
       확인했다(2026-09-21):
         楽天(left)/ソフトバンク(right) ↔ DB: SoftBank @ Rakuten
         ロッテ(left)/西武(right)       ↔ DB: Seibu @ Lotte
         日本ハム(left)/オリックス(right) ↔ DB: Orix @ Nippon-Ham
         阪神(left)/DeNA(right)         ↔ DB: DeNA @ Hanshin
    ⚠️ 중지 경기의 점수는 `*-*` 다 — **점수로 읽지 않는다**(None).
    """
    if not html or "score_box" not in html:
        return []
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
    except Exception as exc:
        logger.warning("[parsers] npb 스코어보드 파싱 실패: %s", exc)
        return []

    out: list[dict] = []
    for box in soup.select("div.score_box"):
        a = box.find("a", href=True)
        if a is None:
            continue                       # 날짜 칸(`score_box date`) 등
        m = _HREF_DATE.search(a["href"])
        if not m:
            continue
        left = box.select_one("img.logo_left")
        right = box.select_one("img.logo_right")
        if left is None or right is None:
            continue
        home = (left.get("alt") or "").strip()
        away = (right.get("alt") or "").strip()
        if not home or not away or home == away:
            continue

        state_el = box.select_one("div.state")
        state = state_el.get_text(" ", strip=True) if state_el else ""
        venue = ""
        vm = re.search(r"[（(]([^（）()]+)[）)]", state)
        if vm:
            venue = vm.group(1).strip()
        status = "scheduled"
        for token, val in _STATE:
            if token in state:
                status = val
                break
        else:
            if re.search(r"\d+回", state):
                status = "live"

        sc = box.select_one("div.score")
        hs = as_ = None
        if sc is not None:
            sm = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", sc.get_text(strip=True))
            if sm:
                hs, as_ = _int_or_none(sm.group(1)), _int_or_none(sm.group(2))

        out.append({
            "kind": "game_status",
            "event_date": f"{m.group(1)}-{m.group(2)}-{m.group(3)}",
            "as_of": as_of,
            "home": home, "away": away, "venue": venue, "status": status,
            "home_score": hs, "away_score": as_,
            "source_url": url or "", "game_path": a["href"],
        })
    return out
