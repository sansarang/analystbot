# FOT-3 — T-60 재판정이 **이름뿐이다** (PART A 표 S10)

## 왜

`_lineup_recheck` 는 `fotmob.diff_xi` 로 예상 XI ↔ 공식 XI 차이를 만들어
**`game_trace` 에 적고 끝난다.** 확정 라인업이 예상과 달라도 `p_code` 도 등급도
그대로다 — `rejudge.reweigh` 를 **부르지 않는다.**

⚠️ PA-27 은 **딥서치 경로**(기사 결장 명단)를 이었다. 여기는 **공식 XI 경로**다.
   docs/FORKS.md F-2 의 권한표에서 **대체 권한이 있는 쪽이 바로 이쪽인데**
   그쪽이 안 이어져 있었다.

🔴 그리고 이 경로는 딥서치와 달리 **선수 시장가치가 있다** —
   `fotmob.parse_lineup` 이 `market_value` 를, 팀 칸이 `total_market_value` 를
   준다. 중요도 가중이 **진짜로** 된다(딥서치는 1.0 중립이었다).

## ① 이 함수/상태를 읽는 곳 **전부**

```
scheduler._lineup_recheck          ← 잇는 곳 (트리거 kind="lineup" · 축구만)
fotmob.attach → out["diff"]        ← 입력. lineup_type == confirmed 일 때만 찬다
fotmob.parse_lineup starters       ← {id, name, market_value, …}
fotmob 팀 칸 total_market_value    ← 중요도 분모
rejudge.reweigh(source=SRC_OFFICIAL) ← 대체 권한이 있는 출처
pick_ledger.record_rejudge         ← **신규**. `_REJUDGE_SAVE` 의 유일한 사용처
pick_ledger.record_confirm_and_analysis ← 인라인 저장을 이 함수로 바꾼다(사본 제거)
db: adj_after · p_code_after · grade_after · regraded_by  ← 같은 칸을 쓴다
```

## ② 깨뜨릴 수 있는 기존 동작

- 🔴 **저장 전용이다.** `p_code`·`confidence`·`adj_pp` 를 안 덮는다. 카드·발송도
  안 건드린다 — `*_after` 를 읽는 곳은 여전히 0건이다.
- 🔴 **저장 SQL 을 두 곳에 두지 않는다.** PA-27 의 인라인 저장을 `record_rejudge`
  로 옮기고 **둘 다 그것을 부른다.** 계약이 `_REJUDGE_SAVE` 가 한 곳에서만
  쓰이는지 잰다.
- 🔴 **출처는 `SRC_OFFICIAL` 이다** — 이 경로만 `주전결장` 을 대체할 수 있다.
  `regraded_by` 로 딥서치 행과 갈린다. 계약이 잰다.
- 🔴 **`diff` 가 없으면 아무것도 안 한다.** `attach` 는 `confirmed` 일 때만
  `diff` 를 채운다 — 예상 XI 단계에서는 재판정하지 않는다.
- 🔴 **원장 행이 없으면 안 쓴다.** 판정 전이면 되짚을 `p_code` 가 없다.
- 🔴 **실패해도 트리거를 안 막는다** — `game_trace` 기록과 `fired_at` 표시가
  먼저다. CLV·이동과 같은 규약.
- 🔴 **팀별 총가치로 중요도를 맞춘다.** `importance` 의 분모는 **그 선수 팀의**
  총가치인데 `reweigh` 는 `team_total_value` 를 하나만 받는다. 그래서 호출부에서
  원정 선수 가치를 `홈총액/원정총액` 으로 **환산해** 넣는다 — 계산이 같아지고
  `reweigh` 시그니처를 안 바꾼다. 계약이 환산을 잰다.
  ⚠️ 이건 갈림길이 아니다 — `importance` 문서가 "팀 선발 총가치"라고 이미
     정해 놓았다(자기 팀). 딥서치를 돌리지 않았다.
- ⚠️ 이름으로 찾는다. `diff_xi` 는 **id 로 세고 이름을 돌려준다** — 같은 응답의
  선수 목록으로 이름→선수 표를 만들어 쓰므로 표기 흔들림이 없다.

## ③ 되돌리기

커밋 1개 revert. `_lineup_recheck` 의 블록과 `record_rejudge` 가 빠지고
PA-27 경로는 인라인 저장으로 돌아간다.

## ④ 측정

①과 **같은 명령**이 통과한다. 그리고 가짜 fotmob 응답으로 끝에서 끝까지:
```
예상 XI 에 있던 고가 선수가 공식 XI 에서 빠짐
  → adj_after {라인업결장:home …} · regraded_by official_xi · 주전결장 대체됨
  → value_coverage known == total  (딥서치와 달리 가치를 안다)
```

## ⑤ 계약

14건 — 부른다 · 출처가 official_xi · 대체 권한 · diff 없으면 안 함 ·
confirmed 아니면 안 함 · 원장 없으면 안 함 · 실패해도 트리거 계속 ·
원래 칸 안 덮음 · SQL 사본 없음 · 팀별 가치 환산(홈/원정) · 가치 커버리지 ·
이름→선수 표 · 발송 안 켬 · 야구 경로 안 건드림.
