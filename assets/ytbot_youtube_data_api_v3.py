import os
import json
import signal
import logging
import sqlite3
import asyncio
import argparse
import subprocess
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime
from urllib.parse import urlparse
import aiohttp
import time

# Bibliotecas da Google para a YouTube Data API
import googleapiclient.discovery
import googleapiclient.errors

# =============================================================================
# CONFIGURAÇÕES GLOBAIS
# =============================================================================

DB_DIR = os.path.expanduser("~/livebot/db")
CHANNELS_FILE = os.path.expanduser("~/livebot/channels.json")

# Intervalo de checagem em segundos (padrão: 5 minutos = 300).
SLEEP_INTERVAL = 300

MAX_RETRIES = 3

# Substitua pela sua própria chave ou utilize OAuth
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "SUA_CHAVE_AQUI")

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.expanduser('~/livebot/bot.log')),
        logging.StreamHandler()
    ]
)

async def log_message(message: str, debug: bool = False):
    """
    Função auxiliar para logging.
    
    Args:
        message: Mensagem a ser logada
        debug: Se True, imprime também no console (via print)
    """
    logging.info(message)
    if debug:
        print(f"[DEBUG] {message}")

# =============================================================================
# YouTube Data API - Inicialização do client
# =============================================================================
#
# Em produção, você pode querer inicializar este client em outro lugar,
# ou ainda usar OAuth. Aqui, uso apenas a builder com a developerKey.
#

def get_youtube_service():
    """
    Retorna um objeto de serviço para interagir com a API do YouTube Data API v3.
    Você deve garantir que a variável YOUTUBE_API_KEY esteja definida.
    """
    api_service_name = "youtube"
    api_version = "v3"

    return googleapiclient.discovery.build(
        api_service_name,
        api_version,
        developerKey=YOUTUBE_API_KEY
    )

# =============================================================================
# MONITORAMENTO (AGORA VIA API) EM VEZ DE YT-DLP
# =============================================================================

class TabMonitor:
    """
    Classe para monitorar os vídeos de um canal no YouTube usando a
    API oficial. Substitui o processo de "abrir abas" via yt-dlp.
    """
    def __init__(self, rate_limit: int = 5, chunk_size: int = 3):
        """
        Inicializa o monitor.
        
        Args:
            rate_limit: Número máximo de requisições simultâneas
            chunk_size: Tamanho do chunk para processamento (por compatibilidade)
        """
        self.rate_limit = asyncio.Semaphore(rate_limit)
        self.chunk_size = chunk_size
        self.session = None
        self.youtube = get_youtube_service()

    async def __aenter__(self):
        """Inicializa uma sessão HTTP do aiohttp (pode ser útil se for preciso)."""
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Fecha a sessão HTTP."""
        if self.session:
            await self.session.close()

    async def monitor_tabs(self, channel_urls: List[str], debug: bool = False) -> Set[str]:
        """
        Faz a checagem de vídeos de cada canal via YouTube Data API.
        
        Args:
            channel_urls: Lista de URLs do canal (ex.: https://www.youtube.com/@CanalXYZ)
            debug: Flag para ativar logs de debug
            
        Returns:
            Conjunto (set) de IDs de vídeos encontrados.
        """
        await log_message(f"Iniciando monitoramento de {len(channel_urls)} canal(is) via YouTube API", debug=debug)
        
        valid_urls = self._validate_urls(channel_urls)
        if not valid_urls:
            await log_message("Nenhuma URL válida fornecida", debug=debug)
            return set()

        # Neste exemplo, não vou usar chunk_size “por abas”,
        # pois a API oficial não funciona com /live, /community etc.
        # Em vez disso, vamos varrer cada canal e pegar vídeos recentes.
        all_video_ids = set()

        async with self:  # Usa o próprio objeto como context manager
            for url_index, chan_url in enumerate(valid_urls, start=1):
                try:
                    await log_message(f"Processando canal {url_index}/{len(valid_urls)}: {chan_url}", debug=debug)
                    channel_id = await self._extract_channel_id(chan_url)
                    
                    if channel_id:
                        # Pega lista de vídeos do canal
                        video_ids = await self._fetch_channel_videos(channel_id, debug)
                        all_video_ids.update(video_ids)
                    else:
                        await log_message(f"Não foi possível extrair channel_id de {chan_url}", debug=debug)
                except Exception as e:
                    await log_message(f"Erro ao processar canal {chan_url}: {e}", debug=debug)
                    continue

        await log_message(f"Total de vídeos (IDs únicos) encontrados: {len(all_video_ids)}", debug=debug)
        return all_video_ids

    def _validate_urls(self, urls: List[str]) -> List[str]:
        """
        Valida e normaliza as URLs fornecidas, assegurando que sejam do YouTube.
        """
        valid_urls = []
        for url in urls:
            try:
                parsed = urlparse(url)
                if parsed.scheme and parsed.netloc and "youtube.com" in parsed.netloc:
                    clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip('/')
                    valid_urls.append(clean_url)
            except Exception:
                pass
        return valid_urls

    async def _extract_channel_id(self, channel_url: str) -> Optional[str]:
        """
        Tenta obter o channelId real a partir da URL.  
        Exemplo de formatos de URL suportados:
        - https://www.youtube.com/@CanalXYZ
        - https://www.youtube.com/channel/UCxxxx
        
        Se for `channel/UCxxxx`, já temos o ID.  
        Se for `@userName`, chamamos a API para descobrir o ID.
        """
        # Caso seja formato /channel/UCxxxx, extraímos diretamente
        if "/channel/" in channel_url:
            return channel_url.split("/channel/")[-1]

        # Caso seja /@username, precisamos usar "search" ou "channels" endpoint para descobrir o ID
        if "/@" in channel_url:
            username = channel_url.split("/@")[-1]
            # Chama a API para resolver esse username em channelId
            # doc: https://developers.google.com/youtube/v3/docs/channels/list
            try:
                request = self.youtube.channels().list(
                    part="id",
                    forUsername=username  # Nem sempre é 100% compatível; pode ser que precise outro approach
                )
                response = request.execute()
                items = response.get("items", [])
                if items:
                    return items[0]["id"]
            except Exception:
                # Se falhar, tentamos um fallback usando 'search' endpoint
                pass

            # Fallback: também pode-se usar 'search' com type='channel' e q=username
            try:
                request = self.youtube.search().list(
                    part="snippet",
                    q=username,
                    type="channel",
                    maxResults=1
                )
                response = request.execute()
                items = response.get("items", [])
                if items:
                    return items[0]["snippet"]["channelId"]
            except Exception:
                return None

        return None

    async def _fetch_channel_videos(self, channel_id: str, debug: bool) -> Set[str]:
        """
        Consulta a API oficial do YouTube e retorna os IDs de vídeos
        recentes (up to 50) do canal.
        """
        async with self.rate_limit:
            await log_message(f"Buscando vídeos do canal {channel_id} via YouTube Data API...", debug=debug)
            video_ids = set()

            try:
                # 1) Pesquisamos vídeos no canal (search.list)
                # Filtramos por data, maxResults=50 (outra paginação seria necessária para mais resultados).
                search_request = self.youtube.search().list(
                    part="id",
                    channelId=channel_id,
                    maxResults=50,
                    order="date",
                    type="video"
                )
                search_response = search_request.execute()

                for item in search_response.get("items", []):
                    vid_id = item["id"].get("videoId")
                    if vid_id:
                        video_ids.add(vid_id)

            except Exception as e:
                await log_message(f"Erro ao buscar vídeos do canal {channel_id}: {e}", debug=debug)

            await log_message(f"Encontrados {len(video_ids)} vídeos no canal {channel_id}", debug=debug)
            return video_ids

# =============================================================================
# GERENCIAMENTO DO BANCO DE DADOS
# =============================================================================

class DatabaseManager:
    """Classe para gerenciar operações do banco de dados."""
    
    def __init__(self, channel_id: int):
        """
        Inicializa o gerenciador de banco de dados.
        
        Args:
            channel_id: ID do canal
        """
        self.channel_id = channel_id
        self.db_file = os.path.join(DB_DIR, f"channel_{channel_id}.db")
        self.conn = None
        
    async def setup(self) -> bool:
        """
        Configura o banco de dados e cria tabelas, se necessário.
        
        Returns:
            bool: True se a configuração foi bem-sucedida
        """
        try:
            if not os.path.exists(DB_DIR):
                os.makedirs(DB_DIR)
                
            self.conn = sqlite3.connect(self.db_file, isolation_level=None)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS old_video_ids (
                    video_id TEXT PRIMARY KEY
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS notified_video_ids (
                    video_id TEXT PRIMARY KEY,
                    timestamp INTEGER
                )
            """)
            return True
        except Exception as e:
            logging.error(f"Erro ao configurar banco de dados: {e}")
            return False
            
    async def close(self):
        """Fecha a conexão com o banco de dados."""
        if self.conn:
            self.conn.close()
            
    async def load_old_video_ids(self) -> Set[str]:
        """
        Carrega IDs de vídeos antigos.
        
        Returns:
            Set[str]: Conjunto de IDs de vídeos antigos
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT video_id FROM old_video_ids")
            return {row[0] for row in cursor.fetchall()}
        except Exception as e:
            logging.error(f"Erro ao carregar IDs antigos: {e}")
            return set()
            
    async def load_notified_video_ids(self) -> Dict[str, int]:
        """
        Carrega IDs de vídeos notificados.
        
        Returns:
            Dict[str, int]: Dicionário de IDs e timestamps
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT video_id, timestamp FROM notified_video_ids")
            return {row[0]: row[1] for row in cursor.fetchall()}
        except Exception as e:
            logging.error(f"Erro ao carregar IDs notificados: {e}")
            return {}

    async def save_old_video_ids(self, video_ids: Set[str]):
        """
        Salva IDs de vídeos antigos.
        
        Args:
            video_ids: Conjunto de IDs a salvar
        """
        try:
            cursor = self.conn.cursor()
            cursor.executemany(
                "INSERT OR IGNORE INTO old_video_ids (video_id) VALUES (?)",
                [(vid,) for vid in video_ids]
            )
        except Exception as e:
            logging.error(f"Erro ao salvar IDs antigos: {e}")

    async def save_notified_video_ids(self, video_ids: Dict[str, int]):
        """
        Salva IDs de vídeos notificados.
        
        Args:
            video_ids: Dicionário de IDs e timestamps
        """
        try:
            cursor = self.conn.cursor()
            cursor.executemany(
                "INSERT OR REPLACE INTO notified_video_ids (video_id, timestamp) VALUES (?, ?)",
                video_ids.items()
            )
        except Exception as e:
            logging.error(f"Erro ao salvar IDs notificados: {e}")

    @staticmethod
    async def get_all_channel_dbs() -> List[str]:
        """
        Retorna uma lista de todos os arquivos de banco de dados existentes.
        
        Returns:
            List[str]: Lista de caminhos dos arquivos de banco de dados
        """
        if not os.path.exists(DB_DIR):
            return []
        return [
            f for f in os.listdir(DB_DIR)
            if f.startswith("channel_") and f.endswith(".db")
        ]

    @staticmethod
    async def get_channel_id_from_db_file(db_file: str) -> Optional[int]:
        """
        Extrai o ID do canal do nome do arquivo do banco de dados.
        
        Args:
            db_file: Nome do arquivo do banco de dados
            
        Returns:
            Optional[int]: ID do canal ou None se inválido
        """
        try:
            return int(db_file.replace("channel_", "").replace(".db", ""))
        except ValueError:
            return None

    async def list_saved_videos(self, debug: bool = False):
        """
        Lista todos os vídeos salvos no banco de dados.
        
        Args:
            debug: Flag para ativar logs de debug
        """
        try:
            if not os.path.exists(self.db_file):
                await log_message(f"Banco de dados não encontrado para o canal {self.channel_id}", debug=debug)
                return

            await log_message(f"\n=== Vídeos do Canal {self.channel_id} ===", debug=debug)
            
            # Lista vídeos antigos
            cursor = self.conn.cursor()
            cursor.execute("SELECT video_id FROM old_video_ids")
            old_videos = cursor.fetchall()
            await log_message(f"\nVídeos antigos ({len(old_videos)}):", debug=debug)
            await log_message(f"videos: {old_videos}", debug=debug)

            # Lista vídeos notificados com timestamps
            cursor.execute("SELECT video_id, timestamp FROM notified_video_ids ORDER BY timestamp DESC")
            notified_videos = cursor.fetchall()
            
            await log_message(f"\nVídeos notificados ({len(notified_videos)}):", debug=debug)
            for video_id, timestamp in notified_videos:
                date_str = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
                await log_message(
                    f"https://www.youtube.com/watch?v={video_id} (Notificado em: {date_str})",
                    debug=debug
                )
                
        except Exception as e:
            await log_message(f"Erro ao listar vídeos do canal {self.channel_id}: {e}", debug=debug)

# =============================================================================
# GERENCIADOR DE LISTAGENS DE MÚLTIPLOS BANCOS
# =============================================================================

class DatabaseListManager:
    """Classe para gerenciar a listagem de múltiplos bancos de dados."""
    
    @staticmethod
    async def list_all_databases(debug: bool = False):
        """
        Lista o conteúdo de todos os bancos de dados.
        
        Args:
            debug: Flag para ativar logs de debug
        """
        db_files = await DatabaseManager.get_all_channel_dbs()
        
        if not db_files:
            await log_message("Nenhum banco de dados encontrado.", debug=debug)
            return

        for db_file in db_files:
            channel_id = await DatabaseManager.get_channel_id_from_db_file(db_file)
            if channel_id is not None:
                db_manager = DatabaseManager(channel_id)
                await db_manager.setup()
                await db_manager.list_saved_videos(debug)
                await db_manager.close()

    @staticmethod
    async def list_specific_database(channel_id: int, debug: bool = False):
        """
        Lista o conteúdo de um banco de dados específico.
        
        Args:
            channel_id: ID do canal para listar
            debug: Flag para ativar logs de debug
        """
        db_manager = DatabaseManager(channel_id)
        if await db_manager.setup():
            await db_manager.list_saved_videos(debug)
            await db_manager.close()


# =============================================================================
# GERENCIAMENTO DE API (INGEST) - Exemplo de API própria
# =============================================================================

class APIManager:
    """Classe para gerenciar interações com a API de controle (ex.: ingest)."""
    
    def __init__(self):
        self.base_url = "http://127.0.0.1:8787"
        self.token = None
        self.token_expiry = 0
        self.session = None
        
    async def __aenter__(self):
        """Inicializa a sessão HTTP."""
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Fecha a sessão HTTP."""
        if self.session:
            await self.session.close()
            
    async def ensure_token(self):
        """Garante que temos um token válido."""
        current_time = time.time()
        if not self.token or current_time >= self.token_expiry:
            await self.refresh_token()
            
    async def refresh_token(self):
        """Obtém um novo token de autenticação."""
        try:
            async with self.session.post(
                f"{self.base_url}/auth/login/",
                json={"username": "admin", "password": "admin"},
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    self.token = data.get("access_token")
                    self.token_expiry = time.time() + (data.get("expires_in", 3600) - 300)
                else:
                    raise Exception(f"Falha na autenticação: {response.status}")
        except Exception as e:
            await log_message(f"Erro ao obter token: {e}", True)
            raise
            
    async def get_ingest_status(self) -> bool:
        """
        Verifica o status atual de ingestão.
        
        Returns:
            bool: True se está em ingestão, False caso contrário
        """
        try:
            await self.ensure_token()
            async with self.session.get(
                f"{self.base_url}/api/control/1/media/current",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.token}"
                }
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("ingest", False)
                else:
                    raise Exception(f"Erro ao verificar status: {response.status}")
        except Exception as e:
            await log_message(f"Erro ao verificar status de ingestão: {e}", True)
            return False

# =============================================================================
# GESTOR DE STREAMS VIA STREAMLINK
# =============================================================================

class StreamManager:
    """Classe para gerenciar streams do YouTube através do streamlink."""
    
    @staticmethod
    async def start_streamlink(video_url: str, debug: bool = False, retries: int = 0) -> bool:
        """
        Inicia o streamlink para um vídeo.
        
        Args:
            video_url: URL do vídeo
            debug: Flag para ativar logs de debug
            retries: Número de tentativas já realizadas
            
        Returns:
            bool: True se o stream iniciou com sucesso
        """
        await log_message(f"Iniciando streamlink para: {video_url}", debug=debug)

        try:
            command = [
                "/home/junio/livebot/venv/bin/streamlink",
                "--hls-live-edge", "6",
                "--ringbuffer-size", "64M",
                "-4",
                "--stream-sorting-excludes", ">720p",
                "--default-stream", "best",
                "--url", video_url,
                "-p", "mpv",
            ]
            
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid
            )

            # Aguarda o término do processo
            await process.wait()

            if process.returncode == 0:
                await log_message(f"Streamlink executado com sucesso: {video_url}", debug=debug)
                return True
                
            # Se houve erro e ainda há tentativas disponíveis, tenta novamente
            if retries < MAX_RETRIES:
                await log_message(
                    f"Tentando novamente ({retries + 1}/{MAX_RETRIES}) para {video_url}...",
                    debug=debug
                )
                return await StreamManager.start_streamlink(video_url, debug, retries + 1)
                
            await log_message(f"Número máximo de tentativas atingido para: {video_url}", debug=debug)
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            except ProcessLookupError:
                await log_message(f"Processo já encerrado: {process.pid}", debug=debug)
            return False

        except Exception as e:
            await log_message(f"Erro ao iniciar streamlink: {e}", debug=debug)
            return False

# =============================================================================
# FILA DE VÍDEOS
# =============================================================================

class VideoQueue:
    """Classe para gerenciar a fila de vídeos a serem processados."""
    
    def __init__(self):
        self.queue = asyncio.Queue()
        self.api_manager = APIManager()
        self.processing = False
        
    async def add_video(self, video_url: str):
        """
        Adiciona um vídeo à fila para ser processado (streamlink).
        
        Args:
            video_url: URL do vídeo
        """
        await self.queue.put(video_url)
        await log_message(f"Vídeo adicionado à fila: {video_url}", True)
        
        if not self.processing:
            asyncio.create_task(self.process_queue())
            
    async def process_queue(self):
        """Processa a fila de vídeos em background, um por vez."""
        self.processing = True
        
        async with self.api_manager as api:
            while not self.queue.empty():
                try:
                    # Verifica se o sistema de ingestão está ocupado
                    is_ingesting = await api.get_ingest_status()
                    
                    if is_ingesting:
                        await log_message("Sistema em ingestão, aguardando 30s...", True)
                        await asyncio.sleep(30)
                        continue
                    
                    # Processa o próximo vídeo
                    video_url = await self.queue.get()
                    await log_message(f"Processando vídeo da fila: {video_url}", True)
                    
                    success = await StreamManager.start_streamlink(video_url, True)
                    
                    if success:
                        await log_message(f"Vídeo processado com sucesso: {video_url}", True)
                    else:
                        await log_message(f"Falha ao processar vídeo: {video_url}", True)
                        
                    self.queue.task_done()
                    
                except Exception as e:
                    await log_message(f"Erro ao processar fila: {e}", True)
                    await asyncio.sleep(30)
                    
        self.processing = False

# =============================================================================
# PROCESSADOR DE VÍDEOS: AGORA VIA API DO YOUTUBE
# =============================================================================

class VideoProcessor:
    """Classe para processar e notificar (ou iniciar ingest) de novos vídeos."""
    
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        """
        Se db_manager for None, trabalha apenas em memória (canais manuais).
        """
        self.db_manager = db_manager
        self.video_queue = VideoQueue()
        
        # Se não há DB, usaremos estruturas em memória para armazenar IDs
        self.old_video_ids_memory = set()
        self.notified_video_ids_memory = {}

        self.youtube = get_youtube_service()

    async def load_data(self):
        """Carrega dados do BD (se existir) ou inicia estruturas de memória."""
        if self.db_manager:
            self.old_video_ids_memory = await self.db_manager.load_old_video_ids()
            self.notified_video_ids_memory = await self.db_manager.load_notified_video_ids()
        else:
            self.old_video_ids_memory = set()
            self.notified_video_ids_memory = {}

    async def save_data(self):
        """Salva dados no BD (se existir)."""
        if self.db_manager:
            await self.db_manager.save_old_video_ids(self.old_video_ids_memory)
            await self.db_manager.save_notified_video_ids(self.notified_video_ids_memory)

    async def process_new_videos(
        self,
        new_videos: Set[str],
        debug: bool = False
    ):
        """
        Processa novos vídeos detectados.
        
        Args:
            new_videos: Conjunto de IDs de novos vídeos
            debug: Flag para ativar logs de debug
        """
        if not new_videos:
            await log_message("Nenhum vídeo novo detectado", debug=debug)
            return

        videos_to_notify = {}

        for video_id in new_videos:
            result = await self.fetch_and_classify_video_metadata(video_id, debug)
            if not result:
                continue

            metadata, status = result
            published_timestamp = metadata.get("release_timestamp", 0) or 0
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            current_timestamp = int(time.time())

            # Processa de acordo com o status
            if await self._handle_video_status(
                status,
                video_id,
                video_url,
                published_timestamp,
                current_timestamp,
                debug
            ):
                videos_to_notify[video_id] = current_timestamp

        # Se há vídeos a notificar, atualiza a base
        if videos_to_notify:
            self.notified_video_ids_memory.update(videos_to_notify)
            await self.save_data()
            await log_message(f"Salvos {len(videos_to_notify)} novos vídeos notificados", debug=debug)

        # Atualiza e persiste IDs antigos
        self.old_video_ids_memory.update(new_videos)
        await self.save_data()
        await log_message(f"Salvos {len(new_videos)} novos IDs como antigos", debug=debug)

    async def fetch_and_classify_video_metadata(
        self,
        video_id: str,
        debug: bool = False
    ) -> Optional[Tuple[Dict, str]]:
        """
        Faz extração de metadados do vídeo e classifica seu status (live, VOD, upcoming, etc.),
        agora usando a YouTube Data API.
        """
        try:
            request = self.youtube.videos().list(
                part="snippet,liveStreamingDetails",
                id=video_id
            )
            response = request.execute()
            items = response.get("items", [])
            if not items:
                return None

            info = items[0]

            # Monta dicionário básico, simulando algo parecido com o que era no yt-dlp
            snippet = info.get("snippet", {})
            live_details = info.get("liveStreamingDetails", {})

            # Exemplo: se for live ou não
            # (A YouTube Data API também fornece a prop "liveBroadcastContent" = "none", "upcoming" ou "live")
            live_broadcast_content = snippet.get("liveBroadcastContent", "none")
            
            # "release_timestamp" pode vir de snippet.publishedAt, ou de scheduledStartTime
            scheduled_time = live_details.get("scheduledStartTime")
            published_at = snippet.get("publishedAt")

            # Converter publishedAt (ISO8601) em epoch
            release_timestamp = 0
            if scheduled_time:
                # live futura
                dt_obj = datetime.strptime(scheduled_time, "%Y-%m-%dT%H:%M:%SZ")
                release_timestamp = int(dt_obj.timestamp())
            elif published_at:
                dt_obj = datetime.strptime(published_at, "%Y-%m-%dT%H:%M:%SZ")
                release_timestamp = int(dt_obj.timestamp())

            # Preenche metadados internos
            meta_dict = {
                "id": video_id,
                "release_timestamp": release_timestamp,
                "broadcast_content": live_broadcast_content
            }

            # Classifica status
            status = self._classify_video_status(live_broadcast_content, live_details)

            return meta_dict, status

        except Exception as e:
            await log_message(f"Erro ao buscar metadados do vídeo {video_id}: {e}", debug=debug)
            return None

    def _classify_video_status(self, live_broadcast_content: str, live_details: Dict) -> str:
        """
        Classifica o vídeo (live, VOD, upcoming, etc.) com base nas informações
        da YouTube Data API.
        """
        # live_broadcast_content geralmente pode ser:
        # - "none"     => Vídeo comum (VOD)
        # - "upcoming" => Live agendada/futura
        # - "live"     => Está ao vivo
        #
        # Em liveStreamingDetails podemos ter scheduledStartTime, actualStartTime etc.
        
        if live_broadcast_content == "live":
            return "live"  # Ao vivo
        elif live_broadcast_content == "upcoming":
            # Checar se já passou do horário ou não
            scheduled_time = live_details.get("scheduledStartTime")
            if scheduled_time:
                # Data/hora agendada
                dt_obj = datetime.strptime(scheduled_time, "%Y-%m-%dT%H:%M:%SZ")
                if dt_obj.timestamp() > time.time():
                    return "upcoming_scheduled"
                else:
                    return "upcoming_pre_launch"
            else:
                # Se a API não deu a scheduledStartTime, consideramos 'upcoming_pre_launch'
                return "upcoming_pre_launch"
        else:
            # Se for "none", consideramos VOD
            return "VOD"

    async def _handle_video_status(
        self,
        status: str,
        video_id: str,
        video_url: str,
        published_timestamp: int,
        current_timestamp: int,
        debug: bool
    ) -> bool:
        """
        Executa ações de notificação ou ingest dependendo do status do vídeo.
        """
        if status == "upcoming_scheduled":
            if published_timestamp > current_timestamp:
                await log_message(
                    f"Vídeo {video_id} agendado para {datetime.fromtimestamp(published_timestamp)}",
                    debug=debug
                )
                return False
            else:
                await log_message(
                    f"Vídeo {video_id} está atrasado. Data: {datetime.fromtimestamp(published_timestamp)}",
                    debug=debug
                )
                return True

        elif status in ["upcoming_pre_launch", "live", "VOD"]:
            await log_message(f"Novo {status} detectado: {video_url}", debug=debug)
            await self.video_queue.add_video(video_url)
            return True

        return False

# =============================================================================
# SERVIÇO PRINCIPAL DE MONITORAMENTO (PARA CANAIS CADASTRADOS NO JSON)
# =============================================================================

class MonitorService:
    """Serviço de monitoramento para canais com ID, usando banco de dados."""
    
    def __init__(self, channel_id: int, debug: bool = False):
        self.channel_id = channel_id
        self.debug = debug
        self.db_manager = DatabaseManager(channel_id)
        self.video_processor = None
        self.tab_monitor = None
        
    async def setup(self) -> bool:
        """Configura DB, carrega dados e prepara o monitor."""
        if not await self.db_manager.setup():
            return False
            
        self.video_processor = VideoProcessor(self.db_manager)
        await self.video_processor.load_data()  # Carrega old e notified

        # Parâmetros default, pode ajustar se quiser
        self.tab_monitor = TabMonitor(rate_limit=5, chunk_size=3)
        return True
        
    async def start(self):
        """Inicia o loop de monitoramento."""
        channel_urls = await self._load_channel_urls()
        if not channel_urls:
            await log_message(f"Canal {self.channel_id} não encontrado ou sem URLs configuradas", debug=self.debug)
            return
        
        await log_message(
            f"Carregados {len(self.video_processor.old_video_ids_memory)} IDs antigos e "
            f"{len(self.video_processor.notified_video_ids_memory)} IDs notificados",
            debug=self.debug
        )
        
        first_iteration = True

        while True:
            try:
                new_video_ids = await self.tab_monitor.monitor_tabs(channel_urls, self.debug)

                if first_iteration:
                    # Na primeira iteração, consideramos todos os IDs como 'antigos' para não notificar nada
                    self.video_processor.old_video_ids_memory.update(new_video_ids)
                    await self.video_processor.save_data()
                    first_iteration = False
                    await log_message(
                        f"Primeira iteração: salvos {len(new_video_ids)} IDs como antigos",
                        debug=self.debug
                    )
                    await asyncio.sleep(SLEEP_INTERVAL)
                    continue

                # Filtra IDs realmente novos
                old_ids = self.video_processor.old_video_ids_memory
                new_videos = new_video_ids - old_ids

                if not new_videos:
                    await log_message("Nenhum novo vídeo detectado", debug=self.debug)
                else:
                    await log_message(
                        f"Detectados {len(new_videos)} novos vídeos",
                        debug=self.debug
                    )
                    await self.video_processor.process_new_videos(new_videos, debug=self.debug)

                await log_message(f"Aguardando {SLEEP_INTERVAL} segundos...", debug=self.debug)
                await asyncio.sleep(SLEEP_INTERVAL)

            except Exception as e:
                await log_message(f"Erro no monitoramento: {e}", debug=self.debug)
                await asyncio.sleep(SLEEP_INTERVAL)

    async def _load_channel_urls(self) -> List[str]:
        """Carrega as URLs do canal via JSON."""
        channels = await ChannelManager.load_channels(self.debug)
        return channels.get(self.channel_id, [])

# =============================================================================
# SERVIÇO DE MONITORAMENTO MANUAL (SEM USAR O BANCO DE DADOS)
# =============================================================================

class ManualMonitorService:
    """
    Serviço de monitoramento para canais/URLs passados diretamente via linha
    de comando (--manual_channels). Não salva nada em disco.
    """
    def __init__(self, channel_urls: List[str], debug: bool = False):
        self.channel_urls = channel_urls
        self.debug = debug
        
        # Usa VideoProcessor sem DB
        self.video_processor = VideoProcessor(None)
        # Usa TabMonitor padrão
        self.tab_monitor = TabMonitor(rate_limit=5, chunk_size=3)
        
        # Flags internas
        self.first_iteration = True

    async def setup(self) -> bool:
        """Carrega dados apenas em memória."""
        # Para canais manuais, não há DB, mas inicializamos as estruturas.
        await self.video_processor.load_data()  
        return True

    async def start(self):
        """Inicia o loop de monitoramento contínuo para URLs manuais."""
        if not self.channel_urls:
            await log_message("Nenhuma URL fornecida em --manual_channels", debug=self.debug)
            return

        while True:
            try:
                new_video_ids = await self.tab_monitor.monitor_tabs(self.channel_urls, self.debug)

                if self.first_iteration:
                    # Na primeira iteração, consideramos todos os IDs como 'antigos'
                    self.video_processor.old_video_ids_memory.update(new_video_ids)
                    self.first_iteration = False
                    await log_message(
                        f"Primeira iteração (manual): salvos {len(new_video_ids)} IDs como antigos",
                        debug=self.debug
                    )
                    await asyncio.sleep(SLEEP_INTERVAL)
                    continue

                old_ids = self.video_processor.old_video_ids_memory
                new_videos = new_video_ids - old_ids

                if not new_videos:
                    await log_message("Nenhum novo vídeo manual detectado", debug=self.debug)
                else:
                    await log_message(f"Detectados {len(new_videos)} novos vídeos (manuais)", debug=self.debug)
                    await self.video_processor.process_new_videos(new_videos, debug=self.debug)

                await log_message(f"Aguardando {SLEEP_INTERVAL} segundos (monitor manual)...", debug=self.debug)
                await asyncio.sleep(SLEEP_INTERVAL)

            except Exception as e:
                await log_message(f"Erro no monitoramento manual: {e}", debug=self.debug)
                await asyncio.sleep(SLEEP_INTERVAL)

# =============================================================================
# GERENCIAMENTO DE CANAIS (CARREGA O JSON)
# =============================================================================

class ChannelManager:
    """Classe para gerenciar canais do YouTube a partir do arquivo JSON."""
    
    @staticmethod
    async def load_channels(debug: bool = False) -> Dict[int, List[str]]:
        """
        Carrega a configuração dos canais a partir de um JSON.
        
        Returns:
            Dict[int, List[str]]: Dicionário {channel_id: [url1, url2, ...]}
        """
        await log_message("Carregando configuração dos canais (JSON)", debug=debug)

        if not os.path.exists(CHANNELS_FILE):
            await log_message(f"Arquivo {CHANNELS_FILE} não encontrado", debug=debug)
            return {}

        try:
            with open(CHANNELS_FILE, "r") as file:
                channels_data = json.load(file)

            if not isinstance(channels_data, dict) or "channels" not in channels_data:
                raise ValueError("Formato inválido no arquivo de canais")

            channel_dict = {
                channel["id"]: channel["urls"]
                for channel in channels_data["channels"]
                if isinstance(channel.get("urls"), list)
            }

            await log_message(f"Canais carregados: {channel_dict}", debug=debug)
            return channel_dict

        except Exception as e:
            await log_message(f"Erro ao carregar canais do JSON: {e}", debug=debug)
            return {}

# =============================================================================
# FUNÇÃO MAIN
# =============================================================================

def main():
    """Ponto de entrada principal para execução via CLI."""
    parser = argparse.ArgumentParser(description="Monitor de canais do YouTube")

    parser.add_argument(
        "--channel_id",
        type=int,
        help="ID do canal a monitorar (conforme configurado no arquivo JSON)"
    )

    parser.add_argument(
        "--manual_channels",
        nargs="+",
        help="Lista de URLs de canais para monitorar manualmente (sem JSON, sem BD)"
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Ativa logs de debug"
    )

    parser.add_argument(
        "--list",
        nargs="?",
        const="all",
        help="Lista os vídeos salvos no BD. Use '--list all' para todos os canais ou '--list <ID>' para um canal específico"
    )

    parser.add_argument(
        "--monitor_channel",
        type=int,
        metavar="ID",
        help="Monitora um canal específico com base no ID fornecido (similar a --channel_id, mas sem fallback)"
    )

    parser.add_argument(
        "--execute_url",
        metavar="URL",
        help="Executa diretamente um URL de live ou vídeo comum através do Streamlink (sem monitoramento)."
    )

    args = parser.parse_args()

    # 1) Se for apenas executar streamlink em uma URL (ex.: debugging)
    if args.execute_url:
        asyncio.run(StreamManager.start_streamlink(args.execute_url, args.debug))
        return

    # 2) Se usuário pediu listagem de vídeos salvos no BD
    if args.list is not None:
        if args.list == "all":
            asyncio.run(DatabaseListManager.list_all_databases(args.debug))
        else:
            # Tenta converter o valor para int (ID do canal)
            try:
                channel_id = int(args.list)
                asyncio.run(DatabaseListManager.list_specific_database(channel_id, args.debug))
            except ValueError:
                print(f"ID de canal inválido: {args.list}")
        return

    # 3) Se o usuário passou URLs manuais, iniciamos o monitor manual (sem BD)
    if args.manual_channels:
        service = ManualMonitorService(args.manual_channels, args.debug)
        setup_ok = asyncio.run(service.setup())
        if setup_ok:
            asyncio.run(service.start())
        return

    # 4) Se o usuário quer monitorar um canal específico via --monitor_channel
    if args.monitor_channel:
        service = MonitorService(args.monitor_channel, args.debug)
        setup_ok = asyncio.run(service.setup())
        if setup_ok:
            asyncio.run(service.start())
        return

    # 5) Caso contrário, se for apenas --channel_id
    if args.channel_id is None:
        parser.error("É necessário usar --channel_id, --manual_channels ou outro parâmetro (ex.: --list).")
        return

    service = MonitorService(args.channel_id, args.debug)
    setup_ok = asyncio.run(service.setup())
    if setup_ok:
        asyncio.run(service.start())


if __name__ == "__main__":
    main()
