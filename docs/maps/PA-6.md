# PA-6 — 티어 미기입이면 U5~U12 가 통째로 건너뛰어진다

## 왜

손으로 돌린 ACLE 2경기 실측(2026-09-16 15:20 KST · 커밋 `d09f3b9`):

```
[v3] Kashiwa Reysol@Jeonbuk Hyundai Motors FC 승자 Jeonbuk · 확신 하 · 수집{'satellite': 15}
[v3] Vissel Kobe@Port FC 승자 Vissel Kobe · 확신 하 · 수집{'satellite': 15}
[deepsearch] free provider=gemini ok=True 파싱=OK  ×2

g8360 Kashiwa Reysol @ Jeonbuk Hyundai
   사전값=None · src=none · 시장=0.2726 · p_code=0.2726
   가설=없음 · 확인=False · 가감={} · 흐름=False · 구조=False · 결정축=None
```

위성·딥서치·판정은 다 돌았는데 **어제 만든 단계가 전부 비었다.**

원인은 `pick_ledger.record_prior:754` 의 `return None` 이다. 티어가 없으면
사전값만 적고 거기서 끝내는데, **그 뒤 줄**에 가설 생성(U5)이 있고,
호출부에서 `record_confirm_and_analysis`(U7·U12)가 그 반환값을 받는다.
`None` 이 오면 그 둘이 통째로 건너뛰어진다.

🔴 **`hypothesis.build` 는 보드 고정을 이미 처리한다** — 빈 가설 + 사유
   "사전값 또는 시장이 없다 — 찾을 것이 없다"(`hypothesis.py:98`).
   즉 돌게 **설계돼 있는데 앞에서 막힌 것**이다.
🔴 야구가 되고 축구가 안 되는 이유도 이것이다 — MLB·KBO·NPB 는 티어가
   채워져 있어 이 가드를 통과한다. ACL 은 `config/tiers/acl.yaml` 에 이
   두 팀이 없다.

## ① 이 함수/상태를 읽는 곳 **전부**

```
pick_ledger.record_prior          ← 고치는 곳(:748~754)
  └ 반환 {"label","gap_pp","side","p_prior","prior_src"}
     └ pick_ledger.record_analysis 안 호출부(:364) `_gate`
        └ record_confirm_and_analysis(gate=_gate)  ← U7 확인 · U12 분석
hypothesis.build(gate_label, …)   ← G.BOARD 를 이미 처리한다(빈 가설)
gate.BOARD                        ← 라벨 원본. 문자열을 베끼지 않는다
prior.load_tiers / team_elo       ← 티어 None 판정의 원본
_PRIOR_SAVE                       ← 사전값 저장(지금도 저장한다 — 안 건드린다)
```

## ② 깨뜨릴 수 있는 기존 동작

- 🔴 **사전값을 지어내지 않는다.** U3 가 정한 규약(`p_prior=NULL`,
  `prior_src='none'`)은 그대로다. 중앙값으로 메우면 U3 을 되돌리는 것이다.
- 🔴 **LLM 비용이 늘지 않는다.** `analyze.run` 은 게이트가 `OVER|DOUBT` 가
  아니면 스스로 건너뛴다. 보드 고정은 대상이 아니므로 호출이 늘지 않는다.
  계약이 그것을 잰다 — 늘면 무료 한도가 즉시 터진다.
- 🔴 **`if not tiers` (리그 표 자체가 없음, :727) 는 안 건드린다.** 그건
  "이 리그를 아예 모른다"이고 지금 단위의 대상이 아니다.
- ⚠️ 원장에 `hypothesis` 가 **처음으로 채워진다** — 값은 빈 need 와 사유
  문자열이다. "찾을 것이 없다"가 기록되는 것이 목적이다(조용한 NULL 보다 낫다).
- ⚠️ `confirmed` 는 need 가 비어 `sufficient=False`·`board=True` 로 남는다.
  그게 사실이다.

## ③ 되돌리기

커밋 1개 revert. 바뀌는 것은 가드 한 블록(`return None` → 보드 고정 반환)
뿐이다. 되돌리면 종전처럼 사전값만 남고 U5~U12 가 빈다.

## ④ 측정

①과 **같은 명령**이 통과한다. 그리고 ACLE 2경기를 다시 돌려 원장
`hypothesis` 가 차고 `gate_result` 가 보드 고정으로 남는 원문.

## ⑤ 계약

```
test_티어_미기입이면_보드고정을_돌려준다
test_사전값은_여전히_NULL이다                  ← 반대 위험(지어내기)
test_보드고정_가설은_비어_있다
test_보드고정은_analyze를_부르지_않는다         ← 반대 위험(무료 한도)
test_리그표가_없으면_종전대로_None             ← 반대 위험(범위 확장)
test_티어가_있으면_동작이_안_바뀐다             ← 반대 위험(야구 회귀)
```
