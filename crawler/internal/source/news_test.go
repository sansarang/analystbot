package source

import (
	"strings"
	"testing"
	"time"
)

const sample = `<?xml version="1.0"?>
<rss version="2.0"><channel>
<item><title>한화 문동주 선발 제외</title><link>https://a.example/1</link>
<pubDate>Tue, 23 Sep 2026 09:00:00 GMT</pubDate></item>
<item><title>롯데 라인업 발표</title><link>https://a.example/2</link>
<pubDate>Tue, 23 Sep 2026 09:30:00 GMT</pubDate></item>
<item><title>시각 없는 기사</title><link>https://a.example/3</link>
<pubDate></pubDate></item>
<item><title></title><link>https://a.example/4</link>
<pubDate>Tue, 23 Sep 2026 09:40:00 GMT</pubDate></item>
</channel></rss>`

func now() time.Time { return time.Date(2026, 9, 23, 10, 0, 0, 0, time.UTC) }

// 🔴 이 단위의 핵심 — 제목·링크·**발행시각**이 구조화되어 나온다. LLM 0.
func TestParseNews(t *testing.T) {
	snap, skipped := ParseNews("kbo", []byte(sample), now())
	f := snap[NewsKey("kbo")]
	if len(f) != 2 {
		t.Fatalf("기사 2건이어야 한다: %d건 %v", len(f), f)
	}
	if skipped != 2 {
		t.Fatalf("시각 없음·제목 없음 2건을 버려야 한다: %d", skipped)
	}
	var seen int
	for _, v := range f {
		if !strings.Contains(v, "|") {
			t.Fatalf("값에 발행시각이 없다: %q", v)
		}
		if strings.HasPrefix(v, "2026-09-23T09:") {
			seen++
		}
	}
	if seen != 2 {
		t.Fatalf("발행시각이 RFC3339 로 실려야 한다: %v", f)
	}
}

// 🔴 못 읽은 시각을 "지금"으로 채우면 모든 기사가 방금 난 것이 되어
// 시각 대조가 통째로 거짓이 된다.
func TestParsePubNeverGuesses(t *testing.T) {
	if !parsePub("").IsZero() || !parsePub("어제").IsZero() {
		t.Fatal("못 읽은 시각을 지어냈다")
	}
	if parsePub("Tue, 23 Sep 2026 09:00:00 GMT").IsZero() {
		t.Fatal("정상 시각을 못 읽는다")
	}
}

// ⚠️ 미래 시각은 파싱이 깨졌다는 신호다 — 게이트 ① 과 같은 정신.
func TestFutureDropped(t *testing.T) {
	future := strings.Replace(sample, "23 Sep 2026 09:00", "25 Sep 2026 09:00", 1)
	snap, skipped := ParseNews("kbo", []byte(future), now())
	if len(snap[NewsKey("kbo")]) != 1 || skipped != 3 {
		t.Fatalf("미래 기사를 안 버렸다: %v (skipped=%d)", snap, skipped)
	}
}

// 🔴 제목이 아니라 **링크**로 id 를 만든다. 매체가 제목을 고쳐 다시 올리면
// 같은 기사가 매 주기 "새 기사"로 잡혀 변화 목록이 쓰레기가 된다.
func TestIDFromLink(t *testing.T) {
	a := itemID(rssItem{Title: "제목1", Link: "https://x/1"})
	b := itemID(rssItem{Title: "제목2", Link: "https://x/1"})
	c := itemID(rssItem{Title: "제목1", Link: "https://x/2"})
	if a != b {
		t.Fatal("같은 링크인데 id 가 달라졌다")
	}
	if a == c {
		t.Fatal("다른 링크인데 id 가 같다")
	}
}

// 🔴 라인업과 **다른 키**다. 검색이 막혀도 라인업 크롤은 살아야 하고,
// 게이트 ①②가 기사 제목을 보고 폐기하면 안 된다.
func TestNewsKeySeparate(t *testing.T) {
	if NewsKey("kbo") == "kbo" || !strings.HasPrefix(NewsKey("kbo"), "news_") {
		t.Fatalf("뉴스가 라인업과 같은 키를 쓴다: %s", NewsKey("kbo"))
	}
}

// ⚠️ 로케일은 파이썬이 YAML 에서 풀어 준 것을 그대로 쓴다.
func TestFeedURL(t *testing.T) {
	u := feedURL(Feed{Q: "KBO 선발", HL: "ko", GL: "KR"})
	for _, want := range []string{"/news/search?", "format=RSS", "setmkt=ko-KR"} {
		if !strings.Contains(u, want) {
			t.Fatalf("%s 가 없다: %s", want, u)
		}
	}
	if strings.Contains(feedURL(Feed{Q: "x"}), "setmkt") {
		t.Fatal("로케일이 없는데 지어냈다")
	}
}

func TestBadXML(t *testing.T) {
	if snap, _ := ParseNews("kbo", []byte("<not-rss"), now()); snap != nil {
		t.Fatal("깨진 XML 에 스냅샷을 만들었다")
	}
	if snap, _ := ParseNews("kbo", []byte(""), now()); snap != nil {
		t.Fatal("빈 본문에 스냅샷을 만들었다")
	}
}
