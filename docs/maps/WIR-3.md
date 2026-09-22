# WIR-3 — `search.verify` 를 기사 경로에 잇는다 (영향 지도 5문)

## ① 무엇이 안 이어져 있었나 (실측 2026-09-22)

`verify`·`drop_wrappers` 를 부르는 곳은 `tools/search_audition.py`(보고 도구)
**하나뿐**이었다. 운영 기사 경로(`rss_hits` → `chain_search`)는 지나지 않는다.

```
ADD-2(569f86d) MSN 래핑 버리기 · D38(85cdcd5) is_recap 교정
  → 만들었다. 그리고 **아무도 안 불렀다.**

오늘 KBO KT Wiz@SSG Landers 실측: 12건 중 5건이 msn.com · 본문 3자
  요청 5회를 버렸고, LLM 에는 제목만 들어갔다.
```

## ② 절제 실험 — **한 겹씩** 얹었다 (오늘 KBO 2경기 18건)

```
종전 18건 → ①래핑 -6 = 12 → ②리캡 -1 = 11 → ③24h창 -9 = 2
```

| 겹 | 폐기 | 판단 |
|---|---|---|
| ① 래핑(MSN) | 6/18 | **얹는다.** 본문이 3자다. 요청도 6회 아낀다 |
| ② 리캡 | 1/12 | **얹는다.** `‘FA 대박…3안타 1홈런 5타점 대폭발…SSG 4연승’` = 어제 상보 |
| ③ 24h 창 | 9/11 | 🔴 **얹지 않는다** — 아래 |

🔴 **③을 얹으면 오늘 재료가 사라진다**(실측 원문):
```
24h✗  [프로야구 전망] ‘불붙은 타선’ KT 위즈, SSG 상대로 3연승 정조준
24h✗  대만 매체 "왕옌청 한국전 선발 불발…한화와 차출 조건 합의"[AG]
24h✗  [AI프리뷰] 20일 수원 KT-두산전, 대체 선발 박신지 …
```

## ③ 🔴 창이 두 벌이다 — **결정 대기** (→ `docs/FORKS.md` F-19)

```
scout_config.MAX_AGE_H['pre']          48h · **지금 시각** 기준 · rss_hits 가 쓴다
situation.SITUATION_WINDOW_HOURS       24h · **킥오프** 기준 · classify 가 쓴다
                                       (MLB 만 36h — 2026-09-07 실측 근거 있음)
```

두 창은 **소비처가 다르다** — 48h 는 기사 추출 입력, 24h 는 상황 태그.
24h 에는 근거 실측이 붙어 있다("김성현 은퇴식 T-24.8h 가 되살아난다").
**어느 것이 추출 입력의 정본인지는 사용자 결정 사항이다.** 그래서 `verify` 에
`window` 스위치를 두고 `rss_hits` 는 `window=False` 로 부른다 — 결정이 나면
**한 단어**로 뒤집는다.

## ④ 어디를 건드리나

| 파일 | 무엇 |
|---|---|
| `app/deepsearch/search.py` | `verify(..., window: bool = True)` — 기본값 그대로라 오디션 도구 동작 불변 |
| `app/collectors/satellite.py` | `rss_hits(..., sport=None, kickoff=None)` → `verify(window=False)` · `rss_supplement(..., sport=None)` 전달 · `gather_kbo` 가 `sport="kbo"` |
| `app/collectors/satellite_soccer.py` | `rss_supplement` 호출 2곳에 `sport="soccer"` |

⚠️ **`gather_npb`·`gather_mlb` 는 안 건드린다** — 그 둘은 `rss_hits` 를 아직
   부르지 않는다(D48). 연결은 별도 커밋이다.
⚠️ `sport` 를 안 주면 `registry.recap_markers` 규약대로 **빈 튜플** 이라
   리캡을 안 거른다 — 모르는 종목을 굶기지 않는다. 래핑은 항상 버린다.

## ⑤ 되돌릴 수 있나

`verify(...)` 한 줄을 빼면 종전이다. 창은 `window=` 한 단어다.

## ⑥ 틀렸을 때 누가 알려주나

계약 6건: 본문 없는 래핑 폐기 · 같은 제목이 있으면 **갈아끼움** ·
경기 후 상보 폐기 · **24h 창을 여기서 걸지 않는다**(반대 위험) ·
요청이 늘지 않는다(추가 검색 0) · 래핑 목록·리캡 표지를 `rss_hits` 안에
**다시 적지 않았다**(사본 금지) · `sport` 없으면 리캡 미적용.
