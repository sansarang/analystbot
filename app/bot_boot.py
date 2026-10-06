"""🔴🔴 **기동 때 한 번 하는 검사들** — 지시서 2026-10-06 §2 (M129).

> 사전 검사(템플릿 로드 시) — 봇 시작 시 모든 템플릿을 고정물 경기 셋으로
> 렌더링해 §12-b 문지기와 길이 규칙(3~10단어)을 통과하는지 확인한다.
> **하나라도 걸리면 시작 실패**(조용히 건너뛰지 않는다).

🔴 **왜 기동인가** — 걸리는 템플릿은 그 유형을 **구조적으로 0건**으로 만든다.
   실측 2026-10-06: `squad_rotation`·`national_duty_return` 의 질의가 전부
   §12-b 에 걸려 그 두 유형이 카드에서 통째로 비었다. ⚠️ 그 사실은 **카드 블록
   1 을 읽어야** 보였다 — 기동에서 터지면 그 자리에서 보인다.

⚠️ 여기에 검사를 **늘릴 때는** 기동을 멈출 만한 것만 넣는다. 돌다가 고칠 수 있는
   것은 사유로 남기는 쪽이 맞다(§8-6).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def boot_checks() -> None:
    """🔴 기동 검사 — 걸리면 **터진다.**"""
    from app import queries
    queries.assert_templates_ok()
    logger.info("[boot] 질의 템플릿 사전 검사 통과(§2 · M129) — 템플릿 %d개",
                len(queries.template_precheck.__doc__ or "") and
                sum(1 for _ in _all_templates()))


def _all_templates():
    from app import rules
    for vtype in sorted(rules.variable_types()):
        yield from rules.type_templates_tagged(vtype)
