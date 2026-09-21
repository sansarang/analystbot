# DS-5 — 재순위를 추출 경로에 잇는다 (영향 지도 5문)

사용자 지시 2026-09-21: "순서대로 해" (배선 2순위 — 소스를 안 바꿔 가장 안전)

## ① 배선 전에 **먼저 쟀다** — 운영 11경기

```
경기                              기사   창(전)   재순위(후)  문단
Yokohama DeNA@Hanshin Tigers      13    6,000     2,130     6
Milwaukee@Baltimore               65    6,000       400     6
San Francisco@LA Dodgers          53    6,000       510     6
NY Yankees@Arizona                64    6,000       454     6
Miami@San Diego                   37    4,471       607     6
Minnesota@LA Angels               38    6,000       526     6
Hiroshima@Chunichi                 9    5,400     1,068     6
Fukuoka SoftBank@Tohoku Rakuten    7    4,200       991     6
Real Sociedad@Valencia CF         14    6,000       484     2
Saitama Seibu@Chiba Lotte          6    3,600         0     0  🔴
Orix@Hokkaido Nippon-Ham           6    3,600         0     0  🔴
```

## ② 🔴 0자 두 경기를 들여다봤다 — **재순위가 맞았다**

```
롯데vs세이부 기사 6건  → 「アジア大会 트러블…태국 선수단 식사 '열악'」
니혼햄vs오릭스 기사 6건 → 「阪神의 石井大智 투수…」(다른 팀)
```
**그 경기 이야기가 기사에 없다.** 지금은 그 무관한 3,600자가 통째로 LLM 에
들어간다. → 배선하면 **증거 0 → LLM 호출 안 함**(절대 규칙 6).

## ③ 🔴 현지 별칭이 없으면 NPB 가 통째로 죽는다

DB 는 `Chiba Lotte Marines`, 기사는 `千葉ロッテマリーンズ` 다.
별칭을 넣자 **0자 경기가 4 → 2** 로 줄었다(위 표가 별칭을 넣은 뒤 값이다).
⚠️ 오디션 도구(AUD-1)에서 **똑같은 실수를 했다.** 같은 원본을 쓴다 —
   `news_rss.QUERY_ALIAS` · `scout_config.local_name`.

## ④ 어디를 건드리나

| 파일 | 무엇 |
|---|---|
| `app/collectors/satellite.py` | `_extract_names()` 추가 · `extract_game_facts` 의 블록 조립 |
| `config/deepsearch.yaml` | `rerank.wire_extract` **스위치** |

`_windows`·`WINDOW_BUDGET` 은 **남긴다** — 스위치를 끄면 그 경로로 돌아간다.

## ⑤ 되돌릴 수 있나

🔴 **config 한 줄로 끈다**(`rerank.wire_extract: false`). 배포 없이 되돌아간다.
`source_gate` 와 같은 방식이다. 계약이 끈 상태의 동작을 잠근다.

⚠️ 이 변경은 **LLM 입력을 6,000자 → 400~2,100자로 줄인다.** 되돌릴 수단이
   없으면 안 되는 크기다.

## ⑥ 틀렸을 때 누가 알려주나

계약 5건: 입력이 줄고 정답 문단이 남나(피카츄 빠짐) · **증거 0 이면 호출 0** ·
현지 별칭이 넘어가나(일본어 기사) · 스위치를 끄면 종전 경로 ·
별칭 표를 새로 만들지 않았나.
