"""Tecla de atalho: leitura da combinação e loop de mensagens com API do Windows falsa
(python -m unittest testes.test_hotkey, dentro da pasta IA)."""
import os
import queue
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pet_logic as L  # noqa: E402
from pet_hotkey import MOD_NOREPEAT, AtalhoGlobal  # noqa: E402


class Parser(unittest.TestCase):
    def test_aceita_varias_formas_de_escrever(self):
        for texto, esperado, mods, vk in (
            ("F9", "f9", 0, 0x78), ("f9", "f9", 0, 0x78), ("F1", "f1", 0, 0x70), ("F24", "f24", 0, 0x87),
            ("ctrl+alt+espaço", "ctrl+alt+space", L.MOD_CONTROL | L.MOD_ALT, 0x20),
            ("Ctrl + Shift + A", "ctrl+shift+a", L.MOD_CONTROL | L.MOD_SHIFT, 0x41),
            ("shift+ctrl+a", "ctrl+shift+a", L.MOD_CONTROL | L.MOD_SHIFT, 0x41),  # ordem canônica
            ("pausa", "pause", 0, 0x13), ("Pause", "pause", 0, 0x13), ("scrolllock", "scrolllock", 0, 0x91),
            ("printscreen", "print", 0, 0x2C), ("win+z", "win+z", L.MOD_WIN, 0x5A),
            ("alt+0", "alt+0", L.MOD_ALT, 0x30), ("ctrl+pgup", "ctrl+pageup", L.MOD_CONTROL, 0x21),
            ("ctrl+alt+enter", "ctrl+alt+enter", L.MOD_CONTROL | L.MOD_ALT, 0x0D),
        ):
            a = L.parse_atalho(texto)
            self.assertEqual((a.texto, a.mods, a.vk), (esperado, mods, vk), texto)

    def test_rotulo_bonito(self):
        self.assertEqual(L.parse_atalho("ctrl+alt+espaco").rotulo, "Ctrl+Alt+Espaço")
        self.assertEqual(L.parse_atalho("f9").rotulo, "F9")
        self.assertEqual(L.parse_atalho("print").rotulo, "PrintScreen")

    def test_o_texto_salvo_le_de_volta_igual(self):
        for t in ("f9", "ctrl+alt+space", "ctrl+shift+a", "pause"):
            self.assertEqual(L.parse_atalho(L.parse_atalho(t).texto).texto, t)

    def test_recusa_teclas_que_roubariam_a_digitacao(self):
        for t in ("a", "5", "espaço", "enter", "tab", "backspace", "left", "home", "delete"):
            with self.assertRaises(ValueError, msg=t) as cm:
                L.parse_atalho(t)
            self.assertIn("sozinha", str(cm.exception))

    def test_recusa_entradas_invalidas_com_mensagem(self):
        for t, trecho in (("", "Nenhuma"), ("ctrl", "principal"), ("ctrl+alt", "principal"), ("ctrl+a+b", "uma tecla"),
                          ("ctrl+ç", "Não conheço"), ("f25", "Não conheço"), ("f0", "Não conheço"), (None, "Nenhuma")):
            with self.assertRaises(ValueError, msg=t) as cm:
                L.parse_atalho(t)
            self.assertIn(trecho, str(cm.exception), t)

    def test_tecla_do_qt_vira_atalho(self):
        F1, CTRL, SHIFT, ALT, META = 0x01000030, 0x01000021, 0x01000020, 0x01000023, 0x01000022
        c = L.combo_de_qt
        self.assertEqual(c(F1 + 8), "f9")
        self.assertEqual(c(0x41, ctrl=True, shift=True), "ctrl+shift+a")
        self.assertEqual(c(0x20, alt=True), "alt+space")
        self.assertEqual(c(0x01000008), "pause")
        self.assertEqual(c(0x31, ctrl=True), "ctrl+1")
        self.assertEqual(c(F1 + 23), "f24")
        self.assertEqual(c(0x01000005, ctrl=True), "ctrl+enter")
        self.assertEqual(c(0x0, meta=True), None)
        for so_modificador in (CTRL, SHIFT, ALT, META):
            self.assertIsNone(c(so_modificador, ctrl=True), "só modificador: continua esperando")
        self.assertIsNone(c(0x21), "'!' (Shift+1) não é uma tecla suportada")
        self.assertIsNone(c(F1 + 24), "F25 não existe")

    def test_ida_e_volta_qt_para_parser(self):
        """Tudo que o 'aperte a tecla' produz o parser aceita (e vice-versa)."""
        for tecla, kw in ((0x01000030 + 8, {}), (0x41, {"ctrl": True}), (0x20, {"ctrl": True, "alt": True}),
                          (0x01000008, {}), (0x01000009, {}), (0x31, {"alt": True}), (0x01000016, {"ctrl": True})):
            L.parse_atalho(L.combo_de_qt(tecla, **kw))


class ApiFalsa:
    """Faz o papel do Windows: fila de mensagens da thread + registro de teclas."""
    ERRO_JA_REGISTRADA = 1409

    def __init__(self):
        self.fila = queue.Queue()
        self.log = []                # ("reg", mods, vk) / ("des",)
        self.recusar = set()         # vks que o "Windows" recusa (já em uso)
        self.tid = 4242
        self.thread_da_fila = None

    def preparar_fila(self):
        self.thread_da_fila = threading.get_ident()
        return self.tid

    def registrar(self, id_, mods, vk):
        assert threading.get_ident() == self.thread_da_fila, "RegisterHotKey tem de ser na thread do loop"
        if vk in self.recusar:
            return False, self.ERRO_JA_REGISTRADA
        self.log.append(("reg", mods, vk))
        return True, None

    def desregistrar(self, id_):
        assert threading.get_ident() == self.thread_da_fila
        self.log.append(("des",))

    def esperar_mensagem(self):
        return self.fila.get()

    def postar(self, tid, tipo):
        assert tid == self.tid
        self.fila.put((tipo, None))

    def apertar(self):
        self.fila.put(("hotkey", 1))


def esperar_ate(cond, s=2.0):
    fim = time.time() + s
    while time.time() < fim:
        if cond():
            return True
        time.sleep(0.01)
    return False


class Loop(unittest.TestCase):
    def setUp(self):
        self.api, self.vezes = ApiFalsa(), []
        self.h = AtalhoGlobal(lambda: self.vezes.append(time.time()), api=self.api)

    def tearDown(self):
        self.h.parar()

    def test_registra_e_dispara_o_callback(self):
        ok, msg = self.h.definir(L.parse_atalho("f9"))
        self.assertEqual((ok, msg), (True, None))
        self.assertEqual(self.api.log, [("reg", 0 | MOD_NOREPEAT, 0x78)], "sem repetição ao segurar a tecla")
        self.api.apertar()
        self.assertTrue(esperar_ate(lambda: len(self.vezes) == 1))
        self.api.apertar()
        self.assertTrue(esperar_ate(lambda: len(self.vezes) == 2))
        self.assertEqual(self.h.atual.texto, "f9")

    def test_registra_na_thread_do_loop(self):
        self.h.definir(L.parse_atalho("ctrl+alt+espaço"))  # a api falsa dá assert se for noutra thread
        self.assertEqual(self.api.log[0][1], (L.MOD_CONTROL | L.MOD_ALT) | MOD_NOREPEAT)

    def test_trocar_a_tecla_desregistra_a_antiga(self):
        self.h.definir(L.parse_atalho("f9"))
        ok, _ = self.h.definir(L.parse_atalho("ctrl+f10"))
        self.assertTrue(ok)
        self.assertEqual(self.api.log, [("reg", MOD_NOREPEAT, 0x78), ("des",),
                                        ("reg", L.MOD_CONTROL | MOD_NOREPEAT, 0x79)])
        self.assertEqual(self.h.atual.texto, "ctrl+f10")

    def test_tecla_em_uso_explica_e_mantem_a_antiga(self):
        self.h.definir(L.parse_atalho("f9"))
        self.api.recusar.add(0x7A)  # F11 já é de outro programa
        ok, msg = self.h.definir(L.parse_atalho("f11"))
        self.assertFalse(ok)
        self.assertIn("já está sendo usada", msg)
        self.assertIn("F11", msg)
        self.assertEqual(self.h.atual.texto, "f9", "continua valendo a anterior")
        self.assertEqual(self.api.log[-1], ("reg", MOD_NOREPEAT, 0x78), "e ela foi registrada de novo")
        self.api.apertar()
        self.assertTrue(esperar_ate(lambda: len(self.vezes) == 1))

    def test_remover_a_tecla(self):
        self.h.definir(L.parse_atalho("f9"))
        self.assertEqual(self.h.definir(None), (True, None))
        self.assertIsNone(self.h.atual)
        self.assertEqual(self.api.log[-1], ("des",))

    def test_remover_sem_ter_nada_nao_faz_nada(self):
        self.assertEqual(self.h.definir(None), (True, None))
        self.assertEqual(self.api.log, [])

    def test_erro_no_callback_nao_mata_o_atalho(self):
        def quebra():
            self.vezes.append(1)
            raise RuntimeError("falhou na interface")
        h = AtalhoGlobal(quebra, api=self.api)
        h.definir(L.parse_atalho("f9"))
        self.api.apertar()
        self.api.apertar()
        self.assertTrue(esperar_ate(lambda: len(self.vezes) == 2))
        h.parar()

    def test_parar_desregistra_e_encerra_a_thread(self):
        self.h.definir(L.parse_atalho("f9"))
        t = self.h._thread
        self.h.parar()
        self.assertFalse(t.is_alive())
        self.assertEqual(self.api.log[-1], ("des",))
        self.assertIsNone(self.h.atual)

    def test_parar_sem_nunca_ter_iniciado(self):
        AtalhoGlobal(lambda: None, api=self.api).parar()

    def test_fora_do_windows_avisa_em_vez_de_quebrar(self):
        if AtalhoGlobal.disponivel():
            self.skipTest("rodando no Windows")
        ok, msg = AtalhoGlobal(lambda: None).definir(L.parse_atalho("f9"))
        self.assertFalse(ok)
        self.assertIn("Windows", msg)
        self.assertEqual(AtalhoGlobal(lambda: None).definir(None)[0], False)

    def test_win32_real_e_importavel_so_no_windows(self):
        import pet_hotkey
        self.assertTrue(hasattr(pet_hotkey.Win32, "esperar_mensagem"))


if __name__ == "__main__":
    unittest.main()
