# 인계 — 의심 검증 통합본 v2 (2026-10-14 · 작업 중단 지점)

🔴🔴 **"이어서 해라" 를 받으면 이 문서의 §2 첫 줄부터 그대로 잇는다.**
정본 지시서: [docs/fable/inbox/2026-10-14i_doubt_v2.md](fable/inbox/2026-10-14i_doubt_v2.md)
(그 안의 §0~§7 과 보고 순서가 기준이다 · 공격 계층은 **폐기**다)

---

## §1 끝낸 것 (커밋돼 있다 · 스위트 1905 passed · 17 skipped)

| 무엇 | 어디 | 상태 |
|---|---|---|
| **공격 계층 제거**(§0) | `app/core/attack.py` 삭제 · `pipeline._attack_of` 삭제 · `Card.attack` 삭제 · `render._attack_line` 삭제 · `tools/attack_sixgame.py`·`attack_efficacy.py` 삭제 · 계약 `test_v28_1_attack.py` 삭제 | ✅ 끝 |
| **의심 변수 등록표**(§3-1) | `config/doubt_vars.yaml`(옛 `attack_vars.yaml` 을 옮겼다) — 변수 44개 · `시험` 칸에 (가)/(나)/(다) · `의심.유효 = [H1]` | ✅ 끝 |
| **보드 사다리**(§1-1·1-2) | `app/core/boardfeed.py` — ① 캡처(`var/board/<날짜>.yaml`) ② `football-data.co.uk/fixtures.csv`(robots 전면 허용 · 실측) ③ 배당 API(`ODDS_API_KEY` 있다 · h2h·spreads·totals) · 국내 한 줄 고르기(`main_line`·`pick_domestic`) · 쿼터 라인은 **국내 미대응** 표시 · 실패는 **경보** | ✅ 끝(④ 통로는 아직 없다) |
| 보드 배선(§7) | `pipeline` → `layers["board_feed"]`·`board_lines` → `Card.board_feed`·`board_lines` → 카드 맨 위 보드 블록(`render`) | ✅ 끝 |
| 별칭표(§1-3) | `app/core/teamname.ALIAS`(Wolves→Wolverhampton · QPR · West Brom · Man City · Nott'm Forest …) + **여자팀 가름**(`is_women` · `(W)`·Women 이 한쪽만 있으면 share 0) | ✅ 끝 |
| 사다리 실측(보고 1번 재료) | `var/accept/board_ladder.log` — 10-14 12경기: ② 5 · 실패 7 / 10-15 15경기: ② 3 · 실패 12. ⚠️ **별칭표 넣기 전** 수치다 → **다시 돌려야 한다**(아래 §2-0) | ⏳ 재실행 필요 |

### 알아 둘 실측 (다시 재지 않아도 되는 것)
- `football-data.co.uk` robots = `Disallow:`(전면 허용) · `fixtures.csv` 는 **그 주 유럽 리그**만(그날 코드 E1·E2·SC1) · 열에 `B365H/D/A` · **`AHh`**(아시안 핸디 기준선) · `B365AHH/AHA` · `B365>2.5`·`B365<2.5`.
- 과거 마감 배당 = `https://www.football-data.co.uk/mmz4281/<시즌>/<코드>.csv`(예 `2526/E1.csv` · 553줄 · 132열) — **실보드 백필의 원천**이다(§1-4).
- 배당 API 열쇠는 `.env` 의 **`ODDS_API_KEY`**(월 500 · `get_settings().the_odds_api_key` 같은 이름은 **없다**).
- 사다리 ③ 는 카드 안에서 이미 돈다 — 사바흐–슬라비아는 **피나클 22곳**을 받았고(실측) 알사드–알힐랄은 **매칭 실패**(이벤트 18건)였다.
- UCL·ACL·J1 은 ② 가 없다 → ③ 아니면 **경보**다.

---

## §2 남은 것 — **이 순서로** 잇는다

### 2-0. 사다리 실측 다시 (10분)
```bash
PYTHONPATH=. uv run python - <<'PY' > var/accept/board_ladder2.log 2>&1
# var/accept/board_ladder.log 를 만든 그 스크립트를 그대로 쓴다(그 파일 머리에 있다)
PY
```
→ 별칭표·여자팀 가름을 넣은 뒤 **출처별 성공률**을 다시 센다(보고 1번).
⚠️ ③ 를 표에 넣으려면 `market=` 에 피드를 넘겨야 한다 — 카드 안에서는 이미 넘어간다.

### 2-1. 백필 보드(§1-4) — `tools/fit_board_hist.py` (새로 만든다)
- `mmz4281/<시즌>/<코드>.csv` 를 리그별로 받아 `data/board_hist/<리그>/<시즌>.yaml` 로.
- 한 줄: `{day, home, away, 1X2(B365H/D/A), AHh, AHH, AHA, O2.5, U2.5}` · 이름은 `teamname.share` 로 우리 이름에 붙인다.
- 코드 표: E0=PL · **E1=ELC** · E2=League One · SC1=SPL · D1=BL1 · I1=SA · SP1=PD · F1=FL1 · N1=DED · P1=PPL.
- 없는 리그(MLS·J1·K1·ACLE·UCL)는 **근사 보드**(봇 확률로 양쪽 50%에 가장 가까운 0.5 단위) · 표에 **근사** 꼬리표 · 판정표는 **따로 집계**.

### 2-2. 1단 기계 점검(§2) — `app/core/machine.py` (새로 만든다)
- 입력 완전성(축0~3 · Elo · 폼 표본 · XI 확정/예상 · 결장 원천 · 감독 isCoach · 리그 오프셋 · 대회 이력 · 보드 출처/시각) · 버그 반영(①②③④ · 0-0 · 이력 기간) · 신선도.
- 판정 `정상 / 고장 / 기계 보류` → `Card.machine` + 카드 의심 블록 머리.
- **기계 보류면 확신·역배 둘 다 금지**(칠 표에서 빠진다).

### 2-3. 2단 의심 + 조건부 보정표(§3-2·3-3) — `tools/fit_doubt.py` (새로 만든다)
- 아직 **측정 안 된** 의심 변수부터: **B1 폼 표본 · A2 축0 착시 · B3 운 요소 골**(+ 가능하면 J1·E1). 방법은 체급 3구간 통제 + 95% 구간(끝난 측정은 `config/doubt_vars.yaml` 의 `시험` 칸).
- 보정표: 줄 종류(승무패 방향 · 보드 핸디 · 보드 언오버) × 봇 확률 구간(40-45·45-50·50-55·55-60·60-70·70-80·80+) × **유효 불리 의심 개수(0·1·2+)** → 칸마다 경기 수·봇 평균·실측·95% 구간·반대쪽 실측·실보드/근사.
- 칸 <100 이면 이웃 합침, 그래도 <100 이면 **보류**. 판은 `data/doubt_cal/<줄종류>.yaml`.
- 재료: `var/judge/atk_*.json`(1,470경기 · 좌표·xG·선발·골 시각 들어 있다) + 2-1 의 실보드.

### 2-4. 판정(§4) — `app/core/doubt.py` (새로 만든다)
- 의심 후 확률 = 그 칸 실측 · **확신**(1단 정상 + 문턱 이상 + 구간 하한도 문턱 근처) · **역배**(반대쪽 구간 하한 > 50% + 다른 시즌 유지) · 나머지 **보류**.
- 문턱은 **백필 곡선**으로(`tools/cut_curve.py` 를 의심 후 확률로 다시 그린다).
- 카드 의심 블록(§7) · `core/picks` 는 **확신/역배만** 받는다(지금은 문턱만 쓴다 — 그 자리를 갈아끼운다).

### 2-5. 검증(§5) · 10-14 시험(§6) · 출력(§7)
- 보정 곡선(의심 후가 원래보다 실측에 가까운가) · 확신/역배 적중률 · 보류 비율 · 시즌 교차 · 다폴 규칙(기계 보류 다리 금지).
- §6 대상: 챔피언십 6 · ACL 4 · UCL 2 · 알사드–알힐랄 — 카드 로그가 `var/accept/ch_*.log`·`ucl_*.log`·`alsadd_board2.log` 에 있다.
- 예상 확인: 울브스 = 기계 보류 · 사바흐 = 기계 보류 · 카디프 = 확신 여부 · 밀월 = 보류 여부.

---

## §3 함정 (전에 밟은 것)
1. **미배선 주차 금지** — `NOT_WIRED` 는 선언 셋뿐이다(계약이 센다). 새 모듈은 **만든 턴에 배선**한다.
2. `probmodel.home_mul(` 글자를 건드리면 계약 `test_v7_...열쇠를_본다` 가 빨개진다 — 후보 함수 이름은 `team_home` 처럼 **갈라** 쓴다.
3. `competition.py` 에 `_words` 같은 **이미 있는 이름**을 또 쓰면 조용히 덮는다(`_stage_words` 로 갈랐다).
4. 카드 글이 바뀌면 e2e 스냅샷이 빨개진다 — `V6_SNAPSHOT_UPDATE=1` 로 갱신하고 **까닭을 커밋에 적는다**.
5. 파이프라인에서 `layers["divergence"] = said_div` 와 그 대입 사이에 코드를 끼우면 계약 DV2 가 빨개진다(400자 창).
6. 돌연변이·치환 뒤에는 `find . -name __pycache__ -not -path "./.venv/*" -exec rm -rf {} +`.

## §4 지금 바로 쓰는 명령
```bash
PYTHONPATH=. uv run pytest tests -q                  # 1905 passed · 17 skipped
PYTHONPATH=. uv run python tools/slate_queue.py --comp league:ELC --hours 30        # 큐만
PYTHONPATH=. uv run python tools/slate_queue.py --comp league:ELC --hours 30 --run  # 카드+칠 표
PYTHONPATH=. uv run python tools/cut_curve.py --board-only    # 문턱 곡선(보드 줄만)
PYTHONPATH=. uv run python tools/fit_attack2.py               # 의심 변수(체급 통제)
```
보드 캡처는 `var/board/<날짜>.yaml` — `{"경기 이름": "승무패 2.15 3.25 3.40\n핸디 1.5 1.80 2.05\n언더오버 2.5 1.90 1.95"}`.
