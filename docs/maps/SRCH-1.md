# SRCH-1 — x_search 삭제 · 2차 검증(⑤) 삭제

사용자 지시 2026-09-12:
- "x seach 삭제....그자리에 안트로픽 서치로"
- "퍼플릭스와 안트로픽...x 삭제...그리고 그자리 Grok 4.1 Fast 도입 여부 판단"
- **"최종 판정 2단계는 삭제..1단계로 제미니 최종 판정으로 간다"**

## 왜 — 실측 (2026-09-12, 운영 컨테이너)

같은 질문 3개(어제 2차 검증관이 실제로 낸 것)를 각 채널에 던졌다.

| 채널 | 시간 | 비용/경기 | 정답 |
|---|---|---|---|
| Anthropic sonnet-5 + `web_search` **(날짜 게이트 O)** | 12초 | **$0.102** | **3/3** |
| Anthropic sonnet-5 + `web_search` (게이트 X) | 12초 | $0.098 | 1.5/3 |
| `grok-4.3` + `web_search` | 13초 | $0.495 | 0/3 (전부 "모름") |
| `grok-4.20-0309-non-reasoning` + `web_search` | 6초 | $1.082 | 1.5/3 |
| `x_search` (종전) | — | $0.413/콜 × 2~4콜 | 본문 수율 0 |

**Grok 4.1 Fast 는 도입하지 않는다 — 우리 키의 모델 목록에 없다(은퇴).**
현세대(`grok-4.3`·`grok-4.5`·`grok-4.6`·`grok-4.20-*`)로 대체해도 5~10배
비싸면서 더 낫지 않다. 게다가 `grok-4.20` 은 "2026-09-10 이후 기사만"이라는
지시를 받고도 **9월 8일 기사를 근거일자로 적었고**, 기사가 아니라 "성격이
강함"이라는 **추론으로 답을 채웠다**.

### 날짜 게이트가 결정적이었다 — 구자욱 건

| 출처 | 답 |
|---|---|
| Anthropic (게이트 X) | "좌측 가슴뼈 미세골절" ← **2026년 4월** 부상. 5개월 지난 기사 |
| grok-4.20 (게이트 O) | "컨디션 관리·휴식" ← 오답 |
| **정답** | **2026-09-12 훈련 중 등 담 증세로 긴급 제외** · 김헌곤 9번 좌익수 |
| Anthropic (게이트 O) | 위와 **일치**. 라인업 변경까지 [근거일자 2026-09-12] |

인용까지 붙은 확신 있는 오답은 "수집 실패"보다 나쁘다.
→ `[근거일자]` 는 **코드가 검사**한다. 프롬프트만으로 부족하다는 것을
   grok 이 방금 실증했다.

---

## ① 이 함수/상태를 읽는 곳 **전부**

원본 grep: [`SRCH-1.grep.txt`](SRCH-1.grep.txt)

**x_search**
| 파일 | 줄 | 무엇 |
|---|---|---|
| `app/collectors/xsearch.py` | 전체(262) | 모듈 |
| `app/pipeline.py` | 2604·2612·2631–2643·2686–2688 | `_maybe_xsearch` 와 호출부 |
| `app/engine/gather.py` | 10·91–108 | `_x_news` |
| `app/engine/verify.py` | 97 | `_search` 주석 |
| `app/registry.py` | 116·131–133 | `ScoutSport` 뉴스소스 |
| `app/config.py` | 183–206 | 설정 6개 |
| `app/research/grok.py` | 156–172·181·205·257–259 | `X_ONLY`·`WEB_AND_X`·`_tools` |
| `app/engine/deepsearch.py` | 1098 | **주석뿐** — 문구만 정리 |

**2차 검증**
| 파일 | 줄 | 무엇 |
|---|---|---|
| `app/engine/verify.py` | 전체 | 모듈 |
| `app/engine/matchup.py` | 1021·1029–1030 | `_judge_v3` 의 ⑤ |
| `app/engine/form_card.py` | 302–304 | 카드의 "2차 검증 이견" 줄 |
| `app/config.py` | 449–456 | `verify_enabled`·`verify_model` |
| `app/llm/judge_route.py` | 36 | 주석 |

🔴 **건드리지 않는 것 — 이름이 겹치지만 다른 것이다**
- `app/engine/judge.py:60` `"2차 반박 검증에서 발견된…"` — **구 Judge(축구)**
  스키마 필드다. `verify.py` 와 무관하다.
- `app/research/grok.py` 자체 — `counter_briefing`·`delta_check`·
  `search_with_citations` 가 `pipeline.py`·`deepsearch.py` 에서 따로 쓰인다.
  **X 도구만 뗀다.**

**테스트** — `test_xsearch_path.py`·`test_grok_tools.py`·`test_verify.py` 삭제,
`test_scout_registry.py`·`test_gather.py`·`test_situation.py`·
`test_order_v3.py`·`test_anthropic_final_only.py` 수정.

## ② 만드는/바꾸는 상태

**지우는 상태**
| 상태 | 어디 | 다른 곳이 갱신하나 |
|---|---|---|
| `xsearch:done:*`·`xsearch:items:*`·`xsearch:calls:*` | Redis | 아니다 — `xsearch.py` 전용. TTL 26h 로 스스로 소멸 |
| `SCOUT_XSEARCH_*` 6개 | env | Railway 변수. **삭제 전 운영값 확인 필요** |
| `VERIFY_ENABLED`·`VERIFY_MODEL` | env | 운영에 설정된 적 없다(기본 False) |
| `jg["verify"]`·`order_v3["2차"·"2차사유"·"검색요청"·"검색n"]` | 판정 원장 | `persist_matchup_record` 가 통째로 저장 — 키가 빠져도 읽는 쪽은 `.get` |

🔴 **원장 하위호환**: `form_card.py:302` 가 `ov.get("2차")` 를 읽는다.
   키가 사라지면 `None` → 종전 `elif … in ("검증실패","없음")` 가지에 걸려
   **없던 경고줄이 생긴다.** 그래서 렌더 코드도 같이 지운다. 이미 저장된
   과거 원장에 `"2차"` 가 남아 있어도 **읽지 않으면 그만**이다.

## ③ 리그·종목·경로 분기

**생기지 않는다.** x_search 는 `registry.ScoutSport` 에서 kbo·npb·mlb
**세 종목 모두**에 달려 있었고 셋 다 똑같이 뗀다. 축구는 애초에
`ScoutSport` 에 없다(구 Judge 경로).

⚠️ 단, 지우는 `_maybe_xsearch` 는 **구 경로(ORDER_V3 꺼짐)**에서만 돌던
   코드다. 운영은 지금 `order_v3=False` 라 **이 경로가 살아 있다** —
   다만 `scout_xsearch_enabled=False` 라 무조건 조기 반환한다. 즉 동작 변화 0.
   **이 전제를 배포 전에 운영 변수로 확인한다**(②의 "삭제 전 운영값 확인").

## ④ 조용히 실패하는가

| 위험 | 대응 |
|---|---|
| `gather._x_news` 를 지웠는데 `collect` 가 계속 부른다 | ORD-21 에서 이미 `jobs` 에서 뺐다. **계약 테스트로 못 박는다** — `collect` 의 jobs 키 집합을 단언 |
| `_judge_v3` 가 `verify` 를 임포트한 채 남는다 | 모듈이 없으면 `ImportError` 로 **판정 전체가 죽는다** → 조용하지 않다. 다만 `_drop` 이 사유를 남기도록 임포트를 함수 최상단에 유지 |
| 카드에서 "2차" 줄만 사라지고 아무도 모른다 | 카드 렌더 계약 테스트가 `2차` 문자열 부재를 단언 |
| env 를 안 지워 Railway 에 유령 변수가 남는다 | **코드에서 지우면 pydantic 이 무시한다** — 해는 없으나 배포 후 `railway variables` 로 정리 확인 |

🔴 **가장 큰 위험: ⑤를 지우면 검색 요청자가 사라진다.**
   2차 검증관이 `판단불가` 일 때만 검색을 돌렸다. 그게 없어지면
   (가) 검색을 아예 안 하거나 (나) 무조건 검색해 경기당 $0.10 이 고정된다.
   → **SRCH-3 에서 ②선별(triage)로 요청자를 옮긴다.** `triage.run` 은 이미
     `없는것` 을 반환한다(`triage.py:119`). 새 개념을 만들지 않는다.
   ⚠️ SRCH-1 만 배포한 상태에서는 **검색이 0** 이다. 이것은 의도된 중간
     상태이며, SRCH-2·3 전까지 켜지 않는다.

## ⑤ 이미 있는 사실을 다시 적는가

- 모델 목록·단가를 문서에 베끼지 않는다. 위 표는 **실측 로그**이고
  날짜가 박혀 있다(사본이 아니라 관측 기록).
- `ScoutSport` 뉴스소스는 `registry.py` 가 원본 — 거기서만 지운다.
- 검색 채널 스위치는 `config.py` 가 원본. 카드·프롬프트에 이름을 복사하지 않는다.
