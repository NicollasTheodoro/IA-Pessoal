import time

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

from audio.vad import Vad


class Listener:
    def __init__(self, modelo="small"):
        self.model = WhisperModel(modelo, compute_type="int8")
        self.samplerate = 16000
        self.blocksize = 1600              # blocos de 0,1 s
        self.threshold = 0.01              # volume mínimo para considerar "voz" (ajuste ao seu microfone)
        self.silence_time_limit = 1.0      # antes era 2.0: cada segundo aqui é um segundo a menos de espera
        self.max_segundos = 20             # trava de segurança
        self.pre_roll_blocos = 4           # guarda 0,4 s antes da voz para não cortar a 1ª sílaba
        self.voz_min = 0.25                # menos que isso acima do limiar é estalo/batida: descarta
        self.auto_limiar = True            # acompanha o ruído de fundo (nunca fica abaixo de `threshold`)
        # lidos de fora (ex.: o pet desenha o anel de volume): "parado", "esperando", "gravando", "transcrevendo"
        self.estado = "parado"
        self.nivel = 0.0
        self.limiar_atual = self.threshold

    def ouvir_som(self, espera_max=None, cancelar=None):
        """Grava até o silêncio e transcreve. Devolve None se ninguém falou em `espera_max` segundos
        ou se o evento `cancelar` for acionado (usado pela chamada na interface web)."""
        vad = Vad(limiar=self.threshold, silencio=self.silence_time_limit, max_seg=self.max_segundos,
                  pre_roll=self.pre_roll_blocos, dur_bloco=self.blocksize / self.samplerate,
                  voz_min=self.voz_min, auto=self.auto_limiar)
        gravando_antes = False
        self.estado, self.nivel = "esperando", 0.0

        print("🎧 Ouvindo...")
        t_ini = time.time()

        def callback(indata, frames, time_info, status):
            volume = float(np.sqrt(np.mean(indata ** 2)))
            vad.alimentar(volume, indata.copy(), time.time())

        try:
            with sd.InputStream(
                samplerate=self.samplerate,
                channels=1,
                dtype="float32",
                blocksize=self.blocksize,
                callback=callback,
            ):
                while True:
                    if cancelar is not None and cancelar.is_set():
                        return None
                    if not vad.gravando and espera_max and time.time() - t_ini > espera_max:
                        return None
                    self.nivel, self.limiar_atual = vad.nivel, vad.limiar()
                    self.estado = "gravando" if vad.gravando else "esperando"
                    if vad.gravando and not gravando_antes:
                        print("🗣 Voz detectada, começando gravação...")
                    gravando_antes = vad.gravando
                    if vad.acabou(time.time()):
                        print("🤫 Silêncio detectado. Parando gravação.")
                        break
                    time.sleep(0.05)

            buffer = vad.buffer
            if not buffer:
                return None

            self.estado = "transcrevendo"
            return self._transcrever(buffer)
        finally:
            self.estado, self.nivel = "parado", 0.0

    def _transcrever(self, buffer):
        audio = np.concatenate(buffer).flatten()
        pico = np.max(np.abs(audio))
        if pico > 0:
            audio = audio / pico

        print("🧠 Transcrevendo...")
        segments, _ = self.model.transcribe(
            audio,
            language="pt",
            beam_size=1,                         # mais rápido, qualidade quase igual para fala curta
            vad_filter=True,                     # ignora ruído e silêncio
            condition_on_previous_text=False,
            initial_prompt="Alice",              # ajuda o Whisper a acertar o nome dela
        )

        texto = " ".join(s.text.strip() for s in segments).strip()
        if texto:
            print("Você disse:", texto)
            return texto
        return None