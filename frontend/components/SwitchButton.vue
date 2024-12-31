<template>
  <div class="flex justify-center items-center flex-col" :dark="colorMode.value === 'dark'">
    <div class="flex items-center space-x-1">
      <div
        ref="switchButton"
        class="relative w-16 h-8 rounded-full shadow-md cursor-pointer"
        :class="{ 'bg-[#4caf50]': channel.isOn, 'bg-[#f44336]': !channel.isOn, 'focus:outline focus:outline-white focus:outline-2 focus:outline-offset-2': channel.isKeyboardFocused }"
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
          :style="{ transform: channel.isOn ? 'translateX(36px)' : 'translateX(4px)' }"
          tabindex="0"
          @mouseenter="onMouseEnter"
          @mouseleave="onMouseLeave"
          @focus="onFocus"
          @blur="onBlur"
          @mousedown="onMouseDown"
          @mouseup="onMouseUp"
        ></div>
      </div>
      <span class="text-base">{{ channel.serviceStatus }}</span>
    </div>
    <div v-if="errorMessage" class="text-red-500 mt-2">{{ errorMessage }}</div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue';

// Defina o tipo estendido para Channel
interface ExtendedChannel extends Channel {
  isOn: boolean;
  serviceStatus: string;
  isKeyboardFocused: boolean;
  focusByTab: boolean;
  knob?: HTMLDivElement | null;
}

const colorMode = useColorMode();
const authStore = useAuth();
const configStore = useConfig();
const indexStore = useIndex();
const { i } = storeToRefs(configStore); // Índice do canal selecionado
const contentType = { 'content-type': 'application/json;charset=UTF-8' };

const channel = ref({} as ExtendedChannel); // Canal atual
const errorMessage = ref('');

// Inicializa os estados dos canais
onMounted(() => {
  // configStore.channels.forEach((channel: Channel) => {
  //   (channel as ExtendedChannel).isOn = false;
  //   (channel as ExtendedChannel).serviceStatus = 'Off';
  //   (channel as ExtendedChannel).isKeyboardFocused = false;
  //   (channel as ExtendedChannel).focusByTab = true;
  // });

  updateChannel(configStore.i);
  checkServiceStatus(configStore.channels[configStore.i] as ExtendedChannel);
});

// Observa mudanças no índice do canal
watch(() => configStore.i, (newIndex) => {
  updateChannel(newIndex);
  checkServiceStatus(configStore.channels[newIndex] as ExtendedChannel);
});

function updateChannel(index: number) {
  if (configStore.channels[index]) {
    channel.value = configStore.channels[index] as ExtendedChannel;
    //indexStore.msgAlert('info', `Verificando status do canal: ${channel.value.name}`, 2);
  } else {
    errorMessage.value = 'Canal inválido selecionado.';
  }
}

enum AlertType {
  Success = 'success',
  Warning = 'warning',
  Error = 'error',
  // Outros tipos de alerta, se necessário
}

function getAlertType(rawData: string): AlertType {
  const lowerRawData = rawData.toLowerCase(); // Para comparação case-insensitive

  if (lowerRawData.includes('iniciado')) {
    return AlertType.Success;
  } else if (lowerRawData.includes('interrompido')) {
    return AlertType.Warning;
  } else {
    // Define um tipo padrão ou lance um erro
    return AlertType.Error; // ou outro valor padrão
  }
}

// Handle mouse down to distinguish between keyboard and mouse focus
const onMouseDown = () => {
  channel.value.focusByTab = false; // Set flag to false on mouse down
  channel.value.isKeyboardFocused = false; // Do not apply keyboard-focus class
};

const handleBackgroundClick = () => {
  if (!channel.value.id) {
    errorMessage.value = 'Nenhum canal selecionado.';
    return;
  }

  channel.value.isOn = !channel.value.isOn;
  toggleService();
};

const onMouseEnter = () => {
  if (channel.value.knob) {
    channel.value.knob.style.boxShadow = '0 0 10px rgba(0,0,0,0.3)';
  }
};

const onMouseLeave = () => {
  if (channel.value.knob) {
    channel.value.knob.style.boxShadow = 'none';
  }
};

const onFocus = () => {
  if (channel.value.knob) {
    channel.value.knob.style.outline = '2px solid rgba(0,0,0,0.5)';
  }
};

const onBlur = () => {
  if (channel.value.knob) {
    channel.value.knob.style.outline = 'none';
  }
};

const onMouseUp = () => {
  if (channel.value.knob) {
    channel.value.knob.style.outline = 'none'; // Remove the outline when the mouse button is released
  }
};

const onSwitchFocus = () => {
  if (channel.value.focusByTab) { // Only apply the class if focused via keyboard
    channel.value.isKeyboardFocused = true;
  }
};

const onSwitchBlur = () => {
  channel.value.isKeyboardFocused = false; // Remove the class on blur
  channel.value.focusByTab = true; // Reset flag on blur
};

const onSwitchKeyDown = (event: { code: string; }) => {
  if (event.code === 'Space') {
    handleBackgroundClick();
  }
};

// Verifica o status do serviço para o canal atual
async function checkServiceStatus(channel: ExtendedChannel) {
  await fetch(`/api/ytbot/status/${channel.id}`, {
    method: 'GET',
    headers: { ...contentType, ...authStore.authHeader },
  })
    .then(async (response) => {
      const clonedResponse = response.clone();
      const rawData = await clonedResponse.text();
      const data = await response.json();

      if (!response.ok) {
        indexStore.msgAlert('error', `${rawData}`, 4);
      }
      if (response.ok) {
        if (data.status === 'active') {
          channel.isOn = true;
          channel.serviceStatus = 'On';
          errorMessage.value = ''; // Clear error message
          indexStore.msgAlert('success', `Bot de live ativo para o canal ${channel.name}`, 3);
        } else if (data.status === 'inactive') {
          channel.isOn = false;
          channel.serviceStatus = 'Off';
          errorMessage.value = ''; // Clear error message
          indexStore.msgAlert('warning', `Bot de live inativo para o canal ${channel.name}`, 3);
        } else {
          console.error('Unexpected status: ', `${rawData}`);
          errorMessage.value = `Unexpected status: ${rawData}`;
          channel.isOn = false; // Set isOn to false if an unexpected status is received
          indexStore.msgAlert('error', `Status inesperado: ${rawData}`, 4);
          console.error('SwitchButton resposta bruta do backend:', `${rawData}`);
          return;
        }
    }
    })
    .catch((error) => {
      console.error('Failed to check service status: ', error);
      channel.serviceStatus = 'Error';
      errorMessage.value = `Failed to check service status: ${error}`;
      channel.isOn = false; // Set isOn to false if an error occurs
      indexStore.msgAlert('error', `Erro ao verificar status do Bot de live para o canal ${channel.name}: ${error}`, 4);
    });
}

// Alterna o estado do serviço para o canal atual
async function toggleService() {
  if (!channel.value.id) {
    errorMessage.value = 'Nenhum canal selecionado.';
    return;
  }

  const action = channel.value.isOn ? 'start' : 'stop';

  await fetch(`/api/ytbot/control/${channel.value.id}`, {
    method: 'POST',
    headers: { ...contentType, ...authStore.authHeader },
    body: JSON.stringify({ action }),
  })
    .then(async (response) => {
      const clonedResponse = response.clone();
      const rawData = await clonedResponse.text();
      //const data = await response.json();

      if (!response.ok) {
        indexStore.msgAlert('error', `${rawData}`, 4);
      }

      if (response.ok) {
        channel.value.serviceStatus = channel.value.isOn ? 'On' : 'Off';
        const alertType = getAlertType(rawData);
        errorMessage.value = ''; // Clear error message
        indexStore.msgAlert(alertType, `${rawData}`, 4);
      } else {
        console.error(`Failed to ${action === 'start' ? 'start' : 'stop'} the service: `, `${rawData}`);
        errorMessage.value = `Failed to ${action === 'start' ? 'start' : 'stop'} the service: ${rawData}`;
        channel.value.isOn = false; // Set isOn to false if a failure occurs
        indexStore.msgAlert('error', `Falha ao ${action === 'start' ? 'Iniciar' : 'Parar'} o Bot de live para o canal ${channel.value.name}: ${rawData}`, 4);
        console.error('SwitchButton resposta bruta do backend:', `${rawData}`);
      }
    })
    .catch((error) => {
      console.error(`Error while ${channel.value.isOn ? 'stopping' : 'starting'} the service: `, error);
      channel.value.serviceStatus = 'Error';
      errorMessage.value = `Error while ${channel.value.isOn ? 'Stopping' : 'Starting'} the service: ${error}`;
      channel.value.isOn = false; // Set isOn to false if an error occurs
      indexStore.msgAlert('error', `Erro ao ${channel.value.isOn ? 'Parar' : 'Iniciar'} o Bot de live para o canal ${channel.value.name}: ${error}`, 4);
    });
}
</script>