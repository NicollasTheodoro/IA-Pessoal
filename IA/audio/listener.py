import sounddevice as sd
import numpy as np
from faster_whisper import WhisperModel
import time


class Listener:
    def __init__(self):
        self.model = WhisperModel("small", compute_type="int8")
        self.samplerate = 16000
        self.threshold = 0.01  # ajuste isso
        self.silence_time_limit = 2.0  # segundos de silêncio pra parar
        self.audio_buffer = []
        self.last_voice_time = None
        self.gravando = False

    def ouvir_som(self):
        self.audio_buffer = []
        self.gravando = False
        self.last_voice_time = None

        print("🎧 Ouvindo...")

        def callback(indata, frames, time_info, status):
            volume = np.sqrt(np.mean(indata**2))

            if volume > self.threshold:
                if not self.gravando:
                    print("🗣 Voz detectada, começando gravação...")
                    self.gravando = True

                self.audio_buffer.append(indata.copy())
                self.last_voice_time = time.time()

            elif self.gravando:
                # ainda grava enquanto não ultrapassar tempo de silêncio
                self.audio_buffer.append(indata.copy())

        with sd.InputStream(
            samplerate=self.samplerate,
            channels=1,
            dtype="float32",
            callback=callback
        ):
            while True:
                if self.gravando and self.last_voice_time:
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