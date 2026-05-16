ARG GLUTTON_BUILDER_IMAGE=golang:1.23-bookworm
ARG GLUTTON_RUNTIME_IMAGE=debian:bookworm-slim

FROM ${GLUTTON_BUILDER_IMAGE} AS build

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ca-certificates \
    libpcap-dev \
    pkg-config \
    gcc-arm-linux-gnueabihf \
    g++-arm-linux-gnueabihf \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

RUN git clone --depth 1 https://github.com/mushorg/glutton.git /src/glutton

WORKDIR /src/glutton

ENV CGO_ENABLED=1 \
    GOOS=linux \
    GOARCH=arm \
    GOARM=7 \
    CC=arm-linux-gnueabihf-gcc \
    CXX=arm-linux-gnueabihf-g++

# Важно: upstream собирает app/server.go, а не корневой пакет.
RUN go build -o /out/glutton ./app

FROM ${GLUTTON_RUNTIME_IMAGE}

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libpcap0.8 \
    iptables \
    iproute2 \
    procps \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /out/glutton /usr/local/bin/glutton
COPY config.yaml /etc/glutton/config.yaml
COPY rules.yaml /etc/glutton/rules.yaml

RUN chmod +x /usr/local/bin/glutton && \
    mkdir -p /var/lib/glutton /logs

EXPOSE 5000/tcp 5001/udp \
    110/tcp 135/tcp 139/tcp 143/tcp 445/tcp 465/tcp 515/tcp 548/tcp 554/tcp \
    587/tcp 631/tcp 873/tcp 993/tcp 995/tcp 1883/tcp 2049/tcp 2375/tcp \
    3389/tcp 5000/tcp 5357/tcp 5432/tcp 5900/tcp 5985/tcp 6443/tcp \
    8000/tcp 8291/tcp 8899/tcp 9100/tcp \
    161/udp 5060/udp

CMD ["/usr/local/bin/glutton", "--confpath", "/etc/glutton", "--ssh", "22", "--var-dir", "/var/lib/glutton"]
