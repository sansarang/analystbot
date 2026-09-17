"""ODN-1-a 계약 — 매칭 SQL 의 `$2` 에 **명시 캐스트**가 있다.

🔴 배포 뒤 ⑨ 첫 사이클 실측:
     asyncpg UndefinedFunctionError: operator does not exist: timestamptz >= interval
   `$2` 가 산술에만 쓰여 타입을 못 정했다.
🔴 **스위트도 계약도 통과했었다** — SQL 을 실제로 안 돌리기 때문이다.
   ⑨ 가 아니었으면 못 봤다(ENGINEERING §4).
"""
import inspect
import re

from app import scheduler as S

SQL = inspect.getsource(S._match_oddsapinet).split('"""SELECT', 1)[1].split('"""', 1)[0]


def test_캐스트가_있다():
    assert "$2::timestamptz" in SQL


def test_BETWEEN_범위가_그대로다():
    """🔴 캐스트는 타입을 밝힐 뿐 범위를 안 바꾼다."""
    flat = " ".join(SQL.split())
    assert "BETWEEN" in flat
    assert flat.count("interval '3 hours'") == 2
    assert "- interval '3 hours'" in flat and "+ interval '3 hours'" in flat


def test_파라미터_수가_그대로다():
    assert sorted({int(x) for x in re.findall(r"\$(\d+)", SQL)}) == [1, 2]
