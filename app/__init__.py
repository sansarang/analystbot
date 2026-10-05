
# 🔴 `.env` 를 **여기서** 읽는다 — 패키지의 어느 모듈을 import 해도 한 번 돈다.
#    `app.config` 안에만 두면 그 모듈을 부르지 않는 경로(`app.search` 단독 등)가
#    조용히 기본값으로 돈다(실측 2026-09-27).
from app.config import load_env as _load_env  # noqa: E402

_load_env()
