"""Fumaça da janela do pet com um Qt falso (python -m unittest testes.test_pet_janela, dentro da pasta IA).
Executa __init__, tick, paintEvent, mouse, menu e conversa. Não substitui testar com PySide6 de verdade."""
import math
import os
import sys
import threading
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
        # microfone
        self.est = {"ouvido": True, "pronto": True, "carregando": False, "ativo": False, "estado": "parado",
                    "nivel": 0.0, "limiar": 0.01}
        self.fila_ouvir = []        # respostas de ouvir(), em ordem; vazio = {"texto": None}
        self.portao_ouvir = None    # se definido, ouvir() espera ele abrir
        self.erro_ouvir = None
        self.espera_pedida = []

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
    def parar_fala(self): self.chamadas.append("parar_fala")
    def adiar(self, texto, minutos=10): self.chamadas.append(("adiar", texto, minutos))
    def ouvir_cancelar(self):
        self.chamadas.append("ouvir_cancelar")
        if self.portao_ouvir:
            self.portao_ouvir.set()
    def ouvir_estado(self): return dict(self.est)
    def ouvir_preparar(self): self.chamadas.append("ouvir_preparar")

    def ouvir(self, espera=10):
        self.chamadas.append("ouvir")
        self.espera_pedida.append(espera)
        if self.erro_ouvir:
            raise self.erro_ouvir
        if self.portao_ouvir:
            self.portao_ouvir.wait(3)
        return self.fila_ouvir.pop(0) if self.fila_ouvir else {"texto": None}

    def conversar(self, msg, falar=True, acoes=True):
        self.chamadas.append(("conversar", msg, acoes))
        self.ultimo_falar = falar
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
            def position(s): return QPoint(10, 10)
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
            def position(s): return s._p
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
        for esperado in ("🎤 Falar (microfone)", "💬 Digitar…", "🔇 Calar a Alice", "🎭 Expressões", "💤 Dormir", "❌ Sair"):
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


def centro(w, nome):
    cx, cy, _ = L.botoes(w.L)[nome]
    return int(cx), int(cy)


class EvBotao:
    """Evento de mouse sobre um ponto local da janela (para clicar nos botões desenhados)."""
    def __init__(self, x, y, botao=None):
        self._p = QPoint(int(x), int(y))
        self._b = botao or pet.Qt.MouseButton.LeftButton
    def globalPosition(self): return self._p
    def position(self): return self._p
    def button(self): return self._b


def clicar(w, x, y):
    w.mousePressEvent(EvBotao(x, y))
    w.mouseReleaseEvent(EvBotao(x, y))


class Voz(unittest.TestCase):
    def setUp(self):
        fake_qt.QTimer.pendentes = []
        self.cli = ClienteFalso()
        self.cfg = dict(L.PADRAO)
        self.w = pet.JanelaPet(self.cfg, self.cli)
        esperar(lambda: self.w.mic_disponivel is not None)  # o pet pergunta ao servidor se há microfone

    def tearDown(self):
        self.w._parar.set()
        for g in (self.cli.portao, self.cli.portao_ouvir):
            if g:
                g.set()

    def mic(self):
        clicar(self.w, *centro(self.w, "mic"))

    def chamou(self, nome):
        return any(c == nome or (isinstance(c, tuple) and c[0] == nome) for c in self.cli.chamadas)

    def test_pergunta_pelo_ouvido_e_ja_prepara_o_whisper(self):
        self.assertTrue(self.w.mic_disponivel)
        self.assertTrue(self.w.mic_pronto)
        self.cli2 = ClienteFalso()
        self.cli2.est.update(pronto=False)
        w2 = pet.JanelaPet(dict(L.PADRAO), self.cli2)
        self.assertTrue(esperar(lambda: "ouvir_preparar" in self.cli2.chamadas))
        w2._parar.set()

    def test_clique_ouve_entende_e_envia_sozinho(self):
        self.cli.fila_ouvir = [{"texto": "abre o youtube"}]
        self.cli.portao = threading.Event()  # segura a resposta para observar o "pensando"
        self.mic()
        self.assertTrue(esperar(lambda: self.w.voz_estado == "pensando"))
        self.assertEqual(self.cli.espera_pedida, [10], "espera 10 s você começar a falar")
        self.assertEqual(self.w.balao.tipo, "voce")
        self.assertIn("abre o youtube", self.w.balao.texto)
        self.assertTrue(esperar(lambda: self.chamou("conversar")))
        self.cli.portao.set()
        self.assertTrue(esperar(lambda: self.w.voz_estado == "parado"))
        self.assertTrue(self.cli.ultimo_falar, "responde em voz alta")

    def test_depois_de_responder_precisa_clicar_de_novo(self):
        self.cli.fila_ouvir = [{"texto": "oi"}]
        self.mic()
        self.assertTrue(esperar(lambda: self.w.voz_estado == "parado" and self.chamou("conversar")))
        fake_qt.QTimer.executar_pendentes()
        time.sleep(0.1)
        self.assertEqual(self.cli.chamadas.count("ouvir"), 1, "sem modo chamada, não reabre sozinha")
        self.assertEqual(self.w.voz_estado, "parado")

    def test_clicar_enquanto_ouve_cancela(self):
        self.cli.portao_ouvir = threading.Event()
        self.mic()
        self.assertTrue(esperar(lambda: self.w.voz_estado == "ouvindo"))
        self.assertIn("Pode falar", self.w.balao.texto)
        self.mic()
        self.assertEqual(self.w.voz_estado, "parado")
        self.assertTrue(esperar(lambda: "ouvir_cancelar" in self.cli.chamadas))
        self.assertFalse(self.w.balao.visivel(time.time()))
        time.sleep(0.1)
        self.assertFalse(self.chamou("conversar"), "o texto que chegar depois do cancelamento é descartado")

    def test_ninguem_falou_avisa_e_para(self):
        self.cli.fila_ouvir = [{"texto": None}]
        self.mic()
        self.assertTrue(esperar(lambda: self.w.balao.tipo == "aviso"))
        self.assertIn("Não ouvi nada", self.w.balao.texto)
        self.assertEqual(self.w.voz_estado, "parado")
        self.assertFalse(self.chamou("conversar"))

    def test_clicar_enquanto_ela_fala_interrompe_e_escuta(self):
        self.w.voz_estado = "falando"
        g0 = self.w._gen_chat
        self.cli.portao_ouvir = threading.Event()
        self.mic()
        self.assertTrue(esperar(lambda: "parar_fala" in self.cli.chamadas))
        self.assertGreater(self.w._gen_chat, g0)
        self.assertTrue(esperar(lambda: self.w.voz_estado == "ouvindo"))
        self.assertTrue(esperar(lambda: self.chamou("ouvir")))

    def test_resposta_interrompida_nao_dispara_fim(self):
        self.cli.fila_ouvir = [{"texto": "me conta uma história"}]
        self.cli.portao = threading.Event()
        self.mic()
        self.assertTrue(esperar(lambda: self.w.voz_estado == "pensando"))
        self.cli.portao_ouvir = threading.Event()
        self.mic()  # interrompe
        self.cli.portao.set()
        time.sleep(0.15)
        self.assertEqual(self.w.voz_estado, "ouvindo", "o fim da resposta antiga não derruba a nova escuta")

    def test_modo_chamada_reabre_e_encerra_no_silencio(self):
        self.cfg["chamada"] = True
        self.cli.fila_ouvir = [{"texto": "oi"}, {"texto": None}, {"texto": None}]
        self.mic()
        self.assertTrue(esperar(lambda: self.w.voz_estado == "parado" and self.chamou("conversar")))
        self.assertTrue(self.w.chamada.ativa)
        self.assertTrue(fake_qt.QTimer.pendentes, "agendou voltar a ouvir 0,4 s depois de falar")
        fake_qt.QTimer.executar_pendentes()
        self.assertTrue(esperar(lambda: self.w.balao.tipo == "aviso" and "Encerrei a chamada" in self.w.balao.texto))
        self.assertEqual(self.cli.chamadas.count("ouvir"), 3, "ouviu, tentou de novo uma vez e desistiu")
        self.assertFalse(self.w.chamada.ativa)
        self.assertEqual(self.w.voz_estado, "parado")

    def test_clicar_no_modo_chamada_desliga_a_chamada(self):
        self.cfg["chamada"] = True
        self.cli.portao_ouvir = threading.Event()
        self.mic()
        self.assertTrue(esperar(lambda: self.w.voz_estado == "ouvindo"))
        self.assertTrue(self.w.chamada.ativa)
        self.mic()
        self.assertFalse(self.w.chamada.ativa)

    def test_microfone_indisponivel_explica_o_que_instalar(self):
        cli = ClienteFalso()
        cli.est.update(ouvido=False, pronto=False)
        w = pet.JanelaPet(dict(L.PADRAO), cli)
        esperar(lambda: w.mic_disponivel is False)
        clicar(w, *centro(w, "mic"))
        self.assertIn("faster-whisper", w.balao.texto)
        self.assertFalse("ouvir" in cli.chamadas)
        w._parar.set()

    def test_erro_501_409_e_de_conexao(self):
        casos = ((501, "faster-whisper"), (409, "já está em uso"), (0, "xyz"))
        for status, trecho in casos:
            cli = ClienteFalso()
            cli.erro_ouvir = L.ErroServidor(status, "xyz")
            w = pet.JanelaPet(dict(L.PADRAO), cli)
            esperar(lambda: w.mic_disponivel is not None)
            clicar(w, *centro(w, "mic"))
            self.assertTrue(esperar(lambda: trecho in w.balao.texto), (status, w.balao.texto))
            self.assertEqual(w.voz_estado, "parado")
            self.assertEqual(w.mic_disponivel, False if status == 501 else True)
            w._parar.set()

    def test_anel_de_volume_acompanha_o_microfone(self):
        self.w.voz_estado = "ouvindo"
        self.w.on_nivel({"ativo": True, "pronto": True, "estado": "gravando", "nivel": 0.1, "limiar": 0.01})
        self.assertEqual(self.w.voz_estado, "gravando")
        self.assertGreater(self.w.nivel_alvo, 0.8)
        n0 = self.w.nivel
        for _ in range(5):
            self.w.tick()
        self.assertGreater(self.w.nivel, n0)
        self.w.on_nivel({"ativo": True, "pronto": True, "estado": "transcrevendo", "nivel": 0.0, "limiar": 0.01})
        self.assertEqual((self.w.voz_estado, self.w.nivel_alvo), ("transcrevendo", 0.0))
        self.assertIn("Entendendo", self.w.balao.texto)

    def test_nivel_atrasado_e_ignorado(self):
        self.w.voz_estado = "parado"
        self.w.on_nivel({"ativo": True, "pronto": True, "estado": "gravando", "nivel": 0.1, "limiar": 0.01})
        self.assertEqual(self.w.voz_estado, "parado")

    def test_desenha_o_botao_em_todos_os_estados(self):
        for est in L.ESTADOS_VOZ:
            self.w.voz_estado, self.w.nivel = est, 0.6
            self.w.chamada.ativa = est == "ouvindo"
            self.w._hover = "mic"
            self.w.paintEvent(None)
            nomes = [c[0] for c in QPainter.chamadas]
            self.assertIn("drawEllipse", nomes, est)
            self.assertIn("drawText", nomes, est)
        self.w.voz_estado = "preparando"
        self.w.paintEvent(None)
        self.assertIn("drawArc", [c[0] for c in QPainter.chamadas], "relógio girando enquanto espera")

    def test_passar_o_mouse_destaca_o_botao(self):
        cx, cy = centro(self.w, "mic")
        self.w.mouseMoveEvent(EvBotao(cx, cy))
        self.assertEqual(self.w._hover, "mic")
        self.w.mouseMoveEvent(EvBotao(10, 10))
        self.assertIsNone(self.w._hover)
        self.w.mouseMoveEvent(EvBotao(cx, cy))
        self.w.leaveEvent(None)
        self.assertIsNone(self.w._hover)

    def test_clicar_no_botao_nao_arrasta_nem_cutuca(self):
        x0, y0 = self.w.x(), self.w.y()
        cx, cy = centro(self.w, "texto")
        self.w.mousePressEvent(EvBotao(cx, cy))
        self.w.mouseMoveEvent(EvBotao(cx + 300, cy - 300))  # arrastou para longe com o botão apertado
        self.assertEqual((self.w.x(), self.w.y()), (x0, y0))
        self.assertFalse(self.w.arrastando)
        self.w.mouseReleaseEvent(EvBotao(10, 10))  # soltou fora do botão: cancela
        self.assertFalse(self.w.caixa.isVisible())
        self.assertFalse(self.w._clique.ativo)
        clicar(self.w, cx, cy)
        self.assertTrue(self.w.caixa.isVisible(), "o ⌨ abre a caixa de texto")

    def test_duplo_clique_no_botao_conta_uma_vez(self):
        cx, cy = centro(self.w, "mic")
        self.w.mouseDoubleClickEvent(EvBotao(cx, cy))
        self.assertFalse(self.w.caixa.isVisible())

    def test_digitar_enquanto_ouve_cancela_a_escuta(self):
        self.cli.portao_ouvir = threading.Event()
        self.mic()
        self.assertTrue(esperar(lambda: self.w.voz_estado == "ouvindo"))
        self.w.enviar("prefiro digitar")
        self.assertTrue(esperar(lambda: "ouvir_cancelar" in self.cli.chamadas))
        self.assertTrue(esperar(lambda: self.chamou("conversar")))

    def test_voz_desligada_manda_falar_false(self):
        self.cfg["voz"] = False
        self.cli.fila_ouvir = [{"texto": "oi"}]
        self.mic()
        self.assertTrue(esperar(lambda: self.chamou("conversar")))
        self.assertFalse(self.cli.ultimo_falar)

    def test_fechar_o_pet_nao_deixa_o_microfone_aberto(self):
        self.cli.portao_ouvir = threading.Event()
        self.mic()
        self.assertTrue(esperar(lambda: self.w.voz_estado == "ouvindo"))
        self.w.encerrar()
        self.assertIn("ouvir_cancelar", self.cli.chamadas)

    def test_menu_tem_as_opcoes_de_voz_e_calar_funciona(self):
        m = self.w._menu()
        rotulos = [getattr(i, "texto", "") for i in m.itens]
        for r in ("🔊 Alice fala em voz alta", "📞 Modo chamada (ouve de novo depois de responder)", "👀 Olhar para o mouse"):
            self.assertIn(r, rotulos)
        calar = next(i for i in m.itens if getattr(i, "texto", "") == "🔇 Calar a Alice")
        g0 = self.w._gen_chat
        calar.cb(False)
        self.assertTrue(esperar(lambda: "parar_fala" in self.cli.chamadas))
        self.assertGreater(self.w._gen_chat, g0)
        chamada = next(i for i in m.itens if getattr(i, "texto", "").startswith("📞"))
        self.w.chamada.ligar()
        chamada.toggled.emit(False)
        self.assertFalse(self.w.chamada.ativa)


class LembreteEOlhar(unittest.TestCase):
    def setUp(self):
        self.cli = ClienteFalso()
        self.cfg = dict(L.PADRAO)
        self.w = pet.JanelaPet(self.cfg, self.cli)

    def tearDown(self):
        self.w._parar.set()

    def mostra_lembrete(self):
        self.w.on_evento({"tipo": "aviso", "texto": "Lembrete: tomar o remédio"})
        self.w.paintEvent(None)  # o desenho calcula onde ficam os botões

    def test_lembrete_ganha_botoes_ok_e_mais_10_min(self):
        self.mostra_lembrete()
        self.assertEqual(set(self.w._rects_aviso), {"ok", "mais"})
        self.w.on_evento({"tipo": "aviso", "texto": "Perdi a conexão"})
        self.w.balao.tipo = "aviso"
        self.w.balao.texto = "✓ Aberto o YouTube"
        self.w.paintEvent(None)
        self.assertEqual(self.w._rects_aviso, {}, "só lembrete tem botões")

    def test_ok_dispensa(self):
        self.mostra_lembrete()
        x, y, w, h = self.w._rects_aviso["ok"]
        clicar(self.w, x + w / 2, y + h / 2)
        self.assertFalse(self.w.balao.visivel(time.time()))
        self.assertFalse(any(isinstance(c, tuple) and c[0] == "adiar" for c in self.cli.chamadas))

    def test_mais_10_min_adia_o_lembrete(self):
        self.mostra_lembrete()
        x, y, w, h = self.w._rects_aviso["mais"]
        clicar(self.w, x + w / 2, y + h / 2)
        self.assertTrue(esperar(lambda: ("adiar", "tomar o remédio", 10) in self.cli.chamadas))
        self.assertTrue(esperar(lambda: "10 minutos" in self.w.balao.texto))

    def test_passar_o_mouse_no_botao_do_lembrete_muda_o_cursor(self):
        self.mostra_lembrete()
        x, y, w, h = self.w._rects_aviso["ok"]
        self.w.mouseMoveEvent(EvBotao(x + 3, y + 3))
        self.assertEqual(self.w.cursor, pet.Qt.CursorShape.PointingHandCursor)
        self.w.mouseMoveEvent(EvBotao(5, 5))
        self.assertEqual(self.w.cursor, pet.Qt.CursorShape.ArrowCursor)

    def test_olha_para_o_lado_do_mouse(self):
        centro_x = self.w.x() + self.w.width() / 2
        fake_qt.QCursor.posicao = QPoint(int(centro_x + 600), 300)
        self.w._t_olhar = 0
        self.w.tick()
        self.assertTrue(self.w.virado)
        fake_qt.QCursor.posicao = QPoint(int(centro_x - 600), 300)
        self.w._t_olhar = 0
        self.w.tick()
        self.assertFalse(self.w.virado)

    def test_olhar_desligado_nao_vira(self):
        self.cfg["olhar"] = False
        fake_qt.QCursor.posicao = QPoint(self.w.x() + 2000, 300)
        self.w._t_olhar = 0
        self.w.tick()
        self.assertFalse(self.w.virado)

    def test_pulando_para_a_direita_ela_olha_para_a_direita(self):
        self.cfg["olhar"] = False
        self.w.passeio.proximo = 0
        self.w.set_emo("feliz")
        for _ in range(60):
            self.w._mover(time.time(), 0.03)
            if self.w.salto:
                break
        self.assertIsNotNone(self.w.salto)
        self.assertEqual(self.w.virado, self.w.salto.x1 > self.w.salto.x0)


if __name__ == "__main__":
    unittest.main()
