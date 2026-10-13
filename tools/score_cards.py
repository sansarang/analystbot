"""🔴🔴 **전 경기 평가 — 봇 vs 비교 기준** (사용자 지시 2026-10-12 3번).

> 봇(득실판) · 봇(xG판, 양 팀 xG 있는 경기만) · 비교 기준 둘 — **Elo만**(리그
> Elo→승무패 변환) · **리그 기본률**(홈/무/원정 비율). 지표: **브라이어·로그
> 손실·보정표(5%p 구간)**, 리그별. 시장 배당 있는 경기는 시장도 같은 표에
> (표시만). **봇이 Elo만 쓴 기준보다 못하면 그 사실을 첫 줄에 적는다.**

🔴 예측은 **카드에 적힌 그 수**를 쓴다(다시 돌리지 않는다) — 카드가 그때의 봇이다.
🔴 결과는 **fotmob 경기 페이지**에서 받는다(원장이 아니라 경기 결과가 기준이다).
⚠️ 표본이 작으면 **신뢰구간**을 함께 적는다(브라이어의 부트스트랩 95%).

쓰기:
    PYTHONPATH=. uv run python tools/score_cards.py
    PYTHONPATH=. uv run python tools/score_cards.py --glob "var/accept/*_card.md"
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import math
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
logging.basicConfig(level=logging.WARNING, format="%(message)s")
logger = logging.getLogger("score_cards")

#: 🔴 카드 머리 — `🏟 **A vs B** · 리그 · 10-11 16:00 KST`
HEAD = re.compile(r"^🏟 \*\*(.+?) vs (.+?)\*\* · (.+?) · (\d\d)-(\d\d) ")
#: 🔴 우리 확률 — `🎯 상성 확률 (S3)** — 홈 54% · 무 22% · 원정 24%`
OURS = re.compile(r"상성 확률 \(S3\)\*\* — 홈 (\d+)% · 무 (\d+)% · 원정 (\d+)%")
#: 🔴 xG 판 — `| xG 판 | 61% | 19% | 20% |`
XGB = re.compile(r"\|\s*xG 판\s*\|\s*(\d+)%\s*\|\s*(\d+)%\s*\|\s*(\d+)%")
#: 🔴 기준(Elo) — `- Elo: A **1472** · B **1499** · 차 -27 → 승 35% · 무 29% · 패 35%`
ELO = re.compile(r"Elo:.*?→ 승 (\d+)% · 무 (\d+)% · 패 (\d+)%")
#: 🔴 시장 — `| A 승 | … | 33% (2.75) |`
MKT = re.compile(r"시장 홈 (\d+)% · 원정 (\d+)%")
# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **§15 — 카드가 저장하는 새 열들**(지시서 2026-10-12(둘째))
# ══════════════════════════════════════════════════════════════════
#
#  > 카드마다 저장: 바닥만 · 최종 · **그림자 확률** · 항별 기여 · 경고 등급·S ·
#  > **InfoQ** · 판 날짜 → `score_cards.py` 누적 채점(30경기마다 등급별 표).
#
#  🔴 카드 **글자에서** 읽는다 — 카드가 그때의 봇이다(다시 돌리지 않는다).
#: 🔴 그림자(옛 구조) — `🕯 **그림자 확률**(…) — 홈 27% · 무 25% · 원정 48%`
SHADOW = re.compile(r"그림자 확률\*\*.*?홈 (\d+)% · 무 (\d+)% · 원정 (\d+)%")
#: 🔴 바닥(Elo) — `- 바닥(Elo) — 홈 33% · 무 28% · 원정 39%`
FLOOR = re.compile(r"바닥\(Elo\) — 홈 (\d+)% · 무 (\d+)% · 원정 (\d+)%")
#: 🔴 정보 품질 — `📏 InfoQ **2/5** — …`
INFOQ = re.compile(r"InfoQ \*\*(\d)/(\d)\*\*")
# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **|L9| 구간** — 선택 신호 기록(통합 지시서 2026-10-13 밤 머리 §0)
# ══════════════════════════════════════════════════════════════════
#
#  > 운영 카드마다 |L9| 구간(상위 10% 여부)을 저장 → **30경기마다** |L9| 상위 10%
#  > 경기의 **방향 적중률(운영 판)** 따로 보고. 백필 62경기에서 **51.6%**
#  > (전체 45.7%)였다 — 실전에서 유지되면 **판정 문턱 후보**로 올린다.
#
#  🔴 **확률 불변** — 카드가 적은 구간을 **읽기만** 한다(그 수가 확률을 만든 적 없다).
#: 🔴 `… · |L9| 구간 **상위 10%** — ⚠️ 확률은 안 움직인다…`
L9_BAND = re.compile(r"\|L9\| 구간 \*\*(상위 10%|그 밖|못 쟀다)\*\*")

# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **§11 앙상블 그림자** — 운영·B·M3·E1·E2 를 **함께** 채점한다
# ══════════════════════════════════════════════════════════════════
#
#  > score_cards 30경기마다: 운영·B·M3·Elo·E1·E2 — 로그 손실·방향·상위 20%…
#  🔴 카드 **글자에서** 읽는다(다시 돌리지 않는다). 🔴 E0 유지이므로 운영 =
#     M1 단독이고, E1·E2 는 **그림자**다.
#: 🔴 `**E1**(M1 0.5 + M3 0.5) 홈 41% · 무 27% · 원정 32%`
ENS = re.compile(r"\*\*(E1|E2)\*\*\([^)]*\) 홈 (\d+)% · 무 (\d+)% · 원정 (\d+)%")

# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **4번 — 예상 XI 판 / 확정 XI 판**(지시 2026-10-13 밤 넷째)
# ══════════════════════════════════════════════════════════════════
#
#  > score_cards 30경기마다 두 판의 방향·로그 손실·상위 20% 비교 — 차이가
#  > 작으면 *"판정은 확정 XI 후에만"* 을 **등급 규칙 후보**로 보고.
#
#  🔴 카드 **글자에서** 읽는다. ⚠️ 예상 XI 판이 없는 카드는 **짝이 없다**(그
#     사실을 보고가 적는다 — 0 으로 메우지 않는다).
#: 🔴 `🔁 **예상 XI 판** 홈 41% · 무 27% · 원정 32% → **확정 XI 판**…`
XI_PLATE = re.compile(r"\*\*예상 XI 판\*\* 홈 (\d+)% · 무 (\d+)% · 원정 (\d+)%")

#: 🔴 이변 경고 — `⚠️ 이변 경고 S +0.800 → 🟡 …`
UPSET = re.compile(r"이변 경고 S \*\*([+-][\d.]+)\*\* → (🟡|🔴)")

#: 🔴 30경기 — 지시가 적은 자동 보고 묶음 크기
REPORT_EVERY = 30


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **예상 XI 적중** — 지시 2026-10-13 밤 다섯째 2번("전후")
# ══════════════════════════════════════════════════════════════════
#
#  > 실전 기록으로 측정: 예상 XI 판의 XI 적중(예상 11명 중 실제 선발 수) 전후.
#
#  🔴 **전후를 같은 카드에서** 센다 — 새 규칙의 예상 XI 는 `결장 의심(B 단독)`
#     이름을 **품고 있고**, 옛 규칙의 예상 XI 는 그 이름을 **뺀 것**이다. 그래서
#     한 카드가 두 명단을 다 말해 준다(옛 카드를 다시 돌리지 않는다).
#  ⚠️ **확정 XI 카드는 세지 않는다** — 그 11명은 실제 선발이므로 적중이 늘 11/11
#     이고, 규칙이 바꾸는 것은 **예상** XI 뿐이다.
#: 🔴 XI 머리 — `- **Gwangju FC** 4-2-3-1 [예상] 감독 X`
XI_HEAD = re.compile(r"^- \*\*(.+?)\*\* .*?\[(확정|예상|없음)\]")
#: 🔴 선수 줄 — `    A(GK,1) · B(DF,3) · …` (들여쓴 네 칸)
XI_ROW = re.compile(r"^ {4}(?!⚠️|⬜)(.+)$")
#: 🔴 의심 줄 — `    ⚠️ 결장 의심(B 단독): 이름`
XI_DOUBT = re.compile(r"^ {4}⚠️ 결장 의심\(B 단독\): (.+)$")


def _bare(said: str) -> str:
    """🔴 `A(GK,1)` → `A`(포지션·등번호 괄호를 뗀다)."""
    got = str(said or "").strip()
    i = got.rfind("(")
    return (got[:i] if i > 0 else got).strip()


def xi_of_card(text: str) -> dict:
    """🔴 카드 글자 → `{팀: {"state", "names", "doubt"}}`(블록 2 에서 읽는다)."""
    out: dict[str, dict] = {}
    who = ""
    for line in str(text or "").splitlines():
        head = XI_HEAD.match(line)
        if head:
            who = head.group(1).strip()
            out[who] = {"state": head.group(2), "names": [], "doubt": []}
            continue
        if not who or who not in out:
            continue
        said = XI_DOUBT.match(line)
        if said:
            out[who]["doubt"].append(said.group(1).strip())
            continue
        row = XI_ROW.match(line)
        if row and not out[who]["names"]:
            out[who]["names"] = [_bare(x) for x in row.group(1).split(" · ")
                                 if _bare(x)]
            continue
        if line and not line.startswith(" "):
            who = ""                      # 🔴 블록이 끝났다
    return out


def _pct(*vals: str) -> list[float]:
    got = [float(v) / 100.0 for v in vals]
    tot = sum(got)
    return [x / tot for x in got] if tot else got


def read_card(path: Path) -> dict | None:
    """🔴 카드 한 장 → `{home, away, league, day, ours, xg, elo, market}`."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    head = HEAD.search(text)
    if not head:
        return None
    out: dict = {"file": path.name, "home": head.group(1).strip(),
                 "away": head.group(2).strip(), "league": head.group(3).strip(),
                 "day": f"2026-{head.group(4)}-{head.group(5)}"}
    got = OURS.search(text)
    if not got:
        return None
    out["ours"] = _pct(*got.groups())
    said_l9 = L9_BAND.search(text)
    out["l9_band"] = said_l9.group(1) if said_l9 else ""
    for got_ens in ENS.finditer(text):
        out[got_ens.group(1).lower()] = _pct(*got_ens.groups()[1:])
    said_xi = XI_PLATE.search(text)
    if said_xi:
        out["xi_expected"] = _pct(*said_xi.groups())
    said = XGB.search(text)
    if said:
        out["xg"] = _pct(*said.groups())
    said = ELO.search(text)
    if said:
        out["elo"] = _pct(*said.groups())
    said = MKT.search(text)
    if said:
        h, a = float(said.group(1)) / 100.0, float(said.group(2)) / 100.0
        d = max(0.0, 1.0 - h - a)
        out["market"] = [x / (h + d + a) for x in (h, d, a)] if (h + a) else None
    # 🔴🔴 §15 — 새 열들(없으면 **없는 채로** 둔다 · 0 으로 세지 않는다 · #3)
    said = SHADOW.search(text)
    if said:
        out["shadow"] = _pct(*said.groups())
    said = FLOOR.search(text)
    if said:
        out["floor"] = _pct(*said.groups())
    said = INFOQ.search(text)
    if said:
        out["infoq"] = int(said.group(1))
    said = UPSET.search(text)
    if said:
        out["upset_s"] = float(said.group(1))
        out["upset"] = said.group(2)
    # 🔴 예상 XI 적중의 재료(블록 2) — 없으면 **빈 표**다(0 으로 세지 않는다)
    out["xi_block"] = xi_of_card(text)
    return out


async def result_of(net, row: dict) -> tuple[int, str, dict] | None:
    """🔴 그 경기의 **결과**(0 홈승·1 무·2 원정승)·스코어·**실제 선발 명단**.

    🔴 선발은 같은 경기 페이지에서 온다(`lineup.{home,away}Team.starters`) —
       예상 XI 적중을 세는 재료다. 못 읽으면 **빈 표**다(#3).
    """
    from app.collect import fotmob as fm
    from app.core import discover as d
    idx = await fm.team_index(net)
    for name in (row["home"], row["away"]):
        for tid, slug in d._slug_hit(idx, name)[:3]:
            page = await net.get(fm.team_fixtures_url(tid, slug))
            rows = d.team_fixtures(getattr(page, "text", "") or "", tid)
            for one in rows:
                if not str(one.get("utc") or "").startswith(row["day"]):
                    continue
                if not one.get("finished"):
                    continue
                g = await net.get(fm.match_url(str(one.get("id") or "")))
                j = fm.payload(getattr(g, "text", "") or "") or {}
                goals = fm.goals_of(j)
                if not goals:
                    continue
                h = sum(1 for x in goals
                        if bool(x.get("home")) != bool(x.get("own_goal")))
                a = len(goals) - h
                said_xi = {}
                for which in ("homeTeam", "awayTeam"):
                    side = fm._side(j, which)
                    got_names = fm._names(side)
                    if got_names:
                        said_xi[str(side.get("name") or which)] = got_names
                return ((0 if h > a else (1 if h == a else 2)), f"{h}-{a}",
                        said_xi)
    return None


def brier(p: list[float], hit: int) -> float:
    return sum((p[i] - (1.0 if i == hit else 0.0)) ** 2 for i in range(3))


def logloss(p: list[float], hit: int) -> float:
    return -math.log(max(1e-9, min(1.0, p[hit])))


def boot_ci(vals: list[float], *, n: int = 2000) -> tuple[float, float]:
    """🔴 부트스트랩 95% — 표본이 작을 때 **반드시** 함께 적는다."""
    if len(vals) < 2:
        return (float("nan"), float("nan"))
    rnd = random.Random(7)
    got = []
    for _ in range(n):
        said = [vals[rnd.randrange(len(vals))] for _ in vals]
        got.append(sum(said) / len(said))
    got.sort()
    return got[int(0.025 * n)], got[int(0.975 * n)]


def _bins(rows: list[tuple[float, int]]) -> str:
    """🔴 보정표 — **5%p 구간**(예측 확률 ↔ 실제 비율)."""
    box: dict[int, list[int]] = {}
    for p, hit in rows:
        key = min(19, int(float(p) * 20))
        box.setdefault(key, []).append(hit)
    out = ["    | 구간 | n | 예측 | 실제 |", "    |---|---|---|---|"]
    for key in sorted(box):
        got = box[key]
        out.append(f"    | {key * 5}~{key * 5 + 5}% | {len(got)} | "
                   f"{key * 5 + 2.5:.0f}% | {sum(got) / len(got):.0%} |")
    return "\n".join(out)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default="var/accept/*_card.md")
    args = ap.parse_args()
    from app.net import Net
    net = Net(cache=True)
    rows: list[dict] = []
    seen: set[str] = set()
    for path in sorted(ROOT.glob(args.glob)):
        got = read_card(path)
        if not got:
            continue
        key = f"{got['home']}|{got['away']}|{got['day']}"
        if key in seen:          # 🔴 같은 경기 여러 카드 → **마지막 것만**
            rows = [r for r in rows if f"{r['home']}|{r['away']}|{r['day']}" != key]
        seen.add(key)
        rows.append(got)
    print(f"카드 {len(rows)}장(같은 경기는 마지막 카드만)")
    scored: list[dict] = []
    for one in rows:
        said = await result_of(net, one)
        if said is None:
            continue
        one["hit"], one["score"], one["starters"] = said
        scored.append(one)
    print(f"결과를 받은 경기 **{len(scored)}장**")
    if not scored:
        return
    # ── 리그 기본률(그 표본 자체의 홈/무/원정 비율)
    base = [sum(1 for r in scored if r["hit"] == i) / len(scored)
            for i in range(3)]
    print(f"리그 기본률(이 표본) — 홈 {base[0]:.0%} · 무 {base[1]:.0%} · "
          f"원정 {base[2]:.0%}")
    #: 🔴 1번 — **균등 기준**(33/33/33)을 더한다(사용자 지시 2026-10-12)
    even = [1 / 3, 1 / 3, 1 / 3]
    models = {
        "봇(득실판)": [(r["ours"], r["hit"]) for r in scored],
        "봇(xG판)": [(r["xg"], r["hit"]) for r in scored if r.get("xg")],
        # 🔴 §15 — **그림자(옛 구조)** 와 **바닥만**(Elo 바닥)도 같은 표에
        "그림자(옛 구조)": [(r["shadow"], r["hit"]) for r in scored
                      if r.get("shadow")],
        "바닥만(Elo 바닥)": [(r["floor"], r["hit"]) for r in scored
                       if r.get("floor")],
        "Elo만": [(r["elo"], r["hit"]) for r in scored if r.get("elo")],
        "리그 기본률": [(base, r["hit"]) for r in scored],
        "균등 33/33/33": [(even, r["hit"]) for r in scored],
        "시장(표시만)": [(r["market"], r["hit"]) for r in scored
                    if r.get("market")],
    }
    print()
    print("| 모형 | n | 브라이어 | 95% 구간 | 로그 손실 |")
    print("|---|---|---|---|---|")
    got_brier: dict[str, float] = {}
    for name, box in models.items():
        if not box:
            print(f"| {name} | 0 | — | — | — |")
            continue
        b = [brier(p, h) for p, h in box]
        ll = [logloss(p, h) for p, h in box]
        lo, hi = boot_ci(b)
        got_brier[name] = sum(b) / len(b)
        print(f"| {name} | {len(box)} | **{sum(b) / len(b):.4f}** | "
              f"{lo:.4f}~{hi:.4f} | {sum(ll) / len(ll):.4f} |")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **§13·§15 InfoQ 구간별 적중률** · **§10 경고 등급별**
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 지난 카드 전부의 **InfoQ 분포**와 **구간별 적중률**(표본 수 함께 · §18).
    #  > 경고 등급별: 경기 수 · 예측 강팀 승률 · 실제 강팀 승률.
    #
    #  🔴 등급·경고는 **확률을 안 바꿨다** — 이 표가 묻는 것은 *"그 등급이 뜻이
    #     있었나"* 다. ⚠️ 30경기 미만 묶음은 **그 사실을 적는다**(작은 표본).
    from app.core import metrics as _me
    said_iq = [r for r in scored if r.get("infoq") is not None]
    print()
    if said_iq:
        print("| InfoQ | n | 방향 적중률 | 95% | ⚠️ |")
        print("|---|---|---|---|---|")
        for lo, hi, name in ((0, 2, "0~2(얇다)"), (3, 3, "3"), (4, 5, "4~5")):
            box = [r for r in said_iq if lo <= int(r["infoq"]) <= hi]
            if not box:
                print(f"| {name} | 0 | — | — | — |")
                continue
            hits = sum(1 for r in box
                       if _me.direction_hit(r["ours"], r["hit"]))
            w_lo, w_hi = _me.wilson(hits, len(box))
            print(f"| {name} | {len(box)} | **{hits / len(box):.1%}** | "
                  f"{w_lo:.1%}~{w_hi:.1%} | "
                  + ("" if len(box) >= REPORT_EVERY
                     else f"🔴 **{REPORT_EVERY}경기 미만**") + " |")
    else:
        print("⬜ **InfoQ 를 적은 카드가 없다** — 그 열은 이번 지시로 생겼다"
              "(앞으로 쌓인다)")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **|L9| 상위 10% 구간의 방향 적중률**(머리 §0 · 확률 불변)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **§11 — 운영·M3·E1·E2 를 나란히**(30경기 미만은 "참고")
    print()
    print("| 판 | n | 로그 손실 | 방향 | 상위 20% | ⚠️ |")
    print("|---|---|---|---|---|---|")
    for name, key in (("운영(M1 단독)", "ours"), ("그림자 M3", "shadow"),
                      ("E1(0.5/0.5)", "e1"), ("E2(판 w)", "e2")):
        box = [r for r in scored if r.get(key)]
        if not box:
            print(f"| {name} | 0 | — | — | — | ⬜ 그 줄을 적은 카드가 없다 |")
            continue
        ll = [_me.logloss(r[key], r["hit"]) for r in box]
        hit = sum(1 for r in box if _me.direction_hit(r[key], r["hit"]))
        said_b = _me.bands([{"p": r[key], "hit": r["hit"]} for r in box],
                           keys=("p",))
        print(f"| {name} | {len(box)} | **{sum(ll) / len(ll):.4f}** | "
              f"{hit / len(box):.1%} | {said_b[0.20]['p']['rate']:.1%} | "
              + ("" if len(box) >= REPORT_EVERY
                 else f"🔴 **{REPORT_EVERY}경기 미만 — 참고**") + " |")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **예상 XI 판 vs 확정 XI 판**(지시 4번) — 짝이 있는 카드만
    # ══════════════════════════════════════════════════════════════════
    pair = [r for r in scored if r.get("xi_expected") and r.get("ours")]
    print()
    if pair:
        print("| 판 | n | 로그 손실 | 방향 | 상위 20% | ⚠️ |")
        print("|---|---|---|---|---|---|")
        for name, key in (("예상 XI 판", "xi_expected"),
                          ("확정 XI 판(운영)", "ours")):
            ll = [_me.logloss(r[key], r["hit"]) for r in pair]
            hit = sum(1 for r in pair if _me.direction_hit(r[key], r["hit"]))
            said_b = _me.bands([{"p": r[key], "hit": r["hit"]} for r in pair],
                               keys=("p",))
            print(f"| {name} | {len(pair)} | **{sum(ll) / len(ll):.4f}** | "
                  f"{hit / len(pair):.1%} | "
                  f"{said_b[0.20]['p']['rate']:.1%} | "
                  + ("" if len(pair) >= REPORT_EVERY
                     else f"🔴 **{REPORT_EVERY}경기 미만 — 참고**") + " |")
        a = [_me.logloss(r["xi_expected"], r["hit"]) for r in pair]
        b = [_me.logloss(r["ours"], r["hit"]) for r in pair]
        gap = sum(a) / len(a) - sum(b) / len(b)
        print()
        print(f"🔴 두 판 차이 — 로그 손실 **{gap:+.4f}**(예상 − 확정) · "
              + ("차이가 **작다** → *\"판정은 확정 XI 후에만\"* 을 등급 규칙 "
                 "**후보로 올린다**(지시 4번)" if abs(gap) < 0.005
                 else "차이가 **크다** → 확정 XI 판을 기다릴 값이 있다"))
    else:
        print("⬜ **예상/확정 두 판을 적은 카드가 없다** — 그 줄은 이번 지시로 "
              "생겼다(재분석이 돌면 쌓인다)")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **예상 XI 적중 — 전후**(지시 2026-10-13 밤 다섯째 2번)
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 **후**(새 규칙) = 카드에 적힌 11명 그대로 · **전**(옛 규칙) = 그 중
    #     `결장 의심(B 단독)` 이름을 **뺀 명단**. 적중은 *"그 명단 중 실제로
    #     선발한 수"* 이고, 명단 길이가 다르므로 **비율도 함께** 적는다.
    print()
    box_xi: list[dict] = []
    for r in scored:
        said_start = dict(r.get("starters") or {})
        if not said_start:
            continue
        for who, one in dict(r.get("xi_block") or {}).items():
            if str(one.get("state")) != "예상" or not one.get("names"):
                continue
            # 🔴 실제 선발은 **같은 경기 페이지**의 팀 이름으로 찾는다
            real = None
            for name, rows_real in said_start.items():
                if (str(name).strip().lower() == str(who).strip().lower()
                        or str(who) in str(name) or str(name) in str(who)):
                    real = {str(x).strip() for x in rows_real}
                    break
            if not real:
                continue
            after = [str(x) for x in one["names"]]
            doubt = {str(x).strip() for x in (one.get("doubt") or [])}
            before = [x for x in after if x not in doubt]
            box_xi.append({"file": r["file"], "team": who, "real": real,
                           "after": after, "before": before,
                           "doubt": sorted(doubt)})
    if box_xi:
        print("| 규칙 | 명단 | 예상 명단 수 | 실제 선발 적중 | 적중률 |")
        print("|---|---|---|---|---|")
        for name, key in (("전(옛 — B 단독도 뺐다)", "before"),
                          ("후(새 — B 단독은 남긴다)", "after")):
            n_all = sum(len(x[key]) for x in box_xi)
            n_hit = sum(sum(1 for p in x[key] if p in x["real"])
                        for x in box_xi)
            print(f"| {name} | {len(box_xi)}팀 | {n_all} | **{n_hit}** | "
                  f"{(n_hit / n_all if n_all else 0):.1%} |")
        said_diff = [x for x in box_xi if x["doubt"]]
        print()
        print(f"🔴 **규칙이 갈린 명단 {len(said_diff)}팀**"
              + (" — " + " · ".join(
                  f"{x['team']} {', '.join(x['doubt'])}"
                  f"(실제 선발 {sum(1 for p in x['doubt'] if p in x['real'])}"
                  f"/{len(x['doubt'])})" for x in said_diff[:8])
                 if said_diff else " — 🔴 **B 단독 결장이 한 건도 없었다**("
                 "규칙이 아직 아무 명단도 바꾸지 않았다)"))
        if len(box_xi) < REPORT_EVERY:
            print(f"⚠️ **{REPORT_EVERY}팀 미만 — 참고**(쌓이면 다시 센다)")
    else:
        print("⬜ **예상 XI 를 적은 카드가 없다** — 적중을 셀 재료가 없다"
              "(확정 XI 카드는 세지 않는다 · 늘 11/11 이다)")
    said_l9 = [r for r in scored if r.get("l9_band")]
    print()
    if said_l9:
        print("| |L9| 구간 | n | 방향 적중률(운영) | 95% | ⚠️ |")
        print("|---|---|---|---|---|")
        for name in ("상위 10%", "그 밖", "못 쟀다"):
            box = [r for r in said_l9 if r["l9_band"] == name]
            if not box:
                print(f"| {name} | 0 | — | — | — |")
                continue
            hits = sum(1 for r in box
                       if _me.direction_hit(r["ours"], r["hit"]))
            w_lo, w_hi = _me.wilson(hits, len(box))
            print(f"| {name} | {len(box)} | **{hits / len(box):.1%}** | "
                  f"{w_lo:.1%}~{w_hi:.1%} | "
                  + ("" if len(box) >= REPORT_EVERY
                     else f"🔴 **{REPORT_EVERY}경기 미만 — 참고**") + " |")
        print()
        print("🔴 백필(630경기 · 2026-10-13)에서는 상위 10% 62경기가 **51.6%**, "
              "전체가 **45.7%** 였다 — 실전에서 유지되면 **판정 문턱 후보**다.")
        print("⚠️ 이 구간은 **확률을 만든 적이 없다**(표시·검증용 · 잠금 계약).")
    else:
        print("⬜ **|L9| 구간을 적은 카드가 없다** — 그 줄은 이번 지시로 생겼다"
              "(앞으로 쌓인다)")
    said_up = [r for r in scored if r.get("upset")]
    print()
    if said_up:
        print("| 경고 | n | 예측 강팀 승률 | 실제 강팀 승률 | 차이 95% |")
        print("|---|---|---|---|---|")
        for grade in ("🔴", "🟡"):
            box = [r for r in said_up if r["upset"] == grade]
            if not box:
                print(f"| {grade} | 0 | — | — | — |")
                continue
            fav = [(0 if r["ours"][0] >= r["ours"][2] else 2) for r in box]
            pred = sum(r["ours"][f] for r, f in zip(box, fav, strict=True))
            real = sum(1 for r, f in zip(box, fav, strict=True)
                       if r["hit"] == f)
            diff = _me.paired(
                [float(1 if r["hit"] == f else 0)
                 for r, f in zip(box, fav, strict=True)],
                [float(r["ours"][f]) for r, f in zip(box, fav, strict=True)])
            print(f"| {grade} | {len(box)} | {pred / len(box):.1%} | "
                  f"{real / len(box):.1%} | "
                  f"{diff['lo']:+.3f}~{diff['hi']:+.3f} |")
    else:
        print("⬜ **이변 경고가 켜진 카드가 없다**(판이 없거나 신호가 0 이었다)")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **1번 짝지은 비교** — 모든 모형이 예측을 가진 **같은 경기만**
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 왜 — 모형마다 n 이 다르면(봇 11 · Elo만 8) 그 차이가 **표본 차이**인지
    #     **실력 차이**인지 가릴 수 없다. 짝지어야 차이의 구간을 낼 수 있다.
    pairs = [r for r in scored if r.get("elo")]
    print()
    print(f"**짝지은 비교**(모든 모형이 예측을 가진 경기 **{len(pairs)}장**)")
    if pairs:
        got_rate = [sum(1 for r in pairs if r["hit"] == i) / len(pairs)
                    for i in range(3)]
        print(f"그 표본의 실제 비율 — 홈 {got_rate[0]:.0%} · 무 "
              f"{got_rate[1]:.0%} · 원정 {got_rate[2]:.0%}")
        box = {"봇(득실판)": [(r["ours"], r["hit"]) for r in pairs],
               "Elo만": [(r["elo"], r["hit"]) for r in pairs],
               "리그 기본률": [(base, r["hit"]) for r in pairs],
               "균등 33/33/33": [(even, r["hit"]) for r in pairs]}
        print()
        print("| 모형 | 브라이어 | 로그 손실 |")
        print("|---|---|---|")
        for name, rows_p in box.items():
            b = [brier(p, h) for p, h in rows_p]
            ll = [logloss(p, h) for p, h in rows_p]
            print(f"| {name} | **{sum(b) / len(b):.4f}** | "
                  f"{sum(ll) / len(ll):.4f} |")
        # 🔴 **차이의 부트스트랩 구간** — 경기별 차이를 다시 뽑는다(짝 유지)
        print()
        print("| 차이(봇 − 기준) | 브라이어 차 | 95% 구간 | 0 을 품나 |")
        print("|---|---|---|---|")
        mine = [brier(r["ours"], r["hit"]) for r in pairs]
        for name in ("Elo만", "리그 기본률", "균등 33/33/33"):
            other = [brier(p, h) for p, h in box[name]]
            diff = [a - b for a, b in zip(mine, other, strict=True)]
            lo, hi = boot_ci(diff)
            print(f"| vs {name} | {sum(diff) / len(diff):+.4f} | "
                  f"{lo:+.4f}~{hi:+.4f} | "
                  + ("⚠️ 품는다(판정 못 한다)" if lo <= 0 <= hi
                     else ("🔴 **봇이 나쁘다**" if lo > 0 else "✅ 봇이 낫다"))
                  + " |")
    print()
    if "Elo만" in got_brier and got_brier.get("봇(득실판)", 9) > got_brier["Elo만"]:
        print(f"🔴🔴 **봇이 `Elo만` 쓴 기준보다 못하다** — 봇 "
              f"{got_brier['봇(득실판)']:.4f} vs Elo만 {got_brier['Elo만']:.4f}")
    elif "Elo만" in got_brier:
        print(f"✅ 봇이 `Elo만` 기준보다 낫다 — 봇 {got_brier['봇(득실판)']:.4f} "
              f"vs Elo만 {got_brier['Elo만']:.4f}")
    print()
    print("보정표 — 봇(득실판) 홈 확률")
    print(_bins([(r["ours"][0], 1 if r["hit"] == 0 else 0) for r in scored]))
    # ── 리그별
    print()
    print("| 리그 | n | 봇 브라이어 | Elo만 |")
    print("|---|---|---|---|")
    by: dict[str, list[dict]] = {}
    for r in scored:
        by.setdefault(r["league"], []).append(r)
    for lg, box in sorted(by.items(), key=lambda kv: -len(kv[1])):
        b = sum(brier(r["ours"], r["hit"]) for r in box) / len(box)
        said = [r for r in box if r.get("elo")]
        e = (sum(brier(r["elo"], r["hit"]) for r in said) / len(said)
             if said else None)
        print(f"| {lg} | {len(box)} | {b:.4f} | "
              + (f"{e:.4f} |" if e is not None else "— |"))


if __name__ == "__main__":
    asyncio.run(main())
