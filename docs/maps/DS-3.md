# DS-3 — 기사 검색을 robots 허용 경로로 (영향 지도 5문)

사용자 지시 2026-09-21: "3번해라" (배선 3순위 · "체인은 bing으로")

## ① 🔴 지금 기사 공급이 **100% robots 거부 경로**다 — 실측

```
운영 캐시의 기사 URL   174건 · 도메인 **1종** = news.google.com
```
`news.google.com/robots.txt`: `*` 에 `Disallow: /`, `/rss/` 를 여는 Allow 줄이
없고, `ClaudeBot`·`anthropic-ai`·`GPTBot`·`PerplexityBot` 을 **이름으로 지목**해
전면 거부한다(원문 직접 수신).
같은 파일에서 `search.daum.net` 도 거부다(`satellite.py:270` `_daum_fetch`).

🔴 **배선은 선택이 아니라 강제다.** 다만 대체가 없으면 기사가 0 이 되므로
   대체를 먼저 실측했다.

## ② 대체가 **더 낫다** — 실측

Bing News RSS 는 `<News:Source>`(매체 이름)를 주고, apiclick 링크의
**`url=` 파라미터에 원문 URL 이 그대로** 들어 있다:
```
link → …apiclick.aspx?…&url=https%3a%2f%2fwww.osen.co.kr%2farticle%2fG1112879088
도메인 분포(12건): osen.co.kr · yna.co.kr · mt.co.kr · fnnews.com ·
                   newspim.com · sportsworldi.com · ajunews.com · msn.com×4
```
⚠️ **내가 앞서 "원문 URL 은 1회 추가 요청이 든다"고 적은 것은 틀렸다.** 요청 0 이다.
⚠️ 12건 중 4건이 `msn.com` 으로 감싸여 온다. 그때 `News:Source` 가
   `노컷뉴스 on MSN` 처럼 매체 이름을 준다 — 버리지 않는다.

## ③ 어디를 건드리나

| 파일 | 무엇 |
|---|---|
| `app/deepsearch/search.py` | `real_url()` · `parse_rss` 가 `News:Source`·원문 URL |
| `app/collectors/satellite.py` | `rss_hits` 의 **가져오는 층만** 교체 |

**출력 모양은 안 바꾼다** — `{url,title,snippet,source,source_url,published}`.
`_tor_supplement`·`scout_config.screen` 이 그 모양을 본다.
`published` 는 **datetime** 이다(`screen` 이 타입으로 RSS 를 가른다 · SCT-6).

⚠️ `_daum_fetch`(다음 검색)는 **이번에 안 건드린다.** 같은 함수를 축구 위성도
   쓰고(`satellite_soccer.py:538`) 파서가 다르다. 한 번에 둘을 바꾸면 무엇이
   깨졌는지 못 가린다 — 별 단위로 남긴다(**D40**).

## ④ 사본이 생기나

- 요청: DS-1 런타임(robots·간격·상한·서킷).
- 공급자·순서: `config/deepsearch.yaml` 의 `search.chain`.
- 신선도·등급: `scout_config.MAX_AGE_H`·`rank` 그대로.
- `news_rss.parse_feed` 는 **구글 RSS 전용 파서**라 안 쓴다.
  계약이 `rss_hits` 본문에 `news_rss` 가 없음을 확인한다.

## ⑤ 되돌릴 수 있나

⚠️ **config 스위치를 두지 않았다.** 되돌릴 자리가 `news.google.com` 인데
   그곳은 **robots 거부**다 — 되돌리면 안 되는 변경이다.
   되돌리려면 커밋을 되돌려야 하고, 그것이 맞다.

## ⑥ 함께 눈에 띈 것 (등록만)

⚠️ KBO 소스 등급표가 사실상 비어 있다 — `sources.yaml` 의 `tier1_club_local.kbo`
   는 `gukjenews.com` 하나, `tier2_aggregator.kbo` 는 **빈 목록**이다.
   그래서 `osen.co.kr`·`yna.co.kr` 이 전부 `RANK_UNKNOWN(9)` 이다.
   오디션의 "화이트리스트 0%" 가 이것이었다. → **D41** 로 등록만.
