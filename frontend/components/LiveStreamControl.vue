<template>
  <div class="flex items-center justify-center gap-2 mt-5" :dark="colorMode.value === 'dark'">
    <!-- Streaming Input -->
    <input
      id="liveUrl"
      v-model="liveUrl"
      type="text"
      placeholder="Insira o link do YouTube"
      class="input input-bordered w-[700px] max-w-full focus:outline-white focus:outline-2"
      name="liveUrl"
    />

    <!-- Start Button (verde opaco quando não iniciado, verde brilhante quando streaming) -->
    <button
      class="btn"
      :class="{ 
        'bg-green-500 text-white shadow-lg hover:bg-green-400': isStreaming,    /* Verde brilhante com sombra quando streaming */
        'bg-green-700 text-white hover:bg-green-600': !isStreaming              /* Verde opaco com hover mais claro quando não iniciado */
      }"
      @click="startStream"
    >
      Start
    </button>

    <!-- Stop Button (cinza brilhante quando não iniciado, vermelho claro brilhante quando streaming) -->
    <button
      class="btn"
      :class="{ 
        'bg-red-500 text-white shadow-lg hover:bg-red-400': isStreaming,       /* Vermelho brilhante com hover mais claro quando streaming */
        'bg-gray-600 text-white hover:bg-gray-500': !isStreaming               /* Cinza brilhante com hover harmonioso quando não iniciado */
      }"
      @click="stopStream"
    >
      Stop
    </button>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';
const authStore = useAuth();
const indexStore = useIndex(); // Supondo que o indexStore seja importado dessa forma
const colorMode = useColorMode();
const configStore = useConfig()

const liveUrl = ref('');
const isStreaming = ref(false);
const contentType = { 'content-type': 'application/json;charset=UTF-8' };
const streamUpdateTimer = ref();

const { i } = storeToRefs(useConfig())

const channel = ref({} as Channel)

onMounted(() => {
  if (configStore.channels[i.value]) {
    channel.value = { ...configStore.channels[i.value] }
  }
})

watch([i], () => {
  if (configStore.channels[i.value]) {
    channel.value = { ...configStore.channels[i.value] }
  }
})

onMounted(() => {
  streamStatus();
});

onBeforeUnmount(() => {
  if (streamUpdateTimer.value) {
    clearTimeout(streamUpdateTimer.value); // Sem uso de "as NodeJS.Timeout"
  }
});

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
  return fetch('/api/livestream/ffmpeg/status', {
    method: 'GET',
    headers: { ...contentType, ...authStore.authHeader },
  })
    .then(async (response) => {
      const data = await response.json();
      if (response.ok) {
        isStreaming.value = data.status === 'active';
      } else {
        // Tratamento de erro em caso de falha na resposta da API
        indexStore.msgAlert('error', data.status || 'Erro ao obter status do stream', 4);
      }
    })
    .catch((error) => {
      console.error('Error getting stream status:', error);
      isStreaming.value = false;
      indexStore.msgAlert('error', 'Erro ao obter status do stream', 4);
    });
}

async function startStream() {
  if (!channel.value.id) {
    indexStore.msgAlert('error', 'Canal não encontrado', 3)
    return
  }
  return fetch(`/api/livestream/control/${channel.value.id}`, {
    method: 'POST',
    headers: { ...contentType, ...authStore.authHeader },
    body: JSON.stringify({
      action: 'start',
      url: liveUrl.value,
    }),
  })
    .then(async (response) => {
      const data = await response.json();
      if (response.ok) {
        isStreaming.value = true;
        indexStore.msgAlert('success', 'Stream iniciado com sucesso', 4);
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
    indexStore.msgAlert('error', 'Canal não encontrado', 3)
    return
  }
  return fetch(`/api/livestream/control/${channel.value.id}`, {
    method: 'POST',
    headers: { ...contentType, ...authStore.authHeader },
    body: JSON.stringify({ action: 'stop' }),
  })
    .then(async (response) => {
      const data = await response.json();
      if (response.ok) {
        isStreaming.value = false;
        indexStore.msgAlert('success', 'Stream parado com sucesso', 4);
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

<style scoped>

</style>