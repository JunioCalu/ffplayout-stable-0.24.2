from yt_dlp import YoutubeDL

def get_playlist_ids(url):
    ydl_opts = {
        'call_home': False,
        'skip_download': True,
        'extract_flat': True,
        'no_color': True,
        'noplaylist': True,
        'no_warnings': True,
        'noprogress': True,
        'verbose': False,
    }
    
    video_ids = []
    
    with YoutubeDL(ydl_opts) as ydl:
        try:
            # Extrai as informações do canal/playlist
            result = ydl.extract_info(url, download=False)
            
            # Se for um único vídeo
            if isinstance(result, dict):
                webpage_url = result.get('webpage_url', '').lower()
                print("webpage_url on if num 1:", webpage_url)
                entry_url = result.get('url', '').lower()
                print("Subentry URL on if num 1:", entry_url)
                if result.get('_type') == 'url' and result.get('id'):
                    video_ids.append(result['id'])
                
                # Se tiver entradas (playlist/canal)
                if 'entries' in result:
                    for entry in result['entries']:
                        # Verifica se é uma playlist
                        if isinstance(entry, dict):
                            # Ignora se for playlist de shorts
                            webpage_url = entry.get('webpage_url', '').lower()
                            print("webpage_url on if num 2:", webpage_url)
                            entry_url = entry.get('url', '').lower()
                            print("Subentry URL on if num 2:", entry_url)
                            
                            # Ignora se for um short
                            if 'shorts' in webpage_url or 'shorts' in entry_url:
                                print("Ignored short video on if:", entry)
                                continue
                            
                            # Se a entrada tiver suas próprias entries (sub-playlist)
                            print("continuando")
                            if 'entries' in entry:
                                for subentry in entry['entries']:
                                    webpage_url = subentry.get('webpage_url', '').lower()
                                    print("webpage_url on if num 3:", webpage_url)
                                    entry_url = subentry.get('url', '').lower()
                                    print("Subentry URL on if num 3:", entry_url)
                                    if (isinstance(subentry, dict) and 
                                        subentry.get('_type') == 'url' and 
                                        subentry.get('id')):
                                        video_ids.append(subentry['id'])
                            # Se for um vídeo direto
                            elif (entry.get('_type') == 'url' and 
                                  entry.get('id')):
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
