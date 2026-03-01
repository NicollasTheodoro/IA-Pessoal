import requests
import pygame
import sys
import os
import time
from murf import Murf

api_key = os.getenv("MURF_API_KEY")

class Speak:
    def __init__(self):
        self.output_dir = "falas"
        self.client = Murf(api_key=api_key)
        self.voice_id = "pt-BR-Isadora"
        self.multi_native_locale = "pt-BR"

        pygame.mixer.init()  # inicializa só uma vez

    def falar(self, output_assistant):

        response = self.client.text_to_speech.generate(
            voice_id=self.voice_id,
            text=output_assistant,
            multi_native_locale=self.multi_native_locale
        )

        audio_url = response.audio_file

        if not audio_url:
            print("❌ ERRO: API não retornou arquivo de áudio.")
            return

        r = requests.get(audio_url)

        if "audio" not in r.headers.get("Content-Type", ""):
            print("❌ ERRO: Resposta não é áudio válido.")
            print(r.text[:500])
            return

        # 🔥 PARA E DESCARREGA O ÁUDIO ANTERIOR
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()

        try:
            pygame.mixer.music.unload()
        except:
            pass

        # 🔥 Nome único evita conflito
        filename = f"audio_{int(time.time()*1000)}.wav"
        filepath = os.path.join(self.output_dir, filename)

        with open(filepath, "wb") as f:
            f.write(r.content)

        pygame.mixer.music.load(filepath)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)


# teste

# speak = Speak()
# speak.falar("Olá!")