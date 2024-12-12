<template>
  <div 
    class="flex flex-col h-screen w-screen bg-base-200 text-base-content overflow-hidden" 
    :class="{ 'dark': colorMode.value === 'dark' }"
  >
    <Menu class="bg-base-300 shadow-md z-10" />
    <div class="flex-grow bg-neutral-800 overflow-hidden">
      <iframe 
        src="http://localhost:8081/" 
        class="w-full h-full rounded-none md:rounded-lg shadow-none md:shadow-md" 
        frameborder="0"
      ></iframe>
    </div>
  </div>
</template>

<script setup lang="ts">
const colorMode = useColorMode(); // Controle do tema (escuro ou claro).

useHead({
  title: 'ffplayout | Download'
});
</script>

<style scoped>
/* Estilos adicionais não são necessários devido ao uso completo das classes Tailwind/DaisyUI */
</style>
