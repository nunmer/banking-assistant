FROM golang:1.22-alpine AS builder

WORKDIR /app
COPY mib-service/go.mod ./
COPY mib-service ./
RUN go build -o /out/mib-service .

FROM alpine:3.20

COPY --from=builder /out/mib-service /usr/local/bin/mib-service

EXPOSE 8001

CMD ["mib-service"]
