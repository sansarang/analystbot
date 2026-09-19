"""[EXP-2] T-3h·T-60 자동 내보내기 — 단계 인자·파일명·출력 위치·스케줄러 잡.

🔴 이 파일이 잠그는 것은 **네 가지**다.
   ① `--stage {t3h,lineup}` 인자가 있다.
   ② 단계가 파일명에 나타난다 — `lineup` 은 `_lineup` 접미사를 붙인다.
   ③ 출력 디렉토리가 **환경에 따라 갈린다** — 컨테이너에서는 볼륨, 로컬에서는
      다운로드 폴더. 컨테이너 파일시스템은 재배포마다 지워지므로(→ FORKS F-18)
      볼륨 밖에 쓰면 백업이 아니다.
   ④ 스케줄러가 두 시점에 그것을 부른다.

⚠️ 네트워크·DB 를 타지 않는다 — 순수 함수와 잡 등록 목록만 본다.
"""
from __future__ import annotations

import pathlib

import pytest


# ── ① 단계 인자

def test_stage_인자가_있다():
    import argparse

    from app.export import for_fable as F

    ap = argparse.ArgumentParser()
    # 파서를 직접 만들지 않는다 — 모듈이 내보내는 것을 본다.
    assert hasattr(F, "STAGES"), "STAGES 목록이 없다"
    assert set(F.STAGES) == {"t3h", "lineup"}, F.STAGES
    del ap


# ── ② 파일명 규칙

def test_lineup_단계는_접미사가_붙는다(tmp_path, monkeypatch):
    from app.export import for_fable as F

    monkeypatch.setattr(F, "OUT_DIR", tmp_path)
    a = F.out_path("2026-09-19", "mlb", stage="t3h")
    b = F.out_path("2026-09-19", "mlb", stage="lineup")
    assert a.name == "2026-09-19_mlb_slate.json", a.name
    assert b.name == "2026-09-19_mlb_slate_lineup.json", b.name


def test_같은_단계를_다시_돌리면_덮지_않는다(tmp_path, monkeypatch):
    from app.export import for_fable as F

    monkeypatch.setattr(F, "OUT_DIR", tmp_path)
    p1 = F.out_path("2026-09-19", "mlb", stage="lineup")
    p1.write_text("x", encoding="utf-8")
    p2 = F.out_path("2026-09-19", "mlb", stage="lineup")
    assert p2.name == "2026-09-19_mlb_slate_lineup_r2.json", p2.name


# ── ③ 출력 위치 — 볼륨이 있으면 볼륨

def test_볼륨이_있으면_거기_쓴다(monkeypatch, tmp_path):
    vol = tmp_path / "vol"
    vol.mkdir()
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", str(vol))
    from app.export import for_fable as F

    got = F.resolve_out_dir()
    assert got == vol / "export", got


def test_볼륨이_없으면_다운로드_폴더다(monkeypatch):
    monkeypatch.delenv("RAILWAY_VOLUME_MOUNT_PATH", raising=False)
    from app.export import for_fable as F

    got = F.resolve_out_dir()
    assert got == pathlib.Path.home() / "Downloads" / "analystbot_export", got


# ── ④ 스케줄러 잡

def test_스케줄러가_두_시점에_내보낸다():
    from app import scheduler as S

    ids = {spec[0] for spec in S._job_specs()}
    assert "export_t3h_10m" in ids, sorted(ids)
    assert "export_lineup_5m" in ids, sorted(ids)


@pytest.mark.parametrize("name", ["export_t3h_job", "export_lineup_job"])
def test_잡_함수가_존재한다(name):
    from app import scheduler as S

    assert hasattr(S, name), name
