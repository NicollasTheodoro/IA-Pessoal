import time
from collections import deque

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel


class Listener:
    def __init__(self, modelo="small"):
        self.model = WhisperModel(modelo, compute_type="int8")
        self.samplerate = 16000
        self.blocksize = 1600              # blocos de 0,1 s
        self.threshold = 0.01              # volume mínimo para considerar "voz" (ajuste ao seu microfone)
        self.silence_time_limit = 1.0      # antes era 2.0: cada segundo aqui é um segundo a menos de espera
        self.max_segundos = 20             # trava de segurança
        self.pre_roll_blocos = 4           # guarda 0,4 s antes da voz para não cortar a 1ª sílaba

    def ouvir_som(self, espera_max=None, cancelar=None):
        """Grava até o silêncio e transcreve. Devolve None se ninguém falou em `espera_max` segundos
        ou se o evento `cancelar` for acionado (usado pela chamada na interface web)."""
        buffer = []
        pre = deque(maxlen=self.pre_roll_blocos)
        est = {"gravando": False, "ultima_voz": None, "inicio": None}

        print("🎧 Ouvindo...")
        t_ini = time.time()

        def callback(indata, frames, time_info, status):
            volume = np.sqrt(np.mean(indata ** 2))
            bloco = indata.copy()

            if volume > self.threshold:
                if not est["gravando"]:
                    print("🗣 Voz detectada, começando gravação...")
                    est["gravando"] = True
                    est["inicio"] = time.time()
                    buffer.extend(pre)  # inclui o trecho logo antes da voz
                    pre.clear()
                buffer.append(bloco)
                est["ultima_voz"] = time.time()
            elif est["gravando"]:
                buffer.append(bloco)
            else:
                pre.append(bloco)

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
                if not est["gravando"] and espera_max and time.time() - t_ini > espera_max:
                    return None
                if est["gravando"]:
                    agora = time.time()
                    if agora - est["ultima_voz"] > self.silence_time_limit:
                        print("🤫 Silêncio detectado. Parando gravação.")
                        break
                    if agora - est["inicio"] > self.max_segundos:
                        break
                time.sleep(0.05)

        if not buffer:
            return None

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