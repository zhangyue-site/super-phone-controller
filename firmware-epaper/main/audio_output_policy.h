#pragma once
namespace controller {
constexpr unsigned audio_dma_descriptors=4;
constexpr unsigned audio_dma_frames=128;
constexpr unsigned audio_warmup_frames=1600; // 100 ms at 16 kHz.
// Push real audio beyond both the queued DMA ring and the active descriptor.
constexpr unsigned audio_tail_frames=(audio_dma_descriptors+2)*audio_dma_frames;
}
