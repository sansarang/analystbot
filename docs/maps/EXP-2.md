# EXP-2 영향 지도 — T-3h·T-60 자동 내보내기

## 1. 무엇이 틀렸나 (재현 원문)

```
$ rg -n "for_fable" app/ tools/ config/
app/export/for_fable.py:3:    python -m app.export.for_fable --league mlb --date 2026-09-19
   → 참조가 자기 머리말 한 줄뿐. 부르는 곳이 0건이다.

$ rg -n "export" app/scheduler.py
   (출력 없음)

$ PYTHONPATH=. uv run pytest tests/export/test_exp2_stage.py -q -x
AssertionError: STAGES 목록이 없다                    exit=1
```

내보내기는 **사람이 손으로 치는 커맨드**다. "오늘처럼" 운영은 매일 T-3h 와 T-60
두 번을 요구하는데 그 둘을 부르는 코드가 없다.

## 2. 어디를 고치나 (파일:라인)

| 파일 | 무엇 |
|---|---|
| `app/export/for_fable.py:39` | `OUT_DIR` 상수 → `resolve_out_dir()` (볼륨 우선) |
| `app/export/for_fable.py:113` | `out_path(...)` 에 `stage` 인자 · `_lineup` 접미사 |
| `app/export/for_fable.py:863` | `main()` 에 `--stage` 인자 |
| `app/scheduler.py` `_job_specs()` | 잡 2개 등록 |
| `app/scheduler.py` (새 함수 2개) | `export_t3h_job` · `export_lineup_job` |

## 3. 영향 지도 5문

**① 이 값을 읽는 곳이 또 있나.**
`OUT_DIR` 은 `for_fable.py` 안에서만 쓰인다(`rg "OUT_DIR"` → 39·115행 두 곳).
`out_path` 는 `write()` 한 곳에서만 불린다. 밖에서 부르는 코드는 0건이다 —
내보내기 참조가 자기 머리말뿐이라는 재현 원문이 그 증거다.

**② 이 함수의 반환 모양이 바뀌나.**
바뀌지 않는다. `out_path` 는 여전히 `pathlib.Path` 를 돌려주고, `stage` 는
**기본값 `"t3h"` 를 가진 키워드 인자**다. 기존 호출부(`write()`)는 그대로 돈다.
`resolve_out_dir()` 는 새 함수이고 `OUT_DIR` 은 모듈 임포트 시 그것으로 초기화된다
— 테스트가 `monkeypatch.setattr(F, "OUT_DIR", ...)` 로 갈아끼우는 길이 유지된다.

**③ 스케줄러 잡을 늘리면 무엇이 같이 도나.**
`_job_specs()` 의 모든 잡은 `_instrument()` 래퍼를 통과한다 — 실행 기록과 실패
알림이 자동으로 붙는다. 잡 2개가 늘면 **워치독이 보는 잡 수가 늘어난다.**
주기는 10분·5분이고 각 실행은 DB 읽기뿐이라(내보내기는 읽기 전용) 부하는
`flow_shadow_15m`(36경기 전수 처리)보다 작다.
⚠️ 두 잡은 **발송 경로를 타지 않는다** — `n13_send` 도 `_send_card` 도 부르지 않는다.
   규율 9(발송 중단 유지)를 깨지 않는다.

**④ 출력 위치를 바꾸면 무엇이 깨지나.**
로컬에서는 아무것도 바뀌지 않는다(`RAILWAY_VOLUME_MOUNT_PATH` 가 없으면 종전
다운로드 폴더). 컨테이너에서는 볼륨 경로로 간다 — 볼륨이 없으면 지금처럼
`/tmp` 아래에 쓰고 **재배포 때 사라진다**(→ FORKS F-18). 그래서 볼륨 생성이
이 수정 단위의 전제다. 볼륨이 붙기 전에는 잡이 돌아도 백업이 아니다.

**⑤ 실패하면 무엇이 조용히 0이 되나.**
슬레이트가 비면 내보내기는 `경기 0건` 경고를 찍고 빈 문서를 쓴다(`main()` 기존 동작).
잡이 죽으면 `_instrument` 가 실패 알림을 보낸다. **조용한 0 은
"잡은 돌았는데 파일이 없는" 경우**인데, 그것은 Phase 5-2 가 만들 `W-EXPORT-MISSING`
경보가 잡을 자리다. 이 단위에서는 잡 로그에 산출 경로·바이트 수를 남기는 것으로
멈춘다(내보내기가 이미 `logger.info("내보냄 %s · %d경기 · %d바이트")` 를 찍는다).

## 4. 안 하는 것

- 새 수집기 0개. 내보내기는 읽기 전용이고 DB·Redis 만 읽는다.
- 발송 스위치를 건드리지 않는다.
- 로컬 맥에 자동으로 파일을 밀어넣지 않는다 — 서버가 주체이고, 로컬은 받아간다.
