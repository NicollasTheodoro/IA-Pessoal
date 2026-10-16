import glob
import os
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pygame
import requests
from murf import Murf

api_key = os.getenv("MURF_API_KEY")


class Speak:
    """
    Fluxo em pipeline: cada frase vai para a fila assim que o LLM a termina.
    O Murf sintetiza até 2 frases ao mesmo tempo, e o áudio toca na ordem certa,
    então a frase 2 já está pronta quando a frase 1 acaba de tocar.
    """

    def __init__(self):
        self.output_dir = "falas"
        self.client = Murf(api_key=api_key)
        self.voice_id = "pt-BR-Isadora"
        self.multi_native_locale = "pt-BR"
        self.http = requests.Session()  # reaproveita a conexão: download mais rápido

        os.makedirs(self.output_dir, exist_ok=True)
        for velho in glob.glob(os.path.join(self.output_dir, "audio_*.wav")):
            try:
                os.remove(velho)  # limpa os áudios que sobraram de execuções anteriores
            except OSError:
                pass

        pygame.mixer.init()
        self._pool = ThreadPoolExecutor(max_workers=2)
        self._fila = queue.Queue()  # guarda as "promessas" de áudio, na ordem de fala
        threading.Thread(target=self._tocar_loop, daemon=True).start()

    # ---------- API pública ----------
    def enfileirar(self, texto, ao_iniciar=None):
        """Não bloqueia: manda sintetizar e toca quando chegar a vez.
        ao_iniciar: função chamada no instante em que ESTA frase começa a tocar (sincroniza a expressão)."""
        texto = (texto or "").strip()
        if texto:
            self._fila.put((self._pool.submit(self._sintetizar, texto), ao_iniciar))

    def esperar(self):
        """Bloqueia até tudo que foi enfileirado terminar de tocar."""
        self._fila.join()

    def ocupado(self):
        """True se ainda há frase sintetizando ou tocando (a Alice não puxa assunto por cima)."""
        return self._fila.unfinished_tasks > 0

    def falar(self, texto):
        """Compatível com o código antigo: enfileira e espera acabar."""
        self.enfileirar(texto)
        self.esperar()

    def parar(self):
        """Interrompe a fala atual e descarta o que estava na fila."""
        try:
            while True:
                fut, _ = self._fila.get_nowait()
                fut.cancel()
                self._fila.task_done()
        except queue.Empty:
            pass
        pygame.mixer.music.stop()

    # ---------- internos ----------
    def _sintetizar(self, texto):
        response = self.client.text_to_speech.generate(
            voice_id=self.voice_id,
            text=texto,
            multi_native_locale=self.multi_native_locale,
        )
        url = response.audio_file
        if not url:
            raise RuntimeError("a API do Murf não retornou arquivo de áudio")

        r = self.http.get(url, timeout=20)
        if "audio" not in r.headers.get("Content-Type", ""):
            raise RuntimeError("a resposta do Murf não é áudio: " + r.text[:200])

        caminho = os.path.join(self.output_dir, f"audio_{int(time.time() * 1000)}_{threading.get_ident()}.wav")
        with open(caminho, "wb") as f:
            f.write(r.content)
        return caminho

    def _tocar_loop(self):
        while True:
            fut, ao_iniciar = self._fila.get()
            caminho = None
            chamou = False

            def avisar():
                nonlocal chamou
                if ao_iniciar and not chamou:
                    chamou = True
                    try:
                        ao_iniciar()
                    except Exception as e:  # um erro na interface nunca pode calar a Alice
                        print("Erro no gancho da fala:", e)

            try:
                caminho = fut.result()
                pygame.mixer.music.load(caminho)
                pygame.mixer.music.play()
                avisar()
                while pygame.mixer.music.get_busy():
                    pygame.time.wait(50)
            except Exception as e:
                print("Erro na voz:", e)
                avisar()  # sem áudio, o texto e a expressão ainda aparecem no pet
            finally:
                try:
                    pygame.mixer.music.unload()
                    if caminho:
                        os.remove(caminho)  # não acumula mais arquivos na pasta falas/
                except Exception:
                    pass
                self._fila.task_done()