"""Detector de fala (Vad) e Listener com microfone/Whisper falsos (python -m unittest testes.test_voz, dentro da pasta IA)."""
import importlib.machinery
import os
import sys
import threading
import time
import types
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from audio.vad import Vad  # noqa: E402


# ----------------------------------------------------------------------------- Vad puro
def rodar(vad, volumes, passo=0.1, t0=0.0):
    """Alimenta o Vad com um volume por bloco; devolve (motivo, instante)."""
    t = t0
    for v in volumes:
        t += passo
        vad.alimentar(v, ("b", v), t)
        m = vad.acabou(t)
        if m:
            return m, t
    return None, t


class VadTeste(unittest.TestCase):
    def test_sala_silenciosa_mantem_o_limiar_de_sempre(self):
        v = Vad()
        for i in range(20):
            v.alimentar(0.002, 0, i * 0.1)
        self.assertEqual(v.limiar(), 0.01)

    def test_sala_barulhenta_sobe_o_limiar(self):
        v = Vad()
        for i in range(20):
            v.alimentar(0.02, 0, i * 0.1)
        self.assertAlmostEqual(v.limiar(), 0.05)

    def test_limiar_tem_teto(self):
        v = Vad()
        for i in range(20):
            v.alimentar(0.2, 0, i * 0.1)
        self.assertEqual(v.limiar(), 0.08)

    def test_ruido_de_fundo_nao_dispara_gravacao(self):
        v = Vad()
        m, _ = rodar(v, [0.02] * 30 + [0.04] * 10)  # zumbido constante, um pouco mais alto
        self.assertFalse(v.gravando)
        self.assertIsNone(m)

    def test_voz_acima_do_ruido_grava_e_termina_no_silencio(self):
        v = Vad()
        m, t = rodar(v, [0.02] * 20 + [0.15] * 10 + [0.02] * 20)
        self.assertEqual(m, "silencio")
        self.assertTrue(v.gravando)

    def test_limiar_congela_quando_a_voz_comeca(self):
        v = Vad()
        rodar(v, [0.002] * 10)
        v.alimentar(0.3, 0, 2.0)
        self.assertTrue(v.gravando)
        for i in range(20):
            v.alimentar(0.3, 0, 2.1 + i * 0.1)  # falando alto não "ensurdece" o detector
        self.assertEqual(v.limiar(), 0.01)

    def test_silencio_demora_o_tempo_configurado(self):
        v = Vad(silencio=1.0)
        m, t = rodar(v, [0.002] * 5 + [0.2] * 5 + [0.002] * 30)
        self.assertEqual(m, "silencio")
        self.assertAlmostEqual(t, 1.0 + 1.1, delta=0.15)

    def test_estalo_curto_e_descartado_e_continua_esperando(self):
        v = Vad()
        m, t = rodar(v, [0.002] * 5 + [0.3] * 1 + [0.002] * 20)  # 0,1 s de batida na mesa
        self.assertIsNone(m)
        self.assertFalse(v.gravando)
        self.assertEqual(v.buffer, [])
        m, _ = rodar(v, [0.2] * 6 + [0.002] * 20, t0=t)  # a fala de verdade vem depois
        self.assertEqual(m, "silencio")

    def test_pre_roll_guarda_o_inicio_da_fala(self):
        v = Vad(pre_roll=3)
        rodar(v, [0.002] * 10 + [0.2] * 5 + [0.002] * 20)
        self.assertEqual(sum(1 for b in v.buffer if b[1] == 0.002) >= 3, True)
        self.assertEqual(v.buffer[0], ("b", 0.002))

    def test_trava_de_seguranca_no_maximo(self):
        v = Vad(max_seg=2.0)
        m, t = rodar(v, [0.2] * 100)
        self.assertEqual(m, "maximo")
        self.assertAlmostEqual(t, 2.3, delta=0.15)  # começa em 0,3 s (depois do aquecimento) + 2 s

    def test_pausa_curta_entre_palavras_nao_encerra(self):
        v = Vad(silencio=1.0)
        m, _ = rodar(v, [0.2] * 5 + [0.002] * 6 + [0.2] * 5)  # pausa de 0,6 s
        self.assertIsNone(m)
        self.assertTrue(v.gravando)


# ----------------------------------------------------------------------------- Listener com falsos
class FluxoFalso:
    """Substitui sounddevice.InputStream: entrega blocos de amplitude escolhida, em tempo real acelerado."""
    roteiro = []       # [(amplitude, quantidade de blocos)]
    intervalo = 0.01

    def __init__(self, samplerate=16000, channels=1, dtype="float32", blocksize=1600, callback=None):
        self.callback, self.blocksize, self._parar = callback, blocksize, threading.Event()

    def __enter__(self):
        def alimentar():
            for amp, n in list(FluxoFalso.roteiro) + [(0.001, 10 ** 6)]:
                for _ in range(n):
                    if self._parar.is_set():
                        return
                    self.callback(np.full((self.blocksize, 1), amp, dtype="float32"), self.blocksize, None, None)
                    time.sleep(FluxoFalso.intervalo)
        self._t = threading.Thread(target=alimentar, daemon=True)
        self._t.start()
        return self

    def __exit__(self, *a):
        self._parar.set()
        self._t.join(1)


class WhisperFalso:
    texto = "olá alice"
    chamadas = []

    def __init__(self, *a, **k):
        pass

    def transcribe(self, audio, **kw):
        WhisperFalso.chamadas.append((len(audio), float(np.max(np.abs(audio)))))
        seg = types.SimpleNamespace(text=" " + WhisperFalso.texto + " ") if WhisperFalso.texto else None
        return ([seg] if seg else []), None


def modulo_falso(nome, **atributos):
    """Módulo de mentira com __spec__ válido (o server.py consulta importlib.util.find_spec)."""
    m = types.ModuleType(nome)
    m.__spec__ = importlib.machinery.ModuleSpec(nome, None)
    for k, v in atributos.items():
        setattr(m, k, v)
    return m


sys.modules["sounddevice"] = modulo_falso("sounddevice", InputStream=FluxoFalso)
sys.modules["faster_whisper"] = modulo_falso("faster_whisper", WhisperModel=WhisperFalso)
from audio.listener import Listener  # noqa: E402


class ListenerTeste(unittest.TestCase):
    def setUp(self):
        self.l = Listener()
        self.l.silence_time_limit = 0.15
        WhisperFalso.texto, WhisperFalso.chamadas = "olá alice", []

    def roteiro(self, *r):
        FluxoFalso.roteiro = list(r)

    def test_fala_e_silencio_devolve_o_texto(self):
        self.roteiro((0.002, 8), (0.2, 12))
        self.assertEqual(self.l.ouvir_som(espera_max=5), "olá alice")
        self.assertEqual(len(WhisperFalso.chamadas), 1)
        self.assertEqual(WhisperFalso.chamadas[0][1], 1.0, "o áudio vai normalizado para o Whisper")

    def test_estado_e_nivel_ficam_visiveis_para_o_pet(self):
        self.roteiro((0.002, 20), (0.2, 60))
        vistos, nivel_max = [], [0.0]
        resultado = []
        t = threading.Thread(target=lambda: resultado.append(self.l.ouvir_som(espera_max=5)))
        t.start()
        while t.is_alive():
            vistos.append(self.l.estado)
            nivel_max.append(self.l.nivel)
            time.sleep(0.005)
        t.join()
        self.assertIn("esperando", vistos)
        self.assertIn("gravando", vistos)
        self.assertGreater(max(nivel_max), 0.15)
        self.assertLess(vistos.index("esperando"), vistos.index("gravando"))
        self.assertEqual((self.l.estado, self.l.nivel), ("parado", 0.0))
        self.assertEqual(resultado, ["olá alice"])

    def test_ninguem_fala_volta_none_no_tempo_limite(self):
        self.roteiro()
        t0 = time.time()
        self.assertIsNone(self.l.ouvir_som(espera_max=0.3))
        self.assertLess(time.time() - t0, 1.5)
        self.assertEqual(WhisperFalso.chamadas, [], "sem voz nem chama o Whisper")
        self.assertEqual(self.l.estado, "parado")

    def test_cancelar_interrompe(self):
        self.roteiro((0.002, 10 ** 5))
        ev = threading.Event()
        threading.Timer(0.15, ev.set).start()
        t0 = time.time()
        self.assertIsNone(self.l.ouvir_som(espera_max=30, cancelar=ev))
        self.assertLess(time.time() - t0, 1.5)

    def test_estalo_nao_chega_ao_whisper(self):
        self.roteiro((0.002, 10), (0.4, 1), (0.002, 10 ** 5))
        self.assertIsNone(self.l.ouvir_som(espera_max=0.6))
        self.assertEqual(WhisperFalso.chamadas, [])

    def test_whisper_sem_texto_volta_none(self):
        WhisperFalso.texto = ""
        self.roteiro((0.002, 5), (0.2, 12))
        self.assertIsNone(self.l.ouvir_som(espera_max=5))
        self.assertEqual(len(WhisperFalso.chamadas), 1)

    def test_quarto_barulhento_nao_grava_o_ruido(self):
        self.l.auto_limiar = True
        self.roteiro((0.02, 30), (0.04, 20))
        self.assertIsNone(self.l.ouvir_som(espera_max=0.5))
        self.assertEqual(WhisperFalso.chamadas, [])

    def test_estado_parado_depois_de_excecao(self):
        WhisperFalso.texto = None

        class Quebra(WhisperFalso):
            def transcribe(self, *a, **k):
                raise RuntimeError("modelo falhou")
        self.l.model = Quebra()
        self.roteiro((0.002, 5), (0.2, 12))
        with self.assertRaises(RuntimeError):
            self.l.ouvir_som(espera_max=5)
        self.assertEqual(self.l.estado, "parado")


if __name__ == "__main__":
    unittest.main()
