#!/bin/bash

# Variáveis padrão
DEFAULT_IP="127.0.0.1"
DEFAULT_RTMP_DETAILS=":1936/live/stream"
FFMPEG_RETRY_DELAY=5
FIFO_PATH="/tmp/ffmpeg_mpv_fifo"

# Função para exibir o uso do script
usage() {
    echo "Uso: $0 [--ip IP_ADDRESS] [--rtmp-details PORT_AND_STREAMKEY]"
    echo "  --ip                Define o endereço IP (padrão: 127.0.0.1)"
    echo "  --rtmp-details      Define os detalhes RTMP (padrão: :1936/live/stream)"
    exit 1
}

# Processa argumentos
IP="$DEFAULT_IP"
RTMP_DETAILS="$DEFAULT_RTMP_DETAILS"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --ip)
            IP="$2"
            shift 2
            ;;
        --rtmp-details)
            RTMP_DETAILS="$2"
            shift 2
            ;;
        *)
            usage
            ;;
    esac
done

# Construir a URL de escuta
LISTEN_URL="rtmp://$IP$RTMP_DETAILS"

# Função de limpeza ao encerrar
cleanup() {
    echo "Encerrando os processos..."
    if [[ -n "$MPV_PID" ]]; then
        kill "$MPV_PID" 2>/dev/null
        wait "$MPV_PID" 2>/dev/null
    fi
    if [[ -n "$FFMPEG_PID" ]]; then
        kill "$FFMPEG_PID" 2>/dev/null
        wait "$FFMPEG_PID" 2>/dev/null
    fi
    if [[ -p "$FIFO_PATH" || -e "$FIFO_PATH" ]]; then
        echo "Removendo o FIFO em $FIFO_PATH..."
        rm -f "$FIFO_PATH"
    fi
    exit 0
}

# Capturar sinais de interrupção para limpeza
trap cleanup SIGINT SIGTERM

# Certificar-se de que o named pipe (FIFO) está limpo e recriado
if [[ -p "$FIFO_PATH" || -e "$FIFO_PATH" ]]; then
    echo "Removendo o named pipe existente em $FIFO_PATH..."
    rm -f "$FIFO_PATH"
fi

echo "Criando o named pipe em $FIFO_PATH..."
mkfifo "$FIFO_PATH"
if [[ ! -p "$FIFO_PATH" ]]; then
    echo "Falha ao criar o FIFO em $FIFO_PATH."
    exit 1
fi

# Iniciar o MPV para ler do named pipe
echo "Iniciando o MPV..."
mpv "$FIFO_PATH" --keep-open --idle --profile=fast --hwdec=auto --cache=yes \
    --demuxer-lavf-format=mpegts --demuxer-max-bytes=50M --demuxer-max-back-bytes=50M --cache-secs=30 &
MPV_PID=$!
echo "MPV iniciado com PID: $MPV_PID"

# Verificar se o MPV foi iniciado com sucesso
if ! kill -0 "$MPV_PID" 2>/dev/null; then
    echo "Falha ao iniciar o MPV."
    cleanup
fi

# Loop para reiniciar o FFmpeg em caso de falhas
while true; do
    echo "Iniciando o FFmpeg no modo de escuta: $LISTEN_URL"

    # Iniciar o processo FFmpeg
    ffmpeg -y -f live_flv -listen 1 -i "$LISTEN_URL" -c copy -f mpegts "$FIFO_PATH" &
    FFMPEG_PID=$!
    wait "$FFMPEG_PID"  # Espera o processo FFmpeg terminar

    echo "FFmpeg caiu. Reiniciando em ${FFMPEG_RETRY_DELAY} segundos..."
    sleep "$FFMPEG_RETRY_DELAY"
done
