# ACL-2 — ACL-1 이 만든 회귀 둘. 키를 바꿨으면 **비교하는 쪽도** 바꿔야 한다

## 왜

ACL-1 배포 직후 진단표가 잡았다.
```
A-1 디빅 | 6행 · 북 ['oddsportal-avg','op-1205'] · 배당 None/4.8/None  ← Draw 만 붙었다 (4/4)
C-5 FotMob | 8199 교토@대전 — 경기 매칭 0
```
둘 다 **ACL-1 이 바꾼 키를 한쪽만 따라간** 결함이다.

① `team_key()` 에 국가 접미사 제거를 넣었다(ACL-1). 경기 매칭 키
   `key_home`/`key_away` 는 그것으로 만드는데, `odds_free.collect_soccer` 는
   저장할 side 이름을 되돌릴 때 **`norm(side)`** 로 비교한다:
```
team_key('Kashima Antlers (Jpn) ') = 'kashima antlers'      ← 키
norm     ('Kashima Antlers (Jpn) ') = 'kashima antlers jpn'  ← 비교
```
   그래서 홈·원정 줄은 오즈포털 원표기 그대로 저장되고, 우리 팀명과 맞는 것은
   `Draw` 뿐이다. `p_market` 이 못 서고 → D-8·D-10 이 통째로 무효다.

② `SLATE_CANONICAL` 로 `Daejeon Hana Citizen → Daejeon Citizen` 을 넣었는데
   (ACL-1, 한 구단이 두 팀이 되는 것을 막으려고), `fotmob.find_match` 는
   FotMob 원표기로만 비교한다. 우리 `games` 에는 짧은 이름이 있으니 안 붙는다.

## ① 이 함수/상태를 읽는 곳 **전부**

```
odds_free.collect_soccer  side 되돌리기  ← 축구 배당 전량(7리그 + acl)
fotmob.find_match         ← attach · _lineup_recheck · 진단 스크립트
```

## ② 깨뜨릴 수 있는 기존 동작

- 🔴 `norm` → `team_key` 로 바꾸면 **별칭까지 탄다.** 기존 7리그에서 side 가
  다른 팀으로 환원되면 배당이 엉뚱한 팀에 붙는다. 그런데 키를 만든 것과
  **같은 함수**를 쓰는 것이므로 오히려 지금이 비대칭이다 — 계약이 기존
  리그 표기 대조를 그대로 유지하는지 본다.
- 🔴 `find_match` 에 canonical 을 넣으면 **FotMob 쪽만** 거쳐야 한다. 우리
  `games` 이름에까지 적용하면 이미 canonical 인 값을 두 번 매핑한다.

## ③ 되돌리기

커밋 1개 revert. 스키마·설정 변경 없음.

## ④ 측정

`repro_acl2.py` 재실행 + 운영에서 배당 재수집 후 홈·원정 줄 존재 확인.

## ⑤ 계약

```
test_side_되돌리기가_경기_매칭과_같은_키를_쓴다
test_국가접미사_붙은_side_가_우리_팀명으로_돌아온다
test_기존_리그_side_되돌리기가_그대로다          ← 반대 위험
test_find_match가_canonical을_거친다
test_find_match는_우리이름을_두_번_매핑하지_않는다  ← 반대 위험
```
