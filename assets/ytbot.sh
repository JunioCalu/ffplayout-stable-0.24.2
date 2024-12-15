#!/bin/bash

# Recebe os parâmetros do canal
CHANNEL_ID="$1"
CHANNEL_NAME="$2"

# Verifica se os parâmetros foram fornecidos
if [ -z "$CHANNEL_ID" ] || [ -z "$CHANNEL_NAME" ]; then
    echo "Uso: $0 <CHANNEL_ID> <CHANNEL_NAME>"
    exit 1
fi

# Define o caminho do arquivo de log específico para o canal
LOG_FILE="/tmp/ytbot_${CHANNEL_ID}.log"

# Inicia o serviço para o canal
echo "ytbot iniciado para o canal ID: $CHANNEL_ID, Nome: $CHANNEL_NAME" >> "$LOG_FILE"

# Loop infinito para simular o serviço
while true; do
    echo "ytbot para canal $CHANNEL_NAME (ID: $CHANNEL_ID) rodando em $(date)" >> "$LOG_FILE"
    sleep 60  # Espera 60 segundos
done
