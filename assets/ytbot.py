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
from itertools import chain
import aiohttp
from yt_dlp import YoutubeDL
import time

# =============================================================================
# CONFIGURAÇÕES GLOBAIS
# =============================================================================

DB_DIR = os.path.expanduser("~/livebot/db")
CHANNELS_FILE = os.path.expanduser("~/livebot/channels.json")

# Intervalo de checagem em segundos.
# Se realmente deseja 5 segundos, troque para 5. Mas se a intenção é 5 minutos, use 300.
SLEEP_INTERVAL = 300  # 5 minutos

MAX_RETRIES = 3

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
        debug: Flag para ativar logs de debug
    """
    logging.info(message)
    if debug:
        print(f"[DEBUG] {message}")


# =============================================================================
# MONITORAMENTO DE ABAS DO YOUTUBE
# =============================================================================

class TabMonitor:
    """Classe para monitorar abas de canais do YouTube."""
    
    def __init__(self, rate_limit: int = 5, chunk_size: int = 3):
        """
        Inicializa o monitor de abas.
        
        Args:
            rate_limit: Número máximo de requisições simultâneas
            chunk_size: Tamanho do chunk para processamento em lote
        """
        self.rate_limit = asyncio.Semaphore(rate_limit)
        self.chunk_size = chunk_size
        self.session = None

    async def __aenter__(self):
        """Inicializa a sessão HTTP."""
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Fecha a sessão HTTP."""
        if self.session:
            await self.session.close()

    async def monitor_tabs(self, channel_urls: List[str], debug: bool = False) -> Set[str]:
        """
        Monitora abas de URLs do canal de forma paralela e eficiente.
        
        Args:
            channel_urls: Lista de URLs dos canais
            debug: Flag para ativar logs de debug
            
        Returns:
            Set[str]: Conjunto de IDs de vídeos únicos
        """
        await log_message(f"Iniciando monitoramento de {len(channel_urls)} URLs", debug=debug)
        
        valid_urls = self._validate_urls(channel_urls)
        if not valid_urls:
            await log_message("Nenhuma URL válida fornecida", debug=debug)
            return set()

        all_tabs = self._generate_tabs(valid_urls)
        all_video_ids = set()
        
        # Usa o próprio 'self' como context manager
        async with self:
            # Divide as abas em chunks para processar em lotes
            chunks = [all_tabs[i:i + self.chunk_size] for i in range(0, len(all_tabs), self.chunk_size)]
            for chunk_index, chunk in enumerate(chunks, start=1):
                try:
                    await log_message(f"Processando chunk {chunk_index}/{len(chunks)}", debug=debug)
                    tasks = [self._process_tab(tab, debug) for tab in chunk]
                    chunk_results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    for result in chunk_results:
                        if isinstance(result, set):
                            all_video_ids.update(result)
                        elif isinstance(result, Exception):
                            await log_message(f"Erro ao processar aba: {result}", debug=debug)
                    
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    await log_message(f"Erro ao processar chunk de abas: {e}", debug=debug)
                    continue

        await log_message(f"Total de vídeos únicos encontrados: {len(all_video_ids)}", debug=debug)
        return all_video_ids

    def _validate_urls(self, urls: List[str]) -> List[str]:
        """
        Valida e limpa as URLs fornecidas.
        
        Args:
            urls: Lista de URLs para validar
            
        Returns:
            List[str]: Lista de URLs válidas e limpas
        """
        valid_urls = []
        for url in urls:
            try:
                parsed = urlparse(url)
                if parsed.scheme and parsed.netloc and "youtube.com" in parsed.netloc:
                    clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip('/')
                    valid_urls.append(clean_url)
            except Exception:
                continue
        return valid_urls

    def _generate_tabs(self, urls: List[str]) -> List[str]:
        """
        Gera todas as abas para cada URL.
        
        Args:
            urls: Lista de URLs base
            
        Returns:
            List[str]: Lista de URLs com todas as abas
        """
        tab_types = ["live", "community", "featured", "videos", "streams"]
        return [f"{url}/{tab}" for url in urls for tab in tab_types]

    async def _process_tab(self, tab_url: str, debug: bool) -> Set[str]:
        """
        Processa uma única aba com rate limiting.
        
        Args:
            tab_url: URL da aba a ser processada
            debug: Flag para ativar logs de debug
            
        Returns:
            Set[str]: Conjunto de IDs de vídeos encontrados
        """
        async with self.rate_limit:
            try:
                await log_message(f"Processando aba: {tab_url}", debug=debug)
                with YoutubeDL(ydl_opts) as ydl:
                    info = await asyncio.to_thread(
                        ydl.extract_info,
                        tab_url,
                        download=False,
                        process=False
                    )
                    if not info or 'entries' not in info or not info['entries']:
                        return set()
                    
                    video_ids = {entry['id'] for entry in info['entries'] if entry and 'id' in entry}
                    await log_message(f"Encontrados {len(video_ids)} vídeos em {tab_url}", debug=debug)
                    return video_ids
            except Exception as e:
                await log_message(f"Erro ao processar {tab_url}: {e}", debug=debug)
                return set()


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
        Configura o banco de dados.
        
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
# GERENCIAMENTO DE API
# =============================================================================

class APIManager:
    """Classe para gerenciar interações com a API de controle."""
    
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
                    # Define expiração para 5 minutos antes do tempo real
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
# FILA DE VÍDEOS
# =============================================================================

class VideoQueue:
    """Classe para gerenciar a fila de vídeos."""
    
    def __init__(self):
        """Inicializa a fila de vídeos."""
        self.queue = asyncio.Queue()
        self.api_manager = APIManager()
        self.processing = False
        
    async def add_video(self, video_url: str):
        """
        Adiciona um vídeo à fila.
        
        Args:
            video_url: URL do vídeo a ser processado
        """
        await self.queue.put(video_url)
        await log_message(f"Vídeo adicionado à fila: {video_url}", True)
        
        if not self.processing:
            asyncio.create_task(self.process_queue())
            
    async def process_queue(self):
        """Processa a fila de vídeos."""
        self.processing = True
        
        async with self.api_manager as api:
            while not self.queue.empty():
                try:
                    # Verifica o status de ingestão
                    is_ingesting = await api.get_ingest_status()
                    
                    if is_ingesting:
                        await log_message("Sistema em ingestão, aguardando...", True)
                        await asyncio.sleep(30)  # Aguarda 30 segundos antes de verificar novamente
                        continue
                    
                    # Processa o próximo vídeo da fila
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
# PROCESSADOR DE VÍDEOS
# =============================================================================

class VideoProcessor:
    """Classe para processar vídeos do YouTube."""
    
    def __init__(self, db_manager: DatabaseManager):
        """
        Inicializa o processador de vídeos.
        
        Args:
            db_manager: Instância do gerenciador de banco de dados
        """
        self.db_manager = db_manager
        self.video_queue = VideoQueue()
        
    async def process_new_videos(
        self,
        new_videos: Set[str],
        old_video_ids: Set[str],
        notified_video_ids: Dict[str, int],
        channel_urls: List[str],
        debug: bool = False
    ):
        """
        Processa novos vídeos detectados.
        
        Args:
            new_videos: Conjunto de novos IDs de vídeos
            old_video_ids: Conjunto de IDs antigos
            notified_video_ids: Dicionário de IDs notificados
            channel_urls: Lista de URLs dos canais
            debug: Flag para ativar logs de debug
        """
        if not new_videos:
            await log_message("Nenhum vídeo novo detectado", debug=debug)
            return

        videos_to_notify = {}  # Dicionário para acumular novos vídeos a serem notificados

        for video_id in new_videos:
            result = await self.fetch_and_classify_video_metadata(video_id, debug)
            if not result:
                continue

            metadata, status = result
            published_timestamp = metadata.get("release_timestamp", 0) or 0
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            current_timestamp = int(time.time())

            # Processa o vídeo baseado em seu status
            if await self._handle_video_status(
                status,
                video_id,
                video_url,
                published_timestamp,
                current_timestamp,
                notified_video_ids,
                debug
            ):
                # Se o vídeo foi processado (ou seja, será notificado), acumula no dicionário
                videos_to_notify[video_id] = current_timestamp

        if videos_to_notify:
            # Atualiza o dicionário de vídeos notificados em memória
            notified_video_ids.update(videos_to_notify)
            # Salva os novos vídeos notificados no banco de dados
            await self.db_manager.save_notified_video_ids(videos_to_notify)
            await log_message(f"Salvos {len(videos_to_notify)} novos vídeos notificados", debug=debug)

        # Atualiza e salva os IDs antigos
        old_video_ids.update(new_videos)
        await self.db_manager.save_old_video_ids(old_video_ids)
        await log_message(f"Salvos {len(new_videos)} novos IDs na tabela de vídeos antigos", debug=debug)

    async def fetch_and_classify_video_metadata(
        self,
        video_id: str,
        debug: bool = False
    ) -> Optional[Tuple[Dict, str]]:
        """
        Busca e classifica metadados do vídeo.
        
        Args:
            video_id: ID do vídeo
            debug: Flag para ativar logs de debug
            
        Returns:
            Optional[Tuple[Dict, str]]: Tupla com metadados e status do vídeo
        """
        try:
            with YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.to_thread(
                    ydl.extract_info,
                    f"https://www.youtube.com/watch?v={video_id}",
                    download=False
                )

            if not info:
                return None

            status = self._classify_video_status(info)
            return info, status

        except Exception as e:
            await log_message(f"Erro ao buscar metadados do vídeo {video_id}: {e}", debug=debug)
            return None

    def _classify_video_status(self, info: Dict) -> str:
        """
        Classifica o status do vídeo.
        
        Args:
            info: Dicionário com informações do vídeo
            
        Returns:
            str: Status classificado do vídeo
        """
        # Alguns campos podem não existir em certas versões do yt-dlp
        is_live_now = info.get("isLiveNow", False)
        is_live = info.get("is_live", False)
        is_upcoming = info.get("upcoming", False)
        was_live = info.get("was_live", False)

        # Regras simples de classificação
        if is_live_now and was_live:
            return "live"
        elif is_upcoming:
            # Se ainda não passou a data/hora de lançamento
            if info.get("release_timestamp", 0) > int(time.time()):
                return "upcoming_scheduled"
            return "upcoming_pre_launch"
        elif is_live:
            return "live_VOD"
        return "VOD"

    async def _handle_video_status(
        self,
        status: str,
        video_id: str,
        video_url: str,
        published_timestamp: int,
        current_timestamp: int,
        notified_video_ids: Dict[str, int],
        debug: bool
    ) -> bool:
        """
        Manipula o vídeo com base em seu status.
        
        Args:
            status: Status do vídeo
            video_id: ID do vídeo
            video_url: URL do vídeo
            published_timestamp: Timestamp de publicação
            current_timestamp: Timestamp atual
            notified_video_ids: Dicionário de IDs notificados
            debug: Flag para ativar logs de debug
            
        Returns:
            bool: True se o vídeo deve ser notificado, False caso contrário
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

        elif status in ["upcoming_pre_launch", "live", "live_VOD", "VOD"]:
            await log_message(f"Novo {status} detectado: {video_url}", debug=debug)
            # Em vez de chamar start_streamlink diretamente, adicionamos à fila
            await self.video_queue.add_video(video_url)
            return True

        return False


# =============================================================================
# GESTOR DE STREAMS VIA STREAMLINK
# =============================================================================

class StreamManager:
    """Classe para gerenciar streams do YouTube."""
    
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

            # Se retornou 0, significa que o processo rodou sem erros
            if process.returncode == 0:
                await log_message(f"Streamlink executado com sucesso: {video_url}", debug=debug)
                return True
                
            if retries < MAX_RETRIES:
                await log_message(
                    f"Tentando novamente ({retries + 1}/{MAX_RETRIES}) para {video_url}...",
                    debug=debug
                )
                return await StreamManager.start_streamlink(video_url, debug, retries + 1)
                
            await log_message(f"Número máximo de tentativas atingido: {video_url}", debug=debug)
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            except ProcessLookupError:
                await log_message(f"Processo já encerrado: {process.pid}", debug=debug)
            return False

        except Exception as e:
            await log_message(f"Erro ao iniciar streamlink: {e}", debug=debug)
            return False


# =============================================================================
# GERENCIAMENTO DE CANAIS
# =============================================================================

class ChannelManager:
    """Classe para gerenciar canais do YouTube."""
    
    @staticmethod
    async def load_channels(debug: bool = False) -> Dict[int, List[str]]:
        """
        Carrega a configuração dos canais.
        
        Args:
            debug: Flag para ativar logs de debug
            
        Returns:
            Dict[int, List[str]]: Dicionário com IDs e URLs dos canais
        """
        await log_message("Carregando configuração dos canais", debug=debug)

        if not os.path.exists(CHANNELS_FILE):
            await log_message(f"Arquivo {CHANNELS_FILE} não encontrado", debug=debug)
            return {}

        try:
            with open(CHANNELS_FILE, "r") as file:
                channels = json.load(file)

            if not isinstance(channels, dict) or "channels" not in channels:
                raise ValueError("Formato inválido no arquivo de canais")

            channel_dict = {
                channel["id"]: channel["urls"]
                for channel in channels["channels"]
            }

            await log_message(f"Canais carregados: {channel_dict}", debug=debug)
            return channel_dict

        except Exception as e:
            await log_message(f"Erro ao carregar canais: {e}", debug=debug)
            return {}


# =============================================================================
# SERVIÇO PRINCIPAL DE MONITORAMENTO
# =============================================================================

class MonitorService:
    """Serviço principal de monitoramento."""
    
    def __init__(self, channel_id: int, debug: bool = False):
        """
        Inicializa o serviço de monitoramento.
        
        Args:
            channel_id: ID do canal a monitorar
            debug: Flag para ativar logs de debug
        """
        self.channel_id = channel_id
        self.debug = debug
        self.db_manager = DatabaseManager(channel_id)
        self.video_processor = None
        self.tab_monitor = None
        
    async def setup(self) -> bool:
        """
        Configura o serviço de monitoramento.
        
        Returns:
            bool: True se a configuração foi bem-sucedida
        """
        if not await self.db_manager.setup():
            return False
            
        self.video_processor = VideoProcessor(self.db_manager)
        self.tab_monitor = TabMonitor(rate_limit=5, chunk_size=3)
        return True
        
    async def start(self):
        """Inicia o serviço de monitoramento."""
        channels = await ChannelManager.load_channels(self.debug)
        
        if self.channel_id not in channels:
            await log_message(
                f"Canal {self.channel_id} não encontrado na configuração",
                debug=self.debug
            )
            return

        channel_urls = channels[self.channel_id]
        
        # Carrega os IDs das duas tabelas
        old_video_ids = await self.db_manager.load_old_video_ids()
        notified_video_ids = await self.db_manager.load_notified_video_ids()
        
        await log_message(
            f"Carregados {len(old_video_ids)} IDs antigos e {len(notified_video_ids)} IDs notificados",
            debug=self.debug
        )
        
        first_iteration = True

        while True:
            try:
                # Monitora todas as abas dos canais
                new_video_ids = await self.tab_monitor.monitor_tabs(channel_urls, self.debug)

                if first_iteration:
                    # Na primeira iteração, salvamos todos os IDs como antigos
                    old_video_ids = new_video_ids
                    await self.db_manager.save_old_video_ids(new_video_ids)
                    first_iteration = False
                    await log_message(
                        f"Primeira iteração: salvos {len(new_video_ids)} IDs como antigos",
                        debug=self.debug
                    )
                    await asyncio.sleep(SLEEP_INTERVAL)
                    continue

                # Detecta apenas vídeos verdadeiramente novos (que não estavam em old_video_ids)
                new_videos = new_video_ids - old_video_ids

                if not new_videos:
                    await log_message("Nenhum novo vídeo detectado", debug=self.debug)
                else:
                    await log_message(
                        f"Detectados {len(new_videos)} novos vídeos",
                        debug=self.debug
                    )
                    # Processa apenas os vídeos novos
                    await self.video_processor.process_new_videos(
                        new_videos,
                        old_video_ids,
                        notified_video_ids,
                        channel_urls,
                        self.debug
                    )

                await log_message(f"Aguardando {SLEEP_INTERVAL} segundos...", debug=self.debug)
                await asyncio.sleep(SLEEP_INTERVAL)

            except Exception as e:
                await log_message(f"Erro no monitoramento: {e}", debug=self.debug)
                await asyncio.sleep(SLEEP_INTERVAL)


# =============================================================================
# LOGGER PERSONALIZADO PARA YOUTUBE-DL
# =============================================================================

class YoutubeDLLogger:
    """Logger personalizado para o youtube-dl."""
    def debug(self, msg):
        """Log de debug."""
        logging.debug(msg)

    def warning(self, msg):
        """Log de warning."""
        logging.warning(msg)

    def error(self, msg):
        """Log de erro."""
        logging.error(msg)


# =============================================================================
# CONFIGURAÇÃO DO YOUTUBE-DL (YT-DLP)
# =============================================================================

home_directory = os.path.expanduser('~')
cookie_file_path = os.path.join(home_directory, 'livebot', 'cookies.txt')

if not os.path.exists(os.path.dirname(cookie_file_path)):
    os.makedirs(os.path.dirname(cookie_file_path))

ydl_opts = {
    'call_home': False,
    'forcejson': True,
    'logger': YoutubeDLLogger(),
    'color': False,
    'noplaylist': True,
    'no_warnings': True,
    'noprogress': True,
    'verbose': False,
    'quiet': True,
    'cookies': cookie_file_path,
}


# =============================================================================
# FUNÇÃO MAIN
# =============================================================================

def main():
    """Função principal."""
    parser = argparse.ArgumentParser(
        description="Monitor de canais do YouTube"
    )
    
    parser.add_argument(
        "--channel_id",
        type=int,
        help="ID do canal a monitorar"
    )
    
    parser.add_argument(
        "--manual_channels",
        nargs="+",
        help="Lista de URLs de canais para escanear manualmente (não implementado neste script)"
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
        help="Lista os vídeos salvos. Use '--list all' para todos os canais ou '--list ID' para um canal específico"
    )
    
    parser.add_argument(
        "--monitor_channel",
        type=int,
        metavar="ID",
        help="Monitora um canal específico com base no ID fornecido"
    )
    
    parser.add_argument(
        "--execute_url",
        metavar="URL",
        help="Executa diretamente uma URL de live ou vídeo comum através do Streamlink"
    )

    args = parser.parse_args()

    # Se o usuário passar --execute_url, executamos diretamente o Streamlink
    if args.execute_url:
        asyncio.run(StreamManager.start_streamlink(args.execute_url, args.debug))
        return

    # Trata o comando --list (listar vídeos salvos)
    if args.list is not None:
        if args.list == "all":
            asyncio.run(DatabaseListManager.list_all_databases(args.debug))
        else:
            # Tenta converter o valor para int; se falhar, é formato inválido
            try:
                channel_id = int(args.list)
                asyncio.run(DatabaseListManager.list_specific_database(channel_id, args.debug))
            except ValueError:
                print(f"ID de canal inválido: {args.list}")
        return

    # Se o usuário optar por monitorar um canal específico via --monitor_channel
    if args.monitor_channel:
        service = MonitorService(args.monitor_channel, args.debug)
        setup_ok = asyncio.run(service.setup())
        if setup_ok:
            asyncio.run(service.start())
        return

    # Se não for listagem nem monitor_channel, mas o usuário não passou channel_id
    if args.channel_id is None:
        parser.error("--channel_id é obrigatório quando não se usa --list ou --monitor_channel")
        return

    # Fluxo normal: monitorar canal passado por --channel_id
    service = MonitorService(args.channel_id, args.debug)
    setup_ok = asyncio.run(service.setup())
    if setup_ok:
        asyncio.run(service.start())


if __name__ == "__main__":
    main()
