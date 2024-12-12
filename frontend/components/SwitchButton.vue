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
          @keydown="onKeyDown"
          @mousedown="onMouseDown"
          @mouseup="onMouseUp"
        ></div>
      </div>
      <span class="text-base">{{ serviceStatus }}</span>
    </div>
    <div v-if="errorMessage" class="text-red-500 mt-2">{{ errorMessage }}</div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue';

const colorMode = useColorMode();

const isOn = ref(false);
const knob = ref(null);
const switchButton = ref(null);
const isKeyboardFocused = ref(false);
let focusByTab = true; // Flag to check if the focus was done via tab

const authStore = useAuth();
const indexStore = useIndex(); // Supondo que o indexStore seja importado dessa forma
const contentType = { 'content-type': 'application/json;charset=UTF-8' };

const serviceStatus = ref('');
const errorMessage = ref('');

// Handle mouse down to distinguish between keyboard and mouse focus
const onMouseDown = () => {
  focusByTab = false; // Set flag to false on mouse down
  isKeyboardFocused.value = false; // Do not apply keyboard-focus class
};

const handleBackgroundClick = () => {
  isOn.value = !isOn.value;
  toggleService();
};

const onMouseEnter = () => {
  knob.value.style.boxShadow = '0 0 10px rgba(0,0,0,0.3)';
};

const onMouseLeave = () => {
  knob.value.style.boxShadow = 'none';
};

const onFocus = () => {
  knob.value.style.outline = '2px solid rgba(0,0,0,0.5)';
};

const onBlur = () => {
  knob.value.style.outline = 'none';
};

const onMouseUp = () => {
  knob.value.style.outline = 'none'; // Remove the outline when the mouse button is released
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

const onSwitchKeyDown = (event) => {
  if (event.code === 'Space') {
    handleBackgroundClick();
  }
};

// Funções para verificar e alterar o estado do serviço
async function checkServiceStatus() {
  await fetch('/api/ytbot/status', {
    method: 'GET',
    headers: { ...contentType, ...authStore.authHeader },
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }
      const data = await response.json();

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
        indexStore.msgAlert('error', `Status inesperado: ${JSON.stringify(data)}`, 4);
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

async function toggleService() {
  const action = isOn.value ? 'start' : 'stop';
  await fetch('/api/ytbot/control', {
    method: 'POST',
    headers: { ...contentType, ...authStore.authHeader },
    body: JSON.stringify({ action }),
  })
    .then(async (response) => {
      const data = await response.json();

      if (response.ok) {
        serviceStatus.value = isOn.value ? 'On' : 'Off';
        errorMessage.value = ''; // Clear error message
        indexStore.msgAlert('success', `Bot de live ${action === 'start' ? 'iniciado' : 'parado'} com sucesso`, 4);
      } else {
        console.error(`Failed to ${action === 'start' ? 'start' : 'stop'} the service: `, data);
        errorMessage.value = `Failed to ${action === 'start' ? 'start' : 'stop'} the service: ${JSON.stringify(data)}`;
        isOn.value = false; // Set isOn to false if a failure occurs
        indexStore.msgAlert('error', `Falha ao ${action === 'start' ? 'iniciar' : 'parar'} o Bot de live: ${JSON.stringify(data)}`, 4);
      }
    })
    .catch((error) => {
      console.error(`Error while ${isOn.value ? 'stopping' : 'starting'} the service: `, error);
      serviceStatus.value = 'Error';
      errorMessage.value = `Error while ${isOn.value ? 'stopping' : 'starting'} the service: ${error.message}`;
      isOn.value = false; // Set isOn to false if an error occurs
      indexStore.msgAlert('error', `Erro ao ${isOn.value ? 'parar' : 'iniciar'} o Bot de live: ${error.message}`, 4);
    });
}

onMounted(() => {
  checkServiceStatus();
});
</script>

<style scoped>

</style>