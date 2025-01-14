import subprocess
import sys

def main():
    if len(sys.argv) < 2:
        print("Uso: python streamlink_to_ffmpeg.py <URL do vídeo/stream>")
        sys.exit(1)

    url = sys.argv[1]
    rtmp_destination = "rtmp://127.0.0.1:1936/live/stream"
    stream_options = [
        "streamlink",
        "--hls-live-edge", "6",
        "--ringbuffer-size", "64M",
        "-4",
        "--stream-sorting-excludes", ">720p",
        "--default-stream", "best",
        "--url", url,
        "-o", "-"
    ]

    ffmpeg_command = [
        "ffmpeg",
        "-re",
        "-i", "pipe:0",
        "-c", "copy",
        "-f", "flv",
        rtmp_destination
    ]

    try:
        # Inicia o streamlink e conecta ao ffmpeg usando pipes
        process_streamlink = subprocess.Popen(stream_options, stdout=subprocess.PIPE)
        process_ffmpeg = subprocess.Popen(ffmpeg_command, stdin=process_streamlink.stdout)

        # Aguarda o término dos processos
        process_streamlink.stdout.close()  # Fecha o stdout do streamlink no processo principal
        process_ffmpeg.communicate()

    except KeyboardInterrupt:
        print("Interrompido pelo usuário.")
        sys.exit(0)
    except Exception as e:
        print(f"Erro: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
