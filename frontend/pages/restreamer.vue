<template>
    <div 
      class="flex items-center justify-center h-screen w-screen bg-base-200 text-base-content overflow-hidden" 
      :class="{ 'dark': colorMode.value === 'dark' }"
    >
      <iframe 
        src="http://localhost:8080/ui/" 
        class="w-full h-full bg-neutral-800 rounded-none md:rounded-lg shadow-none md:shadow-md" 
        frameborder="0"
      ></iframe>
    </div>
  </template>
  
  <script setup lang="ts">
  const colorMode = useColorMode(); // Controle do tema (escuro ou claro).
  
  useHead({
    title: 'ffplayout | Restreamer'
  });
  </script>
  
  <style scoped>
  /* Nenhum estilo adicional é necessário devido ao uso completo das classes Tailwind/DaisyUI */
  </style>
  