# 갈림길 원장 — 2갈래로 갈린 것과, 딥서치로 찾은 자료

> **규칙은 [CLAUDE.md](../CLAUDE.md) "🔴 2갈래로 갈리면 딥서치한다" 에 있다.**
> 여기는 그 규칙을 적용한 **기록**이다. 갈림길 하나에 항목 하나.
> **결론이 아니라 자료를 적는다.** 자료가 갈리면 갈린다고 적는다.

---

## F-1 · 확정 XI 는 예상치를 **대체하는가, 얹는가** (2026-09-17 · PA-27-b)

**갈림길** — `주전결장`(이력 대비 오늘 결장)과 `라인업결장`(예상 XI 대비 공식
XI 결장)이 같은 선수를 두 번 셌다. 둘을 **더할 것인가 갈아끼울 것인가.**

**찾은 자료 — 대체다.**

| 출처 | 내용 |
|---|---|
| Sportmonks *Predicted Lineups* | 예상 라인업은 구단 발표 전까지만 유효하고, 그 뒤에는 **확정 11명으로 대체된다** |
| PlayerElo · FanPick | 현대 Elo 계열도 확정 라인업을 얹지 않고 **갈아끼운다** |
| Footy Forecast | 결장 반영은 "그 선수 기여를 빼고 **대체자 기여를 더한다**" — 결장자 수에 벌점을 주는 방식이 **아니다** |
| OddsIndex 외 | 확정 상태는 보통 **킥오프 60~90분 전**에 갈리고, 그때 라인이 빠르게 움직인다 |

**덤으로 얻은 크기 기준** — 확정 라인업 변경 하나가 승률 **2~9%p**, EPL 핵심
창조형 결장이 핸디 **0.25~0.5골**. 우리 `OUT_MULT 1.5 · OUT_CAP 6.0` 은 그
범위 안이다 → **상한을 바꿀 근거가 없어 안 바꿨다.**

**적용** — PA-27-b (커밋 `599ac60`). 실측 `{주전결장 −1.5, 라인업결장 −3.0}`
→ `{라인업결장 −3.0}`.

---

## F-2 · 딥서치 결장 명단이 **오늘 타순 집계를 대체해도 되는가** (2026-09-17 · PA-27)

**갈림길** — 같은 "누가 빠졌나"인데 성질이 다르다.

| | `주전결장` | 딥서치 `out` |
|---|---|---|
| 근거 | 오늘 타순/XI **전체** | 기사에 **이름이 난 선수만** |
| 완전성 | 완전(빠진 사람은 다 빠져 있다) | **부분** |
| 세밀함 | 인원수만 | 이름 — 중요도 가중 가능 |
| 시각 | 타순 확정 후 | 그 전에도 |

F-1 규칙을 그대로 쓰면 뒤가 앞을 대체한다. **그런데 이건 대체가 아니라
부분이 전체를 덮는 것일 수 있다.**

**찾은 자료 — 갈라진다. 그리고 갈라지는 지점이 분명하다.**

이 문제는 스포츠 문헌이 아니라 **데이터 통합(MDM)의 survivorship** 문제다.
표준 규칙이 넷이고, 우리 경우 둘이 **서로 반대를 가리킨다**:

| 규칙 | 우리에 적용하면 |
|---|---|
| **Most Trusted Source Wins** (출처 신뢰) | 공식 팀시트 > 기사 → **주전결장이 이긴다** |
| **Most Complete Wins** (완전성) | 전체 집계 > 부분 명단 → **주전결장이 이긴다** |
| **Most Recent** (최신) | 기사가 더 이를 수도, 늦을 수도 → 갈린다 |
| **Most Frequent** (빈도) | 해당 없음 |

> Profisee: "**완전성 규칙은 오류 위험이 높아** 다른 기법(최신성)과 함께,
> 또는 잘 안 바뀌는 속성에만 쓰는 것이 좋다."
> Profisee: "**속성 단위로 규칙을 짜라.** 'ERP 를 통째로 믿는다' 같은 레코드
> 단위 신뢰는 금세 문제가 된다."

베팅 쪽 자료도 같은 쪽을 가리킨다 — 종목 불문 **리그·구단의 공식 명단이
정산의 법적 기준**이고, 기사·전문가 해석은 맥락일 뿐 공식 지정을 뒤집지
못한다(ActionNetwork · Sharp Football).

**그래서 지금 코드는 규칙과 어긋난다.** PA-27 은 딥서치 `out` 을
`라인업결장` 축으로 만들고, PA-27-b 규칙이 그것으로 `주전결장` 을 대체한다.
**부분이 전체를 덮는다.** 기사가 두 명만 말하고 실제로 다섯 명이 빠졌으면
−6.0 이 −3.0 으로 **줄어든다.**

### 고쳤다 — PA-27-d (2026-09-17 · 사용자 "니생각대로 해")

**규칙 하나로 좁혔다: 대체는 완전한 출처만 한다.**

```
공식 XI diff   완전 + 신뢰  →  대체할 수 있다        (rejudge.CAN_REPLACE)
오늘 타순 집계  완전        →  대체 대상이 아니다
기사 결장 명단  부분        →  🔴 빈자리만 채운다. 남의 자리를 못 뺏는다
```

`주전결장` 이 있으면 부분 출처의 결장 축은 **대체도 가산도 안 한다 — 뺀다.**
대체하면 기사가 둘만 말했을 때 −6.0 이 −3.0 으로 줄고, 얹으면 PA-27-b 가
고친 이중 계산이 되살아난다. 물러난 사실은 `yielded_to`·`why` 에 남는다
("조용한 0"은 결함이다).

⚠️ **손해가 아니다.** `주전결장` 은 타순이 확정돼야 생긴다. 축구 판정은 T-3h
   라 그 구간엔 주전결장이 없고, 거기서는 기사 명단이 **유일한 신호**이고
   그대로 쓰인다. 물러나는 것은 **더 좋은 자료가 이미 있는 구간**뿐이다.

**안 고른 쪽 — 1번(딥서치 이름으로 `주전결장` 의 크기를 정밀화).** 이론상 제일
좋지만 `주전결장` 은 이름 집합이 아니라 **홈−원정 인원 차이 하나**다. 거기에
이름별 중요도를 녹이려면 변수를 새로 설계해야 하고, 그건 배선이 아니라 **새
코드**다. 방향을 먼저 바로잡고, `regraded_by` 로 갈린 표를 보고 정할 일이다.

---

## F-3 · 시장가치를 모르는 선수를 **평균으로 볼 것인가 대체선수로 볼 것인가** (2026-09-17 · PA-27)

**갈림길** — 딥서치 추출은 **이름만** 준다. `importance()` 는 아무것도 모르면
**1.0(평균 주전)** 을 돌려준다. 이게 맞나, 아니면 더 낮게 봐야 하나.

**찾은 자료 — 평균이 맞다. 단, 조건이 붙는다.**

| 출처 | 내용 |
|---|---|
| FanGraphs *Replacement Level* | 대체선수는 리그 최저 연봉으로 데려올 수 있는 수준 — 보통 **리그 평균의 80%** |
| Hockey Graphs (WAR 3부) | 평균을 기준으로 삼으면 **평균 선수의 출전 시간 가치를 못 본다** — 그래서 대체선수 개념이 따로 있다 |
| 미측정 리그 선수 처리 실무 | 대체선수는 **유스에게 너무 가혹**하고, 미측정 프로 리그 선수는 대체선수보다 나으며 출전 시간도 많다 → **리그 평균값을 쓴다** |

우리 경우는 뒤쪽이다 — 딥서치가 **이름을 낸** 선수는 유스가 아니라 기사에
날 만한 프로다. 오히려 **선택 효과**가 있다(기사는 주목할 선수를 쓴다) →
1.0 은 보수적인 쪽이다.

**🔴 다만 자료가 함께 경고하는 것이 있다 — "모름"을 "평균"과 못 가르는 것.**

> panna #242: 미평가 선수 평점을 **0 으로 채우자** 평점이 리그 중심화돼 있어
> 그 팀이 **"정확히 평균"으로 보였다.** "전 선수가 미평가인 팀은
> `home_sum_psr` 이 0 이고, 모델은 이것을 **진짜 중위 팀과 구별하지 못한다**."
> 제안된 고침 셋: ① **커버리지 지표**(`n_rated_players`)를 따로 넣어 모델이
> '미평가 스쿼드'를 별개 신호로 배우게 한다 ② 0 대신 **NA** 를 넘긴다
> ③ 최소한 **채워 넣었다는 사실을 로그로 남긴다**.

**우리 상태** — `importance()` 가 1.0 을 돌려주는 것은 **의도된 중립**이고
docstring 에 "지어내지 않는다"고 적혀 있다(①은 지켰다). 그러나 **몇 명의
가치를 실제로 알았는지는 아무 데도 안 남는다** — ③이 없다. `라인업결장 −3.0`
을 나중에 보면 "중요도 2.0인 두 명"인지 "모르는 두 명"인지 못 가른다.

### 고쳤다 — PA-27-d (2026-09-17)

`reweigh` 가 `value_coverage = {known, total}` 을 돌려주고, 모르는 사람이
있으면 사유에 `가치 아는 선수 n/m` 이 붙는다. **계산은 안 바뀐다** — 자료가
평균(1.0)을 지지하므로 값을 모른다고 벌점을 주지 않는다. 계약이 그것까지
잰다(`test_커버리지가_계산을_안_바꾼다`).

---

## F-4 · 변수를 **적중률로 채점할까 CLV 로 채점할까** (2026-09-17 · PA-28)

**갈림길** — 지시문 10단계는 "delta 방향이 **결과와** 맞았는가"라고 쓴다.
결과는 경기 결과(적중)인가, 마감 라인(CLV)인가.

**찾은 자료 — CLV 다. 갈리지 않는다.**

| 출처 | 내용 |
|---|---|
| ThePowerRank · Sharp Football | 포화된 시장에서는 **승률보다 CLV 가 더 나은 지표**다 |
| Pikkit · TheLines | 프로는 승패 기록이 아니라 CLV 를 주지표로 쓴다 — **장기 수익성을 더 잘 예측**한다 |
| Bet2Invest | CLV 는 **여러 베팅에 걸쳐 합산되므로** 개별 사건에 덜 흔들린다 → 작은 표본에서 유리 |
| XCLSV | "승패 기록은 그 자체로는 거의 아무 의미가 없다 — 55% 를 맞혀도 물밑일 수 있다" |

**우리 실측도 같은 쪽이다**(CLAUDE.md §1): 판정 확률 **AUC 0.5122**(판별력
없음) · 시장 확률 AUC 0.6421. 100건 남짓 표본에서 적중률로 변수를 끄고 켜는
것은 잡음을 재는 것이다.

**그래서 통계는 "평균 CLV"다.** Bet2Invest 의 "걸쳐 합산" 이 그 근거이고,
`prob.py` 결정 B 도 이미 **"평균 CLV 부호"** 라고 적어 두었다. 건별 부호
일치율은 **참고로만** 낸다(같은 평균이라도 흩어짐이 다를 수 있어 눈으로
보기에는 쓸모가 있다). 적중률도 표에 내되 **판정 근거로 쓰지 않는다** —
계약이 그것까지 잰다(`test_적중률은_참고일_뿐_판정을_안_바꾼다`).

**적용** — PA-28. 표본 문턱 100 은 `config/rules.yaml report.var_min_n` 이
원본이고, 못 미치면 **판단하지 않는다**("표본 부족"). 적은 표본으로 변수를
끄는 쪽이 켜 두는 쪽보다 위험하다 — **끈 변수는 다시 켜 볼 기회가 없다.**

---

## F-5 · 표를 **어떻게 내놓을까** — 도구인가 정기 발송인가 (2026-09-17 · RPT-1)

**갈림길** — `report.py` 다섯 함수가 전부 순수 함수라 **행을 넣어주는 쪽**이
없다(운영·도구 import 0건). 무엇을 만들어야 하나.

**찾은 자료 — 세 가지가 서로를 보탠다.**

| 출처 | 내용 |
|---|---|
| LogRocket | **대시보드 피로는 실재**하고 BI 를 실제로 쓰는 직원은 **약 30%** 뿐 — 대시보드는 "**누가 열어주기를 기다린다**" |
| LogRocket · Kaelio | 그래서 **이미 일하는 곳으로 밀어 넣는다.** 단 **전용 채널**에, **훑어볼 수 있게** — 아니면 알림 피로가 온다 |
| DEV · Bigeye | 개발 중엔 임시 CLI 로 되지만 **운영은 정기 잡 + 모니터링**이 권장(신뢰성·감사·알림) |

**깎아야 하는 지점 — 자료를 그대로 따르면 안 된다.**
Airflow·Dagster 같은 오케스트레이션은 **우리 규모에 과하다.** 우리는 이미
APScheduler 가 있고 `_send_daily_summary`(잡 → 순수 함수 → 텔레그램)가 같은
일을 한다.
그리고 **변수별 채점은 매일 볼 것이 아니다** — 문턱이 100건이라 그 전에는
전부 "표본 부족"이 나온다. 매일 보내면 같은 문구를 90일 보내게 되고, 그게
자료가 경고한 **알림 피로**다. `report.py` 는 이미 답을 갖고 있다 —
`CHECKPOINTS = [50, 150, 300]`, "그 수가 쌓일 때마다 다시 본다".

**결론 — 둘로 나눈다. A 를 먼저.**

| | 무엇 | 왜 이 순서인가 |
|---|---|---|
| **A** | `tools/report_vars.py` — 원장에서 행을 뽑아 `report.py` 에 넣고 찍는다 | B 가 A 없이는 못 만들어지고, **A 만으로 오늘 밤 결과를 볼 수 있다** |
| B | 그 어댑터를 스케줄러가 재사용해 **체크포인트에 닿았을 때만** 텔레그램 발송 | A 가 쓸 만한 표를 내는 것을 **본 뒤**에 건다 — 안 그러면 또 "만들고 안 이었다" |

**적용** — A = RPT-1 (2026-09-17). B 는 **안 만들었다** — 사용자 지시가
"a만 먼저" 였다.

---

## F-6 · 승자를 **LLM 이 정하나 코드가 정하나** (2026-09-17 · 규격 문서 §0)

**갈림길** — 「Gemini 판정 서술 규격」 §0 은 "Gemini 를 **판정하는 자에서
설명하는 자로** 바꾼다"고 한다. 그런데 이 저장소는 **페이블 방식**이다:

```
5d54e94  "최종 판정은 Anthropic Fable 이 단 한 번에 낸다"
         사용자 지시 2026-09-06: "마지막 판정은 단 한 번으로 제한하고 fable 로 정해라"
verdict.decide:  parsed["승자"] 가 없으면 판정 자체가 없다 · 주석 "승자가 본체다"
```
**지금은 LLM 이 승자를 정한다. 그게 설계다.** 규격은 그 뿌리를 바꾸자는 것이다.

**찾은 자료 — 갈린다. 그리고 갈리는 지점이 분명하다.**

### ① "LLM 은 판정 못 한다"는 **너무 센 말이다**

| 출처 | 내용 |
|---|---|
| LLM-SoccerArena (arXiv 2607.24573 · WC2026 104경기) | **Gemini 3.1 Pro 평균 브라이어 0.497 vs 시장 0.498** — 사실상 동률 |
| 같은 논문 | 웹 접근이 브라이어를 **0.535 → 0.512** 로 내린다(T−24h) |
| WC2026-Agents | 웹 에이전트 4종 중 **시장을 이긴 것은 없다** |
| AI World Cup (arXiv 2608.03416) | 10개 LLM 단일 예측 — GPT-5.5 Thinking 744점 선두 |

→ **프런티어 LLM 은 시장과 비긴다. 이기지는 못한다.**

### ② 그런데 **자기보고 확신은 확률이 아니다** — 여기는 안 갈린다

> "자기보고 확신은 정확도·총점 어느 쪽과도 무관했다. **자기보고 확신을
>  보정된 확률로 취급해서는 안 된다.**" — AI World Cup
> "보고된 확신은 반드시 보정돼 있지 않다 … **예측이 맞는지에 대한 신호로
>  해석해서는 안 된다.**" — LLM-SoccerArena

→ 우리는 이미 맞게 하고 있다. `verdict.shadow_level` 이 LLM 확신을 **섀도로
   내려 카드에 안 보낸다.** 규격 §0 의 절반은 **이미 구현돼 있다.**

### ③ 운영 구조의 통설은 규격 편이다

> 결정적 데이터 처리 계층이 분석의 뼈대를 맡고, **LLM 은 해석·설명·전달에
> 집중한다.** LLM 은 언어에 강하지만 **신뢰할 수 있는 수치 분석에는 여전히
> 약하고**, 최적화 목표가 재현성이 아니라 **그럴듯함**이다. — Towards Data Science
> 결정 계층이 판정을 내고 **서술 계층이 사람이 읽을 글을 만든다.** 이 분리가
> **사후 서술이 거짓 근거로 쓰이는 것을 막는다.** — 같은 글

→ 마지막 문장이 이 저장소와 정면으로 맞닿는다. 지금은 **같은 LLM 이 승자도
   정하고 그 승자를 정당화하는 글도 쓴다.** 서술이 판정의 독립 검증이 못 된다.

### 🔴 우리 실측은 **두 겹으로 오염돼 있다** — 이것부터 말해야 한다

CLAUDE.md 는 판정 확률 **AUC 0.5122 · 브라이어 0.2537**(시장 0.6421 · 0.2394)
을 근거로 쓴다. 오늘 운영 표도 355건에 **적중 0.549 · 브라이어 0.251** 이다.
그런데 그 숫자는 아래 두 조건에서 나왔다:

1. **판정이 배당을 못 봤다.** 종전 규칙이 "배당을 판정 입력에 절대 넣지
   않는다"였고 **2026-09-13 에 뒤집혔다.** 벤치마크는 개방형 접근이 브라이어를
   0.023 개선한다고 말한다 — 눈을 가린 판정을 재고 "LLM 은 못 한다"고 결론
   내린 셈이다.
2. **프런티어 모델이 아니다.** 시장과 비긴 것은 **Gemini 3.1 Pro** 다. 우리
   운영 판정은 무료 사슬이고, 오늘 배포 스모크에서 `gemini-3.5-flash-lite` 가
   **3회 중 2회 파싱 실패**했다.

→ **"LLM 이 승자를 정하면 안 된다"는 아직 측정으로 뒷받침되지 않았다.**
   측정된 것은 "**눈 가린 소형 모델**이 승자를 정하면 AUC 0.51"이다.

### 결론 — 셋으로 나뉘고, 셋의 확실성이 다르다

| | 자료가 말하는 것 | 지금 |
|---|---|---|
| **확신 등급** | LLM 자기보고를 쓰면 안 된다 — **확실** | ✅ 이미 섀도 |
| **서술·판정 분리** | 같은 주체가 결정하고 정당화하면 서술이 검증이 못 된다 — **통설** | 🔴 안 됨 |
| **승자** | 프런티어면 시장과 비긴다 · 우리 실측은 오염 — **미결** | LLM 이 정한다 |

🔴 **승자를 코드로 옮기는 것은 지금 결정하지 않는다.** 먼저 **잴 수 있다** —
원장의 `gate_vs_llm = 'diff'`(오늘 355건 중 **25건**)가 정확히 "코드와 LLM 이
갈린 경기"다. 갈렸을 때 누가 맞았는지를 세면 이 갈림길이 **자료가 아니라
우리 원장으로** 닫힌다. 25건은 아직 적고, 오늘 배포로 쌓이기 시작한다.

---

## F-7 · 승자를 코드가 덮으면 **서술은 무엇이 되나** (2026-09-17 · 규격 §0)

**갈림길** — P0-1(코드가 승자·확신을 덮어쓴다)을 되돌릴까, 둘까.

**찾은 자료 — 선택지 자체가 틀렸다. 둘 다 서술을 믿으면 안 된다.**

| 출처 | 내용 |
|---|---|
| Post-Hoc Reasoning in CoT (arXiv 2603.01437) | 모델은 **설명하기 전에 이미 답을 정해 놓았다** — 마지막 pre-CoT 토큰 활성에서 선형 디코딩으로 **AUC 0.9 이상** |
| 같은 논문 | 자기가 안 고른 답을 정당화하라고 **강제하면** 두 가지가 나온다: **confabulation(거짓 전제를 지어냄)** · non-entailment(전제는 맞는데 결론이 안 따라옴) |
| CoT in the Wild Is Not Always Faithful (arXiv 2503.08679) | 숨은 단서로 답해 놓고 **CoT 에서는 빼고** 사후 합리화를 쓴다 |
| Chain-of-Thought Is Not Explainability | 서술은 설명이 아니다 |

**두 갈래가 각자 다른 병을 앓는다:**

```
LLM 이 정하고 LLM 이 설명    → 앞뒤는 맞지만 **설명이 진짜 이유가 아니다**(사후 합리화)
코드가 정하고 LLM 이 설명    → **자기가 안 고른 답을 정당화**하는 상황 = confabulation 유발
```

🔴 **P0-1 의 구조가 정확히 두 번째다.** 우리 시스템은 이미 그 위험 위에 있다.

**그래서 답은 "누가 정하나"가 아니다:**
1. **서술을 검증으로 쓰지 않는다.** 검증은 `l1` 처럼 **외부 자료와 대조**하는 것뿐이다.
2. **승자가 바뀌면 서술을 버린다.** v3 는 DB 가 승자를 바꿀 때 이미 그렇게 한다
   (`_story = "" if ref["승자변경"]`). **코드 덮어쓰기(P0-1)에도 같은 규칙이
   있는지는 안 쟀다.** 없으면 그건 결정이 아니라 **결함**이다.

---

## F-8 · 서술 반려 뒤 **재호출을 허용할까** (2026-09-17 · 규격 §7-7)

**갈림길** — 규격은 "반려 시 재호출 최대 2회", 커밋 `5d54e94` 는 **"판정은 단
한 번"**(같은 재료로 0.440 → 0.590 → 0.450 으로 갈린 실측이 근거).

**찾은 자료 — 갈리지 않는다. 둘은 다른 것이다.**

| 출처 | 내용 |
|---|---|
| DEV (검증 실패 시 오류를 재시도에 먹여라) | **같은 프롬프트로 그냥 재시도하면 성공 확률이 대체로 같다.** 대신 검증 오류와 모델의 잘못된 출력을 **다음 프롬프트에 넣고** 그것만 고치라고 해야 한다 |
| 같은 글 | 오류를 입력으로 주면 "이름 붙은 구체적 실수"를 고치는 일이 되어 **훨씬 싼 작업**이다 |
| 실무 패턴 | 오류 유형별 힌트를 붙여 최대 3회 재호출 · 소진하면 결정적 폴백 |

```
막아야 할 것:  같은 재료로 **다시 굴리기**        ← 5d54e94 가 막은 것
허용해야 할 것: "네가 쓴 X 가 규칙 Y 를 어겼다, Y 만 고쳐라"  ← 다시 굴리기가 아니다
```

**안전장치까지 자료가 준다** — 재호출 결과의 **승자가 바뀌면 버린다.** 그러면
"판정은 단 한 번"이 글자 그대로 지켜지면서 형식 반려만 고쳐진다.

---

## F-9 · 서술의 **어조를 기계로 강제할까** (2026-09-17 · 규격 §5, §4)

**갈림길** — §5 "등급별 톤"·§4 "금지 패턴 8종"을 정규식으로 강제할까.

**찾은 자료 — 결정적 검사와 판단을 **가르라**고 한다.**

| 출처 | 내용 |
|---|---|
| Pydantic Logfire | **구조·스키마·필수 칸·금지 문자열·범위 안의 숫자** — 이건 결정적이고 비용이 0 이며 흔들리지 않는다. 그러나 **어조가 적절한지**는 문자열 비교가 아니다 |
| ThumbGate #3687 | 어휘 정규식이 **최종 심판**이면 그 오탐이 **상시 비용**이 된다 |
| 같은 이슈 | 그래서 어휘 일치가 나면 **싼 모델을 심판으로 한 번 더** 부르고, 그 판정을 전부 로그로 남겨 **오탐률을 실제로 잴 수 있게** 한다 |
| Pydantic Logfire | LLM 심판은 **성문 루브릭 + 실제 실패 예시**가 있어야 한다 — 실패 예시 없는 루브릭은 **전부 B 를 준다** |

**결론:**
- **§3 문장 수 · 300자 · 칸 누락**: 결정적 검사로 **바로 넣는다**(공짜·무드리프트)
- **§4 금지 패턴**: 넣되 **최종 심판으로 두지 않는다** — **표시(flag)** 로 두고
  오탐률을 원장에 쌓는다. 종전 계획("한 종류씩 넣고 오탐 측정")보다 한 걸음
  더 나간 것이고, 자료가 그쪽을 지지한다.
- **§5 등급별 톤**: **지금은 안 한다.** 실패 예시가 0 건이라 루브릭을 쓸 수
  없다. 위 표시가 쌓이면 그때 LLM 심판을 붙인다.

---

## F-10 · 결장 **한 명**을 셀 것인가 (2026-09-17 · S7 가감이 12/18 빔)

**갈림길** — 결장 1명은 `1.5%p` 인데 잡음 문턱이 `2.0%p` 다. **한 명은 늘 버려진다.**
실측:
```
딥서치 결장 1명 → adj_after={}              버림={라인업결장 -1.5}  changed=False
        2명 → adj_after={라인업결장 -3.0}   반영
```
그래서 오늘 딥서치가 **"서호철 1군 말소"·"고종욱 1군 말소"를 찾아냈는데
가감은 0** 이었다. 야구는 결장이 보통 한 명씩 난다.

**찾은 자료 — 1.5%p 라는 *크기*는 맞다.**

WAR 는 "그 선수를 잃으면 시즌 순위가 몇 경기 떨어지나"다
(Baseball-Reference · FanGraphs). 경기당으로 나누면:

| 선수 | 시즌 WAR | 경기당 = WAR/162 |
|---|---|---|
| 평균 주전 | 2 | **1.2%p** |
| 좋은 주전 | 4 | 2.5%p |
| 준스타 | 6 | 3.7%p |
| 역대급(예: 11.5 WAR) | 11.5 | **7.1%p** |

→ 중요도를 모르는 선수에게 주는 **1.5%p 는 "평균 주전" 자리**다. **크기는 맞다.**

**틀린 것은 문턱이다.** `MIN_CONTRIB_PP = 2.0` 은 **WAR 3.2 미만을 전부 버린다.**
야구에서 결장은 대개 한 명이고, 그 한 명은 대개 평균 주전이다 →
**구조적으로 항상 버려진다.**

⚠️ 축구는 다르다. F-1 에서 찾은 "라인업 변경 하나가 승률 2~9%p" 는 이 문턱을
   넘는다. **같은 문턱이 두 종목에 다르게 작동한다.**

🔴 **안 고쳤다.** 문턱은 `config/rules.yaml adjust.min_contrib_pp` 이고
   표 크기와 같은 **사용자 결정** 영역이다(CLAUDE.md "지시받지 않은 파라미터
   변경 금지"). 선택지는 셋:
   1. 문턱을 낮춘다(예 1.0) — 한 명도 센다. 잡음도 는다
   2. 종목별로 가른다 — 야구 1.0 · 축구 2.0
   3. 그대로 둔다 — 야구는 결장 2명 이상일 때만 센다

## F-11 · `last3` 를 **어디서** 얻을 것인가 (2026-09-18 · 확인률 0/15)

**갈림길** — 가설 need 의 `last3`(최근 3경기)를 **기사에서 LLM 으로 뽑을 것인가**,
**우리 DB(`games`)에서 셀 것인가.**

실측 2026-09-18 운영 원장(최근 5일):
```
last3   확인 0 · 반증 15 · 미상 11      ← 한 번도 채워진 적이 없다
```
기사 발췌에 "최근 3경기 전적"이 적혀 있을 이유가 없다. 그런데 **우리 DB 에는 있다**
(`games` 표 · `status='final'` · MLB 511경기).

**찾은 자료 — 최근 폼의 예측력은 0 에 가깝다.**

- Razzball 이 타자 최근 3·5일 성적을 기준 투영과 비교했다: *"previous 3 and 5 day
  performance provides **zero to negligible** (and likely not statistically
  significant) improvement upon baseline player projections."*
- FanGraphs·Grantland 는 모멘텀 효과가 있더라도 **최소**라고 본다. 야구 결과는
  연쇄가 아니라 **독립 시행에 가깝게** 움직인다.
- 평균 회귀가 더 강한 힘이다 — 긴 연승/연패는 통계적으로 불안정하다.

**고른 것 — DB 에서 채우되, 승패 예측에 쓰지 않는다.**

`last3` 는 지금도 **`동의` 라벨에서만** need 로 선다(`hypothesis.build`:
`"득점 환경(U/O)"`). 즉 용도가 **승패가 아니라 파생(언더/오버)** 이고, 그 용도에는
득점 환경 정보로서 값어치가 있다. DB 로 채우면 확인률 0% → 100% 가 되고 **LLM 콜은
한 건도 안 는다.**

**안 고른 쪽 — 기사 LLM 추출 유지.** 15번 시도해 0번 성공했다. 기사에 없는 것을
계속 묻는 것은 토큰만 태운다.

🔴 **함께 정정된 것 — `prior.form_pp` 는 배선하지 않는 것이 맞다.**
2026-09-18 에 "최근 5경기 보정(±4%p)이 만들어만 놓고 안 불린다"고 결함으로 보고했다.
위 자료가 그 반대를 가리킨다 — **최근 5경기로 확률을 ±4%p 움직일 근거가 없다.**
미배선은 결함이 아니라 **맞는 상태**다. 배선하려면 자체 실측이 먼저다.

---

## F-12 · 야구 need 에 **무엇**이 들어가야 하나 (2026-09-18 · 확인 6/133)

**갈림길** — 야구 need 는 `out`·`doubt`·`last3` 셋이다. 이대로 둘 것인가, 바꿀 것인가.

실측 2026-09-18 운영 원장(최근 5일):
```
out      확인  5 · 반증 25 · 미상 22     9.6%
doubt    확인  0 · 반증 30 · 미상 22     0.0%   ← 한 번도 없다
last3    확인  0 · 반증 15 · 미상 11     0.0%   ← F-11
```

**찾은 자료 — 야구에서 움직이는 것은 *선발투수*다.**

- *"In baseball, the single most impactful individual variable is the starting
  pitcher. A pitching matchup can swing the line dramatically."*
- 라인 이동도 같은 것을 말한다: *"in baseball, **pitching injuries drive odds
  changes**"* · *"minor injuries or **the absence of role players may have little
  effect** on betting markets."*
- 반면 팀 단위 지표(ERA·득실차)가 개별 타자보다 예측력이 높다는 결과도 있다
  (Wharton 논문 · TDS).

**갈린다고 적고 멈춘다 — 두 갈래가 남는다.**

1. **`doubt` 를 뺀다** — 자료가 지지한다. MLB 는 IL 등재/미등재로 이분되어
   "출전 불투명"이라는 상태가 기사에 잘 안 나온다(실측 0/30). 축구는 그 개념이
   실재하므로 **야구에서만** 뺀다(`_BASEBALL_OUT`).
2. **선발투수 축을 넣는다** — 자료가 가장 강하게 지지하지만, 추출 스키마 8칸에
   투수 칸이 **없다**(`hypothesis.FIELDS`). 칸을 늘리는 것은 수집·추출·채점 셋을
   동시에 건드리는 일이라 **사용자 지시 없이 열지 않는다.**

⚠️ 지금 `out` 은 **투수와 야수를 구분하지 않는다.** 자료가 말하는 "투수 부상이
   라인을 움직인다"를 우리는 못 재고 있다 — 같은 `out` 한 칸에 섞여 있다.

---

## F-13 · 결장을 **기사 LLM 으로** 뽑을 것인가 **공식 API 로** 받을 것인가 (2026-09-18)

**갈림길** — need `out` 을 채우는 경로.

실측: 기사 LLM 추출 확인률 **9.6%** (5/52). 같은 날 위성은 기사를 **513건** 모았다.

**찾은 자료 — 공식 API 가 더 신뢰할 수 있다.**

- statsapi 는 IL 등재/해제를 **구조화된 transaction** 으로 준다. 10일·15일·60일 IL
  구분과 사유 문자열이 포함된다.
- *"Using the official StatsAPI or MLB.com's official channels would generally
  provide **more reliable data than news scraping** or informal sources."*

**🔴 그런데 우리는 이미 그걸 하고 있다.** `app/collectors/absences.py` 머리말:

> *"[§2] 결장 정보 — statsapi(IL 명단 + 확정 라인업)로 **자체 산출**. 그동안 결장은
> Perplexity 산문에서만 왔고… 라인업 확정: 최근 타석 상위 9명 중 오늘 타순에 없는
> 선수가 곧 결장이다. IL이 아니어도(휴식·부진) 잡힌다."*

`pipeline.py:1782` 가 `fetch_for_games` 를 부르고 `statcast.py:589` 가
`merge_into_research` 로 **`research` 에 합친다.**

**고른 것 — 채점이 그 값을 보게 한다.**

`hypothesis.confirm` 은 위성 추출 상자(`read_extract` → `teams`)만 읽는다. **공식
API 로 만든 결장은 `research` 에 있고 채점은 그것을 안 본다.** 두 경로가 따로 돈다.
LLM 콜 0 · 새 수집 0 으로 확인률을 올릴 수 있는 가장 싼 길이다.

**안 고른 쪽 — 기사 추출을 공식 API 로 대체.** 대체하지 않는다. KBO·NPB 는 공식
피드가 약하고(KBO 는 말소 공시를 `_kbo_official` 로 이미 쓴다), 기사는 "휴식·부진"
같은 IL 밖 결장을 잡는다. **얹는 것이 아니라 합치는 것**이고, 충돌 시 우선순위는
F-2(MDM survivorship)가 이미 정했다 — **공식이 이긴다.**

---

## F-14 · 괴리 임계 **4%p** 가 맞나 (2026-09-18)

**갈림길** — `gate.py` 의 `|gap| < 4 → 동의(조사 생략)`. 4%p 를 낮춰 조사 대상을
늘릴 것인가.

**찾은 자료 — 쿠션 없이 엣지를 다 먹으면 손실이다.**

- 2024 MLB 플레이오프 실측: *"placing bets across all perceived edges resulted in
  an **overall loss** without stricter thresholds, though with a **3% cushion
  beyond the sportsbook margin**, it would have produced positive returns."*

**고른 것 — 4%p 유지.** 자료의 3% 쿠션과 같은 자릿수이고, 우리 값이 약간 더 보수적이다.
낮추면 조사 대상이 늘어 **비용이 늘고 엣지는 마진에 먹힌다.**

⚠️ 이 자료는 **베팅 임계**에 관한 것이고 우리 4%p 는 **조사 배분 임계**다. 정확히
   같은 것은 아니다 — 다만 "쿠션 없이 작은 괴리를 쫓으면 손해"라는 방향은 같다.

---

### 출처 (2026-09-18 추가)

- [Razzball — Does a hitter's last 3–5 games matter?](https://razzball.com/hitter-streakiness/)
- [FanGraphs — How to argue about momentum](https://blogs.fangraphs.com/how-to-argue-about-momentum/)
- [Grantland — MLB playoff myths](https://grantland.com/the-triangle/mlb-playoff-myths-to-ignore/)
- [Wharton — Forecasting MLB games using machine learning](https://fisher.wharton.upenn.edu/wp-content/uploads/2020/09/Thesis_Andrew-Cui.pdf)
- [TDS — ML algorithm for predicting MLB outcomes](https://towardsdatascience.com/a-machine-learning-algorithm-for-predicting-outcomes-of-mlb-games-fa17710f3c04/)
- [arXiv 2511.17733 — Complex matchup models and baseball win probability](https://arxiv.org/pdf/2511.17733)
- [MyBookie — Betting impact of injured players](https://www.mybookie.ag/sports-betting-guide/determining-wagering-impact-of-injured-players/)
- [MLB.com — Injury report](https://www.mlb.com/injury-report)
- [Wikipedia — Injured list](https://en.wikipedia.org/wiki/Injured_list)
- [Wikipedia — MLB transactions](https://en.wikipedia.org/wiki/Major_League_Baseball_transactions)

---

### 출처

- [Sportmonks — Predicted Lineups](https://www.sportmonks.com/football-api/predicted-lineups/)
- [Profisee — MDM Survivorship](https://profisee.com/blog/mdm-survivorship/)
- [Data Ladder — Guide to data survivorship](https://dataladder.com/guide-to-data-survivorship-how-to-build-the-golden-record/)
- [FanGraphs — Replacement Level](https://library.fangraphs.com/misc/war/replacement-level/)
- [Hockey Graphs — WAR: Replacement Level (Part 3)](https://hockey-graphs.com/2019/01/18/wins-above-replacement-replacement-level-decisions-results-and-final-remarks-part-3/)
- [panna #242 — zero-fill reads as average](https://github.com/peteowen1/panna/issues/242)
- [Baseball-Reference — Position Player WAR](https://www.baseball-reference.com/about/war_explained_position.shtml)
- [FanGraphs — Win Probability Added](https://blogs.fangraphs.com/i-think-win-probability-added-is-a-neat-statistic/)
- [Post-Hoc Reasoning in Chain of Thought (arXiv 2603.01437)](https://arxiv.org/html/2603.01437)
- [CoT Reasoning In The Wild Is Not Always Faithful (arXiv 2503.08679)](https://arxiv.org/pdf/2503.08679)
- [DEV — Feed the validation error back into the retry](https://dev.to/nhirschfeld/when-an-llm-response-fails-validation-feed-the-error-back-into-the-retry-2e1e)
- [Pydantic Logfire — LLM as a Judge: rubrics, scores, agreement](https://pydantic.dev/logfire/llm-as-a-judge)
- [LLM-SoccerArena (arXiv 2607.24573)](https://arxiv.org/abs/2607.24573)
- [AI World Cup 2026 (arXiv 2608.03416)](https://arxiv.org/abs/2608.03416)
- [Towards Data Science — Hybrid AI: deterministic analytics + LLM reasoning](https://towardsdatascience.com/hybrid-ai-combining-deterministic-analytics-with-llm-reasoning/)
- [LogRocket — Slack workflows for PMs who hate dashboards](https://blog.logrocket.com/product-management/ai-powered-slack-workflows-for-product-managers/)
- [Kaelio — Automated metrics digests in Slack](https://www.kaelio.com/blog/how-to-set-up-automated-business-metrics-digests-in-slack)
- [Bigeye — Which scheduler should I use](https://www.bigeye.com/blog/which-scheduler-should-i-use-for-dbt-jobs)
- [ThePowerRank — Closing line value](https://thepowerrank.com/2021/07/29/closing-line-value/)
- [Sharp Football — CLV betting](https://www.sharpfootballanalysis.com/sportsbook/clv-betting/)
- [Bet2Invest — CLV applied to sports betting](https://bet2invest.com/blog/Closing-Line-Value-(CLV)-Applied-to-Sports-Betting:-A-Key-Indicator-for-Bettors)
- [ActionNetwork — Prop betting rules: if the player doesn't play](https://www.actionnetwork.com/education/prop-betting-rules-what-happens-if-player-doesnt-play)
- [OddsIndex — How injuries impact betting lines](https://oddsindex.com/guides/injury-impact-betting-guide)
