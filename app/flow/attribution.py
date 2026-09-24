"""[MOV-C 4·5단계] **배당이 왜 움직였는지 시각으로 맞춘다.**

사용자 2026-09-23: "왜 이렇게 배당이 이동되었는지…초기 가설과 접목" ·
**"이유 미상은 없다"**

🔴 **"이유 미상"을 만들지 않는다.** 모든 이동에 분류가 붙는다:
```
정보(news)   창 안에 관측된 변화·기사가 있다        → 그 근거를 적는다
자금(money)  찾아봤는데 없다                        → 자금 이동이다. 회피가 아닌 답
```
⚠️ **"자금"이라 말하려면 실제로 찾아봤어야 한다.** MOV-T7 커밋이 그 자백을
   남겼다 — `"{pp}%p 이동 — 뉴스 근거 없음(**딥서치 미실행** 또는 무소득)"`.
   찾지 않고 자금이라 부르면 `none` 에 이름만 바꾼 것이다. 그래서 이 모듈은
   **관측이 실제로 있었는지**(`observed`)를 함께 낸다 — 관측이 없으면
   `money` 라고 말하지 않고 `unobserved` 다.

🔴 **중요도·방향 판단을 하지 않는다.** `diff.go` 와 같은 규약이다
   ("크롤러가 임의 가중치를 만들면 측정되지 않은 튜닝이 된다"). 여기서는
   "무엇이 언제 있었다"를 이동에 붙이기만 하고, 그것이 유리한지는 ⑦이 정한다.

⚠️ **순수 함수다** — DB·HTTP·LLM 0건. 계약이 잠근다.
"""
from __future__ import annotations

import datetime as dt
import logging

from app.flow import rules as R

logger = logging.getLogger(__name__)

#: 원인이 붙지 않은 이동의 분류.
MONEY = "money"           # 관측은 있었는데 창 안에 아무것도 없었다
UNOBSERVED = "unobserved"  # 관측 자체가 없었다 — 자금이라 부를 수 없다
NEWS = "news"


def _to_dt(v):
    """`at` · `captured_at` → aware datetime. 못 읽으면 None(지어내지 않는다)."""
    if isinstance(v, dt.datetime):
        return v if v.tzinfo else v.replace(tzinfo=dt.UTC)
    if not isinstance(v, str) or not v.strip():
        return None
    try:
        t = dt.datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.UTC)


def _is_noise(c: dict) -> bool:
    """볼 가치가 없는 변화인가.

    🔴 목록의 원본은 `config/rules.yaml` 이다 — 이름을 여기 적지 않는다.
    ⚠️ 실측 2026-09-23: 크롤러 변화 154건 중 **83건이 `status`**(9회초→9회말)
       였다. 회 진행은 이동의 원인이 아니라 경기 중계다.
    ⚠️ `확정 → 미상` 같은 역행은 파싱이 깨진 것이지 사건이 아니다.
    """
    field = str(c.get("field") or "")
    if field in {str(x) for x in (R.get("move.ignore_fields") or [])}:
        return True
    pair = f"{c.get('from') or ''}→{c.get('to') or ''}"
    return pair in {str(x) for x in (R.get("move.ignore_transitions") or [])}


def _when(c: dict):
    """그 변화가 **실제로 일어난** 시각.

    🔴 기사는 크롤 시각(`at`)이 아니라 **발행시각**이 맞다. `news.go` 가
       값에 `<RFC3339>|<제목>` 으로 실어 보낸다.
    """
    to = str(c.get("to") or "")
    if "|" in to:
        t = _to_dt(to.split("|", 1)[0])
        if t is not None:
            return t
    return _to_dt(c.get("at"))


def _local_names() -> dict:
    """현지 표기 → 영문 팀명. 🔴 **원본은 수집기의 대조표 둘이다**(사본 금지).

    `naver_kbo.TEAM_TO_ODDS`(한글 10팀) · `yahoo_npb.TEAM_TO_ODDS`(일어 12팀).
    Go `source.go` 도 같은 표를 쓴다(CRW-6 이 전수 대조해 차이 0 확인).
    ⚠️ 읽기만 한다 — I/O 가 아니므로 순수 함수 규약을 깨지 않는다.
    """
    out: dict = {}
    for mod, name in (("app.collectors.naver_kbo", "TEAM_TO_ODDS"),
                      ("app.collectors.yahoo_npb", "TEAM_TO_ODDS")):
        try:
            m = __import__(mod, fromlist=[name])
            out.update(getattr(m, name, {}) or {})
        except Exception as exc:          # pragma: no cover - 표가 없으면 못 가린다
            logger.debug("[attribution] 대조표 %s 없음: %s", mod, exc)
    return out


def _is_ours(c: dict, teams) -> bool:
    """이 변화가 **이 경기의 것**인가.

    🔴 [2026-09-23] 종전에는 안 가렸다. 그래서 같은 시각에 공시된 한 경기의
       라인업이 **그 리그 전 경기**의 이동 원인으로 붙었다 — 실측: KBO 3경기가
       전부 같은 원인(KIA 라인업)을 받았다. 거짓 귀인이다.

    ⚠️ 라인업·선발 변화는 `game`("원정@홈#id")에 **영문 팀명**이 있어 그대로
       대조한다. 뉴스는 제목이 현지 표기라 대조표로 옮겨 비교한다.
    ⚠️ **어느 팀도 못 찾으면 이 경기의 원인이 아니다.** 리그 맥락 기사를
       특정 경기의 이유로 쓰면 "이유 미상은 없다"가 거짓말이 된다.
    """
    want = {str(t) for t in (teams or []) if t}
    if not want:
        return True                        # 팀을 모르면 가리지 않는다(종전 동작)
    # 🔴 [KEY-1 2026-09-24] **`game` 이 있다고 경기 이름인 것은 아니다.**
    #    Go 는 뉴스를 `NewsKey(리그)` = `"news_mlb"` 라는 **가짜 경기 키**에
    #    담는다. 그걸 경기 이름으로 읽으면 어느 팀도 안 맞아 `False` 로
    #    끝나고 **제목을 보지도 않는다** — 실측: 후보 28건 전부 걸렀다.
    #    진짜 경기 키는 `"원정@홈#id"` 라 `@` 가 있다.
    g = str(c.get("game") or "")
    if "@" in g:
        return any(t in g for t in want)
    to = str(c.get("to") or "")
    title = to.split("|", 1)[1] if "|" in to else to
    if not title:
        return False
    # 🔴 [KEY-1 2026-09-24] **영문 리그는 대조표가 없다.** `_local_names` 는
    #    KBO(한글)·NPB(일어) 22개뿐이다(실측). MLB 제목은 팀명이 영문 그대로
    #    나오므로 **우리가 가진 팀 이름으로 직접 맞춘다**:
    #      "Rangers Set Probable Pitchers … with Athletics"
    #      "Astros vs Braves series preview …"
    #    ⚠️ 전체 이름("Los Angeles Angels")은 제목에 잘 안 나오고 별명
    #       ("Angels")으로 줄여 쓴다 — 마지막 낱말이 그것이다.
    for full in want:
        if _names_subject(title, full):
            return True
        nick = str(full).split()[-1] if str(full).split() else ""
        # ⚠️ 짧은 별명은 우연히 걸린다("A's"·"Sox"). 4자 미만은 쓰지 않는다.
        if len(nick) >= 4 and _names_subject(title, nick):
            return True
    for local, eng in _local_names().items():
        if local and str(eng) in want and _names_subject(title, str(local)):
            return True
    return False


def _label(c: dict) -> str:
    """사람이 읽을 한 줄. 값이 길면 자른다."""
    field = str(c.get("field") or "?")
    to = str(c.get("to") or "")
    if "|" in to:
        to = to.split("|", 1)[1]
    frm = str(c.get("from") or "")
    if frm and not to:
        return f"{field} 사라짐: {frm[:60]}"
    if frm:
        return f"{field}: {frm[:30]} → {to[:40]}"
    return f"{field}: {to[:60]}"


def _title_of(c: dict) -> str:
    """변화 한 건의 **기사 제목**. 기사가 아니면 빈 문자열."""
    to = str((c or {}).get("to") or "")
    return to.split("|", 1)[1].strip() if "|" in to else ""


#: 팀명 바로 뒤에 오면 **상대 표기**라는 뜻 — 그 팀의 기사가 아니다.
#  ⚠️ 실측 2026-09-23 라이브 RSS: "'SSG 대체 외인' 마드리스, 16일 **LG전**이
#     마지막! 에레디아 21일 1군 복귀" 가 LG 호재로 붙었다. SSG 기사다.
#  ⚠️ 낱말이 아니라 **문법**이라 사전(`evidence_lexicon.yaml`)이 아니라
#     여기 둔다 — 그 파일은 "무엇이 악재인가"의 목록이고 이건 조사다.
_OPPONENT_SUFFIX = ("전", "戦", "戦は")


def _names_subject(title: str, local: str) -> bool:
    """제목에서 그 팀이 **주체**인가. `LG전`(상대 표기)이면 아니다."""
    i, n = 0, len(local)
    while True:
        i = title.find(local, i)
        if i < 0:
            return False
        tail = title[i + n:]
        if not any(tail.startswith(sfx) for sfx in _OPPONENT_SUFFIX):
            return True
        i += n


def tone_of(title):
    """제목 → `{"dir": -1|+1, "word"}`. 못 정하면 **None**.

    🔴 [NWS-S 2026-09-24] `direction_of` 안에 묻혀 있던 **낱말 판정**을 꺼냈다.
       팀을 이미 아는 자리(`news_dir_sided`)에서도 같은 규약을 써야 하는데,
       꺼내지 않으면 사본이 생긴다.
    🔴 낱말의 원본은 `config/evidence_lexicon.yaml` 의 `direction:` 하나다.
    ⚠️ 악재·호재가 **둘 다** 걸리면 None 이다 — "부상 딛고 복귀"를 악재로
       읽으면 정반대가 된다.
    """
    from app.engine.scout_config import LEXICON_DIR

    t = str(title or "").strip()
    if not t:
        return None
    low = t.lower()

    def _hit(kind):
        for _lang, words in (LEXICON_DIR.get(kind) or {}).items():
            for w in words:
                if w and (w in t or str(w).lower() in low):
                    return str(w)
        return None

    bad, good = _hit("bad"), _hit("good")
    if (bad and good) or not (bad or good):
        return None
    return {"dir": -1 if bad else +1, "word": bad or good}


def news_dir_sided(table, *, max_age_h=None) -> dict | None:
    """[NWS-S] **쪽이 이미 정해진** 기사표 → `{"home","away","basis"}`.

    `table` 은 `news_rss.by_side` 가 내는 `{"home": [기사…], "away": [기사…]}` 다.

    🔴 **왜 따로 필요한가.** `news_dir` 은 크롤러 변화 목록을 받아 *제목에서*
       팀을 찾는다. 여기서는 팀이 **질의로 이미 정해져** 있어 그 단계가
       필요 없고, 오히려 해롭다 — 한국어 기사는 제목에 영문 팀명이 없다.
    🔴 실측 2026-09-24 가 이 함수를 만든 이유:
```
크롤러 Bing 리그 검색   기사 6~9일 전 · ±30분 창과 겹치지 않음 → news_dir 8/8 = 0
news_rss 팀별 구글 질의 **0.3h ~ 5.6h** · "최원태 … 하필 지금 부상 이탈"(4.9h)
```
       같은 "RSS" 라도 **질의가 팀별이면 신선하다.** (→ FORKS F-24 정정)
    ⚠️ **창을 두 벌 만들지 않는다**(F-19 가 지적한 자리). 나이는
       `news_rss.parse_feed` 가 이미 72시간으로 자른다 — `max_age_h` 는
       호출부가 굳이 더 좁힐 때만 쓰고 기본은 **그대로 둔다**.
    ⚠️ 한 팀에 악재와 호재가 모두 오면 **0**(상쇄) — `news_dir` 과 같은 규약.
    """
    if not table:
        return None
    score = {"home": 0, "away": 0}
    why: list = []
    seen = False
    for side in ("home", "away"):
        for a in (table.get(side) or []):
            if not isinstance(a, dict):
                continue
            age = a.get("age_h")
            if max_age_h is not None and age is not None and age > float(max_age_h):
                continue
            got = tone_of(a.get("title"))
            if not got:
                continue
            seen = True
            score[side] += got["dir"]
            why.append(f"{got['word']} — {str(a.get('title'))[:40]}")
    for k in score:
        score[k] = 1 if score[k] > 0 else (-1 if score[k] < 0 else 0)
    if not seen:
        return None
    return {"home": score["home"], "away": score["away"],
            "basis": " · ".join(why[:2])}


def direction_of(title, teams):
    """[NWS-D] 제목 → `{"team", "dir": -1|+1, "word"}`. 못 정하면 **None**.

    사용자 2026-09-23: "기사가 악재인가 호재인가를 판단해서 부상이나 다른
    문제가 있으면 **예측에 무조건 좌우되어야 한다**"

    🔴 **지어내지 않는다.** 넷 중 하나라도 걸리면 None 이다:
         악재·호재가 **둘 다** 걸린다 → "부상 딛고 복귀" 를 악재로 읽으면 정반대
         낱말이 하나도 없다
         제목에서 **이 경기의 팀**을 못 찾는다 → 리그 맥락 기사다
         팀 대조표를 못 읽는다
    🔴 낱말의 원본은 `config/evidence_lexicon.yaml` 의 `direction:` 하나다 —
       코드에 적지 않는다(계약이 잠근다).
    ⚠️ 제목만 본다. 본문은 안 읽는다(`llm.enabled: false`). 그래서 "누가
       다쳤는지"가 아니라 **"이 팀에 부상 소식이 있다"** 까지다.
    """
    got = tone_of(title)
    if not got:
        return None
    bad, good = (got["word"], None) if got["dir"] < 0 else (None, got["word"])
    t = str(title or "").strip()

    want = {str(x) for x in (teams or []) if x}
    for local, eng in _local_names().items():
        if local and str(eng) in want and _names_subject(t, str(local)):
            return {"team": str(eng), "dir": (-1 if bad else 1),
                    "word": bad or good}
    return None


def news_dir(changes, teams, *, at=None, window_min=None):
    """[NWS-D] 창 안 기사들의 방향을 **팀별로 합산**한다.

    반환 `{"home", "away", "basis"}` 또는 기사가 없으면 **None**.
    ⚠️ 한 팀에 악재와 호재가 모두 오면 **0** 이다(상쇄). 억지로 하나를
       고르지 않는다.
    ⚠️ 창 폭은 `move.window_min` 을 **재사용**한다 — 사본을 만들지 않는다.
    """
    import datetime as _dt

    if not changes:
        return None
    win = _dt.timedelta(minutes=float(
        window_min if window_min is not None else R.get("move.window_min", 30)))
    now = _to_dt(at) or _dt.datetime.now(_dt.UTC)
    home, away = (list(teams) + [None, None])[:2]

    score = {"home": 0, "away": 0}
    why: list = []
    seen = False
    for c in changes:
        if not isinstance(c, dict):
            continue
        t = _when(c)
        if t is None or abs(t - now) > win:
            continue
        d = direction_of(_title_of(c), teams)
        if not d:
            continue
        seen = True
        key = "home" if d["team"] == home else "away" if d["team"] == away else None
        if key is None:
            continue
        score[key] += d["dir"]
        why.append(f"{d['word']} — {_title_of(c)[:40]}")
    for k in score:
        score[k] = 1 if score[k] > 0 else (-1 if score[k] < 0 else 0)
    return {"home": score["home"], "away": score["away"],
            "basis": " · ".join(why[:2]) if seen else ""}


def explain(points, changes, *, teams=None, window_min=None, min_pp=None) -> dict:
    """이동 구간마다 원인을 붙인다.

    `points`  `[(시각, 홈확률)]` — `n02_market._sets` 가 낸 것, 오래된 것부터
    `changes` `[{at, field, from, to, game}]` — `crawler_feed.load_changes`
    `teams`   `(홈, 원정)` 영문 팀명 — **이 경기의 것만** 남긴다

    반환 `{"moves": [...], "observed": bool, "unexplained_pp": float}`.
    각 move 는 `{from_p, to_p, pp, at, kind, causes: [라벨]}`.
    """
    win = dt.timedelta(minutes=float(
        window_min if window_min is not None else R.get("move.window_min", 30)))
    floor = float(min_pp if min_pp is not None else R.get("move.min_pp", 1.0))

    seq = []
    for ts, p in (points or []):
        t = _to_dt(ts)
        if t is None:
            continue
        try:
            seq.append((t, float(p)))
        except (TypeError, ValueError):
            continue
    seq.sort(key=lambda x: x[0])

    cand = []
    for c in (changes or []):
        if not isinstance(c, dict) or _is_noise(c):
            continue
        if not _is_ours(c, teams):
            continue
        t = _when(c)
        if t is not None:
            cand.append((t, c))
    observed = bool(cand)

    moves, unexplained = [], 0.0
    for i in range(len(seq) - 1):
        t0, p0 = seq[i]
        t1, p1 = seq[i + 1]
        pp = round((p1 - p0) * 100, 2)
        if abs(pp) < floor:
            continue
        hits = [_label(c) for t, c in cand if t0 - win <= t <= t1 + win]
        # 🔴 **`none` 을 만들지 않는다.** 관측이 있었는데 못 찾았으면 자금이고,
        #    관측 자체가 없었으면 자금이라 부를 수 없다(찾아보지 않았으므로).
        kind = NEWS if hits else (MONEY if observed else UNOBSERVED)
        if not hits:
            unexplained += abs(pp)
        moves.append({"from_p": round(p0, 4), "to_p": round(p1, 4), "pp": pp,
                      "at": t1.isoformat(), "kind": kind, "causes": hits[:4]})
    return {"moves": moves, "observed": observed,
            "unexplained_pp": round(unexplained, 2)}


def summary(bag: dict) -> str:
    """한 줄 요약. 🔴 이동이 없으면 **빈 문자열** — 없는 말을 만들지 않는다."""
    moves = (bag or {}).get("moves") or []
    if not moves:
        return ""
    n = {NEWS: 0, MONEY: 0, UNOBSERVED: 0}
    for m in moves:
        n[m.get("kind", UNOBSERVED)] = n.get(m.get("kind", UNOBSERVED), 0) + 1
    parts = []
    if n[NEWS]:
        parts.append(f"근거 있음 {n[NEWS]}")
    if n[MONEY]:
        parts.append(f"자금 {n[MONEY]}")
    if n[UNOBSERVED]:
        parts.append(f"관측 없음 {n[UNOBSERVED]}")
    return f"이동 {len(moves)}구간 — " + " · ".join(parts)
