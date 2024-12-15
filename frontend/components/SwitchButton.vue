<template>
  <div class="flex justify-center items-center flex-col" :dark="colorMode.value === 'dark'">
    <div class="flex items-center space-x-1">
      <div
        ref="switchButton"
        class="relative w-16 h-8 rounded-full shadow-md cursor-pointer"
        :class="{ 'bg-[#4caf50]': isOn, 'bg-[#f44336]': !isOn, 'focus:outline focus:outline-white focus:outline-2 focus:outline-offset-2': isKeyboardFocused }"
        tabindex="0"
        @click="handleBackgroundClick"
        @focus="onSwitchFocus"
        @blur="onSwitchBlur"
        @keydown="onSwitchKeyDown"
        @mousedown="onMouseDown"
      >
        <div
          ref="knob"
          class="absolute top-1 w-6 h-6 bg-white rounded-full shadow-md cursor-pointer transition-transform duration-300"
          :style="{ transform: isOn ? 'translateX(36px)' : 'translateX(4px)' }"
          tabindex="0"
          @mouseenter="onMouseEnter"
          @mouseleave="onMouseLeave"
          @focus="onFocus"
          @blur="onBlur"
          @mousedown="onMouseDown"
          @mouseup="onMouseUp"
        ></div>
      </div>
      <span class="text-base">{{ serviceStatus }}</span>
    </div>
    <div v-if="errorMessage" class="text-red-500 mt-2">{{ errorMessage }}</div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue';

const colorMode = useColorMode();

const isOn = ref(false);
const knob = ref<HTMLDivElement | null>(null);
const switchButton = ref(null);
const isKeyboardFocused = ref(false);
const serviceStatus = ref('');
const errorMessage = ref('');
const channel = ref({} as Channel); // Canal atual

let focusByTab = true;

const authStore = useAuth();
const configStore = useConfig();
const indexStore = useIndex();
const { i } = storeToRefs(configStore); // Índice do canal selecionado
const contentType = { 'content-type': 'application/json;charset=UTF-8' };

// Atualiza o canal atual quando o índice muda
watch(i, updateChannel);

onMounted(() => {
  updateChannel();
  checkServiceStatus();
});

function updateChannel() {
  if (configStore.channels[i.value]) {
    channel.value = configStore.channels[i.value];
  } else {
    errorMessage.value = 'Canal inválido selecionado.';
  }
}

// Handle mouse down to distinguish between keyboard and mouse focus
const onMouseDown = () => {
  focusByTab = false; // Set flag to false on mouse down
  isKeyboardFocused.value = false; // Do not apply keyboard-focus class
};

const handleBackgroundClick = () => {
  if (!channel.value.id) {
    errorMessage.value = 'Nenhum canal selecionado.';
    return;
  }

  isOn.value = !isOn.value;
  toggleService();
};

const onMouseEnter = () => {
  if (knob.value) {
    knob.value.style.boxShadow = '0 0 10px rgba(0,0,0,0.3)';
  }
};

const onMouseLeave = () => {
  if (knob.value) {
    knob.value.style.boxShadow = 'none';
  }
};

const onFocus = () => {
  if (knob.value) {
    knob.value.style.outline = '2px solid rgba(0,0,0,0.5)';
  }
};

const onBlur = () => {
  if (knob.value) {
    knob.value.style.outline = 'none';
  }
};

const onMouseUp = () => {
  if (knob.value) {
    knob.value.style.outline = 'none'; // Remove the outline when the mouse button is released
  }
};

const onSwitchFocus = () => {
  if (focusByTab) { // Only apply the class if focused via keyboard
    isKeyboardFocused.value = true;
  }
};

const onSwitchBlur = () => {
  isKeyboardFocused.value = false; // Remove the class on blur
  focusByTab = true; // Reset flag on blur
};

const onSwitchKeyDown = (event: { code: string; }) => {
  if (event.code === 'Space') {
    handleBackgroundClick();
  }
};

// Verifica o status do serviço para o canal atual
async function checkServiceStatus() {
  await fetch(`/api/ytbot/status/${channel.value.id}`, {
    method: 'GET',
    headers: { ...contentType, ...authStore.authHeader },
  })
    .then(async (response) => {
      const data = await response.json();
      const rawData = await response.text();

      // Adicione o log aqui para verificar o conteúdo de `data`
      console.error('SwitchButton resposta bruta do backend:', rawData);

      if (!response.ok) {
        indexStore.msgAlert('error', `HTTP Error: ${rawData}`, 4);
      }

      if (data.status === 'active') {
        isOn.value = true;
        serviceStatus.value = 'On';
        errorMessage.value = ''; // Clear error message
        indexStore.msgAlert('success', 'Bot de live ativo', 3);
      } else if (data.status === 'inactive') {
        isOn.value = false;
        serviceStatus.value = 'Off';
        errorMessage.value = ''; // Clear error message
        indexStore.msgAlert('warning', 'Bot de live inativo', 3);
      } else {
        console.error('Unexpected status: ', data);
        errorMessage.value = `Unexpected status: ${JSON.stringify(data)}`;
        isOn.value = false; // Set isOn to false if an unexpected status is received
        indexStore.msgAlert('error', `Status inesperado: ${data}`, 4);
        console.error('SwitchButton resposta bruta do backend:', rawData);
        return;
      }
    })
    .catch((error) => {
      console.error('Failed to check service status: ', error);
      serviceStatus.value = 'Error';
      errorMessage.value = `Failed to check service status: ${error.message}`;
      isOn.value = false; // Set isOn to false if an error occurs
      indexStore.msgAlert('error', `Erro ao verificar status do Bot de live: ${error.message}`, 4);
    });
}

// Alterna o estado do serviço para o canal atual
async function toggleService() {
  if (!channel.value.id) {
    errorMessage.value = 'Nenhum canal selecionado.';
    return;
  }

  const action = isOn.value ? 'start' : 'stop';

  await fetch(`/api/ytbot/control/${channel.value.id}`, {
    method: 'POST',
    headers: { ...contentType, ...authStore.authHeader },
    body: JSON.stringify({ action }),
  })
    .then(async (response) => {
      const data = await response.json();

      if (response.ok) {
        serviceStatus.value = isOn.value ? 'On' : 'Off';
        errorMessage.value = ''; // Clear error message
        indexStore.msgAlert('success', `Bot de live ${action === 'start' ? 'Iniciado' : 'Parado'} com sucesso`, 4);
      } else {
        console.error(`Failed to ${action === 'start' ? 'start' : 'stop'} the service: `, data);
        errorMessage.value = `Failed to ${action === 'start' ? 'start' : 'stop'} the service: ${JSON.stringify(data)}`;
        isOn.value = false; // Set isOn to false if a failure occurs
        indexStore.msgAlert('error', `Falha ao ${action === 'start' ? 'Iniciar' : 'Parar'} o Bot de live: ${JSON.stringify(data)}`, 4);
      }
    })
    .catch((error) => {
      console.error(`Error while ${isOn.value ? 'stopping' : 'starting'} the service: `, error);
      serviceStatus.value = 'Error';
      errorMessage.value = `Error while ${isOn.value ? 'Stopping' : 'Starting'} the service: ${error.message}`;
      isOn.value = false; // Set isOn to false if an error occurs
      indexStore.msgAlert('error', `Erro ao ${isOn.value ? 'Parar' : 'Iniciar'} o Bot de live: ${error.message}`, 4);
    });
}
</script>

<style scoped>
/* Estilos podem ser mantidos conforme a necessidade */
</style>
