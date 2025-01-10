#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import time
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

import aiohttp
from yt_dlp import YoutubeDL

# =============================================================================
# CONFIGURAÇÕES GLOBAIS
# =============================================================================

CHANNELS_FILE = os.path.expanduser("~/workspace/livebot/channels.json")

# Intervalo de checagem em segundos (padrão: 5 minutos = 300).
SLEEP_INTERVAL = 5

MAX_RETRIES = 3

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(os.path.expanduser("~/workspace/livebot/bot.log")),
        logging.StreamHandler(),
    ],
)

def handle_signal(sig, _frame):
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

home_directory = os.path.expanduser("~")
cookie_file_path = os.path.join(home_directory, "workspace/livebot", "cookies.txt")

if not os.path.exists(os.path.dirname(cookie_file_path)):
    os.makedirs(os.path.dirname(cookie_file_path))

ydl_opts = {
    "call_home": False,
    "forcejson": True,
    "logger": YoutubeDLLogger(),
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
    "cookies": cookie_file_path,
}

# =============================================================================
# NOVO MONITOR DE CANAIS
# =============================================================================

class TabMonitor:
    """Monitor de canais do YouTube."""

    def __init__(self, rate_limit: int = 5, chunk_size: int = 3):
        self.rate_limit = asyncio.Semaphore(rate_limit)
        self.chunk_size = chunk_size
        self.session = None
        self.seen_ids = set()
        self.videos_loaded = 0

    async def __aenter__(self):
        """Inicializa a sessão HTTP (aiohttp)."""
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Fecha a sessão HTTP."""
        if self.session:
            await self.session.close()

    def _classify_video_status(self, info: Dict) -> str:
        """Classifica o status do vídeo com base nos metadados."""
        current_time = int(time.time())
        release_ts = info.get("release_timestamp", 0)
        release_ts = 0 if release_ts in [None, "null"] else int(release_ts)

        has_duration = info.get("duration", None)
        has_formats = info.get("formats", [])

        sources = [
            f.get("url", "") or f.get("manifest_url", "")
            for f in has_formats
            if "url" or "manifest_url" in f
        ]
        has_live_broadcast = any("yt_live_broadcast" in s for s in sources)
        has_premiere_broadcast = any("yt_premiere_broadcast" in s for s in sources)

        if (has_live_broadcast and
            info.get("is_live", False) is True and
            info.get("live_status", "") == "is_live" and
            info.get("was_live", None) is False and
            not has_duration):
            return "live"

        elif (has_premiere_broadcast and
            info.get("live_status", "") == "is_live" and
            release_ts and
            isinstance(release_ts, int) and
            info.get("was_live", None) is False and
            has_duration and
            isinstance(has_duration, int)):
            return "upcoming_launched"

        elif (info.get("live_status", "") == "is_upcoming" and
            release_ts and
            isinstance(release_ts, int) and
            release_ts >= current_time and
            info.get("was_live", None) is False and
            not has_formats):
            return "upcoming_scheduled"

        elif (info.get("live_status", "") == "post_live" or
            info.get("live_status", "") == "was_live" and
            release_ts and
            isinstance(release_ts, int)):
            return "live_VOD"

        elif (info.get("live_status", "") == "not_live" and
            info.get("was_live", None) is False and
            release_ts and
            isinstance(release_ts, int)):
            return "live_VOD_Upcoming"

        return "VOD"

    async def process_entry(self, entry: Dict, is_initial: bool = False, debug: bool = False) -> Optional[str]:
        """Processa uma entrada de vídeo e retorna o ID se for novo."""
        if isinstance(entry, dict):
            video_id = entry.get('id')
            live_status = entry.get('live_status', '')
            
            if video_id and video_id not in self.seen_ids:
                if is_initial:
                    self.seen_ids.add(video_id)
                    self.videos_loaded += 1
                    
                    if live_status == 'is_live':
                        url = f"https://www.youtube.com/watch?v={video_id}"
                        with YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(url, download=False)
                            status = self._classify_video_status(info)
                            await log_message(
                                f"[CARGA INICIAL] Vídeo ao vivo detectado: {url}, Status: {status}",
                                debug=debug
                            )
                else:
                    self.seen_ids.add(video_id)
                    url = f"https://www.youtube.com/watch?v={video_id}"
                    with YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=False)
                        status = self._classify_video_status(info)
                        await log_message(
                            f"\nNovo vídeo detectado: {url}, Status: {status}",
                            debug=debug
                        )
                return video_id
        return None

    async def monitor_tabs(
            self, channel_urls: List[str], debug: bool = False, initial_load: bool = True
        ) -> Set[str]:
            """
            Monitora cada canal em uma única solicitação.

            Args:
                channel_urls: Lista de URLs de canais
                debug: Flag para logs de debug
                initial_load: Flag para indicar carga inicial

            Returns:
                Set[str]: Conjunto de IDs de vídeos únicos encontrados
            """
            if initial_load:
                await log_message("Iniciando carregamento de vídeos...", debug=debug)
            else:
                await log_message("\nVerificando por novos vídeos...", debug=debug)

            valid_urls = self._validate_urls(channel_urls)
            if not valid_urls:
                await log_message("Nenhuma URL válida fornecida", debug=debug)
                return set()

            new_video_ids = set()

            async with self:
                for url in valid_urls:
                    try:
                        with YoutubeDL(ydl_opts) as ydl:
                            result = ydl.extract_info(url, download=False)
                            
                            if 'entries' in result:
                                for entry in result['entries']:
                                    if isinstance(entry, dict):
                                        if 'entries' in entry:  # Processa subentradas
                                            for subentry in entry['entries']:
                                                video_id = await self.process_entry(
                                                    subentry, 
                                                    is_initial=initial_load,
                                                    debug=debug
                                                )
                                                if video_id:
                                                    new_video_ids.add(video_id)
                                        else:
                                            video_id = await self.process_entry(
                                                entry,
                                                is_initial=initial_load,
                                                debug=debug
                                            )
                                            if video_id:
                                                new_video_ids.add(video_id)

                    except Exception as e:
                        await log_message(f"Erro ao processar {url}: {e}", debug=debug)
                        continue

            if initial_load:
                await log_message(
                    f"\nCarregamento inicial concluído. {self.videos_loaded} vídeos encontrados",
                    debug=debug
                )
                self.videos_loaded = 0  # Reset counter
            else:
                await log_message(
                    f"Total de novos vídeos encontrados: {len(new_video_ids)}",
                    debug=debug
                )

            return new_video_ids

    def _validate_urls(self, urls: List[str]) -> List[str]:
        """Valida e padroniza as URLs fornecidas."""
        valid_urls = []
        for url in urls:
            try:
                parsed = urlparse(url)
                if parsed.scheme and parsed.netloc and "youtube.com" in parsed.netloc:
                    clean_url = (
                        f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
                    )
                    valid_urls.append(clean_url)
            except Exception:
                pass
        return valid_urls

# =============================================================================
# GERENCIAMENTO DE CANAIS
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
# STREAM MANAGER
# =============================================================================

class StreamManager:
    """Gerenciador de streams usando ffmpeg."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    async def start_stream(self, url: str, rtmp_details: str) -> Tuple[int, int]:
        """
        Inicia o streaming do conteúdo usando ffmpeg.

        Args:
            url: URL do vídeo/live
            rtmp_details: Detalhes do endpoint RTMP

        Returns:
            Tuple[int, int]: Códigos de retorno (streamlink, ffmpeg)
        """
        streamlink_proc = None
        ffmpeg_proc = None

        try:
            # Inicia o processo do streamlink
            streamlink_cmd = [
                "streamlink",
                "--hls-live-edge", "6",
                "--ringbuffer-size", "128M",
                "-4",
                "--stream-sorting-excludes", ">720p",
                "--default-stream", "best",
                "--url", url,
                "-o", "-"
            ]

            streamlink_proc = await asyncio.create_subprocess_exec(
                *streamlink_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # Inicia o processo do ffmpeg
            ffmpeg_cmd = [
                "ffmpeg",
                "-re",
                "-hide_banner",
                "-nostats",
                "-v", "level+error",
                "-i", "pipe:0",
                "-c:v", "copy",
                "-c:a", "copy",
                "-f", "flv",
                f"rtmp://127.0.0.1{rtmp_details}"
            ]

            ffmpeg_proc = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdin=streamlink_proc.stdout,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # Aguarda a conclusão dos processos
            streamlink_rc = await streamlink_proc.wait()
            ffmpeg_rc = await ffmpeg_proc.wait()

            return streamlink_rc, ffmpeg_rc

        except Exception as e:
            self.logger.error(f"Erro ao iniciar stream: {e}")
            if streamlink_proc:
                streamlink_proc.terminate()
            if ffmpeg_proc:
                ffmpeg_proc.terminate()
            return -1, -1

# =============================================================================
# MONITOR SERVICE
# =============================================================================

class MonitorService:
    """Serviço principal de monitoramento."""

    def __init__(self, channel_id: int, debug: bool = False, 
                 channel_name: str = "", rtmp_details: str = ""):
        self.channel_id = channel_id
        self.debug = debug
        self.channel_name = channel_name
        self.rtmp_details = rtmp_details
        self.tab_monitor = TabMonitor(rate_limit=5, chunk_size=3)
        self.stream_manager = StreamManager()

    async def _load_channel_urls(self) -> List[str]:
        """Carrega as URLs do canal via JSON."""
        channels = await ChannelManager.load_channels(self.debug)
        return channels.get(self.channel_id, [])

    async def start(self):
        """Inicia o loop de monitoramento."""
        channel_urls = await self._load_channel_urls()
        if not channel_urls:
            await log_message(
                f"Canal {self.channel_id} não encontrado ou sem URLs configuradas",
                debug=self.debug
            )
            return

        # Primeira execução com carga inicial
        await self.tab_monitor.monitor_tabs(
            channel_urls, 
            self.debug, 
            initial_load=True
        )

        while True:
            try:
                new_video_ids = await self.tab_monitor.monitor_tabs(
                    channel_urls,
                    self.debug,
                    initial_load=False
                )

                for video_id in new_video_ids:
                    url = f"https://www.youtube.com/watch?v={video_id}"
                    await log_message(
                        f"Iniciando stream para: {url}",
                        debug=self.debug
                    )
                    streamlink_rc, ffmpeg_rc = await self.stream_manager.start_stream(
                        url,
                        self.rtmp_details
                    )
                    
                    if streamlink_rc == 0 and ffmpeg_rc == 0:
                        await log_message(
                            f"Stream finalizado com sucesso: {url}",
                            debug=self.debug
                        )
                    else:
                        await log_message(
                            f"Falha no stream (códigos: {streamlink_rc}, {ffmpeg_rc}): {url}",
                            debug=self.debug
                        )

                await log_message(
                    f"Aguardando {SLEEP_INTERVAL} segundos...",
                    debug=self.debug
                )
                await asyncio.sleep(SLEEP_INTERVAL)

            except Exception as e:
                await log_message(f"Erro no monitoramento: {e}", debug=self.debug)
                await asyncio.sleep(SLEEP_INTERVAL)

# =============================================================================
# FUNÇÃO MAIN
# =============================================================================

def main():
    """Ponto de entrada principal para execução via CLI."""
    parser = argparse.ArgumentParser(description="Monitor de canais do YouTube")
    
    parser.add_argument(
        "--channel_id",
        type=int,
        required=True,
        help="ID do canal a monitorar (conforme configurado no arquivo JSON)"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Ativa logs de debug"
    )

    parser.add_argument(
        "--channel_name",
        type=str,
        default="(canal-desconhecido)",
        help="Nome do canal (apenas para logs informativos)"
    )

    parser.add_argument(
        "--rtmp_details",
        type=str,
        default="/live/test",
        help="Detalhes do RTMP, usado como sufixo em rtmp://127.0.0.1{rtmp_details}"
    )

    args = parser.parse_args()

    service = MonitorService(
        args.channel_id,
        args.debug,
        channel_name=args.channel_name,
        rtmp_details=args.rtmp_details
    )
    
    asyncio.run(service.start())

if __name__ == "__main__":
    main()
