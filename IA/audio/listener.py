import sounddevice as sd
import numpy as np
from faster_whisper import WhisperModel
import time
import webrtcvad


class Listener:
    def __init__(self, on_partial_callback=None):
        self.model = WhisperModel("small", compute_type="int8")
        self.samplerate = 16000
        self.threshold = 0.1  # ajuste isso
        self.silence_time_limit = 2.0  # segundos de silêncio pra parar
        self.vad = webrtcvad.Vad(2)
        self.frame_duration = 30
        self.frame_size = int(self.samplerate * self.frame_duration / 1000)
        self.audio_buffer = []
        self.last_voice_time = None
        self.gravando = False

        self.partial_audio = []
        self.partial_text = ""
        self.partial_window_seconds = 1.0
        self.partial_samples_limit = int(self.samplerate * self.partial_window_seconds)
        self.on_partial_callback = on_partial_callback

    def ouvir_som(self):
        self.audio_buffer = []
        self.partial_audio = []
        self.partial_text = ""
        self.gravando = False
        self.last_voice_time = None

        print("🎧 Ouvindo...")

        def callback(indata, frames, time_info, status):
            audio_int16 = (indata.flatten() * 32768).astype(np.int16)
            frame_bytes = audio_int16.tobytes()
            is_speech = self.vad.is_speech(frame_bytes, self.samplerate)

            if is_speech:
                if not self.gravando:
                    print("🗣 Voz detectada, começando gravação...")
                    self.gravando = True

                self.audio_buffer.append(indata.copy())
                self.partial_audio.append(indata.copy())
                self.last_voice_time = time.time()

            elif self.gravando:
                # ainda grava enquanto não ultrapassar tempo de silêncio
                self.audio_buffer.append(indata.copy())

        with sd.InputStream(
            samplerate=self.samplerate,
            channels=1,
            dtype="float32",
            blocksize=self.frame_size,
            callback=callback
        ):
            while True:
                if self.gravando:
                    if self.partial_audio:
                        current_sample = sum(len(chunk) for chunk in self.partial_audio)

                        if current_sample >= self.partial_samples_limit:
                            audio_np = np.concatenate(self.audio_buffer).flatten()
                            
                            segments, _ = self.model.transcribe(
                                audio_np,
                                language="pt",
                                vad_filter=False
                            )

                            texto_parcial = ""
                            for segment in segments:
                                texto_parcial += segment.text + " "

                            texto_parcial = texto_parcial.strip()

                            if texto_parcial:
                                print("Parcial : ", texto_parcial)
                                self.partial_text = texto_parcial

                                if self.on_partial_callback:
                                    self.on_partial_callback(texto_parcial)
                            self.partial_audio = []

                        if self.last_voice_time:
                            tempo_silencio = time.time() - self.last_voice_time
                            if tempo_silencio > self.silence_time_limit:
                                print("🤫 Silêncio detectado. Parando gravação.")
                                break

                    time.sleep(0.1)

            if not self.audio_buffer:
                return None

            audio_np = np.concatenate(self.audio_buffer).flatten()

            if np.max(np.abs(audio_np)) > 0:
                audio_np = audio_np / np.max(np.abs(audio_np))

            print("🧠 Transcrevendo...")

            segments, _ = self.model.transcribe(audio_np, language="pt")

            texto_final = ""
            for segment in segments:
                texto_final += segment.text + " "

            texto_final = texto_final.strip()

            if texto_final:
                print("Você disse:", texto_final)
                return texto_final

            return None