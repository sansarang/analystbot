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
# 10분 주기 — 경기 직전 선발 교체를 잡으려면 이보다 길면 놓친다
CMD ["crawler", "-interval", "10m"]
