#!/bin/bash

# Configurações padrão
DEFAULT_LISTEN_URL="-f live_flv -listen 1 -i rtmp://127.0.0.1:1936/live/stream" # Porta de escuta padrão para o servidor FFmpeg

# Função para exibir uso
usage() {
  echo "Uso: $0 [--listen-url <url>]"
  echo
  echo "  --listen-url <url>  URL de escuta do FFmpeg (padrão: $DEFAULT_LISTEN_URL)"
  exit 1
}

# Processar argumentos
LISTEN_URL=$DEFAULT_LISTEN_URL

while [[ $# -gt 0 ]]; do
  case $1 in
    --listen-url)
      LISTEN_URL=$2
      shift 2
      ;;
    *)
      usage
      ;;
  esac
done

# Verificar se FFmpeg está instalado
if ! command -v ffmpeg &> /dev/null; then
  echo "Erro: FFmpeg não está instalado. Por favor, instale-o antes de executar este script."
  exit 1
fi

# Verificar se MPV está instalado
if ! command -v mpv &> /dev/null; then
  echo "Erro: MPV não está instalado. Por favor, instale-o antes de executar este script."
  exit 1
fi

# Iniciar o servidor FFmpeg no modo de escuta e usar pipes para transferir o stream ao MPV
echo "Iniciando o servidor FFmpeg no modo de escuta com $LISTEN_URL..."
ffmpeg $LISTEN_URL -c copy -f mpegts pipe:1 | mpv - --profile=fast --hwdec=auto --cache=yes --demuxer-max-bytes=50M --demuxer-max-back-bytes=50M --cache-secs=30 &

# Obter o PID do processo
FFMPEG_MPV_PID=$!

# Limpeza ao encerrar o script
trap "
  echo 'Encerrando o servidor e o player...';
  kill $FFMPEG_MPV_PID &> /dev/null;
  exit 0;
" SIGINT SIGTERM

# Manter o script em execução
echo "Servidor e player em execução. Pressione Ctrl+C para encerrar."
wait
