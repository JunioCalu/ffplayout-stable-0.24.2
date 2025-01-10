import time
import asyncio
import argparse
from yt_dlp import YoutubeDL
from typing import Dict, Set, Optional

ydl_opts = {
    "call_home": False,
    "color": False,
    "skip_download": True,
    "extract_flat": True,
    "no_check_certificate": True,
    "restrict_filenames": True,
    "ignore_no_formats_error": True,
    "no_warnings": True,
    "noprogress": True,
    "verbose": False,
    "quiet": True,
}

def classify_video_status(url: str, debug: bool = True) -> str:
    """Classifica o status do vídeo com base nos metadados e exibe os valores para depuração."""

    try:
        with YoutubeDL(ydl_opts) as ydl:
            entry = ydl.extract_info(url, download=False)
            current_time = int(time.time())
            release_ts = entry.get("release_timestamp", 0)
            release_ts = 0 if release_ts in [None, "null"] else int(release_ts)

            has_duration = entry.get("duration", None)
            has_formats = entry.get("formats", [])

            sources = [
                f.get("url", "") or f.get("manifest_url", "")
                for f in has_formats
                if "url" or "manifest_url" in f
            ]
            has_live_broadcast = any("yt_live_broadcast" in s for s in sources)
            has_premiere_broadcast = any("yt_premiere_broadcast" in s for s in sources)

            if debug:
                print("\n[DEBUG] Valores usados em classify_video_status:")
                print(f"\nentry: ", entry)
                print(f"release_ts: {release_ts}")
                print(f"has_duration: {has_duration}")
                print(f"has_formats: {bool(has_formats)}")
                print(f"has_live_broadcast: {has_live_broadcast}")
                print(f"has_premiere_broadcast: {has_premiere_broadcast}")
                print(f"is_live: {entry.get('is_live', False)}")
                print(f"live_status: {entry.get('live_status', '')}")
                print(f"was_live: {entry.get('was_live', None)}")
                print(f"current_time: {current_time}")

            if (has_live_broadcast and
                entry.get("is_live", False) is True and
                entry.get("live_status", "") == "is_live" and
                entry.get("was_live", None) is False and
                not has_duration):
                return "live"

            elif (has_premiere_broadcast and
                entry.get("live_status", "") == "is_live" and
                release_ts and
                isinstance(release_ts, int) and
                entry.get("was_live", None) is False and
                has_duration and
                isinstance(has_duration, int)):
                return "upcoming_launched"

            elif (entry.get("live_status", "") == "is_upcoming" and
                release_ts and
                isinstance(release_ts, int) and
                release_ts >= current_time and
                entry.get("was_live", None) is False and
                not has_formats):
                return "upcoming_scheduled"

            elif (entry.get("live_status", "") == "post_live" or
                entry.get("live_status", "") == "was_live" and
                release_ts and
                isinstance(release_ts, int)):
                return "live_VOD"

            elif (entry.get("live_status", "") == "not_live" and
                entry.get("was_live", None) is False and
                release_ts and
                isinstance(release_ts, int)):
                return "live_VOD_Upcoming"

            return "VOD"

    except Exception as e:
        print(f"\nErro ao classificar novos vídeos': {e}")

async def monitor_youtube_channel(url: str, interval: int = 5, debug: bool = False, initial_load: bool = True) -> None:
    """
    Monitora um canal do YouTube para novos vídeos, combinando carregamento inicial e monitoramento contínuo.
    
    Args:
        url: URL do canal ou playlist do YouTube
        interval: Intervalo entre verificações em segundos
        debug: Ativa modo de depuração
        initial_load: Se True, indica primeira execução para carregar IDs existentes
    """
    seen_ids: Set[str] = set()
    videos_loaded = 0
    
    def process_entry(entry: Dict, is_initial: bool = False) -> Optional[str]:
        """Processa uma entrada de vídeo e retorna o ID se for novo."""
        nonlocal videos_loaded
        if isinstance(entry, dict):
            video_id = entry.get('id')
            live_status = entry.get('live_status', '')
            
            if video_id and video_id not in seen_ids:
                if is_initial:
                    seen_ids.add(video_id)
                    videos_loaded += 1
                    url = f"https://www.youtube.com/watch?v={video_id}"
                    #status = classify_video_status(url, debug=debug)
                    print(f"\rCarregando vídeos... {videos_loaded} vídeos encontrados", end="", flush=True)
                    
                    # Durante a carga inicial, só processa e salva IDs de vídeos ao vivo
                    if live_status == 'is_live':
                        seen_ids.add(video_id)
                        url = f"https://www.youtube.com/watch?v={video_id}"
                        status = classify_video_status(url, debug=debug)
                        print(f"[CARGA INICIAL] Vídeo ao vivo detectado: https://www.youtube.com/watch?v={video_id}, Status: {status}")
                else:
                    # Após a carga inicial, processa todos os vídeos normalmente
                    seen_ids.add(video_id)
                    url = f"https://www.youtube.com/watch?v={video_id}"
                    status = classify_video_status(url, debug=debug)
                    print(f"\nNovo vídeo detectado: https://www.youtube.com/watch?v={video_id}, Status: {status}")
                return video_id
        return None

    while True:
        if initial_load:
            print("Iniciando carregamento de vídeos...")
        else:
            print("\nVerificando por novos vídeos...")
        
        try:
            with YoutubeDL(ydl_opts) as ydl:
                result = ydl.extract_info(url, download=False)
                
                if 'entries' in result:
                    for entry in result['entries']:
                        if isinstance(entry, dict):
                            if 'entries' in entry:  # Processa subentradas
                                for subentry in entry['entries']:
                                    process_entry(subentry, is_initial=initial_load)
                            else:
                                process_entry(entry, is_initial=initial_load)
                
                if initial_load:
                    print(f"\nCarregamento inicial concluído")
                    initial_load = False  # Próximas iterações não são mais carga inicial
                    videos_loaded = 0  # Reseta o contador para próximas verificações
                
        except Exception as e:
            print(f"\nErro ao {'carregar vídeos iniciais' if initial_load else 'monitorar novos vídeos'}: {e}")
        
        await asyncio.sleep(interval)

async def main():
    parser = argparse.ArgumentParser(description="Monitora um canal do YouTube para novos vídeos com classificação detalhada.")
    parser.add_argument(
        "--url",
        type=str,
        help="URL do canal ou playlist do YouTube para monitorar"
    )
    parser.add_argument(
        "-i", "--interval",
        type=int,
        default=5,
        help="Intervalo entre verificações (em segundos). Padrão: 300"
    )
    parser.add_argument(
        "-d", "--debug",
        action="store_true",
        help="Ativa o modo de depuração para mensagens detalhadas de erro"
    )

    args = parser.parse_args()
    
    print(f"Monitorando o canal: {args.url}")
    print(f"Intervalo de verificação: {args.interval} segundos")

    await monitor_youtube_channel(args.url, args.interval, args.debug)

if __name__ == "__main__":
    asyncio.run(main())
