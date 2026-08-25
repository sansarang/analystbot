"""실행 중인 코드의 버전 추적.

실사고(2026-08-25): 봇이 **26커밋 뒤처진 코드**로 하루 넘게 돌고 있었다.
그동안 만든 λ 모델·Statcast·라인무브가 사용자에게 하나도 도달하지 않았고,
아무도 그 사실을 알 수 없었다. 코드는 바뀌었는데 프로세스는 안 바뀌었다.

→ 기동 시 커밋 해시를 로그·알림에 남기고, 작업트리가 앞서 있으면 경고한다.
"""

import logging
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# 프로세스 기동 시각·커밋을 한 번만 고정한다 (이후 git이 바뀌어도 실행 중인 코드는 그대로)
_BOOT: "BuildInfo | None" = None


@dataclass
class BuildInfo:
    """이 프로세스가 실제로 실행 중인 코드의 정체."""

    commit: str              # 기동 시점 HEAD 짧은 해시
    subject: str             # 그 커밋의 제목
    committed_at: str        # 그 커밋 시각 (ISO)
    dirty: bool              # 기동 시 작업트리에 미커밋 변경이 있었는가
    started_at: datetime     # 프로세스 기동 시각 (UTC)

    @property
    def short(self) -> str:
        return f"{self.commit}{'+dirty' if self.dirty else ''}"


def _git(*args: str) -> str:
    """git 호출 — 실패하면 빈 문자열 (git이 없어도 크래시 금지)."""
    try:
        out = subprocess.run(
            ["git", *args], capture_output=True, text=True, timeout=5, check=False,
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("[version] git 호출 실패 %s: %s", args, exc)
        return ""


def _from_env() -> BuildInfo | None:
    """컨테이너 배포용 — 빌드 플랫폼이 주입한 커밋 정보.

    이미지에는 `.git`이 없다(비밀·용량 때문에 .dockerignore로 제외). git 호출은
    반드시 실패하므로, 배포 환경이 주는 환경변수를 1순위로 본다.
    이게 없으면 "지금 어떤 코드가 도는가"를 배포 후에 알 수 없어
    [6]에서 만든 버전 추적이 통째로 무력해진다.
    """
    sha = (os.getenv("RAILWAY_GIT_COMMIT_SHA")
           or os.getenv("GIT_COMMIT_SHA")
           or os.getenv("SOURCE_COMMIT"))
    if not sha:
        return None
    return BuildInfo(
        commit=sha[:7],
        subject=(os.getenv("RAILWAY_GIT_COMMIT_MESSAGE") or "(배포 커밋)")[:120],
        committed_at="",
        dirty=False,
        started_at=datetime.now(timezone.utc),
    )


def boot_info() -> BuildInfo:
    """이 프로세스의 빌드 정보. 최초 호출 시점으로 고정된다.

    우선순위: 배포 환경변수 → git → unknown.
    """
    global _BOOT
    if _BOOT is None:
        _BOOT = _from_env() or BuildInfo(
            commit=_git("rev-parse", "--short", "HEAD") or "unknown",
            subject=_git("log", "-1", "--format=%s") or "(git 정보 없음)",
            committed_at=_git("log", "-1", "--format=%cI") or "",
            dirty=bool(_git("status", "--porcelain")),
            started_at=datetime.now(timezone.utc),
        )
    return _BOOT


def commits_behind() -> int:
    """기동 시 커밋이 현재 HEAD보다 몇 커밋 뒤처졌는가. 알 수 없으면 0."""
    info = boot_info()
    if info.commit == "unknown":
        return 0
    if not _git("rev-parse", "--git-dir"):
        return 0      # 컨테이너 배포 — 비교 대상 저장소가 없다
    head = _git("rev-parse", "--short", "HEAD")
    if not head or head == info.commit:
        return 0
    count = _git("rev-list", "--count", f"{info.commit}..HEAD")
    try:
        return int(count)
    except ValueError:
        return 0


def staleness_line() -> str | None:
    """뒤처진 상태면 사람이 읽을 한 줄, 최신이면 None."""
    n = commits_behind()
    if n <= 0:
        return None
    return (f"⚠️ 봇이 {n}커밋 뒤처진 코드로 실행 중 — 재시작 필요\n"
            f"   실행 중: {boot_info().short} ({boot_info().subject[:60]})")


def uptime_text() -> str:
    delta = datetime.now(timezone.utc) - boot_info().started_at
    hours, rem = divmod(int(delta.total_seconds()), 3600)
    days, hours = divmod(hours, 24)
    mins = rem // 60
    if days:
        return f"{days}일 {hours}시간"
    return f"{hours}시간 {mins}분" if hours else f"{mins}분"


def boot_line(process: str) -> str:
    """기동 로그 한 줄 — 어떤 코드가 도는지 즉시 보이게 한다."""
    info = boot_info()
    return (f"[version] {process} 기동 — 커밋 {info.short} "
            f"({info.committed_at[:16]}) {info.subject[:60]}")
