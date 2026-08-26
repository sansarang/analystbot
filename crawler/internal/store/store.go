// Package store — Redis 인터페이스.
//
// ⚠️ **Postgres에 직접 쓰지 않는다.** 스키마 결합을 피하고, 파이썬 쪽이
// 교차검증을 통과시킨 뒤에만 DB에 반영하게 한다. 크롤러가 DB를 직접 건드리면
// 검증되지 않은 값이 그대로 λ로 흘러간다.
package store

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"

	"analystbot/crawler/internal/diff"
)

const snapshotTTL = 26 * time.Hour // 하루치 + 여유

type Store struct{ rdb *redis.Client }

func New(url string) (*Store, error) {
	opt, err := redis.ParseURL(url)
	if err != nil {
		return nil, fmt.Errorf("REDIS_URL 파싱: %w", err)
	}
	return &Store{rdb: redis.NewClient(opt)}, nil
}

func (s *Store) Close() error { return s.rdb.Close() }

func latestKey(sport, date string) string  { return fmt.Sprintf("crawl:%s:%s:latest", sport, date) }
func stampKey(sport, date, hhmm string) string {
	return fmt.Sprintf("crawl:%s:%s:%s", sport, date, hhmm)
}
func changesKey(sport, date string) string { return fmt.Sprintf("crawl:%s:%s:changes", sport, date) }

// Latest 는 직전 스냅샷. 없으면 빈 맵(첫 실행).
func (s *Store) Latest(ctx context.Context, sport, date string) (diff.Snapshot, error) {
	raw, err := s.rdb.Get(ctx, latestKey(sport, date)).Bytes()
	if err == redis.Nil {
		return diff.Snapshot{}, nil
	}
	if err != nil {
		return nil, err
	}
	var snap diff.Snapshot
	if err := json.Unmarshal(raw, &snap); err != nil {
		return diff.Snapshot{}, nil // 손상된 캐시는 첫 실행처럼 다룬다
	}
	return snap, nil
}

// Save 는 최신 스냅샷과 **시각별 스냅샷**을 함께 남긴다.
//
// 시각별을 남기는 이유: 나중에 "몇 시에 바뀌었나"를 되짚을 수 있어야 한다.
// 변화 자체보다 **언제 바뀌었는지**가 정보일 때가 많다(경기 직전 교체 등).
func (s *Store) Save(ctx context.Context, sport, date string, snap diff.Snapshot,
	changes []diff.Change, now time.Time) error {
	body, err := json.Marshal(snap)
	if err != nil {
		return err
	}
	pipe := s.rdb.Pipeline()
	pipe.Set(ctx, latestKey(sport, date), body, snapshotTTL)
	pipe.Set(ctx, stampKey(sport, date, now.Format("1504")), body, snapshotTTL)
	if len(changes) > 0 {
		// 변화는 누적한다 — 하루 동안 무엇이 몇 번 바뀌었는지가 신호다
		for _, c := range changes {
			line, _ := json.Marshal(struct {
				diff.Change
				At string `json:"at"`
			}{c, now.Format(time.RFC3339)})
			pipe.RPush(ctx, changesKey(sport, date), line)
		}
		pipe.Expire(ctx, changesKey(sport, date), snapshotTTL)
	}
	pipe.Set(ctx, "crawl:heartbeat", now.Format(time.RFC3339), 2*time.Hour)
	_, err = pipe.Exec(ctx)
	return err
}
