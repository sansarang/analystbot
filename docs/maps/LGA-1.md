# LGA-1 영향 지도 — 이미 오는 자료를 버린다 (STEP 1-i-1)

## 0. 재현 (실측 2026-09-20)

football-data 무료 전역 `/matches` 응답:

```
2026-09-19 · 전체 53경기
   Championship 10 · Bundesliga 6 · **Ligue 1 6** · Premier League 6
   **Eredivisie 5** · Serie A 5 · Primera Division 5 · Brasileiro 5
   Primeira Liga 4 · Copa Libertadores 1        (전부 종료)
```

`football.py:123` 이 화이트리스트 밖이라며 **전건 버린다**. `LEAGUES` 에 두
리그가 아예 없기 때문이다.

## 1. 그 제외는 정책인가 (보고 a)

```
$ git blame -L 122,125 app/collectors/football.py
9528ba54 (2026-08-23 16:33) 124)  continue  # 화이트리스트 밖 리그 (리그앙·브라질 등) 제외
```

`9528ba5` 는 **축구 7리그 커버리지를 처음 연** 커밋이다(커밋 제목:
"soccer coverage x7 leagues (LaLiga/SerieA/Bundesliga/K1) …"). 리그앙 제외에
별도 사유가 적혀 있지 않다 — **정책이 아니라 그때의 범위**였다.

## 2. `LEAGUES` 소비처 (보고 b)

| 소비처 | 읽는 칸 | 채우면 켜지는 것 |
|---|---|---|
| `collectors/odds.py:25·48` | `odds_key` | 배당 수집 |
| `collectors/football.py:112` | `fd_names` | **결과 적재** ← 목표 |
| `collectors/fotmob.py:493` | `fotmob_contains` | FotMob 슬레이트 |
| `collectors/satellite_soccer.py:339` | `tm_code` | 부상표 |
| `pipeline.py:279` | `elo` | 축구 Elo 사전값 |
| `bot/main.py:411·437` · `leagues.find_league` | `label`·`aliases` | **라우터 노출** |

🔴 **칸이 비면 그 기능은 안 켜진다.** 별도 기능 플래그가 필요 없다 —
이미 칸 단위로 분리돼 있다.

## 3. 영향 지도 5문

**① 어디를 고치나.** `app/leagues.py` 의 `LEAGUES` 에 두 항목 추가. 끝.

**② 무엇만 켜나.** `fd_names` 뿐이다. `odds_key`·`tm_code`·`elo`·`aliases` 는
**비워 둔다**. 특히 `aliases` — 자료가 없는 리그가 라우터에 보이면 사용자가
부를 수 있고, 그때 "자료 없음"이 아니라 **빈 카드**가 나간다.

**③ 새 숫자를 만드나.** 만들지 않는다. `fd_names` 는 **실측한 응답 문자열
그대로**다(`"Ligue 1"`·`"Eredivisie"`). 추측한 철자를 쓰지 않는다.

**④ 무엇이 깨질 수 있나.**
`games` 에 축구 행이 는다(하루 10여 경기). 🔴 **돌던 리그를 건드리지 않는
것**이 반대 위험이고, 테스트가 `epl`·`la_liga` 설정을 그대로 잠근다.
⚠️ 이 두 리그는 사전값(`elo`)이 없으므로 ③ 게이트에서 `사전값없음` 경로로
간다 — STEP 1-e 가 그 자리다. 지금은 **결과만** 쌓는다.

**⑤ 틀렸을 때 알려줄 테스트.**
`tests/test_lga1_ligue1_ered.py` 4건 — 목록에 있나 · **결과만 켜졌나** ·
fd 이름이 실측과 같나 · **기존 리그 설정 불변**.

## 4. 완료 조건 (원문)

> 다음 날 Ligue 1·Eredivisie 종료 경기가 `games(final)` 에 들어온 행 수.
