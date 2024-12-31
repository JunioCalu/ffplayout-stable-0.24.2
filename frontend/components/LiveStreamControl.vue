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

    <!-- Stream Control Buttons -->
    <div class="flex gap-2">
      <button
        class="btn"
        :class="{
          'bg-green-500 text-white shadow-lg hover:bg-green-400': channel.isStreaming,
          'bg-green-700 text-white hover:bg-green-600': !channel.isStreaming,
          'opacity-50': isLoading,
        }"
        @click="startStream"
      >
        Start
      </button>

      <button
        class="btn"
        :class="{
          'bg-red-500 text-white shadow-lg hover:bg-red-400': channel.isStreaming,
          'bg-gray-600 text-white hover:bg-gray-500': !channel.isStreaming,
          'opacity-50': isLoading,
        }"
        @click="stopStream"
      >
        Stop
      </button>
    </div>
  </div>
  <!-- Exemplo de exibição de mensagem de erro -->
  <p v-if="errorMessage" class="text-red-500 text-sm mt-2">{{ errorMessage }}</p>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount } from "vue";

// Tipos
interface Channel {
  id: number;
  name: string;
  // Adicione outras propriedades do canal conforme necessário
}

interface ExtendedChannel extends Channel {
  isStreaming: boolean;
  liveUrl: string;
}

// Estrutura de resposta para o status do stream
interface StreamResponse {
  status: string;
}

// Stores
const authStore = useAuth();
const indexStore = useIndex();
const configStore = useConfig();
const { i } = storeToRefs(configStore);
const contentType = { "content-type": "application/json;charset=UTF-8" };

// Estado reativo principal do canal
const channel = ref<ExtendedChannel>({
  id: 0,
  name: "",
  isStreaming: false,
  liveUrl: "",
} as ExtendedChannel);

// Outras refs reativas
const isLoading = ref(false);
const errorMessage = ref("");
const streamUpdateTimer = ref<NodeJS.Timeout | null>(null);
const isStreamActive = ref(false);

// Intervalo para rechecagem do stream
const STREAM_CHECK_INTERVAL = 1000; // 1 segundo

// Funções para salvar e carregar a URL de live no LocalStorage
const storage = {
  getLiveUrl: (channelId: number): string =>
    localStorage.getItem(`liveUrl_${channelId}`) || "",
  setLiveUrl: (channelId: number, url: string): void =>
    localStorage.setItem(`liveUrl_${channelId}`, url),
};

// -----------------------------------------------------------------------------
// Funções de requisição usando .then(async), .catch(), .finally()
// -----------------------------------------------------------------------------

// Obtém status do stream
function getStreamStatus(channelId: number) {
  return fetch(`/api/livestream/ffmpeg/status/${channelId}`, {
    method: "GET",
    headers: { ...contentType, ...authStore.authHeader },
  })
    .then(async (response) => {
      const clonedResponse = response.clone();
      const rawData = await clonedResponse.text();

      if (!response.ok) {
        throw new Error(rawData);
      }

      const data = (await response.json()) as StreamResponse;
      return data;
    })
    .catch((error) => {
      console.error("Error getting stream status:", error);
      throw error;
    });
}

// Controla o stream (iniciar ou parar)
function controlStream(channelId: number, action: "start" | "stop", url?: string) {
  return fetch(`/api/livestream/control/${channelId}`, {
    method: "POST",
    headers: { ...contentType, ...authStore.authHeader },
    body: JSON.stringify({ action, ...(url ? { url } : {}) }),
  })
    .then(async (response) => {
      const clonedResponse = response.clone();
      const rawData = await clonedResponse.text();

      if (!response.ok) {
        throw new Error(rawData);
      }

      return rawData; // Retornamos a mensagem de sucesso
    })
    .catch((error) => {
      console.error(`Error while ${action}ing the stream:`, error);
      throw error;
    });
}

// -----------------------------------------------------------------------------
// Funções de gerenciamento do status do stream
// -----------------------------------------------------------------------------

// Checa o status atual do stream (chamada pontual)
function checkStreamStatus() {
  if (!channel.value.id) return;

  isLoading.value = true;
  errorMessage.value = "";

  getStreamStatus(channel.value.id)
    .then((data) => {
      const newStreamingState = data.status === "active";
      channel.value.isStreaming = newStreamingState;

      // Se estiver ativo, iniciamos o loop de checagem periódica
      if (newStreamingState && !streamUpdateTimer.value) {
        startStatusCheck();
      }
      // Caso contrário, interrompemos
      else if (!newStreamingState) {
        stopStatusCheck();
      }
    })
    .catch((error) => {
      console.error("Error checking stream status:", error);
      errorMessage.value = `Erro ao verificar status do stream: ${
        error.message || error
      }`;
      channel.value.isStreaming = false;
      stopStatusCheck();
    })
    .finally(() => {
      isLoading.value = false;
    });
}

// Atualiza o status do stream em loop, usando setTimeout
function updateStreamStatus() {
  if (!channel.value.id || !isStreamActive.value) return;

  getStreamStatus(channel.value.id)
    .then((data) => {
      const newStreamingState = data.status === "active";

      // Se ficar inativo, exibe aviso
      if (!newStreamingState && channel.value.isStreaming) {
        indexStore.msgAlert("warning", "Stream Encerrado", 4);
      }

      channel.value.isStreaming = newStreamingState;

      if (newStreamingState) {
        // Reagendamos nova checagem se ainda estiver ativo
        streamUpdateTimer.value = setTimeout(updateStreamStatus, STREAM_CHECK_INTERVAL);
      } else {
        stopStatusCheck();
      }
    })
    .catch((error) => {
      console.error("Error updating stream status:", error);
      errorMessage.value = `Erro ao atualizar status do stream: ${
        error.message || error
      }`;
      channel.value.isStreaming = false;
      stopStatusCheck();
    });
}

// Inicia o loop de checagem de status com setTimeout
function startStatusCheck() {
  if (streamUpdateTimer.value) return;
  isStreamActive.value = true;
  updateStreamStatus();
}

// Para o loop de checagem de status
function stopStatusCheck() {
  if (streamUpdateTimer.value) {
    clearTimeout(streamUpdateTimer.value);
    streamUpdateTimer.value = null;
  }
  isStreamActive.value = false;
}

// -----------------------------------------------------------------------------
// Funções de controle do stream (iniciar/parar) chamadas pelos botões
// -----------------------------------------------------------------------------

function startStream() {
  if (!channel.value.id) {
    indexStore.msgAlert("error", "Canal não encontrado ou URL não fornecida", 3);
    return;
  }

  isLoading.value = true;
  errorMessage.value = "";

  controlStream(channel.value.id, "start", channel.value.liveUrl)
    .then((responseMessage) => {
      checkStreamStatus();
      indexStore.msgAlert("success", responseMessage, 4);
    })
    .catch((error) => {
      console.error("Error starting stream:", error);
      errorMessage.value = `Erro ao iniciar o stream: ${error.message || error}`;
      indexStore.msgAlert("error", `Erro ao iniciar o stream: ${error}`, 4);
    })
    .finally(() => {
      isLoading.value = false;
    });
}

function stopStream() {
  if (!channel.value.id) {
    indexStore.msgAlert("error", "Canal não encontrado", 3);
    return;
  }

  isLoading.value = true;
  errorMessage.value = "";

  controlStream(channel.value.id, "stop")
    .then((responseMessage) => {
      checkStreamStatus();
      indexStore.msgAlert("success", responseMessage, 4);
      indexStore.msgAlert("warning", "Stream Encerrado", 4);
    })
    .catch((error) => {
      console.error("Error stopping stream:", error);
      errorMessage.value = `Erro ao parar o stream: ${error.message || error}`;
      indexStore.msgAlert("error", `Erro ao parar o stream: ${error}`, 4);
    })
    .finally(() => {
      isLoading.value = false;
    });
}

// -----------------------------------------------------------------------------
// Funções auxiliares de canal
// -----------------------------------------------------------------------------

function updateChannel() {
  if (configStore.channels[i.value]) {
    const channelId = configStore.channels[i.value].id;
    channel.value = {
      ...configStore.channels[i.value],
      liveUrl: storage.getLiveUrl(channelId),
      isStreaming: false,
    } as ExtendedChannel;

    // Checa o status inicial do stream
    checkStreamStatus();
  }
}

function saveLiveUrlToLocalStorage() {
  if (channel.value.id) {
    storage.setLiveUrl(channel.value.id, channel.value.liveUrl);
  }
}

// -----------------------------------------------------------------------------
// Ciclo de vida do componente
// -----------------------------------------------------------------------------

onMounted(() => {
  updateChannel();
});

onBeforeUnmount(() => {
  stopStatusCheck();
});

// Observa mudanças de índice (caso o usuário mude de canal no configStore)
watch(i, updateChannel);
</script>

<style scoped>
/* Estilos opcionais para personalizar os botões e layout */
</style>
