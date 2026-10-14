"""Fumaça da janela do pet com um Qt falso (python -m unittest testes.test_pet_janela, dentro da pasta IA).
Executa __init__, tick, paintEvent, mouse, menu e conversa. Não substitui testar com PySide6 de verdade."""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fake_qt  # noqa: E402

fake_qt.instalar()
import pet  # noqa: E402
import pet_logic as L  # noqa: E402
from fake_qt import QPoint, QPainter  # noqa: E402


class ClienteFalso:
    base = "http://127.0.0.1:5000"

    def __init__(self):
        self.chamadas, self.roteiro, self.n = [], [], 0
        self.portao = None  # se definido, conversar() espera ele abrir (para observar o balão "pensando")

    def eventos(self, desde=None):
        self.n += 1
        if desde is None:
            return [], 5, {"nome": "feliz", "rotulo": "Animada"}
        novos, self.roteiro = self.roteiro, []
        return novos, 5 + len(novos), {}

    def toque(self): self.chamadas.append("toque")
    def definir(self, n, dur=10): self.chamadas.append(("definir", n))
    def ritmo(self, v): self.chamadas.append(("ritmo", v))
    def dormir(self): self.chamadas.append("dormir")
    def acordar(self): self.chamadas.append("acordar")

    def conversar(self, msg, falar=True, acoes=True):
        self.chamadas.append(("conversar", msg, acoes))
        if self.portao:
            self.portao.wait(3)
        yield "sentence", {"text": "oi"}
        yield "acao", {"acao": "x", "resultado": "Aberto o YouTube"}
        yield "fim", {}


def esperar(cond, s=2.0):
    fim = time.time() + s
    while time.time() < fim:
        if cond():
            return True
        time.sleep(0.02)
    return False


class Janela(unittest.TestCase):
    def setUp(self):
        self.cli = ClienteFalso()
        self.cfg = dict(L.PADRAO)
        self.w = pet.JanelaPet(self.cfg, self.cli)

    def tearDown(self):
        self.w._parar.set()

    def test_nasce_no_chao_no_canto_direito(self):
        self.assertEqual(self.w.y(), self.w._chao_y())
        self.assertGreater(self.w.x(), 1000)

    def test_sincroniza_o_estado_inicial_do_servidor(self):
        self.assertTrue(esperar(lambda: self.w.emo == "feliz"))

    def test_desenha_todas_as_emocoes_sem_erro(self):
        for nome in self.w.cat:
            self.w.set_emo(nome, reanima=True)
            self.w.balao.mostrar("Uma frase razoavelmente comprida para testar a quebra de linhas do balão.", 5, time.time())
            self.w.tick()
            self.w.paintEvent(None)
            self.assertIn(("drawPixmap",), [(c[0],) for c in QPainter.chamadas if c[0] == "drawPixmap"][:1])

    def test_fala_vira_expressao_e_balao(self):
        self.w.on_evento({"tipo": "fala", "texto": "Mas não some lá dentro, hein.", "emocao": "desconfiada", "dur": 2.5})
        self.w.tick()
        self.assertEqual(self.w.emo, "desconfiada")
        self.assertTrue(self.w.balao.visivel(time.time()))
        self.assertIn("some", self.w.balao.texto)

    def test_eventos_seguidos_respeitam_a_fila(self):
        self.w.on_evento({"tipo": "fala", "texto": "a", "emocao": "feliz", "dur": 3})
        self.w.on_evento({"tipo": "fala", "texto": "b", "emocao": "irritada", "dur": 3})
        self.w.tick()
        self.assertEqual(self.w.emo, "feliz")
        self.w.tick()
        self.assertEqual(self.w.emo, "feliz", "a segunda espera a vez")

    def test_aviso_aparece_na_hora_e_clique_so_dispensa(self):
        self.w.on_evento({"tipo": "aviso", "texto": "Lembrete: remédio"})
        self.assertEqual(self.w.emo, "ideia")
        self.assertEqual(self.w.balao.tipo, "aviso")
        self.w._cutucar()
        self.assertFalse(self.w.balao.visivel(time.time()))
        self.assertNotIn("toque", self.cli.chamadas)
        self.w._cutucar()
        self.assertTrue(esperar(lambda: "toque" in self.cli.chamadas))

    def test_arrastar_solta_e_cai(self):
        class Ev:
            def __init__(s, x, y, botao):
                s._p, s._b = QPoint(x, y), botao
            def globalPosition(s): return s._p
            def button(s): return s._b
        esq = pet.Qt.MouseButton.LeftButton
        x0, y0 = self.w.x(), self.w.y()
        self.w.mousePressEvent(Ev(600, 500, esq))
        self.w.mouseMoveEvent(Ev(650, 300, esq))
        self.assertTrue(self.w.arrastando)
        # a janela acompanha o cursor mantendo o ponto em que foi agarrada
        self.assertEqual((self.w.x(), self.w.y()), (x0 + 50, y0 - 200))
        self.w.mouseReleaseEvent(Ev(650, 300, esq))
        self.assertFalse(self.w.arrastando)
        self.assertTrue(self.w.fisica.caindo)
        for _ in range(400):
            self.w._mover(time.time(), 1 / 30)
            if not self.w.fisica.caindo:
                break
        self.assertEqual(self.w.y(), self.w._chao_y(), "pousou no chão")

    def test_clique_simples_cutuca_e_duplo_abre_a_caixa(self):
        class Ev:
            def __init__(s, botao): s._b = botao; s._p = QPoint(10, 10)
            def globalPosition(s): return s._p
            def button(s): return s._b
        esq = pet.Qt.MouseButton.LeftButton
        self.w.mousePressEvent(Ev(esq))
        self.w.mouseReleaseEvent(Ev(esq))
        self.assertTrue(self.w._clique.ativo, "espera para saber se é duplo clique")
        self.w.mouseDoubleClickEvent(Ev(esq))
        self.assertFalse(self.w._clique.ativo)
        self.assertTrue(self.w.caixa.isVisible())

    def test_passeio_move_a_janela(self):
        self.w.passeio.proximo = 0
        self.w.set_emo("feliz")
        self.w.balao.fechar()
        x0 = self.w.x()
        for _ in range(5):
            self.w._mover(time.time(), 0.03)
            if self.w.salto:
                break
        self.assertIsNotNone(self.w.salto)
        self.w.salto.t0 -= 10  # avança o tempo: salto terminado
        self.w._mover(time.time(), 0.03)
        self.assertIsNone(self.w.salto)
        self.assertNotEqual(self.w.x(), x0)

    def test_nao_passeia_dormindo_ou_com_a_caixa_aberta(self):
        self.w.passeio.proximo = 0
        self.w.set_emo("dormindo")
        self.w._mover(time.time(), 0.03)
        self.assertIsNone(self.w.salto)
        self.w.set_emo("feliz")
        self.w.caixa.show()
        self.w._mover(time.time(), 0.03)
        self.assertIsNone(self.w.salto)

    def test_conversar_envia_ao_servidor_e_mostra_resultado_da_acao(self):
        import threading
        self.cli.portao = threading.Event()
        self.w.enviar("abre o youtube")
        self.assertEqual(self.w.balao.tipo, "pensando")
        self.cli.portao.set()
        self.assertTrue(esperar(lambda: any(c[0] == "conversar" for c in self.cli.chamadas if isinstance(c, tuple))))
        self.assertTrue(esperar(lambda: "YouTube" in self.w.balao.texto))
        self.assertEqual([c for c in self.cli.chamadas if isinstance(c, tuple) and c[0] == "conversar"][0][2], True)

    def test_caixa_de_texto_envia_e_fecha(self):
        recebido = []
        self.w.caixa.enviado.connect(recebido.append)
        self.w.abrir_caixa()
        self.w.caixa.edit.setText("  oi alice  ")
        self.w.caixa._enviar()
        self.assertEqual(recebido, ["oi alice"])
        self.assertFalse(self.w.caixa.isVisible())

    def test_menu_monta_e_as_acoes_chamam_o_servidor(self):
        m = self.w._menu()
        rotulos = [getattr(i, "texto", "") for i in m.itens]
        for esperado in ("💬 Conversar…", "🎭 Expressões", "💤 Dormir", "❌ Sair"):
            self.assertIn(esperado, rotulos)
        expressoes = next(i for i in m.itens if getattr(i, "texto", "") == "🎭 Expressões")
        self.assertEqual(len(expressoes.itens), len(self.w.cat))
        expressoes.itens[2].cb(False)  # o Qt passa 'checked' como 1º argumento
        dormir = next(i for i in m.itens if getattr(i, "texto", "") == "💤 Dormir")
        dormir.cb(False)
        self.assertTrue(esperar(lambda: "dormir" in self.cli.chamadas))
        self.assertTrue(any(isinstance(c, tuple) and c[0] == "definir" for c in self.cli.chamadas))

    def test_menu_trocar_tamanho_e_alternar_opcoes(self):
        m = self.w._menu()
        tam = next(i for i in m.itens if getattr(i, "texto", "") == "📏 Tamanho")
        w0 = self.w.width()
        tam.itens[3].cb(False)  # Enorme
        self.assertGreater(self.w.width(), w0)
        self.assertEqual(self.w.y(), self.w._chao_y())
        passear = next(i for i in m.itens if getattr(i, "texto", "") == "🐾 Passear pela tela")
        passear.toggled.emit(False)
        self.assertFalse(self.w.cfg["passear"])

    def test_servidor_cai_e_volta(self):
        self.w.on_online(False)
        self.assertEqual(self.w.balao.tipo, "aviso")
        self.assertIn("conexão", self.w.balao.texto)
        self.w.on_online(True)
        self.assertFalse(self.w._offline_avisado)

    def test_encerrar_salva_posicao(self):
        self.w.encerrar()
        self.assertEqual(self.cfg["x"], self.w.x())

    def test_particulas_e_sombra_desenhadas(self):
        self.w.set_emo("apaixonada", reanima=True)
        for _ in range(20):
            self.w.particulas.proxima = 0
            self.w.tick()
        self.w.paintEvent(None)
        nomes = [c[0] for c in QPainter.chamadas]
        self.assertIn("drawEllipse", nomes)
        self.assertIn("drawText", nomes)


if __name__ == "__main__":
    unittest.main()
