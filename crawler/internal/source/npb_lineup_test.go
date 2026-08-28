package source

import (
	"strings"
	"testing"
)

func dasen(rows [][2]string) string {
	s := "<table><tr><th>打順</th><th>位置</th><th>選手名</th></tr>"
	for i, r := range rows {
		s += "<tr><td>" + itoa(i+1) + "</td><td>" + r[1] + "</td><td>" + r[0] + "</td></tr>"
	}
	return s + "</table>"
}

func itoa(n int) string {
	return []string{"0", "1", "2", "3", "4", "5", "6", "7", "8", "9"}[n]
}

var cl9 = [][2]string{
	{"山田 哲人", "捕"}, {"塩見 泰隆", "中"}, {"村上 宗隆", "三"},
	{"サンタナ", "右"}, {"オスナ", "一"}, {"西川 輝矢", "左"},
	{"長岡 秀樹", "遊"}, {"山野 太一", "投"}, {"山崎 晃大朗", "二"},
}
var pl9 = [][2]string{
	{"藤原 恭大", "中"}, {"藤岡 裕大", "遊"}, {"ソト", "一"},
	{"山口 航輝", "左"}, {"ポランコ", "右"}, {"安田 尚憲", "三"},
	{"佐藤 都志也", "捕"}, {"茶谷 健太", "二"}, {"石川 慎吾", "指"},
}

func TestParseNPBLineupsNineEachSide(t *testing.T) {
	h, a := parseNPBLineups(dasen(cl9) + dasen(pl9))
	if h == "" || a == "" {
		t.Fatalf("empty lineups home=%q away=%q", h, a)
	}
	if got := len(strings.Split(h, "-")); got != 9 {
		t.Fatalf("home %d names, want 9 (%s)", got, h)
	}
	if got := len(strings.Split(a, "-")); got != 9 {
		t.Fatalf("away %d names, want 9 (%s)", got, a)
	}
	if !strings.Contains(h, "山野 太一(投)") {
		t.Fatalf("CL 투수가 타순에 있어야 한다: %s", h)
	}
	if !strings.Contains(a, "石川 慎吾(指)") {
		t.Fatalf("PL 지명타자가 있어야 한다: %s", a)
	}
	if strings.Contains(h, "1루수") || strings.Contains(a, "3루수") {
		t.Fatalf("한글 포지션은 게이트가 숫자를 보고 버린다: %s / %s", h, a)
	}
}

func TestParseNPBLineupsPregameEmpty(t *testing.T) {
	html := "予告先発<table><tr><td>背番号</td><td>投</td><td>選手名</td></tr>" +
		"<tr><td>26</td><td>左投</td><td>山野 太一</td></tr></table>"
	h, a := parseNPBLineups(html)
	if h != "" || a != "" {
		t.Fatalf("경기 전 打順이 없는데 %q / %q", h, a)
	}
}

func TestParseNPBLineupsRejectsEight(t *testing.T) {
	h, a := parseNPBLineups(dasen(cl9[:8]) + dasen(pl9))
	if h != "" || a != "" {
		t.Fatalf("8명은 버려야 한다: %q / %q", h, a)
	}
}

func TestScoreCardHTMLDropsOtherDays(t *testing.T) {
	html := `<div id="gm_card"><a href="/npb/game/2021039331/index">神宮 ヤクルト 巨人 6 - 8 試合終了</a></div>` +
		`<div id="week_table"><a href="/npb/game/2021039200/index">ZOZOマリン ロッテ ソフトバンク 3 - 1 試合終了</a></div>`
	got := scoreCardHTML(html)
	if !strings.Contains(got, "2021039331") {
		t.Fatalf("그날 카드가 빠졌다: %s", got)
	}
	if strings.Contains(got, "2021039200") {
		t.Fatalf("주간 표 경기가 섞였다: %s", got)
	}
}
