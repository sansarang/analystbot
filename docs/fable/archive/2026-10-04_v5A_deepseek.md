# 2026-10-04_v5a_appendix.pdf — **기계 추출**(손으로 옮겨 적지 않는다 · §11-5)


---

## PDF Page 1

AnalystBot v5-A 부록 — DeepSeek 가설·시나리
오·반증 단계
​Oct 4, 2026 · ​@jung youngjin
0. 지위·범위
이 문서는 v5 전환 지시문의 부록 A다. v5 본문은 그대로 유효하고, 이 부록은 DeepSeek를 파이프라인
의 두 단계(가설·시나리오 생성, 반증)에 넣는 것만 정한다. 충돌하면 이 부록이 이긴다.
규칙 변경 — 유료 API 예외는 Solar 하나에서 Solar(Upstage)와 DeepSeek 둘로 늘어난다. 그 외 유
료 서비스는 여전히 0건이다. 두 API의 비용은 v5 §2 예산 가드가 합산해서 센다.
적용 시점 — v5 §10-4 게이트 5(측정 2: 카드 비교)를 Solar 단독으로 한 번 돈 다음이다. Solar 단독 결
과가 기준선이 되어야 DeepSeek가 적중을 올렸는지 숫자로 보인다(§6). 그 전에 DeepSeek 코드를
쓰지 않는다.
왜 이 자리인가 — 09-29~10-04 미적중을 갈라 보면 변수를 못 찾아서 난 것보다 찾은 변수로 시나리오
를 잘못 짜서 난 것이 많다. 남아공 5-0(결장 변수는 있었는데 대량득점 시나리오 부재), 콜롬비아 0-
1(h2h로 한 시나리오를 눌러 무패 0.85), 크로아티아 봇 카드(난타전 시나리오 부재로 거짓 1.0). 이 단계
는 검색이 아니라 추론이고, DeepSeek의 추론 모델을 여기에 둔다.
1. 역할 분담 — 파이프라인 다섯 단계
결론(등급·pick)은 계속 코드가 낸다. DeepSeek는 시나리오 세트를 만들고 넓히는 일만 한다.
DeepSeek가 하지 않는 것
단계
담당
입력
출력
웹 접
근
1 검색·읽기
Solar
경기 정보·구조 사실
변수 후보(인용·URL)
있음
2 검증
코드(v5
§5)
Solar 출력
검증된 변수 목록
—
3 가설·시나리
오
DeepSeek
검증된 변수 + 구조 사실 + 보
드 줄
팀별 가설, 시나리오 A~E
없음
4 반증
DeepSeek
3의 시나리오 + 보드 줄 + 변
수
빠진 시나리오 제안
없음
5 판정
코드(v5
§6)
3+4
필수형 보강, 대입, 상한, 등급,
pick
—
AnalystBot v5-A 부록 — DeepSeek 가설·시나리오·반증 단계
Page 1 of 8


---

## PDF Page 2

검색·본문 읽기·변수 추가 — Solar 자리다. DeepSeek가 새 사실을 말하면 그 시나리오는 폐기(§5
M41).
등급·생존율·pick·상한 — 코드 자리다. DeepSeek 출력에 등급·확률·승자 단어가 있으면 무시하고
로그만 남긴다.
시나리오 삭제 — 반증 단계는 시나리오를 추가만 할 수 있다. 기존 시나리오를 지우거나 무게를 낮추
지 못한다(시나리오를 줄이면 거짓 1.0이 다시 생긴다).
보드 숫자(배당) — 보드는 마켓 종류와 기준선만 받는다.
Solar 출력의 가설·시나리오 초안(v5 §3-5)은 어떻게 되나 — Solar는 변수와 gaps 까지만 낸다. 가설·
시나리오 초안 칸은 v5 §3-6 스키마에서 선택(optional)으로 바꾸고, 있으면 DeepSeek 입력에 "참고
초안"으로 같이 넘긴다. DeepSeek가 최종 초안을 쓴다.
2. DeepSeek 호출 사양
모델 — 추론 모드가 있는 모델을 쓴다. 2026-09 개편 이후 모델 ID와 가격이 자주 바뀌었으니 Claude
Code가 공식 api-docs·pricing 페이지를 직접 읽어 config/llm.yaml 의 deepseek: 칸에 모델
ID·입력/캐시/출력 단가·확인 날짜를 적는다. 매체 수치는 쓰지 않는다. 시작은 저가 모델(Flash 계열, 추
론 켬), 측정(§6)에서 반증 단계 효과가 약하면 사용자 승인 후 상위 모델.
키·결제 — 키는 로컬 .env 의 DEEPSEEK_API_KEY , 이름만 .env.example . 결제·충전은 사용자가
콘솔에서 한다. 봇에 결제 코드 없음. .env 키 ⊆ .env.example 계약 그대로.
웹 차단 — DeepSeek 호출에는 도구를 하나도 넘기지 않는다(tools 비움). 함수 호출·검색 기능이 있어
도 쓰지 않는다. 입력은 코드가 만든 JSON 하나, 출력은 JSON 하나다.
예산 — v5 §2 상한에 합산
단계 3·4 입력은 검증된 변수 목록과 시나리오뿐이라 경기당 1만 토큰 안팎이다. 시스템 프롬프트(규칙·필
수형·스키마)는 고정 문자열로 앞에 두어 캐시 단가를 받는다. usage 와 단가 곱을 Solar와 같은
ledger/cost_YYYYMM.jsonl 에 provider:deepseek 로 적는다.
상한
값(초기)
초과 시
경기당 DeepSeek 입력 토
큰
30,000
단계 3만 돌리고 단계 4 생략, 카드에
redteam_skipped
경기당 DeepSeek 출력 토
큰(추론 포함)
15,000
같음
하루·월 비용
v5 §2의 하루 $3·월 $40에
Solar와 합산
v5 §2 그대로
AnalystBot v5-A 부록 — DeepSeek 가설·시나리오·반증 단계
Page 2 of 8


---

## PDF Page 3

호출 규칙 — OpenAI 호환 SDK, base_url 은 공식 문서 값. JSON 출력 모드 강제. 타임아웃 120초,
재시도 2회. 실패하면 DeepSeek 없이 v5 원래 경로(Solar 초안 + 코드 필수형 보강)로 판정하고 카드
에 deepseek_unavailable . DeepSeek 장애가 경기 분석을 막지 않는다.
보내는 것 — 검증된 변수(유형·방향·주장·인용 요약), 구조 사실(순위·최근 결과·선발·XI), 보드 줄(마켓·
기준선). 기사 원문 전체, URL, 사용자 정보, 배당은 보내지 않는다.
3. 단계 3 — 가설·시나리오
입력( HypoInput ) — 코드가 만든다.
{
  "match": {"home":"team:000151","away":"team:000266","names":
{...},"sport":"soccer",
            "competition":"UEFA Nations League 
A3","venue_type":"home|neutral","kickoff_kst":"..."},
  "lineup_state": {"home":"confirmed|predicted|none","away":"..."},
  "facts": {"standings":..., "recent":..., "h2h":..., "starters":..., 
"xi":...},
  "variables": 
[{"id":"R1","type":"absence_def","team":"team:000151","direction":"opp_goals_
up",
                 "hardness":2,"claim":"에를리치 햄스트링 결
장","conflict":false}],
  "board": [{"market":"1x2"},
{"market":"handicap","side":"away","point":-0.5},
{"market":"total","point":2.5}],
  "required_types": ["fav_concedes","blowout","regression_flip"],
  "solar_draft": {...}
}
required_types 는 코드가 v5 §6-2 조건으로 미리 계산해서 넘긴다. DeepSeek는 그 목록의 시나리
오를 반드시 쓴다.
프롬프트 요지(시스템, 고정)
1. 너는 사실을 만들지 않는다. variables 와 facts 에 없는 사실은 쓰지 않는다. 모르면 시나리오에
넣지 않는다.
2. 먼저 두 팀의 폼을 facts.recent 로 요약한다(최근 5경기·연속·직전 득실).
3. 팀별 가설: 이긴다면 왜(변수 ID들) + 그 가설을 무너뜨리는 조건(변수 ID들). 양방향 변수는 양쪽에
다 쓴다.
4. 시나리오 4~6개. 각 시나리오는 driver_vars (변수 ID), mechanism (그 변수들이 어떻게 작동해
그 결과가 나오는지 1~2문장), outcomes (스코어 1~2개).
AnalystBot v5-A 부록 — DeepSeek 가설·시나리오·반증 단계
Page 3 of 8


---

## PDF Page 4

5. required_types 의 시나리오를 반드시 포함한다. 근거 변수가 약하면 weak:true 로 표시하되 빼
지 않는다.
6. 전부 같은 방향이면 안 된다. 각 팀이 이기는 시나리오가 적어도 하나씩 있어야 한다(근거가 약하면
weak).
7. h2h는 메커니즘(세트피스·역습 방식)이 있을 때만 driver로 쓰고, 다른 시나리오를 누르는 근거로 쓰
지 않는다.
8. 등급·확률·승자·배당·추천 단어를 쓰지 않는다.
출력( HypoOutput )
{
  "form": {"team:000151":"...","team:000266":"..."},
  "hypotheses": {"team:000151":{"reasons":["R3","R6"],"breaks":["R1","R2"]}, 
"team:000266":{...}},
  "scenarios": [{"id":"A","driver_vars":
["R2","R7"],"mechanism":"...","outcomes":[[1,2],[1,3]],
                 
"type":"normal|fav_concedes|blowout|regression_flip|upset","weak":false}]
}
코드 처리
driver_vars 의 ID가 입력 variables 에 없으면 그 시나리오 폐기( unknown_var ).
mechanism 에 입력에 없는 고유명사(선수·팀·사건)가 나오면 폐기( new_fact ). 고유명사 목록은
입력 변수·사실·XI에서 코드가 뽑는다.
outcomes 가 비거나 종목 범위 밖(축구 0~9, 야구 0~25)이면 폐기.
남은 시나리오에 v5 §6-2 자동 보강을 그대로 돌린다 — DeepSeek가 필수형을 빠뜨렸으면 코드가
템플릿으로 추가하고 added_by:code . 추가가 생기면 원장에 deepseek_missed_required 로
센다(§6 측정 지표).
strength는 v5 §6-1대로 driver_vars의 hardness 합. weak:true 는 strength를 바꾸지 않는다
(표시만).
4. 단계 4 — 반증(레드팀)
판정 직전에 이 마켓을 죽이는 시나리오가 세트에 빠졌나를 따로 묻는다. 페이블이 채팅에서 놓쳤던 질문
이 이것이다(남아공 5-0: 언더를 죽이는 대량득점형 부재 / 크로아티아 봇: 언더 3.5를 죽이는 난타전 부
재 / 콜롬비아: 무패를 죽이는 파라과이 승 갈래를 h2h로 눌러 무시).
언제 도나 — 단계 3 시나리오 세트로 코드가 1차 생존 계산을 한 뒤, 생존 0.8 이상인 마켓이 하나라도 있
을 때만. 등급 후보가 없으면 반증할 결론도 없으니 비용을 쓰지 않는다.
입력( RedTeamInput ) — HypoInput 의 변수·사실·보드 + 단계 3 시나리오(코드 보강 포함) + 1차 생
존표에서 0.8 이상인 마켓 목록.
AnalystBot v5-A 부록 — DeepSeek 가설·시나리오·반증 단계
Page 4 of 8


---

## PDF Page 5

프롬프트 요지(시스템, 고정)
1. 너의 일은 아래 마켓들이 틀릴 수 있는 길을 찾는 것이다. 마켓을 지지하지 마라.
2. 마켓마다: 이 마켓을 죽이는 스코어 범위를 적는다(예: 언더 2.5 → 합계 3골 이상).
3. 그 범위에 들어가는 시나리오가 세트에 있는지 본다. 있으면 covered .
4. 없으면, 입력 변수만으로 그 범위를 만드는 시나리오가 가능한지 판단한다. 가능하면
driver_vars · mechanism · outcomes 로 새 시나리오를 제안한다. 근거 변수가 하나라도 있으면
제안한다 — 약해도 제안하고 weak:true .
5. 입력 변수로 정말 만들 수 없으면 impossible 과 이유 한 줄.
6. 기존 시나리오를 지우거나 약하다고 평가하지 마라. 추가만 한다.
7. 새 사실을 만들지 마라.
출력( RedTeamOutput )
{
  "markets": [
    
{"market":"total_under_2.5","kill_range":"sum>=3","status":"covered|proposed|
impossible",
     "covered_by":["E"],
     "proposal":{"id":"RT1","driver_vars":
["R1","R4"],"mechanism":"...","outcomes":[[2,2]],"weak":true},
     "reason":"..."}
  ]
}
코드 처리
proposal 은 §3 코드 처리와 같은 검사(unknown_var·new_fact·범위)를 통과해야 세트에 들어
간다. 통과하면 added_by:redteam .
추가 뒤 v5 §6-3~§6-6 판정을 다시 돈다. 그 마켓의 생존율이 떨어지면 등급이 내려가고, 카드에 "반
증 단계가 시나리오 RT1을 추가해 언더 2.5 생존 1.0 → 0.83"처럼 적는다.
impossible 은 그대로 받지 않는다. 코드가 v5 §6-2 필수형 조건을 다시 대조해 필수형 조건이 걸
리는데 impossible 이라 했으면 무시하고 템플릿 시나리오를 넣는다( redteam_overruled ).
반증 단계는 등급을 올리지 못한다. 시나리오가 늘기만 하므로 생존율은 같거나 내려간다. 올라가는
결과가 나오면 버그로 보고 카드 금지(M44).
출력 예(카드 하단)
AnalystBot v5-A 부록 — DeepSeek 가설·시나리오·반증 단계
Page 5 of 8


---

## PDF Page 6

■ 반증
  언더 2.5   covered (E 2-2)            생존 0.80 유지
  잉글랜드 무패 proposed RT1(R10·R13 → 2-1 크로아티아, weak)  생존 0.85 → 0.85 (C와 
같은 갈래)
  오버 2.5   covered (B 0-0)            생존 0.80 유지
5. 계약 M41~M46과 돌연변이
v5 §9 체계 그대로 tests/contracts/ 에 조항 번호 이름으로 하나씩 두고, 각 계약에 실제로 가드를
끄는 돌연변이를 단다.
정답지 재현 계약 — v5 §10-1 정답지의 페이블 오답 경기 셋(남아공 5-0 에리트레아전, 콜롬비아–파라
과이, 크로아티아 봇 카드)을 고정 입력으로 단계 3·4를 돌렸을 때, 각 경기에서 실제 결과를 만든 갈래(대
량득점·파라과이 승·난타전)가 세트에 들어가야 한다. 하나라도 빠지면 실패. 이 셋이 DeepSeek를 넣는
이유이므로 이 테스트가 통과하지 않으면 DeepSeek 단계를 켜지 않는다.
6. 도입 순서와 측정
DeepSeek가 적중을 올리는지는 같은 정답지로 켜기 전·후를 나란히 재서 판단한다. 감으로 켜지 않는
다.
1. 기준선 — v5 게이트 5까지 Solar 단독으로 통과한 상태에서, 정답지 20경기의 카드 비교(v5 §10-3)
결과를 metrics/baseline_solar.json 에 고정한다.
2. 단계 3만 켬 — DeepSeek 가설·시나리오만 넣고 같은 20경기를 다시 돈다.
번호
계약
돌연변이(빨개져야 함)
M41
DeepSeek 시나리오의 driver_vars는 검증된 변수
ID만, mechanism에 입력 밖 고유명사 금지 → 위반
시나리오 폐기
unknown_var 검사 제거, new_fact 검
사 제거
M42
DeepSeek 호출에 tools를 넘기지 않는다(웹 차단)
tools에 search 하나 넣기
M43
DeepSeek 출력의 등급·확률·승자 단어는 판정 입력
에 닿지 않는다
출력의 "confidence" 칸을 strength에
더하기
M44
반증 단계 전후로 어떤 마켓의 생존율도 올라가지 않
는다 — 올라가면 카드 금지
반증이 시나리오를 삭제할 수 있게 하기
M45
DeepSeek 장애 시 v5 원래 경로로 판정이 끝까지 돈
다( deepseek_unavailable )
장애 시 예외를 위로 던지기
M46
필수형 조건이 걸리는데 반증이 impossible이라 해
도 코드 템플릿이 들어간다( redteam_overruled )
impossible을 그대로 받기
AnalystBot v5-A 부록 — DeepSeek 가설·시나리오·반증 단계
Page 6 of 8


---

## PDF Page 7

3. 단계 3+4 켬 — 반증까지 넣고 다시 돈다.
4. 세 결과를 아래 지표로 나란히 보고한다.
켜는 기준 — 결과 갈래 포함률이 기준선보다 오르고, 오답 재현 수가 줄거나 같고, 등급 마켓 수가 기준선
의 70% 이상이면 단계 3을 운영에 켠다. 단계 4는 거짓 확신 수가 줄 때만 켠다. 기준을 못 넘으면 결과를
questions/ 에 적고 사용자 판단을 받는다.
운영 뒤 — 원장 30건마다 같은 지표를 다시 뽑아 카드 하단 통계로 보고한다. DeepSeek 비용이 하루 예
산의 절반을 넘으면 단계 4를 생존 0.85 이상 마켓에만 돌리도록 좁힌다.
7. v5 본문에서 바뀌는 조항
v5 문서를 고치지 않고, 아래 표를 v5 위에 얹어 읽는다. Claude Code는 구현할 때 이 표의 "바뀐 뒤"를
따른다.
지표
뜻
좋아지는 방향
필수형 누락
률
코드가 템플릿으로 보강해야 했던 시나리오 비율
( added_by:code )
↓
결과 갈래 포
함률
실제 결과 스코어가 세트의 어느 시나리오
outcomes에 들어 있었나
↑
거짓 확신 수
생존 0.85+ 마켓이 실제로 진 횟수
↓
오답 재현 수
페이블 오답 경기에서 같은 결론을 낸 횟수
↓(0이 목표)
등급 마켓 수
0.8 이상으로 낸 마켓 수
너무 줄면 경고 — 픽이 없는 분석은
쓸모없다
경기당 비용
Solar+DeepSeek USD
하루 $3 안
폐기율
M41로 버려진 DeepSeek 시나리오 비율
20% 넘으면 프롬프트 재조정
v5 조항
지금
바뀐 뒤
§0 규칙 변경
유료 예외 Solar 하나
Solar + DeepSeek, 비용 합산
§1 역할 경계
표
가설·시나리오 초안 = 에이전트
(Solar)
가설·시나리오 = DeepSeek(단계 3), 반증 =
DeepSeek(단계 4)
§2 예산 가드
Solar만
하루 $3·월 $40은 두 API 합산, DeepSeek 경기
당 상한은 부록 §2
§3-3 프롬프트
7·8번
Solar가 가설·시나리오 작성
Solar는 선택적 초안만, 필수는 아님
AnalystBot v5-A 부록 — DeepSeek 가설·시나리오·반증 단계
Page 7 of 8


---

## PDF Page 8

이 부록 자체 — docs/fable/inbox/2026-10-04_v5A_deepseek.md 로 v5 문서 옆에 넣는다. 커밋
메시지·테스트 이름에 "v5-A §n"과 M번호를 적는다.
v5 조항
지금
바뀐 뒤
§3-5
에이전트 초안 → 코드 재생성
DeepSeek 초안 → M41 검사 → 코드 필수형 보강
§3-6 출력 스키
마
hypotheses·scenarios 필수
Solar 출력에서는 선택(optional)
§6-2 자동 보
강
에이전트 초안 기준
DeepSeek 초안 기준, 보강 발생 시
deepseek_missed_required 기록
§6 순서
보강 → 대입 → 상한 → pick
보강 → 1차 대입 → 반증(부록 §4) → 재대입 → 상
한 → pick
§8-6 사유 코
드
—
추가: unknown_var, new_fact,
redteam_skipped, redteam_overruled,
deepseek_unavailable,
deepseek_missed_required
§9-4 신규 계
약
M26~M40
+ M41~M46
§10-4 게이트
1~8
게이트 5 뒤에 "5-A 부록 §6 측정 → DeepSeek
켬 여부" 추가
§11-3 결정 기
본값
유료 API Solar만, 모델 solar-
pro4
유료 API Solar+DeepSeek, DeepSeek 모델은
공식 문서 확인 후 저가 추론 모델
AnalystBot v5-A 부록 — DeepSeek 가설·시나리오·반증 단계
Page 8 of 8
