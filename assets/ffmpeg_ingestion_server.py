import subprocess
import signal
import sys
import time

def start_ffmpeg_to_mpv(listen_url):
    """
    Inicia o FFmpeg no modo de escuta e redireciona o stream para o MPV via pipe.
    O MPV é iniciado uma vez e mantém a conexão aberta, enquanto o FFmpeg é reiniciado em caso de falhas.

    Args:
        listen_url (str): URL para o FFmpeg escutar (exemplo: "-f live_flv -listen 1 -i rtmp://127.0.0.1:1936/live/stream").
    """
    mpv_proc = None
    try:
        # Iniciar o MPV uma vez
        print("Iniciando o MPV...")
        mpv_command = [
            "mpv", "-", "--keep-open", "--idle", "--profile=fast",
            "--hwdec=auto", "--cache=yes", "--demuxer-max-bytes=50M",
            "--demuxer-max-back-bytes=50M", "--cache-secs=30"
        ]
        mpv_proc = subprocess.Popen(mpv_command, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
        print("MPV iniciado.")

        # Loop para reiniciar o FFmpeg em caso de falhas
        while True:
            try:
                print(f"Iniciando o FFmpeg no modo de escuta: {listen_url}")

                ffmpeg_command = [
                    "ffmpeg",
                    *listen_url.split(),             # Dividir a URL em argumentos
                    "-c", "copy",                    # Modo de cópia
                    "-f", "mpegts",                  # Formato MPEG-TS
                    "pipe:1"                         # Redirecionar saída para o pipe
                ]

                # Iniciar o FFmpeg e conectar ao stdin do MPV
                ffmpeg_proc = subprocess.Popen(ffmpeg_command, stdout=mpv_proc.stdin, stderr=subprocess.DEVNULL)
                print("FFmpeg iniciado. Pressione Ctrl+C para encerrar.")

                # Aguardar o término do FFmpeg
                ffmpeg_proc.wait()

                print("FFmpeg caiu. Reiniciando em 5 segundos...")
                time.sleep(5)

            except KeyboardInterrupt:
                cleanup(ffmpeg_proc, mpv_proc)
                break

            except Exception as e:
                print(f"Erro inesperado: {e}. Reiniciando em 5 segundos...")
                time.sleep(5)

    except KeyboardInterrupt:
        cleanup(None, mpv_proc)

    except Exception as e:
        print(f"Erro crítico: {e}")
        if mpv_proc:
            mpv_proc.terminate()
        sys.exit(1)

def cleanup(ffmpeg_proc, mpv_proc):
    """ Finaliza os processos do FFmpeg e MPV. """
    print("Encerrando os processos...")
    if ffmpeg_proc and ffmpeg_proc.poll() is None:
        ffmpeg_proc.terminate()
    if mpv_proc and mpv_proc.poll() is None:
        mpv_proc.terminate()
    sys.exit(0)

if __name__ == "__main__":
    # Configuração padrão
    DEFAULT_LISTEN_URL = "-f live_flv -listen 1 -i rtmp://127.0.0.1:1936/live/stream"

    # Iniciar o servidor
    start_ffmpeg_to_mpv(DEFAULT_LISTEN_URL)
