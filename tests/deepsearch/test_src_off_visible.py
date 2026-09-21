"""[2]b — 꺼진 소스를 **보이게** 한다.

🔴 왜. SRC-OFF 로 KBO 를 껐더니 `kbo_park.refresh` 가 `{'stadiums':0,'games':0}`,
   `kbo_usage.refresh` 가 `{'teams':0}` 을 **정상 반환**했다(실측 2026-09-21
   13:44 운영 컨테이너). 수집기가 `SourceDisabled` 를 잡아 삼키고 0 을 돌려주기
   때문이다. 읽는 쪽은 "오늘 자료가 없다"와 "소스를 껐다"를 구분할 수 없다 —
   CLAUDE.md 가 말하는 **조용한 0** 이다.

🔴 그래서 "미상으로 멈춤이 **의도한 동작**"임을 `/health` 와 export 에 사유와
   함께 찍는다(사용자 지시 2026-09-21).

⚠️ 문구·리그 매핑의 원본은 `config/rules.yaml` 의 `sources.*` 하나다.
   여기서도, 코드에서도 다시 적지 않는다(사본 금지) — 아래 계약이 그것을 잠근다.
"""
import pytest


def test_제한_목록은_꺼진_소스만_리그별로_묶는다():
    from app.collectors.source_gate import restrictions

    out = restrictions()
    assert out, "꺼진 소스가 있는데 제한 목록이 비었다"
    kbo = [x for x in out if x["league"] == "KBO"]
    assert len(kbo) == 1, f"KBO 가 한 줄로 묶이지 않았다: {out}"
    assert kbo[0]["defect"] == "D33"
    assert set(kbo[0]["sources"]) == {"koreabaseball", "naver_apigw"}
    # 사유는 source_gate.REASONS 가 원본이다 — 여기서 문구를 다시 적지 않는다
    from app.collectors.source_gate import REASONS
    assert all(REASONS[s] in kbo[0]["reason"] for s in kbo[0]["sources"])


def test_제한_줄의_형식(monkeypatch):
    from app.collectors.source_gate import restriction_lines

    lines = restriction_lines()
    assert any(ln.startswith("🔒 KBO — 자료 제한: 소스 중단(D33)") for ln in lines), lines


def test_켜면_줄이_사라진다(monkeypatch):
    """🔴 config 가 원본이다 — 코드에 박혀 있으면 이 시험이 실패한다."""
    from app.collectors import source_gate as G

    monkeypatch.setattr(G, "enabled", lambda name: True)
    assert G.restrictions() == []
    assert G.restriction_lines() == []


def test_모르는_소스는_제한에_안_들어간다(monkeypatch):
    from app.collectors import source_gate as G

    assert all(x["league"] for x in G.restrictions()), "리그 없는 제한 줄이 있다"


@pytest.mark.asyncio
async def test_health_에_제한_줄이_있다():
    from app.health import build_health

    body = await build_health(None, None)
    assert "KBO — 자료 제한: 소스 중단(D33)" in body, body[-600:]
    assert "robots" in body, "사유가 안 실렸다"


def test_export_에_restrictions_블록이_있다():
    from app.export.for_fable import restrictions_block

    b = restrictions_block()
    assert b["n"] == 1
    assert b["items"][0]["league"] == "KBO"
    assert b["items"][0]["defect"] == "D33"
    assert "robots" in b["items"][0]["reason"]
