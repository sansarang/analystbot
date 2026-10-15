"""🔴🔴 **표시 판의 팀 이름 맞춤** — 판은 fotmob 약칭, 카드는 정식명이다.

⚠️ 실사고 2026-10-14 01:14(UCL 두 경기): 판 셋(`comp_record`·`comp_history`·
   `league_elo_auto`)을 그 자리에서 채웠는데 카드가 **셋 다 ⬜** 였다 —
   판에는 `Lens`·`Sporting CP`·`Slavia Prague` 로 적혔고 카드는
   `Racing Club de Lens`·`Sporting Clube de Portugal`·`SK Slavia Praha` 로
   물었다. 똑같은 팀인데 글자가 달라 못 찾았다.

🔴 **맞춤은 이 함수 하나다**(사본 금지) — 세 읽기가 같은 규칙을 쓴다.
🔴 규칙 — ① 글자 그대로(대소문자 무시) ② 흔한 꼬리말(fc·cp·sk·fk·clube…)을 뺀
   **속 낱말**이 반쪽이라도 겹치면 후보 ③ 후보가 **하나일 때만** 쓴다.
⚠️ 후보가 둘 이상이면 **고르지 않는다** — 이름으로 남긴다(지어내지 않는다 · #3).
⚠️ 이 통로는 **표시 전용 판**만 쓴다 — 확률 경로에 닿지 않는다.
"""
from __future__ import annotations

#: 🔴 팀 이름에서 **구단 형태**를 말하는 낱말 — 겹침을 셀 때 뺀다
NOISE = {"fc", "cf", "cp", "sc", "sk", "fk", "ac", "as", "rc", "club",
         "clube", "de", "da", "do", "of", "the", "futbol", "football",
         "calcio", "sport", "sportif", "team", "afc", "kf", "nk", "bk",
         # 🔴🔴 **관사**(사용자 지적 2026-10-15) — ⚠️ 실사고: `de`·`da`·`do` 는
         #    있는데 `la` 가 없어 **`LA Galaxy` 가 `Avenir de La Marsa`**(튀니지
         #    Ligue I)에 붙었다(속 낱말 `la` 하나 ÷ 2 = 0.5 = CUT). 그 바람에
         #    MLS 11:30 세 경기 질의가 **남의 경기**로 확정됐다.
         "la", "le", "les", "el", "los", "las", "lo",
         "du", "di", "del", "des", "der", "den", "dos"}
# ⚠️ `racing`·`sporting`·`united`·`city` 는 **빼지 않는다** — 그것이 유일한 속
#    낱말인 이름이 있다(`Sporting CP` 의 속 낱말은 `sporting` 뿐이다).

#: 🔴🔴 **혼자서는 못 맞추는 낱말** — 수십 팀이 함께 쓴다.
#    ⚠️ 실사고 2026-10-14 01:19: `Buriram United` 가 `united` 하나로
#    `JEF United Chiba`(J1 판)에 붙었다 — 계약 SR2 가 잡았다(`ja` ≠ `th`).
WEAK = {"united", "city", "sporting", "racing", "athletic", "club", "al"}
# ⚠️ `al` — 아랍어 관사다. 안 빼면 `Al-Sadd`·`Al Hilal`·`Al Ahli` 가 서로
#    절반 겹친다(실측 2026-10-14: 외부 대조 표에 남의 경기가 섞여 들어왔다).
# ⚠️ `real`·`atletico` 는 **빼지 않는다** — 실측 2026-10-14: `real` 을 약한
#    낱말로 두자 `Real Madrid` 와 `Atlético Madrid` 의 겹침이 **1.00 으로 같아져**
#    외부 대조에서 짝을 못 골랐다(UCL 58경기가 그렇게 떨어졌다).

#: 🔴 겹침 문턱 — 속 낱말이 **반쪽**은 같아야 한다
CUT = 0.5


#: 🔴🔴 **별칭표**(의심 검증 v2 §1-3) — 보드·CSV 의 약칭을 우리 이름 쪽 낱말로.
#:
#:  ⚠️ 실측 2026-10-14: `football-data` 의 `Wolves` 가 `Wolverhampton Wanderers`
#:     와 **한 낱말도 안 겹쳐** 보드 수집이 실패했다(울브스–볼턴). 약칭은 추측이
#:     아니라 **그 파일이 쓰는 표기**다(받아서 확인했다).
#:  🔴 여자팀은 `(W)`·`women` 으로 **갈라 둔다** — 같은 이름의 남자팀과 섞이면
#:     보드가 다른 경기 것이 된다.
ALIAS = {
    "wolves": "wolverhampton", "spurs": "tottenham",
    "man": "manchester", "utd": "united", "weds": "wednesday",
    "brom": "bromwich", "wba": "bromwich", "qpr": "queens",
    "forest": "nottingham", "nott": "nottingham", "sheff": "sheffield",
    "boro": "middlesbrough", "psg": "paris", "inter": "internazionale",
    "atleti": "atletico", "gladbach": "monchengladbach",
    "dortmund": "dortmund", "bayern": "bayern", "leverkusen": "leverkusen",
    "frankfurt": "frankfurt", "sociedad": "sociedad", "betis": "betis",
    "zvezda": "crvena", "cska": "cska", "psv": "psv", "ajax": "ajax",
}
#: 🔴 여자팀 꼬리표 — 이 낱말이 한쪽에만 있으면 **다른 팀**이다
WOMEN = {"w", "women", "feminine", "femenino", "여자"}

#: 🔴🔴 **두 낱말 별칭**(§1-3 · 실측 2026-10-14) — 한 낱말로는 못 가르는 약칭.
#:
#:  ⚠️ `football-data` 의 `Ath Madrid` 는 **아틀레티코**이고 `Ath Bilbao` 는
#:     **아틀레틱**이다 — `ath` 하나만 보면 둘이 같아지고, 거기에 `madrid` 가
#:     `Real Madrid` 와도 반쪽 겹쳐 *"후보가 둘 이상"* 으로 떨어졌다(라리가
#:     백필 실보드 **140줄**이 그렇게 빠졌다).
#:  🔴 그래서 **낱말 쪼개기 전에** 글자를 바꾼다. 추측이 아니라 그 파일이 쓰는
#:     표기다(받아서 확인했다 · `mmz4281/2526/SP1.csv`).
PHRASE = {
    "ath madrid": "atletico madrid", "ath bilbao": "athletic bilbao",
    "espanol": "espanyol", "sp lisbon": "sporting lisbon",
    "sp braga": "sporting braga", "vallecano": "rayo vallecano",
    "for sittard": "fortuna sittard", "la coruna": "deportivo coruna",
}


def _core(said: str) -> set[str]:
    """🔴 속 낱말 — 소문자·꼬리말 제거 · **분음 부호도 걷는다**.

    🔴 분음 부호를 걷는 곳은 `teamref._plain` **하나**다(사본 금지) — 한글·가나를
       자모로 쪼개지 않는 규칙이 거기에 있다(그 함수 머리말의 실사고 둘).
    ⚠️ 실측 2026-10-14: 걷지 않아서 `Alaves`↔`Deportivo Alavés` ·
       `Malaga`↔`Málaga` 가 **한 낱말도 안 겹쳤다** — 라리가 백필 실보드가
       그만큼 빠졌다.
    """
    from app.teamref import _plain
    flat = _plain(str(said or "")).lower()
    # 🔴 **두 낱말 별칭을 먼저** 바꾼다(쪼갠 뒤에는 못 본다)
    for bad, good in PHRASE.items():
        if bad in flat:
            flat = flat.replace(bad, good)
    # ⚠️ 한 글자 토막은 버린다(`F.C.` → `f`·`c` 가 남아 겹침을 어지럽힌다)
    got = {ALIAS.get(w, w) for w in
           flat.replace(".", " ").replace("-", " ")
           .replace("(", " ").replace(")", " ").replace("'", " ").split()
           if w and len(w) > 1 and w not in NOISE}
    return got or {w for w in flat.split() if w}


def is_women(said: str) -> bool:
    """🔴 그 이름이 **여자팀**인가(`(W)`·`Women`…) — 원문 토막으로 본다."""
    got = {w for w in str(said or "").lower()
           .replace("(", " ").replace(")", " ").replace(".", " ").split()}
    return bool(got & WOMEN)


def share(a: str, b: str, *, weak: bool = True) -> float:
    """🔴 두 이름의 **속 낱말 겹침**(0~1) — `pick` 과 외부 대조가 같이 쓴다.

    🔴 `weak=False` 면 흔한 낱말을 **안 뺀다** — 외부 대조가 `Real Madrid` 와
       `Atlético Madrid` 를 가를 때 그 수를 잣대로 쓴다(짝 맞춤의 가름끈).
    """
    mine, yours = _core(a), _core(b)
    if not mine or not yours:
        return 0.0
    # 🔴 **여자팀/남자팀이 섞이면 0 이다**(§1-3) — 한쪽에만 꼬리표가 있으면 다른 팀
    #    ⚠️ 꼬리표는 **원문에서** 본다 — `(W)` 의 `w` 는 한 글자라 `_core` 가
    #       버린다(실측 2026-10-14: `Arsenal` ↔ `Arsenal (W)` 가 1.00 이었다).
    if is_women(a) != is_women(b):
        return 0.0
    if weak:
        x, y = mine - WEAK, yours - WEAK
        if x and y:
            mine, yours = x, y
    return len(mine & yours) / max(1, min(len(mine), len(yours)))


def pick(name: str, keys) -> tuple[str, str]:
    """🔴 그 이름에 맞는 **판의 열쇠**. 못 고르면 `("", 사유)`.

    🔴 후보가 둘 이상이면 **고르지 않는다**(사유에 후보를 적는다).
    """
    rows = [str(k) for k in (keys or [])]
    said = str(name or "").strip()
    if not said or not rows:
        return "", "⬜ 판이 비었다"
    low = said.lower()
    hits: list[tuple[float, str]] = []
    for k in rows:
        if k.strip().lower() == low:
            return k, "글자 그대로"
    for k in rows:
        # 🔴 **흔한 낱말만 겹치는 것은 맞춤이 아니다**(`share` 가 그 규칙을 든다)
        got = share(said, k)
        if got >= CUT:
            hits.append((got, k))
    if not hits:
        return "", f"⬜ `{said}` 가 판에 없다(적힌 팀 {len(rows)}개)"
    top = max(h[0] for h in hits)
    best = [k for s, k in hits if s >= top]
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **같은 비율이면 겹친 낱말이 많은 쪽**(§1-3 · 실측 2026-10-14)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ `share` 는 **비율**이라 짧은 이름이 유리하다. 실측: `Sheffield Weds` 가
    #     `Sheffield United`(겹침 `sheffield` 하나 ÷ 1 = **1.00**)와
    #     `Sheffield Wednesday`(`sheffield`·`wednesday` ÷ 2 = **1.00**)에
    #     똑같이 1.00 이 나와 *"후보가 둘 이상"* 으로 떨어졌다(ELC 백필 46줄).
    #  🔴 그때는 **겹친 낱말 수**가 가른다 — 둘이 겹친 쪽이 맞는 팀이다.
    #  ⚠️ 그래도 같으면 **고르지 않는다**(지어내지 않는다 · #4).
    if len(best) > 1:
        mine = _core(said)
        deep = {k: len(mine & _core(k)) for k in best}
        most = max(deep.values())
        narrow = [k for k in best if deep[k] == most]
        if len(narrow) == 1:
            return narrow[0], (f"이름 맞춤 `{narrow[0]}`(속 낱말 {top:.0%} 같고 "
                               f"겹친 낱말 {most}개 — 후보 {len(best)}개 중 최다)")
        best = narrow
    if len(best) > 1:
        return "", (f"⬜ `{said}` 는 후보가 둘 이상이다 — "
                    f"{' · '.join(sorted(best)[:4])}(고르지 않는다)")
    return best[0], f"이름 맞춤 `{best[0]}`(속 낱말 {top:.0%} 같다)"
