# CTX-1 영향 지도 — 있는 재료로 계산되는 것을 비워 뒀다

## 1. 무엇이 틀렸나 (실측 원문)

판정 캐시에는 순위 자료가 있다:

```json
home_standing = {"rank": 5, "w": 71, "l": 82, "d": 0, "games_behind": 24.0, "win_pct": 0.464}
away_standing = {"rank": 2, "w": 85, "l": 68, "d": 0, "games_behind": 10.0, "win_pct": 0.556}
```

그런데 내보내기는 이렇게 낸다:

```json
"context": {"gb": 19.0, "record": null, "streak": null,
            "playoff_status": null, "playoff_reason": "진출·탈락 상태 저장 없음",
            "travel": null, "series_travel_reason": "시리즈 차수·이동 이력 저장 없음"}
```

`record` 는 `w-l` 이면 되는데 `standing.get("record")` 만 보고 null 을 냈다
(그 키는 캐시에 없다). 이동은 VEN-1 이 구장을 저장한 뒤로 계산 가능해졌다.

## 2. 어디를 고치나

`app/export/for_fable.py` — `_context_block` + 순수 함수 둘.

## 3. 영향 지도 5문

**① `playoff_status` 를 어디까지 낼 수 있나.**
🔴 **탈락만 증명된다.** 잔여경기 = `season_games − (w + l)` 이고,
`games_behind > 잔여` 면 산술적으로 따라잡을 수 없다.
**진출 확정(`clinched`)은 못 낸다** — 컷라인 아래 팀들의 순위표가 필요한데
캐시에 없다. 못 내는 것을 지어내지 않고 `alive` 로 둔다.
계약이 100승 팀도 `alive` 인지 확인한다(그게 정직한 값이다).

**② `streak` 은.**
캐시에 없다. **그대로 null + 사유**다. 최근 5경기로 계산할 수도 있지만
그것은 "연속"의 정의를 내가 새로 만드는 일이라 하지 않는다.

**③ 이동을 어떻게 아나.**
VEN-1 이 `games.venue_name` 을 저장했고 `form.last5` 가 그것을 싣는다.
직전 경기 구장과 오늘 구장이 같으면 **홈스탠드 N일차**, 다르면 **이동**이다.
🔴 구장을 모르면 **None** — "이동 없음"이 아니다.

**④ 시즌 경기 수를 어디서 아나.**
MLB 162 를 상수로 둔다. KBO(144)·NPB(143)는 다르므로 **리그별 상수**로
받고, 모르는 리그는 `playoff_status=None` 이다. 손으로 162 를 박지 않는다.

**⑤ 판정에 새나.**
새면 안 된다. CLAUDE.md §9: "시즌 순위 자체는 판정 입력 아님".
내보내기 표시값이고 `context` 안에만 있다.

## 4. 안 하는 것

- `clinched` 를 추측하지 않는다.
- `streak` 을 새로 정의하지 않는다.
- 시리즈 차수(`series_game`)는 statsapi 가 `seriesGameNumber` 로 주지만
  아직 저장하지 않는다 — 별건으로 등록한다(2-10-b).
