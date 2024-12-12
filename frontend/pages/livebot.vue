<template>
  <div class="flex flex-col items-center min-h-screen p-4 bg-base-200 text-base-content" :dark="colorMode.value === 'dark'">
    <div class="w-full max-w-2xl mt-4 p-4 bg-base-300 rounded-lg shadow-md">
      <h1 class="text-[1.16rem] font-bold mb-4 text-center">
        Clique no botão abaixo para ativar ou desativar a detecção automática de lives
      </h1>
    </div>
    <div class="w-full max-w-2xl mt-4 p-4 bg-base-300 rounded-lg shadow-md">
      <SwitchButton />
    </div>
    <div class="w-full max-w-2xl mt-4 p-4 bg-base-300 rounded-lg shadow-md">
      <p class="text-base text-justify">
        Para iniciar uma live manualmente, desative a detecção automática de lives, insira o link de uma live do Youtube no campo abaixo e clique em start para iniciar a retransmissão de TV.
      </p>
    </div>
    <div class="w-full max-w-2xl mt-4 p-4 bg-base-300 rounded-lg shadow-md">
      <LiveStreamControl />
    </div>
  </div>
</template>

<script setup lang="ts">

const colorMode = useColorMode();

useHead({
    title: 'ffplayout | Livebot'
  })

</script>

<style scoped lang="scss">

</style>