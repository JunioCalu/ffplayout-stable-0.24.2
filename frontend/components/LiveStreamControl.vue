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

const { i } = storeToRefs(configStore);
const channel = ref({} as ExtendedChannel);
const streamUpdateTimer = ref<ReturnType<typeof setTimeout> | null>(null);
const isStreamActive = ref(false);

const contentType = { 'content-type': 'application/json;charset=UTF-8' };

interface ExtendedChannel extends Channel {
  isStreaming: boolean;
  serviceStatus: string;
  liveUrl: string;
}

onMounted(() => {
  updateChannel();
  // Iniciar verificação de status apenas uma vez na montagem
  streamStatus();
});

watch(i, updateChannel);

onBeforeUnmount(() => {
  stopStatusCheck();
});

function stopStatusCheck() {
  if (streamUpdateTimer.value) {
    clearTimeout(streamUpdateTimer.value);
    streamUpdateTimer.value = null;
  }
}

function updateChannel() {
  if (configStore.channels[i.value]) {
    channel.value = { 
      ...configStore.channels[i.value], 
      liveUrl: getLiveUrlFromLocalStorage(configStore.channels[i.value].id) 
    } as ExtendedChannel;
  }
}

function saveLiveUrlToLocalStorage() {
  if (channel.value.id) {
    localStorage.setItem(`liveUrl_${channel.value.id}`, channel.value.liveUrl);
  }
}

function getLiveUrlFromLocalStorage(channelId: number): string {
  return localStorage.getItem(`liveUrl_${channelId}`) || '';
}

async function streamStatus() {
  if (streamUpdateTimer.value) return; // Evita múltiplas instâncias do loop

  async function updateStreamStatus() {
    if (!isStreamActive.value && !channel.value.isStreaming) {
      stopStatusCheck();
      return;
    }

    await getStreamStatus();
    streamUpdateTimer.value = setTimeout(updateStreamStatus, 1000);
  }

  await updateStreamStatus();
}

async function getStreamStatus() {
  if (!channel.value.id) return;

  try {
    const response = await fetch(`/api/livestream/ffmpeg/status/${channel.value.id}`, {
      method: 'GET',
      headers: { ...contentType, ...authStore.authHeader },
    });

    const clonedResponse = response.clone();
    const rawData = await clonedResponse.text();
    console.log("getStreamStatus: ", rawData);

    if (!response.ok) {
      throw new Error(rawData);
    }

    const data = await response.json();
    const wasStreaming = channel.value.isStreaming;
    const newStreamingState = data.status === 'active';
    
    channel.value.isStreaming = newStreamingState;
    channel.value.serviceStatus = newStreamingState ? 'On' : 'Off';
    isStreamActive.value = newStreamingState;

    // Se o stream estava ativo e agora está inativo
    if (wasStreaming && !newStreamingState) {
      indexStore.msgAlert('warning', 'Stream Encerrado', 4);
      stopStatusCheck();
    }

  } catch (error) {
    console.error('Error getting stream status:', error);
    channel.value.isStreaming = false;
    channel.value.serviceStatus = 'Off';
    isStreamActive.value = false;
    indexStore.msgAlert('error', 'Erro ao obter status do stream', 4);
    stopStatusCheck();
  }
}

async function startStream() {
  if (!channel.value.id) {
    indexStore.msgAlert('error', 'Canal não encontrado', 3);
    return;
  }

  try {
    const response = await fetch(`/api/livestream/control/${channel.value.id}`, {
      method: 'POST',
      headers: { ...contentType, ...authStore.authHeader },
      body: JSON.stringify({
        action: 'start',
        url: channel.value.liveUrl,
      }),
    });

    const data = await response.text();

    if (!response.ok) {
      throw new Error(data);
    }

    channel.value.isStreaming = true;
    channel.value.serviceStatus = 'On';
    isStreamActive.value = true;
    indexStore.msgAlert('success', data, 4);
    
    // Reiniciar verificação de status após iniciar stream
    streamStatus();

  } catch (error) {
    console.error('Error starting stream:', error);
    indexStore.msgAlert('error', `Erro ao iniciar o stream: ${error}`, 4);
  }
}

async function stopStream() {
  if (!channel.value.id) {
    indexStore.msgAlert('error', 'Canal não encontrado', 3);
    return;
  }

  try {
    const response = await fetch(`/api/livestream/control/${channel.value.id}`, {
      method: 'POST',
      headers: { ...contentType, ...authStore.authHeader },
      body: JSON.stringify({ action: 'stop' }),
    });

    const data = await response.text();

    if (!response.ok) {
      throw new Error(data);
    }

    channel.value.isStreaming = false;
    channel.value.serviceStatus = 'Off';
    isStreamActive.value = false;
    indexStore.msgAlert('success', data, 4);
    indexStore.msgAlert('warning', 'Stream Encerrado', 4);
    stopStatusCheck();

  } catch (error) {
    console.error('Error stopping stream:', error);
    indexStore.msgAlert('error', `Erro ao parar o stream: ${error}`, 4);
  }
}
</script>