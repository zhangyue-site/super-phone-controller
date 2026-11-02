# AMOLED explicit hold-to-record candidate

Candidate: 0.5.0-amoled; base 9a296f1, isolated audio worktree.
Source and host-test evidence only. No firmware build, real microphone test,
deployment, firmware publication or flash has been performed.

## Actual capture path

The board-local voice page owns a PRESS -> RELEASE lifecycle. PRESS reserves the
USB/HID/OTA interlock and relay audio owner; it fails if BLE/direct/HID/OTA is
already active. It then creates one recorder worker. No recorder task, codec or
PCM buffer is allocated at boot, and there is no wake word or automatic listening.

The implementation uses the official Waveshare BSP microphone API
bsp_audio_codec_microphone_init(), which creates an ES7210 input codec, followed
by esp_codec_dev_open()/set_in_gain()/read()/close(). It requests mono signed
16-bit 16 kHz PCM and reads 256-sample blocks. Source remains pinned to BSP 2.0.1
by idf_component.yml. The official maintained BSP header/source and Waveshare
reference example at the repository's existing vendor commit were inspected.
The exact resolved managed component and its transitive codec API still require
the formal GitHub ESP-IDF compile; host shims are not that compile.

The buffer is bounded to 320000 bytes in PSRAM (10 seconds). RELEASE submits only
a take with at least 12800 bytes and RMS >=80. Short/silent input is not uploaded.
Each blocking read is followed by generation/network/owner/OTA checks, so late
DMA data after STOP is discarded. A stalled codec read may delay closing the
physical ADC until the codec driver returns; actual fault latency must be
measured. It does not permit a late upload or re-arm. No recording is stored in
flash or logged; the full allocated PCM buffer is zeroed before free.

## Network and visible result

The existing configured HTTPS endpoint and private identity-header helper are
used. POST /voice carries raw PCM, fresh random X-Voice-Session and sequence 1.
There is no X-Voice-Dialogue: this slice performs recognition only, never creates
or confirms a phone/HID task. No audio playback is initialized.

The optional X-Voice-Result:text-v1 header requests current recognizedText plus
session/sequence. This is a minimal opt-in server extension; old clients keep the
same response. It returns only current recognition, 1..120 characters, rejects
control characters, and rechecks STOP generation/turn cancellation immediately
before sending. It does not return interaction/quota, cached text or task data.
Firmware accepts only a matching session/sequence with bounded nonempty text and
shows that text in a scrollable result area with "未执行手机任务".

TLS uses the certificate bundle and valid clock; redirects, chunked/oversized
responses, malformed/current-binding failures and NUL escapes fail closed.
Transfers are single attempt, finite socket timeout and 90-second absolute
budget. STOP cancels generation synchronously; after outstanding I/O returns the
worker sends one bounded /stop for the old session and never replays the upload.
Recognition after a failed upload is not shown as success.

The new server tests first failed for missing recognizedText/unbounded text, then
passed. They cover opt-in versus legacy, no task creation, current session/turn,
STOP racing ASR, oversized/control text. No live service has been changed.

## Muting, amplifier and ownership

Capture initializes no ES8311 output codec and never enables its DAC or unmutes
speaker output. BSP_POWER_AMP_IO (GPIO46) is explicitly driven low before opening
the input codec and after closing it; failure to establish PA-off rejects input
initialization. This does not implement playback, volume, or a pretend user mute
setting. Existing e-paper mute/power sequencing is untouched. Future playback
must introduce a separately reviewed owner, persisted mute/volume policy and
power/ramp/flush timing rather than enabling PA here.

Audio owner is serialized by the relay mux and USB input mutex. It excludes BLE,
direct owner and OTA reservation; manual HID arming also rejects while audio owns
the input interlock. Rejected BLE handles cannot cancel the audio/direct owner.
Wi-Fi loss, USB detach and board STOP revoke audio generation. Navigating away
or losing the held touch cancels the recording; ordinary RELEASE submits it.

## Evidence and remaining acceptance

Host tests use generated PCM, fake transport and real cJSON, never a real ASR API:

- tools/test_amoled_audio.py: explicit start, frame alignment, 0.4..10s, RMS/size,
  cancellation epoch and monotonic duration.
- tools/test_amoled_audio_recorder.py: production worker PRESS/RELEASE, silence,
  STOP during a read, network loss, max wall time, allocation/codec failure,
  owner cleanup, full PCM zeroization and no background capture.
- tools/test_amoled_audio_transport.py --cjson-dir <registry host deps>:
  production uploader with TLS/redirect/size/partial write/cancellation,
  no dialogue header, matching returned text, no retries, total deadline.
- tools/check_amoled_audio_syntax.py: whole worker host syntax only.
- Existing font coverage, direct owner/disconnect and OTA/input interlock checks.
- tests/test_remote_http.py: six synthetic HTTP tests including text-v1.

Actual ES7210 channel routing, gain/SNR, startup transients, read-fault latency,
PA voltage/pop-free state, touch-hold robustness, real ASR and displayed Chinese
text remain hardware-unverified. Common static UI glyph coverage is checked;
arbitrary recognized rare Unicode may need a later font expansion.
The existing >=32 KiB internal-heap boot health threshold remains unchanged.
No physical memory value is fabricated. Formal builds remain GitHub Actions.

Official references:
- https://github.com/waveshareteam/Waveshare-ESP32-components/tree/master/bsp/esp32_s3_touch_amoled_2_16
- https://github.com/waveshareteam/ESP32-S3-Touch-AMOLED-2.16
- https://components.espressif.com/components/waveshare/esp32_s3_touch_amoled_2_16/versions/2.0.1/versions


Review follow-up: RELEASE during a blocking codec read now discards and zeroes
that crossing block before any append/RMS accounting. Previously completed valid
PCM may still be submitted; releasing during the first block uploads nothing.
The production recorder mock explicitly releases inside read(), with regression
cases at the first block, just below 0.4 seconds, and after a qualified take.
