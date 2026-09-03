"""[리허설] 격리가 **실제로 격리인지**를 잠근다.

🔴 리허설이 실캐시나 실발송으로 새면, 그날 슬레이트가 리허설 결과로
   오염된다. 특히 `judge_prompt:*` 가 새면 저녁 L1 이 리허설 판정의
   프롬프트를 진짜로 알고 대조한다 — 감시가 거짓을 검증하게 된다.
"""
from pathlib import Path

import pytest

from tools.rehearsal import PREFIX, RehearsalRedis

SRC = Path("tools/rehearsal.py").read_text(encoding="utf-8")


class Fake:
    def __init__(self):
        self.keys = {}

    async def get(self, k):
        return self.keys.get(k)

    async def set(self, k, v, **kw):
        self.keys[k] = v

    async def hincrby(self, k, f, n):
        self.keys.setdefault(k, {})[f] = self.keys.setdefault(k, {}).get(f, 0) + n

    async def scan_iter(self, match, count=100):
        for k in list(self.keys):
            yield k

    async def delete(self, k):
        self.keys.pop(k, None)


@pytest.mark.asyncio
async def test_every_key_is_prefixed():
    f = Fake()
    r = RehearsalRedis(f)
    await r.set("analysis:kbo:2026-09-03", "x")
    await r.set("judge_prompt:123", "y")
    await r.hincrby("dispatch:kbo:2026-09-03", "sent", 1)
    assert all(k.startswith(PREFIX) for k in f.keys), \
        f"실 키로 샜다: {[k for k in f.keys if not k.startswith(PREFIX)]}"
    assert f"{PREFIX}judge_prompt:123" in f.keys


@pytest.mark.asyncio
async def test_reads_are_prefixed_too():
    """쓰기만 막고 읽기를 실 키로 하면 실판정을 리허설 결과로 착각한다."""
    f = Fake()
    f.keys["analysis:kbo:2026-09-03"] = "REAL"
    r = RehearsalRedis(f)
    assert await r.get("analysis:kbo:2026-09-03") is None


@pytest.mark.asyncio
async def test_cleanup_removes_everything():
    from tools.rehearsal import _cleanup

    f = Fake()
    r = RehearsalRedis(f)
    await r.set("analysis:kbo:x", "1")
    await r.set("judge_prompt:9", "2")
    assert await _cleanup(f) == 0
    assert not f.keys


def test_both_send_paths_are_blocked():
    """목이 둘이다 — `alerts._send` 와 `notify.send_telegram`."""
    assert "A._send = capture" in SRC
    assert "N.send_telegram = capture" in SRC


def test_ledger_and_audit_writes_are_blocked():
    assert "PL.record_analysis = no_record" in SRC
    assert "_spawn_fact_audit" in SRC
    # 감시 테이블 저장 함수를 부르지 않는다
    for banned in ("_store_review(", "_store_shadow(", "_review_one(",
                   "_shadow_one(", "run_panel("):
        assert banned not in SRC, f"리허설이 {banned} 로 감시 테이블에 쓴다"


def test_guards_are_restored():
    """가드를 안 풀면 그 프로세스는 남은 하루 동안 발송을 못 한다."""
    assert "_remove_guards" in SRC and "finally:" in SRC
    assert "A._send = s[\"send\"]" in SRC
    assert "N.send_telegram = s[\"tg\"]" in SRC


def test_stops_after_17_kst():
    assert "now.hour >= 17" in SRC, "실슬레이트 창에서 멈추지 않는다"


def test_hook_is_flag_gated():
    sch = Path("app/scheduler.py").read_text(encoding="utf-8")
    assert 'os.getenv("REHEARSAL") == "1"' in sch


def test_required_materials_are_named():
    """공시 전에도 차 있어야 하는 자료를 **명시**한다 — 판단을 미루지 않는다."""
    from tools.rehearsal import OK_TO_BE_EMPTY, REQUIRED_BEFORE_LINEUP

    assert "3타순" in OK_TO_BE_EMPTY
    for k in ("1박스", "7선발시즌", "8타선시즌", "9불펜"):
        assert k in REQUIRED_BEFORE_LINEUP
