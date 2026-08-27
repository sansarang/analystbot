package source

import "testing"

// 🔴 크롤러가 positionName을 버리고 있었다. 그러면 지명타자 활용(주전이 수비 없이
//    타석만 서는 체력 관리 신호)과 포지션 변경을 영영 감지할 수 없다.
//    수집돼 있는 것을 버리는 것이 가장 아까운 손실이다.
func TestLineupTextKeepsPosition(t *testing.T) {
	rows := []struct {
		PlayerName string `json:"playerName"`
		Position   string `json:"positionName"`
	}{
		{"김도영", "3루수"},
		{"최형우", "지명타자"},
		{"양현종", "선발투수"}, // 선발투수는 타순이 아니다 — 빠져야 한다
		{"박찬호", ""},        // 포지션이 없으면 이름만
	}
	got := lineupText(rows)
	want := "김도영(3루수)-최형우(지명타자)-박찬호"
	if got != want {
		t.Fatalf("lineupText = %q, want %q", got, want)
	}
}

func TestLineupTextEmpty(t *testing.T) {
	var rows []struct {
		PlayerName string `json:"playerName"`
		Position   string `json:"positionName"`
	}
	if got := lineupText(rows); got != "" {
		t.Fatalf("빈 입력에 %q — 없는 것을 만들면 안 된다", got)
	}
}
