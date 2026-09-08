# AnalystBot 크롤러 (Go) — Railway 3번째 서비스.
#
# 파이썬 봇/스케줄러와 **별도 서비스**다. 크롤러가 죽어도 봇은 계속 응답한다.
# Postgres/Redis는 공유하되, 크롤러는 **Redis에만 쓴다**(스키마 결합 회피).

FROM golang:1.26-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
# CGO 끄고 정적 링크 — 런타임 이미지를 최소로 만든다
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/crawler ./cmd/crawler

FROM alpine:3.20
# HTTPS 조회에 필요 / tzdata: KST 날짜 경계 계산의 근간
RUN apk add --no-cache ca-certificates tzdata
COPY --from=build /out/crawler /usr/local/bin/crawler
ENV TZ=Asia/Seoul
# 평시 10분 — 타순 창에 들어선 종목만 2분. 창은 경기 starts_at으로 계산한다.
#
# 🔴 [CRW-6 2026-09-08] **여기가 실행 명령의 원본이다.** 2026-09-01 에 "10m 이
#    의도다"라고 결정하고 `tools/deploy.sh` 의 문자열만 고쳐 항목을 닫았는데,
#    그 문자열은 `railway up` 에 전달되지 않는다(echo 전용). 그래서 운영은
#    일주일 내내 60분이었고 KBO 라인업 공시를 최대 1시간 늦게 봤다.
#    (실질 피해는 가속 창 밖 구간뿐이다 — KBO 는 T-4:30 부터 2분 주기다.)
#    부하: 한 틱은 KBO ≈6요청·NPB ≈7요청. 10분이면 시간당 ≈78요청으로,
#    이미 매일 도는 가속 창(2분 ≈195요청/시간)보다 낮다.
CMD ["crawler", "-interval", "10m"]
