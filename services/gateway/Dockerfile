FROM golang:1.22-alpine AS build
WORKDIR /src
COPY . .
RUN go env -w GOPROXY=https://proxy.golang.org
RUN go mod download
RUN go get github.com/go-redis/redis/v8@v8.11.5 github.com/gorilla/websocket@v1.5.0
RUN go mod tidy
RUN go build -o /usr/local/bin/gateway ./

FROM build AS test
RUN go test -v -count=1 ./...

FROM alpine:3.18
RUN apk add --no-cache ca-certificates
COPY --from=build /usr/local/bin/gateway /usr/local/bin/gateway
EXPOSE 8080
CMD ["/usr/local/bin/gateway", "-addr", ":8080"]
