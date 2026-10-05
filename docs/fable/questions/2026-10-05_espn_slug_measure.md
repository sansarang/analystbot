# 실측 — **ESPN 리그 슬러그** (지시서 §3-2) · 2026-10-05

지시서 §3-2:

> ESPN 어댑터가 이미 있다. ESPN 이 **콜롬비아 Primera A** 같은 리그를 슬러그로
> 제공하는지, 그 경로가 **robots 허용**인지 **실측해서 결과를 `questions/` 에
> 적는다.** 허용이면 … `config/espn_slugs.yaml` 를 두고 … 표에 없는 리그는
> 3-1·3-3 으로 간다. 이 표에 리그를 넣는 것은 **데이터 추가이지 리그 선언이
> 아니다**(`leagues.yaml` 불변).

## 받아서 확인했다 (추측 없음)

| 경로 | 상태 | 길이 |
|---|---|---|
| `site.api.espn.com/apis/site/v2/sports/soccer/col.1/scoreboard` | 🔴 **403** | 0자 |
| `site.api.espn.com/apis/site/v2/sports/soccer/col.1/teams` | 🔴 **실패**(0) | 0자 |
| `site.api.espn.com/apis/site/v2/sports/soccer/leagues` | 🔴 **실패**(0) | 0자 |
| `www.espn.com/soccer/league/_/name/col.1` | ✅ **200** | 128,577자 |

### robots

```
https://www.espn.com/robots.txt        200
  User-agent: * → Disallow: */admin/ · */boxscore? · */calendar/ · */cat/
                  · */conversation? · */conversations/ …
https://site.api.espn.com/robots.txt   🔴 403
```

⚠️ `www.espn.com` 의 `Disallow` 에 **리그 페이지가 없다** — `/soccer/league/`
   는 막혀 있지 않다. 🔴 `*/boxscore?` 는 막혀 있으므로 **그 길은 안 쓴다.**
🔴 `site.api.espn.com` 은 **robots 를 403 으로 준다** — 절대규칙 3(§4-7)이
   *"robots 거부 도메인은 dead 처리뿐"* 이라고 했다. ⚠️ robots 를 **못 읽으면
   그 호스트는 쓰지 않는다**(우회·UA 위장 금지).

## 🔴 그래서 표를 **만들지 않았다**

`col.1` 이라는 슬러그는 **있다**(HTML 페이지가 200 이다). 그런데:

1. **구조 자료 경로가 막혔다** — 일정·순위·결과를 주는 것은
   `site.api.espn.com` 이고 그것은 **403**이다(robots 도 403).
2. HTML 페이지(`www.espn.com/soccer/league/_/name/col.1`)는 열리지만, 그것을
   읽으려면 **새 파서**가 필요하다 — 🔴 지시서 §3-1 이 *"새 파서를 짓지
   않는다"* 고 했다.
3. ⚠️ 그러므로 `config/espn_slugs.yaml` 은 **지금 뜻이 없다** — 표에 `col.1` 을
   적어도 **받아올 경로가 없다.**

→ 콜롬비아는 **3-1(경기 페이지 자체) · 3-3(에이전트 보강)** 으로 간다.
  그것이 지시서가 *"표에 없는 리그는 3-1·3-3 으로 간다"* 라고 적은 길이다.

## ⬛ 사용자에게 물을 것 — 없다(지금은)

🔴 **갈림길이 아니다** — 지시서가 이미 길을 적었다(표에 없으면 3-1·3-3).
⚠️ 나중에 ESPN 이 그 API 를 열거나 다른 무료·무키 경로가 보이면 그때 표를
   만든다. 그 전에는 **빈 표를 만들지 않는다**(안 이어진 코드는 없는 코드보다
   나쁘다 · CLAUDE.md #2).
