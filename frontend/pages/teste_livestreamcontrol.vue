<template>
    <div v-if="channel" class="w-full max-w-[800px]">
      <h2 class="pt-3 text-3xl">{{ channel.name }} ({{ channel.id }})</h2>
  
      <!-- Botões de controle do stream -->
      <div class="flex gap-4 my-5">
        <button class="btn btn-success" @click="startStream()">
          Iniciar Stream
        </button>
        <button class="btn btn-error" @click="stopStream()">
          Parar Stream
        </button>
      </div>
  
      <!-- Resto do template -->
      ...
    </div>
  </template>
  
  <script setup lang="ts">
  import { ref, onMounted, watch } from 'vue'
  import { useAuth } from '~/stores/auth'
  import { useConfig } from '~/stores/config'
  import { useIndex } from '~/stores/index'
  import { storeToRefs } from 'pinia'
  
  const authStore = useAuth()
  const configStore = useConfig()
  const indexStore = useIndex()
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
  
  async function startStream() {
    if (!channel.value.id) {
      indexStore.msgAlert('error', 'Canal não encontrado', 3)
      return
    }
  
    try {
      // Aqui enviamos action: 'start' e url com o valor de channel.preview_url
      const response = await $fetch(`/livestream/control/${channel.value.id}`, {
        method: 'POST',
        headers: { ...authStore.authHeader, 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'start', url: channel.value.preview_url })
      })
  
      console.log('Stream iniciado:', response)
      indexStore.msgAlert('success', 'Stream iniciado com sucesso', 2)
    } catch (error) {
      console.error('Erro ao iniciar o stream:', error)
      indexStore.msgAlert('error', 'Erro ao iniciar o stream', 3)
    }
  }
  
  async function stopStream() {
    if (!channel.value.id) {
      indexStore.msgAlert('error', 'Canal não encontrado', 3)
      return
    }
  
    try {
      // Aqui enviamos action: 'stop' e url como null (opcional)
      const response = await $fetch(`/livestream/control/${channel.value.id}`, {
        method: 'POST',
        headers: { ...authStore.authHeader, 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'stop', url: null })
      })
  
      console.log('Stream parado:', response)
      indexStore.msgAlert('success', 'Stream parado com sucesso', 2)
    } catch (error) {
      console.error('Erro ao parar o stream:', error)
      indexStore.msgAlert('error', 'Erro ao parar o stream', 3)
    }
  }
  </script>
  