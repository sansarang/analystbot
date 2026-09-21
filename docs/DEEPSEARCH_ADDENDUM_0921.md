# deepsearch_addendum_0921 — 최신 도구 도입 (지시문 원문 보관)

🔴 **사용자 지시문 원문이다. 요약하지 않는다.** 다음 세션이 이것을 읽는다.
착수 순서: DS-1(런타임) → **DS-2a 는 DS-2 와 함께** · DS-3a 는 DS-3 과 함께 ·
DS-5a 는 DS-5 와 함께 · **DS-4a 의 비교는 DS-4 착수 전에.**

규율(본문 그대로): 추측 금지 · 원문 증빙 · 사본 금지(값은 `config/deepsearch.yaml`) ·
1단계 1커밋 · 슬레이트 창 배포 금지 · 발송 OFF ·
**차단 우회 금지**(프록시 회전·UA 위장·Tor·로그인/유료 벽 통과·안티봇 회피 금지.
robots 거부·403·429 는 "불가"로 기록).
⚠️ 지시문의 숫자는 전부 **미검증 사전값**이다.

---

## DS-2a — 직독기를 "변경 감지" 방식으로 (비용 0 · 가장 먼저)

목적: 공시·중지 공지·경기 페이지처럼 **정해진 페이지가 바뀐 순간**을 분 단위로
잡는다(09-21: 중지 08:30 · 등록 공시 11:06 · 우천 중지 12:40경을 늦게 알았다).

1. `app/deepsearch/watch.py` — source_map 의 `watch: true` 행을 주기적으로 읽어
   **정규화 본문 해시**를 Redis 에 저장하고, 해시가 바뀐 때만 파서를 돌린다.
   정규화 = 광고·타임스탬프·조회수 등 잡음 영역을 source_map 의
   `ignore_selectors` 로 제거한 뒤 해시. 잡음 때문에 매번 바뀌는 페이지는
   watch 대상에서 빼고 사유 기록.
2. 주기(값은 config): 공시·중지 공지 `10분`(06:00~경기 시작) · 경기 페이지
   `T-180 이전 30분 / T-180~T-65 10분 / T-65~T-20 5분 / T-20~시작 3분` ·
   그 외 60분. 조건부 요청(ETag·If-Modified-Since)을 지원하는 서버에는 반드시
   쓴다(304 는 본문 미수신).
3. 바뀌면: 파서 → Fact(`event_date`·`as_of` 필수) → DS-6 검증 → 카드.
   상태 사실(개최·중지·지연)은 `as_of` 와 함께 저장하고 30분 지나면 stale.
4. 변화 이벤트를 `watch_events(url, changed_at, kind, parsed_ok)` 에 기록.
   "공지 게시 → 봇 인지"까지의 지연(분)을 능력치로 /health 에 싣는다.
5. 예절: 도메인당 동시 1 · 최소 간격 2초 · 도메인 일일 상한.
   서킷 브레이커가 열리면 watch 도 멈춘다.

**완료 조건**: 09-21 NPB 페이지 조각 3장(예정→중지, 공시 추가, 스타멘 출현)으로
변화 감지가 재현되는 로그 · 하루 실측에서 인지 지연(분) 표.

## DS-3a — 검색 경로를 "갈아 끼우는 구조"로 + 공급자 오디션

목적: 검색 품질은 우리가 만들지 말고 비교해서 고른다. **도입 결정은 사용자**가 한다.

1. 인터페이스 `SearchProvider.search(query, lang, since_hours, max_results) -> list[Hit]`,
   `Hit={url,title,snippet,published_at?,content?}`.
   구현체: `rss_google`(현재·기본) · `brave` · `firecrawl` · `parallel` · `tavily`
   — 키가 없으면 자동 비활성. 공급자 이름을 코드에 박지 않고
   `deepsearch.search.chain` 설정으로만.
   공급자가 본문(content)을 같이 주면 L3 수집을 생략할 수 있게 하되,
   **DS-6 검증(날짜·인용·시점·경기 후 기사)은 똑같이 적용**한다.
2. 예산: 공급자별 `daily_query_cap`·`monthly_budget_usd`(사전값 0 = 무료 티어만).
   상한 도달 시 다음 공급자 → 마지막은 rss_google. 비용·건수를 /health 에.
3. 오디션 도구 `tools/search_audition.py`(판정·배포 경로와 분리):
   입력 = 09-20·09-21 의 실제 질문 세트(야구·축구, ko/ja/en + 현지어) × 공급자.
   같은 시각 조건을 맞추기 위해 **오늘 이후 새 슬레이트에서 경기 전 시점에**
   돌린다(과거 경기로 돌리면 경기 후 기사가 섞인다).
   지표(코드 채점): 당일(≤24h) 기사 회수 수 · 화이트리스트 도메인 비율 ·
   DS-6 검증 통과 사실 수 · 폐기 사유 분포 · 중앙 응답 ms · 건당 비용 ·
   한/일 기사 비율.
   출력 `docs/SEARCH_AUDITION_<날짜>.md`. 3일 이상 돌린 표를 본 뒤 사용자가
   하나를 고른다. **자동 채택 금지.**
4. 의미(임베딩) 검색 계열은 속보에 약할 수 있으므로 오디션에서
   **당일 기사 회수율**을 1순위 지표로 본다.

**완료 조건**: 인터페이스·rss_google 구현체·키 없는 상태 완주 테스트 통과 ·
오디션 도구가 rss 단독으로 표를 낸다(유료 키는 사용자가 넣은 것만 사용).

## DS-4a — 수집기 구현 선택지 (직접 짜기 전에 비교)

1. 정적·JS 페이지 본문 확보를 직접 구현하기 전에, **자체 호스팅 오픈소스
   크롤러(Crawl4AI 계열)** 를 crawler 서비스에 올리는 안을 실측 비교한다:
   설치 크기·메모리 피크·페이지당 ms·본문 추출 품질(실측 HTML 10장)·비동기
   동시성 제어가 DS-1 런타임 한도와 함께 동작하는지.
   결과가 직접 구현보다 나으면 채택하되, **요청은 반드시 DS-1 런타임의
   세마포어·서킷 브레이커·robots 검사를 거친다**(도구가 제 멋대로 요청하지
   못하게 어댑터로 감싼다).
2. 브라우저 자동화(Playwright 기반 에이전트류)는 `source_map.fetch=js` 이고
   `headless_allowed:true` 인 공개 페이지에서 **탭 클릭·스크롤로 값이 나오는
   경우**에만. 로그인·결제·캡차·접근 통제 통과에 쓰지 않는다. LLM 이 브라우저를
   조종하는 방식은 비용·재현성 때문에 기본 금지, **스크립트된 동작만**.
3. 외부 "URL→마크다운" 변환 서비스는 제3자에게 URL 을 넘기는 것이므로 기본
   미사용. 쓰려면 사용자 승인.

**완료 조건**: 비교표 1장과 채택 결정 제안(채택은 사용자 승인).

## DS-5a — 재순위(rerank)로 LLM 입력 줄이기

목적: 기사 14건을 통째로 넣어 추출 0건이 나오는 대신, 질문과 실제로 관련된
문단만 추려 넣는다.

1. 단계: 기사 → 문단 분할 → (a) 키워드 사전 적중 점수 (b) 선수·팀·감독 이름
   적중 (c) 선택: 소형 재순위 모델 점수 → 질문별 상위 `k=6` 문단만 LLM 에.
2. (c)는 기본 꺼짐. 켤 경우 로컬에서 도는 소형 다국어 재순위 모델만(외부 API
   금지). crawler 메모리 영향 실측 후 사용자 승인. **(a)(b)만으로도 동작해야 한다.**
3. 문단마다 `article_idx·para_idx` 를 붙여 LLM 의 인용이 어느 문단에서 왔는지
   코드가 검증한다.
4. 계측: 질문당 LLM 입력 토큰(전/후) · 인용 검증 통과율(전/후) ·
   추출 0건 경기 비율(전/후).

**완료 조건**: 09-20 K리그 2경기에서 전/후 표(토큰·통과율·추출 건수).

---

## T-ADD — 추가 테스트 (`tests/deepsearch/test_addendum.py`)

**변경 감지**

1. `test_watch_detects_change_only` — 본문 동일·타임스탬프만 다른 두 응답 →
   변화 없음 / 중지 문구가 생긴 응답 → 변화 1회·파서 1회.
2. `test_watch_uses_conditional_request` — ETag 있는 서버에 두 번째 요청은
   If-None-Match, 304 면 파서 0회.
3. `test_watch_interval_by_phase` — 가짜 시계로 T-180/T-65/T-20 경계에서 주기가 바뀐다.
4. `test_status_fact_has_as_of_and_goes_stale` — 상태 사실은 as_of 필수,
   30분 뒤 stale, 최신 사실이 이전 사실을 이긴다
   (픽스처: 11:50 "예정대로 개장" 기사 → 이후 "試合中止 降雨のため" 페이지).
5. `test_notice_lag_metric` — watch_events 로 인지 지연(분)이 계산된다.
6. `test_noisy_page_excluded` — ignore_selectors 로도 매번 바뀌는 페이지는
   watch 대상에서 제외되고 사유가 기록된다.

**검색 공급자**

7. `test_provider_chain_from_config_only` — 코드에 공급자 이름 하드코딩 없음(rg) ·
   키 없는 공급자는 비활성.
8. `test_provider_cap_falls_through` — 일일 상한 도달 → 다음 공급자 → rss_google.
   예외 없음.
9. `test_provider_content_still_verified` — 공급자가 준 본문에도 날짜·인용·
   post_match 검증이 적용된다(9/11 공지 오독 픽스처 재사용).
10. `test_audition_outputs_table_without_paid_keys` — 유료 키 없이도 rss 단독 표가 나온다.
11. `test_budget_zero_means_free_only` — monthly_budget_usd=0 이면 과금 가능한 호출 0.

**수집·브라우저**

12. `test_third_party_crawler_goes_through_runtime` — 어댑터를 거치지 않은 직접
    요청 경로가 없다(세마포어·robots·서킷 적용 확인).
13. `test_browser_automation_scripted_only` — LLM 조종 경로 없음 ·
    로그인/캡차 처리 코드 없음(rg).
14. `test_no_bypass_artifacts` — 프록시 회전·UA 위장 목록·Tor/SOCKS 설정·
    쿠키 주입 경로가 코드·설정에 없다(rg).

**재순위**

15. `test_rerank_works_without_model` — (c) 꺼진 상태에서 (a)(b)만으로 상위 k 선별.
16. `test_rerank_reduces_tokens` — 픽스처 기사 14건에서 LLM 입력 토큰이 기준
    대비 감소, 정답 문단이 상위 k 안에 있다(무고사 출전·대전 로테이션 문단).
17. `test_quote_maps_to_paragraph` — LLM 인용이 article_idx·para_idx 문단에 실제로 존재.

## 보고 형식

각 단계 보고 = T-ADD 해당 항목 통과 증빙 + 실측 표 + pytest 마지막 20줄 +
발송 0건. **유료 공급자·재순위 모델·외부 변환 서비스의 채택은 전부 사용자 승인
사항이다.**

---

# 🔴 착수 전에 갈린 것 — 지시 없이 고르지 않는다 (실측 2026-09-21 13:59)

## 충돌 1 — `T-ADD 14` 는 **지금 코드에서 실패한다**

지시문은 "프록시 회전·UA 위장 목록·**Tor/SOCKS 설정**·쿠키 주입 경로가 코드·
설정에 **없다**"를 잠그라고 한다. 그런데 **이미 있다**:

```
app/collectors/tor_search.py            ← Tor 경로가 존재한다
  + 배선: app/config.py · app/collectors/satellite.py ·
          app/collectors/satellite_soccer.py · app/engine/scout_config.py
UA 위장 22개 파일 (`Mozilla/5.0 …Chrome/128…`)   ← D34
```

🔴 **그리고 실제로 돌고 있다.** DS-0 계측(NPB 3경기 직렬 1회, 09-21 12:45):
`check.torproject.org 6회 · lite.duckduckgo.com 6회`.

⚠️ 이것은 "테스트를 나중에 맞추면 되는" 문제가 아니다. 지시문이 금지한 것이
**운영 경로에 배선돼 있다**는 뜻이다. 갈림길:

| 갈래 | 뜻 | 대가 |
|---|---|---|
| (가) Tor·UA 위장을 **걷어낸다** | 지시문 규율대로 | 403 이 늘 수 있다. `tor_search` 실적은 "보강 검색(성과 0)"이라 손실은 작아 보인다 — **실측 필요** |
| (나) `T-ADD 14` 를 **현실에 맞춰 좁힌다** | 기존 경로 유지 | 규율이 문서에만 남는다 |

**지시를 기다린다. 고르지 않았다.**

## 충돌 2 — 체인의 **최후 폴백이 robots 거부 경로**다

DS-3a 는 "상한 도달 시 다음 공급자 → **마지막은 rss_google**" 이라고 한다.
그런데 [3] 감사(커밋 `1303164`)에서:

```
news.google.com  /rss/search   🔴 거부
  robots: Disallow: /  ·  Allow: /$  /?  /home$  /topics/ …
  (`/rss/search` 를 여는 Allow 줄이 없다)
```

🔴 **최후 폴백이 거부 경로면 체인 전체가 성립하지 않는다.** 유료 공급자 상한이
0 인 사전값에서는 **모든 검색이 거부 경로로 떨어진다.**

⚠️ 함께 걸린 것: `search.daum.net/search`(satellite.py:270) 도 거부다.
   허용으로 확인된 검색 경로는 `lite.duckduckgo.com` 하나인데, 그것은 지금
   **Tor 를 거쳐** 불린다(충돌 1).

**지시를 기다린다.** 이 둘이 정해져야 DS-3a 의 "마지막"을 적을 수 있다.

## 새로 필요한 것 (지시문이 승인한 범위 — 착수는 순서대로)

| 무엇 | 어디 | 지금 |
|---|---|---|
| `watch_events` 테이블 | 신규 | 없음 |
| `source_map` 칸 `watch`·`ignore_selectors`·`headless_allowed` | `config/source_map.yaml` | 없음 |
| `config/deepsearch.yaml` | 신규 | **없음** — DS-1 이 만든다 |
| `app/deepsearch/runtime.py` | DS-1 | 없음 |
