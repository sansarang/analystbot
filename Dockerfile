# AnalystBot — 봇·스케줄러 공용 이미지.
#
# 한 이미지로 두 서비스(app.bot / app.scheduler)를 띄운다. 실행 명령만 다르고
# 코드·의존성은 같으므로 이미지를 나누면 빌드 시간만 두 배가 된다.
#
# ⚠️ pybaseball/soccerdata가 pandas·numpy·scikit-learn을 끌고 온다. 이미지가
#    크고 Statcast 집계(30일 11.6만 행)는 메모리를 쓴다 — 스케줄러 서비스의
#    메모리를 봇보다 넉넉히 잡아야 한다.

FROM python:3.12-slim

# tzdata: KST/미국 동부 날짜 경계 계산에 필요 (슬레이트 날짜 규칙의 근간)
# curl: 헬스체크·디버깅용
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# 의존성만 먼저 — 코드가 바뀌어도 이 레이어는 캐시된다
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app/ ./app/
COPY db/ ./db/
COPY mock_data/ ./mock_data/
COPY tools/ ./tools/
# data/: 학습된 λ 계수·Elo 피팅값. 없으면 해당 기능만 건너뛴다(크래시 금지 규칙)
COPY data/ ./data/

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# 기본은 봇. 스케줄러는 railway.json / 서비스 설정에서 startCommand로 덮어쓴다.
CMD ["python", "-m", "app.bot"]
