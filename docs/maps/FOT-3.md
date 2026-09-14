# FOT-3 — 교차검증 2순위를 Transfermarkt 로 (API-Football 은 호출 0). 사용자 지시

## 왜

FotMob 이 `unavailable` 키를 안 주는 팀이 있다(실측: 로마). 2순위로 쓰려던
API-Football 은 **무료 플랜이 현 시즌을 막는다** — 실측 원문:
```
GET /injuries {league:135, season:2026, date:2026-09-14}
  status 200 · results 0
  errors: {"plan": "Free plans do not have access to this season,
                    try from 2022 to 2024."}
```
사용자 지시: API-Football 은 사슬에서 빼고(키는 두되 **호출 0**), 2순위는
**이미 층1 로 긁고 있는 Transfermarkt 부상표**로 한다.

재현:
```
PYTHONPATH=. .venv/bin/python <scratchpad>/repro_fot3.py
  → 교차검증 함수 없음 · build_analysis 안에 API-Football 호출 있음
```

## ① 이 함수/상태를 읽는 곳 **전부**

```
$ grep -rn "APIFootballClient(" app/
app/pipeline.py:1476   else 분기 — 이미 "Free 플랜은 현재 시즌 미지원"이라 주석에 적혀 있다
   (fetch_fixtures → 항상 빈손 → 아래 football-data/odds 폴백으로 감)
$ grep -rn "_tm_rows\|_tm_injuries" app/
app/collectors/satellite_soccer.py   부상표 수집(층1) — 이미 매 경기 긁는다
```
교차검증은 `_tm_injuries` **안**에서 한다 — 그 함수가 방금 받은 표(`idx`)를
들고 있어 **추가 요청이 0**이고, `fotmob.attach` 가 그보다 먼저 돌아
`jg["fotmob"]` 이 이미 있다(FOT-2 가 정한 순서).

## ② 만드는/바꾸는 상태

| 상태 | 성격 |
|---|---|
| `jg["fotmob"][side]["unavailable"]` | None 이던 자리를 TM 명단으로 채운다 |
| `jg["fotmob"][side]["unavailable_src"]` | `fotmob` \| `transfermarkt` — 출처를 남긴다 |
| `jg["fotmob"][side]["conflict"]` | 두 소스 명단이 다르면 True |
| `jg["fotmob"]["missing"]` | 둘 다 없으면 **그대로 남는다** |

새 테이블·새 컬럼·새 외부 호출 없다. API-Football 호출 한 줄을 **지운다**.

🔴 **규칙(사용자 지시 그대로)**
1. FotMob 에 있으면 **FotMob 이 정본**, TM 은 conflict 검사만.
2. FotMob 이 None 이고 TM 에 그 팀이 있으면 **TM 명단을 out 으로**.
3. 둘 다 없으면 `missing` 유지 — **0 으로 쓰지 않는다.**

## ③ 리그·종목·경로 분기가 생기는가

축구만이다(TM 코드가 `app/leagues.py` 의 `tm_code` 인 리그만 표를 긁는다).
그 코드가 없는 리그는 종전처럼 빈손이고, 그 사실이 로그에 남는다.

## ④ 실패하면 "시끄럽게" 실패하는가

- TM 표에 팀이 없으면 종전 로그가 이미 말한다(`부상표에 없는 팀 … '부상자
  없음'으로 쓰지 않는다`).
- 교차검증 결과를 한 줄로 남긴다 — 어느 소스가 정본이었는지, 충돌인지.
- ⚠️ **빅매치 3순위(구단 공식 RSS)는 이번에 넣지 않는다.** "빅매치 태그"가
  아직 시스템에 없다. 태그가 생기면 그때 붙인다 — 없는 조건으로 코드를
  만들면 영원히 안 도는 가지가 된다.

## ⑤ 시스템에 이미 있는 사실을 다시 적고 있지 않은가

- TM 리그 코드·표 파싱·팀 키 정규화는 전부 기존 함수(`_tm_rows`·`tm_key`)다.
- 결장 명단 저장 자리도 기존 `lineups.scratches` 그대로다.
