#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
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
from yt_dlp import YoutubeDL
import time

# Novos imports para o StreamManager (ffmpeg + streamlink):
import shutil
from pathlib import Path
from dataclasses import dataclass

# =============================================================================
# CONFIGURAÇÕES GLOBAIS
# =============================================================================

DB_DIR = os.path.expanduser("~/livebot/db")
CHANNELS_FILE = os.path.expanduser("~/livebot/channels.json")

# Intervalo de checagem em segundos (padrão: 5 minutos = 300).
SLEEP_INTERVAL = 300

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

def handle_signal(sig, frame):
    """Tratamento de sinais (SIGINT, SIGTERM) para encerramento gracioso."""
    logging.info(f"Recebido sinal {sig}. Encerrando o programa de forma graciosa.")
    sys.exit(0)

# Registra os handlers de sinal
signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)

async def log_message(message: str, debug: bool = False):
    """
    Função auxiliar para logging.
    
    Args:
        message: Mensagem a ser logada
        debug: Flag para ativar logs de debug (imprime também no console)
    """
    logging.info(message)
    if debug:
        print(f"[DEBUG] {message}")


# =============================================================================
# LOGGER PERSONALIZADO PARA O YOUTUBE-DL (YT-DLP)
# =============================================================================

class YoutubeDLLogger:
    """Logger personalizado para o yt-dlp (youtube-dl)."""
    def debug(self, msg):
        logging.debug(msg)

    def warning(self, msg):
        logging.warning(msg)

    def error(self, msg):
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
    'noplaylist': True,      # Não processar playlists de forma "tradicional"
    'no_warnings': True,
    'noprogress': True,
    'verbose': False,
    'quiet': True,
    'cookies': cookie_file_path,
}


# =============================================================================
# NOVO MONITOR DE CANAIS (UMA CHAMADA POR CANAL)
# =============================================================================

class TabMonitor:
    """
    Monitor de canais do YouTube em uma única solicitação por canal.
    Em vez de gerar abas (live/community/videos), faz apenas 1 chamada ao canal.
    """
    
    def __init__(self, rate_limit: int = 5, chunk_size: int = 3):
        """
        Inicializa o monitor.

        Args:
            rate_limit: Número máximo de requisições simultâneas
            chunk_size: Tamanho do chunk para processamento em lote
        """
        self.rate_limit = asyncio.Semaphore(rate_limit)
        self.chunk_size = chunk_size
        self.session = None

    async def __aenter__(self):
        """Inicializa a sessão HTTP (aiohttp)."""
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Fecha a sessão HTTP."""
        if self.session:
            await self.session.close()

    async def monitor_tabs(self, channel_urls: List[str], debug: bool = False) -> Set[str]:
        """
        Monitora cada canal em uma única solicitação, coletando todos os vídeos
        que o yt-dlp retornar.

        Args:
            channel_urls: Lista de URLs de canais (ex.: https://www.youtube.com/@MeuCanal)
            debug: Flag para logs de debug
            
        Returns:
            Set[str]: Conjunto de IDs de vídeos únicos encontrados
        """
        await log_message(f"Iniciando monitoramento de {len(channel_urls)} URLs", debug=debug)
        
        valid_urls = self._validate_urls(channel_urls)
        if not valid_urls:
            await log_message("Nenhuma URL válida fornecida", debug=debug)
            return set()

        all_video_ids = set()

        # Usa o próprio objeto como context manager
        async with self:
            chunks = [valid_urls[i:i + self.chunk_size] for i in range(0, len(valid_urls), self.chunk_size)]
            for chunk_index, chunk in enumerate(chunks, start=1):
                try:
                    await log_message(f"Processando chunk {chunk_index}/{len(chunks)}: {chunk}", debug=debug)
                    tasks = [self._process_channel(url, debug) for url in chunk]
                    chunk_results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    for result in chunk_results:
                        if isinstance(result, set):
                            all_video_ids.update(result)
                        elif isinstance(result, Exception):
                            await log_message(f"Erro ao processar canal: {result}", debug=debug)

                    # Pequena pausa para evitar sobrecarga
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    await log_message(f"Erro ao processar chunk de canais: {e}", debug=debug)
                    continue

        await log_message(f"Total de vídeos únicos encontrados: {len(all_video_ids)}", debug=debug)
        return all_video_ids

    def _validate_urls(self, urls: List[str]) -> List[str]:
        """Valida e padroniza as URLs fornecidas."""
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

    async def _process_channel(self, channel_url: str, debug: bool) -> Set[str]:
        """
        Faz uma única requisição ao canal para extrair todas as entradas (vídeos).
        
        Args:
            channel_url: URL do canal (ex.: https://www.youtube.com/@MeuCanal)
            debug: Logs de debug

        Returns:
            Set[str]: IDs de vídeos encontrados
        """
        async with self.rate_limit:
            try:
                await log_message(f"Processando canal: {channel_url}", debug=debug)
                with YoutubeDL(ydl_opts) as ydl:
                    info = await asyncio.to_thread(
                        ydl.extract_info,
                        channel_url,
                        download=False,
                        process=False
                    )
                    if not info or "entries" not in info:
                        return set()
                    
                    entries = info.get("entries") or []
                    video_ids = {entry["id"] for entry in entries if entry and "id" in entry}

                    await log_message(f"Encontrados {len(video_ids)} vídeos em {channel_url}", debug=debug)
                    return video_ids

            except Exception as e:
                await log_message(f"Erro ao processar {channel_url}: {e}", debug=debug)
                return set()


# =============================================================================
# GERENCIAMENTO DO BANCO DE DADOS
# =============================================================================

class DatabaseManager:
    """Classe para gerenciar operações do banco de dados (SQLite)."""
    
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
        Também ativa o modo WAL e ajusta 'synchronous' para NORMAL.
        
        Returns:
            bool: True se a configuração foi bem-sucedida
        """
        try:
            if not os.path.exists(DB_DIR):
                os.makedirs(DB_DIR)
                
            self.conn = sqlite3.connect(self.db_file, isolation_level=None)

            # Melhora robustez contra corrupção de dados
            self.conn.execute("PRAGMA journal_mode = WAL;")
            self.conn.execute("PRAGMA synchronous = NORMAL;")

            # Cria tabelas se não existirem
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
            self.conn = None
            
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
# GERENCIAMENTO DE API (INGEST)
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
# NOVA IMPLEMENTAÇÃO DE STREAM MANAGER (streamlink + ffmpeg)
# =============================================================================

@dataclass
class StreamConfig:
    """Configuração para streaming."""
    url: str
    rtmp_details: str
    hls_live_edge: int = 6
    ringbuffer_size: str = "128M"
    max_quality: str = "720p"
    stream_quality: str = "best"

class StreamManagerError(Exception):
    """Exceção customizada para erros do StreamManager."""
    pass

class StreamManager:
    """Gerenciador de streams do streamlink para ffmpeg (RTMP)."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._setup_logging()
        
    def _setup_logging(self):
        """Configura o logging básico."""
        logging.basicConfig(
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            level=logging.INFO
        )
    
    @staticmethod
    def _get_executable(name: str) -> Optional[Path]:
        """Localiza um executável no sistema."""
        path = shutil.which(name)
        return Path(path) if path else None
    
    async def _create_streamlink_process(
        self,
        config: StreamConfig
    ) -> asyncio.subprocess.Process:
        """Cria e configura o processo do streamlink."""
        streamlink_path = self._get_executable("streamlink")
        if not streamlink_path:
            raise StreamManagerError("Streamlink não encontrado no sistema")
            
        args = [
            str(streamlink_path),
            "--hls-live-edge", str(config.hls_live_edge),
            "--ringbuffer-size", config.ringbuffer_size,
            "-4",
            "--stream-sorting-excludes", f">{config.max_quality}",
            "--default-stream", config.stream_quality,
            "--url", config.url,
            "-o", "-"
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL
            )
            return process
        except Exception as e:
            raise StreamManagerError(f"Erro ao iniciar streamlink: {e}")

    async def _create_ffmpeg_process(
        self,
        rtmp_url: str
    ) -> asyncio.subprocess.Process:
        """Cria e configura o processo do ffmpeg."""
        ffmpeg_path = self._get_executable("ffmpeg")
        if not ffmpeg_path:
            raise StreamManagerError("FFmpeg não encontrado no sistema")
            
        # Ajuste: envia para rtmp://127.0.0.1{rtmp_url}
        args = [
            str(ffmpeg_path),
            "-re",
            "-hide_banner",
            "-nostats",
            "-v", "level+error",
            "-i", "pipe:0",
            "-c:v", "copy",
            "-c:a", "copy",
            "-f", "flv",
            f"rtmp://127.0.0.1{rtmp_url}"
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            return process
        except Exception as e:
            raise StreamManagerError(f"Erro ao iniciar ffmpeg: {e}")

    async def _stream_copy(
        self,
        source: asyncio.StreamReader,
        destination: asyncio.StreamWriter,
        chunk_size: int = 65536
    ) -> None:
        """Copia dados entre streams."""
        try:
            while True:
                chunk = await source.read(chunk_size)
                if not chunk:
                    break
                destination.write(chunk)
                await destination.drain()
        except Exception as e:
            self.logger.error(f"Erro na cópia do stream: {e}")
        finally:
            destination.close()
            await destination.wait_closed()

    async def _log_stream(
        self,
        prefix: str,
        stream: asyncio.StreamReader,
        level: int = logging.DEBUG
    ) -> None:
        """Processa e loga a saída de um stream."""
        while True:
            line = await stream.readline()
            if not line:
                break
            self.logger.log(level, f"{prefix}: {line.decode().strip()}")

    async def start_stream(self, config: StreamConfig) -> Tuple[int, int]:
        """
        Inicia o streaming do conteúdo.
        
        Returns:
            Tuple[int, int]: Códigos de retorno (streamlink, ffmpeg)
        """
        # Inicializa processos
        streamlink_proc = await self._create_streamlink_process(config)
        try:
            ffmpeg_proc = await self._create_ffmpeg_process(config.rtmp_details)
        except Exception:
            streamlink_proc.terminate()
            await streamlink_proc.wait()
            raise

        # Configura tasks
        tasks = [
            asyncio.create_task(self._stream_copy(
                streamlink_proc.stdout, 
                ffmpeg_proc.stdin
            )),
            asyncio.create_task(self._log_stream(
                "streamlink",
                streamlink_proc.stderr
            )),
            asyncio.create_task(self._log_stream(
                "ffmpeg",
                ffmpeg_proc.stderr
            ))
        ]

        try:
            # Aguarda conclusão da cópia principal
            await tasks[0]
        finally:
            # Cancela tasks de logging
            for task in tasks[1:]:
                task.cancel()
            
            # Aguarda término dos processos
            streamlink_rc = await streamlink_proc.wait()
            ffmpeg_rc = await ffmpeg_proc.wait()
            
            return streamlink_rc, ffmpeg_rc


# =============================================================================
# FILA DE VÍDEOS
# =============================================================================

class VideoQueue:
    """Classe para gerenciar a fila de vídeos a serem processados."""
    
    def __init__(self, channel_name: str = "", rtmp_details: str = ""):
        self.queue = asyncio.Queue()
        self.api_manager = APIManager()
        self.processing = False
        
        # Parâmetros adicionais para logs e config do RTMP
        self.channel_name = channel_name
        self.rtmp_details = rtmp_details

    async def add_video(self, video_url: str):
        """
        Adiciona um vídeo à fila para ser processado (streamlink+ffmpeg).
        
        Args:
            video_url: URL do vídeo
        """
        await self.queue.put(video_url)
        await log_message(f"[{self.channel_name}] Vídeo adicionado à fila: {video_url}", True)
        
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
                        await log_message(f"[{self.channel_name}] Sistema em ingestão, aguardando 30s...", True)
                        await asyncio.sleep(30)
                        continue
                    
                    # Processa o próximo vídeo
                    video_url = await self.queue.get()
                    await log_message(f"[{self.channel_name}] Processando vídeo da fila: {video_url}", True)
                    
                    # Configuração do stream
                    config = StreamConfig(
                        url=video_url,
                        rtmp_details=self.rtmp_details,  # ex: "/live/test"
                        hls_live_edge=6,
                        ringbuffer_size="128M",
                        max_quality="720p",
                        stream_quality="best"
                    )
                    
                    stream_manager = StreamManager()
                    
                    streamlink_rc, ffmpeg_rc = await stream_manager.start_stream(config)
                    success = (streamlink_rc == 0 and ffmpeg_rc == 0)

                    if success:
                        await log_message(f"[{self.channel_name}] Vídeo processado com sucesso: {video_url}", True)
                    else:
                        await log_message(
                            f"[{self.channel_name}] Falha ao processar vídeo (retornos: {streamlink_rc}, {ffmpeg_rc}): {video_url}",
                            True
                        )
                        
                    self.queue.task_done()
                    
                except Exception as e:
                    await log_message(f"[{self.channel_name}] Erro ao processar fila: {e}", True)
                    await asyncio.sleep(30)
                    
        self.processing = False


# =============================================================================
# PROCESSADOR DE VÍDEOS
# =============================================================================

class VideoProcessor:
    """Classe para processar e notificar (ou iniciar ingest) de novos vídeos."""
    
    def __init__(self, db_manager: Optional['DatabaseManager'] = None, channel_name: str = "", rtmp_details: str = ""):
        """
        Se db_manager for None, trabalha apenas em memória (canais manuais).
        """
        self.db_manager = db_manager
        self.video_queue = VideoQueue(channel_name=channel_name, rtmp_details=rtmp_details)
        
        # Se não há DB, usaremos estruturas em memória para armazenar IDs
        self.old_video_ids_memory = set()
        self.notified_video_ids_memory = {}

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

            if await self._handle_video_status(
                status,
                video_id,
                video_url,
                published_timestamp,
                current_timestamp,
                debug
            ):
                videos_to_notify[video_id] = current_timestamp

        if videos_to_notify:
            self.notified_video_ids_memory.update(videos_to_notify)
            await self.save_data()
            await log_message(f"Salvos {len(videos_to_notify)} novos vídeos notificados", debug=debug)

        self.old_video_ids_memory.update(new_videos)
        await self.save_data()
        await log_message(f"Salvos {len(new_videos)} novos IDs como antigos", debug=debug)

    async def fetch_and_classify_video_metadata(
        self,
        video_id: str,
        debug: bool = False
    ) -> Optional[Tuple[Dict, str]]:
        """
        Faz extração de metadados do vídeo e classifica seu status (live, VOD, etc.).
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
        Classifica o vídeo (live, VOD, upcoming, etc.) com base nos metadados do yt-dlp.
        """
        is_live_now = info.get("isLiveNow", False)
        is_live = info.get("is_live", False)
        is_upcoming = info.get("upcoming", False)
        was_live = info.get("was_live", False)

        if is_live_now and was_live:
            return "live"
        elif is_upcoming:
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

        elif status in ["upcoming_pre_launch", "live", "live_VOD", "VOD"]:
            await log_message(f"Novo {status} detectado: {video_url}", debug=debug)
            await self.video_queue.add_video(video_url)
            return True

        return False


# =============================================================================
# SERVIÇO PRINCIPAL DE MONITORAMENTO (PARA CANAIS CADASTRADOS NO JSON)
# =============================================================================

class MonitorService:
    """Serviço de monitoramento para canais com ID, usando banco de dados."""
    
    def __init__(self, channel_id: int, debug: bool = False, channel_name: str = "", rtmp_details: str = ""):
        self.channel_id = channel_id
        self.debug = debug
        self.db_manager = DatabaseManager(channel_id)
        # Adicionamos channel_name e rtmp_details para repassar ao VideoProcessor
        self.channel_name = channel_name
        self.rtmp_details = rtmp_details
        
        self.video_processor = None
        self.tab_monitor = None
        
    async def setup(self) -> bool:
        """Configura DB, carrega dados e prepara o monitor."""
        if not await self.db_manager.setup():
            return False
            
        self.video_processor = VideoProcessor(
            self.db_manager,
            channel_name=self.channel_name,
            rtmp_details=self.rtmp_details
        )
        await self.video_processor.load_data()  # Carrega old e notified

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
                    # Na primeira iteração, consideramos todos os IDs como 'antigos'
                    self.video_processor.old_video_ids_memory.update(new_video_ids)
                    await self.video_processor.save_data()
                    first_iteration = False
                    await log_message(
                        f"Primeira iteração: salvos {len(new_video_ids)} IDs como antigos",
                        debug=self.debug
                    )
                    await asyncio.sleep(SLEEP_INTERVAL)
                    continue

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
    def __init__(self, channel_urls: List[str], debug: bool = False, channel_name: str = "", rtmp_details: str = ""):
        self.channel_urls = channel_urls
        self.debug = debug
        
        # Usa VideoProcessor sem DB, mas inclui channel_name e rtmp_details
        self.video_processor = VideoProcessor(None, channel_name=channel_name, rtmp_details=rtmp_details)
        self.tab_monitor = TabMonitor(rate_limit=5, chunk_size=3)
        
        self.first_iteration = True

    async def setup(self) -> bool:
        """Carrega dados apenas em memória."""
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

    # NOVOS PARÂMETROS
    parser.add_argument(
        "--channel_name",
        type=str,
        default="(canal-desconhecido)",
        help="Nome do canal (apenas para logs informativos)."
    )

    parser.add_argument(
        "--rtmp_details",
        type=str,
        default="/live/test",
        help="Detalhes do RTMP, usado como sufixo em rtmp://127.0.0.1{rtmp_details}"
    )

    args = parser.parse_args()

    # Log do channel_name (apenas informativo)
    logging.info(f"Canal (apenas log): {args.channel_name}")

    # 1) Se for apenas executar streamlink em uma URL
    if args.execute_url:
        # Aqui, se quisermos usar ffmpeg + streamlink, podemos montar um config e rodar:
        loop = asyncio.get_event_loop()
        try:
            stream_manager = StreamManager()
            config = StreamConfig(
                url=args.execute_url,
                rtmp_details=args.rtmp_details
            )
            streamlink_rc, ffmpeg_rc = loop.run_until_complete(stream_manager.start_stream(config))
            success = (streamlink_rc == 0 and ffmpeg_rc == 0)
            if success:
                print("Stream finalizado com sucesso.")
            else:
                print(f"Falha no streaming (códigos de retorno: {streamlink_rc}, {ffmpeg_rc}).")
        finally:
            loop.close()
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
        service = ManualMonitorService(
            args.manual_channels,
            args.debug,
            channel_name=args.channel_name,
            rtmp_details=args.rtmp_details
        )
        setup_ok = asyncio.run(service.setup())
        if setup_ok:
            asyncio.run(service.start())
        return

    # 4) Se o usuário quer monitorar um canal específico via --monitor_channel
    if args.monitor_channel:
        service = MonitorService(
            args.monitor_channel,
            args.debug,
            channel_name=args.channel_name,
            rtmp_details=args.rtmp_details
        )
        setup_ok = asyncio.run(service.setup())
        if setup_ok:
            asyncio.run(service.start())
        return

    # 5) Caso contrário, se for apenas --channel_id
    if args.channel_id is None:
        parser.error("É necessário usar --channel_id, --manual_channels ou outro parâmetro (ex.: --list).")
        return

    service = MonitorService(
        args.channel_id,
        args.debug,
        channel_name=args.channel_name,
        rtmp_details=args.rtmp_details
    )
    setup_ok = asyncio.run(service.setup())
    if setup_ok:
        asyncio.run(service.start())


if __name__ == "__main__":
    main()
