# 인계 — **다음 세션이 먼저 읽을 것** (2026-10-04 19:12 · 맥 종료)

사용자가 맥을 끈다. 🔴 **돌던 것은 전부 세웠다**(거짓 사유가 로그에 남지
않게) · 미커밋 변경 **0**.

---

## 1. 이번 세션이 끝낸 것 — 커밋 둘

| 커밋 | 무엇 |
|---|---|
| `76d39cc` | 작업지시 §4-5 — **정답지 재현 계약**(v5-A §5) |
| `4b26053` | 작업지시 §5 / v5-A §6 — **측정**(`metrics/`) |

✅ 스위트 **1594 통과 · 16 skip · 2 xfail** · ruff 통과 · 돌연변이 **9/9 빨갛다**

---

## 2. 🔴🔴 **DeepSeek 는 켤 수 없다** — 기계가 막고 있다

`enabled: false` 다. 작업지시 §6 금지: *"정답지 재현 계약이 빨간 채로
DeepSeek 를 켜지 않는다."* 지금 셋 중 **둘이 빨갛다**:

| 경기 | 실제 | 필요한 갈래 | 결과 |
|---|---|---|---|
| 콜롬비아 vs 파라과이 | 0-1 | 원정승 | ✅ **섰다** |
| 남아공 vs 에리트레아 | 5-0 | 대량득점형 | 🔴 `A~E 가 다 찼다` |
| 크로아티아 vs 잉글랜드 | 2-2 | 난타전 | 🔴 `A~E 가 다 찼다` |

⬛ **사용자 답을 기다린다** →
`docs/fable/questions/2026-10-04_scenario_letters_full.md` (갈림길 A~D).
🔴 **DeepSeek 를 켜도 이 구멍은 그대로다** — 모델이 대량득점형을 써 보내도
들어갈 글자가 없다.

⚠️ 그 둘은 `xfail(strict=True)` 다 — **고쳐지면 XPASS 로 빨개진다.** 그때
표시를 떼고 켤 수 있다(켜는 결정은 사용자).

---

## 3. 게이트 2 — **5경기 중 1경기만 끝났다**

```bash
# 재실행(인터넷·SearXNG·Ollama 가 돌아온 뒤)
bash docs/fable/stages/gate2_logs/gate2.sh
```

| 경기 | 결과 | `verified_vars` |
|---|---|---|
| **MLB** 밀워키 vs 샌디에이고 | ✅ 끝 | **10** (≥6 통과) |
| **NPB** 広島東洋カープ vs 中日ドラゴンズ | 🔴 `match_not_found` | — |
| **KBO** 한화 vs 키움 | ⚠️ **중간에 세웠다**(653줄) | — |
| 북마케도니아 vs 스코틀랜드 | ⬛ 시작 못 함 | — |
| 크로아티아 vs 잉글랜드 | ⬛ 시작 못 함 | — |

🔴 **완료 조건**: 5경기 중 **4경기가 `verified_vars ≥ 6`** + M47~M52 돌연변이
전부 빨강 → `config/stage_gates.yaml` 서명 + 커밋 해시 기록.

### ⚠️ NPB 는 **봇 결함이 아니다** — 그 경기가 오늘 없다

10/4 NPB 일정은 **横浜DeNAベイスターズ vs 阪神タイガース** 였다(어댑터가 3경기를
온전히 적었다). 🔴 그래서 `gate2.sh` 의 npb 줄을 **일정에 있는 경기로** 바꿔야
한다 — 봇은 제 할 일을 했다.

### 🔴 로그는 **저장소로 옮겼다**

스크래치패드는 재부팅에 사라진다 → `docs/fable/stages/gate2_logs/*.log.gz`
(하네스 `ask_bot.py` · 실행본 `gate2.sh` 포함).

---

## 4. 🔴🔴 **다음 한 수** — 실측으로 좁혀 둔 결함 (아직 **안 고쳤다**)

MLB 로그의 깔때기가 적은 가장 큰 폐기:

```
queries 탈락: query_too_bare 26        ← 에이전트 질의의 **절반**
🔴 고칠 곳: 검색 26건 · 읽기 19건 · 에이전트 6건 · 수집 6건 · 검증 3건
```

### 까닭 — **이름표에 짧은 이름이 없다**(실측 2026-10-04, 이 세션)

```
_names_of_key("team:000338") → ['Milwaukee Brewers', '밀워키 브루어스']
                                🔴 'Brewers' 가 **없다**

teamref.key_of 실측:
  Athletics ✅ team:000323    White Sox ✅ team:000335
  Yankees   ✅ team:000337    Guardians ✅ team:000345
  🔴 Brewers · Padres · Pirates · Giants · Angels · Cardinals ·
     Rangers · Dragons · Tigers · Twins · Marlins · Mariners → **없다**
```

그래서 모델이 이렇게 치면 문지기가 요소를 **1개**로 세고 거부한다:

```
'Brewers Padres NLDS Game 1 2026 MLB.com recap'  →  (1, ['team'])
   🔴 'Padres' 가 상대로 안 보인다 · 'MLB' 는 대회로 보인다
   ✅ 짧은 이름이 들어오면 team + opponent + competition = 3 → **통과**
```

### 🔴 공식 API 가 **이미 주고 있다** — 우리가 흘린다

```
statsapi.mlb.com/api/v1/teams?sportId=1  (실측 2026-10-04)
  {'id':135,'name':'San Diego Padres','teamName':'Padres',
   'clubName':'Padres','shortName':'San Diego','abbreviation':'SD'}

app/league_index.py:147
  "mlb": lambda d: [str(t.get("name") or "") for t in (d.get("teams") or [])]
                        🔴 `name` **하나만** 받는다
```
⚠️ fdorg 쪽은 **이미 `name`+`shortName` 을 둘 다** 받는다(같은 파일 205줄) —
**같은 모양의 구멍**이고 한쪽만 메워져 있다.

### ⚠️ 그냥 넣으면 안 된다 — **부딪친다**

`Giants` 는 SF 자이언츠 · 요미우리 자이언츠 · 롯데 자이언츠가 다 쓴다.
`Tigers` 는 디트로이트 · 한신 · 기아. 🔴 CLAUDE.md 가 이미 같은 사고를 적어
뒀다(`config/entities.yaml`: *"맨이름 `롯데` 는 넣지 않는다"*).

🔴 그래서 §11-1 대로 **계약 먼저**: *"짧은 이름이 이름표에 들어갈 때 다른 팀과
부딪치면 빨개진다"* → 빨간 것 확인 → 그 다음 고친다.
⚠️ `abbreviation`(`SD`·`PIT`)은 **넣지 않는다** — fdorg 의 `tla` 를 뺀 것과 같은
까닭이고 그 사유가 `league_index.py:206` 에 적혀 있다.

---

## 5. 그 밖에 열려 있는 것

| 무엇 | 어디 |
|---|---|
| ⬛ 시나리오 글자 소진(A~E) | `questions/2026-10-04_scenario_letters_full.md` |
| ⬛ 야구가 시나리오를 2개만 만든다 | `questions/2026-10-04_baseball_only_two_scenarios.md` |
| ⬛ CJK 이름 검사가 라틴만 본다 | `questions/2026-10-04_cjk_name_check.md` |
| ⚠️ Solar 단가 3개 미확인 | 카드가 *"⚠️ 단가 미확인(§2)"* 를 계속 적는다 |
| ⚠️ 콘솔 월 상한 미설정 | `console_cap_set_by_user: false` |
| 🔴 측정 세 파일 전부 "안 쟀다" | `metrics/README.md` — 게이트 2~5 가 앞이다 |

---

## 6. 맥을 다시 켠 뒤

```bash
colima start                       # 도커가 안 잡히면
docker compose up -d               # postgres · redis · searxng
curl -s 127.0.0.1:8888 >/dev/null && echo searxng ok
PYTHONPATH=. uv run pytest tests -q        # 1594 통과 · 16 skip · 2 xfail 이어야 한다
```

⚠️ `com.ollama.ollama` · `homebrew.mxcl.colima` 는 launchd 가 되살린다.
⚠️ SearXNG 엔진은 하루 만에 뒤집힌다 — 게이트2 재실행 전에 `google news` 가
   사는지 본다(죽어 있어도 §19-b-4 가 **지정 없이 다시** 던져 36~45건을 받는다).
