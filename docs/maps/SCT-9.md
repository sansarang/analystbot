# SCT-9 — 미상 도메인을 버리지 말고 tier 4 로 (사용자 지시) + 티어 표 확장

## 왜

대진 질의(SCT-8)가 신선한 기사 28건을 가져왔는데 **24건이 '미상'으로
폐기**됐다(실측 2026-09-14). 오늘 실제로 프리뷰를 낸 매체가 표에 없었다:
```
eurosport.it · ilmessaggero.it · romatoday.it · lapresse.it · teleradiostereo.it
dallaplatea.it · diretta.it · calcio.com · calciomercato.com · sportparma.com
```
사용자 지시: 열거한 도메인을 tier1/tier2 에 넣고, **등록 안 된 도메인은
폐기하지 말고 tier 4 로 통과**시킨다(단 `blocked`·`js_only` 는 예외).
상위 3건은 tier 순이라 등록 매체가 있으면 미상은 자연히 밀린다. 그리고
미상으로 fetch 된 도메인과 추출 성공 여부를 **매일 로그로 남겨 승격 후보**로.

## ① 이 함수/상태를 읽는 곳 **전부**

```
$ grep -rn "RANK_UNKNOWN\|rank_and_pick\|blocked(" app/ tests/
app/engine/scout_config.py   rank · blocked · js_only · screen · rank_and_pick
app/collectors/satellite.py  _tor_supplement · rss_supplement · extract_facts
tests/collectors/test_satellite_search.py · test_scout_undated.py
   · test_satellite_search_wiring.py · test_rss_channel.py
```

## ② 만드는/바꾸는 상태

**없다.** 설정 목록과 선별 규칙만 바뀐다.
| 무엇 | 전 | 후 |
|---|---|---|
| `sources.yaml` serie_a | tier1 7 · tier2 4 | tier1 11 · tier2 10 |
| 미상 도메인 | 폐기 | `RANK_UNLISTED`(4) 로 통과 + `unlisted` 표시 |
| 승격 후보 | 없음 | 로그 2줄(선별 시 목록 · 추출 시 성적) |

## ③ 리그·종목·경로 분기가 생기는가

**생기지 않는다.** 규칙은 리그 무관이고, 표만 리그별이다.

## ④ 실패하면 "시끄럽게" 실패하는가

- 🔴 **이 변경이 문을 넓히므로 반대 위험이 커진다.** 그래서 두 줄을 남긴다:
  `[scout] serie_a pre — 미상 N건(후보 [...]) · 그중 fetch [...]`
  `[scout] 승격후보 {도메인} — out N · xi {상태} ({팀})`
  "열어 봤는데 쓸모없었다"와 "열었더니 결장이 나왔다"를 가려야 표를 넓힐지
  판단할 수 있다.

🔴 **이 단위가 잠재 결함 하나를 드러냈다 — 함께 고쳤다.** 미상을 통과시키자
   `tipico.de` 가 열렸다. 원인은 `screen()` 이 차단·js_only 를 **구글 링크**
   (news.google.com)로 검사한 것이다. 매체 도메인(`source_url`)으로 보게
   고쳤다. 종전에는 미상 폐기가 이 구멍을 우연히 덮고 있었다.

## ⑤ 시스템에 이미 있는 사실을 다시 적고 있지 않은가

- 도메인 목록은 `sources.yaml` 한 곳이다. 코드에 적지 않는다.
- 등급 상수도 `RANK_UNLISTED` 하나를 두고 계약이 값을 잠근다.
- 승격 후보 판정도 `rank()` 원본을 다시 부른다 — 별도 목록을 만들지 않는다.
