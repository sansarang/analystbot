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

func TestNPBStopsFifteenMinutesBeforeStart(t *testing.T) {
	start := at("18:00")
	if !Fast("npb", at("17:00"), []time.Time{start}) {
		t.Fatal("시작 1시간 전은 가속")
	}
	if Fast("npb", at("16:59"), []time.Time{start}) {
		t.Fatal("1시간보다 이르면 평시")
	}
	if !Fast("npb", at("17:44"), []time.Time{start}) {
		t.Fatal("17:44는 아직 가속(17:45에 끝낸다)")
	}
	if Fast("npb", at("17:45"), []time.Time{start}) {
		t.Fatal("17:45부터는 가속하지 않는다 — 크롤·분석 종료선")
	}
	if Fast("npb", at("17:50"), []time.Time{start}) {
		t.Fatal("17:45 이후는 가속하지 않는다")
	}
	if Fast("npb", at("18:00"), []time.Time{start}) {
		t.Fatal("시작 시각은 가속하지 않는다")
	}
}

func TestNPBEighteenThirtyIsNotEighteenHundred(t *testing.T) {
	// 18:30 시작이면 창은 17:30~18:15. 18:00 경기 창(17:00~17:45)과 다르다.
	start := at("18:30")
	if Fast("npb", at("17:00"), []time.Time{start}) {
		t.Fatal("18:30 경기를 18:00 시계로 가속하면 안 된다")
	}
	if !Fast("npb", at("17:30"), []time.Time{start}) {
		t.Fatal("18:30 경기 17:30은 가속")
	}
	if Fast("npb", at("18:15"), []time.Time{start}) {
		t.Fatal("18:30 경기 시작 15분 전 이후는 가속하지 않는다")
	}
	if Fast("npb", at("18:20"), []time.Time{start}) {
		t.Fatal("18:30 경기 18:20은 가속하면 안 된다")
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

func TestWaitWakesAtWindowOpenNotFullIdle(t *testing.T) {
	// 평시 60분만 자면 창 시작을 지나친다. 창이 idle보다 가까우면 그때 깬다.
	idle, fast := time.Hour, 2*time.Minute
	// KBO 18:30 → 14:00 창. 13:32면 28분 뒤.
	got := Wait("kbo", at("13:32"), []time.Time{at("18:30")}, idle, fast)
	if got != 28*time.Minute {
		t.Fatalf("KBO 창 직전 Wait=%v want 28m", got)
	}
	// 창이 2시간 이상 남으면 평시 유지
	got = Wait("kbo", at("11:32"), []time.Time{at("18:30")}, idle, fast)
	if got != idle {
		t.Fatalf("창이 멀 때 Wait=%v want idle", got)
	}
	// NPB 18:00 → 17:00 창. 16:32면 28분 뒤.
	got = Wait("npb", at("16:32"), []time.Time{at("18:00")}, idle, fast)
	if got != 28*time.Minute {
		t.Fatalf("NPB 창 직전 Wait=%v want 28m", got)
	}
	// 이미 가속 중이면 2분
	got = Wait("npb", at("17:10"), []time.Time{at("18:00")}, idle, fast)
	if got != fast {
		t.Fatalf("가속 중 Wait=%v want fast", got)
	}
}
