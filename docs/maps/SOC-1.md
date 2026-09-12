# SOC-1 — 수집 채널을 종목 표로. 축구는 새 행이지 새 분기가 아니다.

사용자 지시 2026-09-12: "코드 꼬이지 않게 분류해서 작업을 할거다"

## 왜

`gather.collect` 의 `jobs` 가 **야구 전용으로 하드코딩**돼 있다:

```python
jobs = {"satellite": _satellite(jg, redis),
        "라인업": _lineup(jg, redis, date),      # 크롤러 선발 예고·타순
        "크롤러": _bullpen(pool, jg)}            # pitcher_appearances
```

축구에는 **선발투수도 불펜도 없다.** 그대로 두고 축구를 끼우면
`if sport == "soccer"` 가 엔진 전체에 번지고, 그때부터 야구를 고칠 때마다
축구가 깨진다(그 반대도).

SAT-S2 로 축구 위성이 111건을 긁는 것을 확인했다. 이제 그것이 v3 수집으로
들어가야 하는데, 지금 `collect` 를 축구로 부르면 **야구 채널 둘이 빈손 호출**된다:
`_lineup` 은 크롤러 스냅샷(야구)을, `_bullpen` 은 `pitcher_appearances`(야구)를
본다. 터지지는 않지만 호출과 시간이 낭비되고, 무엇보다 **"축구도 라인업을
긁는다"는 착시**를 만든다.

## ① 이 함수/상태를 읽는 곳 **전부**

```
$ grep -rn "gather.collect\|from app.engine import gather" app/
app/engine/matchup.py:  col = await gather.collect(jg, redis, date, pool=pool)
   → **유일한 호출부**다(SRCH-3 에서 확인한 그대로)

$ grep -rn "_lineup\|_bullpen\|_satellite" app/ | grep -v gather.py
   (없음 — 전부 gather 안에서만 쓰인다)
```

새로 만드는 `registry.COLLECT_CHANNELS` 를 읽는 곳은 `gather.collect` 하나다.

빌려 쓰는 원본 — 새로 만들지 않는다:
| 무엇 | 원본 |
|---|---|
| 채널 함수 넷 | `gather._satellite` · `_lineup` · `_bullpen` · `enrich` |
| 종목 표가 사는 자리 | `app/registry.py` (`SCOUT_SPORTS`·`ODDS_PROVIDERS` 와 같은 자리) |

## ② 만드는/바꾸는 상태

| 상태 | 성격 | 다른 곳이 다른 규칙으로 갱신하나 |
|---|---|---|
| `registry.COLLECT_CHANNELS` | 새 표 | 아니다 |
| `gather.collect` 의 `jobs` 조립 | 하드코딩 → 표 조회 | 🔴 아래 |

🔴 **`jobs` 의 키가 곧 `출처` 의 키다.** `col["출처"]` 는 `order_v3["수집"]`
   으로 원장에 들어가고 카드·로그가 읽는다. 키 이름이 바뀌면 **과거 원장과
   대조가 깨진다.** → 이름을 그대로 둔다(`satellite`·`라인업`·`크롤러`).
   계약이 야구 세 종목의 튜플을 **문자 그대로** 단언한다.

⚠️ DB·Redis·env 를 건드리지 않는다.

## ③ 리그·종목·경로 분기

**분기를 없애는 것이 이 수정의 목적이다.** 표가 분기를 대신한다.

```
kbo · npb · mlb  → ("satellite", "라인업", "크롤러")   ← 지금 그대로
soccer           → ("satellite",)
표에 없는 종목    → ("satellite",) + 로그
```

⚠️ 축구의 라인업·부상은 **위성이 기사로 가져온다**(SAT-S2 실측: 예상 라인업이
   토르 DDG 기사 제목에 그대로 있다). 별도 채널이 필요해지면 그때 표에
   행을 더한다 — 지금 추측으로 만들지 않는다.

⚠️ `enrich` 는 표 밖이다. 크롤러 스냅샷에서 **비어 있을 때만** 채우고,
   축구는 스냅샷이 없어 아무것도 안 채운다(무해). 계약이 호출 순서를 지킨다.

## ④ 조용히 실패하는가

| 위험 | 대응 |
|---|---|
| 🔴 **야구에서 채널이 빠진다** ← 가장 큰 반대 위험 | 세 종목의 튜플을 문자 그대로 단언 + 실제 호출 집합을 단언 |
| 출처 키 이름이 바뀌어 원장 대조가 깨진다 | 위와 같은 계약이 이름까지 잠근다 |
| 표에 없는 종목이 조용히 0 | 위성만 쓰고 **종목 이름과 함께 로그**. 계약이 단언 |
| 표에 유료 채널이 섞여 수집에서 돈이 나간다 | 표 전수에서 `pplx`·`퍼플렉시티` 부재를 단언 |
| `enrich` 순서가 뒤집혀 선발이 "미정"이 된다 | 첫 호출이 `enrich` 인지 단언(ORD-16 전례) |
| 한 채널이 터져 경기가 빈손 | 기존 `return_exceptions=True` 유지 + 계약 |

⚠️ **아직 못 재는 것**: 축구가 `collect` 로 몇 건을 받는가. SAT-S2 는
   `gather_soccer` 를 직접 불러 111건을 봤는데, `collect` 는 **위성 캐시**를
   읽는다(`_satellite` → `satellite.read_cache`). 캐시가 비어 있으면 0 이다 —
   위성 잡이 먼저 돌아야 한다(`SATELLITE_SPORTS` 에 soccer 를 넣고 배포).
   이번 합격 기준은 "표로 갈린다 · 야구 회귀 0"까지다.

## ⑤ 이미 있는 사실을 다시 적는가

- 채널 함수를 다시 만들지 않는다 — 이름으로 조회해 **기존 함수를 부른다**.
- 종목 목록을 새로 정의하지 않는다 — 표의 키가 곧 목록이다.
- 출처 키 이름을 새로 정하지 않는다 — 지금 원장에 있는 그대로 쓴다.
