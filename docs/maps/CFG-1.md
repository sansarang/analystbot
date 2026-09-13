# CFG-1 — 설정 파일이 배포 이미지에 안 올라간다

## 왜 (첫 사이클 실측 2026-09-13 22:0x)

배포 직후 서버에서 확인했더니:
```
[scout] 설정 없음: config/search_terms.yaml
[scout] 설정 없음: config/sources.yaml
scout 리그 0 · 소스 {'tier1_official': 0, 'tier2_local': 0, ...}
$ ls /app/config   → No such file or directory
$ ls /app          → app data db mock_data pyproject.toml tools uv.lock
```
`git ls-files config/` 는 12개를 추적한다. **git 은 아는데 이미지에 없다** —
`Dockerfile` 이 `app/`·`db/`·`mock_data/`·`tools/` 만 복사한다.

🔴 이것이 조용한 결함의 전형이다. 모듈은 **정상 동작한다** — 빈 설정으로.
   검색어 0개면 딥서치가 질의를 못 만들고, 티어가 없으면 사전값이 전부
   중앙값이다. 둘 다 **예외 없이** 그렇게 된다. 로그 한 줄이 유일한 신호였다.

## ① 이 상태를 읽는 곳 **전부**

```
$ grep -rn 'Path("config")\|CONFIG_DIR\|TIER_DIR' app/
app/engine/prior.py          TIER_DIR = Path("config/tiers")
app/engine/scout_config.py   CONFIG_DIR = Path("config")
```
둘 다 오늘 만든 것이고, 둘 다 **없으면 빈 값**으로 간다(예외를 안 낸다).

## ② 만드는/바꾸는 상태

| 상태 | 성격 |
|---|---|
| `Dockerfile` 에 `COPY config/ ./config/` | 한 줄 |

⚠️ 코드는 안 바꾼다. 빈 설정으로 도는 것 자체는 **의도한 폴백**이다
   (티어 미기입 → 중앙값 + `prior_src="tier:미기입"`).

## ③ 리그·종목·경로 분기

분기가 없다. 이미지에 파일이 있느냐 없느냐이고 종목·리그와 무관하다.
로컬 테스트는 저장소 루트에서 돌아 항상 파일을 보므로 **로컬에서는 영원히
재현되지 않는다** — 그래서 계약이 `Dockerfile` 자체를 본다.

## ④ 조용히 실패하는가

| 위험 | 대응 |
|---|---|
| 🔴 **또 다른 디렉토리가 빠진다** | 계약이 `Path(...)` 로 읽는 최상위 디렉토리를 전수로 찾아 `Dockerfile` COPY 와 대조한다 — 목록을 손으로 적지 않는다 |
| 설정이 비었는데 정상으로 보인다 | 이미 로그가 있다(`[scout] 설정 없음`). 배포 후 실측으로 확인 |

⚠️ **아직 못 잰 것**: 배포 후 서버에서 실제로 채워지는지. 배포 직후 잰다.

## ⑤ 사본

복사 목록을 테스트에 손으로 적지 않는다 — 소스에서 읽는 경로를 찾아 대조한다.
