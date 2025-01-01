<template>
  <div
    class="min-h-screen bg-gradient-to-b from-base-200 to-base-300 text-base-content px-4 py-6 md:py-8"
    :dark="colorMode.value === 'dark'"
  >
    <div class="max-w-4xl mx-auto space-y-6">
      <!-- Header Section -->
      <header
        class="bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm rounded-xl shadow-lg p-6 border border-gray-100 dark:border-gray-700"
      >
        <div class="flex items-center justify-between">
          <div class="flex items-center space-x-4">
            <div
              class="h-[1.5em] w-[1.5em] rounded-full transition-all duration-300 flex-shrink-0"
              :class="{
                'bg-emerald-500 shadow-lg shadow-emerald-500/50 animate-pulse':
                isStreaming,
                'bg-red-500 shadow-lg shadow-red-500/50': !isStreaming
              }"
              :aria-label="isStreaming ? 'Canal online' : 'Canal offline'"
              role="status"
            ></div>
            <div>
              <h1 class="text-2xl font-bold">
                {{ liveStreamStore.channel.name || 'Nenhum canal selecionado' }}
              </h1>
              <p class="text-sm text-gray-600 dark:text-gray-400">
                Status: {{ isStreaming ? 'Transmitindo' : 'Offline' }}
              </p>
            </div>
          </div>
        </div>
      </header>
      <!-- Main Control Panel -->
      <main class="grid gap-6 md:grid-cols-2">
        <!-- Auto Detection Section -->
        <section
          class="bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm rounded-xl shadow-lg p-6 border border-gray-100 dark:border-gray-700"
        >
          <h2 class="text-lg font-semibold mb-4">Detecção Automática</h2>
          <div class="space-y-4">
            <p class="text-sm text-gray-600 dark:text-gray-400">
              Ative para detectar automaticamente novas lives
            </p>
            <SwitchButton />
          </div>
        </section>

        <!-- Manual Control Section -->
        <section
          class="bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm rounded-xl shadow-lg p-6 border border-gray-100 dark:border-gray-700"
        >
          <h2 class="text-lg font-semibold mb-4">Controle Manual</h2>
          <div class="space-y-4">
            <p class="text-sm text-gray-600 dark:text-gray-400">
              Insira o link da live para transmissão manual
            </p>
            <LiveStreamControl />
          </div>
        </section>
      </main>

      <!-- Information Card -->
      <section
        class="bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm rounded-xl shadow-lg p-6 border border-gray-100 dark:border-gray-700"
      >
        <div class="flex items-start space-x-4">
          <div class="p-2 bg-blue-100 dark:bg-blue-900 rounded-lg">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              class="h-6 w-6 text-blue-600 dark:text-blue-300"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          </div>
          <div class="flex-1">
            <h2 class="text-lg font-semibold mb-2">Como usar</h2>
            <p class="text-gray-600 dark:text-gray-400 text-sm leading-relaxed">
              Para iniciar uma live manualmente:
            </p>
            <ol class="list-decimal ml-5 mt-2 space-y-1">
              <li>Desative a detecção automática</li>
              <li>Cole o link da live do Youtube no campo</li>
              <li>Clique em "Iniciar" para começar a transmissão</li>
            </ol>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, watch, ref } from 'vue'
import { storeToRefs } from 'pinia'

// Definindo a interface para o status da resposta
interface PlayoutStatus {
  ingest: boolean;
}

const colorMode = useColorMode();
const configStore = useConfig();
const authStore = useAuth();
const liveStreamStore = useLiveStreamStore();
//const playlistStore = usePlaylist();
const { i } = storeToRefs(configStore);
const errorCounter = ref(0)

const localIngestRuns = ref(false);

// Computed property para verificar se está transmitindo
const isStreaming = computed(() => {
    return liveStreamStore.channel.isStreaming || localIngestRuns.value;
});

const streamUrl = ref(`/data/event/${configStore.channels[i.value]?.id}?endpoint=playout&uuid=${authStore.uuid}`);


const { status, data, error, close } = useEventSource(streamUrl, [], {
  autoReconnect: {
    retries: -1,
    delay: 1000,
  },
});

watch(data, () => {
  if (data.value && data.value !== "connected") {
    try {
      const playoutStatus = JSON.parse(data.value) as PlayoutStatus;
      localIngestRuns.value = Boolean(playoutStatus.ingest);
    } catch (error) {
      localIngestRuns.value = false;
    }
  }
});

watch([status, error], async () => {
    if (status.value === 'OPEN') {
        errorCounter.value = 0
    } else {
        errorCounter.value += 1

        if (errorCounter.value > 11) {
            await authStore.obtainUuid();
            streamUrl.value = `/data/event/${configStore.channels[i.value]?.id}?endpoint=playout&uuid=${authStore.uuid}`;
            errorCounter.value = 0;
        }
    }
})

// Adicione este watch para atualizar a URL quando i mudar
watch(i, () => {
    streamUrl.value = `/data/event/${configStore.channels[i.value]?.id}?endpoint=playout&uuid=${authStore.uuid}`;
})

function updateChannel() {
  if (configStore.channels[i.value]) {
    liveStreamStore.updateChannel({
      ...configStore.channels[i.value]
    });
  }
}

onMounted(() => {
  updateChannel();
});

watch(i, () => {
  updateChannel();
});

onBeforeUnmount(() => {
  close();
});

useHead({
  title: 'ffplayout | Livebot',
  meta: [
    {
      name: 'description',
      content: 'Painel de controle para gerenciamento de transmissões ao vivo'
    }
  ]
});
</script>