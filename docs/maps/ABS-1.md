# ABS-1 영향 지도 — 결장 근거를 필드로

## 1. 무엇이 틀렸나 (재현 원문)

```
$ PYTHONPATH=. uv run pytest tests/export/test_1_3_basis.py -q -x
AttributeError: module 'app.collectors.absences' has no attribute 'BASES'   exit=1
```

오늘 NYY 내보내기 원문 — 근거가 **문장 안에만** 있다:

```
- New York Yankees의 Jazz Chisholm Jr.(주전 타자) Injured 10-Day로 결장
- New York Yankees의 Aaron Judge 중심 타선 결장 — 평소 3번, 오늘 라인업에서 빠짐
"regulars_missing_count": 10          ← IL 6 과 라인업 제외 4 가 한 숫자에 뭉쳐 있다
```

읽는 쪽은 정규식을 쓰게 되고, 그 정규식은 문장을 바꾸는 날 조용히 틀린다.

## 2. 어디를 고치나 (파일:라인)

| 파일 | 무엇 |
|---|---|
| `app/collectors/absences.py` | `BASES`·표지 상수·`classify()` 추가 |
| `app/engine/lineup_diff.py:281` | 표지를 손으로 적던 자리를 상수 참조로 |
| `app/export/for_fable.py:472` | `out` 을 객체로 · `regulars_missing_count` 를 근거별로 |

## 3. 영향 지도 5문

**① 문장을 바꾸나.**
아니다. **한 글자도 바꾸지 않는다.** `absences._describe` 머리말이 "문구가 곧
계수다 — '주포'는 −4%p, 그 외 타자는 −2%p"라고 적고 있고, `scoring._absence_factors`
가 그 문구를 읽는다. 계약이 `merge_absences_from_diff` 출력 두 줄을 **문자열
그대로** 잠근다.

**② 왜 분류를 만든 쪽에 두나.**
근거를 아는 것은 문장을 만든 쪽이다. 읽는 쪽이 정규식으로 되짚으면 그것이 사본이고,
사본은 원본이 바뀔 때 따라가지 않는다(이 저장소가 워치독 오탐 4건으로 겪은 것).
그래서 표지 문자열을 `absences.py` 에 한 번 적고 **두 생산자가 그것을 가져다 쓴다.**
계약이 `lineup_diff` 안에 그 문자열이 다시 나타나면 실패한다.

**③ `out` 의 모양이 바뀌면 누가 깨지나.**
`out` 은 내보내기 산출물 안에만 있다. `rg "\\[.out.\\]"` 로 읽는 곳은
`for_fable.to_md`(개수만 센다)뿐이고, 판정 경로는 `research["absences"]`(문장
리스트)를 그대로 읽는다 — 그쪽은 **건드리지 않는다**. `n05_evidence` 도
`ctx.inject["absences"]` 를 보지 내보내기를 보지 않는다.

**④ 근거가 넷인데 둘만 나오면.**
`transfermarkt`·`fotmob_unavailable` 은 축구 경로다. 야구 슬레이트에서는 나오지
않는 것이 정상이고, 모르는 문장은 `basis=None + basis_reason` 으로 남긴다 —
**지어내지 않는다**(`null + reason` 규율).

**⑤ 무엇이 조용히 0이 되나.**
`classify` 가 못 알아본 문장이 생기면 근거별 집계에서 빠진다. 그래서 집계에
`unknown` 칸을 두고, 합이 전체와 같은지 계약이 센다.

## 4. 안 하는 것 (범위 밖 — 등록만)

- `lineup_diff` 의 "평소" 대조는 **이름 기준**(`canon_name`)이다. 09-14 지시는
  선수 id 기준을 요구한다. 그것을 바꾸면 매칭되는 선수 집합이 바뀌고 곧 λ 가
  바뀐다 — **판정 로직 변경**이라 이 단위에서 하지 않는다 → `1-3-b`.
- `regulars_missing_count` 가 투수(선발·불펜)까지 세는 것도 그대로 둔다.
  이름과 내용이 어긋나 있으나 세는 대상을 바꾸는 것은 범위 밖이다 → `1-3-c`.
