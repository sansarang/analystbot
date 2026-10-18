"""🔴🔴 **선수 능력치를 전략분석가에게 준다** — 사용자 지시 2026-10-17.

> 핵심선수 결장 · 후보선수로 대체했을때 가설제공(**숫자가 아닌 능력치**) …
> 이거는 전략분석가한테 줘야 하는거다 … 그러면 전략분석가들이 가설을 세워서
> 분석도 할거고 이게 맞다 안맞다는 교차검증을 통해 할거고 맞으면 변수를 움직일거고

🔴 **이 통로가 내는 것은 "글자"다.** 수(백분위)는 코드가 읽고, 모델에게는
   `강점 / 보통 / 약점` 이라는 **상대 글자**로 넘긴다. 왜:
   ① 모델에 수를 주면 모델이 **그 수를 근거로** 말한다 — 그 수가 틀리면 평도
      틀리고, 그때 `0.36` 이 어디서 왔는지 사람이 못 되짚는다.
   ② 이 저장소의 결이 이미 그렇다 — ⑤-b2 는 모델에게 **부등호만** 받는다.
   🔴 그래서 여기서도 **비교는 코드가, 전술 해석은 모델이** 한다.

## 재료는 어디서 오나 — 실측 2026-10-17
`fotmob.com/players/{번호}` 의 `traits` 다(`fotmob.traits_of` 가 읽는다):

```
Duk(공격형 MF/윙) "Stats compared to other attacking midfielders/wingers"
   찬스 창출 0.36 · 공중볼 0.80 · 수비 행동 0.68 · 득점 0.34 · 슈팅 0.32 …
Nagai(GK)        골키퍼는 **지표가 다르다**
   선방률 0.88 · 실점 0.24 · 스위퍼 0.56 · 하이볼 0.01 · 클린시트 0.10 …
```

🔴🔴 **비교 묶음을 출처가 고른다** — 그래서 *"어떤 지표로 견줄까"* 를 우리가
   정하지 않는다(#4 추측 금지). ⚠️ 종전 선수단 페이지에는 **경합·수비 지표가
   아예 없었다**(실측 2026-10-10: `goals·assists·rating·age·height·injury` 뿐) —
   그래서 어제 설계는 *"능력치를 자리 글자로 만들자"* 였다. 🔴 만들 필요가 없다.

## 🔴 잠금 넷
  ① **수는 안 넘긴다** — 문턱으로 `강점/보통/약점` 글자를 만들고 그것만 준다.
     문턱은 `config/ability.yaml` 이 든다(코드에 박지 않는다).
  ② **대상을 고른다** — 선수 한 명이 **2.09초·880KB** 다(실측). 교체 짝과
     핵심 결장만 받고 상한(`MAX_PLAYERS`)을 둔다. 22명을 다 받지 않는다.
  ③ **이름으로 찾지 않는다** — 열쇠는 `Player.pid` 다(동명이인·표기 변형이
     있다 · 어제 `Sohel Rana` 로 선발을 결장 처리한 그 병).
  ④ **못 받은 것은 이름으로 남긴다**(#3) — 번호가 없다 / 페이지를 못 받았다 /
     `traits` 가 비었다 / 상한에 걸렸다를 **갈라서** 적는다.

⚠️ 이 파일은 **갈래를 만들지 않는다.** 능력치는 ⑤-b2 의 **재료**이고, 변수는
   기존 갈래(`수비 라인`·`측면 집중`·`중원 수싸움`…)가 그대로 낸다. 그 변수가
   충돌하면 ⑤-b3 가 판정한다(사용자 지시의 *"교차검증 → 변수를 움직인다"*).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 🔴 ② **받을 선수 수 상한** — 한 명이 2.09초다(실측). 교체 짝 + 핵심 결장.
MAX_PLAYERS = 6
#: 🔴 ② 한 팀에서 받을 수 — 양 팀이 고르게 들어가게 가른다
MAX_PER_SIDE = 3
#: 🔴 ① 문턱 표가 사는 곳(코드에 박지 않는다)
CONF = "config/ability.yaml"
#: 🔴 ④ 능력치를 못 받은 사유 머리글자 — 카드·사유에 그대로 간다
NONE_MARK = "⬜"

_CUTS: dict | None = None


def _load() -> dict:
    """🔴 표를 읽는 곳은 **하나**다 — `config/ability.yaml`(#1 사본 금지).

    ⚠️ 한 번 읽고 기억한다. 없으면 **빈 꼴**이고 부르는 쪽이 그 사실을 적는다.
    """
    global _CUTS
    if _CUTS is None:
        import pathlib

        import yaml
        p = pathlib.Path(CONF)
        _CUTS = (dict(yaml.safe_load(p.read_text(encoding="utf-8")) or {})
                 if p.exists() else {})
    return dict(_CUTS)


def cuts() -> tuple[float, float]:
    """🔴 `(강점 문턱, 약점 문턱)` — 표가 없으면 **쓰지 않는다**(빈 꼴).

    ⚠️ 여기서 수를 짓지 않는다 — `config/ability.yaml` 이 원본이다. 표가 없으면
       `(0, 0)` 이고 부르는 쪽이 *"문턱 표가 없다"* 를 사유로 적는다(#3).
    """
    box = _load()
    try:
        return float(box["strong"]), float(box["weak"])
    except (KeyError, TypeError, ValueError):
        return 0.0, 0.0


def word_of(value: float) -> str:
    """🔴🔴 ① **백분위 → 글자**. 수는 여기서 멈춘다(모델은 글자만 본다).

    🔴 `강점`(문턱 위) · `약점`(문턱 아래) · `보통`(사이). ⚠️ 문턱 표가 없으면
       **빈 글자**다 — 그러면 부르는 쪽이 그 사실을 적는다(지어내지 않는다).
    """
    strong, weak = cuts()
    if not (strong and weak):
        return ""
    got = float(value)
    return "강점" if got >= strong else ("약점" if got <= weak else "보통")


def _pids_of(xi) -> dict[str, int]:
    """🔴 그 XI 의 `{이름: 선수 번호}`. ⚠️ 번호 없는 선수는 **안 담는다**(③)."""
    out: dict[str, int] = {}
    for one in list(getattr(xi, "lineup", None) or []):
        nm = str(getattr(one, "name", "") or "").strip()
        pid = getattr(one, "pid", None)
        if nm and isinstance(pid, int):
            out[nm] = pid
    return out


def pid_book(facts, ref) -> dict[str, int]:
    """🔴🔴 **이름 → 선수 번호** 한 권. 오늘 XI · 평소 XI · 직전 XI 를 다 모은다.

    🔴 빠진 선수는 **오늘 XI 에 없다** — 그 번호는 `past_xi`·`last_xi` 에서
       온다(평소 XI 가 그 선수를 들고 있다). ⚠️ 그래서 세 칸을 다 본다.
    """
    out: dict[str, int] = {}
    for side in ("home", "away"):
        key = str(getattr(ref, side, "") or "")
        out.update(_pids_of(dict(getattr(facts, "xi", None) or {}).get(key)))
        out.update(_pids_of(dict(getattr(facts, "last_xi", None) or {})
                            .get(key)))
        for one in list(dict(getattr(facts, "past_xi", None) or {})
                        .get(key) or []):
            out.update(_pids_of(one))
    return out


def targets(ref, facts, plan) -> tuple[list[dict], str]:
    """🔴🔴 ② **누구를 받을까** — `(대상 목록, 사유)`.

    받는 사람은 둘뿐이다:
      · **교체 짝** — `strategy` 가 센 `swap` 사실(`빠짐 [A] · 들어옴 [B]`)
      · **핵심 선수** — `key_player` 사실(명단 제외·벤치)
    🔴 자리(`swap`)로 묶어 **빠진 쪽과 들어온 쪽을 짝으로** 넘긴다 — 그래야
       모델이 *"무엇이 무엇으로 바뀌었나"* 를 읽는다(사용자 지시의 그 뜻).
    ⚠️ 대상은 **`plan.facts` 가 이미 센 글자**에서만 나온다 — 여기서 XI 를 다시
       비교하지 않는다(#1 사본 금지 · `strategy._swaps` 가 그 자리다).
    """
    book = pid_book(facts, ref)
    rows: list[dict] = []
    said: list[str] = []
    n_side: dict[str, int] = {"home": 0, "away": 0}
    for rid, one in dict(getattr(plan, "facts", None) or {}).items():
        row = dict(one) if isinstance(one, dict) else {}
        kind = str(row.get("kind") or "")
        side = str(row.get("side") or "")
        text = str(row.get("text") or "")
        if kind not in ("swap", "key_player"):
            continue
        if n_side.get(side, 0) >= MAX_PER_SIDE:
            said.append(f"{NONE_MARK} `{rid}` — 한 팀 상한 {MAX_PER_SIDE}명을 넘겼다")
            continue
        # ══════════════════════════════════════════════════════════
        # 🔴🔴 **이름을 글에서 파싱하지 않는다** — 명부에서 **찾는다**
        # ══════════════════════════════════════════════════════════
        #
        #  ⚠️ 실측 2026-10-17: 처음 판은 `'([^']{2,40})'` 로 따옴표 사이를
        #     긁었다 — 한 글자 이름(`'A'`)을 건너뛰고 **그 사이 글자**
        #     (`] · 들어옴 [`)를 이름으로 잡았다. 🔴 꾸민 글을 되파싱하는 것은
        #     언제나 이렇게 깨진다(글 모양이 바뀌면 또 깨진다).
        #  🔴 그래서 뒤집는다 — **아는 선수 이름이 그 글에 있나**를 본다.
        #     명부(`pid_book`)가 권위이고, 거기 없는 이름은 애초에 받을 수 없다.
        #  ⚠️ **긴 이름부터** 본다 — 짧은 이름이 긴 이름 안에 들어 있으면
        #     (`Rana` ⊂ `Sohel Rana`) 긴 쪽 하나로 센다(어제 그 병의 사촌).
        got: list[tuple[str, int]] = []
        taken = ""
        for nm in sorted(book, key=len, reverse=True):
            if nm and nm in text and nm not in taken:
                got.append((nm, book[nm]))
                taken += f"|{nm}"
        if not got:
            said.append(f"{NONE_MARK} `{rid}` — 그 글에 **아는 선수 이름이 "
                        f"없다**(명부 {len(book)}명)")
            continue
        rows.append({"id": rid, "side": side, "kind": kind, "text": text,
                     "players": got})
        n_side[side] = n_side.get(side, 0) + len(got)
        if sum(len(r["players"]) for r in rows) >= MAX_PLAYERS:
            said.append(f"{NONE_MARK} 전체 상한 {MAX_PLAYERS}명에서 멈췄다")
            break
    if not rows:
        return [], (f"{NONE_MARK} 받을 선수가 없다(교체·핵심 선수 사실 0건)"
                    + (" · " + " · ".join(said[:3]) if said else ""))
    return rows, (f"대상 {sum(len(r['players']) for r in rows)}명 / "
                  f"자리 {len(rows)}곳"
                  + (" · " + " · ".join(said[:3]) if said else ""))


async def fetch(net, rows: list[dict], *, clock=None
                ) -> tuple[dict[str, dict], str]:
    """🔴🔴 ② 선수 페이지를 받아 **능력치만** 꺼낸다. `({이름: 묶음}, 사유)`.

    🔴 통로는 **기존 `net.get`** 이다(robots·캐시·UA 를 그것이 지킨다) —
       새 fetch 경로를 만들지 않는다.
    ⚠️ 한 명이 **2.09초**다(실측). 그래서 카드 상한(`clock`)이 바닥이면 **그
       자리에서 멈추고** 사유를 남긴다(#3 · 조용히 적게 받지 않는다).
    ⚠️ 실패는 네 가지로 **갈라서** 적는다 — 번호가 없다 / 못 받았다 /
       `traits` 가 비었다 / 시간 상한.
    """
    from app.collect import fotmob as _fm
    out: dict[str, dict] = {}
    said: list[str] = []
    n_dead = n_empty = 0
    for row in list(rows or []):
        for nm, pid in list(row.get("players") or []):
            if nm in out:
                continue
            if clock is not None and getattr(clock, "over", lambda: False)():
                said.append(f"{NONE_MARK} **카드 상한**을 넘겨 멈췄다"
                            f"(받은 것 {len(out)}명)")
                return out, " · ".join(said)
            url = _fm.player_url(pid)
            if not url:
                said.append(f"{NONE_MARK} `{nm}` 번호가 꼴이 아니다({pid!r})")
                continue
            try:
                page = await net.get(url)
            except Exception as exc:                        # noqa: BLE001
                n_dead += 1
                said.append(f"{NONE_MARK} `{nm}` 못 받았다({exc!r:.40})")
                continue
            title, items = _fm.traits_of(_fm.payload(page.text) or {})
            if not items:
                n_empty += 1
                said.append(f"{NONE_MARK} `{nm}` 능력치 칸이 비었다")
                continue
            out[nm] = {"pid": pid, "group": title, "items": items}
    head = f"능력치 **{len(out)}명**"
    if n_dead:
        head += f" · 🔴 못 받은 선수 {n_dead}명"
    if n_empty:
        head += f" · 🔴 능력치 빈 선수 {n_empty}명"
    return out, head + (" · " + " · ".join(said[:4]) if said else "")


def said_of(rows: list[dict], box: dict[str, dict], *, ref=None) -> list[str]:
    """🔴🔴 ① **모델에게 줄 글자** — 자리별로 *빠진 쪽 ↔ 들어온 쪽*을 짝 지어
    `강점/보통/약점` 으로 적는다. `수를 넣지 않는다.`

    꼴(실측 재료로 만든 보기):

    ```
    - away `FW` 자리 — 빠짐 `Duk` · 들어옴 `Zaldívar`
        `Duk` [공격형 MF/윙 비교] 공중볼 **강점** · 수비 행동 **강점** · …
        `Zaldívar` [같은 묶음] 찬스 창출 **강점** · 공중볼 **약점** · …
    ```

    ⚠️ **비교 묶음이 다르면 그 사실을 적는다** — 골키퍼와 윙은 **다른 지표**로
       재므로 나란히 놓고 *"누가 더 세다"* 고 말할 수 없다(출처가 그렇게 준다).
    ⚠️ 못 받은 선수는 `⬜ 능력치 없음` 으로 **이름을 남긴다**(#3).
    """
    out: list[str] = []
    for row in list(rows or []):
        side = str(row.get("side") or "")
        nm_side = (str(getattr(ref, f"{side}_name", "") or "") if ref else "") \
            or side
        out.append(f"- {nm_side} — {str(row.get('text') or '')[:90]}")
        for nm, _pid in list(row.get("players") or []):
            one = dict(box.get(nm) or {})
            if not one:
                out.append(f"    `{nm}` {NONE_MARK} 능력치 없음")
                continue
            said = " · ".join(
                f"{x['title']} **{word_of(x['value']) or '등급 못 냄'}**"
                for x in list(one.get("items") or [])[:6])
            out.append(f"    `{nm}` [{one.get('group') or '비교 묶음 미상'}]"
                       f" {said}")
    return out


# ══════════════════════════════════════════════════════════════════════
# 🔴🔴 **전술 갈래를 능력치로 가른다** — 사용자 지시 2026-10-17
# ══════════════════════════════════════════════════════════════════════
#
#  > 선발 명단·후보명단이 들어오면 **그 선수들의 능력치로 변수를 결정**하게
#  > 한다 … 전술에 관련해서는 … **변수에 그렇게 들어가야 한다**
#
#  ⚠️ 실측 2026-10-17(가시와 vs 나고야): ⑤-b3 1단이 `중원 수싸움` 을
#     **머릿수**(`3-4-2-1` → 4 ↔ `4-3-3` → 3)로 갈랐다. 선수가 누구든 수만
#     같으면 같은 답이 나온다.
#  🔴 그래서 **누가 서 있느냐**로 가린다 — 자리에 맞는 선수들의 백분위 평균.
#     ⚠️ 백분위는 **그 포지션군 대비**이므로(출처가 묶음을 고른다) 같은 자리
#        끼리만 견준다. 지표·자리·문턱은 **표가 든다**(`config/ability.yaml`).


def branch_table() -> dict:
    """🔴 갈래 → `{pos, flank, traits, why}` 표. 없으면 **빈 꼴**이다."""
    return dict(_load().get("branches") or {})


def branch_gap() -> float:
    """🔴 두 팀 평균 백분위 차 문턱 — 표가 든다. 없으면 **0**(안 가린다)."""
    try:
        return float(_load().get("branch_gap") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def branch_min() -> int:
    """🔴 한쪽 최소 인원 — 이보다 적으면 평균이 한 사람에 휘둘린다."""
    try:
        return int(_load().get("branch_min") or 0)
    except (TypeError, ValueError):
        return 0


def squad_cap() -> int:
    """🔴 한 팀에서 능력치를 받을 **선수 수 상한**(선발 + 벤치)."""
    try:
        got = int(_load().get("squad_cap_per_side") or 0)
    except (TypeError, ValueError):
        got = 0
    return got if got > 0 else 11


def squad_of(facts, ref, side: str) -> tuple[list[dict], str]:
    """🔴🔴 그 팀의 **선발 + 벤치** — `([{name,pid,pos,flank,bench}], 사유)`.

    🔴 재료는 `XI.lineup`(자리·측면·번호)과 `XI.bench` 다 — 둘 다 `s2_facts`
       가 fotmob 에서 싣는다. ⚠️ 번호(`pid`)가 없는 선수는 **안 담는다**(선수
       페이지를 못 연다) — 그 수를 사유에 적는다(#3).
    """
    from app.core.schema import XI                          # noqa: F401
    box = dict(getattr(facts, "xi", None) or {})
    key = str(getattr(ref, side, "") or "")
    one = box.get(key)
    if one is None:
        return [], f"{NONE_MARK} `{side}` XI 가 없다"
    got: list[dict] = []
    n_nopid = 0
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **벤치는 이름만 온다** — 실측 2026-10-17
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ `XI.bench` 는 **`list[str]`**(이름 글자)이고 `XI.lineup` 만
    #     `Player`(자리·측면·**번호**)다. 번호가 없으면 선수 페이지를 못 연다.
    #  🔴 그래서 지금 능력치를 받는 것은 **선발뿐**이다 — 그 사실을 사유에
    #     적는다(#3 조용한 0 금지). ⚠️ 카드의 InfoQ 가 이미 *"벤치 id 확정"*
    #     을 빠진 칸으로 세고 있다 — 그 칸이 차면 벤치도 받는다.
    for p in list(getattr(one, "lineup", None) or []):
        pid = getattr(p, "pid", None)
        nm = str(getattr(p, "name", "") or "").strip()
        if not nm:
            continue
        if not isinstance(pid, int) or pid <= 0:
            n_nopid += 1
            continue
        got.append({"name": nm, "pid": pid,
                    "pos": str(getattr(p, "pos", "") or ""),
                    "flank": str(getattr(p, "flank", "") or ""),
                    "bench": False})
    n_bench = len(list(getattr(one, "bench", None) or []))
    said = f"{side} 선발 **{len(got)}명**"
    if n_bench:
        said += (f" · {NONE_MARK} 벤치 {n_bench}명은 **이름만 와서** 능력치를 "
                 f"못 받는다(`XI.bench` 에 번호가 없다)")
    if n_nopid:
        said += f" · {NONE_MARK} 번호 없는 선발 {n_nopid}명"
    if not got:
        return [], said
    return got[:squad_cap()], said


async def squad_fetch(net, facts, ref, *, clock=None
                      ) -> tuple[dict[str, dict], str]:
    """🔴🔴 **양 팀 선발+벤치의 능력치**. `({이름: 묶음}, 사유)`.

    ⚠️ 한 명이 ~2초다 — 팀당 18명이면 두 팀 **~72초**다. 카드 상한
       (`clock`)이 바닥이면 `fetch` 가 그 자리에서 멈추고 사유를 남긴다.
    """
    rows: list[dict] = []
    said: list[str] = []
    for side in ("home", "away"):
        one, why = squad_of(facts, ref, side)
        said.append(why)
        if one:
            rows.append({"players": [(x["name"], x["pid"]) for x in one]})
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **결장자도 받는다** — 사용자 지시 2026-10-18(*"전부 고쳐라"*)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측(오스틴 vs 밴쿠버): `datavars` 의 A2(결장 품질 손실)가 두 팀 다
    #     *"⬜ 빠진 N명의 백분위를 못 받았다(선수 페이지를 안 열었다)"* 였다 —
    #     🔴 이 함수가 **오늘 선발만** 받아 결장자가 `box` 에 아예 없었다.
    #  🔴 번호는 `pid_book`(오늘 XI · 평소 XI · 직전 XI)이 든다 — 빠진 선수의
    #     번호는 **과거 선발**에서 온다. ⚠️ 번호가 없으면 **안 받는다**(#3).
    said_gone: list[tuple] = []
    book = pid_book(facts, ref)
    for side in ("home", "away"):
        key = str(getattr(ref, side, "") or "")
        for m in list(dict(getattr(facts, "missing", None) or {}).get(key)
                      or []):
            nm = str(getattr(m, "name", "") or "").strip()
            pid = book.get(nm)
            if nm and isinstance(pid, int):
                said_gone.append((nm, pid))
    if said_gone:
        rows.append({"players": said_gone})
        said.append(f"결장자 {len(said_gone)}명도 받는다(A2 재료)")
    else:
        said.append(f"{NONE_MARK} 결장자 번호가 없다 — A2 는 안 돈다")
    if not rows:
        return {}, " · ".join(said)
    box, why_f = await fetch(net, rows, clock=clock)
    return box, " · ".join([*said, why_f])


def _pct_of(one: dict, traits: list[str]) -> float | None:
    """🔴 그 선수의 **고른 지표 평균 백분위**. 하나도 없으면 `None`."""
    items = list(dict(one or {}).get("items") or [])
    want = {str(x) for x in (traits or [])}
    got = [float(x.get("value")) for x in items
           if str(x.get("key") or "") in want
           and isinstance(x.get("value"), (int, float))]
    return (sum(got) / len(got)) if got else None


def side_pct(facts, ref, side: str, box: dict, rule: dict
             ) -> tuple[float | None, int, str]:
    """🔴🔴 그 팀에서 **그 자리 선수들의 평균 백분위**. `(값, 인원, 사유)`.

    🔴 자리는 표가 고른다(`pos`·`flank`) — `flank` 가 빈 목록이면 **안 가린다**.
    ⚠️ **선발만** 센다(벤치는 오늘 안 뛴다) — 벤치 능력치는 모델이 읽는 글자로
       만 간다(교체 짝 가설). 그 사실을 사유에 적는다.
    """
    rows, why = squad_of(facts, ref, side)
    if not rows:
        return None, 0, why
    want_pos = {str(x) for x in (rule.get("pos") or [])}
    want_fl = {str(x) for x in (rule.get("flank") or [])}
    traits = [str(x) for x in (rule.get("traits") or [])]
    got: list[float] = []
    n_seen = 0
    for p in rows:
        if p["bench"]:
            continue
        if want_pos and p["pos"] not in want_pos:
            continue
        if want_fl and p["flank"] not in want_fl:
            continue
        n_seen += 1
        pct = _pct_of(box.get(p["name"]) or {}, traits)
        if pct is not None:
            got.append(pct)
    if not got:
        return None, n_seen, (f"{NONE_MARK} 그 자리 선발 {n_seen}명의 능력치를 "
                              f"못 받았다")
    return sum(got) / len(got), len(got), f"{len(got)}명"


def judge_branch(kind: str, facts, ref, box: dict) -> tuple[str, str]:
    """🔴🔴 **전술 갈래를 능력치로 가린다** — `(부등호, 사유)`.

    🔴 빈 부등호면 **안 가려졌다**(2단으로 간다). 사유는 늘 돌려준다(#3).
    ⚠️ `>` 는 **홈이 낫다**는 뜻이다(⑤-b3 의 그 약속과 같다).
    """
    rule = dict(branch_table().get(str(kind or "")) or {})
    if not rule:
        return "", f"{NONE_MARK} `{kind}` 는 능력치 표에 없다(`{CONF}`)"
    if not box:
        return "", f"{NONE_MARK} 능력치를 **한 명도 못 받았다**"
    h, nh, why_h = side_pct(facts, ref, "home", box, rule)
    a, na, why_a = side_pct(facts, ref, "away", box, rule)
    said_t = "·".join(str(x) for x in (rule.get("traits") or []))
    head = f"능력치 `{said_t}` — "
    if h is None or a is None:
        return "", head + f"{NONE_MARK} 못 쟀다(홈 {why_h} · 원정 {why_a})"
    low = branch_min()
    if nh < low or na < low:
        return "", (head + f"홈 {nh}명 ↔ 원정 {na}명 — 한쪽이 **{low}명 미만**"
                           f"이라 평균이 한 사람에 휘둘린다(안 가린다)")
    said = (head + f"홈 **{h:.2f}** ({nh}명) ↔ 원정 **{a:.2f}** ({na}명)"
            f" · {rule.get('why') or ''}")
    gap = branch_gap()
    if abs(h - a) < gap:
        return "", said + f" — 차이가 {gap:g} 미만이다(안 가린다)"
    return (">" if h > a else "<"), said + f" → `{'>' if h > a else '<'}`"
