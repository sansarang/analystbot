"""[§8-22] 소스 교차검증 — **여러 곳에서 모은 값이 서로 맞는지 대조한다.**

사용자 지시(2026-08-26): "기사를 크롤링하고 각종 커뮤니티를 뒤지고
**그 내용이 맞는지 검증해서** 보태면 된다."

실사고가 바로 나왔다. 같은 경기(NC @ LG, 2026-08-26)에서:

    딥서치(Perplexity)  NC 선발 = 구창모
    네이버 preview      NC 선발 = 구창모
    X 구단 공식 계정      NC 선발 = **박준현**   ← 가장 최신

경기 임박에 바뀌었거나 앞선 소스가 어제 경기를 본 것이다. 어느 쪽이든
**소스가 갈리면 최종 픽 자격을 주지 않는다**(라인업 2단계 규율).

설계 원칙
  ① 소스마다 **신선도 등급**이 다르다 — 구단 공식 X > 포털 > 기사 > 커뮤니티
  ② 불일치를 **숨기지 않는다.** 한쪽을 조용히 고르면 왜 틀렸는지 영원히 모른다.
  ③ 판정에 **양쪽 다** 넘기고 `source_conflict`로 표시한다.
  ④ 커뮤니티 단독 정보는 확률 근거가 아니다 — "(미확인)"으로 남긴다.
"""

import logging
import re

logger = logging.getLogger(__name__)

# 신선도 등급 — 큰 값이 최신·정확하다고 본다.
#   구단 공식 계정은 라인업을 가장 먼저 올린다(실측: X에서만 확정 라인업이 나왔다).
SOURCE_RANK = {
    "official_x": 5,     # 구단 공식 X/홈페이지
    "portal": 4,         # 네이버 스포츠·Yahoo!スポーツ preview
    "official_record": 3,  # KBO 기록실·npb.jp (시즌 누적 — 오늘 정보는 아니다)
    "news": 2,           # 기사
    "deep_search": 2,    # Perplexity 요약
    "community": 1,      # 커뮤니티 — 단독으로는 확률 근거 아님
}

# 커뮤니티 단독 정보에 붙는 표시. 이게 붙으면 λ·자격 판정에 쓰지 않는다.
UNVERIFIED = "(미확인)"

_NAME_CLEAN = re.compile(r"[\s·\-—()]+")


def norm_name(v) -> str:
    """선수명 비교용 정규화. '山野 太一' · '山野太一' · '山野  太一' → 같은 값."""
    return _NAME_CLEAN.sub("", str(v or "")).strip()


def compare_field(values: dict[str, object]) -> dict:
    """{소스: 값} → 합의 결과.

    반환: {"value", "source", "agree": [...], "conflict": [{source, value}], "rank"}
    값이 하나뿐이면 conflict는 빈 목록이다.
    """
    present = {k: v for k, v in values.items() if v not in (None, "", [])}
    if not present:
        return {"value": None, "source": None, "agree": [], "conflict": []}
    buckets: dict[str, list[str]] = {}
    for src, val in present.items():
        buckets.setdefault(norm_name(val), []).append(src)
    # 신선도가 가장 높은 소스가 속한 값을 채택한다 (다수결이 아니다 —
    # 오래된 소스 둘이 새 소스 하나를 이기면 안 된다)
    def best_rank(srcs):
        return max(SOURCE_RANK.get(s, 0) for s in srcs)

    winner_key = max(buckets, key=lambda k: (best_rank(buckets[k]), len(buckets[k])))
    win_srcs = buckets[winner_key]
    top_src = max(win_srcs, key=lambda s: SOURCE_RANK.get(s, 0))
    conflict = [{"source": s, "value": present[s]}
                for k, srcs in buckets.items() if k != winner_key for s in srcs]
    return {
        "value": present[top_src], "source": top_src,
        "agree": sorted(win_srcs), "conflict": conflict,
        "rank": SOURCE_RANK.get(top_src, 0),
    }


def extract_starters_from_text(text: str, teams: tuple[str, str]) -> dict[str, str]:
    """속보·여론 텍스트에서 '선발 XXX' 패턴을 뽑는다.

    ⚠️ 정규식이 놓치면 **불일치를 못 잡는다.** 못 뽑는 것이 잘못 뽑는 것보다 낫다 —
       확실한 패턴만 본다.
    """
    out: dict[str, str] = {}
    for pat in (r"선발\s*(?:투수\s*)?[:은는]?\s*([가-힣]{2,4})",
                r"([가-힣]{2,4})\s*\((?:선발|先発)\)"):
        for m in re.finditer(pat, text or ""):
            out.setdefault("any", m.group(1))
    return out


def crosscheck_starters(sources: dict[str, dict]) -> dict:
    """[§8-22] 선발 투수 교차검증. sources = {소스명: {"home": 이름, "away": 이름}}.

    반환: {"home": compare_field결과, "away": ..., "conflict": bool}
    """
    out: dict = {}
    conflict = False
    for side in ("home", "away"):
        res = compare_field({src: (d or {}).get(side) for src, d in sources.items()})
        out[side] = res
        if res["conflict"]:
            conflict = True
            logger.warning("[crosscheck] %s 선발 불일치 — 채택 %s(%s) vs %s",
                           side, res["value"], res["source"],
                           ", ".join(f"{c['value']}({c['source']})"
                                     for c in res["conflict"]))
    out["conflict"] = conflict
    return out


def apply(research: dict, jg: dict, sources: dict[str, dict]) -> dict:
    """교차검증 결과를 research·jg에 반영. 반환: 요약(판정·카드 표시용).

    ⚠️ **불일치를 조용히 해결하지 않는다.** 값은 최신 소스로 채우되,
       `lineup_status`를 conflict로 내려 최종 픽 자격을 박탈한다
       (실사고: 소스가 갈렸는데 최종 픽을 냈다 — 문서화된 과거 사고).
    """
    from app.collectors.lineups import STATUS_CONFLICT

    starters = crosscheck_starters(sources)
    summary: dict = {"starters": {}, "conflict": starters["conflict"]}
    for side in ("home", "away"):
        res = starters[side]
        if not res.get("value"):
            continue
        blk = research.setdefault(f"{side}_pitcher", {})
        if norm_name(blk.get("name")) != norm_name(res["value"]):
            blk["name"] = res["value"]
            # 이름이 바뀌면 이전 소스의 성적은 그 투수 것이 아니다 — 함께 비운다
            for k in ("era_season", "whip", "ip_avg_recent", "era_vs_opponent"):
                blk.pop(k, None)
        summary["starters"][side] = {
            "name": res["value"], "source": res["source"],
            "agree": res["agree"],
            "conflict": [f"{c['value']}({c['source']})" for c in res["conflict"]],
        }
    if starters["conflict"]:
        jg["lineup_status"] = STATUS_CONFLICT      # 최종 픽 자격 박탈
        jg["source_conflict"] = summary
        research["source_conflict"] = "; ".join(
            f"{s} 선발: {v['name']}({v['source']}) vs {' / '.join(v['conflict'])}"
            for s, v in summary["starters"].items() if v["conflict"])
    return summary


def missing_fields(research: dict, required: tuple[str, ...]) -> list[str]:
    """[§8-22] 아직 빈 필드 목록 — **딥서치를 여기에만 쓴다.**

    크롤링이 채운 것을 다시 묻지 않으면 쿼터가 남고, 짧은 질문이라 채움률도 높다
    (실측: 프롬프트가 길수록 모델이 검색을 포기한다).
    """
    out = []
    for path in required:
        cur: object = research
        for part in path.split("."):
            cur = (cur or {}).get(part) if isinstance(cur, dict) else None
        if cur in (None, "", [], {}):
            out.append(path)
    return out
