# Dialogue and local ADB implementation plan

> Use superpowers:executing-plans and test-driven development for each task.

**Goal:** Complete screen/voice roundtrip through106, with local verified ADB actions and cancellable spoken results.
**Architecture:** Asynchronous per-turn cloud job; board closes HTTP before executing local ADB; typed bounded commands and fresh UI verification; PCM playback after result.
**Tech Stack:** ESP-IDF C++, Python standard-library HTTP, existing cloud chat providers, edge-tts/ffmpeg on106.

- [x] Test then implement typed ADB commands and serial worker execution with ticket cancellation and readback.
- [x] Test then implement isolated per-turn job mailbox, UI node validation and conversational model runner.
- [x] Test then implement HTTP voice/job/result/audio endpoints and chunk upload compatibility, preserving deployed endpoints.
- [x] Integrate board polling, acknowledgement, PCM download/playback and screen states with cancellation.
- [x] Run host/Python/firmware checks, real106 model/TTS and mocked device end-to-end, inspect target hardware availability.
- [x] Independent review, fix findings, update documentation and existing PR, package tested firmware.

实机联调未通过：目标小米offline、目标板未连接，保留明确验收缺口，不将模拟结果算作硬件通过。
