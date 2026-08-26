# 배포 메모 (Railway)

프로젝트: `attractive-victory` · 환경: `production`

| 서비스 | 실행 명령 | 비고 |
|---|---|---|
| `analystbot-bot` | `python -m app.bot` | Dockerfile CMD 기본값 |
| `analystbot-scheduler` | `python -m app.scheduler` | **서비스 설정으로 지정** |
| `Postgres` / `Redis` | 애드온 | 참조 변수로 주입 |

## ⚠️ railway.json에 `startCommand`를 넣지 마라

`railway.json`은 **저장소 공용**이라 두 서비스에 모두 적용된다. 여기에
`startCommand`를 넣으면 **서비스별 설정을 덮어써서** 스케줄러까지 봇을 실행한다.

실사고(2026-08-26): `railway.json`에 `"startCommand": "python -m app.bot"`이
있어 스케줄러 서비스가 봇을 띄웠고, 텔레그램 폴링이 서로 충돌했다
(`TelegramConflictError: terminated by other getUpdates request`).
스케줄러는 **한 번도 실행되지 않았는데** 배포 상태는 SUCCESS로 보였다.

→ 서비스별 명령은 Railway 서비스 설정(`update_service --start-command`)에만 둔다.

## 배포 전 필수 확인

배포 업로드는 `.gitignore`를 따른다. 로컬 `docker build`는 그렇지 않아
**로컬 성공이 배포 성공을 보장하지 않는다**. 다음으로 미리 확인한다:

```bash
TMP=$(mktemp -d) && git archive --format=tar HEAD | tar -x -C "$TMP" \
  && docker build -t analystbot:ctx "$TMP" && rm -rf "$TMP"
```

실사고(2026-08-26): `data/`와 `uv.lock`이 `.gitignore`에 있어 업로드에서 빠져
빌드가 두 번 연속 깨졌다. `uv.lock`은 추적 대상으로 바꿨고 `data/`는 이미지에서 뺐다.

## 스키마

`analystbot-scheduler`의 pre-deploy 명령이 `python -m app.db init`을 실행한다.
스키마는 멱등(CREATE TABLE IF NOT EXISTS)이라 매 배포 시 안전하다.
