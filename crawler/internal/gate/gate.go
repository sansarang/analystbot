// Package gate — 긁은 값을 Redis에 넣기 **전에** 거른다.
//
// 왜 Go에서 거르는가:
//
//	지금 구조는 날것을 Redis에 넣고 파이썬이 뒷수습한다. 그러면 쓰레기가 이미
//	카드·λ까지 흘러간 뒤에야 걸린다. 게이트 ①②는 이력도 DB도 필요 없는
//	**즉시 판정**이므로 수집 지점에서 끝내는 것이 맞다.
//	(게이트 ③ 소스 대조·④ 사후 채점은 이력이 필요해 파이썬이 맡는다.)
//
// 게이트 ① 물리 검사 — 값이 물리적으로 불가능한가.
//
//	투구수 200개 · ERA 189.00 · 타순 10번. 이것은 "거짓 정보"가 아니라
//	**파싱이 깨졌다는 신호**다. 실사고: Yahoo에서 齋藤 響介 ERA 189.00을
//	그대로 받아 선발 억제 계수가 무너졌다.
//
// 게이트 ② 자기 일관성 — 값들끼리 앞뒤가 맞는가.
//
//	라인업 9명인가 · 이름 중복은 없는가 · 승+패+무 = 경기수인가.
//	마지막 검사는 실제로 효과가 증명됐다(2026-08-27): 네이버가 준
//	61승 50패 2무 = 113경기가 공식 기록 113과 맞아떨어져 그 스냅샷이
//	특정 경기 **이전** 것임을 증명했다.
//
// ⚠️ **빈 값은 위반이 아니다.** 선발·라인업은 경기 임박까지 비어 있는 것이
// 정상이다. 값이 **있는데** 불가능할 때만 폐기한다. 그러지 않으면 정상 데이터를
// 버리는 반대 방향 사고가 난다(새 가드는 양방향으로 측정한다 — 규율).
package gate

import (
	"fmt"
	"strconv"
	"strings"
	"unicode"

	"analystbot/crawler/internal/diff"
)

// Drop 은 폐기된 값 하나다. **무엇을 왜 버렸는지 반드시 남긴다** —
// 조용한 폐기는 조용한 오염만큼 위험하다.
type Drop struct {
	Game   string `json:"game"`
	Field  string `json:"field"`
	Value  string `json:"value"`
	Reason string `json:"reason"`
	Gate   string `json:"gate"` // "물리" | "일관성"
}

func (d Drop) String() string {
	return fmt.Sprintf("%s %s=%q 폐기(%s): %s", d.Game, d.Field, d.Value, d.Gate, d.Reason)
}

// ---------------------------------------------------------------- 게이트 ① 물리

type kind int

const (
	kName  kind = iota // 사람 이름 하나
	kNames             // "-"로 이은 이름 목록
	kInt               // 정수 범위
	kFloat             // 실수 범위
	kEnum              // 허용 값 목록
	kFree              // 자유 문자열 — 길이만 본다
)

type rule struct {
	k        kind
	min, max float64
	allowed  []string
}

// 필드별 물리 한계. **여기 없는 필드는 검사하지 않고 통과시킨다** —
// 새 필드를 넣는 사람이 규칙을 함께 정의하도록 강제하지 않으면 검사가
// 의미 없이 넓어지고, 반대로 미등록 필드를 폐기하면 수집이 조용히 멈춘다.
var rules = map[string]rule{
	// 이름
	"home_pitcher":   {k: kName},
	"away_pitcher":   {k: kName},
	"stadium":        {k: kFree, max: 20},
	"status":         {k: kFree, max: 30},
	"starter_status": {k: kEnum, allowed: []string{"확정", "예상", "미상"}},
	// 라인업 — 야구는 지명타자 포함 9명
	"lineup_home": {k: kNames, min: 9, max: 9},
	"lineup_away": {k: kNames, min: 9, max: 9},

	// 아래는 [2][3] 수집 확대에서 채워질 필드다. 규칙을 **먼저** 박아둔다 —
	// 값이 들어오기 시작한 뒤에 규칙을 만들면 그 사이 데이터가 무검증으로 샌다.
	"home_pitches_l3": {k: kInt, min: 0, max: 200}, // 최근 3경기 투구수
	"away_pitches_l3": {k: kInt, min: 0, max: 200},
	"home_closer_b2b": {k: kEnum, allowed: []string{"0", "1", "2", "3"}}, // 마무리 연투 일수
	"away_closer_b2b": {k: kEnum, allowed: []string{"0", "1", "2", "3"}},
	"home_era":        {k: kFloat, min: 0, max: 15}, // 齋藤 響介 189.00 사고
	"away_era":        {k: kFloat, min: 0, max: 15},
	"home_ip_avg":     {k: kFloat, min: 0, max: 15},
	"away_ip_avg":     {k: kFloat, min: 0, max: 15},
	"home_rank":       {k: kInt, min: 1, max: 12}, // KBO 10 · NPB 6 (리그별)
	"away_rank":       {k: kInt, min: 1, max: 12},
	"home_w":          {k: kInt, min: 0, max: 200},
	"home_l":          {k: kInt, min: 0, max: 200},
	"home_d":          {k: kInt, min: 0, max: 200},
	"home_g":          {k: kInt, min: 0, max: 200},
	"away_w":          {k: kInt, min: 0, max: 200},
	"away_l":          {k: kInt, min: 0, max: 200},
	"away_d":          {k: kInt, min: 0, max: 200},
	"away_g":          {k: kInt, min: 0, max: 200},
}

const maxNameRunes = 20

// nameOnly — 괄호 안 포지션 표기를 떼고 이름 부분만 남긴다.
//
// 🔴 KBO 타순은 "나승엽(1루수)" 꼴이다. 1루수·2루수·3루수에 숫자가 들어 있어
//    checkName 의 숫자 검사가 **정상 타순을 100% 폐기**했다.
//    실측 2026-08-30 17:09 운영 로그: 키움@두산·LG@롯데 4건 전부
//    "이름에 숫자가 섞임 — 컬럼 밀림"으로 폐기, 변화 0건 →
//    스케줄러 crawler_lineup_poll 이 타순을 못 봐 저녁 재판정이 트리거되지 않았다.
//    NPB는 포지션이 中堅手 처럼 숫자가 없어 이 사고를 겪지 않았다.
//
// 가드를 푸는 것이 아니다 — 검사 대상을 **원래 의도했던 이름 칸**으로
// 되돌리는 것이다. 컬럼이 밀려 이름 자리에 숫자가 오면 여전히 잡힌다.
func nameOnly(v string) string {
	if i := strings.IndexRune(v, '('); i >= 0 {
		return strings.TrimSpace(v[:i])
	}
	return v
}

// checkName — 사람 이름이 될 수 있는 문자열인가.
// 숫자가 섞였다면 표 컬럼이 밀린 것이다(조용한 오염의 전형).
func checkName(v string) string {
	r := []rune(nameOnly(v))
	if len(r) > maxNameRunes {
		return fmt.Sprintf("이름이 %d자 — 표 파싱이 밀렸을 가능성", len(r))
	}
	for _, c := range r {
		if unicode.IsDigit(c) {
			return "이름에 숫자가 섞임 — 컬럼 밀림"
		}
	}
	return ""
}

func checkPhysical(field, v string) string {
	ru, known := rules[field]
	if !known || v == "" {
		return "" // 미등록 필드·빈 값은 통과 (빈 값 = 아직 발표 전)
	}
	switch ru.k {
	case kName:
		return checkName(v)
	case kFree:
		if ru.max > 0 && float64(len([]rune(v))) > ru.max {
			return fmt.Sprintf("길이 %d자 초과", int(ru.max))
		}
	case kEnum:
		for _, a := range ru.allowed {
			if v == a {
				return ""
			}
		}
		return fmt.Sprintf("허용 값(%s) 밖", strings.Join(ru.allowed, "/"))
	case kInt:
		n, err := strconv.Atoi(strings.TrimSpace(v))
		if err != nil {
			return "정수가 아님"
		}
		if float64(n) < ru.min || float64(n) > ru.max {
			return fmt.Sprintf("%d — 물리 범위 %d~%d 밖", n, int(ru.min), int(ru.max))
		}
	case kFloat:
		f, err := strconv.ParseFloat(strings.TrimSpace(v), 64)
		if err != nil {
			return "숫자가 아님"
		}
		if f < ru.min || f > ru.max {
			return fmt.Sprintf("%.2f — 물리 범위 %.0f~%.0f 밖", f, ru.min, ru.max)
		}
	case kNames:
		names := splitNames(v)
		if float64(len(names)) < ru.min || float64(len(names)) > ru.max {
			return fmt.Sprintf("%d명 — %d명이어야 함", len(names), int(ru.min))
		}
		for _, n := range names {
			if msg := checkName(n); msg != "" {
				return msg
			}
		}
	}
	return ""
}

func splitNames(v string) []string {
	var out []string
	for _, p := range strings.Split(v, "-") {
		if p = strings.TrimSpace(p); p != "" {
			out = append(out, p)
		}
	}
	return out
}

// ---------------------------------------------------------------- 게이트 ② 일관성

// consistency 는 값들끼리의 모순을 찾는다. 반환: 폐기할 필드 → 사유.
//
// ⚠️ 경기 전체를 버리지 않는다. 라인업이 어긋났다고 선발까지 버리면
// 멀쩡한 정보를 잃는다 — **어긋난 항목군만** 버린다.
func consistency(fields map[string]string) map[string]string {
	bad := map[string]string{}

	// 라인업 — 같은 사람이 두 번 나올 수 없다
	for _, f := range []string{"lineup_home", "lineup_away"} {
		v := fields[f]
		if v == "" {
			continue
		}
		seen := map[string]bool{}
		for _, n := range splitNames(v) {
			if seen[n] {
				bad[f] = fmt.Sprintf("타순에 %s가 중복 — 파싱 오류", n)
				break
			}
			seen[n] = true
		}
	}

	// 전적 — 승+패+무 = 경기수. 어긋나면 그 팀 전적 전체를 버린다.
	// 이 검사가 스냅샷의 **시점**을 증명한다(2026-08-27 실측).
	for _, side := range []string{"home", "away"} {
		w, okW := atoi(fields[side+"_w"])
		l, okL := atoi(fields[side+"_l"])
		d, okD := atoi(fields[side+"_d"])
		g, okG := atoi(fields[side+"_g"])
		if !(okW && okL && okD && okG) {
			continue // 넷이 다 있어야 검사할 수 있다
		}
		if w+l+d != g {
			msg := fmt.Sprintf("승%d+패%d+무%d=%d ≠ 경기수%d", w, l, d, w+l+d, g)
			for _, k := range []string{"_w", "_l", "_d", "_g"} {
				bad[side+k] = msg
			}
		}
	}

	// 선발 두 명이 동일인일 수 없다
	if hp, ap := fields["home_pitcher"], fields["away_pitcher"]; hp != "" && hp == ap {
		bad["home_pitcher"] = "양 팀 선발이 동일인 — 파싱 오류"
		bad["away_pitcher"] = "양 팀 선발이 동일인 — 파싱 오류"
	}
	return bad
}

func atoi(v string) (int, bool) {
	n, err := strconv.Atoi(strings.TrimSpace(v))
	return n, err == nil
}

// ---------------------------------------------------------------- 적용

// Apply 는 스냅샷에 게이트 ①②를 걸어 **깨끗한 스냅샷**과 폐기 목록을 돌려준다.
//
// 원본을 수정하지 않는다 — 호출자가 원본·정제본을 비교할 수 있어야
// 게이트가 정상 데이터를 버리고 있는지(반대 방향 위험) 측정할 수 있다.
func Apply(snap diff.Snapshot) (diff.Snapshot, []Drop) {
	clean := diff.Snapshot{}
	var drops []Drop
	for game, fields := range snap {
		kept := map[string]string{}
		for f, v := range fields {
			if msg := checkPhysical(f, v); msg != "" {
				drops = append(drops, Drop{game, f, v, msg, "물리"})
				continue
			}
			kept[f] = v
		}
		for f, msg := range consistency(kept) {
			drops = append(drops, Drop{game, f, kept[f], msg, "일관성"})
			delete(kept, f)
		}
		clean[game] = kept
	}
	return clean, drops
}
