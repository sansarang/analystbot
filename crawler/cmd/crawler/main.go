// AnalystBot 크롤러 — LLM 0회로 경기력 재료를 모으고 **변화를 감지**한다.
//
// 실행:
//
//	crawler -sport kbo -date 2026-08-26     # 1회
//	crawler -interval 60m                   # 평시 주기. 타순 창은 종목·경기 시각으로 2분
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
	"analystbot/crawler/internal/pace"
	"analystbot/crawler/internal/source"
	"analystbot/crawler/internal/store"
)

type fetcher func(context.Context, string) (diff.Snapshot, []time.Time, error)

var fetchers = map[string]fetcher{
	"kbo": source.FetchKBO,
	"npb": source.FetchNPB,
}

func main() {
	sport := flag.String("sport", "", "kbo | npb (비우면 전부)")
	date := flag.String("date", "", "YYYY-MM-DD (비우면 KST 오늘)")
	interval := flag.Duration("interval", 0, "평시 주기 (0이면 1회)")
	// 가속 간격. 창 자체는 종목·경기 starts_at으로 정한다 — KBO 18:30과
	// NPB 18:00을 한 시계로 묶지 않는다. NPB는 시작 15분 전(17:45)까지.
	fastInterval := flag.Duration("fast-interval", 2*time.Minute, "가속 구간 간격")
	// [MOV-C] 뉴스는 라인업보다 **드물게** 긁는다. 예산 계산(질의 상한 400/일):
	//   리그 3 × (24h / 20m = 72) = 216/일 → 상한 안.
	//   10분으로 하면 432/일이라 넘는다.
	newsInterval := flag.Duration("news-interval", 20*time.Minute, "뉴스 피드 간격")
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

	starts := map[string][]time.Time{}
	last := map[string]time.Time{}

	runSport := func(name string, fn fetcher) {
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
		defer cancel()
		got, err := once(ctx, st, name, fn, *date)
		last[name] = time.Now()
		if err != nil {
			log.Printf("[%s] 실패: %v", name, err)
			return
		}
		starts[name] = got
	}

	for name, fn := range fetchers {
		if *sport != "" && *sport != name {
			continue
		}
		runSport(name, fn)
	}

	// [MOV-C] 오늘 남은 경기가 있을 때만 뉴스를 긁는다 — 경기가 없으면
	// 이동을 설명할 일도 없고, 질의 예산만 태운다.
	var lastNews time.Time
	runNews := func() {
		upcoming := false
		for _, ts := range starts {
			if len(ts) > 0 {
				upcoming = true
			}
		}
		if !upcoming {
			return
		}
		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
		defer cancel()
		onceNews(ctx, st, *date)
		lastNews = time.Now()
	}
	runNews()

	if *interval <= 0 {
		return
	}
	idle := *interval
	fast := *fastInterval
	// 종목마다 간격이 다르다. 한 종목이 가속 중이면 그 종목만 2분이고,
	// 다른 종목은 평시를 유지한다.
	for {
		now := time.Now()
		sleep := idle
		for name, fn := range fetchers {
			if *sport != "" && *sport != name {
				continue
			}
			wait := pace.Wait(name, now, starts[name], idle, fast)
			due := last[name].IsZero() || now.Sub(last[name]) >= wait
			if due {
				runSport(name, fn)
				now = time.Now()
				wait = pace.Wait(name, now, starts[name], idle, fast)
			}
			if wait < sleep {
				sleep = wait
			}
			if remain := wait - now.Sub(last[name]); remain > 0 && remain < sleep {
				sleep = remain
			}
		}
		if !lastNews.IsZero() && time.Since(lastNews) >= *newsInterval {
			runNews()
		}
		if sleep < time.Second {
			sleep = time.Second
		}
		time.Sleep(sleep)
	}
}

// onceNews 는 리그 뉴스 피드를 한 바퀴 긁는다.
//
// 🔴 [MOV-C 2026-09-23] **라인업 수집과 완전히 분리한다.** 별도 종목 키
// (`news_<리그>`)에 저장하고, 실패는 그 리그만 건너뛴다. 검색이 막혀서
// 라인업 크롤까지 죽으면 안 된다 — 그쪽이 본체다.
//
// ⚠️ 게이트 ①②를 태우지 않는다. 그건 투구수·타순 검사라 기사 제목에
// 적용할 것이 없고, 태우면 정상 기사를 버릴 위험만 생긴다.
func onceNews(ctx context.Context, st *store.Store, date string) {
	feeds, err := st.NewsFeeds(ctx)
	if err != nil {
		log.Printf("[news] 피드 설정 조회 실패 — 이번 주기 생략: %v", err)
		return
	}
	if len(feeds) == 0 {
		return // 파이썬이 아직 안 실었다. 조용히 넘어간다(에러가 아니다).
	}
	kst := time.FixedZone("KST", 9*3600)
	now := time.Now().In(kst)
	for league, f := range feeds {
		snap, skipped, err := source.FetchNews(ctx, league, f)
		if err != nil {
			// ⚠️ 429·차단을 무시하지 않는다 — 건너뛰고 남긴다.
			log.Printf("[news:%s] 수집 실패 — 이번 주기 생략: %v", league, err)
			continue
		}
		if len(snap) == 0 {
			log.Printf("[news:%s] 기사 0건(버림 %d) — 질의나 구조 확인 필요",
				league, skipped)
			continue
		}
		key := source.NewsKey(league)
		prev, err := st.Latest(ctx, key, date)
		if err != nil {
			log.Printf("[news:%s] 이전 스냅샷 조회 실패: %v", league, err)
			continue
		}
		changes := diff.Compare(prev, snap)
		if err := st.Save(ctx, key, date, snap, changes, now); err != nil {
			log.Printf("[news:%s] 저장 실패: %v", league, err)
			continue
		}
		log.Printf("[news:%s] %s — 기사 %d건(버림 %d), 새 기사 %d건",
			league, date, countFields(snap), skipped, len(changes))
	}
}

func once(ctx context.Context, st *store.Store, sport string, fn fetcher, date string) ([]time.Time, error) {
	kst := time.FixedZone("KST", 9*3600)
	now := time.Now().In(kst)
	if date == "" {
		date = now.Format("2006-01-02")
	}
	raw, starts, err := fn(ctx, date)
	if err != nil {
		return nil, err
	}
	if len(raw) == 0 {
		// ⚠️ 조용한 0건이 가장 위험하다 — 구조가 바뀌어도 아무도 모른다.
		log.Printf("[%s] %s 경기 0건 — 소스 구조 변경 가능성", sport, date)
		return starts, nil
	}
	// 게이트 ①② — **Redis에 넣기 전에** 거른다. 날것을 넣고 파이썬이
	// 뒷수습하면 쓰레기가 이미 카드·λ까지 흘러간 뒤에야 걸린다.
	snap, drops := gate.Apply(raw)
	for _, d := range drops {
		// 조용한 폐기 금지 — 무엇을 왜 버렸는지 반드시 보이게 한다.
		log.Printf("[%s] 🚫 %s", sport, d)
	}
	if n := countFields(raw); n > 0 && len(drops)*2 > n {
		// 반대 방향 위험: 게이트가 정상 데이터를 버리고 있을 수 있다.
		log.Printf("[%s] ⚠️ 수집값 %d개 중 %d개 폐기 — 게이트 과잉이거나 소스 구조 변경",
			sport, n, len(drops))
	}
	prev, err := st.Latest(ctx, sport, date)
	if err != nil {
		return starts, err
	}
	changes := diff.Compare(prev, snap)
	if err := st.Save(ctx, sport, date, snap, changes, now); err != nil {
		return starts, err
	}
	log.Printf("[%s] %s — %d경기 수집, 값 %d개(폐기 %d), 변화 %d건, 예정 %d",
		sport, date, len(snap), countFields(snap), len(drops), len(changes), len(starts))
	for _, c := range diff.Notable(changes) {
		fmt.Printf("  ⚠️ %s\n", c)
	}
	return starts, nil
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
