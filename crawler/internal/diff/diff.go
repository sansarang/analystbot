// Package diff — 시각별 스냅샷을 비교해 **무엇이 바뀌었는지** 뽑는다.
//
// 왜 필요한가:
//
//	한 번만 긁으면 "지금 상태"만 안다. 변화는 못 본다.
//	    18:00  선발 임찬규
//	    18:20  선발 최원태   ← 교체! 이게 정보다.
//	선발 교체·라인업 변경은 경기 직전에 일어나고, 시장이 늦게 반영하는 몇 안 되는
//	정보다. 스냅샷 하나만 보는 지금 구조로는 이걸 영원히 못 본다.
//
// ⚠️ 중요도 판단은 여기서 하지 않는다. "무엇이 바뀌었다"만 사실로 기록하고,
// 그것이 경기에 어떤 영향인지는 판정(Claude)이 결정한다 — 크롤러가 임의 가중치를
// 만들면 측정되지 않은 튜닝이 된다.
package diff

import (
	"fmt"
	"sort"
)

// Change 는 한 필드의 변화 하나다.
type Change struct {
	Game  string `json:"game"`  // "원정@홈"
	Field string `json:"field"` // "home_pitcher", "lineup" 등
	From  string `json:"from"`
	To    string `json:"to"`
	Kind  string `json:"kind"` // "added" | "removed" | "changed"
}

func (c Change) String() string {
	switch c.Kind {
	case "added":
		return fmt.Sprintf("%s %s 신규: %s", c.Game, c.Field, c.To)
	case "removed":
		return fmt.Sprintf("%s %s 사라짐: %s", c.Game, c.Field, c.From)
	default:
		return fmt.Sprintf("%s %s 변경: %s → %s", c.Game, c.Field, c.From, c.To)
	}
}

// Snapshot 은 한 시점의 수집 결과다. game → field → value.
type Snapshot map[string]map[string]string

// Compare 는 old→new 변화를 뽑는다. old가 비어 있으면(첫 수집) 변화 없음으로 본다.
//
// ⚠️ 첫 수집을 "전부 신규"로 내보내면 매일 첫 실행마다 알림이 폭주한다.
// 실사고 유형: 관측 장치가 본체보다 시끄러우면 아무도 안 본다.
func Compare(old, new Snapshot) []Change {
	if len(old) == 0 {
		return nil
	}
	var out []Change
	for game, fields := range new {
		prev, seen := old[game]
		if !seen {
			continue // 새로 생긴 경기 — 편성 변경이지 '변화'가 아니다
		}
		for f, v := range fields {
			pv, had := prev[f]
			switch {
			case !had && v != "":
				out = append(out, Change{game, f, "", v, "added"})
			case had && v != pv:
				if v == "" {
					out = append(out, Change{game, f, pv, "", "removed"})
				} else {
					out = append(out, Change{game, f, pv, v, "changed"})
				}
			}
		}
	}
	// 출력 순서를 고정한다 — 같은 입력이면 같은 결과여야 비교·테스트가 가능하다
	sort.Slice(out, func(i, j int) bool {
		if out[i].Game != out[j].Game {
			return out[i].Game < out[j].Game
		}
		return out[i].Field < out[j].Field
	})
	return out
}

// Notable 은 사람이 즉시 알아야 할 변화만 거른다.
//
// ⚠️ 여기서 "얼마나 중요한가"를 점수화하지 않는다. **어떤 필드가 바뀌면 알린다**는
// 목록일 뿐이며, 실제 영향 판단은 판정이 한다.
var notableFields = map[string]bool{
	"home_pitcher":   true, // 선발 교체 — 가장 큰 변수
	"away_pitcher":   true,
	"lineup_home":    true, // 라인업 확정·변경 (홈·원정 분리)
	"lineup_away":    true,
	"starter_status": true, // 予告 → 확정
	"status":         true, // 우천 취소·연기
}

func Notable(changes []Change) []Change {
	var out []Change
	for _, c := range changes {
		if notableFields[c.Field] {
			out = append(out, c)
		}
	}
	return out
}
