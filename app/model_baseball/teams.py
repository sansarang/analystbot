"""[MBL-1] 팀 키.

🔴 **별칭표를 만들지 않는다.** MLB 는 statsapi 팀 id(정수)를 그대로 키로 쓴다 —
   이름 매칭은 이 저장소가 반복해 틀린 자리다(AC밀란↔인테르 오매칭, 소뱅 연전
   행 충돌). id 는 그런 사고가 구조적으로 불가능하다.
   KBO·NPB 는 6단계에서 붙인다.
"""
from __future__ import annotations

#: 표시용 이름. 적재할 때 statsapi 가 준 것을 그대로 담는다(손으로 적지 않는다).
NAME: dict[int, str] = {}


def remember(team_id, name) -> None:
    if team_id and name:
        NAME.setdefault(int(team_id), str(name))


def label(team_id) -> str:
    return NAME.get(int(team_id), str(team_id)) if team_id is not None else ""
