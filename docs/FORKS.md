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

🔴 **[2026-09-18 페이블 검토] 두 축을 구분한다 — 같은 "최근 3경기"가 아니다.**

| 축 | 무엇 | 예측력 | 우리 처리 |
|---|---|---|---|
| **팀 최근 3경기** (`last3` · `form_recent5`) | 팀 승패 흐름 | **없음** — "zero to negligible"(Razzball) · 모멘텀 최소(FanGraphs) | 파생(U/O) 득점 환경 재료로만. **승패 확률을 움직이지 않는다** |
| **선발 최근 3등판** (`starter_recent3`) | 그 투수의 이닝·실점·투구수 | **가장 큼** — "개별 변수 중 가장 영향이 큰 것은 선발투수" · 교체 시 머니라인 40~60센트(F-16) | **핵심(core) 변수.** 채점 문턱에 든다 |

⚠️ 이름이 비슷해 한 줄로 묶기 쉽다. **묶으면 가장 중요한 축을 예측력 0 짜리와
   같은 취급 하게 된다.** F-11 의 "최근 폼은 예측력이 없다"는 **팀 흐름**에만
   해당하고, 선발 등판 기록에는 해당하지 않는다.

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

## F-15 · 야구에 `doubt`(출전 불투명)가 실재하는가 (2026-09-18 · 확인 0/30)

**갈림길** — `_BASEBALL_OUT` 에서 `doubt` 를 뺄 것인가.
2026-09-18 에 나는 **"야구에는 그 개념이 없다(축구 개념이다)"** 고 말했다.

🔴 **그 말이 틀렸다.** 딥서치가 반대를 가리킨다:

> **Day-to-Day (DTD):** 아프거나 다쳤지만 한두 경기 이상 빠질 것으로 보지 않는 상태.
> 최소 결장 일수도, 로스터 보호도, 연봉 처리도 없다.
> *"IL 에 올리는 대신, 팀은 그를 로스터에 두고 **day-to-day** 로 알릴 수 있다 —
> 의료진이 언제 복귀할지 판단하지 못한다는 뜻이다."* (Wikipedia · FantasyNewsAuthority)

**즉 `doubt` 는 야구에도 실재한다.** 우리 확인률 0/30 은 개념이 없어서가 아니다.

**그런데 구조화된 소스가 없다 — 실측으로 확인했다.**

`statsapi.mlb.com/api/v1/teams/{id}/roster?rosterType=fullRoster` 를 3개 구단에 대해
전수 조회한 결과, 상태 코드는 이것뿐이다:
```
A(Active) · D7 · D10 · D15 · D60 · ILF(Full Season)
RM · RES · DEV · RST · DES · TI
→ "Day To Day" 코드 없음
```
DTD 는 **로스터 상태가 아니다.** 그 선수는 `A(Active)` 로 남는다. 위 인용이 말한 그대로다 —
IL 에 안 올리는 것이 DTD 의 정의이므로 **정의상 공식 로스터에 안 나타난다.**

DTD 를 얻으려면 2차 소스(MLB.com 부상 리포트 · RotoWire · FanGraphs RosterResource)나
기사가 필요하다. 그런데 기사 추출은 **0/30** 이다.

**고른 것 — 야구 `doubt` 는 뺀다. 단, 이유를 바꿔 적는다.**

빼는 결론은 같지만 **이유가 다르고, 그 차이가 중요하다**:
- ❌ "야구에는 그 상태가 없다" → 틀렸다. 영영 안 되돌린다는 뜻이 되어 위험하다.
- ✅ **"실재하지만 우리에게 구조화된 소스가 없다"** → 소스가 생기면 되살릴 축이다.

⚠️ **되살릴 조건을 함께 적는다**: DTD 를 주는 2차 소스를 붙이는 날, `doubt` 를
   `_BASEBALL_OUT` 에 되돌린다. 그때까지는 분모에 두면 문턱만 높인다(5칸 중 2칸이
   구조적으로 0 이면 문턱 2 를 넘기가 거의 불가능하다).

**안 고른 쪽 — 그대로 두기.** 30번 시도해 0번 성공한 칸을 분모에 남기는 것은
채점을 못 하게 만드는 것과 같다.

✅ **[2026-09-18] 적용됨.** 야구에서만 뺐다 —
   `config/rules.yaml` `flow.adjust_prior_pp.baseball` · `hypothesis._BASEBALL_OUT`.
   **축구는 그대로다**(`_SOCCER_OUT` 에 `doubt` 유지 — 개념도 소스도 있다).
   되살릴 조건은 위 ⚠️ 그대로다. 계약 테스트가 두 종목을 갈라 잠근다.

---

## F-16 · 선발투수 축을 **새 칸으로** 만들 것인가 (2026-09-18)

**갈림길** — 야구 need 에 선발투수가 없다. 추출 스키마에 칸을 늘릴 것인가.
2026-09-18 에 나는 **"이름표가 세 곳에 있어 큰 작업"** 이라고 말했다.

**찾은 자료 — 선발은 야구에서 가장 큰 단일 변수이고, 그 크기가 수치로 있다.**

- *"야구에서 개별 변수 중 가장 영향이 큰 것은 **선발투수**다. 투수 매치업 하나가
  라인을 크게 흔든다."*
- 선발 교체(scratch)의 크기:
  · 전면 선발이 빠지면 **머니라인 40~60센트** · 토탈은 **1점 이상**
  · 에이스 → 하위 선발 교체는 **30~50센트**
  · 중위 → 중위는 5~10센트
- 빈도: *"리그 전체로 **주당 여러 번**"*
- *"늦은 선발 교체는 주의 깊은 베터에게 **가장 값어치 있는 라인 이동 사건**이다.
  시작 90분 안에 발표되고 대체 투수가 아직 없으면 북은 마켓을 내리거나 유금을 넓힌다."*

머니라인 40~60센트는 우리 게이트 임계(4%p)의 **두세 배** 크기다.

🔴 **그런데 우리는 이미 감지하고 있다 — 내 "세 곳" 발언이 틀렸다.**

```
app/pipeline.py:1246   starter_change_notes(research, before)
                       → "홈 선발 변경: {old} → {new}"
app/pipeline.py:1753   "starter_changed": lineup_status == "conflict"
app/pipeline.py:3943   주석: "경기 직전 선발 교체는 시장이 늦게 반영하는
                              몇 안 되는 신호다"
app/scheduler.py:830   r["home_pitcher"] != game["home_pitcher"]
app/research/deep.py:457  `starter_changed` → 리서치 강제 갱신 트리거
```

감지는 있고 **리서치 갱신까지** 간다. 가는 곳이 거기서 끝난다 — 가설(`hypothesis.FIELDS`)에
투수 칸이 없고, 채점(`confirm`)은 위성 추출 상자만 본다.

**즉 WIR-1 과 완전히 같은 패턴이다: 만들어 놓고 안 이었다.**

그리고 WIR-1 로 붙인 공식 결장 문장에는 **역할 표시가 이미 있다**:
```
"Cincinnati Reds의 Hunter Greene(선발) Injured 60-Day로 결장"
                              ^^^^^^ absences._describe 가 붙인다
```

**고른 것 — 스키마를 늘리기 전에 배선부터 본다.**

두 경로가 이미 존재한다:
1. **결장한 선발** — `absences` 문장의 `(선발)` 표시 (WIR-1 로 채점에 이미 들어간다)
2. **교체된 선발(scratch)** — `starter_change_notes` (채점에 안 들어간다)

칸을 늘리는 것은 **수집·저장·채점 셋이 동시에 움직이는 일**이고, 위 둘로 충분한지
아직 안 쟀다. **재고 나서 정한다** — 그전에 스키마를 건드리지 않는다.

⚠️ **갈린다고 적고 멈추는 자리다.** 자료는 "선발이 제일 중요하다"고 강하게 말하지만,
   그것이 **"새 칸이 필요하다"로 곧장 이어지지 않는다.** 이미 있는 두 신호를 채점에
   잇는 것이 더 싸고, 안 되면 그때 칸을 논한다.

---

### 출처 (2026-09-18 추가 · F-15·F-16)

- [Wikipedia — Injured list (day-to-day)](https://en.wikipedia.org/wiki/Injured_list)
- [FantasyNewsAuthority — Official MLB/NFL/NBA/NHL injury designations](https://fantasynewsauthority.com/understanding-official-injury-designations)
- [FanGraphs RosterResource — 2026 Injury Report](https://www.fangraphs.com/roster-resource/injury-report)
- [ActionNetwork — MLB betting rules for scratched pitchers](https://www.actionnetwork.com/mlb/mlb-betting-rules-for-scratched-pitchers-action-vs-listed)
- [ParlayTools — MLB starting pitcher betting](https://parlaytools.com/articles/mlb-starting-pitcher-betting/)
- [Sports Insights — Action vs. listed pitcher](https://www.sportsinsights.com/blog/mlb-betting-lines-action-vs-listed-pitcher/)
- 실측: `statsapi.mlb.com/api/v1/teams/{113,119,111}/roster?rosterType=fullRoster`
  (2026-09-18 · 상태 코드 12종 전수 · DTD 없음)

## F-17 · 가설을 **시장 전에** 세울 것인가 (2026-09-18 · 사용자 지시)

**사용자 지시 원문:** *"시장에 끌려가지 않고 우리 쪽 판단을 먼저 적는 게 중요함.
페이블도 이렇게 '내 가설부터 세우고 검증'하는 스타일이야."*

**갈림길** — 지금은 `gate.classify` 가 시장이 없으면 **보드 고정**을 돌려주고,
`hypothesis.build(BOARD)` 는 `need = ()` 다. 즉 **배당이 안 오면 가설이 통째로 없다.**

실측 2026-09-18 17:10:
```
09-19 mlb   15경기 · 배당 14 · 이름표 14      ← MLB 는 하루 전에 붙는다
09-19 kbo    4경기 · 배당  0 · 이름표  0      🔴 가설 0
09-20 kbo    5경기 · 배당  0 · 이름표  0      🔴 가설 0
```
팀도 알고 티어도 있고 올해 성적도 있는데, **시장이 안 왔다고 아무 가설도 안 선다.**

---

### 찾은 자료 ① — 시장을 먼저 보면 내 판단이 오염된다 (사용자 방향 지지)

- NFL 베팅 시장에서 **앵커링 편향이 실증**됐다. 베터도 북메이커도 시즌 내내 프리시즌
  우승 배당에 끌린다 (ScienceDirect 2025).
- Pinnacle: *"북메이커가 공개한 가격이 **잠재의식적으로** 그 경기를 보는 눈을 바꾼다 —
  가격을 보기 **전에** 경기를 연구했다면 다른 견해를 가졌을 수 있다."*
- *"자기 확률을 직접 계산하는 도박꾼은 **극소수**이고, 대다수는 북이 매긴 가격을 먼저
  본다 — 그래서 앵커링이 판단 과정에 들어간다."*
- 슈퍼포캐스팅 방법론의 핵심은 **순서**다:
  *"**The order matters. Sequence, not weighting.**"* — 기준율(외부 관점)로 먼저 닻을
  내리고, **그 다음에야** 개별 사정(내부 관점)으로 조정한다.

### 찾은 자료 ② — 그래도 시장이 최종적으로는 더 낫다 (반대편)

- 종가(closing line)는 **가장 효율적인 가격**이고, CLV 가 장기 수익의 최고 예측자다.
- *"종가는 경기 시점의 모든 알려진 정보를 반영한다 — 부상·날씨·라인업·샤프머니.
  즉 **당신이 모델을 만들 때 없던 정보**가 들어 있다."*
- 시장 효율성은 "모든 가격이 완벽하다"가 아니라 "명백한 오류는 빠르게 경쟁으로
  사라진다"는 뜻이고, 그래서 엣지는 작고 빠르고 체계적이어야 한다.

### 🔴 둘은 충돌하지 않는다 — 우리 구조가 이미 갈라 놓았다

우리 봇에서 **확률과 조사 방향은 다른 물건**이다:

```
p_code   = 시장 뼈대 + 조정          ← 시장 효율성을 이미 존중한다
p_prior  = 티어 + 올해 성적          ← "p_prior 는 p_code 에 더하지 않는다"(prior.py)
           쓰이는 곳은 게이트와 카드 서술 둘뿐
```

그러니 **가설을 사전값 기준으로 먼저 세워도 확률은 한 글자도 안 바뀐다.**
바뀌는 것은 "무엇을 조사할지"뿐이다.

그리고 자료 ②가 오히려 자료 ①을 요구한다 — **CLV 로 채점하려면 독립적인 사전
판단이 있어야 한다.** 라인을 보고 만든 견해로는 "내가 종가를 이겼다"가 성립하지
않는다(그 견해가 이미 라인의 함수이므로). FORKS **F-4** 에서 우리는 이미 승률 대신
CLV 를 고르기로 했다 — 그 선택이 사전 판단의 독립성을 **전제**한다.

### 고른 것 — **가설은 사전값만으로 먼저 세운다. 시장은 검증·수정한다.**

```
종전   사전값 → [시장 대기] → 게이트 → 가설
이후   사전값 → 가설 → (시장 도착) → 게이트가 다시 분류
```

- 시장이 없을 때의 가설은 **한 종류뿐이다** — "우리 사전값을 무너뜨릴 근거를 찾아라"
  (지금 `가치 의심` 이 만드는 need 와 같다). 비교 대상이 없을 때 정직한 조사는 그것뿐이다.
- 시장이 오면 게이트가 다시 분류한다. 방향이 **뒤집힐 수 있다**(시장 과대). 그건
  결함이 아니라 검증이 작동한 것이고, 두 시점이 원장에 다 남아야 "가설이 맞았나"를 잰다.
- ⚠️ `prior.py` 가 이미 같은 원칙을 뉴스에 대해 적어 두었다 —
  *"사전값은 검색 전에 확정한다. 검색 후 적으면 뉴스 어조에 끌린다."*
  **시장에 대해서만 그 규칙이 없었다.** 이 항목이 그 구멍을 메운다.

### 안 고른 쪽 — 지금대로(시장 없으면 보드 고정)

게이트의 원래 목적이 "딥서치를 **어디에 쓸지** 고른다"이므로, 시장이 없으면 값어치
있는 자리를 모른다는 반론이 있다. **그 반론은 조사 배분에는 맞지만 가설 생성에는
맞지 않는다** — 가설은 순수 함수라 비용이 0이고, 배분은 그 위의 §3 예산(30%·최대 8)이
이미 막는다. 둘을 한 문에 묶어 둔 것이 문제였다.

⚠️ **범위를 갈라 둔다.** 이 항목은 **가설 생성**만 연다. 시장 없는 가설을 §3 예산
경쟁에 넣을지는 **별개 결정**이고 그건 LLM 콜을 늘린다 — 여기서 함께 열지 않는다.

---

### 출처 (2026-09-18 추가 · F-17)

- [ScienceDirect — Anchoring bias in the NFL gambling market](https://www.sciencedirect.com/science/article/pii/S0165176525001259)
- [Pinnacle — Anchoring bias and odds movement](https://www.pinnacle.com/betting-resources/en/educational/how-to-solve-a-problem-like-efficiency-part-two/ks5jtmy67w9xfggm)
- [Cultivate Labs — Superforecasting: everything has a base rate](https://www.cultivatelabs.com/posts/superforecasting-everything-has-a-base-rate)
- [WisdomFromExperts — How superforecasters use the inside/outside view](https://wisdomfromexperts.com/how-superforecasters-use-the-inside-outside-view/)
- [Joe Saumarez — Market efficiency and the role of the closing line](https://joesaumarez.co.uk/sports-betting-market-efficiency-and-the-closing-line)
- [Bet-Analytix — Closing odds as the ultimate indicator](https://www.bet-analytix.com/academy/closing-odds-ultimate-indicator)
- [NYU Stern — Finding inefficiency in sports betting markets](https://www.stern.nyu.edu/sites/default/files/assets/documents/con_042958.pdf)

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

## F-18 — T-3h·T-60 export 산출물을 어디에 두나 (2026-09-19)

**무엇이 갈렸나.** 마스터 지시문 1-1 은 산출물이 `~/Downloads/analystbot_export/`(로컬)
와 운영 컨테이너 `/data/export/`(백업) **둘 다**에 생기기를 요구한다. 그런데
스케줄러는 Railway 컨테이너 안에서 돌기 때문에 사용자 맥에 직접 쓸 수 없고,
`/data` 는 애초에 존재하지 않는다.

```
$ railway ssh ... "df -h; ls -la /data"
overlay  2.9T ... /
ls: cannot access '/data': No such file or directory
```

갈래는 둘이었다 — (a) Railway Volume 을 `/data` 에 붙인다 (b) 산출물을 Postgres 에
넣고 파일은 임시로만 쓴다.

**어떤 자료를 찾았나.**

- Railway 기본 컨테이너 파일시스템은 **재배포·재시작마다 초기화**된다. 볼륨 밖에
  쓴 것은 복구되지 않는다 — 공식 문서와 사용자 사고 보고가 같은 말을 한다.
  → [Railway Services](https://docs.railway.com/reference/services) ·
    [Critical Data Loss Issue — Ephemeral Storage](https://station.railway.com/questions/critical-data-loss-issue-ephemeral-sto-5f150da4)
  `RAILWAY_VOLUME_MOUNT_PATH` 아래에 쓴 것만 남는다.
- Postgres 쪽 반대 근거도 찾았다: 2KB 를 넘는 값은 TOAST 로 빠지고, 그 뒤로는
  JSONB 접근 성능이 나빠질 수 있다.
  → [PostgreSQL TOAST](https://www.postgresql.org/docs/current/storage-toast.html) ·
    [pganalyze — JSONB TOAST 성능 절벽](https://pganalyze.com/blog/5mins-postgres-jsonb-toast)

**무엇을 골랐나 — (a) 볼륨.**

지시문이 경로를 `/data/export/` 로 **이름을 대어** 지정했고, 그 경로가 살아남는
방법은 볼륨뿐이다. 볼륨 생성은 코드가 아니라 인프라 설정이라 1-1 의 수정 범위
(인자·잡·파일명)를 넓히지 않는다. 산출물은 하루 몇 MB라 100GB 한도에 무관하다.

**안 고른 쪽은 왜 안 골랐나.**

(b) Postgres 는 내구성은 같지만 **새 테이블·마이그레이션·조회 도구**가 필요해
수정 범위를 넘는다. 게다가 우리 산출물은 245KB 짜리 통짜 문서이고 안을 질의하지
않는데, 굳이 TOAST 경계를 넘는 값을 DB 에 넣을 이유가 없다. 찾은 자료도 그 경계
너머를 권하지 않았다.

⚠️ **로컬 절반은 여전히 사람이 당긴다.** 서버가 주체이고(메모리 규칙) 맥이 켜져
   있을 필요가 없어야 하므로, 컨테이너가 볼륨에 쓰고 로컬은 필요할 때 받아간다.

## F-19 — 페이블 판정을 원장 어디에 넣나 (2026-09-19)

**무엇이 갈렸나.** 사람이 건 픽(페이블 채팅 판정·승률 모드)을 봇 판정과 나란히
기록해야 한다(지시문 1-4 · 7-2). 그런데 `pick_ledger` 에는 이 인덱스가 있다:

```sql
CREATE UNIQUE INDEX idx_pick_ledger_final ON pick_ledger (game_id) WHERE is_final;
```

한 경기에 `is_final` 행은 **하나뿐**이다. 갈래는 셋 —
(a) 인덱스를 `(game_id, judge_by)` 로 넓힌다 (b) 사람 픽을 별도 표에 둔다
(c) 사람 픽을 `is_final=false` 로 넣는다.

**어떤 자료를 찾았나.**

(a) 를 고르면 곧바로 함정이 하나 있다. 기존 1,382행의 `judge_by` 가 NULL 이면
**유니크가 풀린다** — 같은 경기에 NULL 행이 여러 개 들어간다. Postgres 는
유니크 인덱스에서 NULL 을 서로 다른 값으로 보기 때문이다(기본
`NULLS DISTINCT`). PG15 부터 `NULLS NOT DISTINCT` 가 있지만 기본값은 여전히
`DISTINCT` 다.
→ [Unique Indexes](https://www.postgresql.org/docs/9.0/indexes-unique.html) ·
  [Partial Indexes](https://www.postgresql.org/docs/9.6/indexes-partial.html) ·
  [EDB — unique constraint with NULL](https://www.enterprisedb.com/postgres-tutorials/postgresql-unique-constraint-null-allowing-only-one-null)

**무엇을 골랐나 — (a), 단 `judge_by` 를 `NOT NULL DEFAULT 'bot_v14'` 로.**

기본값이 있으면 기존 행이 그 자리에서 `bot_v14` 로 채워지고(PG11+ 는 표를 다시
쓰지도 않는다), NULL 이 없으니 유니크가 온전하다. 지시문의 "기존 행 이관은
`judge_by=bot_v14`" 도 이 한 수로 끝난다.

**안 고른 쪽은 왜 안 골랐나.**

(b) 별도 표는 `report.py --by judge_by` 와 `--compare`(7-2)가 매번 UNION 을
해야 하고, 채점·CLV 잡도 두 곳을 봐야 한다 — 같은 성질의 행을 두 곳에 두는 것은
나중에 한쪽만 고치게 된다.
(c) `is_final=false` 는 이 저장소에서 **"재판정으로 밀려난 옛 행"** 이라는 뜻이
이미 정해져 있다(`merged_from` 주석). 사람 픽은 옛 행이 아니다. 뜻이 둘이 되면
계수기가 틀린다(09-08 계수기 규율).

---

## F-20 — ⑥의 **반증**은 픽을 철회하는가, 강화하는가 (2026-09-20 · CNF-2)

**무엇이 갈렸나.**
⑥의 반증(`refuted` = "찾아봤는데 없다")이 핵심 변수에서 나면 무엇을 해야 하나.
저장소가 **두 갈래로** 말하고 있었다:

```
hypothesis.py:11-13   가치 의심 → 우리 쪽을 무너뜨릴 근거를 찾는다
                      (못 찾으면 사전값이 틀린 것이다)            → 철회
hypothesis.confirm    refuted 를 세기만 하고 철회하지 않는다       → 중립
n06_verdict.py:5      핵심이 refuted → 반박됨(픽 철회)            → 철회
```

이것이 실제 문제가 된 이유: ⑥의 반증이 **구조적으로 불가능**했고(실측 최근
2h `{'unknown': 496, 'confirmed': 137}` · 반증 0건), 그것을 고쳐 반증을 켜는
순간 `lineup_out` 이 핵심 변수(`rules.yaml` `core: True`)이므로 **결장 0명인
건강한 라인업 경기가 전부 철회**된다.

**어떤 자료를 찾았나.**
- *Rational Inferences From Absent Data* (Princeton CoCoSci) ·
  *When does absence of evidence constitute evidence of absence?*
  (Forensic Science International, Bayesian confirmation theory) ·
  *Bayesian reanalysis of null results reported in medicine* (PMC5919013)
- 공통 원리: **absence of evidence is evidence of absence to the degree that
  evidence would have been expected had the claim been true.**
  즉 관건은 **탐지 가능성**이다. 찾았으면 나왔을 상황에서 안 나온 것은 강한
  증거이고, 애초에 안 찾았거나 소스가 없던 것은 증거가 아니다.

**무엇을 골랐나.**
🔴 **반증의 뜻은 가설의 주장에 달렸다.** 게이트가 주장을 정하므로 ④가 싣고
⑥이 읽는다(표의 원본은 `app/flow/labels.REFUTED_MEANS` 하나다):

| 가설 | 주장 | 반증 = 주장이 틀림 | 픽 |
|---|---|---|---|
| `H_fade` (시장과대) | 시장 반대편을 세울 근거가 있다 | 근거 없음 | **철회** |
| `H_break` (가치의심·사전값단독) | 우리 픽을 무너뜨릴 근거가 있다 | 무너뜨릴 게 없음 | **강화** |
| `H_deriv` (동의) | 파생 재료 | — | **중립** |

그리고 **탐지 가능성을 코드로 가른다**: ⑤는 결장 수집이 **돌았을 때만**
(`absences` 1건 이상) "두 팀 해당 0명" 행을 남긴다. 수집이 아예 안 돌았으면
행을 만들지 않는다 — 그건 모름이고, **모름을 반증으로 둔갑시키는 것**이 이
수정의 최대 위험이다.

**안 고른 쪽은 왜 안 골랐나.**
- **언제나 철회**(종전): 위 자료의 조건을 무시한다. "안 찾아서 없다"와 "찾았는데
  없다"를 같게 보고, `H_break` 에서는 **좋은 소식을 나쁜 소식으로 읽는다.**
- **언제나 중립**(`confirm` 의 현재 동작): `H_fade` 에서 "시장 반대편을 세울
  근거가 전혀 없다"는 사실을 버린다. 그건 시장이 맞다는 가장 직접적인 신호다.

**남은 것(등록만).**
`scout_config.validate:427` 이 LLM 이 내지 않은 칸까지 `[]`/`""` 로 채운다.
바로 위 `:416` 주석이 "빈 목록은 사실이다 · 결손과 구분해서 읽어야 한다"고
적는데 그 줄이 구분을 없앤다. 상자 경로를 ⑥이 아직 쓰지 않아 이번 범위 밖이다
(**4-8-c**).

---

## F-21 — 축구 ① 사전값을 무엇으로 만드나 (2026-09-20 · SELO-1)

**무엇이 갈렸나.**
축구 7리그 전부 `① 사전값 = null` 이고 오늘 슬레이트 `n03_freeze` 21건 중
18건이 축구였다. 레이팅 소스로 셋이 있었고 **어느 것도 명백하지 않았다.**

**어떤 자료를 찾았나 — 셋 다 실측으로 닫았다.**

| 안 | 실측 원문 | 판정 |
|---|---|---|
| (a) 우리 `games` 로 자체 Elo | 축구 종료 경기 **131건** · 팀당 **2.5~5.1** (라리가 5.1 · 세리에A 3.9 · EPL 2.5 · 분데스 2.6). 야구는 MLB 35.5 · KBO 70.8 · NPB 34.8 | 🔴 **기각** |
| (b) ClubElo API (지시문 STEP 10 이 지정) | `http://api.clubelo.com/2026-09-20` **502** · `/2026-09-19` 502 · `/2026-09-18` 502 · `/Barcelona` 502 · `/Fixtures` → `200 "Fixtures API deactivated"` · https 는 ConnectTimeout | 🔴 **기각** |
| (c) football-data.co.uk (`app/models/soccer_elo.py`) | 서버에서 `refresh()` 성공 — 10리그(E0·E1·D1·SP1·I1·F1·N1·P1·DNK·JPN) · `E0.csv` 200/203KB · `JPN.csv` 200/572KB | ✅ **채택** |

(a)의 근거: `tools/fit_elo.py` 머리말이 **야구**(팀당 ~12 유효경기)에서도
"레이팅이 거의 벌어지지 않는다 — 축은 넣었는데 **진폭이 없다**"고 적었다.
축구는 그 1/3 이다.

**무엇을 골랐나.**
(c) football-data.co.uk. 레이팅은 Redis `elo:{리그}:{날짜}` — **야구와 같은
자리**다(`team_elo.CACHE_KEY`, TTL 26h). `n01_prior` 는 이미 그 키를 읽고
축구 3-way(`draw_prior`) 분기를 갖고 있어 **읽는 쪽을 한 줄도 고치지 않았다.**

**부수 갈림길 — 이름 대조를 어떻게 하나.**
(c)를 막던 것은 Elo 가 아니라 이름이었다: elo 는 `Arsenal`·`Ath Bilbao`,
우리는 `Arsenal FC`·`Athletic Club` — **144팀 중 2개만 일치.**
딥서치 결과 football-data.co.uk 는 클럽 이름을 *"copied as is including
typos"* 로 싣고 **공식 대조표가 존재하지 않는다.** `soccerdata` 가 래퍼를
제공하지만 새 의존성이라 쓰지 않았다.

→ `config/elo_names.yaml` 에 표를 만들었다(106항목·6리그). 규칙은 셋:
같은 리그 안에서만 · 토큰 일치(접두 축약은 **짧은 토큰 5자 이하**) ·
상호 유일할 때만 확정. 나머지는 손으로 적고 항목마다 사실 하나다.

⚠️ 접두를 느슨하게 뒀을 때 **오매칭이 났다** — `Rayo Vallecano` →
`Valladolid`(공통 접두 `vall`). CLAUDE.md 가 경고한 자리(AC밀란 오매칭)다.
5자 상한으로 조이고 Vallecano 는 명시 표로 옮겼다. 계약 테스트가 *한 elo
이름에 다른 팀이 붙는 것*을 토큰 포함 관계로 막는다.

**안 고른 쪽은 왜 안 골랐나.**
- 자체 Elo: 표본이 없다. 넣으면 **전 팀이 비슷한 레이팅**이 되어 ①이
  "모른다"를 "비슷하다"로 위장한다 — 그게 더 나쁘다.
- ClubElo: 지시문이 지정했지만 **소스가 죽어 있다.** 지시문을 따르는 것보다
  실측이 앞선다(추측 금지).
- 퍼지 문자열 유사도: CLAUDE.md 가 금지한다. 실제로 내 느슨한 규칙이
  오매칭을 냈다.

**남은 것.** K리그1·ACL엘리트는 football-data.co.uk 에 **리그 자체가 없다**
→ 사전값없음 경로(STEP 1-e). 그리고 채택 여부의 AUC 검증은 STEP 10 이다 —
여기서는 **배선만** 했다.

---

## F-22 — 순위·득실차를 사전값에 넣을 것인가 (2026-09-20 · **닫힌 결정**)

**무엇이 갈렸나.**
딥서치 로그(K리그·J리그 2026-09-13)가 쓴 수동 확률 산출법:

```
기본값   축구 홈 우위 사전값 ≈ 홈 45 / 무 27 / 원정 28
실력 축  순위·득실차로 ±5~8%p 조정 (J1 은 6경기라 조정폭 절반)
최근 폼  최근 5경기 방향으로 ±3~5%p
```

그 방식은 그 자리에서는 합리적이었다 — 배당도 Elo 도 없이 손으로 재는
상황이었다. 문제는 **우리 봇에 옮길 것인가**다.

**결정 — 옮기지 않는다.**

🔴 **순위·득실차를 ① 사전값에 넣지 않는다.** CLAUDE.md 판정 입력 동결이
   "시즌 누적(방어율·타율·**순위**) 금지"라고 못박고 있고, 그 동결은
   2026-09-04·09-07 사용자 결정이다. 이 딥서치 로그는 그것을 뒤집을 **실측이
   아니다** — 한 사람이 한 번 손으로 잰 방법일 뿐이다.

🔴 **순위는 `motivation_state` 에만 쓴다**(v2 STEP 7-3). "1위 다툼·강등권·
   확정/탈락"은 **동기**의 근거이지 실력의 근거가 아니다. 그 구분이 동결의 뜻이다.

🔴 **무승부 사전값의 원본은 우리 값이다 — `draw_prior` 0.26.**
   로그의 0.27 을 가져오지 않는다. 비슷하다고 남의 숫자로 바꾸면 그때부터
   우리 값이 어디서 왔는지 아무도 모른다(사본 금지).

**안 고른 쪽은 왜 안 골랐나.**
"조정폭이 작으니(±5~8%p) 괜찮다"는 이유가 될 수 없다. 동결의 목적은 크기가
아니라 **입력 목록**이다 — 한 번 열면 다음에는 승률이, 그다음에는 타율이 들어온다.
실제로 이 저장소는 그 경로로 AUC 0.51 짜리 판정을 만든 적이 있다(MODEL.md §1).

**⚠️ 함께 확인된 사실(반대 근거가 아니라 제약):**
`games(final)` 적재가 축구 4리그·팀당 1~7경기뿐이라 **DB 계산 순위도 지금은
불가능하다**(STEP0 문서 0-e 추가). 즉 순위는 당분간 외부 표에서만 오고,
그렇기에 더더욱 **동기 용도로 한정**하는 편이 안전하다.

---

## F-23 — 리그를 언제 여나 (2026-09-20 · **닫힌 결정** · LGA-1b)

**무엇이 갈렸나.**
`results` 만 켠 리그(리그앙·에레디비시)를 언제 `odds`·`satellite`·`router`·
`judge` 로 넓힐 것인가. "자료가 오니 바로 열자"와 "준비될 때까지 닫자"가 갈렸다.

**결정 — 셋이 모두 갖춰졌을 때만 연다.**

```
(a) 소급 적재 완결   팀당 경기 수가 리그 라운드 수와 맞는다 (STEP 1-i-3)
(b) 배당 스냅샷      그 리그 경기에 open/open_proxy 가 실제로 있다
(c) 위성 URL 실측    config/sources.yaml 의 그 리그 소스가 fetch 성공
```

셋이 되면 `aliases` 를 채워 라우터에 노출한다. **그 전에는 열지 않는다.**

**왜.** 라우터에 보이면 사용자가 부른다. 그때 나가는 것은 "자료 없음"이 아니라
**빈 카드**다 — 사전값도 배당도 결장도 없는데 형식만 갖춘 답이 가장 나쁘다.

**역방향도 잠근다.**
🔴 `judge`/`router` 를 켜려면 `results` 와 그 **적재 경로**(`fd_names` 또는
`fotmob_id`)가 **먼저** 있어야 한다. 없으면 판정만 쌓이고 **영원히 채점되지
않는다** — 실측 2026-09-20: **ACL 8건**이 판정 8 · 채점 0 · 결과 0 이었다.

그 잠금은 지금 **일부러 실패한다**(`j1`·`denmark`·`kleague1`·`acl` 네 리그가
`xfail`). 고치는 것은 STEP 1-i-2 이고, **xfail 이 남은 채로 1-i-2 를 닫지
않는다**(`tests/test_lga1b_feature_lock.py`).

**안 고른 쪽은 왜 안 골랐나.**
"결과만이라도 보여 주자"는 카드의 값어치를 **적중이 아니라 설명의 구체성**에
둔다는 원칙(CLAUDE.md MODEL.md §1)과 정면으로 어긋난다. 설명할 재료가 없는
카드는 구체성이 0이다.

## F-18 — 검색 체인의 최후 폴백 (2026-09-21)

**무엇이 갈렸나.** DS-3a 지시문은 "상한 도달 시 다음 공급자 → **마지막은
rss_google**" 이라고 적는데, `news.google.com/rss/search` 는 robots 거부다.
최후 폴백이 거부 경로면 체인 전체가 성립하지 않는다.

**어떤 자료를 찾았나** (전부 직접 수신 · `docs/SEARCH_PATH_2026-09-21.md`):
- `news.google.com/robots.txt` — `*` 는 `Disallow: /` + 화이트리스트이고 거기
  `/rss/` 가 없다. 게다가 `ClaudeBot`·`anthropic-ai`·`GPTBot`·`PerplexityBot`
  을 **이름으로 지목해** `Disallow: /` 한다.
- `bing.com/robots.txt` — `/search` 는 막지만 **`/news/…` 를 막는 줄이 없다.**
  실측: ko 11항목 2.3s · ja 11항목, 전부 200.
- GDELT DOC 2.0 — 무료·키 불필요지만 **5초 1회 제한**이고 회수 품질이 나빴다
  (`プロ野球` 질의 → 기사 2건, 둘 다 무관).
- 매체 자체 RSS(동아 50 · 한경 50 · 연합뉴스TV 11) — 허용이지만 **검색이 아니다.**

**무엇을 골랐나.** 🔴 **고르지 않았다.** 지시문 본문이 "마지막은 rss_google"
이라고 못박고 있어 그 줄을 바꾸는 것은 사용자 결정이다. 제안만 적었다
(`chain: [bing_news_rss, media_rss]`).

**안 고른 쪽은 왜.** GDELT 는 5초 제한이 슬레이트당 수십 질의와 맞지 않는다.
DuckDuckGo 는 허용이지만 지금 **Tor 경유**라 "우회 금지" 규율과 물린다(충돌 1).

**축구도 쟀다**(사용자 지시 "축구도 필히"). EPL 9항목·최근2일 3(`Arsenal XI vs
Brighton: Confirmed team news`) · 라리가 12·3(`Alineación confirmada del Real
Madrid`) · 분데스 7 · J리그 8 · K리그 3.
🔴 **현지어가 결정적이다** — 라리가는 `alineación` 으로 물어야 확정 라인업이 온다.

🔴 **이 갈림길에서 나온 뜻밖의 것**: Bing 질의가 09-21 주니치 **확정 스타멘**을
전날 22:19 기사로 돌려줬다. 그날 우리가 몇 시간을 쓰고도 못 찾은 값이다.
**자료가 없던 게 아니라 검색 경로가 막혀 있었다.**

---

## F-19 — 기사 신선도 창이 **두 벌**이다 (2026-09-22 · **결정 대기**)

### 무엇이 갈렸나

`verify` 를 기사 경로에 이으면서(WIR-3) 창이 둘인 것이 드러났다.

```
scout_config.MAX_AGE_H['pre']     48h · **지금 시각** 기준 · rss_hits 가 쓴다
situation.SITUATION_WINDOW_HOURS  24h · **킥오프** 기준  · classify 가 쓴다
                                       (MLB 만 36h)
```

둘은 **소비처가 다르다** — 48h 는 LLM 추출 입력, 24h 는 카드의 상황 태그.
같은 자료에 두 자를 대는 것이 지금까지 문제가 안 된 이유가 그것이다.
`verify` 를 추출 경로에 얹는 순간 **둘이 같은 자료에 겹친다.**

### 어떤 자료를 찾았나 — **우리 원장이 이미 갖고 있다** (딥서치 불필요)

두 값 모두 이 저장소의 실측에 근거가 붙어 있다. 검색보다 실측이 가깝다.

**24h 쪽 근거** (`situation.py` 머리말 · 2026-09-06~07):
```
경기가 17~18시라 전날 저녁 예고·공지까지는 오늘의 재료다.
MLB 기사 332건 창별 통과 태그: 12h=5 · 24h=32 · 36h=34 · 48h=34 · 72h=34
  → 36h 위로는 늘지 않는다. KBO·NPB 는 24h — 넓히면 김성현 은퇴식(T-24.8h)이 되살아난다.
```

**48h 쪽 근거** (오늘 절제 실험 · KBO 2경기 18건):
```
종전 18 → 래핑 -6 = 12 → 리캡 -1 = 11 → **24h창 -9 = 2**

24h 가 버리는 것들(원문):
  [프로야구 전망] ‘불붙은 타선’ KT 위즈, SSG 상대로 3연승 정조준
  대만 매체 "왕옌청 한국전 선발 불발…한화와 차출 조건 합의"[AG]
  [AI프리뷰] 20일 수원 KT-두산전, 대체 선발 박신지 …
```

🔴 **자료가 갈린다.** 24h 는 **상황 태그**(은퇴식 같은 잡음을 막는 것)에서
   검증됐고, 48h 는 **추출 입력**(프리뷰·선발 기사를 살리는 것)에서 검증됐다.
   같은 숫자가 두 목적에 맞을 이유가 없다 — 그러니 "하나로 합치자"가 답이
   아닐 수 있다. **억지로 하나로 만들지 않았다.**

### 무엇을 골랐나

🔴 **고르지 않았다.** `verify(..., window: bool = True)` 스위치를 두고
`rss_hits` 는 `window=False` 로 부른다 — **지금 동작은 종전과 같다**(48h).
래핑·리캡 폐기만 새로 걸린다.

### 사용자에게 묻는 것

| 갈래 | 뜻 | 대가 |
|---|---|---|
| (가) 지금대로 — 추출은 48h, 태그는 24h | 소비처마다 다른 자 | 같은 기사가 추출엔 들어가고 태그엔 안 나온다(설명 불일치) |
| (나) 추출도 24h(`window=True`) | 자가 하나 | 실측 18건 → 2건. 오늘 프리뷰가 사라진다 |
| (다) 태그를 48h 로 넓힌다 | 자가 하나 | 2026-09-06 실측이 막은 것(은퇴식)이 되살아난다 |
| (라) 추출 창을 따로 정한다(36h 등) | 목적별로 잰다 | 새 상수 하나 — **사용자 승인 필요** |

⚠️ 어느 쪽이든 **한 단어**(`window=`) 또는 상수 하나로 뒤집힌다.

---

## F-20 — 결과가 적을 때 무엇으로 채점하는가 (2026-09-23)

**사용자 지시:** "딥서치해서 찾아서 수정해라" (문제 1 — 성적을 잴 수 없다)

### 무엇이 갈렸나

흐름 판정의 성적을 재야 하는데 **끝난 경기가 1건**이었다. 셋 중 하나를 골라야 했다.

| 갈래 | 내용 | 대가 |
|---|---|---|
| (가) 결과(win/loss)를 기다린다 | 가장 정직 | 표본이 하루 몇 건씩만 는다 |
| (나) **CLV(종가 대비)로 잰다** | 결과 없이 즉시 | CLV 자체도 200~500건은 필요 |
| (다) 과거 경기에 흐름을 소급해 돌린다 | 표본을 즉시 확보 | **look-ahead 누설** 위험 |

### 찾은 자료

- **CLV 는 결과보다 빠른 신호다.** 적중률은 "결과 지표"이고 CLV 는 "과정
  지표"다. 50건 표본의 60% 적중은 운으로도 나오지만 CLV 는 같은 표본에서
  훨씬 덜 흔들린다. 양의 CLV 를 꾸준히 내는 쪽이 장기 수익을 내고, 음이면
  못 낸다 — 적중률은 분산에 크게 흔들려 상관이 약하다.
  → [Pikkit — What Is CLV](https://pikkit.com/blog/what-is-closing-line-value) ·
    [VSiN — The Importance of CLV](https://vsin.com/how-to-bet/the-importance-of-closing-line-value/) ·
    [Rob Brown — CLV Explained](https://robbrownbetting.com/closing-line-value-clv-explained/)
- ⚠️ **CLV 도 만능은 아니다.** 200건 이상에서 60~65%가 종가를 이겨야 "값을
  찾는다"고 말할 수 있고, 확신 있는 증거는 300~500건이다. 지금 목표는
  **결론이 아니라 잴 수 있게 만드는 것**이다.
- **소급(다)은 누설이 첫째 위험이다.** 결정 시점에 없던 정보를 쓰면 성적이
  부풀고 실전에서 사라진다. 축구 예측 사례연구도 look-ahead 를 1순위 위협으로
  다루며 같은 날 정보에 **시간 완충**을 둔다.
  → [Purged cross-validation](https://en.wikipedia.org/wiki/Purged_cross-validation) ·
    [LaLiga 누설 인지 워크플로](https://www.sciencedirect.com/science/article/pii/S2590005626003620) ·
    [Look-ahead bias in backtests](https://www.marketcalls.in/machine-learning/understanding-look-ahead-bias-and-how-to-avoid-it-in-trading-strategies.html)

### 무엇을 골랐나 — **(나) CLV**

실측이 갈래를 갈랐다:

```
flow_v14 원장 경기 23
  종료(결과로 채점 가능)      2건
  종가 스냅샷 있음(CLV 가능)  17건    ← 8배
```

도구도 이미 있었다 — `learning.prices.close_p` · `learning.metrics.clv`.
**부르는 곳만 없었다.**

### 안 고른 쪽은 왜

- **(가)** 를 버린 것이 아니다. `grade_pending` 은 그대로 돌고 결과가 들어오는
  대로 채점한다. CLV 를 **먼저** 쓸 뿐이다.
- **(다) 소급은 안 한다.** 흐름이 읽는 값 중 `games.home_pitcher` 와
  `analysis:{sport}` 캐시는 **오늘 값**이라 과거 경기에 그대로 쓰면 누설이다.
  등판·최근3 질의는 `starts_at < kickoff` 로 이미 시점 안전하지만, 안전한
  칸과 아닌 칸이 섞여 있어 "일부만 안전한 소급"은 믿을 수 없다.
  🔴 하려면 각 칸에 `available_at` 을 붙이는 일이 먼저다(LE-2 가 같은 말을
  한다) — 별건이고 지시를 받아야 한다.

---

## F-21 — CLV 를 선택당 몇 번 세는가 (2026-09-23)

**사용자 지시:** "지금 안되는것만 딥서치 해서 고치라고"

### 무엇이 갈렸나

흐름은 한 경기를 15분마다 다시 판단한다. 그 판단마다 CLV 가 생기는데,
**전부 세는가 / 하나만 세는가**가 갈렸다.

### 실측이 문제를 보여줬다

```
행 590 · CLV 정확히 0 인 행 200 (33.9%)
킥오프까지 남은 시간(분)  최소 4 · 중앙 287 · 최대 769
  0~30분    33행 · CLV0 27 · 양수   0 · 평균 -0.00172
  30~90분   68행 · CLV0 50 · 양수   0 · 평균 -0.00221   ← 양수 0건
  90~180분  88행 · CLV0 34 · 양수  28 · 평균 -0.00011
  180분+   401행 · CLV0 89 · 양수 166 · 평균 +0.00273
```

킥오프 직전 재평가는 **정의상 CLV≈0 또는 음수**다 — 그 가격이 이미 종가다.
전부 섞어 평균 내니 "종가를 이긴 비율 30.8%" 라는 거짓 비관이 나왔다.

### 찾은 자료

- **"베팅 시점에 받은 가격은 고정된 스냅샷이고 재평가하지 않는다."** CLV 는
  선택당 한 번 재는 것이고, 진입 기록과 마감 기록은 같은 경기·같은 북·같은
  마켓·같은 선택이어야 한다.
- **마감 기준을 일관되게 정의하라** — 예: T−5분.
- 진 베팅도 양의 CLV 를 가질 수 있고 이긴 베팅도 음일 수 있다 — CLV 는
  결과와 분리된 **과정 지표**다.
  → [Sportmonks — CLV](https://www.sportmonks.com/glossary/closing-line-value-clv/) ·
    [Pinnacle Odds Dropper — Buchdahl](https://www.pinnacleoddsdropper.com/blog/closing-line-value--clv-demystified-by-expert-joseph-buchdahl) ·
    [SportsBettingDime — CLV](https://www.sportsbettingdime.com/guides/betting-101/closing-line-value/)

### 무엇을 골랐나 — **선택당 첫 판단 하나**

`DISTINCT ON (game_id, side) … ORDER BY ts_decided` — 가장 이른 판단이
"가격을 받은 시점"에 해당한다.

🔴 **자료를 지우지 않았다.** 원장의 590행은 그대로 두고 **세는 법**만 고쳤다 —
언제 무엇을 판단했는지는 라인 이동 학습의 재료이기 때문이다.

🔴 **CLV 0 을 따로 센다.** 0 은 "졌다"가 아니라 "시장이 안 움직였다"다.
섞으면 거짓 비관이 나온다.

⚠️ **200건 미만이면 결론을 붙이지 않는다**(F-20 과 같은 근거). `/health` 가
   "표본 n/200, 아직 결론 금지"라고 그대로 적는다.

### 안 고른 쪽은 왜

- **전부 세기**는 늦은 재평가가 표본을 지배해 일찍 내린 판단의 값어치를
  지운다 — 위 시간대별 표가 그 증거다.
- **마지막 판단 하나**도 안 골랐다. 그건 종가에 가장 가까운 판단이라
  CLV 가 구조적으로 0 에 붙는다.

---

## F-22 · 사전값은 **확률에 섞는가, 방향만 정하는가** (2026-09-23)

**사용자 지시** — "페이블처럼 경기분석을 해야 한다..논문을 찾아서 프로그램
수정해라...딥서치를 하든..."

**갈림길** — `model_w = 0.0` 이라 ①사전값이 최종 확률에 **한 방울도** 안
들어간다. 이것이 (a) 고쳐야 할 결함인가, (b) 옳은 설계인가.

⚠️ 내가 이 세션에서 두 번 (a) 라고 보고했다. **둘 다 틀렸다.**

### 찾은 자료 — 세 갈래로 갈린다

| 출처 | 말하는 것 |
|---|---|
| Egidi 외, *Combining historical data and bookmakers' odds* (arXiv 1802.08848) | 득점률을 역사자료 모수와 배당의 **볼록결합**으로 둔다 → 적합·예측 개선 |
| *Forecast Sports Outcomes under EMH* (arXiv 2604.17194, 90,014경기) | 특징을 더하는 것은 **개념적 실수** — 시장이 이미 담은 관계를 다시 담는다. 역사자료는 시장이 **체계적으로 잘못 매기는 편향 하나**(favourite-longshot)에만 아껴 쓴다 |
| *Beating the market with a bad predictive model* (arXiv 2010.12508) | 수익은 정확도가 아니라 **시장과의 비상관**에서 온다. 시장을 잘 맞히는 모델은 정확해도 쓸모가 없다 |

🔴 **갈린다고 적고, 값은 우리 자료로 정했다.** 논문은 가설을 주고 데이터가
판정한다 — 이 저장소의 규칙이자 페이블식 순서 그 자체다.

### 우리 자료가 판정한 것 (walk-forward · 누수 없음 · 2026-09-23)

`p = w·사전값 + (1−w)·시장`, 종가 직전 pre-kickoff h2h 를 책별 중앙값으로
비그 제거. 사전값은 `tools/fit_elo.ratings_asof`(그 경기 이전 행만).

```
model_w      KBO(n=76)   NPB(n=92)   MLB(n=294)      ← logloss, 낮을수록 좋다
  0.0  ★     0.65837     0.65281     0.65945
  0.3        0.65983     0.66040     0.66690
  0.5        0.66233     0.66666     0.67294
  1.0        0.67371     0.68661     0.69181
```
**세 종목 전부 w=0 이 최적이고, w 를 올릴수록 단조적으로 나빠진다.**
→ **(b) 가 맞다. `model_w = 0.0` 은 결함이 아니라 실측이 지지하는 설계다.**
   CLAUDE.md 가 이미 그렇게 적고 있었다("`p_code` 는 지금처럼 시장을 뼈대로
   쓴다… 떼는 것은 **조사 방향**이다").

### 같은 자료가 가리킨 **진짜 결함**

괴리 구간별, 각 쪽이 고른 팀의 실제 적중률:
```
         KBO            NPB             MLB
 0~3%p   57.1 / 52.4    60.0 / 66.7     47.7 / 43.2     (사전값 / 시장)
 3~6%p   62.5 / 68.8    41.2 / 58.8     54.3 / 53.1
 6~9%p   46.2 / 46.2    64.3 / 85.7     60.3 / 69.0
 9~12%p  70.0 / 60.0    58.8 / 47.1     54.3 / 71.4
 12%p~   64.3 / 71.4    45.5 / 90.9     56.2 / 78.1
```
🔴 **사전값은 시장보다 나쁘고, 괴리가 클수록 더 나쁘다.** 그런데
   `n01_prior.py:119` 에서 **그 사전값이 픽을 정한다**:
```python
state.pick_side = "home" if ph >= (pa or 0) else "away"
```
그 뒤 ⑧이 확률을 **시장**에서 만들기 때문에, 둘이 갈리면 산출이 모순된다 —
**고른 쪽의 승률이 50% 미만**이 된다. 실측 30일 **17/58 = 29.3%**.
오늘 KIA@두산이 그것이다(① 두산 50.5% 픽 → ⑧ 두산 41.2%).

바깥 자료도 같은 방향이다 — 시장 대비 10%p 이상 괴리가 난 픽은 50경기에서
**25%** 적중(문턱 미만 약 58%)으로, 크게 갈릴수록 **틀린 쪽은 모델**이었다
→ [model-vs-market shrink 실측](https://github.com/cerealbowles/sports-betting/pull/53) ·
  [CLV 로 검증한다](https://www.sports-ai.dev/blog/closing-line-value-and-ai-model-performance)

### 무엇을 골랐나 — **한 칸이 두 일을 하고 있다. 나눈다.**

`pick_side` 하나가 서로 다른 두 질문에 답하고 있다:

| 질문 | 지금 | 실측이 말하는 답 |
|---|---|---|
| **무엇을 조사할까** (④가설·⑤수집) | 사전값 | **사전값이 맞다** — 시장을 보고 정하면 앵커링이고 CLV 가 성립하지 않는다 |
| **누구를 고르나** (⑦⑧⑨⑪·원장) | 사전값 | **시장이 맞다** — 전 구간에서 사전값보다 낫다 |

🔴 **둘 다 옳은데 한 칸에 담겨 있어서 29.3% 가 모순이 된다.**
   `hyp_side`(조사 방향 · ①이 정한다)와 `pick_side`(판정 방향 · ②가 정한다)로
   **나누는 것**이 이 갈림길의 답이다.

### 안 고른 쪽은 왜

- **`model_w` 를 올린다** — 세 종목 462경기가 전부 반대다. 볼록결합
  (Egidi)은 우리 사전값의 품질에서는 성립하지 않는다.
- **사전값을 버린다** — 그러면 시장의 함수가 되어 비상관이 0 이 된다
  (arXiv 2010.12508). 조사 방향은 사전값이 계속 정해야 한다.
- **픽을 그대로 두고 50% 미만을 허용한다** — 지금 상태다. ⑪이 전건
  거절하므로 카드가 영영 안 나간다.

### 실행 기록 — SIDE-2 · SIDE-3 (2026-09-23)

```
SIDE-2  hyp_side(①) / pick_side(⑧) 분리 · 커밋 9f35248 · 테스트 5,946 passed
        ⚠️ 구현 중 내가 넣은 축구 결함(1−홈을 원정으로 읽음)을 기존 가드
           `test_종목_분기가_한_곳에만_있다` 가 잡았다. 계약 4개로 잠갔다.

SIDE-3  원장 방향 복원 — 운영에서 1회 실행 (코드 추가 없음)
        748행 중 **298행(39.8%)** 이 반대 팀으로 적혀 있었다
          ⚠️ 종전 보고 22.4% 는 30일·⑧도달 경기만이라 과소였다
        side · p_model · p_market · price 를 스냅샷에서 복원,
        clv/result 를 비워 기존 잡(`grade_pending`·`fill_clv`)이 다시 채우게 했다
        옛 값은 `note` 에 `[SIDE-3]` 표시와 함께 남겼다 — 원본을 지우지 않았다
        쏠림 home 525:221 → **432:316**
        CLV 748행 재계산 · 요약 n=120 avg −0.002787 (움직인 88 중 이긴 50)
        ⚠️ n=120 은 결론 문턱 200 미만이다 — 결론을 붙이지 않는다(F-20)
```

---

## F-23 · 배당 위생 문턱을 **얼마로** 둘 것인가 (2026-09-23 · ODD-S (나))

**갈림길** — (가)에서 `합 < 1`(불가능)을 걸렀는데 NPB 진동이 절반 남았다
(ρ₁ −0.5751 → −0.4062). **문턱을 더 올릴 것인가.**

### 잔여의 정체 — 마진이 얇은 스냅샷

NPB 에서 1%p 이상 튄 증분 193건을 갈라 보면 둘이다:
```
진짜 이동   양쪽이 같이 움직이고 마진 유지
  g3202  1.53/2.47 (1.0585) → 1.69/2.13 (1.0612)  −5.99%p
  g4784  1.64/2.22 (1.0602) → 1.51/2.53 (1.0575)  +5.11%p
마진 붕괴   한쪽이 고정이고 마진이 무너진다
  g3602  1.83/2.17 (**1.0073**) ↔ 1.83/1.83 (1.0929)  ±4.25%p 반복
  g3203  1.98/2.00 (**1.0051**) → 1.75/2.05 (1.0592)
193건 중 63건(32.6%)이 한쪽 스냅샷 마진 1.03 미만
```

### 문턱을 올려 봤다 — **반대 위험까지 함께 쟀다**

```
        남김%    ρ₁        종가−시가(정보)   n
KBO 1.00  96.0  −0.1561   +0.00534        74
    1.03  93.2  −0.0576   +0.00525        74
NPB 1.00  97.5  −0.4062   **+0.00332**    89   ← 부호가 뒤집힌 자리
    1.02  95.8  −0.2297   +0.00150        89
    1.03  94.6  −0.1424   +0.00198        89
    1.04  93.3  −0.1029   +0.00071        89
MLB 1.00  99.9  +0.0007   +0.00167       293
    1.03  93.9  −0.0010   +0.00185      **249**  ← 경기 44개가 통째로 사라진다
```

### 무엇을 골랐나 — **문턱 1.00 그대로. 올리지 않는다.**

🔴 **`합 < 1` 하나만으로 NPB 의 실질 문제가 해결된다.** 종가−시가가
   −0.00896 → +0.00332 로 **부호가 뒤집힌다** — 이동이 정보를 파괴하던 것이
   멈춘다. 그것이 이 작업의 목적이었다.

🔴 **ρ₁ 을 목표로 삼으면 안 된다.** 문턱을 올릴수록 ρ₁ 은 계속 좋아지지만
   (−0.41 → −0.10) **정보는 오히려 줄고**(NPB +0.0033 → +0.0007) MLB 는
   채점 가능 경기가 293 → 249 로 빠진다. 데이터를 깎아 지표를 예쁘게 만드는
   것이고, 실제 목적은 나빠진다.
   ⚠️ CLAUDE.md 규율 그대로다 — "새 필터·가드를 추가할 때는 **반대 위험
      (정상 데이터 폐기)을 함께 측정**한다."

🔴 **남은 ρ₁ −0.41 은 무해한 잔여로 둔다.** 진동은 있지만 종가의 정보를
   파괴하지 않는다. 지표가 나쁘다는 이유만으로 더 깎지 않는다.

### 안 고른 쪽은 왜

- **1.02~1.04 문턱** — 위 표가 전부 반대다. 정보가 줄고 경기가 빠진다.
- **NPB 만 다른 문턱** — 종목별 문턱은 근거가 있을 때만 나눈다. 여기서는
  1.00 이 세 종목 모두에서 최선이라 나눌 이유가 없다.
- **얇은 마진 행을 표시만 하고 읽는 쪽이 거르게** — 읽는 곳이 여럿이라
  사본이 된다. 필요해지면 `impossible_set` 옆에 두고 한 곳에서 판정한다.
