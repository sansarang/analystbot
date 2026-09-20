# SELO-1 영향 지도 — 축구 ① 사전값이 구조적으로 없었다

## 0. 재현 (실측 2026-09-20 · STEP 0-e)

```
축구 7리그 전부   ① 사전값 = null — elo 캐시 키 없음
Redis elo:*      ['elo:kbo:…','elo:mlb:…','elo:npb:…']   ← 축구 키 0개
오늘 슬레이트      {"games":32, "stopped":{"n03_freeze":21, …}}   ← 21 중 18이 축구
soccer_elo 표    **표 없음** · /app/data/elo **디렉토리 없음**
```

원인은 `bridge.ELO_SPORTS = ("mlb","kbo","npb")`. 주석이 뺀 이유를 적어 뒀다 —
`team_elo.refresh` 가 `WHERE sport=$1` 로 긁는데 축구 캐시 키는 **리그 코드**라
종목으로 긁으면 리그 간 비교가 된다.

## 1. 갈림길 — 축구 레이팅을 무엇으로 만드나 (실측으로 닫았다)

| 안 | 실측 | 판정 |
|---|---|---|
| (a) 우리 `games` 로 자체 Elo | 축구 종료 경기 **131건** · 팀당 **2.5~5.1경기** (야구 35.5/70.8/34.8) | 🔴 **기각** — `tools/fit_elo.py` 가 야구(팀당 ~12)에서도 "진폭이 없다"고 적은 수준의 1/3 |
| (b) ClubElo API (지시문 STEP 10 지정) | `api.clubelo.com/{날짜}` · `/{클럽}` **전부 502** · `/Fixtures` → `"Fixtures API deactivated"` · https 는 ConnectTimeout | 🔴 **기각** — 소스가 죽어 있다 |
| (c) football-data.co.uk (`app/models/soccer_elo.py`) | 서버에서 `refresh()` **성공** — 10리그(E0·E1·D1·SP1·I1·F1·N1·P1·DNK·JPN) · CSV 200 OK | ✅ **채택** — 유일하게 살아 있고 표본이 충분 |

🔴 (c)를 막던 것은 Elo 가 아니라 **이름 불일치**였다: elo 는 `Arsenal`·
`Ath Bilbao`, 우리는 `Arsenal FC`·`Athletic Club` — **144팀 중 2개만 일치.**
딥서치 결과 football-data.co.uk 는 *"club names get copied as is including
typos"* 라 **공식 대조표가 없다**. 그래서 표를 만들어야 한다.

기록 → [FORKS F-21](../FORKS.md)

## 2. 이름 대조 규칙 (퍼지 유사도 아님 · 전부 검증 가능)

```
R1 같은 리그 안에서만 짝짓는다.
R2 토큰 완전 일치. 접두 축약은 **짧은 토큰이 5자 이하**일 때만(Man·Ath·Nott).
R3 상호 유일할 때만 확정. 모호하면 **비운다**.
E  규칙으로 안 되는 것은 명시 표에만 둔다 — 항목마다 하나의 사실이다.
```

⚠️ 접두 규칙을 느슨하게 뒀을 때 **오매칭이 났다**: `Rayo Vallecano` →
`Valladolid`(공통 접두 `vall`). CLAUDE.md 가 경고한 자리(AC밀란 오매칭)라
5자 상한으로 조였고, Vallecano 는 명시 표로 옮겼다.

**결과 106/150 = 70.7%.** 미매칭은 대부분 **2부 팀**(Coventry·Hull·Málaga·
Deportivo·Racing Santander·Paderborn·Elversberg·Hamburger SV — 컵/승격으로
슬레이트에 들어온 팀)이고, K리그1·ACL 은 **elo 리그 자체가 없다.**

| 리그 | 확정 |
|---|---|
| 덴마크 수페르리가 | 11/11 (100%) |
| EPL | 22/24 (92%) |
| 라리가 | 22/25 (88%) |
| 세리에A | 19/20 (95%) |
| J1 리그 | 17/20 (85%) |
| 분데스리가 | 15/18 (83%) |
| K리그1 · ACL엘리트 | 0 — **사전값없음 경로**(STEP 1-e) |

## 3. 영향 지도 5문

**① 어디를 고치나.**

| 파일 | 무엇 |
|---|---|
| `config/elo_names.yaml` (신규) | 리그별 대조표. **숫자가 아니라 이름 사실**이다 |
| `app/models/soccer_elo.py` | `ratings_for_league()` · `publish_ratings()` 추가 |
| `app/flow/bridge.py` | `ensure_elo` 가 축구 리그도 보장 |

**② 어디에 싣나.** 야구와 **같은 자리** — Redis `elo:{리그}:{날짜}`
(`team_elo.CACHE_KEY`, TTL 26h). `n01_prior._code()` 가 축구에서 리그 코드를
쓰고 3-way 분기도 이미 있다(`draw_prior`). **읽는 쪽을 고칠 필요가 없다.**

**③ 새 숫자를 만드나.** 만들지 않는다. Elo 파라미터는 `soccer_elo` 가 이미
피팅한 값이고, 무승부 질량은 기존 `draw_prior` 다.

**④ 무엇이 깨질 수 있나.**
🔴 **오매칭이 최대 위험이다** — 다른 팀의 레이팅을 붙이면 ③ 게이트가 조용히
오분류한다. 그래서 (i) 규칙을 5자로 조이고 (ii) 계약 테스트가 *한 elo 이름에
다른 팀이 붙는 것*을 막고 (iii) 미매칭은 **비운다**(리그 평균으로 메우지 않는다 —
`n01_prior` 머리말의 U3 리즈 사례).
⚠️ `n03_freeze` 18건이 줄어 ⑤ 수집이 **새로 도는 경기가 는다** → 검색 예산이
더 빨리 소진된다. STEP 1-a 가 그것을 고칠 자리이고, 여기서는 건드리지 않는다.

**⑤ 틀렸을 때 알려줄 테스트.**
`tests/test_selo1_soccer_prior.py` 5건 — 대조표 존재 · **한 elo 이름에 다른
팀 금지** · `ensure_elo` 가 축구를 본다 · 싣는 함수 존재 · **미매칭을 지어내지
않는다**.

## 4. 하지 않은 것 (등록만)

- **SELO-1-b** `games` 표에 같은 팀이 **두 이름으로** 있다(`Aston Villa` /
  `Aston Villa FC`, `Manchester City` / `Manchester City FC`, `Alavés` /
  `Deportivo Alavés`). 대조표가 둘 다 같은 elo 이름에 붙여 지금은 무해하지만,
  **티어·폼·원장 집계가 갈라진다.** 별건이다.
- **SELO-1-c** `soccer_elo` 아티팩트가 `/app/data/elo`(휘발)에 쓰인다. 볼륨은
  `/data` 다. 지금은 Redis 에 싣고 끝나므로 아티팩트 영속은 불필요하지만,
  백테스트를 돌리려면 옮겨야 한다.
- **STEP 10 의 AUC 채택 규칙**은 이 단위 뒤에 따로 잰다 — 여기서는 **배선**만 한다.
