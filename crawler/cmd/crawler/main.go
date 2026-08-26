// AnalystBot 크롤러 — LLM 0회로 경기력 재료를 모으고 **변화를 감지**한다.
//
// 실행:
//
//	crawler -sport kbo -date 2026-08-26     # 1회
//	crawler -interval 10m                   # 전 종목 주기 실행 (Railway)
package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"os"
	"time"

	"analystbot/crawler/internal/diff"
	"analystbot/crawler/internal/gate"
	"analystbot/crawler/internal/source"
	"analystbot/crawler/internal/store"
)

type fetcher func(context.Context, string) (diff.Snapshot, error)

var fetchers = map[string]fetcher{
	"kbo": source.FetchKBO,
	"npb": source.FetchNPB,
}

func main() {
	sport := flag.String("sport", "", "kbo | npb (비우면 전부)")
	date := flag.String("date", "", "YYYY-MM-DD (비우면 KST 오늘)")
	interval := flag.Duration("interval", 0, "주기 실행 간격 (0이면 1회)")
	flag.Parse()

	redisURL := os.Getenv("REDIS_URL")
	if redisURL == "" {
		redisURL = "redis://localhost:6379"
	}
	st, err := store.New(redisURL)
	if err != nil {
		log.Fatalf("redis: %v", err)
	}
	defer st.Close()

	run := func() {
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
		defer cancel()
		for name, fn := range fetchers {
			if *sport != "" && *sport != name {
				continue
			}
			if err := once(ctx, st, name, fn, *date); err != nil {
				// 한 종목 실패가 다른 종목을 막지 않는다
				log.Printf("[%s] 실패: %v", name, err)
			}
		}
	}

	run()
	if *interval <= 0 {
		return
	}
	tick := time.NewTicker(*interval)
	defer tick.Stop()
	for range tick.C {
		run()
	}
}

func once(ctx context.Context, st *store.Store, sport string, fn fetcher, date string) error {
	kst := time.FixedZone("KST", 9*3600)
	now := time.Now().In(kst)
	if date == "" {
		date = now.Format("2006-01-02")
	}
	raw, err := fn(ctx, date)
	if err != nil {
		return err
	}
	if len(raw) == 0 {
		// ⚠️ 조용한 0건이 가장 위험하다 — 구조가 바뀌어도 아무도 모른다.
		log.Printf("[%s] %s 경기 0건 — 소스 구조 변경 가능성", sport, date)
		return nil
	}
	// 게이트 ①② — **Redis에 넣기 전에** 거른다. 날것을 넣고 파이썬이
	// 뒷수습하면 쓰레기가 이미 카드·λ까지 흘러간 뒤에야 걸린다.
	snap, drops := gate.Apply(raw)
	for _, d := range drops {
		// 조용한 폐기 금지 — 무엇을 왜 버렸는지 반드시 보이게 한다.
		log.Printf("[%s] 🚫 %s", sport, d)
	}
	if n := countFields(raw); n > 0 && len(drops)*2 > n {
		// 반대 방향 위험: 게이트가 정상 데이터를 대량으로 버리고 있을 수 있다.
		// 소스 구조가 바뀌었을 때 이 경보가 먼저 울린다.
		log.Printf("[%s] ⚠️ 수집값 %d개 중 %d개 폐기 — 게이트 과잉이거나 소스 구조 변경",
			sport, n, len(drops))
	}
	prev, err := st.Latest(ctx, sport, date)
	if err != nil {
		return err
	}
	changes := diff.Compare(prev, snap)
	if err := st.Save(ctx, sport, date, snap, changes, now); err != nil {
		return err
	}
	log.Printf("[%s] %s — %d경기 수집, 값 %d개(폐기 %d), 변화 %d건",
		sport, date, len(snap), countFields(snap), len(drops), len(changes))
	for _, c := range diff.Notable(changes) {
		fmt.Printf("  ⚠️ %s\n", c)
	}
	return nil
}

// countFields 는 스냅샷의 값 개수다. 폐기율 계산에 쓴다 —
// "몇 경기"가 아니라 "몇 개 값"이어야 게이트 과잉을 볼 수 있다.
func countFields(s diff.Snapshot) int {
	n := 0
	for _, f := range s {
		n += len(f)
	}
	return n
}
