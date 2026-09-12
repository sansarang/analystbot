# SOC-6 — 축구가 v3 판정 경로에 연결돼 있지 않았다

## 왜

실측 2026-09-12 22:11 (운영 수동 실행, `ORDER_V3=1`) — 12경기 전부:

```
[2단] 12경기 판정 0건 — 재시도 큐 적재
[judge] 구 Judge 꺼짐(SOCCER_JUDGE_ENABLED=false) — soccer 12경기 판정 없이 반환
[pipeline] 판정 부착 0건 — 분석 대상 12경기 중 매칭 실패 (판정 game_id=[])
```

스위치를 켜도 축구는 **구 Judge 경로**로 갔고, 그 경로는 꺼져 있다.
막는 곳이 둘이다:

```
① app/engine/matchup.py:1160   if sport not in BASEBALL_SPORTS: return None
② app/pipeline.py:2126         if sport in _BB:  → _run_baseball_matchups(...)
                               (이름 그대로 야구 전용 러너다)
```

SOC-1(수집 채널 표)·SOC-2(3-way 판정)로 v3 **안쪽**은 축구를 받을 준비가 됐다.
**문 앞까지 오는 길이 없었다.**

## ① 이 함수/상태를 읽는 곳 **전부**

```
$ grep -rn "judge_matchup" app/
app/engine/matchup.py       정의
app/pipeline.py:2870        _run_baseball_matchups 안 — 유일한 호출부
app/pipeline.py:5890 주석

v3 가 켜졌을 때 judge_matchup 이 지나는 것(1160→1277):
  _skip_db=True  → 팀 폼 생략 · 박스스코어 게이트 생략 · 심의 생략
  situation.attach(jg)     try/except
  claim_final              final 일 때만 (축구 러너는 allow_final 을 주지 않는다)
  news_payload({}, {}, jg) 빈 폼이라 사실상 빈손
  → **야구 전용 단계가 전부 비활성이다.** 축구가 지나가도 걸리는 것이 없다.
```

빌려 쓰는 원본 — 새로 만들지 않는다:
| 무엇 | 원본 |
|---|---|
| 판정 진입 | `matchup.judge_matchup` (야구와 같은 문) |
| 4단계 판정 | `matchup._judge_v3` |
| 수집 채널 | `registry.COLLECT_CHANNELS` (SOC-1) |
| 3-way 적용 | `matchup.apply_winner` (SOC-2) |

## ② 만드는/바꾸는 상태

| 상태 | 성격 | 다른 곳이 다른 규칙으로 갱신하나 |
|---|---|---|
| `judge_matchup` 종목 게이트 | 축구를 **v3 일 때만** 허용 | 🔴 아래 |
| `pipeline._run_soccer_matchups` | 새 함수 | 아니다 |
| `build_analysis` 분기 | 축구 가지 추가 | 야구·기타 가지는 손대지 않는다 |

🔴 **v3 가 꺼져 있으면 축구는 종전 그대로여야 한다.** `judge_matchup` 의
   v3 아래쪽 경로(`render_matchup_prompt` 등)는 **야구 모양**이다 —
   축구가 거기로 새면 프롬프트에 선발·타순 칸이 생긴다. 계약이 막는다.

⚠️ DB·Redis·env·프롬프트·모델명·상한을 건드리지 않는다.

## ③ 리그·종목·경로 분기

분기를 **하나만** 늘린다(야구 가지 옆에 축구 가지). 야구 러너는 한 글자도
바뀌지 않는다 — 축구는 별도 러너다. 축구에는 선발·타자·불펜·Elo 부착이
없으므로 그 호출을 **하나도 넣지 않는다**(계약이 부재를 단언).

## ④ 조용히 실패하는가

| 위험 | 대응 |
|---|---|
| 🔴 **야구 판정이 바뀐다** ← 가장 큰 반대 위험 | 야구 3종목이 여전히 v3 로 가는지 계약 |
| 🔴 v3 꺼졌는데 축구가 야구 프롬프트로 샌다 | 꺼진 상태에서 `None` 을 계약 |
| 축구 아닌 종목이 문을 통과한다 | tennis·nba·빈 문자열 거절 계약 |
| 러너를 만들었는데 아무도 안 부른다 | `build_analysis` 소스에 호출이 있는지 계약 |
| 한 경기가 터져 슬레이트가 죽는다 | 경기별 try + `game=N` 로그. 계약 |
| 야구 부착이 축구에 딸려온다 | 소스에 그 이름들이 없는지 계약 |

⚠️ **아직 못 잰 것**: 축구 12경기에서 v3 가 실제로 몇 건을 판정하고, 무 판정이
   몇 건 나오는가. 재료(위성)가 SOC-5 로 이제야 들어오므로 **이번이 첫 측정**이다.

## ⑤ 이미 있는 사실을 다시 적는가

- 종목 목록을 새로 적지 않는다 — `BASEBALL_SPORTS` 를 그대로 쓰고 축구만 더한다.
- 수집 채널을 러너가 정하지 않는다 — `COLLECT_CHANNELS` 가 원본이다.
- 판정 단계를 다시 쓰지 않는다 — `_judge_v3` 를 그대로 부른다.
