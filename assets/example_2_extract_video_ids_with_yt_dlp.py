from yt_dlp import YoutubeDL

def get_playlist_ids(url):
    ydl_opts = {
        'call_home': False,
        #'live_from_start': True,
        #'forcejson': True,
        #'logger': YTDL_Logger(),
        #'cookiefile': '/home/junio/livebot/cookies.txt',
        #'extract_flat': 'in_playlist',     # Equivale ao --flat-playlist
        'skip_download': True,            # Não baixa, só extrai ID
        'extract_flat': True,      # equivalent to --flat-playlist
        #'simulate': True,          # equivalent to -s
        #'dump_single_json': True,   # equivalent to --dump-single-json
        'no_color': True,
        #'noplaylist': True,
        'no_warnings': True,
        'noprogress': True,
        'verbose': False,
        'quiet': True,             # reduce output
        #'lazy_playlist': True,
        # Adiciona um extractor específico para ignorar shorts
        #'match_filter': 'webpage_url!=*/shorts/',
    }

    video_ids = []

    with YoutubeDL(ydl_opts) as ydl:
        try:
            # Extrai as informações do canal/playlist
            result = ydl.extract_info(url, download=False)

            # Se tiver entradas (playlist/canal)
            if 'entries' in result:
                for entry in result['entries']:
                    #print("\nentries on if: ", entry)
                    if isinstance(entry, dict):
                        # Processa subentradas (caso entries contenha outra lista de vídeos)
                        if 'entries' in entry:
                            for subentry in entry['entries']:
                                print("\nentries on second if: ", subentry)
                                if isinstance(subentry, dict):
                                    webpage_url = entry.get('webpage_url', '').lower()
                                    print("webpage_url on if:", webpage_url)
                                    entry_url = subentry.get('url', '').lower()
                                    print("Subentry URL on if:", entry_url)
                                    
                                    # Ignora se for um short
                                    if 'shorts' in webpage_url or 'shorts' in entry_url:
                                        print("Ignored short video on if:", subentry)
                                        continue

                                    # Adiciona o ID do vídeo
                                    if subentry.get('id') and subentry.get('_type') == 'url':
                                        video_ids.append(subentry['id'])

                        # Verifica diretamente a entrada se ela contiver uma URL
                        else:
                            webpage_url = entry.get('webpage_url', '').lower()
                            print("webpage_url on else:", webpage_url)
                            entry_url = entry.get('url', '').lower()
                            print("Entry URL on else:", entry_url)

                            if 'shorts' in webpage_url or 'shorts' in entry_url:
                                print("Ignored short entry:", entry)
                                continue

                            # Adiciona o ID do vídeo
                            if entry.get('id') and entry.get('_type') == 'url':
                                video_ids.append(entry['id'])

            return video_ids

        except Exception as e:
            print(f"Error: {str(e)}")
            return []

# Exemplo de uso
url = "https://www.youtube.com/@JunioCalu"
video_ids = get_playlist_ids(url)
for video in video_ids:
    print(video)
