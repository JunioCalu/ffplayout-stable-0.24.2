<template>
  <div class="flex flex-col md:flex-row items-center justify-center gap-4 mt-5 w-full">
    <!-- Streaming Input -->
    <div class="flex-1 w-full">
      <input
        id="liveUrl"
        v-model="liveStreamStore.channel.liveUrl"
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
          'bg-green-500 text-white shadow-lg hover:bg-green-600': liveStreamStore.channel.isStreaming,
          'bg-green-700 text-white hover:bg-green-600': !liveStreamStore.channel.isStreaming,
          'opacity-50': isLoading,
        }"
        @click="startStream"
      >
        Start
      </button>

      <button
        class="btn"
        :class="{
          'bg-red-500 text-white shadow-lg hover:bg-red-600': liveStreamStore.channel.isStreaming,
          'bg-gray-600 text-white hover:bg-gray-500': !liveStreamStore.channel.isStreaming,
          'opacity-50': isLoading,
        }"
        @click="stopStream"
      >
        Stop
      </button>
    </div>
  </div>
  <!-- mensagem de erro -->
  <p v-if="errorMessage" class="text-red-500 mt-2">{{ errorMessage }}</p>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount } from "vue";
import { useLiveStreamStore } from '@/stores/liveStream';

// Stores
const authStore = useAuth();
const indexStore = useIndex();
const configStore = useConfig();
const liveStreamStore = useLiveStreamStore();
const { i } = storeToRefs(configStore);
const contentType = { "content-type": "application/json;charset=UTF-8" };

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

// Funções de requisição usando .then(async), .catch(), .finally()
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

      const data = (await response.json()) as { status: string };
      return data;
    })
    .catch((error) => {
      console.error("Error getting stream status:", error);
      throw error;
    });
}

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

      return rawData;
    })
    .catch((error) => {
      console.error(`Error while ${action}ing the stream:`, error);
      throw error;
    });
}

// Funções de gerenciamento do status do stream
function checkStreamStatus() {
  if (!liveStreamStore.channel.id) return;

  isLoading.value = true;
  errorMessage.value = "";

  getStreamStatus(liveStreamStore.channel.id)
    .then((data) => {
      const newStreamingState = data.status === "active";
      liveStreamStore.setStreamingStatus(newStreamingState);

      if (newStreamingState && !streamUpdateTimer.value) {
        startStatusCheck();
      } else if (!newStreamingState) {
        stopStatusCheck();
      }
    })
    .catch((error) => {
      console.error("Error checking stream status:", error);
      errorMessage.value = `Erro ao verificar status do stream: ${
        error.message || error
      }`;
      liveStreamStore.setStreamingStatus(false);
      stopStatusCheck();
    })
    .finally(() => {
      isLoading.value = false;
    });
}

function updateStreamStatus() {
  if (!liveStreamStore.channel.id || !isStreamActive.value) return;

  getStreamStatus(liveStreamStore.channel.id)
    .then((data) => {
      const newStreamingState = data.status === "active";

      if (!newStreamingState && liveStreamStore.channel.isStreaming) {
        indexStore.msgAlert(
          "warning",
          `Stream Encerrado para o canal ${liveStreamStore.channel.name}`,
          4
        );
      }

      liveStreamStore.setStreamingStatus(newStreamingState);

      if (newStreamingState) {
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
      liveStreamStore.setStreamingStatus(false);
      stopStatusCheck();
    });
}

function startStatusCheck() {
  if (streamUpdateTimer.value) return;
  isStreamActive.value = true;
  updateStreamStatus();
}

function stopStatusCheck() {
  if (streamUpdateTimer.value) {
    clearTimeout(streamUpdateTimer.value);
    streamUpdateTimer.value = null;
  }
  isStreamActive.value = false;
}

// Funções de controle do stream
function startStream() {
  if (!liveStreamStore.channel.id) {
    indexStore.msgAlert("error", "Canal não encontrado ou URL não fornecida", 3);
    return;
  }

  isLoading.value = true;
  errorMessage.value = "";

  controlStream(liveStreamStore.channel.id, "start", liveStreamStore.channel.liveUrl)
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
  if (!liveStreamStore.channel.id) {
    indexStore.msgAlert("error", "Canal não encontrado", 3);
    return;
  }

  isLoading.value = true;
  errorMessage.value = "";

  controlStream(liveStreamStore.channel.id, "stop")
    .then((responseMessage) => {
      checkStreamStatus();
      indexStore.msgAlert("success", responseMessage, 4);
      indexStore.msgAlert(
        "warning",
        `Stream Encerrado para o canal ${liveStreamStore.channel.name}`,
        4
      );
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

// Funções auxiliares
function updateChannel() {
  if (configStore.channels[i.value]) {
    const channelId = configStore.channels[i.value].id;
    liveStreamStore.updateChannel({
      ...configStore.channels[i.value],
      liveUrl: storage.getLiveUrl(channelId),
      isStreaming: false,
    });

    checkStreamStatus();
  }
}

function saveLiveUrlToLocalStorage() {
  if (liveStreamStore.channel.id) {
    storage.setLiveUrl(
      liveStreamStore.channel.id,
      liveStreamStore.channel.liveUrl
    );
  }
}

// Ciclo de vida
onMounted(() => {
  updateChannel();
});

onBeforeUnmount(() => {
  stopStatusCheck();
});

watch(i, updateChannel);
</script>