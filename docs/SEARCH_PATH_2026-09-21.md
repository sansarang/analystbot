# 충돌 2 딥서치 — 검색 체인의 최후 폴백이 robots 거부 경로다

사용자 지시 2026-09-21: "충돌2는 딥서치해서 찾아라"
실측 14:16~14:22 KST · UA `AnalystBot/1.0 (+research; respects robots)`

## 1. 먼저 — 거부가 맞다. 그리고 **우리를 이름으로 지목한다**

`news.google.com/robots.txt` 원문(직접 받음):

```
User-agent: *
  Disallow: /
  Allow: /$  /?  /home$  /home?  /home/  /nwshp$  /topics/
        /publications/  /stories/  /swg/  /about$  /about?  /about/
      ← `/rss/` 를 여는 줄이 **없다**

User-agent: CCBot | GPTBot | ChatGPT-User | PerplexityBot |
            anthropic-ai | ClaudeBot | Claude-Web
  Disallow: /            ← 이름으로 지목한 전면 거부
```

🔴 `/rss/search` 는 `*` 화이트리스트에 없다. [3] 감사 판정이 맞았다.
⚠️ 검색으로 확인한 일반론: robots 위반이 곧 불법은 아니지만 **구글 ToS 는
   자동 접근을 명시적으로 금지**한다. 우리 규율은 "차단을 우회하지 않는다"이므로
   합법 여부와 무관하게 **쓰지 않는다**.

## 2. 대체 후보 — 전부 **실제로 쳐서** 확인했다

| 후보 | robots | 실측 | 판정 |
|---|---|---|---|
| **Bing News RSS** `bing.com/news/search?…&format=RSS` | 🟢 **허용** — `Disallow: /search`·`/Search` 는 있으나 `/news/…` 를 막는 줄이 없다 | ko 11항목 2.3s · ja 11항목 | 🥇 **1순위** |
| 매체 자체 RSS (동아·한경·연합뉴스TV) | 🟢 허용 | 50 · 50 · 11항목, 전부 200 | 🥈 보조 |
| GDELT DOC 2.0 | 공개 API(키 불필요) · robots 404 | 🔴 **5초에 1회 제한** · `プロ野球` 질의에 기사 2건이고 둘 다 무관(게, MLB 경기) | 🥉 쓰기 어렵다 |
| `search.daum.net` | 🔴 거부 | — | 불가 |
| `lite.duckduckgo.com` | 🟢 허용 | — | 가능하나 지금 **Tor 경유**다 |

## 3. 🔴 Bing RSS 가 **우리가 못 찾던 것을 준다**

09-21 NPB 작업에서 몇 시간을 쓰고도 못 찾은 것이 **확정 스타멘**이었다.
같은 질의를 Bing News RSS 에 던지자 **경기 전날 밤 기사로 이미 있었다**:

```
ja-JP · 2026-09-20 22:19
  【中日21日スタメン】1番福永＆2番村松 クリーンナップは細川 サノ…
ja-JP · 2026-09-20 17:00
  【中日】高橋宏斗、本拠地最終戦に先発…再昇格後は抜群の安定感
ko-KR · 2026-09-20 02:03
  한화 7연패 당해도 웃는다…김서현 155km 슬럼프 완벽 탈출…
```

🔴 **스타멘도 예고선발도 기사에 있었다.** 우리가 못 본 이유는 자료가 없어서가
아니라 **검색 경로가 막혀 있어서**다. 이것이 이 딥서치의 값어치다.

## 3-B. 🔴 축구도 된다 — 리그·언어별 실측 (사용자 지시: "축구도 필히")

사용자 지시 2026-09-21: "내가 준 지시문은 야구에 국한되는 게 아니라 축구 야구라는
거를 명심하고 딥서치도 축구에 필히 적용되어야 한다"

Bing News RSS · 각 리그 현지어 · 실측 14:28~14:31 KST:

| 리그 | 시장 | 항목 | 최근2일 | 나온 것 |
|---|---|---|---|---|
| EPL | `en-GB` | 9 | **3** | `Arsenal XI vs Brighton: Confirmed team news` — **확정 XI** |
| 라리가 | `es-ES` | 12 | **3** | `Alineación confirmada del Real Madrid` — **확정 라인업** |
| 분데스 | `de-DE` | 7 | 0 | `Bundesliga Aufstellungen heute: Alle Startelf-` |
| J리그 | `ja-JP` | 8 | 0 | 방송예정·미리보기 (9/19 경기 뒤라 최신이 없다) |
| K리그 | `ko-KR` | 3 | 0 | 🔴 **가장 약했다** |

🔴 **현지어가 결정적이다.** 라리가를 영어로 물으면 안 되고 `alineación` 으로
   물어야 확정 라인업이 나온다. 지시문 DS-3a 의 "ko/ja/en + **현지어**"가
   실측으로 뒷받침된다.

## 3-C. 🔴 K리그가 약한 이유 — 절제 실험으로 갈랐다

"커버리지가 없다"고 결론내기 전에 **질의어만 바꿔** 다시 쟀다:

```
"K리그 포항 스틸러스 선발 라인업"   항목  3 · 최근3일 0     ← 길수록 나쁘다
"포항 스틸러스"                   항목 12 · 최근3일 2
"K리그1 선발 명단"                항목  8 · 최근3일 1
"K리그1"                          항목  8 · 최근3일 5     ← 가장 좋다
"대전 하나시티즌"                  항목 10 · 최근3일 2
```

돌아온 제목:
```
[K리그1 라인업] 박규현 선발-문건호 벤치 포함...대전, 달라진 명단 속 포항전서 홈…
'가시와전 베스트11 그대로' 전북, 광주전 명단 발표...'이승우-티아고-이동준' 삼각…
포항스틸러스, FC서울 2-1 격파…6위와 승점 같은 7위 도약
```

🔴 **원인은 커버리지가 아니라 질의어다.** K리그 라인업 기사는 있다.
   **검색어가 길수록 회수가 급격히 나빠진다**(6단어 3항목 → 1단어 12항목).

⚠️ 이 실측이 DS-3a 오디션의 설계를 바꾼다 — 공급자만 비교하면 안 되고
   **질의어 길이**를 함께 재야 한다. 지금 `satellite.py`·`news_rss.py` 가
   만드는 검색어가 몇 단어인지는 **아직 안 쟀다.**
⚠️ 규율 "LLM 에게 검색어 생성을 시키지 않는다"는 그대로다. 검색어는 코드가
   만들고, 그 규칙이 **짧아야 한다**는 근거가 이것이다.

## 4. 남는 흠 — 숨기지 않는다

1. 🔴 **링크가 원문이 아니다.** `bing.com/news/apiclick.aspx?ref=FexRss&…` 리다이렉트다.
   원문 URL 을 얻으려면 **1회 추가 요청**이 든다(도메인 화이트리스트·인용
   검증이 원문 URL 을 요구한다). XML 이스케이프(`&amp;`)를 먼저 풀어야 한다 —
   그대로 치면 200 이지만 `redirect_url` 이 비어 돌아온다(실측).
2. ⚠️ **오래된 기사가 섞인다.** ko 결과에 `2026-03-24` 가 한 건 있었다.
   DS-6 의 날짜 일치 검사가 **반드시** 걸려야 한다 — 이건 이미 있는 장치다.
3. ⚠️ **Bing ToS 를 아직 안 읽었다.** robots 만 봤다. RSS 는 제공되는 형식이지만
   검색 결과 자동 수집에 대한 조항은 별개다. 확인할 URL:
   `bing.com/new/termsofuse` · `microsoft.com/servicesagreement`
4. ⚠️ 매체 자체 RSS 는 **검색이 아니다** — 최신 목록이라 "이 경기·이 선수"로
   물을 수 없다. 코드가 걸러야 하고, 그러면 회수율이 질의 기반보다 낮다.

## 5. 제안 (채택은 사용자 결정 — 자동 채택 금지)

DS-3a 의 체인을 이렇게 적는다:

```
deepsearch.search.chain:  [bing_news_rss, media_rss]       ← 둘 다 robots 허용
  # rss_google 은 **뺀다** — 최후 폴백이 거부 경로면 체인이 성립하지 않는다
  # brave·tavily·firecrawl·parallel 은 키가 있을 때만(사용자가 넣은 것만)
```

⚠️ 지시문은 "마지막은 rss_google" 이라고 적혀 있다. **그 줄을 바꾸는 것은
   사용자 결정이므로 지시 없이 구현하지 않는다.** 위는 제안이다.
⚠️ 오디션(DS-3a 3)에서 `bing_news_rss` 대 `media_rss` 를 실제로 채점한 뒤
   순서를 정하는 것이 지시문의 뜻에 맞다.

## 출처

- https://news.google.com/robots.txt (직접 수신 2026-09-21 14:16)
- https://www.bing.com/robots.txt (직접 수신 2026-09-21 14:18)
- https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/
- https://support.google.com/webmasters/thread/241371846
- https://bytetunnels.com/posts/is-robots-txt-legally-binding-scraping-law-explained/
