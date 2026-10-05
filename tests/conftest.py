"""픽스처 + 🔴 **단계 잠금**(v4 §13-2).

asyncio 표식만 두던 파일이다. 단계 2-0 에서 **수집 훅**이 붙었다 — 승인 서명이
없는 단계의 테스트는 **수집조차 되지 않는다.**

⚠️ 판단은 `tests/stage_gate.py` 가 한다. 여기는 그 판단을 pytest 에 이어 주는
   배선뿐이다 — 규칙을 두 곳에 적지 않는다.
"""
import os
import pathlib
import shutil
import sys
import sysconfig

import pytest

import tests.stage_gate as stage_gate

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: 잠겨서 버린 경로의 사유. 🔴 보고에 이름으로 낸다(조용한 0 금지).
_LOCK_NOTES = pytest.StashKey[list]()


def pytest_configure(config):
    config.addinivalue_line("markers", "asyncio: 비동기 계약")
    _drop_bytecode()
    _unplug_env()
    _unplug_ledger()
    _unplug_model()


def _unplug_model() -> str:
    """🔴🔴 **테스트는 실모델을 올리지 않는다** — 사용자 지시 2026-10-05.

    > 테스트 중 모델 예열 **금지**: 진입점 예열은 `ANALYSTBOT_TEST=1`
    > (conftest 에서 설정)이면 건너뛴다. 재정렬이 필요한 계약은 **가짜
    > 재정렬기**(고정 점수 반환)를 주입한다. 실모델 계약은
    > `@pytest.mark.slow` 로 따로 분리.

    ⚠️ 왜 — 스위트가 **11분+** 이었다. 🔴 재정렬 계약 파일 하나가 13초였고,
       그 대부분이 `bge-reranker-v2-m3`(수 GB)를 mps 에 올리는 시간이다.
    """
    os.environ["ANALYSTBOT_TEST"] = "1"
    return "1"


def _unplug_ledger() -> str:
    """🔴🔴 **계약은 이 기계의 비용 원장을 읽지 않는다**(2026-10-05).

    ══════════════════════════════════════════════════════════════════
    🔴 왜 이 자리가 생겼나 — 실사고 2026-10-05
    ══════════════════════════════════════════════════════════════════

    봇을 하루에 여러 번 돌려 **하루 상한에 닿자**(오늘 $3.0074 / 상한 $3.00)
    LLM 을 부르는 계약 **10건이 한꺼번에 빨개졌다**:

    ```
    🔴 합산 예산 가드가 막았다: day_cap_stop: 오늘 $3.0074 / 상한 $3.00
    ```

    ⚠️ 그 10건은 **봇 결함이 아니다** — 기계 상태다. 🔴 `_unplug_env` 가 `.env`
       를 떼어 낸 것과 **같은 이유**로 원장도 뗀다: 계약은 이 기계가 오늘 얼마를
       썼는지에 따라 색이 바뀌면 안 된다.
    ⚠️ 예산 가드 **자체를 시험하는 계약**은 자기 원장을 주입해서 본다
       (`write_ledger(root=…)`) — 그 길은 막히지 않는다.
    """
    import tempfile

    from app import solar

    box = tempfile.mkdtemp(prefix="ledger-unplug-")
    # 🔴 `solar.ROOT` 를 돌린다 — 원장 경로를 정하는 **하나뿐인 자리**다.
    #    ⚠️ 예산 가드를 시험하는 계약은 `monkeypatch.setattr(solar, "ROOT", …)`
    #       로 **자기 폴더**를 주입한다 — 같은 통로이므로 덮어쓰기가 깨끗하다.
    solar.ROOT = pathlib.Path(box)
    return box


def _unplug_env() -> list[str]:
    """🔴🔴 **계약은 이 기계의 `.env` 를 읽지 않는다**(2026-10-04).

    ══════════════════════════════════════════════════════════════════
    🔴 왜 — 결정 ③이 그 결합을 드러냈다
    ══════════════════════════════════════════════════════════════════

    `app/__init__.py` 가 `.env` 를 **`os.environ` 으로** 올린다. 그래서 내 기계의
    `AGENT_ENABLED=true` 가 스위트에 그대로 들어왔고, 결정 ③(에이전트가 켜지면
    세포는 검색하지 않는다)을 넣자 **세포 검색 경로를 시험하는 39건이 빨개졌다.**

    🔴 그 39건은 **멀쩡하다** — 그들은 에이전트가 **꺼져 있을 때**의 길을
       시험한다. ⚠️ 빨개진 까닭은 *"계약 결과가 이 기계의 설정에 달려 있었다"*
       는 것이고, 그것이 진짜 결함이다: 같은 코드가 기계마다 다른 색을 낸다.

    🔴 그래서 **스위치를 뽑는다** — 스위치를 켜고 도는 길은 그 스위치를
       **스스로 켜는 계약**이 시험한다(`test_dec3_cells_no_search.py` 가
       `may_search(agent_on=True)` 를 직접 묻는다).
    ⚠️ 돈·발송처럼 **꺼져 있어야 하는** 것은 건드리지 않는다 — 여기서 뽑는 것은
       *"기능을 켜는"* 스위치뿐이고, 그 목록을 **글로** 남긴다(#3).
    """
    pulled = []
    for key in ("AGENT_ENABLED",):
        if os.environ.get(key):
            pulled.append(f"{key}={os.environ[key]}")
        os.environ[key] = ""
    # 🔴 `get_settings` 는 `lru_cache` 다 — 뽑은 뒤 **비워야** 먹는다
    try:
        from app.config import get_settings
        get_settings.cache_clear()
    except Exception:                                   # noqa: BLE001
        pass
    return pulled


def _drop_bytecode() -> list[str]:
    """🔴🔴 **스위트 시작 전에 `__pycache__` 를 지운다** — 구조로 막는다.

    ══════════════════════════════════════════════════════════════════
    🔴 왜 규율이 아니라 여기인가 — 같은 함정에 **두 번** 빠졌다
    ══════════════════════════════════════════════════════════════════

    ⚠️ 2026-10-02: `effect_of("느낌")` 가 코드를 되돌린 뒤에도 `제거` 를 냈다.
    ⚠️ 2026-10-04: 돌연변이를 되돌린 뒤 `test_영어가_먼저다` 가 빨간 채였다.
       🔴 나는 그것을 **전역 오염으로 오진하고 네 번 헛짚었다**(디렉터리 이분 ·
       `label_of` 계측 · `is_code` 확인 · 고정물 재현).

    🔴 **사용자 지시 2026-10-04**: *"같은 함정에 두 번 빠졌으면 규율 한 줄로는
       세 번째를 못 막는다. 두 가지를 코드로 박아라 — 실행기에
       `PYTHONDONTWRITEBYTECODE=1` 을 고정하고, 스위트 시작 전에
       `__pycache__` 를 지운다."*

    ⚠️ `.venv` 와 표준 라이브러리는 **건드리지 않는다** — 우리가 고치는 코드가
       아니고, 지우면 다음 실행이 느려질 뿐이다.
    🔴 지운 자리를 **세어 돌려준다**(조용한 0 금지 · #3).
    """
    # 🔴 **이 프로세스**가 더 쓰지 않게 한다
    sys.dont_write_bytecode = True
    # 🔴 그리고 **자식 프로세스**도(계약 몇 개가 `subprocess` 로 pytest 를 부른다)
    #    ⚠️ 환경변수는 파이썬이 **시작할 때** 읽는다 — 그래서 이 프로세스에는
    #       위 한 줄이 필요하고, 자식에는 이 한 줄이 필요하다. 둘 다 있어야 한다.
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    # ⚠️ 이 변수를 `skip` 이라 불렀더니 **§13-2 계약이 걸렸다** — 그 계약은
    #    conftest 코드에 `skip` 이라는 글자가 있으면 *"잠금을 skip 으로 때웠다"*
    #    로 읽는다(거친 글자 검사지만 **그 계약이 옳다**). 🔴 이름을 비킨다.
    outside = {str(ROOT / ".venv"),
               str(sysconfig.get_paths().get("stdlib") or "")}
    got: list[str] = []
    for d in ROOT.rglob("__pycache__"):
        path = str(d)
        if any(path.startswith(x) for x in outside if x):
            continue
        shutil.rmtree(d, ignore_errors=True)
        got.append(path)
    return got


def pytest_ignore_collect(collection_path, config):
    """🔴 승인 서명 없는 단계의 경로를 **수집 전에** 버린다.

    v4 §13-2: *"승인 서명 파일이 없으면 다음 단계 테스트가 수집조차 되지
    않는다. 이 잠금을 우회하는 코드 변경은 계약 실패."*

    ⚠️ `pytest_collection_modifyitems` 로 **건너뛰기(skip)** 하면 안 된다 —
       그러면 수집은 되고 초록 옆에 s 가 붙어, 잠긴 것이 **있는 줄** 보인다.
       §13-2 는 "수집조차"라고 못 박았다.
    """
    why = stage_gate.is_locked(collection_path)
    if why is None:
        return None
    reason = f"🔴 단계 잠금 — {collection_path.name}: {why['why']}"
    config.stash.setdefault(_LOCK_NOTES, []).append(reason)
    return True



def pytest_report_collectionfinish(config):
    """🔴 **조용한 0 금지.** 무엇이 잠겨서 안 돌았는지 이름으로 남긴다.

    ⚠️ 이 줄이 없으면 "274 passed" 만 보이고, 잠긴 단계가 **없는 것처럼**
       읽힌다. 못 잰 칸은 이름으로 남긴다(CLAUDE.md §조용한 0 금지).
    """
    out = list(sorted(set(config.stash.get(_LOCK_NOTES, []))))
    # 🔴 **디렉터리가 아직 없어도 잠긴 단계는 말한다.** 훅은 존재하는 경로에만
    #    불리므로, 잠긴 것만 세면 `tests/stage3` 이 없는 동안 스위트는 "286
    #    passed" 만 내고 **잠긴 단계가 없는 것처럼** 읽힌다. 그것이 조용한 0 이다.
    locked = stage_gate.locked_dirs()
    if locked:
        stages = sorted({v["stage"] for v in locked.values()})
        out.append(f"🔒 단계 잠금(v4 §13-2) — 아직 승인 없어 닫힌 단계: "
                   f"{', '.join(str(s) for s in stages)} "
                   f"/ 열린 단계의 계약만 돌았다")
    return ["", *out] if out else []


# ══════════════════════════════════════════════════════════════════
# 🔴 **가짜 재정렬기** — 사용자 지시 2026-10-05 (2번)
# ══════════════════════════════════════════════════════════════════
#
#  > 재정렬이 필요한 계약은 **가짜 재정렬기**(고정 점수 반환)를 주입한다.
#
#  ⚠️ 고정 점수다 — **결정적**이어야 계약이 선다(지시서 §5 "결정성").
class FakeReranker:
    """🔴 고정 점수 재정렬기. ⚠️ 질의 낱말이 든 문서를 **앞으로** 보낸다.

    실모델의 *의미* 재정렬을 흉내내지 않는다 — 계약이 보는 것은
    **순서가 바뀌는가**와 **건수가 그대로인가**다.
    """

    def predict(self, pairs, batch_size: int = 16):
        out = []
        for q, doc in pairs:
            words = {w for w in str(q).lower().split() if len(w) > 2}
            low = str(doc).lower()
            out.append(float(sum(1 for w in words if w in low)))
        return out


@pytest.fixture
def fake_rerank(monkeypatch):
    """🔴 실모델 대신 **가짜**를 끼운다 — 계약이 13초를 안 쓴다."""
    from app.research import rerank
    rerank.reset()
    rerank.warm(_load=lambda: FakeReranker())
    yield rerank
    rerank.reset()
