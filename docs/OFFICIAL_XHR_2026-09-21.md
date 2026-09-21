# 1b-2 — 경로 재탐색 · 화면 뒤 JSON 주소

사용자 지시 2026-09-21: "응 해봐" (1번 경로 재탐색 → 이어서 2번 XHR)

실행 2026-09-21 18:4x~19:1x KST · **헤드리스 0회**

---

## 1. 경로 재탐색 — 실패

| 리그 | 고친 주소 | 결과 |
|---|---|---|
| 세리에A | `legaseriea.it/en/…` → `en.legaseriea.it/` | 여전히 **307** · 본문 **33자** |
| 리그앙 | `www.ligue1.com` → `ligue1.com` | 200 이지만 본문 **444자** · 주머니에 값 없음 |

🔴 **경로 문제가 아니었다.** 둘 다 EPL·UEFA 와 같은 JS 렌더 SPA 다.

---

## 2. 🔴 화면 뒤 JSON 주소는 HTML 에 적혀 있었다

스포츠나비에서 못 찾았던 그 단계인데, 이번엔 **HTML 안에 주소가 있었다**:

| 리그 | 발견한 호스트 | 언급 수 |
|---|---|---|
| EPL | `api.premierleague.com` | 3 |
| UEFA | `fsp-data-cards-service.uefa.com` | 1 |
| J리그 | `data.j-league.or.jp` · `datastadium.co.jp` | 4 · 6 |
| 세리에A | `api-sdp.legaseriea.it` · `serie-a-api-prod.livelikeapp.com` | 각 1 |
| 리그앙 · 덴마크 · AFC | **없음** | — |

---

## 3. 🟢 EPL 이 열렸다 — 완전히

```
GET api.premierleague.com/football/fixtures?comps=1&pageSize=3
    → 200 · 4,412B · numEntries 99,822

GET api.premierleague.com/football/fixtures/128967
    → 200 · 28,657B
```

내용(실측):
```
teamLists[0]  formation "4-2-3-1" · lineup **11명** · substitutes **9명**
  #22 David Affengruber (D) · #24 Josh King (M) · #33 Antonee Robinson (D)
ground   {"name":"Craven Cottage","city":"London","id":9521}
kickoff  "Sun 20 Sep 2026, 16:30 BST"
```

🟢 **확정 XI · 교체 · 포메이션 · 경기장 · 킥오프를 전부 준다.** 키 불필요.

⚠️ `api.premierleague.com/robots.txt` 는 **404** 다 → `access_basis` 는
   **판단불가**이지 허용이 아니다. 약관은 아직 안 읽었다.
   근거 URL: (없음 — 공식 문서를 못 찾았다)

---

## 4. 나머지는 안 됐다

| 리그 | 시도 | 결과 |
|---|---|---|
| J리그 | `data.j-league.or.jp/SFMS02/` | 200 이나 본문 1,503자 · **背番号 0회** → 라인업 아님 |
| UEFA | `fsp-data-cards-service.uefa.com/*` | 301 · 404 — 경로를 못 찾았다 |
| 세리에A | `api-sdp.legaseriea.it/stats-lens/api/v1/matches` | **404** |
| 리그앙·덴마크·AFC | — | HTML 에 API 주소가 **없다** |

⚠️ 여기서 멈췄다. 더 파면 **경로 추측**이 되고, 그건 측정이 아니다.
   남은 길은 (a) 공식 API 문서 찾기 (b) 헤드리스로 XHR 관찰 — 후자는
   "헤드리스를 기본 경로로 쓰지 않는다"에 걸린다.

---

## 5. 🔴 내 감사 방법의 구멍 — 고쳐 적는다

`fsp-data-cards-service.uefa.com/robots.txt` 가 **HTML 을 200 으로** 돌려줬다.
규칙 줄이 하나도 없으니 내 파서가 "빈 robots = 허용"으로 답했다.

⚠️ **그건 "파일 없음"과 같게 봐야 한다.** 재감사 표에서 이런 행이 또 있는지
   확인해야 한다 → **D45** 로 등록.

---

## 6. 지금까지의 점수

| 리그 | 확정 XI 대체 | 경로 |
|---|---|---|
| **라리가** | 🟢 **된다** | `laliga.com/en-GB/match/{slug}` 의 `__NEXT_DATA__` |
| **EPL** | 🟢 **된다** | `api.premierleague.com/football/fixtures/{id}` |
| 세리에A · 리그앙 · 분데스 | ❌ | — |
| J리그 · 덴마크 · AFC · UEFA | ❌ | — |
| **K리그1** | ❌ | **여전히 0** |

**2/9.** (1b-1 에서 1/9 였다)

⚠️ 5대 리그 중 **둘**이 됐다. 그래도 **K리그1·J리그**가 비는 것은 그대로다 —
   우리 슬레이트에서 가장 자주 도는 리그들이다.
