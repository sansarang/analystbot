# SAT-S3 — 위성 검색을 야구/축구로 파일부터 분리한다

사용자 지시 2026-09-12: "인공위성 서치기능은 야구와 축구를 분리해라"

## 왜

한 파일(`app/collectors/satellite.py`, 800줄 남짓)에 MLB·KBO·NPB·축구가 다
들어 있다. SAT-S1~S2 에서 축구를 붙이며 **같은 파일을 네 번 고쳤고**, 그때마다
야구 상수 옆을 지나갔다. 축구 검색어 하나를 만지다 `_KBO_TERMS_LIST` 나
`_NPB_TERMS` 를 건드릴 위험이 그대로 있다.

## ① 이 함수/상태를 읽는 곳 **전부**

밖에서 `satellite` 를 쓰는 곳은 **넷뿐이다**(전수 grep):

```
app/collectors/kbo_roster.py   from app.collectors.satellite import _article
app/engine/deepsearch.py       from app.collectors.satellite import read_cache
app/engine/gather.py           from app.collectors.satellite import read_cache
app/scheduler.py               from app.collectors import satellite  (run_satellite)
```

나머지(`gather_kbo`·`parse_daum_news`·`_daum_fetch` …)는 **전부 파일 안에서만**
쓰인다(+테스트).

🔴 그래서 **야구는 제자리에 두고 축구만 떼어낸다.** 움직이는 코드가 적을수록
   끊길 곳도 적다. 야구 세 어댑터는 운영에서 도는 것이고, 옮기다 끊으면 P0 다.

빌려 쓰는 원본 — 축구가 **다시 만들지 않는다**:
| 무엇 | 어디 |
|---|---|
| 다음 검색·파싱 | `satellite._daum_fetch` · `parse_daum_news` |
| 야후 검색·파싱 | `satellite._yahoo_fetch` · `parse_yahoo_news` |
| 본문 수집 | `satellite._fetch_article_body` |
| 기사 모양 | `satellite._article` |
| 토르 보강 | `satellite._tor_supplement` |

## ② 만드는/바꾸는 상태

| 상태 | 성격 | 다른 곳이 다른 규칙으로 갱신하나 |
|---|---|---|
| `app/collectors/satellite_soccer.py` | 새 파일 | 아니다 |
| `satellite` 에서 축구 심볼 제거 | 이동 | 🔴 테스트가 `SAT.gather_soccer` 를 참조한다 — 함께 옮긴다 |
| `_ADAPTERS["soccer"]` | 참조 대상이 새 모듈 | 아니다. 키·동작 불변 |

🔴 **순환 임포트를 만들지 않는다.** `satellite` 가 축구 모듈의
   `gather_soccer` 를 등록해야 하고, 축구 모듈은 `satellite` 의 검색 함수를
   써야 한다. 해결:
   - 축구 모듈은 검색 함수를 **함수 안에서** 임포트한다(호출 시점 조회).
     그래서 `monkeypatch.setattr(satellite, "_daum_fetch", …)` 가 그대로 먹는다.
   - `satellite` 는 **파일 맨 끝**에서 축구 모듈을 임포트해 `_ADAPTERS` 에 넣는다.

⚠️ DB·Redis·env·프롬프트를 건드리지 않는다. **순수 이동**이다.

## ③ 리그·종목·경로 분기

분기가 **줄어든다.** 지금 `gather_soccer` 안에 있는 리그 분기(`_SOCCER_SOURCE`)는
그대로 축구 파일로 따라간다 — 야구 파일에서는 사라진다.

## ④ 조용히 실패하는가

| 위험 | 대응 |
|---|---|
| 🔴 **야구 어댑터가 끊긴다** ← 전부 | `_ADAPTERS` 넷을 전부 단언 + 야구 함수가 제 파일에 있는지 소스로 단언 |
| 밖에서 쓰는 심볼이 사라진다 | `_article`·`read_cache`·`run_satellite`·`gather` 존재를 단언하고, **실제 임포트 줄을 그대로 실행**하는 계약 |
| 축구가 검색 원시함수를 **복사**한다 | 축구 파일에 `_DAUM_URL`·`parse_daum_news`·`_article` 정의가 없는지 단언 |
| 축구 코드가 야구 파일에 **남는다**(두 곳) | 야구 파일에 축구 심볼 부재를 단언 |
| 순환 임포트로 기동이 죽는다 | 전체 스위트가 임포트를 돌린다. 축구는 지연 임포트 |
| 동작이 바뀐다 | 별칭·리그표·검색어 상수를 값으로 단언 + 실제 호출 경로 1건 |

⚠️ **아직 못 재는 것**: 운영 기동. 순수 이동이라 위험은 임포트뿐이고 스위트가
   그것을 돌린다. 배포 후 `/health` 로 커밋 해시를 대조한다.

## ⑤ 이미 있는 사실을 다시 적는가

- 검색 원시함수·기사 모양·토르 보강을 **복사하지 않는다** — 야구 파일에서
  가져온다. 계약이 복사 금지를 단언한다.
- 리그 라벨은 여전히 `app/leagues.py` 가 원본(계약이 전수 대조).
- 실측 주석(검색어 39/40, 토르 403 …)은 축구 파일로 **함께 옮긴다** —
  그 근거가 코드와 떨어지면 다음 사람이 검색어를 바꾼다.
