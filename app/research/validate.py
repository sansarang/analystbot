"""리서치 응답 검증 — 프롬프트 문구·"확인 불가" 산문을 데이터로 내보내지 않기 위한 게이트.

실사고: Perplexity가 데이터를 못 찾으면 우리가 보낸 요청 문구를 되풀이하는 산문
("최근 5~7경기별 일자·상대·이닝·실점·피OPS 등을 확인할 수 있는 로그에 접근할 수 없어…")
을 돌려주는데, 이것이 recent_form/last5 필드에 그대로 담겨 "선발 최근:" 자리에
데이터인 척 출력됐다. 이 모듈은 그런 값을 **무효**로 만들어 '리서치 실패'로 표시하게 한다.

무효 판정 기준 (텍스트 필드):
  1) 미확보 산문   — "확인할 수 없", "접근할 수 없", "확인 불가", "미확인" 등
  2) 프롬프트 반향 — 우리가 보낸 프롬프트·스키마 문구와 토큰이 과하게 겹침
  3) 숫자 없음     — 수치를 요구한 필드인데 숫자가 하나도 없음
"""

import logging
import re

logger = logging.getLogger(__name__)

# 1) 데이터가 아니라 "못 찾았다"는 진술 — 어떤 필드에서도 데이터로 쓰지 않는다.
UNAVAILABLE_MARKERS = (
    "확인할 수 없", "확인하기 어렵", "확인 불가", "확인되지 않", "확인하지 못", "확인 못",
    "접근할 수 없", "접근이 불가", "접근 불가", "제공할 수 없", "제공하기 어렵",
    "제시할 수 없", "제시하기 어렵", "요약할 수 없", "조회할 수 없", "조회가 불가",
    "찾을 수 없", "검색되지 않", "알 수 없", "판단하기 어렵", "판단이 불가",
    "산출할 수 없", "특정할 수 없", "구할 수 없", "업데이트되어 있지 않",
    "데이터 부족", "데이터가 부족", "정보가 없", "정보 없음", "자료가 없",
    "부족합니다", "부족하다", "부족한 상태", "수치가 부족", "자료가 부족", "정보가 부족",
    "미확인", "미상", "불가합니다", "불가하다", "불가능", "확정 불가", "파악 불가",
    "not available", "unable to", "cannot access", "can't access", "no data",
    "unavailable", "n/a", "not found", "insufficient data",
    # 2026-08-25 프리페치 감사에서 통과해 버린 미탐 표현 보강
    "제공되지 않", "확보되지 않", "포함되어 있지 않", "노출되지 않", "제시하지 않",
    "찾기 어려", "설명하기 어려", "계산할 수 없", "파악할 수 없", "집계할 수 없",
    "데이터가 없", "로그가 없", "직접 데이터가 없", "한계가 있",
    # [§8-14] 2026-08-26 KBO 실호출에서 통과해 버린 미탐 표현.
    #   실제 응답: "…세부 로그에 현재 바로 접근이 되지 않아, 구체적인 최근 5경기
    #   ERA·피OPS·평균 소화 이닝을 숫자로 정리하기 어렵다"
    #   → 문장에 숫자([13]·5경기)가 있어 숫자 요구 조건을 통과했고,
    #     "접근이 되지 않"·"정리하기 어렵"이 목록에 없어 미확보 판정도 피했다.
    #   ⚠️ 반대 위험(정상 문장 폐기)을 함께 재야 한다 — 아래 테스트가 그 역할이다.
    "접근이 되지 않", "접근되지 않", "정리하기 어렵", "정리할 수 없",
    "확보하기 어렵", "수집되지 않", "기재되어 있지 않", "명시되어 있지 않",
)

# 결장 정보에 정상적으로 등장하는 "불가" 표현 — 미확보 산문으로 오판하지 않도록 제외
_KEEP_PHRASES = ("출전 불가", "출장 불가", "기용 불가", "선발 불가")

# 2) 프롬프트·스키마에서만 쓰는 지시 문구 — 응답에 남아 있으면 반향(echo)이다.
INSTRUCTION_MARKERS = (
    "(한국어)", "한국어로", "요약(한국어", "없으면 빈 배열", "…동일…", "...동일",
    "동일...", "등을 확인", "등을 조사", "등을 정리", "output only", "json object",
    "or null", "null/empty", "must be", "최신부터)", "빈 배열",
    "조사하라", "정리하라", "제시하라", "포함하라", "나열하라", "찾아라",
)

# 승/무/패 폼 문자열 (예: "WWLWL", "WDWDW")
_FORM_RE = re.compile(r"\b([WLDwld]{2,10})\b")
_TOKEN_RE = re.compile(r"[가-힣A-Za-z]{2,}")
# 진짜 데이터는 필드 설명과 어휘가 겹칠 수밖에 없다("최근 5경기 ERA 2.41…").
# 임계값을 높게 두고, 순수 자리표시자는 INSTRUCTION_MARKERS로 잡는다.
_ECHO_JACCARD = 0.72  # 프롬프트 문구와 토큰 집합이 이만큼 겹치면 반향으로 본다
_ECHO_MIN_REF = 5     # 너무 짧은 프롬프트 조각은 오탐 방지를 위해 비교 대상에서 제외

_corpus_cache: list[set[str]] | None = None


def _prompt_corpus() -> list[set[str]]:
    """deep.py의 프롬프트·스키마 문구를 토큰 집합으로 캐시 (지연 임포트 — 순환 방지)."""
    global _corpus_cache
    if _corpus_cache is None:
        from app.research import deep

        raw = "\n".join([
            deep.PROMPT, deep._SCHEMA_MLB, deep._SCHEMA_SOCCER, *deep.TARGETS.values(),
        ])
        _corpus_cache = [
            set(_TOKEN_RE.findall(line)) for line in re.split(r"[\n,\"]", raw)
            if len(_TOKEN_RE.findall(line)) >= _ECHO_MIN_REF
        ]
    return _corpus_cache


# "…하기 어렵다/어려움" 형태의 미확보 진술. '타선 공략이 어렵다' 같은 정상 평가와
# 섞이지 않도록 '<동작>하기 어렵'으로 한정한다 (어렵/어려 두 활용형 모두 커버).
_HARD_TO_RE = re.compile(
    r"(확인|파악|산출|제시|설명|비교|요약|특정|집계|판단|조회|검증|추정|재구성|찾)하?기\s*(가\s*)?어[렵려]"
)


def _strip_keep_phrases(text: str) -> str:
    for phrase in _KEEP_PHRASES:
        text = text.replace(phrase, "")
    return text


def is_unavailable_prose(text: str) -> bool:
    """'데이터를 못 찾았다'는 진술인가."""
    stripped = _strip_keep_phrases(str(text))
    if _HARD_TO_RE.search(stripped):
        return True
    lowered = stripped.lower()
    return any(m.lower() in lowered for m in UNAVAILABLE_MARKERS)


def is_prompt_echo(text: str) -> bool:
    """우리가 보낸 프롬프트·스키마 문구를 되풀이한 값인가."""
    s = str(text)
    if any(m.lower() in s.lower() for m in INSTRUCTION_MARKERS):
        return True
    tokens = set(_TOKEN_RE.findall(s))
    if len(tokens) < _ECHO_MIN_REF:
        return False
    for ref in _prompt_corpus():
        # 자카드 — 한쪽이 짧다는 이유로 반향 판정되는 오탐을 막는다
        if len(tokens & ref) / len(tokens | ref) >= _ECHO_JACCARD:
            return True
    return False


# 문장 분리 — 소수점(2.80, .781)에서 끊기지 않도록 마침표 뒤 공백/개행만 경계로 본다
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def filter_sentences(text) -> str | None:
    """문장 단위로 미확보 진술만 걷어내고 실데이터 문장은 남긴다.

    딥서치는 "A는 24.2이닝을 소화했다. 다만 3일 단위 분리는 불가능하다."처럼
    실수치와 '못 찾았다' 단서를 한 값에 섞어 보낸다. 통째로 버리면 실데이터가
    같이 사라지고, 통째로 살리면 비데이터가 데이터인 척 나간다 — 문장으로 가른다.
    (단, '최근 5경기'처럼 구간을 단언하는 필드는 이 함수를 쓰지 않는다. 시즌 수치만
     남아 최근 성적인 척 표기되는 새로운 오표기를 만들기 때문.)
    """
    parts = [s.strip() for s in _SENTENCE_RE.split(str(text)) if s.strip()]
    kept = [s for s in parts if not is_unavailable_prose(s)]
    if not kept:
        return None
    joined = " ".join(kept)
    return joined if re.search(r"\d", joined) else None


def invalid_reason(text, *, require_number: bool = True) -> str | None:
    """텍스트 필드의 무효 사유. 유효하면 None.

    반환: 'empty' | 'unavailable' | 'prompt_echo' | 'no_number'
    """
    if text is None:
        return "empty"
    s = str(text).strip()
    if not s:
        return "empty"
    if is_unavailable_prose(s):
        return "unavailable"
    if is_prompt_echo(s):
        return "prompt_echo"
    if require_number and not re.search(r"\d", s):
        return "no_number"
    return None


def clean_text(text, *, require_number: bool = True, sentencewise: bool = False) -> str | None:
    """유효하면 원문, 무효면 None.

    sentencewise=True(자유서술 필드)는 미확보 문장만 걷어내고 나머지를 남긴다.
    """
    reason = invalid_reason(text, require_number=require_number)
    if reason is None:
        return str(text).strip()
    if sentencewise and reason == "unavailable":
        return filter_sentences(text)
    return None


# [§8-17] 한국어·일본어 승패 표기 → W/L/D.
#   실사고(2026-08-26 KBO): 딥서치는 한국어로 답하는데 필터가 **영문 W/L만** 받아
#   '승승패승패'가 통째로 폐기됐다. "못 가져왔다"가 아니라 "가져왔는데 버렸다"였다.
#   구분자(-·,·공백)도 흔하다: '승-패-승-승-패'.
_FORM_CHARS = {"승": "W", "패": "L", "무": "D",      # 한국어
               "勝": "W", "敗": "L", "分": "D",      # 일본어
               "W": "W", "L": "L", "D": "D",
               "w": "W", "l": "L", "d": "D"}
_FORM_SEP = " -·,/|>→"


def clean_form(value) -> str | None:
    """폼 문자열에서 W/L/D 시퀀스 추출. 한국어(승패무)·일본어(勝敗分)도 받는다.

    'WWLWL (최근 5경기, 최신부터)' → 'WWLWL'
    '승승패승패' · '승-패-승-승-패' → 'WWLWL' / 'WLWWL'
    ⚠️ '5경기 3승 2패'처럼 **집계 서술**은 순서 정보가 없다 — 폼이 아니므로 받지 않는다.
    """
    if not value:
        return None
    s = str(value).strip()
    if is_unavailable_prose(s):
        return None
    m = _FORM_RE.search(s.upper())
    if m:
        return m.group(1)
    # 한/일 표기: 승패무와 구분자만으로 이뤄진 연속 구간을 찾는다.
    #   숫자가 앞에 붙은 '3승 2패'는 집계이므로 제외한다(숫자+승패 패턴 차단).
    if re.search(r"\d\s*[승패무勝敗分]", s):
        return None
    best = ""
    cur = ""
    for ch in s:
        if ch in _FORM_CHARS:
            cur += _FORM_CHARS[ch]
        elif ch in _FORM_SEP and cur:
            continue                      # 구분자는 시퀀스를 끊지 않는다
        else:
            best, cur = (cur if len(cur) > len(best) else best), ""
    best = cur if len(cur) > len(best) else best
    return best[:10] if 2 <= len(best) <= 10 else None


def clean_number(value) -> float | int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ 페이로드 정제

_TEXT_FIELDS_NUM = ("last5", "note", "home_split", "away_split", "last5_detail",
                    "splits", "bullpen", "h2h_history")

# [4-1] 신규 자유서술 필드 — 문장 필터 대상(수치 요구 없음: 정성 정보라도 가치가 있다)
#
# [§8-7] motivation·schedule_load·umpire도 여기에 둔다.
#   정책 판단 근거(CLAUDE.md: "라벨이 무엇을 단언하는가로 나눈다"):
#   이 넷은 **구간을 단언하지 않는다** — last5("최근 5경기")처럼 표본 범위를
#   못 박는 라벨이 아니라 상황 서술이다. 따라서 전량 폐기가 아니라 문장 필터가 맞다.
#   미확보 문장("정보를 찾을 수 없습니다")만 걷어내고 나머지는 살린다.
_TEXT_FIELDS_FREE = ("rotation_plan", "park", "weather",
                     "motivation", "schedule_load", "umpire")
_NUM_FIELDS = ("runs_avg", "gf5", "ga5", "rank", "era_recent", "era_season")


def _clean_form_block(block, dropped: list[str], prefix: str) -> dict:
    if not isinstance(block, dict):
        return {}
    out: dict = {}
    form = clean_form(block.get("form"))
    if form:
        out["form"] = form
    elif block.get("form"):
        dropped.append(f"{prefix}.form")
    for key in _NUM_FIELDS:
        if key in block:
            val = clean_number(block.get(key))
            if val is not None:
                out[key] = val
            elif block.get(key) is not None:
                dropped.append(f"{prefix}.{key}")
    for key in _TEXT_FIELDS_NUM:
        if key in block:
            val = clean_text(block.get(key), sentencewise=True)
            if val:
                out[key] = val
            elif block.get(key):
                dropped.append(f"{prefix}.{key}")
    return out


def sanitize_research(data: dict | None, sport: str = "mlb") -> tuple[dict, list[str]]:
    """리서치 페이로드에서 무효 값을 제거. 반환 (정제본, 제거된 필드 경로들).

    캐시에 이미 들어간 오염 데이터도 렌더 직전에 한 번 더 통과시켜 차단한다.
    """
    if not isinstance(data, dict):
        return {}, []
    dropped: list[str] = []
    out: dict = {}

    for side in ("home_recent_form", "away_recent_form"):
        block = _clean_form_block(data.get(side), dropped, side)
        if block:
            out[side] = block

    for side in ("home_pitcher", "away_pitcher"):
        src = data.get(side)
        if not isinstance(src, dict):
            continue
        block: dict = {}
        if src.get("name"):
            block["name"] = str(src["name"]).strip()
        for key in ("era_recent", "era_season"):
            val = clean_number(src.get(key))
            if val is not None:
                block[key] = val
        last5 = clean_text(src.get("last5"))
        if last5:
            block["last5"] = last5
        elif src.get("last5"):
            dropped.append(f"{side}.last5")
        if src.get("trend") in ("악화", "개선", "유지"):
            block["trend"] = src["trend"]
        if block:
            out[side] = block

    for key in ("splits", "bullpen", "h2h_history"):
        val = clean_text(data.get(key), sentencewise=True)
        if val:
            out[key] = val
        elif data.get(key):
            dropped.append(key)

    # 로테이션 계획·구장·날씨는 수치가 없어도 의미가 있다 (숫자 요구 없이 문장 필터만)
    for key in _TEXT_FIELDS_FREE:
        val = clean_text(data.get(key), require_number=False, sentencewise=True)
        if val:
            out[key] = val
        elif data.get(key):
            dropped.append(key)

    if str(data.get("bullpen_overused") or "").strip() in ("홈", "원정", "양팀"):
        out["bullpen_overused"] = data["bullpen_overused"].strip()

    # [§8-16] 라인업 — **'확정'은 강한 단언이다.** 상태값이 정확히 confirmed/projected일
    #   때만 받고, 명단 문장은 문장 필터를 통과한 것만 남긴다.
    #   예상을 확정으로 받으면 '최종 픽' 자격이 잘못 부여된다(라인업 2단계 규율).
    lu = data.get("lineup")
    if isinstance(lu, dict):
        status = str(lu.get("status") or "").strip().lower()
        if status in ("confirmed", "projected"):
            block = {"status": status}
            for side in ("home", "away"):
                txt = clean_text(lu.get(side), require_number=False, sentencewise=True)
                if txt:
                    block[side] = txt
            src = str(lu.get("source") or "").strip()
            if src and src.lower() not in ("null", "none", "unknown"):
                block["source"] = src[:80]
            # 명단이 한쪽도 없으면 '확정'이라 주장할 근거가 없다 — 상태만 남기지 않는다
            if block.get("home") or block.get("away"):
                out["lineup"] = block
            else:
                dropped.append("lineup(명단 없음)")
        elif lu:
            dropped.append("lineup")

    # 확률 모델(포아송 λ)이 직접 쓰는 수치 필드 — 숫자로 파싱되면 그대로 보존한다.
    # 산문 검증(문장 필터)은 적용하지 않는다: 수치는 산문이 아니다.
    for side in ("home_pitcher", "away_pitcher"):
        src, dst = data.get(side), out.get(side)
        if isinstance(src, dict) and isinstance(dst, dict):
            for key in ("ip_avg_recent", "siera", "xfip", "fip"):
                val = clean_number(src.get(key))
                if val is not None:
                    dst[key] = val
            hand = str(src.get("throws") or "").strip().upper()[:1]
            if hand in ("L", "R"):
                dst["throws"] = hand

    for side in ("home_offense", "away_offense"):
        block = data.get(side)
        if not isinstance(block, dict):
            continue
        kept = {}
        for key in ("woba_30d", "obp_30d", "iso_30d", "k_pct", "bb_pct",
                    "vs_lhp_woba", "vs_rhp_woba", "woba", "obp"):
            val = clean_number(block.get(key))
            if val is not None:
                kept[key] = val
        if kept:
            out[side] = kept

    for side in ("home_bullpen", "away_bullpen"):
        block = data.get(side)
        if not isinstance(block, dict):
            continue
        kept = {}
        for key in ("era", "fip", "ip_last3d"):
            val = clean_number(block.get(key))
            if val is not None:
                kept[key] = val
        if isinstance(block.get("closer_available"), bool):
            kept["closer_available"] = block["closer_available"]
        if kept:
            out[side] = kept

    for key in ("park_factor",):     # park_hr은 소비처가 0곳이라 폐기했다
        val = clean_number(data.get(key))
        if val is not None:
            out[key] = val

    # 축구 xG — recent_form 블록 안의 수치
    for side in ("home_recent_form", "away_recent_form"):
        src, dst = data.get(side), out.get(side)
        if isinstance(src, dict) and isinstance(dst, dict):
            for key in ("xg6", "xga6"):
                val = clean_number(src.get(key))
                if val is not None:
                    dst[key] = val

    absences = []
    for item in data.get("absences") or []:
        # 결장자는 수치가 없어도 유효 (이름 자체가 데이터)
        if clean_text(item, require_number=False):
            absences.append(str(item).strip())
        elif item:
            dropped.append("absences[]")
    out["absences"] = absences

    reversal = []
    for item in data.get("form_reversal") or []:
        if clean_text(item):
            reversal.append(str(item).strip())
        elif item:
            dropped.append("form_reversal[]")
    out["form_reversal"] = reversal

    picks = []
    for pk in data.get("expert_picks") or []:
        if not isinstance(pk, dict) or not str(pk.get("pick") or "").strip():
            continue
        pk = dict(pk)
        # 출처 URL도 전문가 이름도 없는 픽은 인용 불가 — 2-소스 룰의 '전문가 축'이 될 수 없다
        expert = str(pk.get("expert") or "").strip()
        url = str(pk.get("source_url") or "").strip()
        if not url and (not expert or is_unavailable_prose(expert)):
            dropped.append("expert_picks[] (출처·전문가 미상)")
            continue
        if pk.get("reasoning") and not clean_text(pk["reasoning"], require_number=False):
            dropped.append("expert_picks[].reasoning")
            pk["reasoning"] = None
        picks.append(pk)
    out["expert_picks"] = picks

    scores = [s for s in data.get("predicted_scores") or []
              if re.search(r"\d\s*[-:]\s*\d", str(s))]
    out["predicted_scores"] = scores

    if dropped:
        logger.warning("[validate] 무효 리서치 필드 %d개 제거: %s", len(dropped), dropped[:8])
    return out, dropped


def research_materials(data: dict | None) -> dict:
    """분석 재료 유무 — {'form': bool, 'experts': bool, 'absences': bool}."""
    d = data or {}
    form = any(
        (d.get(side) or {}).get("form") is not None
        or any((d.get(side) or {}).get(k) is not None for k in _NUM_FIELDS)
        or any((d.get(side) or {}).get(k) for k in _TEXT_FIELDS_NUM)
        for side in ("home_recent_form", "away_recent_form")
    )
    pitcher = any(
        (d.get(side) or {}).get("last5") or (d.get(side) or {}).get("era_recent") is not None
        for side in ("home_pitcher", "away_pitcher")
    )
    return {
        "form": bool(form or pitcher),
        "experts": bool(d.get("expert_picks")),
        "absences": bool(d.get("absences")),
    }


def has_material(data: dict | None) -> bool:
    """recent_form·전문가 픽·부상 정보 중 하나라도 실재하는가."""
    return any(research_materials(data).values())
