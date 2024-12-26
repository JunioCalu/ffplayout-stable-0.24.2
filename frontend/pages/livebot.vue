<template>
  <div class="flex flex-col items-center min-h-screen p-4 bg-base-200 text-base-content" :dark="colorMode.value === 'dark'">
    <!-- Channel Title with Status Indicator -->
    <div class="w-full max-w-2xl p-4 bg-base-300 rounded-lg shadow-md">
      <div class="flex items-center justify-center">
        <div
          class="h-[1.5em] w-[1.5em] rounded-full mr-3 transition-all duration-300"
          :class="{
            'bg-emerald-500 shadow-lg shadow-emerald-500/50': channel.isStreaming,
            'bg-red-500 shadow-lg shadow-red-500/50': !channel.isStreaming
          }"
          :title="channel.isStreaming ? 'Online' : 'Offline'"
        ></div>
        <h1 class="text-2xl font-bold">
          Canal: {{ channel.name || 'Nenhum canal selecionado' }}
        </h1>
      </div>
    </div>

    <!-- Instructions -->
    <div class="w-full max-w-2xl mt-4 p-4 bg-base-300 rounded-lg shadow-md">
      <h2 class="text-lg font-bold mb-4 text-center">
        Clique no botão abaixo para ativar ou desativar a detecção automática de lives
      </h2>
    </div>

    <!-- SwitchButton -->
    <div class="w-full max-w-2xl mt-4 p-4 bg-base-300 rounded-lg shadow-md">
      <SwitchButton />
    </div>

    <!-- Description -->
    <div class="w-full max-w-2xl mt-4 p-4 bg-base-300 rounded-lg shadow-md">
      <p class="text-base text-justify">
        Para iniciar uma live manualmente, desative a detecção automática de lives, 
        insira o link de uma live do Youtube no campo abaixo e clique em start 
        para iniciar a retransmissão de TV.
      </p>
    </div>

    <!-- LiveStreamControl -->
    <div class="w-full max-w-2xl mt-4 p-4 bg-base-300 rounded-lg shadow-md">
      <LiveStreamControl class="w-full" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue';

interface ExtendedChannel extends Channel {
  isStreaming: boolean;
  serviceStatus: string;
  liveUrl: string;
}

const colorMode = useColorMode();
const configStore = useConfig();
const { i } = storeToRefs(configStore);
const channel = ref<ExtendedChannel>({} as ExtendedChannel);

// Update channel when component mounts and when index changes
function updateChannel() {
  if (configStore.channels[i.value]) {
    channel.value = {
      ...configStore.channels[i.value],
    } as ExtendedChannel;
  }
}

onMounted(updateChannel);
watch(i, updateChannel);

// Set page title
useHead({
  title: 'ffplayout | Livebot'
});
</script>