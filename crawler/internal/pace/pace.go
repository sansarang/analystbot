// Package pace — 종목·경기 시작 시각으로 크롤 간격을 정한다.
//
// 고정 시계(15:30~19:30)는 KBO 18:30과 NPB 18:00을 한 덩어리로 본다.
// 실제 시작 시각은 경기마다 다르고, NPB 타순은 시작 20분 전까지만 보면 된다.
package pace

import "time"

const (
	// KBO SNS 타순은 18:30 경기 기준 14시부터 뜨는 경우가 많다 (14:00 = 4시간 30분 전).
	// 직전 교체 실측은 시작 19분 전이라, 가속은 **시작 직전까지** 유지한다.
	KBOLead = 4*time.Hour + 30*time.Minute

	// NPB 타순은 시작 약 1시간 전부터 뜨고, **시작 20분 전**이면 그만 본다.
	NPBLead       = 1 * time.Hour
	NPBStopBefore = 20 * time.Minute
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
		return false // 시작 20분 전 이후(경기 중 포함)
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

// Wait 는 다음 수집까지 기다릴 시간. 시각을 모르면 평시(idle)다 — 모르는 것을
// 가속의 근거로 쓰면 소스를 과하게 두드린다.
func Wait(sport string, now time.Time, starts []time.Time, idle, fast time.Duration) time.Duration {
	if Fast(sport, now, starts) {
		return fast
	}
	return idle
}
