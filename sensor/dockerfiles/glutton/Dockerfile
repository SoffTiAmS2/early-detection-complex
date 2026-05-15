ARG HONEYPOT_BASE_IMAGE=golang:1.23-bookworm
FROM ${HONEYPOT_BASE_IMAGE} AS build

RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates \
    libpcap-dev pkg-config \
    gcc-arm-linux-gnueabihf \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone --depth 1 https://github.com/mushorg/glutton.git /src/glutton
WORKDIR /src/glutton

ENV CGO_ENABLED=1 \
    CC=arm-linux-gnueabihf-gcc \
    CXX=arm-linux-gnueabihf-g++ \
    PKG_CONFIG_PATH=/usr/lib/arm-linux-gnueabihf/pkgconfig \
    GOOS=linux \
    GOARCH=arm \
    GOARM=7

RUN go build -o /out/glutton .

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpcap0.8 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /out/glutton /usr/local/bin/glutton
RUN chmod +x /usr/local/bin/glutton
EXPOSE 110 135 139 143 161/udp 445 465 515 548 554 587 631 873 993 995 1883 2049 2375 3389 5000 5060/udp 5357 5432 5900 5985 6443 8000 8291 8899 9100
CMD ["/usr/local/bin/glutton", "--config", "/etc/glutton/glutton.yml"]
