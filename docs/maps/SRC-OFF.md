# SRC-OFF 영향 지도 — robots 거부 소스를 기능 플래그로 끈다

## 0. 재현 (실측 2026-09-21 13:04 KST)

`https://www.koreabaseball.com/robots.txt` · HTTP **200** · EUC-KR:

```
# 본 사이트의 데이터를 사전 승인 없이 자동 수집·크롤링·복제하는 행위를 금지합니다.
User-agent: Googlebot / Yeti / Daumoa / Bingbot   Disallow: /ws/
User-agent: *                                     Disallow: /

can_fetch("AnalystBot/1.0") → 전 경로 False
```

그런데 **우리는 7경로를 지금도 친다**:

| 코드 | 경로 |
|---|---|
| `kbo.py:31` | `/ws/Schedule.asmx/GetScheduleList` |
| `kbo.py:89` | `/Schedule/Schedule.aspx` |
| `kbo_stats.py:26·28·29` | `/Record/Team/Hitter/Basic1` · `/Record/Team/Pitcher/Basic1` · `/Record/Player/PitcherBasic/BasicOld` |
| `kbo_roster.py:25` | `/Player/RegisterAll.aspx` |
| `kbo_boxscore.py` | `/ws/Schedule.asmx/GetBoxScoreScroll` |

`api-gw.sports.naver.com` 은 robots.txt 가 **404(판단 불가)** 다. 같은 계열
`sports.news.naver.com` 이 `Disallow: /` 이므로 판단이 설 때까지 함께 끈다
(사용자 지시 [2]a).

## 1. 영향 지도 5문

**① 어디를 고치나.**

| 파일 | 무엇 |
|---|---|
| `config/rules.yaml` | `sources.koreabaseball.enabled: false` · `sources.naver_apigw.enabled: false` |
| `app/collectors/source_gate.py` (신규) | `enabled(name)` · `blocked_reason(name)` — **판단이 한 곳** |
| `kbo.py` · `kbo_stats.py` · `kbo_roster.py` · `naver_kbo.py` | HTTP 진입점 **한 곳씩**만 막는다 |

**② 코드를 지우나.** 지우지 않는다. **플래그로 끈다** — 정식 접근이 허락되면
한 줄로 되돌린다(사용자 지시 원문: "코드 삭제가 아니라 기능 플래그로").

**③ 규칙은 어디에 한 번만 두나.** `source_gate` 하나다. 수집기는 자기 판단을
하지 않고 그 함수를 부른다. 스위치 값은 `config/rules.yaml` 하나다.

**④ 무엇이 깨질 수 있나.**
- 🔴 **KBO 자료가 통째로 빈다.** 일정·결과·선발·타순·불펜·엔트리 전부.
  그것이 이 변경의 **의도된 결과**다 — 없는 것을 없다고 말하게 만든다.
- 🔴 **흐름이 죽으면 안 된다.** 소스가 꺼져도 예외로 파이프라인을 멈추지
  않는다. 수집 함수는 **빈 결과**를 돌려주거나(일정) 명시적 예외를 올리되
  호출부가 이미 감싸고 있는 자리만 그렇게 한다.
- ⚠️ 모르는 이름은 **켜진 것**으로 본다. 게이트가 기존 소스를 조용히 끄면
  그게 더 큰 사고다. 계약이 이것을 잠근다.
- ⚠️ `test_judge_requires_results` 규칙상 KBO 의 judge 를 끄는 것이 기본이나,
  **leagues.py 기능 플래그는 이 커밋에서 건드리지 않는다** — 사용자 결정 사항이다.

**⑤ 틀렸을 때 알려줄 테스트.** `tests/deepsearch/test_src_off.py` — 플래그가
config 에 있나 · 게이트가 한 곳인가 · **요청이 0회인가** · 모르는 이름은 켜지나 ·
끈 이유가 코드에 있나.

## 2. 이 커밋 밖 (사용자 지시 [2]b~e)

- b. 끈 뒤 KBO 칸별 "소스 없음(robots)" 사실표 · /health·export 표시
- c. D09a 원인을 **경로를 치지 않고** 로그로만 가린다
- d. 대체 소스 실측 (robots 먼저 읽고 허용일 때만)
- e. 정식 접근 문의 초안 (작성만 · 발송 안 함)
