# SCT-7 — Google News RSS 를 검색 1순위 통로로 (사용자 지시)

## 왜

축구 검색 통로가 DDG(토르) 하나였고, 그것이 **403 으로 막힌다**(실측
2026-09-14: 경기당 2질의에도 `DDG 403 — 보강 없음`). 그래서 현지 매체가 한
건도 안 열렸고 추출 JSON 이 빈 칸으로 남았다.

RSS 는 무료·속도 제한이 없고 **`pubDate` 를 싣는다** — 날짜 문을 대신할
증거가 붙어 온다. 사용자 지시: RSS 1순위, DDG/토르는 RSS 0건일 때만 폴백.

재현:
```
PYTHONPATH=. .venv/bin/python <scratchpad>/repro_sct7.py
  → AttributeError: module 'app.collectors.satellite' has no attribute 'rss_hits'
```

## ① 이 함수/상태를 읽는 곳 **전부**

```
$ grep -rn "news_rss\|rss_hits\|rss_supplement" app/
app/collectors/news_rss.py      BASE · UA · TIMEOUT · parse_feed · LOCALE(야구 3종목)
app/pipeline.py:2683            by_side·merge_into_research (리서치 병합 — 손대지 않는다)
app/collectors/grounding.py:104 qualified·dedupe_by_title
app/collectors/satellite*.py    **부르는 곳 0** ← 이 배선이 최초
```
새 함수 둘(`rss_hits`·`rss_supplement`)의 호출부는 `gather_soccer` 하나다.

## ② 만드는/바꾸는 상태

**없다.** DB·Redis·env 를 만들지 않는다. 추가되는 것은 설정 한 블록이다:
| 무엇 | 성격 |
|---|---|
| `config/search_terms.yaml` `locales:` | 리그 → `{hl, gl}`. **`ceid` 는 안 적는다** — `{gl}:{hl 앞 2자}` 로 코드가 만든다 |

🔴 로케일은 **새로 정하는 값이 아니다.** 같은 파일의 `terms` 가 이미 그
언어로 쓰여 있다(세리에A = 이탈리아어 → it/IT). 덴마크만 `terms` 가 영어라
로케일도 en/DK 다 — 덴마크어를 지어내지 않는다.

## ③ 리그·종목·경로 분기가 생기는가

- 로케일 표에 없는 리그는 `locale()` 이 `None` → **RSS 를 부르지 않는다**
  (조용히 빈손이 아니라, 부르지 않는 것이 명시적이다).
- 야구는 이 경로를 타지 않는다(`gather_soccer` 안에서만 부른다). 야구 RSS 는
  종전대로 `news_rss.LOCALE` 로 파이프라인이 쓴다 — 두 표가 **다른 경로**를
  담당하며 서로 덮지 않는다.
- 토르는 이제 **RSS 0건일 때만** 돈다.

## ④ 실패하면 "시끄럽게" 실패하는가

- RSS 조회 실패는 `[rss] {리그} 조회 실패` 로 남고 빈 목록을 준다 → 토르 폴백.
- 선별 결과는 `[rss] {away}@{home} +N건 · 폐기 M건` 한 줄.
- RSS 가 열렸으면 `토르 보강 생략` 을 로그가 말한다 — 왜 토르가 안 돌았는지
  나중에 묻지 않게.

## ⑤ 시스템에 이미 있는 사실을 다시 적고 있지 않은가

- **BASE·UA·TIMEOUT·파서를 베끼지 않는다** — `news_rss` 에서 임포트한다.
  계약이 AST 로 "문자열 상수에 URL 이 없다 + 그 셋을 임포트한다"를 잠근다.
- 선별도 새로 만들지 않는다 — 토르와 **같은 `rank_and_pick`** 을 태운다.
- 신선도 상한도 `MAX_AGE_H[stage]` 를 그대로 `parse_feed` 에 넘긴다.

## ⚠️ 규칙 하나를 정리했다 — 보고

RSS 결과가 **날짜 문에서 전량 폐기**됐다(실측: 1시간 전 발행된
"Torino, formazioni ufficiali"). `pubDate` 로 발행 시각을 정확히 아는데
제목에 "oggi" 가 없다고 버리는 것은 **같은 사실을 두 번 재는 것**이고, 둘째
검사는 증거값이 없다. 그래서 `screen()` 에서 **pubDate 가 신선도를 통과하면
그것이 곧 날짜 증거**로 본다. 날짜 문은 원래 pubDate 가 **없을 때** 그 자리를
대신하려던 규칙이다. 지난 연도가 제목에 명시된 글은 그 앞에서 이미 걸러진다.
