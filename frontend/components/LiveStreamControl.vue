<template>
  <div class="flex flex-col md:flex-row items-center justify-center gap-4 mt-5 w-full">
    <!-- Streaming Input -->
    <div class="flex-1 w-full">
      <input
        id="liveUrl"
        v-model="channel.liveUrl"
        type="text"
        placeholder="Insira o link do YouTube"
        class="input input-bordered w-full focus:outline-white focus:outline-2"
        name="liveUrl"
        @input="saveLiveUrlToLocalStorage"
      />
    </div>

    <!-- Botões Start e Stop -->
    <div class="flex gap-2">
      <!-- Start Button -->
      <button
        class="btn"
        :class="{ 
          'bg-green-500 text-white shadow-lg hover:bg-green-400': channel.isStreaming,
          'bg-green-700 text-white hover:bg-green-600': !channel.isStreaming
        }"
        @click="startStream"
      >
        Start
      </button>

      <!-- Stop Button -->
      <button
        class="btn"
        :class="{ 
          'bg-red-500 text-white shadow-lg hover:bg-red-400': channel.isStreaming,
          'bg-gray-600 text-white hover:bg-gray-500': !channel.isStreaming
        }"
        @click="stopStream"
      >
        Stop
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';

const authStore = useAuth();
const indexStore = useIndex();
const colorMode = useColorMode();
const configStore = useConfig();

const { i } = storeToRefs(configStore); // Obter o índice do canal atualmente selecionado
const channel = ref({} as ExtendedChannel); // Usar o tipo estendido

const contentType = { 'content-type': 'application/json;charset=UTF-8' };
const streamUpdateTimer = ref();

// Definir o tipo estendido para Channel
interface ExtendedChannel extends Channel {
  isStreaming: boolean;
  serviceStatus: string;
  liveUrl: string; // Adicionar liveUrl ao tipo estendido
}

onMounted(() => {
  updateChannel();
  streamStatus();
});

watch(i, updateChannel); // Atualizar o canal quando o índice mudar

onBeforeUnmount(() => {
  if (streamUpdateTimer.value) {
    clearTimeout(streamUpdateTimer.value);
  }
});

function updateChannel() {
  if (configStore.channels[i.value]) {
    channel.value = { 
      ...configStore.channels[i.value], 
      liveUrl: getLiveUrlFromLocalStorage(configStore.channels[i.value].id) // Recuperar liveUrl do localStorage
    } as ExtendedChannel; // Atualizar o canal ativo
  }
}

// Função para salvar liveUrl no localStorage
function saveLiveUrlToLocalStorage() {
  if (channel.value.id) {
    localStorage.setItem(`liveUrl_${channel.value.id}`, channel.value.liveUrl);
  }
}

// Função para recuperar liveUrl do localStorage
function getLiveUrlFromLocalStorage(channelId: number): string {
  return localStorage.getItem(`liveUrl_${channelId}`) || '';
}

async function streamStatus() {
  async function updateStreamStatus(resolve: any) {
    await getStreamStatus()
      .then(() => {
        streamUpdateTimer.value = setTimeout(() => updateStreamStatus(resolve), 1000); // Timer de 1 segundo
      });
  }

  // Chamada inicial para obter o status e continuar as chamadas subsequentes
  return new Promise((resolve) => updateStreamStatus(resolve));
}

async function getStreamStatus() {
  if (!channel.value.id) return;

  return fetch(`/api/livestream/ffmpeg/status/${channel.value.id}`, {
    method: 'GET',
    headers: { ...contentType, ...authStore.authHeader },
  })
    .then(async (response) => {
      const data = await response.json();
      if (response.ok) {
        channel.value.isStreaming = data.status === 'active'; // Atualizar o estado de streaming no canal
        channel.value.serviceStatus = channel.value.isStreaming ? 'On' : 'Off'; // Atualizar o status do serviço
      } else {
        // Tratamento de erro em caso de falha na resposta da API
        indexStore.msgAlert('error', data.status || 'Erro ao obter status do stream', 4);
      }
    })
    .catch((error) => {
      console.error('Error getting stream status:', error);
      channel.value.isStreaming = false; // Atualizar o estado de streaming no canal
      channel.value.serviceStatus = 'Off'; // Atualizar o status do serviço
      indexStore.msgAlert('error', 'Erro ao obter status do stream', 4);
    });
}

async function startStream() {
  if (!channel.value.id) {
    indexStore.msgAlert('error', 'Canal não encontrado', 3);
    return;
  }

  return fetch(`/api/livestream/control/${channel.value.id}`, {
    method: 'POST',
    headers: { ...contentType, ...authStore.authHeader },
    body: JSON.stringify({
      action: 'start',
      url: channel.value.liveUrl, // Usar a URL do canal selecionado
    }),
  })
    .then(async (response) => {
      const data = await response.text();
      if (response.ok) {
        channel.value.isStreaming = true; // Atualizar o estado de streaming no canal
        channel.value.serviceStatus = 'On'; // Atualizar o status do serviço
        indexStore.msgAlert('success', data, 4);
      } else {
        indexStore.msgAlert('error', data || 'Erro ao iniciar o stream', 4);
      }
    })
    .catch((error) => {
      console.error('Error starting stream:', error);
      indexStore.msgAlert('error', `Erro ao iniciar o stream: ${error}`, 4);
    });
}

async function stopStream() {
  if (!channel.value.id) {
    indexStore.msgAlert('error', 'Canal não encontrado', 3);
    return;
  }

  return fetch(`/api/livestream/control/${channel.value.id}`, {
    method: 'POST',
    headers: { ...contentType, ...authStore.authHeader },
    body: JSON.stringify({ action: 'stop' }),
  })
    .then(async (response) => {
      const data = await response.text();
      if (response.ok) {
        channel.value.isStreaming = false; // Atualizar o estado de streaming no canal
        channel.value.serviceStatus = 'Off'; // Atualizar o status do serviço
        indexStore.msgAlert('success', data, 4);
      } else {
        indexStore.msgAlert('error', data || 'Erro ao parar o stream', 4);
      }
    })
    .catch((error) => {
      console.error('Error stopping stream:', error);
      indexStore.msgAlert('error', `Erro ao parar o stream: ${error}`, 4);
    });
}
</script>