#!/bin/bash

# Parâmetros do script
URL="$1"
RTMP_DESTINATION="rtmp://127.0.0.1:1936/live/stream"
STREAM_OPTIONS="--hls-live-edge 6 --ringbuffer-size 64M -4 --stream-sorting-excludes '>720p' --default-stream best"

# Verifica se a URL foi fornecida
if [ -z "$URL" ]; then
  echo "Uso: $0 <URL do vídeo/stream>"
  exit 1
fi

# Executa streamlink e redireciona o fluxo para ffmpeg
streamlink $STREAM_OPTIONS --url "$URL" -o - | \
ffmpeg -re -i pipe:0 -c copy -f flv "$RTMP_DESTINATION"
