package main

import (
	"testing"
	"time"
)

func at(hhmm string) time.Time {
	kst := time.FixedZone("KST", 9*3600)
	t, _ := time.ParseInLocation("2006-01-02 15:04", "2026-08-26 "+hhmm, kst)
	return t
}

// [§9-10] 경기 임박 가속. 감독 발언·선발 교체는 경기 직전에 나온다 —
// 실측(2026-08-26): 롯데 감독의 마무리 교체 발언이 경기 **19분 전**에 나왔다.
func TestFastWindowCoversKickoffApproach(t *testing.T) {
	cases := []struct {
		now  string
		want bool
	}{
		{"09:00", false}, // 평시
		{"15:29", false},
		{"15:30", true}, // 가속 시작
		{"18:11", true}, // 실제 감독 발언이 나온 시각
		{"18:30", true}, // 경기 시작
		{"19:29", true},
		{"19:30", false}, // 종료 시각은 포함하지 않는다
		{"23:00", false},
	}
	for _, c := range cases {
		if got := inFastWindow(at(c.now), "15:30", "19:30"); got != c.want {
			t.Errorf("%s: %v, want %v", c.now, got, c.want)
		}
	}
}

func TestFastWindowHandlesMidnightCrossing(t *testing.T) {
	// MLB 슬레이트처럼 자정을 넘는 구간도 지원해야 한다
	if !inFastWindow(at("23:30"), "22:00", "03:00") {
		t.Error("자정 이전 구간이 빠졌다")
	}
	if !inFastWindow(at("01:00"), "22:00", "03:00") {
		t.Error("자정 이후 구간이 빠졌다")
	}
	if inFastWindow(at("12:00"), "22:00", "03:00") {
		t.Error("구간 밖인데 가속했다")
	}
}

func TestBadWindowNeverAccelerates(t *testing.T) {
	// ⚠️ 잘못된 설정으로 소스를 과하게 두드리는 것보다 평시 주기가 안전하다.
	for _, bad := range []string{"", "abc", "25:00", "15", "15:99"} {
		if inFastWindow(at("16:00"), bad, "19:30") {
			t.Errorf("잘못된 from=%q인데 가속했다", bad)
		}
		if inFastWindow(at("16:00"), "15:30", bad) {
			t.Errorf("잘못된 until=%q인데 가속했다", bad)
		}
	}
}
