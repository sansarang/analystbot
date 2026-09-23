// news.go — [MOV-C 2026-09-23] 리그 뉴스 RSS 를 **시각 붙은 사실**로 쌓는다.
//
// 사용자 2026-09-23: "왜 이렇게 배당이 이동되었는지" · "이유 미상은 없다" ·
// "bing 등을 초기에 고랭과 같이 서치의 단계를 옮기면"
//
// 왜 여기인가:
//
//	배당이 움직인 이유를 찾으려면 "그 시각에 무슨 일이 있었나"를 알아야 하고,
//	기사가 **언제** 떴는지는 나중에 되돌아가 알 수 없다. 라인업과 똑같이
//	계속 긁어 두어야 하는 자료다.
//
//	실측 2026-09-22~23: 선발 확정·라인업 공시만으로는 2%p 이상 이동의
//	46.7% 만 설명됐다. 나머지를 설명할 채널이 이것이다.
//
// 🔴 **이것은 검색이지 추출이 아니다.** RSS 가 제목·URL·발행시각을 구조화해
// 주므로 LLM 이 필요 없다 — `llm.enabled: false` 를 지킨다. 기사 본문에서
// 칸을 뽑는 단계만 LLM 이고, 여기서는 하지 않는다.
//
// 🔴 **중요도·방향 판단을 여기서 하지 않는다.** `diff` 패키지와 같은 규약이다
// ("크롤러가 임의 가중치를 만들면 측정되지 않은 튜닝이 된다"). 무엇이 언제
// 있었다는 **사실만** 남기고, 그것이 이동의 원인인지는 파이썬이 시각을 맞춰
// 정한다.
//
// ⚠️ 질의·언어는 `config/search_terms.yaml` 이 **원본**이다. Go 모듈에 YAML
// 파서를 넣지 않으려고 파이썬이 그것을 풀어 Redis 에 싣고(`crawl:news:feeds`)
// 여기서는 읽기만 한다 — 사본을 만들지 않는다.
//
// ⚠️ UA 위장·프록시 회전·쿠키 주입·CAPTCHA 우회·429 무시는 **하지 않는다.**
// 429 나 오류를 받으면 그 리그를 이번 주기만 건너뛰고 로그를 남긴다.
package source

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/xml"
	"fmt"
	"net/url"
	"strings"
	"time"

	"analystbot/crawler/internal/diff"
)

// Feed 는 리그 하나의 뉴스 질의다. 파이썬이 YAML 에서 풀어 싣는다.
type Feed struct {
	Q  string `json:"q"`
	HL string `json:"hl"`
	GL string `json:"gl"`
}

// NewsKey 는 뉴스 스냅샷을 담을 **별도 종목 키**다.
//
// 🔴 라인업과 섞지 않는다. 검색이 막혀도 라인업 크롤은 그대로 돌아야 하고,
// 게이트 ①②(투구수·타순 검사)가 기사 제목을 보고 폐기하면 안 된다.
func NewsKey(league string) string { return "news_" + league }

//: RSS 한 건. 우리가 쓰는 칸만 받는다.
type rssItem struct {
	Title   string `xml:"title"`
	Link    string `xml:"link"`
	PubDate string `xml:"pubDate"`
}

type rssDoc struct {
	Items []rssItem `xml:"channel>item"`
}

// feedURL 은 Bing 뉴스 RSS 주소를 만든다.
//
// ⚠️ 경로는 파이썬 쪽(`config/deepsearch.yaml` 의 `bing_news_rss.base`)과
// 같은 `/news/search` 다. robots 는 `/search` 를 막지만 `/news/…` 를 막는
// 줄이 없다(실측 2026-09-21).
func feedURL(f Feed) string {
	v := url.Values{}
	v.Set("q", f.Q)
	v.Set("format", "RSS")
	if f.HL != "" && f.GL != "" {
		v.Set("setmkt", strings.ToLower(f.HL)+"-"+strings.ToUpper(f.GL))
	}
	return "https://www.bing.com/news/search?" + v.Encode()
}

// itemID 는 기사 하나의 안정적인 식별자다.
//
// 🔴 **링크로 만든다.** 제목은 매체가 조금씩 고쳐 다시 올리면 바뀌어서,
// 같은 기사가 매 주기 "새 기사"로 잡힌다. 그러면 변화 목록이 쓰레기가 된다.
func itemID(it rssItem) string {
	key := strings.TrimSpace(it.Link)
	if key == "" {
		key = strings.TrimSpace(it.Title)
	}
	sum := sha256.Sum256([]byte(key))
	return hex.EncodeToString(sum[:8])
}

// parsePub 은 RSS 발행시각을 읽는다. 못 읽으면 zero time 이다.
//
// ⚠️ **지어내지 않는다.** 못 읽은 것을 "지금"으로 채우면 모든 기사가 방금 난
// 것이 되어 시각 대조가 통째로 거짓이 된다.
func parsePub(s string) time.Time {
	s = strings.TrimSpace(s)
	for _, layout := range []string{
		time.RFC1123Z, time.RFC1123, time.RFC822Z, time.RFC822, time.RFC3339,
	} {
		if t, err := time.Parse(layout, s); err == nil {
			return t.UTC()
		}
	}
	return time.Time{}
}

// ParseNews 는 RSS 본문 → 스냅샷 한 칸. **순수 함수**(HTTP 없음)라 계약이
// 이것만 따로 잰다.
//
// 값 모양: `<RFC3339 발행시각>|<제목>`. 발행시각을 값에 담는 이유는, 크롤
// 시각(`store.Save` 가 붙이는 `at`)과 **기사 자체의 시각**이 다르기 때문이다 —
// 배당 이동과 맞출 때 필요한 것은 후자다.
func ParseNews(league string, body []byte, now time.Time) (diff.Snapshot, int) {
	var doc rssDoc
	if err := xml.Unmarshal(body, &doc); err != nil {
		return nil, 0
	}
	fields := map[string]string{}
	skipped := 0
	for _, it := range doc.Items {
		title := strings.TrimSpace(it.Title)
		pub := parsePub(it.PubDate)
		// 🔴 제목이 없거나 발행시각을 못 읽으면 **버린다.** 시각 없는 기사는
		//    이 설계에서 쓸모가 없고, 넣어 두면 쓸 수 있는 줄 착각하게 된다.
		if title == "" || pub.IsZero() {
			skipped++
			continue
		}
		// ⚠️ 미래 시각은 파싱이 깨졌다는 신호다(게이트 ① 과 같은 정신).
		//    여유 2시간은 매체 타임존 표기 오차를 위한 것이다.
		if pub.After(now.Add(2 * time.Hour)) {
			skipped++
			continue
		}
		fields[itemID(it)] = pub.UTC().Format(time.RFC3339) + "|" + title
	}
	if len(fields) == 0 {
		return nil, skipped
	}
	return diff.Snapshot{NewsKey(league): fields}, skipped
}

// FetchNews 는 한 리그의 뉴스 피드를 긁는다.
//
// ⚠️ 실패는 **그 리그만** 건너뛴다. 호출부가 다른 리그·라인업 수집을 계속한다.
func FetchNews(ctx context.Context, league string, f Feed) (diff.Snapshot, int, error) {
	if strings.TrimSpace(f.Q) == "" {
		return nil, 0, fmt.Errorf("질의가 비었다: %s", league)
	}
	body, err := get(ctx, feedURL(f), "https://www.bing.com/")
	if err != nil {
		return nil, 0, err
	}
	snap, skipped := ParseNews(league, body, time.Now().UTC())
	return snap, skipped, nil
}
