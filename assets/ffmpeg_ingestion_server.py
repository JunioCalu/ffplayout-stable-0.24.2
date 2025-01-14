import subprocess
import signal
import sys

def start_ffmpeg_to_mpv(listen_url):
    """
    Inicia o FFmpeg no modo de escuta e redireciona o stream para o MPV via pipe.

    Args:
        listen_url (str): URL para o FFmpeg escutar (exemplo: "-f live_flv -listen 1 -i rtmp://127.0.0.1:1936/live/stream").
    """
    try:
        # Iniciar o FFmpeg no modo de escuta e criar um pipe para o MPV
        print(f"Iniciando o FFmpeg no modo de escuta: {listen_url}")
        ffmpeg_command = [
            "ffmpeg",
            *listen_url.split(),  # Dividir a URL em argumentos
            "-c", "copy",        # Modo de cópia
            "-f", "mpegts",      # Formato MPEG-TS
            "pipe:1"              # Redirecionar saída para o pipe
        ]

        # Iniciar o MPV
        mpv_command = ["mpv", "-", "--profile=fast", "--hwdec=auto", "--cache=yes", "--demuxer-max-bytes=50M", "--demuxer-max-back-bytes=50M", "--cache-secs=30"]

        # Executar os processos
        ffmpeg_proc = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        mpv_proc = subprocess.Popen(mpv_command, stdin=ffmpeg_proc.stdout, stderr=subprocess.DEVNULL)

        print("FFmpeg e MPV iniciados. Pressione Ctrl+C para encerrar.")

        # Aguardar o término dos processos
        signal.signal(signal.SIGINT, lambda *_: cleanup(ffmpeg_proc, mpv_proc))
        ffmpeg_proc.wait()
        mpv_proc.wait()

    except Exception as e:
        print(f"Erro ao iniciar FFmpeg ou MPV: {e}")
        sys.exit(1)

def cleanup(ffmpeg_proc, mpv_proc):
    """ Finaliza os processos do FFmpeg e MPV. """
    print("Encerrando os processos...")
    ffmpeg_proc.terminate()
    mpv_proc.terminate()
    sys.exit(0)

if __name__ == "__main__":
    # Configuração padrão
    DEFAULT_LISTEN_URL = "-f live_flv -listen 1 -i rtmp://127.0.0.1:1936/live/stream"

    # Iniciar o servidor
    start_ffmpeg_to_mpv(DEFAULT_LISTEN_URL)
