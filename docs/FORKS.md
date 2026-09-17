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

### 출처

- [Sportmonks — Predicted Lineups](https://www.sportmonks.com/football-api/predicted-lineups/)
- [Profisee — MDM Survivorship](https://profisee.com/blog/mdm-survivorship/)
- [Data Ladder — Guide to data survivorship](https://dataladder.com/guide-to-data-survivorship-how-to-build-the-golden-record/)
- [FanGraphs — Replacement Level](https://library.fangraphs.com/misc/war/replacement-level/)
- [Hockey Graphs — WAR: Replacement Level (Part 3)](https://hockey-graphs.com/2019/01/18/wins-above-replacement-replacement-level-decisions-results-and-final-remarks-part-3/)
- [panna #242 — zero-fill reads as average](https://github.com/peteowen1/panna/issues/242)
- [LogRocket — Slack workflows for PMs who hate dashboards](https://blog.logrocket.com/product-management/ai-powered-slack-workflows-for-product-managers/)
- [Kaelio — Automated metrics digests in Slack](https://www.kaelio.com/blog/how-to-set-up-automated-business-metrics-digests-in-slack)
- [Bigeye — Which scheduler should I use](https://www.bigeye.com/blog/which-scheduler-should-i-use-for-dbt-jobs)
- [ThePowerRank — Closing line value](https://thepowerrank.com/2021/07/29/closing-line-value/)
- [Sharp Football — CLV betting](https://www.sharpfootballanalysis.com/sportsbook/clv-betting/)
- [Bet2Invest — CLV applied to sports betting](https://bet2invest.com/blog/Closing-Line-Value-(CLV)-Applied-to-Sports-Betting:-A-Key-Indicator-for-Bettors)
- [ActionNetwork — Prop betting rules: if the player doesn't play](https://www.actionnetwork.com/education/prop-betting-rules-what-happens-if-player-doesnt-play)
- [OddsIndex — How injuries impact betting lines](https://oddsindex.com/guides/injury-impact-betting-guide)
