# ✅ Критично: 1.23 + кросс-компилятор для ARM
ARG HONEYPOT_BASE_IMAGE=golang:1.23-bookworm
FROM ${HONEYPOT_BASE_IMAGE} AS build

# Устанавливаем зависимости для CGO + кросс-компиляции
RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates \
    libpcap-dev pkg-config \
    gcc-arm-linux-gnueabihf \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone --depth 1 https://github.com/mushorg/glutton.git /src/glutton
WORKDIR /src/glutton

# ✅ Настройка CGO для кросс-компиляции под ARMv7
ENV CGO_ENABLED=1 \
    CC=arm-linux-gnueabihf-gcc \
    CXX=arm-linux-gnueabihf-g++ \
    PKG_CONFIG_PATH=/usr/lib/arm-linux-gnueabihf/pkgconfig \
    GOOS=linux \
    GOARCH=arm \
    GOARM=7

RUN go build -o /out/glutton .

# ✅ Финальный образ: минимальный + рантайм-зависимости
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpcap0.8 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /out/glutton /usr/local/bin/glutton
RUN chmod +x /usr/local/bin/glutton
CMD ["/usr/local/bin/glutton", "--config", "/etc/glutton/glutton.yml"]
