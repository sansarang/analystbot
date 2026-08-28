// Package pace — 종목·경기 시작 시각으로 크롤 간격을 정한다.
//
// 고정 시계(15:30~19:30)는 KBO 18:30과 NPB 18:00을 한 덩어리로 본다.
// 실제 시작 시각은 경기마다 다르고, NPB 가속은 발송(17:45) 뒤까지 유지한다.
package pace

import "time"

const (
	// KBO SNS 타순은 18:30 경기 기준 14시부터 뜨는 경우가 많다 (14:00 = 4시간 30분 전).
	// 직전 교체 실측은 시작 19분 전이라, 가속은 **시작 직전까지** 유지한다.
	KBOLead = 4*time.Hour + 30*time.Minute

	// NPB 타순은 시작 약 1시간 전부터 뜬다. 17:45 공통 발송보다 먼저 끊으면
	// Yahoo가 늦게 올린 타순이 스냅샷에 없다 (20분이면 18:00 경기 17:40 종료).
	NPBLead       = 1 * time.Hour
	NPBStopBefore = 10 * time.Minute
)

func kboFast(now, start time.Time) bool {
	if start.IsZero() || !now.Before(start) {
		return false // 시작 시각이 없거나 이미 시작
	}
	return !now.Before(start.Add(-KBOLead))
}

func npbFast(now, start time.Time) bool {
	if start.IsZero() {
		return false
	}
	end := start.Add(-NPBStopBefore)
	if !now.Before(end) {
		return false // 시작 NPBStopBefore 전 이후(경기 중 포함)
	}
	return !now.Before(start.Add(-NPBLead))
}

// Fast 는 그 종목의 **남은 경기 하나라도** 가속 창에 있으면 true.
func Fast(sport string, now time.Time, starts []time.Time) bool {
	for _, t := range starts {
		switch sport {
		case "kbo":
			if kboFast(now, t) {
				return true
			}
		case "npb":
			if npbFast(now, t) {
				return true
			}
		}
	}
	return false
}

func windowBegin(sport string, start time.Time) time.Time {
	switch sport {
	case "kbo":
		return start.Add(-KBOLead)
	case "npb":
		return start.Add(-NPBLead)
	}
	return time.Time{}
}

func windowEnd(sport string, start time.Time) time.Time {
	switch sport {
	case "kbo":
		return start
	case "npb":
		return start.Add(-NPBStopBefore)
	}
	return time.Time{}
}

// UntilWindow 는 아직 열리지 않은 가속 창까지 남은 시간. 이미 가속 중이거나
// 오늘 창이 없으면 0. 평시 주기(60분)만 자면 창 시작을 지나쳐 늦게 들어간다
// (실측 2026-08-28: 11:32 수집 → 60분 주기면 NPB 17:00 창을 17:32에야 만난다).
func UntilWindow(sport string, now time.Time, starts []time.Time) time.Duration {
	var best time.Duration
	found := false
	for _, start := range starts {
		if start.IsZero() {
			continue
		}
		begin := windowBegin(sport, start)
		end := windowEnd(sport, start)
		if begin.IsZero() || !now.Before(end) {
			continue
		}
		if now.Before(begin) {
			d := begin.Sub(now)
			if !found || d < best {
				best, found = d, true
			}
		}
	}
	if !found {
		return 0
	}
	return best
}

// Wait 는 다음 수집까지 기다릴 시간. 시각을 모르면 평시(idle)다 — 모르는 것을
// 가속의 근거로 쓰면 소스를 과하게 두드린다.
// 가속 전이면 min(평시, 창 시작까지) — 창이 열릴 때 맞춰 깨운다.
func Wait(sport string, now time.Time, starts []time.Time, idle, fast time.Duration) time.Duration {
	if Fast(sport, now, starts) {
		return fast
	}
	if u := UntilWindow(sport, now, starts); u > 0 && u < idle {
		return u
	}
	return idle
}
