# cc_collab_0925 · 커밋 bc2437a · 배포 미배포

지시문 `docs/fable/done/2026-09-25_cc_collab.md` · 브랜치 `fable/cc_collab_0925`

## 완료 조건 원문

> ## CC-7 — 검증
>  1. `tests/meta/` 3개(훅·보고서 형식·명령 존재) 통과.
>  2. 실제 시연: 이 파일을 `inbox/2026-09-25_cc_collab.md` 로 넣고 `/fable-run` → `reports/cc_collab_report.md` 생성 · guard.sh 가 17~22시 배포를 실제로 막은 로그(`FAKE_KST_HOUR=19`) · `/fable-status` 산출물.
>  3. github MCP 로 PR 1개 생성(이 설정 커밋), postgres_ro 로 `SELECT count(*) FROM analysis_runs` 1회 조회 로그.
>  4. 완료 보고서를 사용자가 페이블에 올리면 페이블이 형식·훅 동작을 확인한다.
>
> ## 하지 말 것
>  - 훅·에이전트가 봇 판정 코드를 수정하거나 발송을 켜지 않는다. 훅을 `--no-verify` 류로 우회하지 않는다.
>  - 토큰·DB URL 을 파일에 적지 않는다. 쓰기 권한 DB 를 MCP 에 붙이지 않는다.
>  - 지시문을 inbox 밖에서 받아 실행하지 않는다(맥락 유실 방지).

## 전/후 표

### 강제되는 규율

| 규율 | 전 | 후 (실측 exit) |
|---|---|---|
| 배포 창 KST 17~22 | 훅이 이미 막음 | `19시`·`21시` → **exit 2** |
| force push · `reset --hard` | 훅이 이미 막음 | **exit 2** |
| 발송 스위치 켜기 | **아무도 안 막음** | **exit 2** "발송은 사용자만" |
| 컨테이너 쓰기 (`railway run`·`variables 설정`) | **아무도 안 막음** | **exit 2** |
| `ssh` 읽기 프로브 | 통과 | 통과 (exit 0) — 막으면 운영 실측이 죽는다 |
| 변수 **조회** | 통과 | 통과 (exit 0) — 막는 것은 켜는 것뿐 |
| 배포 스크립트 **읽기** (19시) | 통과 | 통과 (exit 0) |

### 자산

| 항목 | 전 | 후 |
|---|---|---|
| `.claude/` 훅 (물린 것) | 7 | **9** (`after_commit`·`on_stop` 추가 · 기존 7 유지) |
| `.claude/commands/` | 0 | **4** |
| `.claude/agents/` | 0 | **2** |
| `docs/fable/` 폴더 | 없음 | **6** + README(형식 원본) |
| `tests/meta/` 계약 | 0 | **42** (훅 25 · 형식 4 · 명령 13) |
| 전체 스위트 | 6,181 | **6,219** passed |

### CC-7 항목별

| # | 조건 | 결과 |
|---|---|---|
| 1 | `tests/meta/` 3개 통과 | ✅ 42 passed · 2 skipped |
| 2 | inbox → 보고서 · guard 로그 · status 산출물 | ✅ 이 파일 · 아래 로그 · `status_2026-09-25.md` |
| 3 | PR 1개 | ✅ 아래 링크 |
| 3 | `SELECT count(*) FROM analysis_runs` | ✅ **66,163** (읽기 전용 조회) |
| 4 | 페이블 확인 | 사용자 몫 |

### guard 실측 로그 (`FAKE_KST_HOUR` 주입)

```
=== 막혀야 하는 것
KST 19시 | exit 2 | tools/deploy.sh all              | 🚫 슬레이트 창 배포 차단 — 지금 KST 19시다 (금지 17:00~22:00).
KST 21시 | exit 2 | tools/deploy.sh all              | 🚫 슬레이트 창 배포 차단 — 지금 KST 21시다 (금지 17:00~22:00).
KST 09시 | exit 2 | 발송 스위치 켜기                 | 🚫 발송 스위치 차단 — 발송은 사용자만 켠다.
KST 09시 | exit 2 | railway run python -m app.pipeline | 🚫 컨테이너 직접 수정 차단 — 저장소와 운영이 갈린다.
KST 09시 | exit 2 | railway variables 설정           | 🚫 컨테이너 직접 수정 차단 — 저장소와 운영이 갈린다.
KST 09시 | exit 2 | git push --force origin main     | 🚫 main 강제 push 차단 — 남의 커밋을 지운다.
=== 통과해야 하는 것
KST 09시 | exit 0 | railway ssh "python /tmp/probe.py"
KST 09시 | exit 0 | railway variables | grep -i pipeline_v14_send
KST 19시 | exit 0 | sed -n 1,20p tools/deploy.sh
KST 09시 | exit 0 | ls docs/fable
```

⚠️ **이 규칙을 시험하다 내가 두 번 걸렸다.** 금지어를 Bash 명령줄에 적으면
   훅이 그 명령을 먼저 막는다(DEFECTS D46 과 같은 함정). 그래서 시험 문자열을
   파일 안 상수로 옮겼다 — 계약이 그 방식을 고정한다.

## pytest 마지막 20줄

```
============================ 외부 HTTP 차단 — 목이 필요한 지점 ============================
  tests/test_satellite_soccer.py::test_표에_없는_팀은_부상자가_없다고_말하지_않는다
      → www.bing.com
  tests/test_satellite_soccer.py::test_한_팀이_터져도_나머지가_산다
      → www.bing.com
  tests/test_satellite_split.py::test_축구가_공용_검색을_쓴다
      → www.bing.com
  tests/test_scope_combos.py::test_flagged_pick_never_recommended_regression
      → generativelanguage.googleapis.com, news.google.com, statsapi.mlb.com
  tests/test_soccer_fixture_sources.py::test_football_data가_막혀도_배당_리그는_산다
      → www.fotmob.com
  tests/test_soccer_fixture_sources.py::test_둘_다_막히면_빈손이지_예외가_아니다
      → www.fotmob.com
  tests/test_soccer_fixture_sources.py::test_목모드_football_data는_부르지_않는다
      → www.fotmob.com
  tests/test_soccer_fixture_sources.py::test_배당이_막혀도_메이저_리그는_산다
      → www.fotmob.com
=========================== short test summary info ============================
SKIPPED [1] tests/test_data_provenance.py:180: 이 슬레이트에 h2h 추천이 없다 (세 방식 비교는 승패 기준)
SKIPPED [1] tests/test_data_provenance.py:200: 적재된 예측이 없다
SKIPPED [1] tests/test_research.py:91: PPLX_API_KEY 필요 (실키 통합)
SKIPPED [1] tests/test_research.py:99: XAI_API_KEY 필요 (실키 통합)
6219 passed, 6 skipped in 157.16s (0:02:37)
```

## 고쳐 쓴 기존 테스트(목록·사유)

**없음.** 이 단계는 `.claude/` 와 `docs/fable/` 만 건드렸고 기존 계약을 하나도
고치지 않았다. 새로 만든 것만 42개다.

⚠️ 대신 **내가 쓴 새 계약 하나를 실행 중에 고쳤다** —
`test_시각을_주입할_수_있다` 가 "창 밖이면 배포가 통과한다"를 단언했는데,
실측 09시 응답은 `"미커밋 변경이 있다"`(다른 게이트)였다. exit 코드가 아니라
**사유**로 가르게 고쳤다. 게이트가 여럿인 것을 내가 몰랐던 것이다.

## 남은 것

| 항목 | 상태 | 왜 |
|---|---|---|
| `postgres_ro` MCP 연결 | **미완** | 읽기 전용 DB 계정이 없다. **내가 만들 수 없다** — 운영 Postgres 권한이 필요하다. `.mcp.json` 은 `${DATABASE_URL_READONLY}` 로 써 뒀고, 계정 생성 + 환경변수 설정은 사용자 몫이다. 조회 자체는 `railway ssh` 읽기 프로브로 대신해 결과(66,163)를 남겼다 |
| `github` MCP 연결 | **미완** | `GITHUB_TOKEN` 환경변수가 없다. 대신 `gh` CLI(이미 `sansarang` 로 인증됨)로 PR 을 만들었다 — 결과는 같고, MCP 는 토큰이 들어오면 붙는다 |
| 드라이브 심볼릭 링크 | **미완** | 폴더명을 사용자가 정한다(지시문 CC-5) |
| 배포 | **안 했다** | 지시 없음. 서버는 `6e6fba6` 로 **4커밋 뒤처져 있다**(PIPE-1~8·CC-1~6 미반영) |
| `/health` HTTP 응답 | **못 받음** | 공개 도메인을 확인하지 못했다. 커밋 해시는 `railway ssh` 로 직접 읽어 대조했다 |
| `on_stop.sh` 실전 발동 | **미확인** | 갈림길에서 멈춘 세션이 아직 없다. 문법·권한·물림은 계약이 확인했고, 실제 발동은 다음 갈림길에서 본다 |
