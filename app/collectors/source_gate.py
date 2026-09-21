"""[SRC-OFF / deepsearch_parallel [2]a] 소스 스위치 — **판단이 한 곳이다.**

🔴 **왜 있나.** `koreabaseball.com` 의 robots.txt 는 우리를 전 경로에서 거부한다
   (실측 2026-09-21 13:04 · HTTP 200 · EUC-KR):

       # 본 사이트의 데이터를 사전 승인 없이 자동 수집·크롤링·복제하는 행위를
       # 금지합니다.
       User-agent: Googlebot / Yeti / Daumoa / Bingbot   Disallow: /ws/
       User-agent: *                                     Disallow: /

   그런데 우리는 7경로를 치고 있었다(일정·팀기록·투수기록·엔트리·박스스코어).
   지시문 규율은 "차단을 우회하지 않는다"이고, robots 거부는 차단이다.

🔴 **코드를 지우지 않는다.** 정식 접근이 허락되면 `config/rules.yaml` 한 줄로
   되돌린다(사용자 지시: "코드 삭제가 아니라 기능 플래그로 끈다").

⚠️ **모르는 이름은 켜진 것으로 본다.** 게이트가 등록되지 않은 소스를 조용히
   끄면 그것이 더 큰 사고다 — 계약 테스트가 이 방향을 잠근다.
⚠️ 스위치 값의 원본은 `config/rules.yaml` 의 `sources.*` 하나다. 여기에
   기본값을 박지 않는다(사본 금지).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 왜 껐는지. 🔴 이유가 없으면 다음 사람이 그냥 켠다.
#  ⚠️ 문구는 robots 원문에서 따온다 — 해석을 적지 않는다.
REASONS: dict = {
    "koreabaseball": (
        "robots 거부 — koreabaseball.com/robots.txt 가 "
        "`User-agent: * / Disallow: /` 이고 "
        "'사전 승인 없이 자동 수집·크롤링·복제하는 행위를 금지합니다' 고지가 "
        "붙어 있다(실측 2026-09-21 · HTTP 200). 정식 접근 문의 중."),
    "naver_apigw": (
        "판단 불가로 중단 — api-gw.sports.naver.com 은 robots.txt 가 404 지만 "
        "같은 계열 sports.news.naver.com 이 `Disallow: /` 다. 판단이 설 때까지 "
        "끈다(사용자 지시 2026-09-21)."),
}


def enabled(name: str) -> bool:
    """이 소스를 써도 되나. 🔴 **모르면 켜진 것**이다.

    ⚠️ 설정을 못 읽어도 켜진 것으로 본다 — 게이트 고장이 수집 전체를
       조용히 멈추면 그게 더 나쁘다.
    """
    key = str(name or "").strip()
    if not key:
        return True
    try:
        from app.engine import rules as R

        v = R.get(f"sources.{key}.enabled")
    except Exception as exc:
        logger.debug("[source_gate] 설정 조회 실패 %s — 켜진 것으로 본다: %s",
                     key, exc)
        return True
    return True if v is None else bool(v)


def blocked_reason(name: str) -> str | None:
    """꺼져 있으면 **왜** 꺼졌나. 켜져 있으면 None."""
    if enabled(name):
        return None
    return REASONS.get(str(name or "").strip(),
                       "설정에서 꺼져 있다(사유 미기재)")


class SourceDisabled(RuntimeError):
    """꺼진 소스를 부르려 했다. 🔴 조용히 빈손을 돌려주지 않는다 —
    호출부가 '자료가 없다'와 '소스를 껐다'를 구분할 수 있어야 한다."""


def require(name: str) -> None:
    """꺼져 있으면 즉시 막는다. 🔴 **요청을 보내지 않는다.**"""
    if enabled(name):
        return
    raise SourceDisabled(f"{name}: {blocked_reason(name)}")
