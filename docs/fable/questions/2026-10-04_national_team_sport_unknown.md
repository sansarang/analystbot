# 갈림길 — **대표팀 경기는 종목을 잃는다** (2026-10-04) ⬛ 답 기다림

실측: 북마케도니아 vs 스코틀랜드 (UEFA Nations League B Grp. 1 · 10-04 03:45 KST).

## 이름 문제는 끝났다 — 이번에 무너진 자리는 **다르다**

```
① 북마케도니아 → team:000151 · 스코틀랜드 → team:000266   ✅ 둘 다 풀렸다
   경기도 찾았다: fotmob-5181780 · North Macedonia(홈) vs Scotland(원정)
② 🔴 **리그 미상** — 대표팀은 리그가 없다(대회만 있다)
③ 그래서 sport = '' · langs = ['en'] 고정
```

## 🔴 무엇이 됐나 — 세어서 적는다

```
queries:69 → hits:1302 → kept_identity:187 → kept_date:25 → facts:25 → typed:20 → variables:3
                         ^^^^^^^^^^^^^^^^^ 🔴 1302건 중 **1115건을 버렸다**(86%)
```

⚠️ 버린 것은 **옳다**. 🔴 문제는 **애초에 안 받아야 했다**는 것이다.
`North Macedonia`·`Scotland` 는 **나라 이름**이다 — 질의에 종목이 없으면 검색엔진이
나라 기사를 준다. 클럽(`Kashiwa Reysol`)은 이름 자체가 축구를 뜻하지만 대표팀은 아니다.

**봇이 실제로 연 것 76건**(표본):

| 무엇 | 왜 왔나 |
|---|---|
| `rottentomatoes.com/tv/succession/s02/e08/cast-and-crew` ×8 | 🔴 질의 `Scotland lineup` → **드라마 출연진** |
| `rugby.com.au/wallabies/…` · `florugby.com/…scotland-vs-england-lineups` ×15 | 🔴 스코틀랜드는 **럭비 국가**다 |
| `skysports.com/rugby-league/australia-vs-scotland` | 같다 |
| `en.wikipedia.org/wiki/{North_Macedonia, Economy_of_, Flag_of_, Macedonia_naming_dispute}` | 나라 기사 — 본문 **109,714자 · 180,470자** |
| `5sim.net/countries/northmacedonia` · `smsfast.com/country/…` | SMS 번호 판매 |
| `telfa.law/juridictions/north-macedonia` | 법률 사무소 |
| `tripadvisor.com/…Skopje` · `reuters.com/…nightclub-blaze-killed-59` | 나라 기사 |

## 🔴 그 쓰레기가 **예산을 먹는다** — 둘은 같은 뿌리다

```
LLM 시간 소진   74회   "🔴 LLM 시간 소진 — L3 를 부르지 않았다(60/60초)"
본문 예산소진   55회   "본문 예산소진 (41건 중 일부만 열었다)"
각도 예산 소진  12회
```

⚠️ 그래서 **진짜 프리뷰 기사에 닿을 때는 예산이 없다** — 로그가 그것을 그대로 적는다:

```
sportsmole.co.uk/…/n-macedonia-vs-scotland-prediction-team-news-lineups_606086.html
  → 🔴 LLM 시간 소진 — L2 를 부르지 않았다(60/60초)
dailyrecord.co.uk/…/scotland-north-macedonia-nations-league-37726524
  → 🔴 LLM 시간 소진 — L2 를 부르지 않았다(60/60초)
```

🔴 **이름 문제가 아니다. 종목을 몰라서 질의가 넓고, 넓은 질의가 예산을 먹는다.**

## 🔴🔴 고칠 길 — **저장소에 이미 적혀 있다**

⚠️ 지어낼 것이 **없다.** 어댑터 일곱이 **스스로 종목을 선언**하고 있다:

```
app/collect/fotmob.py:63   SPORT = "soccer"      ← 이 경기를 저장한 어댑터
app/collect/fdorg.py:35    SPORT = "soccer"
app/collect/kleague.py:32  SPORT = "soccer"
app/collect/kbo.py:71      SPORT = "baseball"
app/collect/npb.py:36      SPORT = "baseball"
app/collect/mlb.py:27      SPORT = "baseball"
app/collect/nhl.py:26      SPORT = "hockey"
```

그리고 그 행이 **어느 어댑터에서 왔는지** `ext_id` 가 말한다 — `fotmob-5181780`.
🔴 즉 **이 경기의 종목은 이미 알 수 있었다.** 사다리 ②가 *"리그가 명부에 없다"* 로
내려갈 때 **행의 출처를 묻지 않는다.**

### 보기 — 사용자가 고른다

| | 무엇을 한다 | 무엇이 는다 | 무엇이 걸린다 |
|---|---|---|---|
| **A** | 사다리 ②에 한 줄 더: 리그가 명부에 없으면 **`ext_id` 접두어 → 어댑터 → `SPORT`** 를 읽는다. 리그는 여전히 미상, **종목만** 채운다 | 종목 게이트가 산다(럭비·드라마 질의가 안 나간다) · `asks()` 가 야구 질문을 막는다 | 언어는 여전히 `en` 하나다 |
| **B** | A + **질의에 종목 낱말을 붙인다**(`football`·`野球`…). 원본은 `search_words.yaml` 에 `sport:` 한 묶음 | 🔴 86% 버림이 줄어든다 — 예산이 진짜 기사에 간다 | 낱말표에 다섯 줄을 더 적는다(번역이라 지어냄 아님) |
| **C** | B + 대표팀의 **현지 언어**를 CLDR 나라→언어로 채운다(`mk`·`en`) | 현지 매체가 손에 들어온다 · 카탈로그 템플릿 6종이 건너뜀을 멈춘다 | ⚠️ 나라→언어는 **일대다**다(스위스 4개) — 고르면 추측이 된다 |
| **D** | 아무것도 안 한다 | — | 🔴 대표팀 경기는 늘 변수 3개로 끝난다 |

🔴 **A 는 추측이 0이다** — 저장소에 적힌 선언을 읽는 것뿐이다.
⚠️ **C 는 추측이 섞인다** — 나라마다 공용어가 여럿이다. 쓰려면 `nations.yaml` 에
   **손으로 적은 언어 줄**이 필요하다(사본이 아니라 새 사실이다).

## 이번 카드는 어떻게 나왔나 (참고)

```
■ 8 결론   소액: [토탈 3.5] 언더 3.5 (생존 1.0) — 죽는 시나리오 없다
■ 9 방향   방향 없음 — 승패 5줄 중 이름 0줄
■ 10 방아쇠 ①②③ 셋 다 "빠지면 자료 부족 — 전부 철회"
```

⚠️ 변수가 **3개뿐**이라 하나만 거짓이면 전부 무너진다 — §7 R5 가 정직하게 그렇게 적었다.
🔴 그래도 이것이 *"정상 작동"* 은 아니다. 변수 3개는 **자료를 못 읽은 결과**다.

| 날짜 | 무엇 | 누가 | 답 |
|---|---|---|---|
| 2026-10-04 | 대표팀 경기의 종목·언어를 어떻게 아나 | **사용자** | ⬛ **A / B / C / D** |
