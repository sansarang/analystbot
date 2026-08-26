# AnalystBot 크롤러 (Go)

## 왜 Go인가

- **동시 수집**: KBO 5 + NPB 6 경기를 goroutine으로 병렬 조회. 파이썬 봇과 분리돼
  크롤러가 죽어도 봇은 계속 응답한다.
- **LLM 0회**: 네이버·Yahoo·구단 공식은 구조화 데이터를 그냥 준다. 딥서치 쿼터를
  아끼고, 실패해도 비용이 0이다.

## 핵심 — 시각별 스냅샷

한 번만 긁으면 "지금 상태"만 안다. **변화는 못 본다.**

```
18:00  선발 임찬규
18:20  선발 최원태   ← 교체! 무슨 일이 있었나
```

이 변화가 정보다. 스냅샷을 시각별로 쌓고 diff를 만들어 판정에 넘긴다.

## 인터페이스 (Redis JSON)

Postgres에 직접 쓰지 않는다 — 스키마 결합을 피하고, 파이썬이 **검증 후에만** 반영한다.

| 키 | 내용 |
|---|---|
| `crawl:{sport}:{date}:latest` | 최신 스냅샷 |
| `crawl:{sport}:{date}:{HHMM}` | 시각별 스냅샷 (TTL 26h) |
| `crawl:{sport}:{date}:changes` | 직전 대비 변화 목록 |
| `crawl:heartbeat` | 마지막 실행 시각 (감시용) |

## 실행

```bash
go run ./cmd/crawler -sport kbo -date 2026-08-26        # 1회
go run ./cmd/crawler -sport kbo -interval 10m           # 주기 실행
```

Railway에서는 `-interval`로 상주시킨다.
