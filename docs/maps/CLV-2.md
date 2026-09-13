# CLV-2 — 트랜잭션 안에서 새 커넥션을 잡아 교착했다

## 왜

실측 2026-09-13 (운영): `record_analysis` 호출이 **400초 타임아웃**(EXIT=124).

```python
# pick_ledger.py:258  바깥
async with pool.acquire() as conn:
    async with conn.transaction():
        ...
        await record_clv(pool, game_id=..., at="verdict")   # 319행
                         ^^^^  → 565행에서 **새 커넥션**을 얻어
                                 같은 pick_ledger 행을 UPDATE 하려 한다
```
바깥 트랜잭션이 그 행을 잠근 상태라 **영원히 기다린다.** CLV-1 배포 뒤
`record_analysis` 를 타는 모든 경로가 멈출 수 있었다.

⚠️ 앞서 소급 기록이 성공했던 것은 `record_clv` 를 **바깥에서 직접** 불러
   중첩이 없었기 때문이다 — 그래서 배포 시점에 드러나지 않았다.

## ① 이 함수/상태를 읽는 곳 **전부**
```
record_clv  ← record_analysis(319, 트랜잭션 **안**) · grade_pending(386, 밖)
```

## ② 만드는/바꾸는 상태

| 상태 | 성격 |
|---|---|
| `record_clv(conn_or_pool, …)` | 커넥션을 받으면 **그대로 쓴다** |
| `record_analysis` 의 호출 | `pool` → `conn` |

🔴 `grade_pending` 은 트랜잭션 밖이라 `pool` 을 그대로 넘겨도 된다 — 두 호출
   방식을 **한 함수가 모두 받는다**(호출부마다 분기하면 그것이 다음 사본이다).

## ③ 분기
없음. 인자가 `acquire` 를 가지면 풀, 없으면 커넥션이다.

## ④ 조용히 실패하는가
| 위험 | 대응 |
|---|---|
| 🔴 **또 중첩한다** | `record_clv(conn` 배선 계약 |
| 풀을 넘기는 경로가 깨진다 | 풀 경로 계약 유지(기존 테스트) |
| 교착이 조용히 재발 | 커넥션 전달 시 `acquire` 호출이 0회인지 계약 |

⚠️ 못 잰 것: 운영에서 이 교착이 실제로 몇 번 걸렸는가. 배포~수정 사이 약 20분이다.

## ⑤ 사본
- 호출부마다 다른 함수를 만들지 않는다. 한 함수가 둘을 받는다.
