package pace

import (
	"testing"
	"time"
)

func at(hhmm string) time.Time {
	kst := time.FixedZone("KST", 9*3600)
	t, _ := time.ParseInLocation("2006-01-02 15:04", "2026-08-28 "+hhmm, kst)
	return t
}

func TestKBOUsesThatGamesStartNotASharedClock(t *testing.T) {
	// 18:30 경기: 14:00부터 시작 전까지. 19:00 경기와 창이 다르다.
	if !Fast("kbo", at("14:00"), []time.Time{at("18:30")}) {
		t.Fatal("18:30 경기 14:00는 가속이어야 한다")
	}
	if Fast("kbo", at("13:59"), []time.Time{at("18:30")}) {
		t.Fatal("14:00 전은 평시")
	}
	if Fast("kbo", at("18:30"), []time.Time{at("18:30")}) {
		t.Fatal("시작 시각부터는 가속하지 않는다")
	}
	if Fast("kbo", at("18:45"), []time.Time{at("18:30")}) {
		t.Fatal("시작 이후는 가속하지 않는다")
	}
	// 19:00 경기 — 18:30 고정 시계로는 이미 끝났을 시각
	if !Fast("kbo", at("18:40"), []time.Time{at("19:00")}) {
		t.Fatal("19:00 경기는 18:40에도 가속이어야 한다")
	}
	if Fast("kbo", at("14:00"), []time.Time{at("14:00")}) {
		t.Fatal("낮 경기가 이미 시작했으면 가속하지 않는다")
	}
}

func TestNPBStopsTwentyMinutesBeforeStart(t *testing.T) {
	start := at("18:00")
	if !Fast("npb", at("17:00"), []time.Time{start}) {
		t.Fatal("시작 1시간 전은 가속")
	}
	if Fast("npb", at("16:59"), []time.Time{start}) {
		t.Fatal("1시간보다 이르면 평시")
	}
	if Fast("npb", at("17:40"), []time.Time{start}) {
		t.Fatal("시작 20분 전(17:40)부터는 가속하지 않는다")
	}
	if Fast("npb", at("18:00"), []time.Time{start}) {
		t.Fatal("시작 시각은 가속하지 않는다")
	}
	if Fast("npb", at("18:20"), []time.Time{start}) {
		t.Fatal("시작 이후는 가속하지 않는다")
	}
}

func TestNPBEighteenThirtyIsNotEighteenHundred(t *testing.T) {
	// 18:30 시작이면 창은 17:30~18:10. 18:00 경기 창(17:00~17:40)과 다르다.
	start := at("18:30")
	if Fast("npb", at("17:00"), []time.Time{start}) {
		t.Fatal("18:30 경기를 18:00 시계로 가속하면 안 된다")
	}
	if !Fast("npb", at("17:30"), []time.Time{start}) {
		t.Fatal("18:30 경기 17:30은 가속")
	}
	if Fast("npb", at("18:10"), []time.Time{start}) {
		t.Fatal("18:30 경기 시작 20분 전 이후는 가속하지 않는다")
	}
}

func TestAnyRemainingGameKeepsThatSportFast(t *testing.T) {
	// 한 경기는 끝났고 늦은 경기가 남으면 그 종목만 가속
	if !Fast("kbo", at("18:40"), []time.Time{at("18:30"), at("19:00")}) {
		t.Fatal("남은 19:00 경기가 있는데 가속이 꺼졌다")
	}
}

func TestUnknownStartDoesNotAccelerate(t *testing.T) {
	if Fast("npb", at("17:10"), nil) {
		t.Fatal("시각을 모르면 가속하지 않는다")
	}
	if Wait("kbo", at("16:00"), nil, time.Hour, 2*time.Minute) != time.Hour {
		t.Fatal("시각 없으면 평시 간격")
	}
}
