"""🔴🔴 **v6 렌더러 — `Card` 하나만 받는다**(§3 · §5 render).

블록 순서는 `docs/fable/output_spec.md` 의 **열 블록**이다(사용자가 두 번 보낸
출력에서 블록과 순서만 뽑은 규격). 🔴 그 표를 여기 베끼지 않는다 — 블록 제목만
쓰고, 무엇이 들어가는지는 규격이 든다.

⚠️ 실사고 2026-10-06: 옛 렌더러가 폐기 줄을 dict 로 알아 `AttributeError: 'tuple'
   object has no attribute 'get'` 로 **카드 전체를 잃었다**. 🔴 v6 는 받는 것이
   `Card` 한 타입이고 전부 `frozen` 이라 그 꼴 차이가 **존재하지 않는다**.
🔴 **카드는 항상 나온다** — 비어 있는 블록도 *왜 비었나*를 적는다(#3).
"""
from __future__ import annotations

from app.core.schema import Card, Variable

#: 🔴 블록 제목 — 규격의 열 블록. ⚠️ 번호를 건너뛰지 않는다(불변식 1).
TITLES: tuple[str, ...] = (
    "자료 한계 고백", "기준 XI", "결장", "폼", "기준 전력 (데이터)", "경우의 수",
    "뒤집는 변수", "팀별 가설 + 무너지는 조건", "시나리오", "확률 세 열",
    "보드 대입", "결론", "방향 판정", "방아쇠")

#: 🔴 규격 번호 — 축구 완성 지시서 §5 가 **2b·3b** 를 새 블록으로 더했다.
#   ⚠️ 번호를 다시 매기지 않는다(사용자가 블록 번호로 말한다) — `2b`·`3b` 로 적는다.
#   🔴 네 층 지시서 §8 이 **3c(기준 전력)**·**7b(확률 세 열)** 를 더했다 —
#      블록 순서는 그대로 두고 **두 블록만** 끼운다(그 문서가 그렇게 못 박았다).
NUMBERS: tuple[str, ...] = ("1", "2", "2b", "3", "3c", "3b", "4", "5", "6",
                            "7b", "7", "8", "9", "10")


def layer1_text(card: Card, *, buttons: bool = True) -> str:
    """🔴🔴 **1겹 카드**(사용자 지시 2026-10-09(3차) §1) — 글은 `layer1` 이 짠다.

    🔴 여기 베끼지 않는다(#1) — 순서·문구·상한이 **한 곳**(`app/core/layer1.py`)에
       있어야 지시가 바뀔 때 한 번만 고친다.
    ⚠️ 깊은 카드는 `card_text` 그대로다 — 버튼 `📖 자세히` 가 그것을 낸다.
    """
    from app.core import layer1
    return layer1.text(card, buttons=buttons)


def card_text(card: Card, *, debug: bool = False) -> str:
    """🔴 카드 전문. ⚠️ 블록이 **늘 전부 있다** — 비면 사유가 들어간다.

    🔴 축구 완성 지시서 §5 가 블록 **2b(결장)**·**3b(경우의 수)** 를 더했다.
    """
    out: list[str] = [_head(card)]
    # 🔴🔴 **§11 역배·보호 줄**(지시서 2026-10-12(둘째) · 즉시 적용) — **1겹 맨 위**.
    #  🔴 왜 여기인가: 실사고 둘에서 시장도 봇도 **강팀만** 봤다. 같은 격자에서
    #     나온 약팀 쪽 줄을 **머리 바로 아래** 두면 그 확률이 확신으로 안 읽힌다.
    #  ⚠️ 확률·등급을 **안 바꾼다**(계약 U1 이 수의 출처를 센다).
    said_dog = _underdog_line(card)
    if said_dog:
        out.append("\n" + said_dog)
    bodies = (_b1(card), _b2(card), _b2b(card), _b3(card), _b3c(card),
              _b3b(card), _b4(card), _b5(card), _b6(card), _b7b(card),
              _b7(card), _b8(card), _b9(card), _b10(card))
    for num, title, body in zip(NUMBERS, TITLES, bodies, strict=True):
        out.append(f"\n**{num}. {title}**\n{body}")
        # 🔴🔴 §3-4 — **🆕 새 사실(72시간)** 은 결장 블록(2b) 바로 뒤다
        #    ⚠️ 왜 거기인가: 새 사실의 대부분이 **결장·복귀**라 같이 읽힌다.
        if num == "2b":
            out.append("\n" + new_facts_block(card))
            # 🔴🔴 ② **손실 표**(사용자 지시 2026-10-11) — 새 사실 0건의 까닭이
            #    *"버린 것: identity_mismatch 7건"* 한 줄로만 적혀 있었다
            out.append("\n" + loss_table(card))
            # 🔴🔴 §4 — **전략 블록**은 기준 XI·결장 바로 뒤다(같은 명단 얘기다)
            out.append("\n" + strategy_long(card))
            # 🔴🔴 §6 — 전술 예측은 전략 블록 바로 뒤다(같은 명단 얘기다)
            out.append("\n" + tactic_long(card))
            # 🔴🔴 §5(셋째) — **상성 자세히**는 그 예측의 재료다(바로 뒤)
            out.append("\n" + matchup_long(card))
            # 🔴🔴 **🔢 변수**(상성 엔진 V-4) — 축·검증·가설의 재료가 전부 여기다
            out.append("\n" + vars_long(card))
            # 🔴🔴 **상성·검증·분포·적합**(상성 엔진 §3 긴 카드)
            out.append("\n" + matchup_report_long(card))
            # 🔴🔴 **상성에서 나온 확률**(사용자 질문 2026-10-11) — 축 바로 뒤다
            out.append("\n" + prob_long(card))
            out.append("\n" + score_grid(card))
            out.append("\n" + verify_long(card))
            # 🔴🔴 **반증 표**(지시서 2026-10-12 ⑯) — 검증 바로 뒤다(같은 얘기다)
            out.append("\n" + breaks_long(card))
            out.append("\n" + fit_long(card))
            # 🔴🔴 **가설 검증표**(순서 재편 §4-5) — 최종 평의 재료다(바로 앞)
            out.append("\n" + check_long(card))
            # 🔴🔴 §4(넷째) — **최종 평 자세히**(근거 id · 원 사실 · 검열 결과)
            out.append("\n" + say_long(card))
        # 🔴 **결론 바로 아래**가 논평 자리다(지시 ④)
        if num == "8":
            out.append(_comment(card, debug=debug))
    return "\n".join(out)


def debug_text(card: Card) -> str:
    """🔴 긴 카드(`/디버그`) — 같은 블록에 **근거 번호·양상 비중**이 붙는다(지시 ④)."""
    return card_text(card, debug=True)


def warn_lines(card: Card) -> list[str]:
    """🔴🔴 §2·§3 — 카드 머리의 **경고 줄들**(없으면 빈 목록).

    | 언제 | 무엇 |
    |---|---|
    | 대회를 못 알아봤다 | `🔴 대회를 알아보지 못했다 — {받은 표기}` |
    | 자료가 얇다 | `🔴 자료 부족 카드 — 판단에 쓰지 말 것` |

    🔴 **판정을 하지 않는다** — 세는 규칙은 `thin_card` 하나이고 여기서는 글만 짓는다.
    """
    out: list[str] = []
    if not comp_key(card):
        out.append(f"{_comp_mod().UNKNOWN_HEAD} — 받은 표기 "
                   f"`{card.match.competition or '없음'}` · 기준·경우의 수·리그 "
                   f"평균이 **비었다** · 등급은 전부 **보류**")
    # 🔴🔴 **L2 표시**(지시 2026-10-12 2번) — 재현에서 **확률 경로에서 뺀 값**을
    #    머리에 적는다. ⚠️ 표시 없이 빼면 사람이 *"왜 수가 다르지"* 를 못 찾는다.
    from app import cassette as _cas
    from app.core import asof as _asof
    said_l2 = _asof.said_of(replay=_cas.mode() == _cas.REPLAY)
    if said_l2:
        out.append(said_l2)
    # 🔴🔴 **[3c] 되돌려 다시 센 카드**(지시서 2026-10-12) — 머리에 찍는다
    if str(getattr(card, "break_rerun", "") or ""):
        out.append(f"🔁 **반증으로 재계산** — {card.break_rerun} · 바뀐 것: "
                   f"상성·확률·등급(이 카드가 **뒤**다)")
    said, why = thin_card(card)
    if said:
        out.append(f"🔴 **자료 부족 카드 — 판단에 쓰지 말 것**({why})")
    # 🔴🔴 §2 마지막 줄 — 블록 3 의 셋이 빠지면 **머리표**다(지시 (5차) ②)
    # ⚠️ `thin_card` 가 걸렸어도 **함께 적는다** — 무엇이 없는지는 다른 말이다
    #    (실측: thin 문구가 블록 3 문구를 가려 사람이 셋 중 무엇이 빠졌는지 못 봤다)
    gaps3 = block3_gaps(card)
    if gaps3:
        out.append(f"🔴 **자료 부족 카드 — 판단에 쓰지 말 것**"
                   f"(블록 3 에 {'·'.join(gaps3)} 가 없다)")
    # 🔴🔴 §4 — **자동 등록 리그면 그 상태를 카드가 적는다**(2026-10-10)
    #
    #  > 각 경기마다: 자동 등록 파일 · 검색 언어 · 라인업 출처 · **기준 상태**.
    #
    #  ⚠️ 손 표에 있는 리그(기준 모델이 달린 리그)는 이 줄이 없다 — 그것이
    #     *"자동 등록으로 열린 리그"* 와 다른 상태임을 사람이 알아야 한다.
    key = comp_key(card)
    if key.startswith("league:fotmob"):
        from app.core import autoleague
        out.append(autoleague.line(key))
    # 🔴🔴 §1-3 — **보드로 만든 경기**는 공식 일정 출처가 없다(2026-10-10 재작성)
    #
    #  > 0개인데 보드가 있다 → 보드로 경기를 만든다(`source=user_board`): 대회명은
    #  > 보드 표기 그대로, **공식 일정 출처 없음 표시**, 분석은 그대로 진행.
    #
    #  🔴 신호는 **경기 열쇠**다(`user_board-…`) — `findgame._board_row` 가 그
    #     접두를 넣는다. ⚠️ 새 DB 칸을 만들지 않았다(열쇠가 이미 말한다).
    if str(card.match.id or "").split(":")[-1].startswith("user_board-"):
        out.append("🟡 **보드로 만든 경기** — 공식 일정 출처 **없음**(대회명·시각은 "
                   "보드 표기 그대로다) · 기준 모델·리그 평균이 **비었다**")
    return out


def _comp_mod():
    from app.core import competition
    return competition


def comp_key(card: Card) -> str:
    """🔴 그 카드의 `competition_key` — 못 알아봤으면 `""`.

    ⚠️ `BaseProb.comp_kind` 에 **이미 적혀 있다**(s2b 가 넣는다) — 다시 판정하지
       않는다(판정점은 `competition.py` 하나다).
    """
    return str(card.base_prob.comp_kind or "")


def thin_card(card: Card) -> tuple[bool, str]:
    """🔴🔴 §3 **빈 카드 감지** — `(얇은가, 사유)`.

    > 변수 **2개 이하** + 기준 **없음** + 폼·XI·순위 중 **둘 이상 없음**.

    🔴 세 조건이 **모두** 맞아야 한다 — 하나만으로는 흔한 일이고, 셋이 겹치면
       카드가 말할 것이 없다는 뜻이다.
    """
    n_var = len(card.variables or [])
    if n_var > 2:
        return False, ""
    if card.base_prob.probs is not None:
        return False, ""
    miss = []
    if not (card.facts.xi or {}):
        miss.append("XI")
    if not (card.facts.recent or {}):
        miss.append("폼")
    if not ((card.facts.standings or {}).get("group") or {}).get("rows"):
        miss.append("순위")
    if len(miss) < 2:
        return False, ""
    return True, (f"변수 {n_var}개 · 기준 없음 · " + "·".join(miss) + " 없음")


#: 🔴 §2 마지막 줄 — 블록 3 이 들어야 하는 셋(사용자 지시 2026-10-09(5차))
#  `recent`(최근 5경기) · `standings.team_totals`(경기당 총골) · `key_players`
BLOCK3_NEED: tuple[tuple[str, str], ...] = (
    ("폼(최근 5경기)", "recent"),
    ("경기당 총골", "team_totals"),
    ("핵심 선수", "key_players"))


def block3_gaps(card: Card) -> list[str]:
    """🔴🔴 §2 — 블록 3 의 **셋 중 빠진 것**(없으면 빈 목록).

    > 카드 블록 3 에 이 셋이 빠지면 *"자료 부족 카드"* 머리표.

    🔴 실사고 2026-10-09(가시마–감바): 폼이 **0건**이라 득점 흐름 변수가 하나도
       없었는데 카드는 아무 표시 없이 나갔다.
    """
    std = dict(card.facts.standings or {})
    out: list[str] = []
    for label, key in BLOCK3_NEED:
        got = (card.facts.recent if key == "recent" else std.get(key))
        if not got:
            out.append(label)
    return out


def _host_of(said: object) -> str:
    """🔴 주소에서 **호스트**만. 주소가 아니면 그 글자를 그대로(`user_capture`)."""
    one = str(said or "").strip()
    if "://" not in one:
        return one
    got = one.split("/")
    return got[2] if len(got) > 2 else one


def _underdog_line(card: Card) -> str:
    """🔴🔴 **U2** — 강팀이 있으면 **모든 카드**가 그 줄을 낸다(§11).

    🔴 수는 ⑯ 이 만든 **스코어 격자 하나**에서 온다. 격자가 없으면(확률 미산출)
       그 사실을 적는다 — 조용히 빼지 않는다(#3).
    """
    from app.core import probfloor as _pf
    from app.core import underdog as _ud
    box = dict(getattr(card, "matchup", None) or {})
    sim = dict(box.get("sim") or {})
    lam = dict((box.get("prob") and getattr(box["prob"], "lam", None))
               or sim.get("lam") or {})
    if not lam:
        said = dict(box.get("sim") or {})
        lam = {"home": said.get("lam_home"), "away": said.get("lam_away")}
    if not lam.get("home") or not lam.get("away"):
        return ("🔁 **역배·보호 줄 없음** — ⑯ 이 λ 를 못 만들었다"
                "(확률이 없으면 그 줄도 없다)")
    rho = float(dict(box.get("coef") or {}).get("rho") or 0.0)
    grid = _pf.score_grid(lam_home=float(lam["home"]),
                          lam_away=float(lam["away"]), rho=rho)
    got = _ud.read(grid, home_name=card.match.home_name,
                   away_name=card.match.away_name)
    return "🔁 " + _ud.line(got)


def _head(card: Card) -> str:
    from app import timefmt
    m = card.match
    # 🔴 표시만 KST 다(절대규칙 2) — 꼴은 `timefmt.kst_label` 하나가 든다(#1)
    head = (f"🏟 **{m.home_name} vs {m.away_name}** · {m.competition_short} · "
            f"{timefmt.kst_label(m.kickoff_utc)}")
    if m.openworld:
        # 🔴 **처음 보는 리그라는 것을 한눈에**(오픈월드 §4 표기)
        head += f"\n🌐 **오픈월드** — 리그: {m.competition} · 팀 열쇠 임시 발급"
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **못 알아본 대회·빈 카드는 머리에 찍는다**(지시 2026-10-09(4차) §2·§3)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 못 알아보면 **크게 실패**: 카드 머리에 *"🔴 대회를 알아보지 못했다 —
    #  > {받은 표기}"* · 그 상태로 등급은 전부 보류.
    #  > 빈 카드 감지: … 카드 머리에 *"자료 부족 카드 — 판단에 쓰지 말 것"*.
    #
    #  🔴 **조용히 나가지 않는다** — 실사고 2026-10-09(가시마–감바)는 변수 1개 ·
    #     기준 없음 · 폼·XI·순위 전무인 카드가 **아무 표시도 없이** 나간 일이다.
    # 🔴🔴 **§13 정보 품질** — 머리 줄에 적는다(지시서 2026-10-12(둘째) §13·§14).
    #  ⚠️ 확률은 안 바뀐다 — **등급만** 내린다(그 사실을 줄이 말한다).
    if card.infoq:
        head += ("\n📏 " + card.infoq
                 + (" → **등급 한 단계↓**"
                    if (card.infoq_score is not None
                        and int(card.infoq_score) <= 2) else ""))
    for line in warn_lines(card):
        head += f"\n{line}"
    c = card.cost
    head += (f"\n💵 ${c.usd:.4f} · 호출 {c.calls}회 · 출력 {c.out_tokens} "
             f"(추론 {c.reasoning_tokens})")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **확정 XI 전 안내**(사용자 지시 2026-10-06(7차) §7)
    # ══════════════════════════════════════════════════════════════════
    #
    # > 킥오프 **90분 이내**인데 XI 가 `confirmed` 가 아니면 카드 머리에
    # > *"확정 XI 전 — HH:MM KST 이후 /재분석"*.
    #
    # ⚠️ 그 시각은 **킥오프 60분 전**이다(확정 XI 는 보통 그때 나온다 · 축구 §2).
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **피드에 없는 경기면 보드를 달라고 한다**(사용자 지시 2026-10-07 ③)
    # ══════════════════════════════════════════════════════════════════
    #
    # > 피드에 경기가 없을 때(대표팀 친선 등): 카드 머리에
    # > *"시장 피드에 없는 경기 — 보드 캡처를 보내 달라"* 한 줄.
    if not card.market.probs and not card.user_market.probs:
        head += ("\n📋 **시장 피드에 없는 경기 — 보드 캡처를 보내 달라**"
                 "(보드가 없으면 등급을 못 붙인다)")
    # 🔴🔴 A-3 — `📋 라인업 {확정|예상|없음} · 출처 {이름} · {HH:MM}`
    if card.facts.xi:
        from app.core import lineups as _ln
        kinds = {str(v.state or "") for v in card.facts.xi.values()} - {""}
        # 🔴🔴 **주소가 아닌 출처도 있다** — ⚠️ 실사고 2026-10-11(스포팅 KC):
        #    사람이 준 캡처 XI 의 출처는 `user_capture` 라 `/` 가 없고,
        #    `split("/")[2]` 가 **IndexError 로 봇을 통째로 죽였다**(카드 0장).
        #    🔴 호스트를 못 뽑으면 **그 글자를 그대로** 쓴다(버리지 않는다 · #3).
        got_src = sorted({_host_of(getattr(v, "source_url", ""))
                          for v in card.facts.xi.values()
                          if str(getattr(v, "source_url", "") or "")})
        when = next((getattr(v, "fetched_at", None)
                     for v in card.facts.xi.values()
                     if getattr(v, "fetched_at", None)), None)
        # 🔴 상태 글자는 `layer1.xi_state` 하나가 정한다(사본 금지)
        #    ⚠️ 실사고 2026-10-10: 여기서 `kinds == {"확정"}` 로 비교했는데
        #       `XI.state` 는 **영어**(`confirmed`)라 **늘 `예상`** 이었다.
        from app.core import layer1 as _l1
        head += "\n" + _ln.status_line(
            state=_l1.xi_state(card),
            source=" · ".join(got_src) or "미상", when=when)
    said_xi = {v.state for v in (card.facts.xi or {}).values()}
    if said_xi and "confirmed" not in said_xi:
        from datetime import timedelta
        from app.triggers import XI_MINS
        # 🔴 그 수는 `triggers.XI_MINS` **하나**다 — 블록 10 방아쇠가 같은 수를 쓴다
        when = m.kickoff_utc - timedelta(minutes=XI_MINS)
        head += (f"\n⏳ **확정 XI 전** — {timefmt.kst_label(when)} 이후 `/재분석`"
                 f"(지금 XI 는 {'·'.join(sorted(said_xi))})")
    if card.changed:
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **재분석 — 바뀐 것**(축구 완성 지시서 §4-4): 카드 **맨 위**다
        # ══════════════════════════════════════════════════════════════
        #
        #  🔴 지시서 2026-10-11 **F1** — 확정 XI 로 다시 돌았으면 머리줄이
        #     *"🔁 **확정 XI 반영** — 바뀐 것: 상성 축(전→후)·확률(전→후)·
        #     등급(전→후)"* 이다. ⚠️ **확정이 아닐 때 그 말을 쓰지 않는다**
        #     (바뀐 것은 적되 "확정 XI 반영" 이라고는 안 한다 · #3).
        said_now = {str(getattr(v, "state", "") or "")
                    for v in (card.facts.xi or {}).values()}
        done = bool(said_now) and said_now <= {"confirmed"}
        head += (("\n\n🔁 **확정 XI 반영** — 바뀐 것: 상성 축(전→후)·"
                  "확률(전→후)·등급(전→후)\n" if done
                  else "\n\n🔁 **재분석 — 바뀐 것**\n")
                 + "\n".join(f"- {x}" for x in card.changed))
    return head


def _b1(card: Card) -> str:
    """블록 1 — 🔴 **이 블록이 비면 그것이 거짓이다.**

    🔴 §2 — 대회를 못 알아봤으면 *"기준·경우의 수·리그 평균이 비었다"* 를 이 블록
       **맨 위**에 적는다(사용자 지시 2026-10-09(4차) §2).
    """
    out: list[str] = []
    # 🔴🔴 §2 — **맨 위**다(아래 줄들보다 먼저 읽혀야 한다)
    if not comp_key(card):
        out.append(f"🔴🔴 **{_comp_mod().UNKNOWN_HEAD}** — 받은 표기 "
                   f"`{card.match.competition or '없음'}` → **기준(①)·경우의 수·"
                   f"리그 평균이 비었다**. 등급은 전부 **보류**이고, 이 표기는 "
                   f"운영자 알림으로 보냈다(표에 넣어야 한다)")
    said_thin, why_thin = thin_card(card)
    if said_thin:
        out.append(f"🔴🔴 **자료 부족 카드 — 판단에 쓰지 말 것**({why_thin})")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **XI 출처 없음**(사용자 지시 2026-10-09(6차) ⑤ 마지막 줄)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > K리그는 킥오프 1시간 전 공식 라인업이 나오는데 경기 페이지가 못 준다.
    #  > … **안 되면 "XI 출처 없음"을 블록 1 맨 위에.**
    #
    #  🔴 두 번째 출처를 **아직 못 붙였다** — `kleague.com` 은 JS 렌더링이고
    #     일정 페이지가 `item.gameId` 템플릿만 준다(`/match.do?year=` 는 400 ·
    #     실측 2026-10-09). ⚠️ 경로를 추측해 붙이지 않았다(CLAUDE.md #4).
    #  ⚠️ 그래서 **그 사실을 맨 위에 적는다** — 확정 XI 가 없는 까닭이 *"아직
    #     안 나왔다"* 가 아니라 *"받을 통로가 없다"* 일 때 둘은 다르다.
    if not (card.facts.xi or {}):
        # 🔴 글은 **사다리가 짓는다**(A-3) — 무엇을 돌았고 무엇이 막혔는지 그 표가
        #    안다. ⚠️ 여기 베끼면 출처가 늘 때 이 줄이 따라가지 못한다(#1).
        from app.core import lineups as _ln
        out.append(_ln.none_line(comp_key(card))
                   + " → ② 라인업 보정·IR02·IR03 이 돌지 못한다")
    if card.started:
        out.append("🔴 **이미 시작한 경기다 — 예측이 아니다**(등급을 내지 않는다)")
    by: dict[str, int] = {}
    for d in card.drops:
        by[d.reason.value] = by.get(d.reason.value, 0) + 1
    if by:
        out.append("버린 것: " + " · ".join(f"`{k}` {v}건"
                                        for k, v in sorted(by.items())))
    docs_n = card.funnel.counts.get("docs")
    out.append(f"문서 {docs_n if docs_n is not None else '못 쟀다'}건 · 변수 "
               f"{len(card.variables)}개 · 시나리오 "
               f"{len(card.hypo.scenarios) if card.hypo else 0}개")
    # 🔴🔴 **못 받은 칸을 칸별로**(축구 완성 지시서 §2 마지막 줄) — s2 가 센 것을 그대로
    #    ⚠️ 이 줄이 비면 *"다 받았다"* 는 거짓이 된다(#3 조용한 0 금지).
    if card.facts.gaps:
        out.append("못 받은 칸 — " + " · ".join(card.facts.gaps))
    elif not card.facts.xi:
        out.append("⚠️ **확정 XI 를 못 잡았다** — 상한이 그만큼 내려간다")
    # 🔴 충돌은 **채택/버림**을 한 줄로(§1-2)
    for d in card.drops:
        if d.reason.value == "conflict":
            out.append(f"🔴 {d.detail}")
    # 🔴🔴 **결장 귀속 정정**(사용자 지시 2026-10-07) — 고친 것을 카드에 적는다
    #    ⚠️ 조용히 고치면 사용자가 *"모델이 틀렸다"* 를 못 본다(#3).
    #    🔴 **같은 줄은 한 번만** — ⚠️ 실측 2026-10-11(LAFC): 같은 선수를 여러
    #       문서에서 고쳐 *"Thomas Muller …→…"* 가 **다섯 번** 찍혔다. 수를 함께
    #       적어 **몇 번 고쳤는지**는 남긴다(지우는 것이 아니다).
    said: dict[str, int] = {}
    for d in card.drops:
        if d.reason.value == "team_reattached":
            key = f"🔴 {d.detail}"
        elif d.reason.value in ("team_unresolved", "team_ambiguous"):
            key = f"⚠️ 결장 귀속 미확정 → 근거 불가 — {d.detail}"
        else:
            continue
        said[key] = said.get(key, 0) + 1
    out += [(x if n == 1 else f"{x} ×{n}") for x, n in said.items()]
    return "\n".join(f"- {x}" for x in out)


#: 🔴 상태 글자 — 사람이 읽는 꼴(§5 블록 2)
#: 🔴 상태 글자 표 — `layer1.XI_KO` 가 **원본**이다(사본 금지)
#  ⚠️ 여기 또 적어 뒀더니 `layer1` 쪽만 고쳐져 두 곳이 갈렸다(2026-10-10).


def _xi_ko() -> dict:
    from app.core import layer1
    return dict(layer1.XI_KO)


def _b2(card: Card) -> str:
    """블록 2 XI — `{팀} {포메이션} [확정|예상|없음] 감독 {이름}` + 선수 11명(§5)."""
    if not card.facts.xi:
        return "- ⬜ 없다 — 어느 쪽 XI 도 못 받았다(사유는 블록 1)"
    out: list[str] = []
    for key, xi in card.facts.xi.items():
        who = _who(card, key)
        coach = card.facts.coach.get(key)
        head = (f"- **{who}** {xi.formation or '포메이션 미상'} "
                f"[{_xi_ko().get(xi.state, xi.state)}]")
        if coach is not None:
            head += f" 감독 {coach.name}" + (" (임시)" if coach.interim else "")
        out.append(head)
        if xi.lineup:
            # 🔴 포지션 약자를 함께 적는다(§5) — 등번호가 있으면 그것도
            said = " · ".join(
                f"{p.name}({p.pos or '?'}" + (f",{p.number}" if p.number else "")
                + ")" for p in xi.lineup[:11])
            out.append(f"    {said}")
        elif xi.players:
            out.append(f"    {' · '.join(xi.players[:11])}")
        else:
            out.append("    ⬜ 선발 명단 없음")
        for said in xi.conflicts:
            # 🔴 결장 충돌로 뺀 선수는 **그 사실을 적는다**(§2·§5)
            out.append(f"    {said}")
    return "\n".join(out)


def _b2b_rungs(card: Card) -> str:
    """🔴 ① — 결장 사다리 **칸별 시도 결과** 한 줄씩. 없으면 빈 글자."""
    rows = list(getattr(card.facts, "absence_rungs", None) or [])
    if not rows:
        return ""
    out = ["- 🪜 **결장 사다리**"]
    out += [f"    {r.get('rung')} — **{r.get('got')}건** · {r.get('why')}"
            for r in rows]
    return "\n".join(out)


def _b2b(card: Card) -> str:
    """블록 2b 결장(새 블록 · §5) — `이름(포지션) — 사유 · 출처 도메인`.

    🔴🔴 **결장 사다리의 칸별 결과를 함께 적는다**(사용자 지시 2026-10-11 ①) —
       *"결장 명단 미확보"* 는 **네 칸 모두 0일 때만**이고, 그때도 칸별 시도
       결과를 적는다(#3 조용한 0 금지).
    """
    rungs = _b2b_rungs(card)
    if not card.facts.missing:
        return ("- ⬜ **결장 명단 미확보**" + ("\n" + rungs if rungs else ""))
    ko = {"injury": "부상", "suspension": "징계", "doubtful": "출전 불확실",
          "international_duty": "대표팀 차출", "other": "사유 미상"}
    out: list[str] = ([rungs] if rungs else [])
    for key, rows in card.facts.missing.items():
        out.append(f"- **{_who(card, key)}**")
        for m in rows:
            dom = (m.source_url.split("/")[2] if m.source_url.count("/") >= 2
                   else "")
            tail = f" · 복귀 {m.returns}" if m.returns else ""
            mark = " ⚠️ 기사" if m.source == "article" else ""
            out.append(f"    {m.name}({m.pos or '?'}) — {ko.get(m.reason, m.reason)}"
                       f"{tail} · {dom}{mark}")
    return "\n".join(out)


def _b3b(card: Card) -> str:
    """🔴🔴 블록 3b **경우의 수** — 사용자 지시 2026-10-06(7차) §2.

    > 결과별 순위·구역, 그리고 **팀별 상태 한 줄**.
    > 예) *"카자흐스탄: must_win(지면 4위 확정적, 비겨도 4위) · 페로: draw_enough"*

    ⚠️ 순위표가 없으면 **그 사실을 적는다**(#3) — 빈 블록은 거짓이다.
    🔴 동률 규칙이 **확인 안 된 대회**면 그 가정을 여기 적는다(금지 조항).
    """
    look = dict(card.outlook or {})
    # 🔴🔴 **게이트가 먼저다**(지시 2026-10-09(5차) ①) — 시즌 초면 한 줄로 끝난다.
    #    ⚠️ 순위표 검사보다 **앞**에 둔다: 게이트가 닫히면 `cells` 가 비어 있고
    #       그러면 아래 *"순위표가 없다"* 로 잘못 적힌다(실측).
    if look and not look.get("gate_open", True):
        return (f"- ⬜ **시즌 초 — 경우의 수 해당 없음**({look.get('gate_why')})"
                f" · 조 `{look.get('group') or '?'}`")
    cells = list(look.get("cells") or [])
    if not cells:
        box = dict(card.facts.standings or {})
        rows = box.get("table") if isinstance(box.get("table"), list) else None
        if not rows:
            return ("- ⬜ 경우의 수를 못 센다 — **순위표가 없다**(`unknown`) · 형식 "
                    f"`{card.facts.match_format}`")
        out = ["| 팀 | 순위 | 승점 | 경기 |", "|---|---|---|---|"]
        for r in rows[:8]:
            row = dict(r) if isinstance(r, dict) else {}
            out.append(f"| {row.get('name', '?')} | "
                       f"{row.get('idx', row.get('rank', '?'))} | "
                       f"{row.get('pts', '?')} | {row.get('played', '?')} |")
        out.append("⚠️ 같은 조 전체 표를 못 받아 **결과별 순위**는 못 센다")
        return "\n".join(out)
    home, away = card.match.home_name, card.match.away_name
    out: list[str] = []
    group = look.get("group") or ""
    # 🔴 `remaining` 은 **조 전체**의 남은 경기 수다 — 우리 두 팀 것이 아니다.
    #    ⚠️ 실사고 2026-10-09(가시마–감바): *"남은 경기 300개"* 가 찍혀 마치 두
    #       팀에게 300경기가 남은 것처럼 읽혔다. 🔴 팀별 라운드를 함께 적는다.
    left_t = dict(look.get("rounds_left") or {})
    mine = (" · 이 두 팀 남은 라운드 "
            + " / ".join(f"{t} {max(0, int(n))}" for t, n in left_t.items())
            if left_t else "")
    out.append(f"- 조 `{group}` · 조 전체 남은 경기 {look.get('remaining', '?')}개"
               + mine + " · "
               + ("**최종 확정 가능**" if look.get("final")
                  else "⚠️ **최종 확정 아니다**(남은 라운드가 더 있다)"))
    if look.get("other"):
        out.append("- 같은 라운드 다른 경기(순위에 닿는 순): "
                   + " · ".join(look["other"]))
    # 🔴 **뺀 경기도 적는다**(지시 2026-10-09 ① · #3 조용한 0 금지)
    if look.get("other_dropped"):
        out.append("- ⚠️ 표에 **넣지 않은** 같은 라운드 경기: "
                   + " · ".join(look["other_dropped"])
                   + f" — 표가 커져 {len(look['other'])}경기까지만 곱했다")
    # 🔴🔴 **분할 컷**이 있으면 그 사실과 도달 가능한 최대 승점을 적는다(지시 ①)
    if look.get("cut"):
        reach = dict(look.get("reachable") or {})
        left = dict(look.get("rounds_left") or {})
        said = " · ".join(f"{t} 최대 {reach.get(t, '?')}점"
                          f"(남은 {max(0, int(left.get(t, 0)) - 1)}라운드)"
                          for t in (home, away))
        out.append(f"- 🔴 **분할 컷 {look['cut']}위** — {look.get('cut_why') or ''}")
        out.append(f"- 도달 가능 최대 승점: {said} "
                   + ("· **이 경기가 마지막이다**" if look.get("final")
                      else "· 남은 라운드가 더 있어 **확정 아니다**"))
    # ⚠️ 사유가 **여러 줄**로 올 수 있다(yaml 블록) — 한 줄로 눌러 담는다(표가 깨진다)
    src = " ".join(str(look.get("source") or "").split())[:150]
    if not look.get("verified"):
        out.append(f"- ⚠️ **동률 규칙 가정**(승점→득실→다득점) — {src}")
    else:
        out.append(f"- 동률 규칙 **확인됨** — {src}")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **다른 경기 칸은 그 경기 팀 이름으로**(사용자 지시 2026-10-09 ①)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실사고 2026-10-09: 종전은 둘째 칸의 `home`·`away` 를 **우리 팀 이름**으로
    #     풀어 *"대전 승 | 대전 승"* 으로 찍었다 — 둘째 칸은 **인천–포항**의 말이다.
    #  🔴 이제 줄마다 그 경기의 팀 이름이 실려 온다(`cells[*]["others"]`).
    others0 = list((cells[0].get("others") or []) if cells else [])
    cols = [f"{o['home']}–{o['away']}" for o in others0]
    head = "| 이 경기 | " + "".join(f"{c} | " for c in cols) \
        + f"{home} | {away} |"
    out += ["", head, "|---|" + "---|" * (len(cols) + 2)]

    def _word(team_home: str, team_away: str, res: str) -> str:
        return {"home": f"{team_home} 승", "draw": "무승부",
                "away": f"{team_away} 승"}.get(res, res)

    for c in cells:
        def _cell(team: str) -> str:
            # 🔴 분할 컷이 있으면 **컷 안/밖**을 함께 적는다(상태 판정과 같은 눈)
            rank = c["ranks"].get(team, "?")
            z = str(c["zones"].get(team, ""))
            said = f"{rank}위"
            if look.get("cut") and isinstance(rank, int):
                said += " **컷 안**" if rank <= int(look["cut"]) else " **컷 밖**"
            elif z:
                said += f" ({z})"
            return said
        cells_txt = [_word(home, away, str(c["ours"]))]
        cells_txt += [_word(str(o["home"]), str(o["away"]), str(o["result"]))
                      for o in (c.get("others") or [])]
        cells_txt += [_cell(home), _cell(away)]
        out.append("| " + " | ".join(cells_txt) + " |")
    # 🔴 팀별 상태 한 줄 — 이동 규칙이 **이 글자**를 본다
    said = dict(look.get("states") or {})
    for team in (home, away):
        box = dict(said.get(team) or {})
        if not box:
            continue
        out.append(f"- **{team}: {box.get('state')}** — {box.get('why')}"
                   + (f" · {box.get('margin')}골 차" if box.get("margin") else ""))
    if look.get("zone_meaning"):
        out.append("- 구역 뜻: " + " · ".join(
            f"`{k}` = {v}" for k, v in dict(look["zone_meaning"]).items()))
    if not look.get("final"):
        out.append("- ⚠️ 위 표는 **이번 경기만 보면** 이다 — 남은 경기가 "
                   f"{look.get('remaining')}개라 최종 순위는 그 뒤에 정해진다")
    return "\n".join(out)


def _who(card: Card, key: str) -> str:
    """🔴 열쇠 → **보일 이름**(열쇠는 사람이 못 읽는다)."""
    if key == card.match.home:
        return card.match.home_name
    if key == card.match.away:
        return card.match.away_name
    return key


def _b3_games(card: Card) -> str:
    """🔴🔴 ① — **상성이 쓴 한 경기 목록**으로 폼 블록을 적는다(두 창 다).

    `matchup["games"][side]` 한 줄은 `s2e_matchup.games_of` 가 만든 것이다 —
    `{date, league, side, opp, score, gf, ga}`. 🔴 창 합은 `form.window_sums`
    하나가 센다(사본 금지) — **축1 이 보는 그 수**다.
    ⚠️ 목록이 없으면 **빈 글자**를 내고 호출부가 옛 폼 블록을 적는다(그 사실이
       블록에 남는다 · #3).
    """
    from app.core import form as _form
    box = dict(getattr(card, "matchup", None) or {})
    games = dict(box.get("games") or {})
    if not games:
        return ""
    bad = dict(box.get("window_bad") or {})
    out: list[str] = []
    for side in ("home", "away"):
        rows = list(games.get(side) or [])
        who = (card.match.home_name if side == "home"
               else card.match.away_name)
        if not rows:
            out.append(f"- **{who}** — ⬜ 경기 목록을 못 받았다")
            continue
        said = []
        for n in _form.WINDOWS:
            win = _form.window_sums(rows, n)
            if not win["n"]:
                continue
            said.append(f"최근 {win['n']}경기 득 {win['gf']:.0f}·"
                        f"실 {win['ga']:.0f}"
                        f"(경기당 {win['gf'] / win['n']:.2f}·"
                        f"{win['ga'] / win['n']:.2f})")
        out.append(f"- **{who}** — " + " · ".join(said)
                   + (f" · 🔴 {bad.get(side)}" if bad.get(side) else ""))
        for one in rows[-5:][::-1]:
            out.append(f"    {one.get('date')} "
                       f"{'홈' if one.get('side') == 'home' else '원정'} "
                       f"{one.get('opp')} {one.get('score')}"
                       + (f" [{one.get('league')}]" if one.get("league")
                          else ""))
    out.append("- 🔴 **두 창은 같은 경기 목록에서 잘랐다** — 폼 블록과 축1 이 "
               "같은 수를 본다(사용자 지시 2026-10-11 ①)")
    return "\n".join(out)


def _b3(card: Card) -> str:
    """블록 3 폼 — 🔴 **사람이 읽는 꼴**(사용자 지시 2026-10-06 ⑦).

    > 블록 3 을 사람이 읽는 형태로(최근 5경기·평균·보정 평균·휴식).

    ⚠️ 실측 2026-10-06: 어댑터 dict 를 `str()` 로 찍어 `{'team': …, 'sequence': [{…}]}`
       가 카드에 그대로 나갔다 — 맞대결은 `matchUrl` 까지 실려 있었다.
    🔴 **없는 칸은 이름으로** 남긴다(#3) — 못 잰 것과 0 을 가른다.
    """
    f = card.facts
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 ① **경기 목록은 하나다** — 사용자 지시 2026-10-11 ①
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 폼 블록(5경기)과 축1(10경기)의 경기 목록을 날짜·대회·스코어로 나란히
    #  > 찍어라. **한 원천(같은 경기 목록)에서 두 창을 자른다.**
    #
    #  ⚠️ 실사고 2026-10-11(LAFC–밴쿠버): 이 블록은 **fotmob 폼 블록**(`f.recent`)
    #     을, 축1 은 **경기 페이지 목록**(`matchup["games"]`)을 읽었다 — 그래서
    #     *"최근5 실점 10"* 과 *"최근10 실점 9"* 가 한 카드에 나란히 찍혔다.
    #  🔴 그래서 **상성이 쓴 그 목록**이 있으면 이 블록도 그것으로 센다.
    said_games = _b3_games(card)
    if not (f.recent or f.standings or f.h2h or said_games):
        return "- ⬜ 없다 — 구조 자료를 못 받았다(사유는 블록 1)"
    out: list[str] = []
    if said_games:
        return said_games
    for key, raw in f.recent.items():
        box = dict(raw) if isinstance(raw, dict) else {}
        who = (card.match.home_name if key == card.match.home
               else card.match.away_name if key == card.match.away else key)
        last5 = " ".join(str(x) for x in (box.get("last5") or [])) or "못 쟀다"
        got = box.get("recent_scored_avg")
        trim = box.get("recent_trimmed_avg")
        rest = box.get("rest_days")
        bits = [f"최근5 **{last5}**"]  # 🔴 §5: 아래에 경기별 한 줄을 적는다
        bits.append(f"득점 평균 {got}" if got is not None else "득점 평균 못 쟀다")
        if trim is not None and got is not None and float(trim) != float(got):
            # 🔴 **보정했으면 그 사실을 적는다** — 조용히 다른 수를 쓰지 않는다
            bits.append(f"보정 평균 **{trim}**")
        bits.append(f"휴식 {rest}일" if rest is not None else "휴식 못 쟀다")
        for name, label in (("streak_unbeaten", "무패"), ("streak_scored", "연속 득점"),
                            ("streak_winless", "무승")):
            if box.get(name):
                bits.append(f"{label} {box[name]}")
        out.append(f"- **{who}** — " + " · ".join(bits))
        seq = [x for x in (box.get("sequence") or []) if isinstance(x, dict)]
        for x in seq[:5]:
            # 🔴 §5 블록 3 — **경기별 한 줄**이다(한 줄에 몰아 적지 않는다)
            rank = x.get("opponent_rank")
            tail = f"({rank}위)" if rank else ""
            out.append(f"    {x.get('date')} "
                       f"{'홈' if x.get('side') == 'home' else '원정'} "
                       f"{x.get('opponent')}{tail} {x.get('score')}")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **허용 목록이다 — 거부 목록이 아니다**(실사고 2026-10-09)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측 2026-10-07(MLS): `standings["group"]` 이 들어오자 이 줄이 **85,682자**
    #     를 쏟았다. 그때 `group`·`outlook_states` 를 **빼는** 식으로 막았다.
    #  🔴 그 거부 목록이 또 뚫렸다 — 실측 2026-10-09(가시마–감바): 순위표가 채워지자
    #     팀별 줄(`rank`·`played`·`points`…)이 그 목록에 없어서 **3,983자**가 나갔다.
    #  🔴 그래서 **뒤집는다**: 블록 3 이 적을 칸을 **이름으로 고른다**. 새 칸이
    #     생겨도 여기 없으면 안 나간다(사본 금지의 형제 규칙 — 손으로 유지하는
    #     거부 목록은 언제나 한 발 늦는다 · CLAUDE.md #1).
    #  ⚠️ 조 순위표는 **블록 3b** 가 그린다(그 블록이 그 일을 한다).
    said_std = _standings_line(card)
    if said_std:
        out.append(said_std)
    if f.h2h:
        h = dict(f.h2h)
        got = h.get("summary")
        bits = []
        n = h.get("count")
        # 🔴🔴 **집계가 안 맞으면 그 수를 안 적는다**(사용자 지시 2026-10-07 ③).
        #    ⚠️ s5 는 변수를 안 만들고 블록 1에 적는데, **블록 3 은 그 수를 계속
        #       찍고 있었다**(실측 2026-10-07: *"5승 4무 4패 · 표본 10경기"*).
        #       🔴 보이는 것도 **쓰는 것**이다 — 사람이 그 수로 판단한다.
        ok3 = (isinstance(got, (list, tuple)) and len(got) == 3
               and (n is None or sum(int(x) for x in got) == int(n)))
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **다시 센 수가 있으면 그것을 적는다**(사용자 지시 2026-10-09 ①)
        # ══════════════════════════════════════════════════════════════
        #
        #  🔴 s5 가 집계 불일치를 만나면 **목록에서 다시 세어** 이 칸에 넣는다.
        #     ⚠️ 그러면 블록 3 도 **같은 수**를 적어야 한다 — 다른 수를 적으면
        #        사람이 어느 쪽을 믿을지 모른다(#3 조용한 0 금지의 형제 문제).
        again = dict(h.get("recounted") or {})
        if again.get("n"):
            # 🔴 **팀 이름을 붙여 한 번만**(지시 2026-10-09 ④) — 기준을 글에 박아
            #    두면 읽는 쪽이 뒤집을 일이 없다
            who = again.get("basis") or card.match.home_name
            bits.append(f"**{who}** {again['w']}승 {again['d']}무 "
                        f"{again['l']}패(상대 {again['l']}승)")
            bits.append(f"표본 {again['n']}경기(**목록에서 다시 셌다**)")
            n = None
        elif ok3:
            bits.append(f"**{card.match.home_name}** {got[0]}승 {got[1]}무 "
                        f"{got[2]}패(상대 {got[2]}승)")
        elif isinstance(got, (list, tuple)) and len(got) == 3:
            bits.append(f"⚠️ **전적 안 적는다**(집계 불일치 — 합 "
                        f"{sum(int(x) for x in got)} ≠ 표본 {n})")
        if n is not None:
            bits.append(f"표본 {n}경기")
        if h.get("window_avg_goals") is not None:
            bits.append(f"평균 {h['window_avg_goals']}골")
        if h.get("sample_weight") is not None:
            bits.append(f"표본 무게 {h['sample_weight']}")
        out.append("- 맞대결 — " + (" · ".join(bits) or "못 쟀다"))
        # 🔴🔴 **올 시즌 맞대결은 따로 적는다**(같은 지시 ① 둘째 줄)
        #    > 올 시즌 맞대결은 **따로 표시**(이 경우 0-1·0-0)
        #    ⚠️ 창(최근 10경기)에 올 시즌이 섞여 있어도 **사람은 올 시즌을 따로**
        #       본다 — 같은 감독·같은 명단이 뛴 경기다.
        season = list(h.get("season_matches") or [])
        if season:
            said = " · ".join(f"{m.get('date')} {m.get('home')} "
                              f"{m.get('score')} {m.get('away')}" for m in season)
            out.append(f"- 올 시즌 맞대결 {len(season)}경기 — {said}")
        elif h.get("season_checked"):
            out.append("- 올 시즌 맞대결 — ⬜ **없다**(올 시즌 첫 대결이다)")
    return "\n".join(out)


#: 🔴 블록 3 이 **적는 칸** — 홈 이점과 쪼갠 표뿐이다(허용 목록 · 지시 2026-10-09)
#  ⚠️ 칸 이름은 `s5_verify._ir_home` 이 읽는 것과 **같다**(`home_advantage`).
STANDINGS_SHOW: tuple[str, ...] = ("home_advantage", "venue", "venue_averages",
                                   "team_totals", "key_players")


def _standings_line(card: Card) -> str:
    """🔴 블록 3 의 순위 줄 — **허용 목록**의 칸만. 없으면 빈 글자."""
    box = dict(card.facts.standings or {})
    said = {k: box[k] for k in STANDINGS_SHOW if box.get(k)}
    if not said:
        # ⚠️ 표가 **있는데** 보일 칸이 없으면 그 사실을 적는다(#3) — 조용히 빠지면
        #    사람이 *"순위를 못 받았다"* 로 읽는다.
        if box.get("group"):
            return "- 순위 — 조 순위표는 **블록 3b** 에 있다(홈/원정 쪼갠 표는 못 받았다)"
        return ""
    out: list[str] = []
    # 🔴🔴 **경기당 총골**(지시 2026-10-09(5차) ②·③) — 블록 3 이 적을 칸이다
    tot = dict(said.get("team_totals") or {})
    # 🔴🔴 §3-2 — **전략이 그 기준을 움직였으면** 그 수를 함께 적는다
    #    ⚠️ `if tot:` **밖에서** 정의한다 — 안에 두면 아래 줄이 이름을 못 찾는다
    #       (계약이 `UnboundLocalError` 로 잡았다 · 2026-10-10)
    said_t = dict((getattr(getattr(card, "strategy", None), "facts", None)
                   or {}).get("TOTAL") or {})
    moved_t = said_t.get("value")
    if tot:
        base = box.get("match_total_baseline")
        out.append("- 경기당 총골 — "
                   + " · ".join(f"**{_who(card, k)}** {v.get('total_per_game')}"
                                f"({v.get('goals_for')}득 {v.get('goals_against')}실"
                                f" {v.get('played')}경기)"
                                for k, v in tot.items())
                   + (f" → **이 경기 기준 {base}**" if base else "")
                   # 🔴 §3-2 — 전략이 움직였으면 **움직인 수**를 함께 적는다
                   + (f" → 전략 반영 **{moved_t}**"
                      if moved_t is not None and base is not None
                      and abs(float(moved_t) - float(base)) >= 0.005 else ""))
    if moved_t is not None and tot:
        out.append(f"    {said_t.get('text')}")
    # 🔴 **핵심 선수** — 시즌 득점·도움 상위(§2 셋째 줄)
    kp = dict(said.get("key_players") or {})
    for key, rows in kp.items():
        bits = " · ".join(f"{dict(r).get('name')} {dict(r).get('value')}"
                          + (f"({dict(r).get('matches')}경기)"
                             if dict(r).get("matches") else "")
                          for r in (rows or []))
        if bits:
            out.append(f"- 핵심 선수 **{_who(card, key)}** — {bits}")
    ha = dict(said.get("home_advantage") or {})
    got = ha.get("win_pct_delta")
    if got is not None:
        out.append(f"- 홈 이점(쪼갠 표) — 홈 승률 {float(got):+g}%p · "
                   f"홈 {ha.get('home_games', '?')}경기 · 원정 "
                   f"{ha.get('away_games', '?')}경기")
    if out:
        return "\n".join(out)
    return f"- 순위 — {_short(said)}"


def _short(box: object, cap: int = 160) -> str:
    """🔴 긴 사전을 **줄여** 적는다 — ⚠️ 줄였다는 사실을 함께 적는다(#3)."""
    said = str(box)
    return said if len(said) <= cap else f"{said[:cap]}… (줄였다 {len(said)}자)"


def _b4(card: Card) -> str:
    """블록 4 변수 — 🔴 **근거 불가 변수는 맨 아래 따로 묶는다**(§5)."""
    if not card.variables:
        return ("- ⬜ 변수 0개 — 🔴 **\"자료가 안 왔다\"와 \"왔는데 못 뽑았다\"는 "
                "다르다**(블록 1 의 사유를 본다)")
    good = [v for v in card.variables if v.usable_as_basis]
    weak = [v for v in card.variables if not v.usable_as_basis]
    out = [_var_line(v) for v in good]
    if weak:
        out.append("")
        out.append("**(근거 불가)** — 맥락으로만 쓴다")
        out += [_var_line(v) for v in weak]
    return "\n".join(out)


def _var_line(v: Variable) -> str:
    """🔴 변수 한 줄 — **승패와 득점 방향을 둘 다** 적는다(사용자 지시 ④).

    ⚠️ 종전엔 `goals_up` 이 승패 칸에 있어 *"어느 팀 쪽인가"* 가 안 보였다.
    """
    rule = f" · [규칙 {v.from_rule}]" if v.from_rule else ""
    goals = {"up": "↑", "down": "↓"}.get(v.goals, "-")
    src = (f"출처 {len(v.doc_ids)}곳" if v.doc_ids else "출처 구조 사실")
    who = f" · 대상 `{v.target}`" if v.target else ""
    return (f"- `{v.id}` [{v.type}] {v.claim} — 승패 **{v.favors}** · "
            f"득점 {goals} · {v.hardness} · {src}{who}{rule}")


def _b5(card: Card) -> str:
    if card.hypo is None or not card.hypo.hypotheses:
        return "- ⬜ 가설이 없다 — DeepSeek 단계가 못 돌았거나 근거 변수가 0개다"
    out = []
    for h in card.hypo.hypotheses:
        who = (card.match.home_name if h.team == "home"
               else card.match.away_name)
        out.append(f"- **{who}**")
        for line in h.reasons:
            out.append(f"  - 이긴다면: {line.text} ({', '.join(line.var_ids)})")
        for line in h.breaks:
            out.append(f"  - 무너지는 조건: {line.text} "
                       f"({', '.join(line.var_ids)})")
    cited = [d for d in (card.hypo.drops or [])]
    for d in cited:
        out.append(f"  - 🔴 버린 줄: `{d.reason.value}` {d.detail}")
    return "\n".join(out)


def _b6(card: Card) -> str:
    if card.hypo is None or not card.hypo.scenarios:
        return "- ⬜ 시나리오가 없다 — 대입할 갈래가 없으면 생존은 뜻이 없다"
    out = []
    for s in card.hypo.scenarios:
        scores = " · ".join(f"{h}-{a}" for h, a in s.outcomes)
        mark = " [보강]" if s.added_by == "code" else ""
        out.append(f"- **{s.id}** ({scores}) {s.type} · 무게 {s.strength}{mark} — "
                   f"{s.mechanism} ← {', '.join(s.driver_vars) or '근거 없음'}")
    return "\n".join(out)


#: 🔴 보드 출처 → 사람이 읽는 말(사용자 지시 2026-10-07 ①)
_SRC_KO = {"user_board": "사용자 보드", "feed": "피드 메인 라인", "none": ""}


def _b7(card: Card) -> str:
    if not card.evals:
        return "- ⬜ 대입한 줄이 없다"
    ids = [s.id for s in (card.hypo.scenarios if card.hypo else [])]
    head = "| 마켓 | " + " | ".join(ids) + " | 생존 | 상한 | 등급 |"
    bar = "|---" * (len(ids) + 4) + "|"
    rows: list[str] = []
    # 🔴🔴 **출처를 적는다** — 보드가 없으면 *"참고 — 보드 없음"*(지시 ②)
    src = str(card.board_source or "none")
    if src == "none":
        rows.append("⏸ **참고 — 보드 없음**(기준선 목록이다 · 등급은 전부 `보류`)")
    else:
        rows.append(f"출처: **{_SRC_KO.get(src, src)}**")
    rows.append("")
    rows += [head, bar]
    extra = set(card.board_extra)
    tail: list[str] = []
    for e in card.evals:
        point = f" {e.line.point}" if e.line.point is not None else ""
        said = (f"{e.line.market} {e.line.side}"
                f"{(' ' + str(e.line.point)) if e.line.point is not None else ''}")
        cells = " | ".join(e.marks.get(i, "?") for i in ids)
        line = (f"| {e.line.market} {e.line.side}{point} | {cells} | "
                f"{e.survival} | {e.cap} | {e.grade} |")
        # 🔴 `추가:` 줄은 **아래 묶음**으로(§4 · 사용자 규칙)
        (tail if said in extra else rows).append(line)
    if tail:
        rows.append("")
        rows.append("**추가 옵션에 있으면**")
        rows += tail
    for said in card.board_bad:
        # 🔴 **못 읽은 줄은 그대로 보인다**(조용히 버리지 않는다 · §4)
        rows.append(f"- 🔴 보드 줄 못 읽음: {said}")
    return "\n".join(rows)


def _comment(card: Card, *, debug: bool = False) -> str:
    """🔴🔴 **종합 논평 블록**(사용자 지시 2026-10-07 ④) — 결론 줄 **바로 아래**.

    ```
    🧭 종합 논평 — {title}
    {reasons 를 한 문단으로 · 변수 번호·코드 없이 사람 말}
    📈 예상 흐름: {flow}
    🎯 예상 스코어: {score_range}
    ```

    🔴 1겹(텔레그램) 카드는 **번호를 지운다**. ⚠️ 긴 카드(`debug=True`)는 같은 블록에
       **근거 `var_ids`·양상 비중 숫자**를 붙인다.
    """
    from app.core.stages.s8_comment import plain
    said = card.commentary
    if said is None:
        box = dict(card.shape or {})
        return ("\n🧭 **종합 논평 — 없다**"
                + (f"(양상 {box.get('shape')} · {box.get('why')})" if box else
                   "(양상을 못 쟀다 — 시나리오가 없다)")
                + ("" if not card.comment_notes else
                   "\n    ⚠️ " + " · ".join(card.comment_notes[:3])))
    out = [f"\n🧭 **종합 논평 — {said.title}**"]
    body = plain(said)
    if body:
        out.append(body)
    if said.flow:
        out.append(f"📈 **예상 흐름**: {said.flow}")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **예상 스코어는 한 곳에서 나온다**(사용자 지시 2026-10-10 D-2)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 1겹·긴 카드 **모두** `top_scores` 하나에서. `0-0` 이면 근거 id 를 양쪽에.
    #
    #  ⚠️ 종전엔 긴 카드가 `commentary.score_range`(작성자가 고른 것)를 썼고 1겹만
    #     무게에서 뽑았다 — 같은 카드가 **두 수**를 말했다.
    #  🔴 `said.score_range` 가 비어도 적는다 — 무게는 작성자와 무관하다.
    from app.core import layer1 as _l1
    out.append(f"🎯 **예상 스코어**: {_l1._scores(card)}")
    if said.lean:
        # ⚠️ 등급이 없으면 *"추천"* 이 아니라 **기울기**다(코드가 그것을 검사했다)
        out.append(f"↗️ **기울기**: {said.lean}")
    if debug:
        box = dict(card.shape or {})
        out.append(f"    [양상] {box.get('shape')} — 2골 이하 "
                   f"{box.get('low', 0):.0%} · 4골 이상 {box.get('high', 0):.0%} · "
                   f"2골 차 이상 {box.get('one_sided', 0):.0%} · 한 골 안 "
                   f"{box.get('close', 0):.0%} · {box.get('why')}")
        for line in said.reasons:
            out.append(f"    [근거] {line.text} ← {', '.join(line.var_ids) or '없음'}")
        # 🔴🔴 **검열 과정은 `/디버그` 에만**(사용자 지시 2026-10-07 §4-3)
        out.append(f"    [검열] {card.comment_audit}"
                   + (f" · 위반 {len(card.comment_violations)}건"
                      if card.comment_violations else ""))
        for x in card.comment_violations[:6]:
            out.append(f"      · {x}")
        if card.comment_notes:
            out.append("    [검사] " + " · ".join(card.comment_notes[:8]))
    return "\n".join(out)


def _b8(card: Card) -> str:
    """🔴 결론 — 🔴🔴 **반증 한 줄을 함께 적는다**(지시서 2026-10-12 ⑯).

    > 결론 줄에 "반증 6조건: 무너짐 0 · 미확인 1 → 조건부(방아쇠: K4 확정 XI)"
    """
    out = [card.conclusion or "- ⬜ 결론을 못 적었다"]
    rows = list(card.breaks or [])
    if card.stance or rows:
        n_b = sum(1 for c in rows if str(getattr(c, "state", "")) == "확인-무너짐")
        n_u = sum(1 for c in rows if str(getattr(c, "state", "")) == "미확인")
        said = [f"`{getattr(c, 'id', '')}`" for c in rows
                if str(getattr(c, "state", "")) == "미확인"][:2]
        out.append(
            f"🧪 **반증 {len(rows)}조건**: 무너짐 {n_b} · 미확인 {n_u} → "
            f"**{card.stance or '판정 없음'}**"
            + (f"(방아쇠: {', '.join(said)})" if said else ""))
    return "\n".join(out)


def breaks_long(card: Card) -> str:
    """🔴 📖자세히 — **반증 표 전문**(조건·종류·확인 방법·결과·출처·시각)."""
    rows = list(card.breaks or [])
    if not rows:
        return "**🧪 반증 표** — ⬜ 조건 0건"
    out = [f"**🧪 반증 표** — 판정 `{card.stance or '없음'}` · 조건 {len(rows)}건",
           "| 조건 | 종류 | 확인 | 결과 | 강도 | 출처 |",
           "|---|---|---|---|---|---|"]
    for one in rows:
        out.append(
            f"| `{getattr(one, 'id', '')}` | {getattr(one, 'kind', '')} "
            f"| {getattr(one, 'how', '')} | {getattr(one, 'state', '')} "
            f"| {getattr(one, 'strength', '') or '—'} "
            f"| {str(getattr(one, 'source', '') or '—')[:40]} |")
    for one in rows:
        said = str(getattr(one, "said", "") or "")
        if said:
            out.append(f"    `{getattr(one, 'id', '')}` {said[:140]}")
    return "\n".join(out)


def _b9(card: Card) -> str:
    # 🔴 **매 경기 한 줄** — "방향 없음" 은 쓰지 않는다(지시서 §2-2)
    return card.direction or "- 🔴 방향 줄이 비었다 — 이것은 결함이다(§2-2)"


def _b10(card: Card) -> str:
    """블록 10 방아쇠 — 🔴 **사람이 읽는 문장**이다(§5: 내부 표기 금지)."""
    if not card.triggers:
        return "- ⬜ 방아쇠가 없다 — 조건 표에 걸린 변수 유형이 없었다"
    return "\n".join(f"- {x}" for x in card.triggers)

# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **블록 3c·7b** — 네 층 지시서 §8
# ══════════════════════════════════════════════════════════════════


def _b3c(card: Card) -> str:
    """🔴 3c 기준 전력 — ① Elo·② 라인업 보정. ⚠️ 없으면 **"없음 — 사유"** 다(§1)."""
    b, a = card.base_prob, card.adj_prob
    out: list[str] = []
    if b.probs is not None:
        out.append(f"- Elo: {card.match.home_name} **{b.home_elo:.0f}** · "
                   f"{card.match.away_name} **{b.away_elo:.0f}** · 차 {b.dr:+.0f} "
                   f"→ 승 {b.probs.home:.0%} · 무 {b.probs.draw:.0%} · "
                   f"패 {b.probs.away:.0%}")
        out.append(f"    출처 {b.source}({b.data_date}) · {b.why}")
    else:
        out.append(f"- ⬜ **기준 없음** — {b.why}")
        if b.we is not None:
            # 🔴 §3-3 — 무승부를 못 나누면 **We 만** 보인다(지어내지 않는다)
            out.append(f"    Elo 기대 득점률 `We` **{b.we:.3f}**"
                       f"(홈 {b.home_elo:.0f} · 원정 {b.away_elo:.0f})")
    if a.strength_pct:
        got = " · ".join(f"{k} {v:+.1f}%" for k, v in a.strength_pct.items())
        # 🔴🔴 **%p 와 계수 신뢰도를 함께**(사용자 지시 2026-10-06(6차) ②)
        #    꼴: `라인업 보정 −1.2%p (환산 R² 0.61 · 표본 33)`
        head = f"- 라인업 보정: 평소 대비 {got}"
        if a.moved and b.probs is not None and a.probs is not None:
            pp = (a.probs.home - b.probs.home) * 100.0
            fit = _ds_fit(b.comp_kind)
            head += (f" → 홈 승 **{pp:+.1f}%p**"
                     f"(환산 R² {fit.get('r2', '?')} · 표본 {fit.get('n', '?')})")
            head += (f"\n    보정 후 승 {a.probs.home:.0%} · 무 {a.probs.draw:.0%} · "
                     f"패 {a.probs.away:.0%}")
        else:
            head += " — ⚠️ 확률은 **안 움직였다**(환산 계수 없음)"
        out.append(head)
        for d in a.deltas[:6]:
            # 🔴 ③ — 같은 포지션끼리만 짝이다. 짝이 없으면 **구조 변경**이라고 적는다
            tag = f"[{d.pos}]" if d.pos else "[포지션 미상]"
            if d.structural:
                # ⚠️ 구조 변경 줄의 수는 **짝의 차이가 아니다** — 그 선수 혼자의
                #    로그 가치다. 그 말을 적지 않으면 팀 ΔS 와 섞여 읽힌다.
                said = (f"{d.out_name} 빠짐 {tag} — **구조 변경**(같은 포지션 교체 없음)"
                        if d.out_name else
                        f"{d.in_name} 들어옴 {tag} — **구조 변경**")
                out.append(f"    {said}: 그 선수 로그가치 {d.delta_s:+.2f}"
                           + (" (추정값)" if d.estimated else ""))
                continue
            else:
                said = f"{d.out_name} → {d.in_name} {tag}"
            out.append(f"    {said}: ΔS {d.delta_s:+.2f}"
                       + (f" → 홈 승 {d.delta_home_pct:+.1f}%p"
                          if d.delta_home_pct is not None else "")
                       + (" (추정값)" if d.estimated else ""))
    else:
        out.append(f"- ⬜ **라인업 보정 없음** — {a.why}")
    return "\n".join(out)


def _b7b(card: Card) -> str:
    """🔴 7b 확률 세 열 — 기준·우리·시장(+사용자 보드). **한 숫자로 합치지 않는다**.

    🔴 배당 원숫자는 시장·사용자 보드 열에 **괄호로** 보인다(§8 · 사용자 결정).
    🔴 기대값·금액은 **어디에도 없다**(§0 금지).
    """
    from app.core.odds import key_of
    mk, user = card.market, card.user_market
    head = f"시장 = {mk.basis or '없음'}"
    if mk.captured_at is not None:
        from app import timefmt
        head += f"(받은 때 {timefmt.kst_label(mk.captured_at)})"
    vig = (mk.vig or {}).get("win")
    if vig is not None:
        head += f" · 업체 몫 {vig:.1%}"
    if mk.used is not None:
        head += f" · 월 사용 {mk.used}/{mk.limit or '?'}"
    # 🔴 §2-6 — 사용자 보드가 **그대로 시장 열**인 경우(피드 없음)에는 열을 **겹쳐
    #    적지 않는다**. ⚠️ 겹쳐 적으면 같은 배당이 두 열에 보여 *"피드도 있다"* 로 읽힌다.
    same_col = bool(user.probs) and mk.basis == user.basis
    cols = ["| | 기준 | 우리 | 시장 |", "|---|---|---|---|"] if same_col else \
           ["| | 기준 | 우리 | 시장 | 사용자 보드 |", "|---|---|---|---|---|"]
    # 🔴🔴 **기준 열은 "②반영" 이다**(네 층 지시서 §6 첫 줄: *"기준(②반영)·우리·시장"*).
    #    ⚠️ ① 만 적으면 우리 열의 **출발점과 다른 수**가 기준 칸에 앉아, 이동량 줄이
    #       설명하지 못하는 차이가 생긴다(실측 2026-10-06: 54% vs 출발 52%).
    base_col = (card.adj_prob.probs if card.adj_prob.probs is not None
                else card.base_prob.probs)
    if card.adj_prob.moved:
        cols[0] = cols[0].replace("| 기준 |", "| 기준(②반영) |")
    rows = [f"- {head}", ""] + cols
    names = ((f"{card.match.home_name} 승", "home"), ("무", "draw"),
             (f"{card.match.away_name} 승", "away"))
    for label, key in names:
        cells = [label]
        cells.append(f"{getattr(base_col, key):.0%}"
                     if base_col is not None else "—")
        cells.append(f"{getattr(card.our_prob, key):.0%}"
                     if card.our_prob is not None else "—")
        for box in ((mk,) if same_col else (mk, user)):
            p = (box.probs or {}).get(key_of("win", key))
            price = _price_of(box, key)
            cells.append("—" if p is None else
                         (f"{p:.0%}" + (f" ({price:g})" if price else "")))
        rows.append("| " + " | ".join(cells) + " |")
    shin = mk.shin or {}
    if shin:
        said = " · ".join(
            f"{nm} {shin.get(key_of('win', k), 0):.0%}"
            for nm, k in (("홈", "home"), ("무", "draw"), ("원정", "away")))
        rows.append(f"- Shin 방식(괄호 비교용): {said}")
    # 🔴🔴 **③ 이 움직인 양**(사용자 지시 2026-10-06(6차) ③) — 없으면 그 사실을 적는다
    if card.moves:
        said = " · ".join(
            f"`{m.get('id')}`({m.get('type')}→{m.get('side')}) "
            f"{float(m.get('logodds') or 0):+.3f}" for m in card.moves[:6])
        tot = sum(abs(float(m.get("logodds") or 0)) for m in card.moves)
        rows.append(f"- ③ 이 움직인 양(로그 오즈 합 {tot:.3f}): {said}")
    else:
        # 🔴🔴 **"우리 열 = 기준" 은 거짓이었다** — ⚠️ 실사고 2026-10-10(제노아):
        #    기준 26/30/45 · 우리 35/30/35 가 **같은 표에** 적혀 있는데 그 아래
        #    줄이 *"우리 열 = 기준"* 이라고 했다. 🔴 상성 엔진 뒤로 우리 열은
        #    **S3(상성+시뮬)** 이 낸 수이고 기준(Elo)과 **다른 길**이다(C7: 변수가
        #    로그 오즈를 미는 ③ 경로를 지웠다 — 그래서 `moves` 가 늘 비었다).
        rows.append("- ③ **변수가 확률을 직접 미는 경로 없음**(C7) — "
                    "우리 열은 **S3(상성)** 이 낸 수다"
                    if card.our_prob is not None else
                    "- ③ **우리 열이 비었다** — S3 가 확률을 못 셌다"
                    "(시나리오 비율을 우리 열로 쓰지 않는다 · 지시 ③)")
    if card.compare:
        rows.append(f"- 판정: **{card.compare}**")
    for line in card.compare_lines:
        if line:
            rows.append(f"    {line}")
    for line in card.tilt:
        rows.append(f"- → {line}")
    for line in card.market_why:
        rows.append(f"- → {line}")
    if card.ocr_text:
        rows.append("- 캡처 인식 원문(그대로):")
        rows += [f"    {x}" for x in card.ocr_text.splitlines() if x.strip()]
    if not mk.probs and not user.probs:
        rows.append(f"- ⬜ **시장 없음** — {mk.why or '피드·사용자 보드 모두 없다'}")
    return "\n".join(rows)


def _ds_fit(kind: str) -> dict:
    """🔴 `ΔS→dr` 계수의 **표본·R²** — 카드가 그 신뢰도를 숨기지 않는다(②)."""
    from app import rules
    return dict((rules.base_model(str(kind)) or {}).get("ds_fit") or {})


def _price_of(box, side: str) -> float | None:
    """🔴 그 쪽의 **원배당** — 괄호로 보이는 숫자다. ⚠️ 없으면 `None`."""
    for q in (box.quotes or []):
        if q.market == "win" and q.side == side:
            return q.price
    return None


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **🆕 새 사실(72시간)** — 사용자 지시 2026-10-10(재작성) §3-4
# ══════════════════════════════════════════════════════════════════
#
#  > 카드 블록 *"🆕 새 사실(72시간)"*: 항목 한 줄 + **출처·날짜** + **변수 번호**.
#  > 0건이면 *"새 사실 0건 — 검색 n회·문서 m건"* 과 운영자 알림.

#: 🔴 새 사실을 나른 하위 과제 — `config/subtask_groups.yaml` 의 `F` 다
NEW_SUBS: tuple[str, ...] = ("F-home", "F-away")
NEW_HEAD = "🆕 **새 사실(72시간)**"


def new_facts(card: Card) -> list:
    """🔴 그 카드의 **새 사실 변수들** — 하위 과제 F 가 나른 것.

    🔴 변수가 **자기 하위를 들고 있다**(`Variable.subtask`) — `Card` 에 `docs`
       칸이 없어서 문서를 거쳐 셀 길이 없었다(그래서 칸을 하나 더했다).
    ⚠️ 묶인 변수는 **F 가 이긴다**(`s5_verify._merge`) — 같은 사실을 72시간 창에서
       찾았다면 그것은 새로 나온 사실이다(§3-3).
    """
    return [v for v in (card.variables or [])
            if not v.from_rule and str(v.subtask or "") in NEW_SUBS]


#: 🔴 ② 손실 표에 적는 최대 줄 수 — ⚠️ 넘치면 **그 사실을 적고** 자른다(#3)
LOSS_ROWS = 40


#: 🔴 단계가 늦을수록 큰 수 — 손실 표가 그 순서로 보인다
_LATE: tuple[tuple[str, int], ...] = (
    ("s9", 60), ("s7", 55), ("s6", 50), ("s5", 40), ("s4", 30), ("s3", 20),
    ("s2", 10),
)


def _late_rank(stage: str) -> int:
    """🔴 그 단계가 **얼마나 늦은가**(모르면 0 — 맨 뒤)."""
    said = str(stage or "").lower()
    for head, rank in _LATE:
        if said.startswith(head):
            return rank
    return 0


def loss_table(card: Card) -> str:
    """🔴🔴 ② **손실 표** — 버린 것 하나하나를 `단계 · 사유 · 제목` 으로.

    > 새 사실 손실 감사: 광주–울산 hits 17 → docs 0. **17건 각각 버린 단계·사유·
    > 제목을 표로.** — 사용자 지시 2026-10-11 ②

    ⚠️ 종전엔 블록 1 이 *"버린 것: `identity_mismatch` 7건 · `stale` 14건"* 처럼
       **수만** 적었다 — 그 글이 무엇이었는지, 어느 문에서 걸렸는지 알 길이 없었다.
    🔴 제목이 빈 줄은 **빈 채로 적는다**(그 통로가 제목을 안 준다는 사실이다).
    """
    rows = list(card.drops or [])
    if not rows:
        return "🧾 **손실 표** — ⬜ 버린 것이 없다"
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **늦은 단계를 먼저 보인다**(사용자 지시 2026-10-11 · 서치 고침)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측: 표가 40줄에서 잘려 `s5/type_content_mismatch` **2건**이 안 보였다
    #     — 그 둘은 추출까지 통과한 *"거의 다 온 것"* 이라 가장 볼 값이 크다.
    #  🔴 단계가 늦을수록 앞에 둔다(s6 → s5 → s4 → s3). 같은 단계면 들어온 순서다.
    rows.sort(key=lambda d: -_late_rank(str(getattr(d, "stage", "") or "")))
    out = ["🧾 **손실 표**(버린 단계 · 사유 · 제목)",
           "", "| 단계 | 사유 | 제목 | 상세 |", "|---|---|---|---|"]
    for d in rows[:LOSS_ROWS]:
        stage = str(getattr(d, "stage", "") or "?")
        title = str(getattr(d, "title", "") or "").replace("|", "·")
        said = str(d.detail or "").replace("|", "·")[:60]
        out.append(f"| `{stage}` | `{d.reason.value}` | "
                   f"{title or '⬜ 제목 없음'} | {said} |")
    if len(rows) > LOSS_ROWS:
        out.append(f"- ⚠️ **{len(rows) - LOSS_ROWS}줄 더 있다**(표는 "
                   f"{LOSS_ROWS}줄까지 적는다)")
    by: dict[str, int] = {}
    for d in rows:
        key = f"{getattr(d, 'stage', '') or '?'}/{d.reason.value}"
        by[key] = by.get(key, 0) + 1
    out.append("- 합계 — " + " · ".join(f"`{k}` {v}건"
                                       for k, v in sorted(by.items())))
    return "\n".join(out)


def new_facts_block(card: Card) -> str:
    """🔴🔴 §3-4 — 카드 블록 한 덩이. **0건이면 그 사실을 적는다**(#3).

    한 줄 꼴: `· {claim} — 출처 {n}곳 · {발행일} · [{변수 번호}]`
    """
    rows = new_facts(card)
    if not rows:
        # 🔴 §3-4 — *"0건이면 '새 사실 0건 — 검색 n회·문서 m건'"*
        # ⚠️ `Cost` 에 검색 횟수 칸이 **없다**(`calls` 는 LLM 호출이다) — 지어
        #    내지 않고 **있는 수**를 적는다: 기사 변수 수와 깔때기다.
        n_var = len([v for v in (card.variables or []) if not v.from_rule])
        box = dict(getattr(getattr(card, "funnel", None), "counts", None) or {})
        said = " · ".join(f"{k} {v}" for k, v in sorted(box.items())
                          if k in ("queries", "hits", "kept_date", "docs"))
        return (f"{NEW_HEAD} — 🔴 **0건** · 기사 변수 {n_var}개(F 하위에서 온 것 "
                f"0개)" + (f" · {said}" if said else ""))
    out = [NEW_HEAD]
    for v in rows:
        out.append(f"· {v.claim} — 출처 {len(v.doc_ids)}곳 · [{v.id}]")
    return "\n".join(out)


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 §4 긴 카드 — **자리별 비교표 · ΔA·ΔD · 전략 변수와 이동량**
# ══════════════════════════════════════════════════════════════════
#
#  > 긴 카드: 자리별 비교표, ΔA·ΔD 계산, 적용된 전략 변수와 이동량, 감독 패턴 표.

STRATEGY_HEAD = "🧠 라인업 전략 (자세히)"


def strategy_long(card: Card) -> str:
    """🔴 §4 — 긴 카드의 전략 블록. **확정 XI 가 아니면 그 사실 한 줄**이다."""
    from app.core import strategy as _st
    plan = getattr(card, "strategy", None)
    said = str(getattr(plan, "audit", "") or "")
    if plan is None or said in ("", "안 돌았다"):
        return f"**{STRATEGY_HEAD}**\n- ⬜ 전략 판정을 안 돌렸다"
    out = [f"**{STRATEGY_HEAD}** — 판정 `{said}`"]
    if said == "확정 XI 전":
        out += [f"- 🔴 {x}" for x in (getattr(plan, "violations", None) or [])]
        return "\n".join(out)
    if said == "버렸다":
        out.append("- 🔴 **수치와 반대인 판정이라 버렸다**(§2-2) — 확률은 "
                   "**잠정 그대로**다")
        out += [f"    · {x}" for x in (getattr(plan, "violations", None) or [])]
        return "\n".join(out)
    # ── §2-1 사실표(자리별 교체·ΔA·ΔD 가 여기 들어 있다)
    box = dict(getattr(plan, "facts", None) or {})
    m = card.match
    for side, name in (("home", m.home_name), ("away", m.away_name)):
        rows = [(k, v) for k, v in box.items() if dict(v).get("side") == side]
        one = None
        for line in (getattr(plan, "lines", None) or []):
            if str(getattr(line, "side", "")) == side:
                one = line
        out.append(f"- **{name}** — "
                   + (f"`{one.strategy}` · 근거 {list(one.fact_refs)} · "
                      f"{one.why}" if one is not None else "판정 없음"))
        for k, v in rows:
            said_v = dict(v)
            out.append(f"    `{k}` [{said_v.get('kind')}] {said_v.get('text')}")
    if getattr(plan, "shape", ""):
        out.append(f"- 양상(§2-3): **{plan.shape}**")
    # ── §3-2 적용된 이동량 — `moves` 에서 전략 줄만 고른다
    rows = [dict(x) for x in (card.moves or [])
            if str(dict(x).get("type") or "") == "strategy_intent"]
    if rows:
        out.append("- **적용된 전략 변수와 이동량**(③ 로그 오즈)")
        for one in rows:
            out.append(f"    {one.get('id')} `{one.get('strategy')}` → "
                       f"{one.get('side')} {float(one.get('logodds') or 0):+.3f}"
                       f" · {one.get('why')}")
    else:
        out.append("- **적용된 전략 변수 없음** — 이동량 0(표에 계수가 없거나 "
                   "`평소 그대로`다)")
    said_cap, said_lam = _st.caps()
    out.append(f"- 상한 — 로그 오즈 ±{said_cap} · λ ±{said_lam:.0f}%"
               f"(`{_st.CONF}`)")
    # ── §3-3 감독 패턴 — 표본이 모자라면 **표시만** 한다
    out.append(f"- 감독 패턴(§3-3) — ⬜ **아직 없다**(같은 감독·같은 조건의 과거 "
               f"경기를 받는 통로가 없다 · 표본 "
               f"{dict(_st.effects().get('coach_pattern') or {}).get('min_sample')}"
               f"경기 미만이면 확률은 안 움직인다)")
    return "\n".join(out)


TACTIC_HEAD = "🎓 전술 전문가 예측"


def tactic_long(card: Card) -> str:
    """🔴🔴 §6 — 긴 카드의 전술 예측. **글뿐이다**(확률을 안 움직인다).

    ⚠️ 못 돌았거나 버린 경우 **그 사유를 적는다**(#3 조용한 0 금지).
    """
    got = getattr(card, "tactic", None)
    said = str(getattr(got, "audit", "") or "")
    if got is None or said in ("", "안 돌았다"):
        return f"**{TACTIC_HEAD}** — ⬜ 안 돌렸다"
    out = [f"**{TACTIC_HEAD}** — 판정 `{said}`"]
    # 🔴🔴 ④ — **어떤 판정이든 사유를 적는다**(사용자 지시 2026-10-11 ④:
    #    *"실패하면 '템플릿' 대신 사유(llm_truncated / 검열 코드 / 근거 0)를"*)
    #  ⚠️ 종전엔 두 판정(`확정 XI 전`·`버렸다`)에서만 적었다 — 그래서 `템플릿`
    #     판정의 카드에는 **까닭이 한 글자도 없었다**(실측 2026-10-11).
    rows = [f"- 🔴 {x}" for x in
            (getattr(got, "violations", None) or [])[:4]]
    out += rows
    if said in ("확정 XI 전", "버렸다"):
        return "\n".join(out)
    for one in (getattr(got, "lines", None) or []):
        out.append(f"- **{one.slot}** — {one.text} · 근거 {list(one.refs)}")
    return "\n".join(out)


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 §5(셋째 지시서) — **긴 카드의 상성 자세히**
# ══════════════════════════════════════════════════════════════════
#
#  > 긴 카드: **골 목록 표(분·유형·상태·xG), 시간대 분포, 리드 유지력·추격력,
#  > 발동 규칙과 적합 효과.**
#
#  🔴 네 덩이를 **그 순서로** 적는다. 수는 `s2e_matchup` 이 센 것뿐이고 여기서
#     다시 세지 않는다(사본 금지).
#  ⚠️ 못 모은 축은 **사유를 적는다**(#3 조용한 0 금지).

EDGE_LONG_HEAD = "⚔️ 상성 세 축 (자세히)"
#: 🔴 유형 어휘를 사람 말로 — ⚠️ `미상` 은 `미상` 으로 남긴다(open 으로 밀지 않는다)
KIND_KO = {"open": "필드골", "counter": "역습", "setpiece": "세트피스",
           "penalty": "PK", "own_goal": "자책골", "미상": "미상"}


def matchup_long(card: Card) -> str:
    """🔴🔴 §5 — 상성 네 덩이. **못 돌았으면 사유 한 줄**."""
    box = dict(getattr(card, "matchup", None) or {})
    if not box:
        return f"**{EDGE_LONG_HEAD}** — ⬜ 안 돌렸다"
    if not box.get("profile"):
        return (f"**{EDGE_LONG_HEAD}** — ⬜ "
                + str(box.get("why") or "세 축을 못 모았다"))
    m = card.match
    names = {"home": str(m.home_name or ""), "away": str(m.away_name or "")}
    out = [f"**{EDGE_LONG_HEAD}**"]
    out += _goal_table(box, names)
    out += _bucket_rows(box, names)
    out += _flow_rows(box, names)
    out += _fired_rows(box, names)
    return "\n".join(out)


def _goal_table(box: dict, names: dict) -> list[str]:
    """🔴 §5 ① **골 목록 표** — 분·유형·상태·xG. 경기별로 묶어 적는다."""
    tab = dict(box.get("table") or {})
    if not tab:
        return ["- 골 목록 — ⬜ **표를 못 만들었다**(경기 페이지 타임라인 미확보)"]
    out = []
    for side in ("home", "away"):
        rows = list(tab.get(side) or [])
        if not rows:
            out.append(f"- **{names[side]}** 골 목록 — ⬜ **0건**")
            continue
        # 🔴 **상태는 넣은 팀 기준**이다(`goals.state_of` · 비중 표와 같은 기준) —
        #    그 말을 안 적으면 실점 줄의 `앞섬` 을 우리가 앞선 것으로 읽는다
        out.append(f"- **{names[side]}** 골 {len(rows)}건 "
                   "(분·유형·상태·xG · 상태는 **넣은 팀 기준**)")
        seen: list[str] = []
        for one in rows:
            key = f"{one.get('opp')}|{one.get('home')}"
            if key not in seen:
                seen.append(key)
                out.append(f"    {'홈' if one.get('home') else '원정'} "
                           f"vs {one.get('opp')}")
            xg = one.get("xg")
            out.append(
                f"      {'득' if one.get('mine') else '실'} "
                f"{int(one.get('minute') or 0)}' · "
                f"{KIND_KO.get(str(one.get('kind')), str(one.get('kind')))} · "
                f"{one.get('state')} · "
                + (f"xG {float(xg):.2f}" if xg is not None else "xG 없음")
                + (" · 🎲 운 요소" if one.get("lucky") else "")
                + (" · 헤더" if one.get("header") else ""))
    return out


def _bucket_rows(box: dict, names: dict) -> list[str]:
    """🔴 §5 ② **시간대 분포** — 0-30 / 31-60 / 61-90+ 득점·실점."""
    prof = dict(box.get("profile") or {})
    out = ["- **시간대 분포**(§3-2)"]
    for side in ("home", "away"):
        one = prof.get(side)
        if one is None:
            out.append(f"    {names[side]} — ⬜ 프로필 없음")
            continue
        for what, got in (("득점", one.scored), ("실점", one.conceded)):
            if not got.n:
                out.append(f"    {names[side]} {what} — ⬜ **0건**")
                continue
            said = " · ".join(
                f"{k} {int(v)}건({float(v) / got.n:.0%})"
                for k, v in sorted(dict(got.by_bucket).items()))
            out.append(f"    {names[side]} {what} {got.n}골 — {said}")
    return out


def _flow_rows(box: dict, names: dict) -> list[str]:
    """🔴 §5 ③ **리드 유지력 · 추격력** — 표본을 함께 적는다(§3-4)."""
    prof = dict(box.get("profile") or {})
    out = ["- **리드 유지력 · 추격력**(§3-2)"]
    for side in ("home", "away"):
        one = prof.get(side)
        if one is None:
            out.append(f"    {names[side]} — ⬜ 프로필 없음")
            continue
        hold, back = one.hold_rate(), one.comeback_rate()
        out.append(
            f"    {names[side]} — 리드 유지력 "
            + (f"{hold:.0%} {dict(one.led_first)}" if hold is not None
               else "⬜ **선제골 경기 0건**")
            + " · 추격력 "
            + (f"{back:.0%} {dict(one.trailed_first)}" if back is not None
               else "⬜ **선실점 경기 0건**"))
    return out


def _fired_rows(box: dict, names: dict) -> list[str]:
    """🔴 §5 ④ **발동 규칙과 적합 효과** — 축2(T1~T6)·축3(T9~T13) 둘 다.

    🔴 `관찰만` 은 **확률을 안 움직인다**(§3-4) — 그 말을 그대로 적는다.
    🔴 임시값 표시는 `Fired.why` 가 들고 온다(사본 금지 · 금지 조항: 적합 없는
       계수를 표시 없이 쓰지 않는다).
    """
    out = ["- **발동 규칙과 적합 효과**(§2 T1~T6 · §3-3 T9~T13)"]
    # 🔴 **축마다 따로 센다** — 한 축이 0건인 것을 다른 축의 발동이 가린다(#3)
    axes = (("축2 T1~T6", list(box.get("fired2") or [])),
            ("축3 T9~T13", list(box.get("fired") or [])))
    out += [f"    ⬜ **{what} 발동 0건** — 문턱을 넘은 규칙이 없다"
            for what, got in axes if not got]
    rows = [one for _, got in axes for one in got]
    for one in rows:
        moved = dict(one.moves())
        out.append(
            f"    `{one.rule}` {names.get(one.side, one.side)} — {one.text}"
            + (f" · 효과 {moved}" if moved
               else f" · **{goals_watch()}** — 확률 미반영")
            + (f" · {one.why}" if one.why else ""))
    return out


def goals_watch() -> str:
    """🔴 `관찰만` 글자는 `app/core/goals.py` 하나가 든다(사본 금지)."""
    from app.core import goals as _g
    return str(_g.WATCH_ONLY)


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 §4 둘째 덩이 — **긴 카드의 최종 평**(2026-10-10 넷째)
# ══════════════════════════════════════════════════════════════════
#
#  > 긴 카드(/디버그): **key_point마다 근거 id와 원 사실, 검열 결과.**

SAY_LONG_HEAD = "🧑‍🏫 최종 평 (자세히)"


def say_long(card: Card) -> str:
    """🔴 §4 — 주장마다 **근거 id + 원 사실**, 그리고 **검열 결과**."""
    got = getattr(card, "say", None)
    said = str(getattr(got, "audit", "") or "")
    if got is None or said in ("", "안 돌았다"):
        return (f"**{SAY_LONG_HEAD}** — ⬜ 안 돌렸다"
                + (f" · {list(getattr(got, 'violations', None) or [])[:2]}"
                   if got is not None and getattr(got, "violations", None)
                   else ""))
    out = [f"**{SAY_LONG_HEAD}** — 판정 `{said}` · 결론 **{got.verdict}**"]
    if str(got.one_line or ""):
        out.append(f"- 한 줄 — {got.one_line}")
    used = dict(getattr(got, "used", None) or {})
    for i, kp in enumerate(got.key_points or [], 1):
        out.append(f"- **주장 {i}** {kp.claim}")
        out.append(f"    메커니즘 — {kp.mechanism}")
        out.append(f"    근거 {list(kp.refs or [])}")
        for r in (kp.refs or []):
            one = used.get(str(r))
            if one:
                out.append(f"      `{r}` {one}")
            else:
                # 🔴 #3 — 원 사실을 못 되찾은 id 도 **이름으로** 남긴다
                out.append(f"      `{r}` ⬜ 원 사실을 못 되찾았다")
    out.append(f"- 흐름 전반 — {got.flow_first}")
    out.append(f"- 흐름 후반 — {got.flow_second}")
    out.append(f"- 승부처 — {got.decisive_moment}")
    out.append(f"- 뒤집히는 조건 — {got.flip_condition}")
    rows = list(getattr(got, "violations", None) or [])
    out.append("- 검열 결과 — "
               + ("⬜ **위반 0건**" if not rows
                  else " / ".join(str(x) for x in rows[:6])))
    # 🔴 **버린 평도 보인다** — 템플릿으로 내려간 이유를 사람이 추적하게(#3)
    for one in list(getattr(got, "dropped", None) or [])[:6]:
        out.append(f"    🗑 버린 평 — {one}")
    return "\n".join(out)


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **긴 카드의 가설 검증표** — 순서 재편 지시서 §4-5·카드
# ══════════════════════════════════════════════════════════════════
#
#  > 긴 카드: **가설 검증표 전체**, **재실행 여부와 이유**, **시나리오별 지지 가설**.

CHECK_LONG_HEAD = "🧪 가설 검증표 (자세히)"


def check_long(card: Card) -> str:
    """🔴 §4-5 — 가설·신호·시뮬 값·판정·반박 원인 + 재실행 + 시나리오별 근거."""
    box = dict(getattr(card, "check", None) or {})
    rows = list(box.get("rows") or [])
    if not rows:
        return (f"**{CHECK_LONG_HEAD}** — ⬜ "
                + str(box.get("why") or "검증을 안 돌렸다"))
    from app.core import signals as _sg
    counts = dict(box.get("counts") or {})
    out = [f"**{CHECK_LONG_HEAD}** — 지지 {int(counts.get(_sg.OK, 0))} · 반박 "
           f"{int(counts.get(_sg.NO, 0))} · 판단 불가 "
           f"{int(counts.get(_sg.NA, 0))}"]
    if str(box.get("stale") or ""):
        out.append(f"- {box['stale']}")
    for one in list(box.get("gaps") or []):
        out.append(f"- {one}")
    # 🔴 **재실행 여부와 이유**(§4-3) — 0회도 적는다(#3)
    out.append("- 재실행 — "
               + (str(box["rerun"]) if str(box.get("rerun") or "")
                  else "⬜ **0회**(조건이 성립하지 않았다)"))
    for one in rows:
        said = dict(one)
        mark = {_sg.OK: "✅", _sg.NO: "❌"}.get(str(said.get("verdict")), "⬜")
        out.append(f"- {mark} **{said.get('side')}/{said.get('kind')}** "
                   f"{said.get('text')}")
        out.append(f"    신호 {said.get('signal')} · 시뮬 {said.get('value')}"
                   f" · 기준 {said.get('want')} · 근거 변수 "
                   f"{list(said.get('var_ids') or [])}")
        out.append(f"    판정 **{said.get('verdict')}**"
                   + (f" · 원인 **{said.get('cause')}**"
                      if said.get("cause") else "")
                   + f" · {said.get('why')}")
    # 🔴 **시나리오별 지지 가설**(§카드) — 시나리오의 근거는 지지된 변수뿐이다
    scen = list(getattr(getattr(card, "hypo", None), "scenarios", None) or [])
    if scen:
        out.append("- **시나리오별 근거**(§4-4 — 지지된 가설의 변수만)")
        for one in scen:
            out.append(f"    `{one.id}` {one.outcomes} — 근거 "
                       f"{list(one.driver_vars)} · {one.mechanism[:70]}")
    return "\n".join(out)


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **🔢 변수 블록** — 상성 엔진 지시서(2026-10-10 여섯째) V-4·§3
# ══════════════════════════════════════════════════════════════════
#
#  > 카드 긴 블록 `🔢 변수` 에 **전부** 보이고, 각 변수가 **어디에 쓰였는지**
#  > (축 몇 / 검증 몇 / 가설 몇) 표시.
#
#  🔴 배치는 `routing.place` 하나가 한다 — 여기서 다시 정하지 않는다(사본 금지).

VARS_HEAD = "🔢 변수 (배치 자리)"


def vars_long(card: Card) -> str:
    """🔴 V-4 — 변수 **전부**와 그 자리. ⚠️ 배치 실패·미배치를 이름으로 적는다."""
    from app.core import routing
    rows = list(getattr(card, "variables", None) or [])
    if not rows:
        return f"**{VARS_HEAD}** — ⬜ **변수 0개**"
    got = getattr(card, "varset", None)
    if got is None:
        # 🔴 파이프라인이 안 실었으면 **여기서 한 번** 배치한다(카드는 나온다).
        #    ⚠️ 그 사실을 적는다 — 운영 경로와 다른 자리에서 센 것이다(#3).
        got = routing.place(rows)
        head = f"**{VARS_HEAD}** — ⚠️ 카드가 직접 배치했다 · {got.why()}"
    else:
        head = f"**{VARS_HEAD}** — {got.why()}"
    out = [head]
    for one in got.rows:
        out.append(
            f"- `{one.id}` [{one.type}] {one.hardness} 무게 {one.weight:g}"
            + (" · 🔴 **근거 불가**(맥락)" if one.context_only else "")
            + f" · 자리 {one.places or '**없다**'}")
        # 🔴 **자른 자리를 말줄임으로 알린다** — ⚠️ 실측 2026-10-10: 90자 자리가
        #    문장 가운데를 잘라 *"…다른 대회 숫자를 빌리지 않는다 · 리그 홈 이점"*
        #    처럼 **괄호가 안 닫힌 채 완결된 문장처럼** 읽혔다(#3 조용한 잘림).
        said_claim = str(one.claim or "")
        out.append(f"    {said_claim[:90]}"
                   + ("…(잘림)" if len(said_claim) > 90 else "")
                   + (f" · {one.why}" if one.why else ""))
    for said in got.fails:
        out.append(f"- {said}")
    if got.unplaced:
        out.append(f"- 🔴 **미배치**(C5 위반) — {got.unplaced}")
    return "\n".join(out)


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **긴 카드 — 상성·검증·시뮬 행렬·적합 정보**(상성 엔진 §3)
# ══════════════════════════════════════════════════════════════════
#
#  > 긴 카드: 🔢 변수 전체(배치 자리) · FactBundle · **MatchupReport 전체** ·
#  > **시뮬 스코어 행렬 상위 10** · **VerificationTable** · 가설 검증표 ·
#  > **적합 정보**.

MATCHUP_LONG_HEAD = "⚔️ MatchupReport (전체)"
VERIFY_LONG_HEAD = "🔎 VerificationTable"
GRID_HEAD = "🎲 시뮬 스코어 상위 10"
FIT_HEAD = "🧮 적합 정보"


def prob_long(card: Card) -> str:
    """🔴🔴 **S3 확률(상성에서 나온 수)** — λ·유도 사슬·축별 기여·오버.

    ══════════════════════════════════════════════════════════════════
    🔴 왜 이 블록이 생겼나 — 사용자 질문 2026-10-11
    ══════════════════════════════════════════════════════════════════

    > 상성에서 나온 확률은 없냐???

    🔴 **있었다** — 7b 의 `우리` 열이 그것이다(상성 → λ → 시뮬). 그런데 긴 카드가
       **유도 사슬을 안 적었다**: λ 두 수·홈 배율·축 종합×β·규칙 λ 가 **로그에만**
       있었고, 축별 기여(3-4)는 **1겹에만** 있었다. 그래서 카드만 보면 그 수가
       어디서 나왔는지 보이지 않았다.
    🔴 수를 **다시 세지 않는다** — `S3`(`probmodel.run`)이 낸 `ProbOut` 을 적는다.
    """
    from app.core import turnover as _turn
    box = dict(getattr(card, "matchup", None) or {})
    # 🔴 **시뮬 표를 읽는다**(`ProbOut.as_sim`) — ⚠️ 카드가 저장을 지나면 그
    #    데이터클래스가 살아 있지 않을 수 있다(실측 2026-10-11: 스냅샷에서
    #    `prob` 칸이 비어 ⬜ 로 떨어졌다). 🔴 **같은 수**가 `sim` 에 다 있다
    #    (`home·draw·away·lam·xg·over·share·why`) — 그것을 쓴다(사본 아님).
    sim = dict(box.get("sim") or {})
    got = box.get("prob")
    if not sim and got is None:
        return "**🎯 상성 확률 (S3)** — ⬜ 안 돌렸다(사유 없음)"
    pull = (lambda k: (sim.get(k) if sim.get(k) is not None
                       else getattr(got, k, None)))
    if pull("home") is None:
        # 🔴 확률을 못 셌어도 **두 판 줄은 적는다**(#3) — ⚠️ 실측 2026-10-12
        #    (아스널–릴 · 챔스): 홈 이점 실측이 없어 여기서 돌아섰고, 그래서
        #    xG 판이 **카드에서 통째로 사라졌다**(돌았는지조차 안 보였다).
        return "\n".join(
            ["**🎯 상성 확률 (S3)** — ⬜ "
             + str(pull("why") or "안 돌렸다(사유 없음)")]
            + _xg_board(box, now={"home": None, "draw": None, "away": None}))
    lam = dict(pull("lam") or {})
    out = ["**🎯 상성 확률 (S3)** — "
           + " · ".join(f"{nm} {float(v):.0%}" for nm, v in
                        (("홈", pull("home")), ("무", pull("draw")),
                         ("원정", pull("away")))
                        if v is not None)
           + (f" · {_turn.PROVISIONAL}"
              if getattr(got, "provisional", True) else "")]
    if lam:
        out.append("- λ(기대 득점) — "
                   + " · ".join(f"{k} {float(v):.3f}" for k, v in lam.items()))
    if pull("why"):
        out.append(f"- 유도 — {pull('why')}")
    # 🔴🔴 **그림자 확률**(사용자 결정 2026-10-12 (a)) — 옛 구조(네 축)의 수다.
    #  ⚠️ **표시만** 한다 — 등급·보드·최종 평은 위의 새 구조가 낸다.
    said_floor = dict(box.get("floor") or pull("floor") or {})
    if said_floor:
        out.append("- 바닥(Elo) — "
                   + " · ".join(f"{nm} {float(said_floor[k]):.0%}"
                                for nm, k in (("홈", "home"), ("무", "draw"),
                                              ("원정", "away"))
                                if said_floor.get(k) is not None))
    said_shadow = dict(box.get("shadow") or pull("shadow") or {})
    if said_shadow:
        out.append("- 🕯 **그림자 확률**(옛 구조 · 네 축 · 표시만) — "
                   + " · ".join(f"{nm} {float(said_shadow[k]):.0%}"
                                for nm, k in (("홈", "home"), ("무", "draw"),
                                              ("원정", "away"))
                                if said_shadow.get(k) is not None)
                   + " — 🔴 판정에는 **안 쓴다**(짝지은 채점용으로 쌓는다)")
    share = dict(box.get("share") or pull("share") or {})
    refs = dict(box.get("share_refs") or {})
    if share:
        out.append("- 기여(리그 평균 대비) — "
                   + " · ".join(f"{k} {float(v):+.1f}%p"
                                for k, v in share.items()))
        said = [f"{k.replace('axis', '축')} {','.join(list(v)[:3])}"
                for k, v in refs.items() if v]
        if said:
            out.append("    주요 변수 " + " · ".join(said))
    over = dict(pull("over") or {})
    if over:
        out.append("- 오버 — " + " · ".join(
            f"{k} {float(v):.0%}" for k, v in sorted(over.items())))
    xg = dict(pull("xg") or {})
    if xg:
        out.append("- 기대 득점(분포 평균) — "
                   + " · ".join(f"{k} {float(v):.3f}" for k, v in xg.items()))
    said_pri = priority_line(card)
    if said_pri:
        out.append(f"- {said_pri} — 🔴 축0 **근거 줄**이다(확률에 곱하지 않는다)")
    out += _xg_board(box, now={"home": pull("home"), "draw": pull("draw"),
                               "away": pull("away")})
    return "\n".join(out)


def priority_line(card) -> str:
    """🔴 [1겹] — *"🎯 우선순위 홈 0.94 · 원정 0.71"*(지시서 2026-10-12 ⑯).

    ⚠️ 못 센 쪽은 `⬜` 다 — 그 사유는 📖자세히(`matchup_report_long`)가 적는다.
    """
    box = dict(getattr(card, "matchup", None) or {})
    said = str(box.get("axis0_said") or "")
    return said or ""


def _xg_board(box: dict, *, now: dict) -> list[str]:
    """🔴🔴 **두 판 나란히**(사용자 결정 2026-10-12 — 3번 b).

    > 4번 검수: 같은 경기 **득실판 vs xG판 확률 비교** … (b) 두 판을 카드에
    > 나란히 적어 둔다.

    🔴 **기본값은 득실판**이다 — 등급·보드·최종 평은 그 수로 간다. xG 판은
       *"백필 브라이어가 더 좋을 때 켠다"* 는 조건이 아직 안 섰다(백필 0건).
    ⚠️ 못 센 까닭은 **이름으로** 적는다(#3).
    """
    said = dict(box.get("xg_pass") or {})
    if not said:
        return []
    sim = dict(said.get("sim") or {})
    if not sim:
        return [f"- 🔬 **xG 판** — ⬜ {said.get('why') or '안 돌렸다'}"]
    def _pct(one: dict) -> str:
        return " | ".join(
            (f"{float(one.get(k)):.0%}" if one.get(k) is not None else "—")
            for k in ("home", "draw", "away"))

    def _tot(gaps: dict) -> str:
        return (f"{sum(float(v) for v in gaps.values()):+.3f}"
                if gaps else "—")

    def _forms(forms: dict) -> str:
        return " / ".join(
            (f"{float(forms.get(s)):+.3f}" if forms.get(s) is not None
             else "—") for s in ("home", "away"))

    mr = box.get("report")
    body = [
        f"| 득실판(기본) | {_pct(now)} | "
        + _tot(dict(mr.gaps()) if mr is not None else {}) + " | "
        + _forms({s: (f.index() if f else None)
                  for s, f in dict(box.get("form") or {}).items()}) + " |",
        f"| xG 판 | {_pct(sim)} | " + _tot(dict(said.get("gaps") or {}))
        + " | " + _forms(dict(said.get("form") or {})) + " |",
    ]
    # 🔴🔴 ⓑ 계약 — 두 판 축1 이 **같으면 경고**(xG 가 안 쓰였다는 뜻이다)
    from app.core import form as _form
    said_warn = _form.boards_warn(
        goal=(dict(box.get("form") or {}).get("home").index()
              if dict(box.get("form") or {}).get("home") else None),
        xg=dict(said.get("form") or {}).get("home"))
    out = ["- 🔬 **두 판 나란히**(지시 2026-10-12 4번 b) — 🔴 **기본값은 득실판**"
           "이다(xG 판은 백필 브라이어 비교 전이다)"
           + (f"\n    {said_warn}" if said_warn else ""),
           "    | 판 | 홈 | 무 | 원정 | 축 종합 | 축1 폼(홈/원정) |",
           "    |---|---|---|---|---|---|"]
    out += [f"    {x}" for x in body]
    # 🔴 두 판이 **다른 쪽을 앞세우면** 그 사실을 적는다(검수 재료)
    def _lead(one: dict) -> str:
        if one.get("home") is None or one.get("away") is None:
            return ""
        return "home" if float(one["home"]) >= float(one["away"]) else "away"
    a, b = _lead(now), _lead(sim)
    if a and b:
        out.append("    → 두 판 방향 "
                   + ("**같다**" if a == b else f"🔴 **갈린다**({a} vs {b})")
                   + f" · xG 판 계수는 `matchup_model.yaml` 의 `xg:` 블록이다")
    return out


def matchup_report_long(card: Card) -> str:
    """🔴 §3 — 축별 값·우위·강도·근거 변수·발동 규칙·전략 판정·종합."""
    box = dict(getattr(card, "matchup", None) or {})
    mr = box.get("report")
    if mr is None:
        return f"**{MATCHUP_LONG_HEAD}** — ⬜ 안 돌렸다"
    verdict = dict(getattr(mr, "verdict", None) or {})
    out = [f"**{MATCHUP_LONG_HEAD}** — 종합 {verdict.get('edge') or '가리지 못함'}"
           f" {verdict.get('strength')} · {verdict.get('why')}"]
    for key in ("axis0", "axis1", "axis2", "axis3"):
        one = mr.axis(key)
        out.append(f"- **{key}** 홈 {one.home} · 원정 {one.away} · 차 "
                   f"{one.gap} · 우위 {one.edge or '—'}({one.strength})")
        out.append(f"    {one.why}")
        out.append(f"    근거 변수 {list(one.refs) or '**없다**'}")
    rows = list(getattr(mr, "fired", None) or [])
    out.append(f"- 발동 규칙 {len(rows)}건"
               + ("" if rows else " — ⬜ **0건**"))
    for f in rows[:8]:
        out.append(f"    `{f.rule}` {f.side} {f.text[:70]}"
                   + (" · **관찰만**(λ 미반영 · C9)" if f.watch_only else ""))
    out.append(f"- r 가중 {dict(getattr(mr, 'r', None) or {})}"
               f" · 꺼진 무기 {dict(getattr(mr, 'off_weapons', None) or {})}"
               f" · 후반 무기 {dict(getattr(mr, 'late_weapons', None) or {})}")
    # 🔴 #3 조용한 0 금지 — **0 이어도 까닭**을 적는다(평소 XI·오늘 빠짐·비중)
    for side, said in dict(getattr(mr, "off_why", None) or {}).items():
        out.append(f"    꺼짐 판정 {side} — {said}")
    return "\n".join(out)


def verify_long(card: Card) -> str:
    """🔴 §3 — **VerificationTable** 전체 + 등급 조정."""
    box = dict(getattr(card, "check", None) or {})
    rows = list(box.get("sources") or [])
    if not rows:
        return f"**{VERIFY_LONG_HEAD}** — ⬜ 검증 출처가 없다"
    out = [f"**{VERIFY_LONG_HEAD}** — {len(rows)}줄"]
    # 🔴🔴 **[1d] 말·일정 ↔ 행동(우선순위 지수)**(수정 지시서 2026-10-12) —
    #    ⚠️ 확률에 닿지 않는다(C1·C7) · 이 줄은 **검증표의 한 줄**이다.
    said_wa = dict(dict(getattr(card, "check", None) or {}).get("word_action")
                   or {})
    for side in ("home", "away"):
        if said_wa.get(side):
            out.append(f"- 🗣 {side} {said_wa[side]}")
    for one in rows:
        said = dict(one)
        out.append(f"- `{said.get('src')}` {said.get('name')} — 방향 "
                   f"**{said.get('dir')}** · 크기 {said.get('size')} · 신뢰 "
                   f"{said.get('trust')}"
                   + (f" · 원인 **{said.get('cause')}**"
                      if said.get("cause") else "")
                   + f" · 근거 {list(said.get('refs') or [])}")
        out.append(f"    {said.get('why')}")
    grade = dict(box.get("grade") or {})
    out.append("- 등급 조정 — "
               + (" / ".join(grade.get("why") or []) or "⬜ 없다")
               + (f" · 내릴 칸 {grade.get('steps')}" if grade else ""))
    return "\n".join(out)


def score_grid(card: Card) -> str:
    """🔴 §3 — **시뮬 스코어 행렬 상위 10**(같은 분포에서 나온다)."""
    box = dict(dict(getattr(card, "matchup", None) or {}).get("sim") or {})
    rows = dict(box.get("scores") or {})
    if not rows:
        return f"**{GRID_HEAD}** — ⬜ 분포가 없다"
    top = sorted(rows.items(), key=lambda kv: -float(kv[1]))[:10]
    said = " · ".join(f"{int(k[0])}-{int(k[1])} {float(v):.1%}"
                      for k, v in top)
    return f"**{GRID_HEAD}** — {said}"


def fit_long(card: Card) -> str:
    """🔴 §3·C10 — **적합 정보**: 임시값인가, 어디서 오나, 왜.

    🔴 표가 원본이다(`config/matchup_model.yaml`·`config/verify_rules.yaml`) —
       여기 수를 적지 않는다(사본 금지).
    """
    from app.core import matchup as _mu
    from app.core.stages import s6c_check as _chk
    box = dict(_mu.table())
    fit = dict(box.get("fit") or {})
    vfit = dict(dict(_chk.rules_table()).get("fit") or {})
    out = [f"**{FIT_HEAD}**"]
    out.append(f"- 상성 계수 — 표본 {fit.get('n')} · "
               + ("🔴 **임시값**" if fit.get("provisional") else "적합됨")
               + f" · {fit.get('why')}")
    out.append(f"    축 비중 {dict(box.get('weights') or {})} · λ 모형 "
               f"{dict(box.get('lambda_model') or {})}")
    out.append(f"- 검증 임계 — 표본 {vfit.get('n')} · "
               + ("🔴 **임시값**" if vfit.get("provisional") else "적합됨")
               + f" · {vfit.get('why')}")
    out.append("- 적합 도구 — `tools/fit_matchup_model.py`"
               f"(`{box.get('fitted_by')}`)")
    return "\n".join(out)
