// Package source — 리그별 수집기. **LLM 0회**, 구조화 데이터만 긁는다.
package source

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"time"

	"analystbot/crawler/internal/diff"
)

const userAgent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

var client = &http.Client{Timeout: 20 * time.Second}

func get(ctx context.Context, url, referer string) ([]byte, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", userAgent)
	if referer != "" {
		req.Header.Set("Referer", referer)
	}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("%s: HTTP %d", url, resp.StatusCode)
	}
	return io.ReadAll(io.LimitReader(resp.Body, 4<<20))
}

// snapshotKey 는 더블헤더가 같은 카드여도 경기를 갈라 둔다.
func snapshotKey(away, home, gameID string) string {
	if gameID != "" {
		return away + "@" + home + "#" + gameID
	}
	return away + "@" + home
}

var (
	tagRe = regexp.MustCompile(`<[^>]+>`)
	wsRe  = regexp.MustCompile(`\s+`)
)

func text(s string) string {
	return strings.TrimSpace(wsRe.ReplaceAllString(tagRe.ReplaceAllString(s, " "), " "))
}

// ---------------------------------------------------------------- KBO (네이버)

// 네이버 축약 표기 → Odds API 팀명. 파이썬 쪽 naver_kbo.TEAM_TO_ODDS와 **같아야** 한다.
var kboTeams = map[string]string{
	"LG": "LG Twins", "두산": "Doosan Bears", "KT": "KT Wiz", "SSG": "SSG Landers",
	"NC": "NC Dinos", "키움": "Kiwoom Heroes", "한화": "Hanwha Eagles",
	"삼성": "Samsung Lions", "롯데": "Lotte Giants", "KIA": "Kia Tigers",
}

type naverGames struct {
	Result struct {
		Games []struct {
			GameID       string `json:"gameId"`
			HomeTeamName string `json:"homeTeamName"`
			AwayTeamName string `json:"awayTeamName"`
			StatusInfo   string `json:"statusInfo"`
			GameDateTime string `json:"gameDateTime"`
			CategoryID   string `json:"categoryId"`
		} `json:"games"`
	} `json:"result"`
}

type naverPreview struct {
	Result struct {
		PreviewData struct {
			GameInfo struct {
				Stadium string `json:"stadium"`
			} `json:"gameInfo"`
			HomeStarter struct {
				PlayerInfo struct {
					Name string `json:"name"`
				} `json:"playerInfo"`
			} `json:"homeStarter"`
			AwayStarter struct {
				PlayerInfo struct {
					Name string `json:"name"`
				} `json:"playerInfo"`
			} `json:"awayStarter"`
			HomeLineUp struct {
				Full []struct {
					PlayerName string `json:"playerName"`
					Position   string `json:"positionName"`
				} `json:"fullLineUp"`
			} `json:"homeTeamLineUp"`
			AwayLineUp struct {
				Full []struct {
					PlayerName string `json:"playerName"`
					Position   string `json:"positionName"`
				} `json:"fullLineUp"`
			} `json:"awayTeamLineUp"`
		} `json:"previewData"`
	} `json:"result"`
}

func lineupText(rows []struct {
	PlayerName string `json:"playerName"`
	Position   string `json:"positionName"`
}) string {
	// 포지션을 함께 싣는다 — "이름(포지션)".
	//   ⚠️ 종전에는 positionName을 **버렸다.** 그러면 지명타자 활용(주전이 수비
	//      없이 타석만 서는 체력 관리 신호)과 포지션 변경을 영영 감지할 수 없다.
	//      수집돼 있는 것을 버리는 것이 가장 아까운 손실이다.
	var names []string
	for _, r := range rows {
		if r.Position != "선발투수" && r.PlayerName != "" {
			if r.Position != "" {
				names = append(names, r.PlayerName+"("+r.Position+")")
			} else {
				names = append(names, r.PlayerName)
			}
		}
	}
	return strings.Join(names, "-")
}

// FetchKBO 은 네이버 스포츠에서 그 날짜 KBO 경기의 선발·라인업을 모은다.
// 두 번째 반환은 **아직 시작하지 않은** 경기 시각 — 가속 창 계산용.
func FetchKBO(ctx context.Context, date string) (diff.Snapshot, []time.Time, error) {
	url := "https://api-gw.sports.naver.com/schedule/games?fields=basic,superCategoryId,category" +
		"&upperCategoryId=kbaseball&fromDate=" + date + "&toDate=" + date + "&size=30"
	body, err := get(ctx, url, "https://m.sports.naver.com/")
	if err != nil {
		return nil, nil, err
	}
	var sched naverGames
	if err := json.Unmarshal(body, &sched); err != nil {
		return nil, nil, fmt.Errorf("일정 파싱: %w", err)
	}
	kst := time.FixedZone("KST", 9*3600)
	out := diff.Snapshot{}
	var starts []time.Time
	for _, g := range sched.Result.Games {
		if !keepKBOGame(g.CategoryID, g.HomeTeamName, g.AwayTeamName, g.GameID) {
			continue // 시범·올스타·중계 껍데기(kbaseballetc) 등 매핑 밖
		}
		home := kboTeams[g.HomeTeamName]
		away := kboTeams[g.AwayTeamName]
		if t, ok := parseNaverStart(g.GameDateTime, kst); ok && kboUpcoming(g.StatusInfo) {
			starts = append(starts, t)
		}
		pv, err := get(ctx, "https://api-gw.sports.naver.com/schedule/games/"+g.GameID+"/preview",
			"https://m.sports.naver.com/game/"+g.GameID)
		if err != nil {
			continue // 한 경기 실패가 전체를 막지 않는다
		}
		var p naverPreview
		if json.Unmarshal(pv, &p) != nil {
			continue
		}
		d := p.Result.PreviewData
		// ⚠️ 라인업은 **홈·원정을 분리해서** 넣는다.
		fields := map[string]string{
			"home_pitcher": d.HomeStarter.PlayerInfo.Name,
			"away_pitcher": d.AwayStarter.PlayerInfo.Name,
			"lineup_home":  lineupText(d.HomeLineUp.Full),
			"lineup_away":  lineupText(d.AwayLineUp.Full),
			"stadium":      d.GameInfo.Stadium,
			"status":       g.StatusInfo,
			"game_id":      g.GameID,
		}
		if t, ok := parseNaverStart(g.GameDateTime, kst); ok {
			fields["starts_at"] = t.Format(time.RFC3339)
		}
		out[snapshotKey(away, home, g.GameID)] = fields
	}
	return out, starts, nil
}

// ---------------------------------------------------------------- NPB (Yahoo)

// Yahoo 약칭 → Odds API 팀명. 파이썬 yahoo_npb.TEAM_TO_ODDS와 **같아야** 한다.
var npbTeams = map[string]string{
	"ヤクルト": "Tokyo Yakult Swallows", "巨人": "Yomiuri Giants",
	"中日": "Chunichi Dragons", "阪神": "Hanshin Tigers",
	"広島": "Hiroshima Toyo Carp", "DeNA": "Yokohama DeNA BayStars",
	"西武": "Saitama Seibu Lions", "日本ハム": "Hokkaido Nippon-Ham Fighters",
	"ロッテ": "Chiba Lotte Marines", "ソフトバンク": "Fukuoka SoftBank Hawks",
	"オリックス": "Orix Buffaloes", "楽天": "Tohoku Rakuten Golden Eagles",
}

var (
	npbLinkRe = regexp.MustCompile(`href="/npb/game/(\d+)/[a-z]*"[^>]*>((?s).*?)</a>`)
	// Go 정규식은 반복 상한이 1000이라 `{0,4000}`을 못 쓴다 —
	// 블록 잘라내기는 문자열 슬라이싱으로 한다(의도도 더 분명하다).
	npbNameRe = regexp.MustCompile(`(?s)<td[^>]*>\s*(\d+)\s*</td>\s*<td[^>]*>\s*([左右]投)\s*</td>\s*<td[^>]*>((?s).*?)</td>`)
	// 확정 경기 구조: 先発 | 投 | 선수명 | 右/左 | 방어율 | 컨디션
	// ⚠️ Yahoo는 경기 전(予告先発)과 확정 후의 구조가 **다르다.**
	//    한쪽만 보면 절반이 조용히 빈다 — 파이썬 쪽에서 이미 겪은 사고다.
	npbFinalRe = regexp.MustCompile(`(?s)<td[^>]*>\s*先発\s*</td>\s*<td[^>]*>[^<]*</td>\s*<td[^>]*>((?s).*?)</td>`)
	npbTableRe = regexp.MustCompile(`(?s)<table[^>]*>(.*?)</table>`)
	npbTrRe    = regexp.MustCompile(`(?s)<tr[^>]*>(.*?)</tr>`)
	npbCellRe  = regexp.MustCompile(`(?s)<t[dh][^>]*>(.*?)</t[dh]>`)
	npbClockRe = regexp.MustCompile(`(\d{1,2}):(\d{2})`)
)

// Yahoo /top 打順 약어. 한글 "3루수"는 숫자라 게이트가 이름을 버린다.
const npbPosJP = "遊三左一右捕二投中指"

// FetchNPB 은 Yahoo!スポーツ에서 그 날짜 NPB 경기의 선발을 모은다.
func FetchNPB(ctx context.Context, date string) (diff.Snapshot, []time.Time, error) {
	body, err := get(ctx, "https://baseball.yahoo.co.jp/npb/schedule/?date="+date, "")
	if err != nil {
		return nil, nil, err
	}
	html := scoreCardHTML(string(body))
	out := diff.Snapshot{}
	seen := map[string]bool{}
	kst := time.FixedZone("KST", 9*3600) // JST와 같다
	var starts []time.Time
	for _, m := range npbLinkRe.FindAllStringSubmatch(html, -1) {
		gid, inner := m[1], text(m[2])
		if seen[gid] {
			continue
		}
		seen[gid] = true
		var found []string
		for jp := range npbTeams {
			if idx := strings.Index(inner, jp); idx >= 0 {
				found = append(found, jp)
			}
		}
		if len(found) != 2 {
			continue // 종료·미정 블록
		}
		if strings.Index(inner, found[0]) > strings.Index(inner, found[1]) {
			found[0], found[1] = found[1], found[0]
		}
		home, away := npbTeams[found[0]], npbTeams[found[1]]
		if t, ok := parseYahooClock(inner, date, kst); ok && npbUpcoming(inner) {
			starts = append(starts, t)
		}
		page, err := get(ctx, "https://baseball.yahoo.co.jp/npb/game/"+gid+"/top", "")
		if err != nil {
			continue
		}
		hp, ap := parseNPBStarters(string(page))
		if hp == "" || ap == "" {
			hp, ap = parseNPBFinal(string(page))
		}
		status := "미상"
		switch {
		case strings.Contains(inner, "(先)"):
			status = "확정"
		case strings.Contains(inner, "(予)"):
			status = "예상"
		}
		fields := map[string]string{
			"home_pitcher": hp, "away_pitcher": ap, "starter_status": status,
			"game_id": gid,
		}
		if t, ok := parseYahooClock(inner, date, kst); ok {
			fields["starts_at"] = t.Format(time.RFC3339)
		}
		if lh, la := parseNPBLineups(string(page)); lh != "" && la != "" {
			fields["lineup_home"], fields["lineup_away"] = lh, la
		}
		out[snapshotKey(away, home, gid)] = fields
	}
	return out, starts, nil
}

func parseNPBStarters(html string) (home, away string) {
	i := strings.Index(html, "予告先発")
	if i < 0 {
		return "", ""
	}
	end := i + 12000
	if end > len(html) {
		end = len(html)
	}
	names := npbNameRe.FindAllStringSubmatch(html[i:end], -1)
	if len(names) >= 1 {
		home = text(names[0][3])
	}
	if len(names) >= 2 {
		away = text(names[1][3])
	}
	return home, away
}

// parseNPBFinal 은 **확정 경기** 구조에서 선발을 뽑는다.
//
// ⚠️ Yahoo는 경기 전(予告先発 블록)과 확정 후(先発 행)의 구조가 다르다.
// 한쪽만 보면 절반이 조용히 빈다 — 파이썬 쪽에서 이미 겪은 사고다.
func parseNPBFinal(html string) (home, away string) {
	m := npbFinalRe.FindAllStringSubmatch(html, -1)
	if len(m) >= 1 {
		home = text(m[0][1])
	}
	if len(m) >= 2 {
		away = text(m[1][1])
	}
	return home, away
}

// scoreCardHTML 은 일정 페이지의 **그날 카드**만 남긴다.
//
// 실측 2026-08-28: `id="gm_card"`가 요청 날짜 경기이고, 그 아래 주간 표에
// 어제·내일이 섞인다. 날짜를 요청 파라미터로 덮어씌우면 남의 경기가 오늘이 된다.
func scoreCardHTML(html string) string {
	const mark = `id="gm_card"`
	i := strings.Index(html, mark)
	if i < 0 {
		return html
	}
	rest := html[i+len(mark):]
	j := strings.Index(rest, `id="`)
	if j < 0 {
		return html[i:]
	}
	return html[i : i+len(mark)+j]
}

func npbCells(row string) []string {
	raw := npbCellRe.FindAllStringSubmatch(row, -1)
	out := make([]string, 0, len(raw))
	for _, m := range raw {
		out = append(out, text(m[1]))
	}
	return out
}

func indexOf(ss []string, want string) int {
	for i, s := range ss {
		if s == want {
			return i
		}
	}
	return -1
}

// parseNPBLineups 는 Yahoo `/top`의 `打順` 표에서 선발 9명을 뽑는다.
//
// 실측 2026-08-28: 종료 후 팀당 1~9번 9행(대타 없음). 첫 표가 홈.
// 경기 전(시작 수 시간 전)에는 표가 없다. 9명이 아니면 버린다.
func parseNPBLineups(html string) (home, away string) {
	var found []string
	for _, tb := range npbTableRe.FindAllStringSubmatch(html, -1) {
		rows := npbTrRe.FindAllStringSubmatch(tb[1], -1)
		var cells [][]string
		for _, r := range rows {
			c := npbCells(r[1])
			if len(c) > 0 {
				cells = append(cells, c)
			}
		}
		if len(cells) == 0 || cells[0][0] != "打順" || indexOf(cells[0], "選手名") < 0 {
			continue
		}
		head := cells[0]
		nameI, posI := indexOf(head, "選手名"), indexOf(head, "位置")
		if posI < 0 {
			posI = 1
		}
		maxI := nameI
		if posI > maxI {
			maxI = posI
		}
		var order []string
		for _, r := range cells[1:] {
			if len(r) <= maxI {
				break
			}
			n := len(order) + 1
			if r[0] != fmt.Sprintf("%d", n) {
				break
			}
			name := strings.TrimSpace(r[nameI])
			if name == "" {
				break
			}
			pos := strings.TrimSpace(r[posI])
			if pos != "" {
				rs := []rune(pos)
				if strings.ContainsRune(npbPosJP, rs[0]) {
					name = name + "(" + string(rs[0]) + ")"
				}
			}
			order = append(order, name)
		}
		if len(order) == 9 {
			found = append(found, strings.Join(order, "-"))
		}
	}
	if len(found) < 2 {
		return "", ""
	}
	return found[0], found[1]
}

func kboUpcoming(status string) bool {
	if strings.Contains(status, "종료") || strings.Contains(status, "취소") {
		return false
	}
	return !strings.Contains(status, "경기중")
}

// keepKBOGame — 1군 정규시즌만. 실측 2026-08-28 네이버 일정에
// categoryId=kbaseballetc (VR·중계 껍데기 등) 가 팀명 없이 13:00/17:00으로
// 섞여 있다. 팀 매핑만 보면 지금은 건너뛰지만, 이름이 채워지면 가속 창이
// 낮 경기로 당겨진다.
func keepKBOGame(categoryID, home, away, gameID string) bool {
	if categoryID != "" && categoryID != "kbo" {
		return false
	}
	_, okH := kboTeams[home]
	_, okA := kboTeams[away]
	return okH && okA && gameID != ""
}

func npbUpcoming(inner string) bool {
	return !strings.Contains(inner, "試合終了") && !strings.Contains(inner, "試合中")
}

func parseNaverStart(s string, loc *time.Location) (time.Time, bool) {
	s = strings.TrimSpace(s)
	if s == "" {
		return time.Time{}, false
	}
	if t, err := time.Parse(time.RFC3339, s); err == nil {
		return t.In(loc), true
	}
	for _, layout := range []string{
		"2006-01-02T15:04:05",
		"2006-01-02 15:04:05",
		"2006-01-02T15:04:05.000",
	} {
		if t, err := time.ParseInLocation(layout, s, loc); err == nil {
			return t, true
		}
	}
	return time.Time{}, false
}

func parseYahooClock(inner, date string, loc *time.Location) (time.Time, bool) {
	m := npbClockRe.FindStringSubmatch(inner)
	if m == nil {
		return time.Time{}, false
	}
	h, err1 := strconv.Atoi(m[1])
	min, err2 := strconv.Atoi(m[2])
	if err1 != nil || err2 != nil || h < 0 || h > 23 || min < 0 || min > 59 {
		return time.Time{}, false
	}
	day, err := time.ParseInLocation("2006-01-02", date, loc)
	if err != nil {
		return time.Time{}, false
	}
	return time.Date(day.Year(), day.Month(), day.Day(), h, min, 0, 0, loc), true
}
