// stores/liveStream.ts
import { defineStore } from 'pinia';

interface Channel {
  id: number;
  name: string;
}

interface ExtendedChannel extends Channel {
  isStreaming: boolean;
  liveUrl: string;
}

export const useLiveStreamStore = defineStore('liveStream', {
  state: () => ({
    channel: {
      id: 0,
      name: '',
      isStreaming: false,
      liveUrl: '',
    } as ExtendedChannel
  }),
  
  actions: {
    updateChannel(channel: Partial<ExtendedChannel>) {
      this.channel = { ...this.channel, ...channel };
    },
    setStreamingStatus(status: boolean) {
      this.channel.isStreaming = status;
    }
  }
});