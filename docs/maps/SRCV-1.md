# SRCV-1 — 꺼진 소스를 /health·export 에 사유와 함께 찍는다 (영향 지도 5문)

사용자 지시([2]b 추가, 2026-09-21): "KBO 가 '미상으로 멈춤'이 **의도한 동작**임을
`/health` 와 export 에 **사유와 함께** 찍는다 ('KBO — 자료 제한: 소스 중단(D33)')."

## ① 무엇이 틀렸나 — 실측

운영 컨테이너 2026-09-21 13:44:

```
kbo_park.refresh   → 정상반환 {'stadiums': 0, 'games': 0}
kbo_usage.refresh  → 정상반환 {'teams': 0}
naver_kbo.refresh  → SourceDisabled (예외가 그대로 올라온다)
kbo_stats/roster   → 게이트가 요청 전에 막는다
```

🔴 **조용한 0 이다.** `source_gate` 는 "조용히 빈손을 주지 않는다"고 적혀 있지만,
그 약속은 **게이트까지**다. 수집기가 `except Exception` 으로 잡아 0 을 돌려주는
순간 약속이 끊긴다. 읽는 쪽은 "오늘 자료가 없다"와 "소스를 껐다"를 구분 못 한다.

⚠️ 수집기의 `except` 를 **고치지 않는다.** 키 없이 크래시하지 않는 것이 절대
   규칙 3 이고, 잡 하나가 스케줄러를 죽이면 그게 더 나쁘다. 고칠 것은 **보임**이다.

## ② 어디를 건드리나

| 파일 | 무엇 |
|---|---|
| `config/rules.yaml` | `sources.*` 에 `affects`(리그) · `defect`(원장 번호) **두 칸 추가** |
| `app/collectors/source_gate.py` | `restrictions()` · `restriction_lines()` **함수 2개 추가** |
| `app/health.py` | `build_health` 끝에 제한 줄 append |
| `app/export/for_fable.py` | `restrictions_block()` + `collect()` 반환에 한 칸 |

**새 모듈 0 · 새 테이블 0 · 수집 경로 변경 0 · 판정 경로 변경 0.**

## ③ 사본이 생기나

🔴 **안 생기게 했다.** 리그 매핑과 결함 번호의 원본은 `config/rules.yaml` 하나,
사유 문구의 원본은 `source_gate.REASONS` 하나다. `/health` 도 export 도 **문구를
만들지 않고** `restriction_lines()` 를 부른다.
계약 `test_켜면_줄이_사라진다` 가 이 방향을 잠근다 — 코드에 박으면 실패한다.

## ④ 기존 경로를 건드리나

- 수집기·게이트의 **동작은 그대로**다. `require()` 도, `enabled()` 도 안 바꾼다.
- `/health` 는 줄이 늘어난다(꺼진 소스가 있을 때만).
- export 는 키가 하나 는다. **표시 전용** — 판정·확률로 가는 경로 0.

## ⑤ 틀렸을 때 누가 알려주나

계약 6건(`tests/deepsearch/test_src_off_visible.py`):
목록이 리그별로 묶이나 · 줄 형식 · **켜면 사라지나(사본 금지)** · 리그 없는 줄이
없나 · `/health` 에 사유가 실리나 · export 블록.

## 아직 안 고친 것 (보고만 — [2]b 는 점검 단계다)

1. 🔴 **Go 크롤러는 게이트 밖이다.** `crawler/internal/source/source.go:137·159`
   가 `api-gw.sports.naver.com` 을 10분마다 친다. Python 만 껐다.
   실측: `lineup_events` `source='crawler'` 마지막 경기일 **2026-09-20**.
2. ⚠️ **UA 위장 20곳** — `Mozilla/5.0`. 지시문 규율은 "봇 크롤러는 식별 가능한
   User-Agent 를 쓴다"이다.
3. `boxscore` 계열은 **게이트 이전부터** 끊겨 있었다(`batter_appearances`
   마지막 경기일 2026-09-12) — D09a 와 같은 자리로 보인다. [2]c 에서 본다.
