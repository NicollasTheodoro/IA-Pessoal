"""
Desktop pet da Alice: ela vive na sua tela, sempre por cima, e usa as mesmas expressões da interface web.

    pip install PySide6          (uma vez)
    python IA/pet.py             (liga o servidor sozinho se ele ainda não estiver no ar)

O que dá para fazer:
    botão 🎤            conversa por voz: clique, fale, e ela percebe sozinha quando você para
                        (clique de novo para falar outra vez; durante a resposta, interrompe e escuta)
    tecla de atalho     (menu > ⌨ Tecla para falar) o mesmo que clicar no 🎤, de qualquer programa
    botão ⌨             abre a caixa de texto (também: duplo clique nela)
    menu > Botões       esconde o 🎤 e/ou o ⌨, ou só mostra quando o mouse chega perto
    clique              cutuca (1x simpática, várias seguidas ela se irrita)
    arrastar            muda de lugar; ao soltar no ar ela cai e quica
    botão direito       menu: conversar, expressões, ritmo, iniciativa, tamanho, passear, dormir...
    iniciativa          ela diz oi ao ligar, pergunta se você está ocupado quando some, comenta as expressões
    ícone na bandeja    mostrar/esconder, conversar, sair

Toda a lógica (conversa com o servidor, fila de expressões, movimentos, física) está em pet_logic.py;
este arquivo só desenha a janela e repassa os eventos.
"""
import argparse
import math
import os
import random
import sys
import threading
import time
import webbrowser

import pet_logic as L
from brain.emocoes import catalogo
from pet_hotkey import AtalhoGlobal
from brain.saida import forcar_utf8

forcar_utf8()

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    Signal = QtCore.Signal
except ImportError:
    try:
        from PyQt6 import QtCore, QtGui, QtWidgets
        Signal = QtCore.pyqtSignal
    except ImportError:
        sys.exit("Falta a biblioteca da janela. Instale com:  pip install PySide6")

Qt = QtCore.Qt
PASTA = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(PASTA)  # o server.py espera rodar a partir da raiz do projeto (memory.json, notas.txt)
FPS_MS = 33


class Ponte(QtCore.QObject):
    """Leva o que acontece nas threads de rede para a thread da janela."""
    evento = Signal(object)    # um evento do servidor (emocao, fala, aviso)
    sync = Signal(object)      # estado atual (primeira conexão ou servidor reiniciado)
    online = Signal(bool)
    texto = Signal(str, str)   # (mensagem, tipo) para o balão: resultados de ação, erros
    nivel = Signal(object)     # /ouvir/estado enquanto o microfone está aberto (anel de volume)
    voz_texto = Signal(str)    # o que o microfone entendeu ('' se ninguém falou)
    voz_erro = Signal(int, str)  # (status http, mensagem)
    voz = Signal(str)          # novo estado do botão (pensando/falando) vindo da conversa
    chat_fim = Signal(bool)    # a resposta terminou (True se a pergunta veio por voz)
    atalho = Signal()          # a tecla de atalho global foi apertada


class CaixaTexto(QtWidgets.QWidget):
    """Janelinha para conversar com a Alice sem abrir o navegador."""
    enviado = Signal(str)

    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        quadro = QtWidgets.QFrame(self)
        quadro.setObjectName("quadro")
        quadro.setStyleSheet("#quadro{background:#231a33;border:2px solid #ff5c93;border-radius:14px}"
                             "QLineEdit{background:transparent;border:none;color:#f6f0ff;font-size:14px;padding:8px 10px}")
        self.edit = QtWidgets.QLineEdit(quadro)
        self.edit.setPlaceholderText("Fale com a Alice…  (Enter envia, Esc fecha)")
        self.edit.returnPressed.connect(self._enviar)
        interno = QtWidgets.QVBoxLayout(quadro)
        interno.setContentsMargins(6, 4, 6, 4)
        interno.addWidget(self.edit)
        externo = QtWidgets.QVBoxLayout(self)
        externo.setContentsMargins(0, 0, 0, 0)
        externo.addWidget(quadro)
        self.setFixedSize(340, 50)

    def abrir(self, pos):
        self.edit.clear()
        self.move(pos)
        self.show()
        self.raise_()
        self.activateWindow()
        self.edit.setFocus()

    def _enviar(self):
        texto = self.edit.text().strip()
        self.hide()
        if texto:
            self.enviado.emit(texto)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(e)

    def changeEvent(self, e):
        if e.type() == QtCore.QEvent.Type.ActivationChange and self.isVisible() and not self.isActiveWindow():
            self.hide()  # clicou em outro lugar
        super().changeEvent(e)


class CapturaTecla(QtWidgets.QWidget):
    """'Aperte a tecla (ou combinação) que você quer usar para falar com a Alice.'"""
    capturada = Signal(str)   # texto do atalho, ex.: 'ctrl+alt+space'
    cancelada = Signal()

    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        quadro = QtWidgets.QFrame(self)
        quadro.setObjectName("quadro")
        quadro.setStyleSheet("#quadro{background:#231a33;border:2px solid #ffd95a;border-radius:14px}"
                             "QLabel{color:#f6f0ff;font-size:14px;padding:10px 14px}")
        self.rotulo = QtWidgets.QLabel("Aperte a tecla (ou combinação) para falar com a Alice.\nEsc cancela.", quadro)
        interno = QtWidgets.QVBoxLayout(quadro)
        interno.setContentsMargins(6, 4, 6, 4)
        interno.addWidget(self.rotulo)
        externo = QtWidgets.QVBoxLayout(self)
        externo.setContentsMargins(0, 0, 0, 0)
        externo.addWidget(quadro)
        self.setFixedSize(400, 84)
        self._concluida = False

    def abrir(self, pos):
        self._concluida = False
        self.move(pos)
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()

    def _fechar(self, combo=None):
        if self._concluida:
            return
        self._concluida = True
        self.hide()
        if combo:
            self.capturada.emit(combo)
        else:
            self.cancelada.emit()

    @staticmethod
    def _tem(modificadores, flag):
        return bool(modificadores & flag)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self._fechar()
            return
        m, K = e.modifiers(), Qt.KeyboardModifier
        combo = L.combo_de_qt(int(e.key()), ctrl=self._tem(m, K.ControlModifier), alt=self._tem(m, K.AltModifier),
                              shift=self._tem(m, K.ShiftModifier), meta=self._tem(m, K.MetaModifier))
        if combo:  # só modificador (Ctrl, Shift...) ou tecla sem suporte: continua esperando
            self._fechar(combo)

    def changeEvent(self, e):
        if e.type() == QtCore.QEvent.Type.ActivationChange and self.isVisible() and not self.isActiveWindow():
            self._fechar()  # clicou em outro lugar: cancela
        super().changeEvent(e)


class JanelaPet(QtWidgets.QWidget):
    def __init__(self, cfg, cliente, ligou_servidor=False, api_atalho=None):
        super().__init__(None)
        self.cfg, self.cliente, self.ligou_servidor = cfg, cliente, ligou_servidor
        self.cat = catalogo()
        self.rng = random.Random()
        agora = time.time()

        # --- janela transparente, sem borda, sempre por cima e fora da barra de tarefas
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if cfg["topo"]:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)  # para destacar os botões quando o mouse passa
        self.setWindowTitle("Alice")

        # --- estado
        self.emo = "neutra"
        self.sprite = self.cat["neutra"]["sprite"]
        self.sprite_ant, self.t_troca = None, 0.0
        self.mov = self.cat["neutra"]["mov"]
        self.t0, self.t_pop, self.virado = agora, 0.0, False
        self.fila, self.balao = L.FilaExpressao(), L.Balao()
        self.particulas, self.fisica = L.Particulas(self.rng), L.Fisica()
        self.passeio, self.salto = L.Passeio(self.rng, agora), None
        self.arrastando, self._press, self._offset, self._moveu = False, None, None, False
        self._press_alvo, self._hover, self._rects_aviso = None, None, {}
        # voz
        self.voz_estado, self.chamada = "parado", L.Chamada()
        self.mic_disponivel, self.mic_pronto = None, False   # None = ainda não sei
        self.nivel, self.nivel_alvo, self.t_voz = 0.0, 0.0, agora
        self._gen_escuta, self._gen_chat, self._t_olhar = 0, 0, 0.0
        self._perto, self._t_perto = False, 0.0   # mouse perto dela (para "botões só ao passar o mouse")
        self._rotulo_tecla = ""
        self._ultimo, self._offline_avisado = agora, False
        self._cache = {}
        self._abertura_feita = False   # o "oi" ao ligar acontece uma vez por execução do pet

        self._aplicar_layout()

        # --- partes
        self.ponte = Ponte()
        self.ponte.evento.connect(self.on_evento)
        self.ponte.sync.connect(self.on_sync)
        self.ponte.online.connect(self.on_online)
        self.ponte.texto.connect(lambda t, tipo: self.balao.mostrar(t, 6 + len(t) / 20, time.time(), tipo))
        self.ponte.nivel.connect(self.on_nivel)
        self.ponte.voz_texto.connect(self.on_voz_texto)
        self.ponte.voz_erro.connect(self.on_voz_erro)
        self.ponte.voz.connect(self.on_voz)
        self.ponte.chat_fim.connect(self.on_chat_fim)
        self.ponte.atalho.connect(self._atalho_apertado)
        self.atalho = AtalhoGlobal(lambda: self.ponte.atalho.emit(), api=api_atalho)
        self.captura = CapturaTecla()
        self.captura.capturada.connect(self._tecla_capturada)
        self.captura.cancelada.connect(self._captura_cancelada)
        self.caixa = CaixaTexto()
        self.caixa.enviado.connect(self.enviar)
        self._clique = QtCore.QTimer(self)
        self._clique.setSingleShot(True)
        self._clique.timeout.connect(self._cutucar)

        self._parar = threading.Event()
        threading.Thread(target=self._loop_eventos, daemon=True).start()

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(FPS_MS)

        self._posicao_inicial()
        self._bandeja()
        if self.cfg["tecla"]:
            self._aplicar_tecla(self.cfg["tecla"], avisar=False)

    # ------------------------------------------------------------------ layout e sprites
    def _aplicar_layout(self):
        self.L = L.layout(self.cfg["escala"])
        self.setFixedSize(self.L.janela_w, self.L.janela_h)
        self._cache.clear()

    def _pix(self, sprite, virado=False):
        chave = (sprite, virado, self.L.sprite_w)
        if chave not in self._cache:
            pm = QtGui.QPixmap(os.path.join(PASTA, "static", "pet", sprite + ".png"))
            if not pm.isNull():
                pm = pm.scaled(self.L.sprite_w, self.L.sprite_h, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
                if virado:
                    t = QtGui.QTransform()
                    t.scale(-1, 1)
                    pm = pm.transformed(t)
            self._cache[chave] = pm
        return self._cache[chave]

    def _tela(self):
        return QtGui.QGuiApplication.screenAt(self.frameGeometry().center()) or QtGui.QGuiApplication.primaryScreen()

    def _chao_y(self):
        """Y da janela quando os pés tocam o topo da barra de tarefas."""
        return self._tela().availableGeometry().bottom() + 1 - self.height() + self.L.margem

    def _posicao_inicial(self):
        geo = self._tela().availableGeometry()
        x = self.cfg["x"] if self.cfg["x"] is not None else geo.right() - self.width() - 40
        x = max(geo.left(), min(int(x), geo.right() + 1 - self.width()))
        self.move(x, self._chao_y())

    # ------------------------------------------------------------------ emoção e eventos
    def set_emo(self, nome, reanima=False):
        c = self.cat.get(nome)
        if not c or (nome == self.emo and not reanima):
            return
        agora = time.time()
        if c["sprite"] != self.sprite:
            self.sprite_ant, self.t_troca = self.sprite, agora
            self.sprite = c["sprite"]
        self.emo, self.mov, self.t_pop = nome, c["mov"], agora
        self.particulas.configurar(c["part"], agora)

    def on_evento(self, ev):
        agora = time.time()
        if ev["tipo"] == "aviso":
            self.set_emo("ideia", reanima=True)
            self.balao.mostrar("⏰ " + ev["texto"], 25, agora, "aviso")
        else:
            self.fila.push(ev)

    def on_sync(self, atual):
        self.fila.limpar()
        self.set_emo(atual["nome"])

    def on_online(self, ok):
        if ok:
            self._offline_avisado = False
            threading.Thread(target=self._ao_conectar, daemon=True).start()
            if self.mic_disponivel is None:
                threading.Thread(target=self._descobrir_ouvido, daemon=True).start()
        elif not self._offline_avisado:
            self._offline_avisado = True
            self.balao.mostrar("Perdi a conexão com a Alice (servidor). Vou tentando de novo…", 8, time.time(), "aviso")

    def _ao_conectar(self):
        """Conectou (ou o servidor reiniciou): passa o nível de iniciativa e, na 1ª vez, ela diz oi."""
        try:
            self.cliente.iniciativa(nivel=self.cfg["iniciativa"], voz=bool(self.cfg["voz"]))
            if not self._abertura_feita:
                self._abertura_feita = True
                if self.cfg["abertura"] and self.cfg["iniciativa"] > 0:
                    self.cliente.abertura()  # o servidor fala e já aquece o modelo
        except L.ErroServidor as e:
            if e.status == 404:
                self._abertura_feita = False
                self.ponte.texto.emit(self.AVISO_SERVIDOR_ANTIGO, "aviso")
        except Exception:
            pass

    AVISO_SERVIDOR_ANTIGO = ("O servidor da Alice é de uma versão antiga (sem iniciativa). Feche o Python/server.py "
                             "que está rodando (Gerenciador de Tarefas > python.exe) e abra o pet de novo.")

    def _descobrir_ouvido(self):
        """Pergunta se o servidor tem microfone e já carrega o Whisper (o 1º clique no 🎤 não espera)."""
        try:
            est = self.cliente.ouvir_estado()
            self.mic_disponivel, self.mic_pronto = bool(est.get("ouvido")), bool(est.get("pronto"))
            if self.mic_disponivel and not self.mic_pronto and self.cfg["preparar_ouvido"]:
                self.cliente.ouvir_preparar()
        except Exception:
            pass

    def _aplicar(self, ev):
        agora = time.time()
        if ev["tipo"] == "fala":
            self.set_emo(ev["emocao"])
            self.balao.mostrar(ev["texto"], float(ev.get("dur", 3)) + 1.0, agora)
        else:
            self.set_emo(ev["nome"], reanima=ev.get("fonte") in ("toque", "manual"))

    def _loop_eventos(self):
        """Thread: pergunta ao servidor o que mudou, ~3x por segundo."""
        desde, ligado = None, None
        while not self._parar.is_set():
            try:
                evs, ultimo, atual = self.cliente.eventos(desde)
                if desde is None or ultimo < desde:  # primeira vez ou servidor reiniciou
                    self.ponte.sync.emit(atual)
                else:
                    for e in evs:
                        self.ponte.evento.emit(e)
                desde = ultimo
                if ligado is not True:
                    ligado = True
                    self.ponte.online.emit(True)
            except Exception:
                if ligado is not False:
                    ligado = False
                    self.ponte.online.emit(False)
                desde = None  # ao voltar, sincroniza do zero
            self._parar.wait(0.35)

    def _async(self, fn, *args):
        """Chamadas ao servidor fora da thread da janela (não congela a Alice)."""
        def rodar():
            try:
                fn(*args)
            except L.ErroServidor as e:
                msg = self.AVISO_SERVIDOR_ANTIGO if e.status == 404 else f"Não consegui falar com o servidor: {e}"
                self.ponte.texto.emit(msg, "aviso")
            except Exception as e:
                self.ponte.texto.emit(f"Não consegui falar com o servidor: {e}", "aviso")
        threading.Thread(target=rodar, daemon=True).start()

    # ------------------------------------------------------------------ conversa
    def abrir_caixa(self):
        geo = self._tela().availableGeometry()
        x = self.x() + (self.width() - self.caixa.width()) // 2
        y = self.y() + self.height() - self.L.margem - self.L.sprite_h - self.caixa.height() - 6
        x = max(geo.left(), min(x, geo.right() + 1 - self.caixa.width()))
        self.caixa.abrir(QtCore.QPoint(x, max(geo.top(), y)))

    def enviar(self, texto, por_voz=False):
        agora = time.time()
        if not por_voz and self.voz_estado in ("preparando", "ouvindo", "gravando", "transcrevendo"):
            self.cancelar_escuta()  # digitou enquanto o microfone estava aberto
        self._gen_chat += 1
        gen = self._gen_chat
        if not por_voz:
            self.balao.mostrar("…", 90, agora, "pensando")  # some quando a primeira frase chegar
        if self.emo == "dormindo":
            self._async(self.cliente.acordar)

        def conversar():
            primeira = True
            try:
                for nome, d in self.cliente.conversar(texto, falar=self.cfg["voz"], acoes=self.cfg["acoes"]):
                    if gen != self._gen_chat:
                        break  # foi interrompida (ou veio outra pergunta): fecha a conexão
                    if nome == "sentence" and primeira:
                        primeira = False
                        self.ponte.voz.emit("falando")
                    elif nome == "acao" and d.get("resultado"):
                        self.ponte.texto.emit("✓ " + str(d["resultado"])[:140], "aviso")
                    elif nome == "erro":
                        self.ponte.texto.emit("⚠ " + str(d.get("error", "erro"))[:140], "aviso")
            except Exception as e:
                self.ponte.texto.emit(f"Não consegui falar com o servidor: {e}", "aviso")
            finally:
                if gen == self._gen_chat:
                    self.ponte.chat_fim.emit(por_voz)
        threading.Thread(target=conversar, daemon=True).start()

    def on_voz(self, estado):
        if self.voz_estado in ("pensando", "falando"):  # não atropela uma nova escuta
            self._set_voz(estado)

    def on_chat_fim(self, por_voz):
        if self.voz_estado in ("pensando", "falando"):
            self._set_voz("parado")
        if por_voz and self.chamada.continuar():  # modo chamada: ela terminou de falar, volta a ouvir
            QtCore.QTimer.singleShot(400, self._reabrir_chamada)

    def _reabrir_chamada(self):
        if self.voz_estado == "parado" and self.chamada.ativa:
            self.iniciar_escuta()

    # ------------------------------------------------------------------ tecla de atalho
    def _atalho_apertado(self):
        if not self.isVisible():
            self.show()  # escondida na bandeja: aparece para você ver que ela está ouvindo
        self.clique_mic()

    def capturar_tecla(self):
        geo = self._tela().availableGeometry()
        x = max(geo.left(), min(self.x() + (self.width() - self.captura.width()) // 2,
                                geo.right() + 1 - self.captura.width()))
        y = max(geo.top(), self.y() + self.height() - self.L.margem - self.L.sprite_h - self.captura.height() - 6)
        # enquanto captura, solta a tecla atual: senão apertá-la de novo acionaria o microfone em vez de ser lida
        threading.Thread(target=self.atalho.definir, args=(None,), daemon=True).start()
        self.captura.abrir(QtCore.QPoint(x, y))

    def _tecla_capturada(self, combo):
        self._aplicar_tecla(combo)

    def _captura_cancelada(self):
        self._aplicar_tecla(self.cfg["tecla"], avisar=False)  # volta a valer a de antes

    def _aplicar_tecla(self, texto, avisar=True):
        """Valida, registra no Windows e salva. Roda em thread (o registro espera a resposta do Windows)."""
        def go():
            try:
                novo = L.parse_atalho(texto) if texto else None
            except ValueError as e:
                self.ponte.texto.emit(str(e), "aviso")
                self._restaurar_tecla()
                return
            ok, msg = self.atalho.definir(novo)
            if not ok:
                self.ponte.texto.emit(msg, "aviso")
                self._restaurar_tecla()
                return
            self._set("tecla", novo.texto if novo else "")
            self._rotulo_tecla = novo.rotulo if novo else ""
            if avisar:
                self.ponte.texto.emit(f"Pronto! Aperte {novo.rotulo} para falar comigo." if novo
                                      else "Tirei a tecla de falar.", "aviso")
        threading.Thread(target=go, daemon=True).start()

    def _restaurar_tecla(self):
        """A tecla nova não serviu: religa a que estava salva (registrar de novo a mesma é inofensivo)."""
        try:
            antiga = L.parse_atalho(self.cfg["tecla"]) if self.cfg["tecla"] else None
            self.atalho.definir(antiga)
            # o rótulo mostra o que está REALMENTE registrado (a salva pode estar em uso por outro programa)
            self._rotulo_tecla = self.atalho.atual.rotulo if self.atalho.atual else ""
        except Exception:
            pass

    # ------------------------------------------------------------------ voz (microfone do PC)
    _DICA_VOZ = {"preparando": "⏳ Preparando o ouvido…", "ouvindo": "🎧 Pode falar…",
                 "gravando": "🎧 Te ouvindo…", "transcrevendo": "🧠 Entendendo…"}

    def _set_voz(self, estado):
        if estado == self.voz_estado:
            return
        self.voz_estado, self.t_voz = estado, time.time()
        if estado == "parado":
            self.nivel_alvo = 0.0
        if estado in self._DICA_VOZ:
            self.balao.mostrar(self._DICA_VOZ[estado], 90, time.time(), "ouvindo")
        elif self.balao.tipo == "ouvindo":
            self.balao.fechar()

    def clique_mic(self):
        if self.mic_disponivel is False:
            self.balao.mostrar("Para falar comigo: pip install faster-whisper sounddevice e reinicie o servidor.",
                               8, time.time(), "aviso")
            return
        acao = L.acao_clique_mic(self.voz_estado)
        if acao == "cancelar":
            self.chamada.desligar()
            self.cancelar_escuta()
            return
        if acao == "interromper":
            self._gen_chat += 1  # solta a resposta que estava chegando
            self._async(self.cliente.parar_fala)
        if self.cfg["chamada"]:
            self.chamada.ligar()
        self.iniciar_escuta()

    def iniciar_escuta(self):
        self._gen_escuta += 1
        gen = self._gen_escuta
        self._set_voz("ouvindo" if self.mic_pronto else "preparando")
        threading.Thread(target=self._escutar, args=(gen,), daemon=True).start()
        threading.Thread(target=self._acompanhar_nivel, args=(gen,), daemon=True).start()

    def cancelar_escuta(self):
        self._gen_escuta += 1  # a resposta do servidor (se vier) é descartada
        self._set_voz("parado")
        self.balao.fechar()
        self._async(self.cliente.ouvir_cancelar)

    def _escutar(self, gen):
        """Thread: abre o microfone no servidor e espera. Ele mesmo percebe quando você parou de falar."""
        try:
            r = self.cliente.ouvir(espera=self.cfg["espera"])
        except L.ErroServidor as e:
            if gen == self._gen_escuta:
                self.ponte.voz_erro.emit(e.status, str(e))
            return
        except Exception as e:
            if gen == self._gen_escuta:
                self.ponte.voz_erro.emit(0, f"Não consegui falar com o servidor: {e}")
            return
        if gen != self._gen_escuta:
            return  # cancelado enquanto ouvia
        self._gen_escuta += 1  # encerra o acompanhamento do volume
        self.ponte.voz_texto.emit((r.get("texto") or "").strip())

    def _acompanhar_nivel(self, gen):
        while gen == self._gen_escuta and not self._parar.is_set():
            try:
                self.ponte.nivel.emit(self.cliente.ouvir_estado())
            except Exception:
                pass
            self._parar.wait(0.12)

    def on_nivel(self, est):
        if self.voz_estado not in ("preparando", "ouvindo", "gravando", "transcrevendo"):
            return  # chegou atrasado: já cancelou ou terminou
        self.mic_pronto = bool(est.get("pronto"))
        st = L.estado_do_servidor(est)
        if st:
            self._set_voz(st)
        self.nivel_alvo = L.escala_nivel(est.get("nivel", 0.0), est.get("limiar", 0.01)) if st in ("ouvindo", "gravando") else 0.0

    def on_voz_texto(self, texto):
        agora = time.time()
        self.chamada.ouviu(texto)
        if not texto:
            if self.chamada.ativa and not self.chamada.encerrou_por_silencio():
                self.iniciar_escuta()  # em chamada, uma vez em silêncio ainda tenta de novo
                return
            msg = ("Encerrei a chamada porque não ouvi nada. Clique no 🎤 para falar."
                   if self.chamada.encerrou_por_silencio() else "Não ouvi nada. Clique no 🎤 e tente de novo.")
            self.chamada.desligar()
            self._set_voz("parado")
            self.balao.mostrar(msg, 5, agora, "aviso")
            return
        self.balao.mostrar("🎤 " + texto, 90, agora, "voce")  # mostra o que ela entendeu (some quando ela responder)
        self._set_voz("pensando")
        self.enviar(texto, por_voz=True)

    def on_voz_erro(self, status, msg):
        self.chamada.desligar()
        self._set_voz("parado")
        if status == 501:
            self.mic_disponivel = False
            msg = "Microfone indisponível no servidor: pip install faster-whisper sounddevice e reinicie."
        elif status == 409:
            msg = "O microfone já está em uso (talvez pela interface web)."
        self.balao.mostrar(msg, 7, time.time(), "aviso")

    # ------------------------------------------------------------------ vida (a cada quadro)
    def tick(self):
        agora = time.time()
        dt = min(0.1, agora - self._ultimo)
        self._ultimo = agora
        ev = self.fila.proximo(agora)
        if ev:
            self._aplicar(ev)
        self._mover(agora, dt)
        self.nivel = L.suavizar(self.nivel, self.nivel_alvo)
        if self.frameGeometry().contains(QtGui.QCursor.pos()):
            self._t_perto = agora
        self._perto = agora - self._t_perto < 0.7  # um pouquinho de folga para os botões não piscarem
        if self.cfg["olhar"] and not self.salto and not self.arrastando and agora - self._t_olhar > 0.25:
            self._t_olhar = agora
            self.virado = L.virar_para(QtGui.QCursor.pos().x(), self.x() + self.width() / 2, self.virado)
        self.particulas.atualizar(agora)
        if self.balao.tipo == "pensando" and not self.balao.visivel(agora):
            self.balao.texto = ""
        self.update()

    def _mover(self, agora, dt):
        if self.arrastando:
            return
        pos, chao = self.pos(), self._chao_y()
        if self.salto:
            x, y, fim = self.salto.pos(agora)
            self.move(int(x), int(y))
            if fim:
                self.salto, self.t_pop = None, agora
            return
        if self.fisica.caindo:
            y, tocou, _ = self.fisica.passo(pos.y(), chao, dt)
            self.move(pos.x(), int(y))
            if tocou:
                self.t_pop = agora
            return
        if pos.y() < chao - 2:  # ficou no ar (ex.: a barra de tarefas mudou)
            self.fisica.soltar()
            return
        if pos.y() > chao:
            self.move(pos.x(), chao)
        geo = self._tela().availableGeometry()
        livre = not self.caixa.isVisible() and not self.balao.visivel(agora) and self.emo != "dormindo"
        s = self.passeio.decidir(agora, self.emo, livre, pos.x(), geo.left(), geo.right() + 1, self.width(),
                                 chao, self.cfg["passear"])
        if s:
            self.salto, self.virado = s, s.x1 > s.x0  # sprite olha p/ esquerda: espelha ao ir para a direita

    # ------------------------------------------------------------------ desenho
    def paintEvent(self, _):
        agora = time.time()
        Lay = self.L
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        cx, pe = Lay.janela_w / 2, Lay.janela_h - Lay.margem  # centro e linha dos pés

        dx, dy, sx, sy, rot = L.transformar(self.mov, agora - self.t0)
        px, py = L.pop((agora - self.t_pop) / 0.32)
        altura = max(0.0, -dy)

        # sombra: encolhe quando ela está pulando
        k = 1 / (1 + 4 * altura)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor(0, 0, 0, int(70 * k)))
        p.drawEllipse(QtCore.QPointF(cx, pe + 1), Lay.sprite_w * 0.26 * k, Lay.sprite_h * 0.04 * k)

        # sprite (gira e estica a partir dos pés), com troca suave entre expressões
        p.save()
        p.translate(cx + dx * Lay.sprite_w, pe + dy * Lay.sprite_h)
        p.rotate(rot)
        p.scale(sx * px, sy * py)
        fade = min(1.0, (agora - self.t_troca) / 0.22)
        if self.sprite_ant and fade < 1.0:
            ant = self._pix(self.sprite_ant, self.virado)
            p.setOpacity(1 - fade)
            p.drawPixmap(int(-Lay.sprite_w / 2), -Lay.sprite_h, ant)
        p.setOpacity(fade if self.sprite_ant else 1.0)
        p.drawPixmap(int(-Lay.sprite_w / 2), -Lay.sprite_h, self._pix(self.sprite, self.virado))
        p.restore()
        p.setOpacity(1.0)

        # partículas
        topo = pe - Lay.sprite_h
        p.setFont(QtGui.QFont("Segoe UI Emoji", max(9, int(Lay.sprite_h * 0.06))))
        for ch, fx, fy, alpha, esc in self.particulas.desenho(agora):
            p.setOpacity(alpha)
            p.drawText(QtCore.QPointF(cx - Lay.sprite_w / 2 + fx * Lay.sprite_w, topo + fy * Lay.sprite_h), ch)
        p.setOpacity(1.0)

        self._desenhar_botoes(p, agora)
        self._desenhar_balao(p, agora, cx, topo)
        p.end()

    _COR_VOZ = {"parado": "#ff5c93", "preparando": "#8f86a8", "ouvindo": "#5fd0c0", "gravando": "#ff4d4d",
                "transcrevendo": "#ffd95a", "pensando": "#b79bff", "falando": "#ff5c93"}
    _ICONE_VOZ = {"preparando": "⏳", "transcrevendo": "⏳", "pensando": "💭", "falando": "⏹"}
    _ROTULO_MIC = {"parado": "Falar", "preparando": "Preparando… (clique p/ cancelar)",
                   "ouvindo": "Ouvindo… (clique p/ cancelar)", "gravando": "Te ouvindo…",
                   "transcrevendo": "Entendendo…", "pensando": "Interromper e falar", "falando": "Interromper e falar"}

    def _cor(self, hex_, alpha=255):
        c = QtGui.QColor(hex_)
        c.setAlpha(alpha)
        return c

    def _texto_centrado(self, p, texto, cx, cy, tamanho, fonte="Segoe UI Emoji"):
        f = QtGui.QFont(fonte, tamanho)
        p.setFont(f)
        fm = QtGui.QFontMetrics(f)
        p.drawText(QtCore.QPointF(cx - fm.horizontalAdvance(texto) / 2, cy + fm.ascent() / 2 - 2), texto)

    def _visiveis(self):
        return L.botoes_visiveis(self.cfg, self.voz_estado != "parado", self._perto)

    def _desenhar_botoes(self, p, agora):
        """🎤 e ⌨ junto aos pés dela. O 🎤 mostra o estado da conversa por voz e o volume da sua voz."""
        visiveis = self._visiveis()
        for nome, (cx, cy, r) in L.botoes(self.L).items():
            if not visiveis[nome]:
                continue
            mic = nome == "mic"
            estado = self.voz_estado if mic else "parado"
            indisponivel = mic and self.mic_disponivel is False
            ativo = estado != "parado"
            p.setOpacity(1.0 if (ativo or self._hover == nome) else (0.3 if indisponivel else 0.55))
            cor = self._COR_VOZ[estado] if mic else "#ff5c93"
            pulso = 0.5 + 0.5 * math.sin((agora - self.t_voz) * 6)

            # anel que reage à sua voz (gravando) ou "respira" (ouvindo)
            p.setBrush(Qt.BrushStyle.NoBrush)
            if estado == "gravando":
                rr = r * (1.15 + 0.75 * self.nivel)
                p.setPen(QtGui.QPen(self._cor(cor, 200), 3))
                p.drawEllipse(QtCore.QPointF(cx, cy), rr, rr)
            elif estado == "ouvindo":
                rr = r * (1.2 + 0.18 * pulso + 0.5 * self.nivel)
                p.setPen(QtGui.QPen(self._cor(cor, int(120 + 100 * pulso)), 3))
                p.drawEllipse(QtCore.QPointF(cx, cy), rr, rr)
            elif estado in ("preparando", "transcrevendo", "pensando"):
                rr = r * 1.25
                p.setPen(QtGui.QPen(self._cor(cor, 230), 3))
                p.drawArc(QtCore.QRectF(cx - rr, cy - rr, 2 * rr, 2 * rr), int(((agora * 300) % 360) * 16), 110 * 16)

            p.setPen(QtGui.QPen(self._cor(cor), 2))
            p.setBrush(self._cor("#231a33", 235))
            p.drawEllipse(QtCore.QPointF(cx, cy), r, r)
            p.setPen(self._cor("#ffffff"))
            icone = self._ICONE_VOZ.get(estado, "🎤") if mic else "⌨"
            self._texto_centrado(p, icone, cx, cy, max(9, int(r * 0.95)))
            if mic and self.chamada.ativa:  # selinho: modo chamada ligado
                self._texto_centrado(p, "📞", cx + r * 0.85, cy - r * 0.85, max(7, int(r * 0.6)))

            if self._hover == nome:  # rótulo do botão
                rotulo = "Microfone indisponível" if indisponivel else self._ROTULO_MIC[estado]
                if mic and estado == "parado" and self._rotulo_tecla and not indisponivel:
                    rotulo += f" ({self._rotulo_tecla})"
                if not mic:
                    rotulo = "Digitar"
                f = QtGui.QFont("Segoe UI", 9)
                p.setFont(f)
                fm = QtGui.QFontMetrics(f)
                larg = fm.horizontalAdvance(rotulo) + 16
                x0 = min(max(4.0, cx - larg / 2), self.L.janela_w - larg - 4)
                y0 = cy - r - fm.height() - 12
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(self._cor("#231a33", 240))
                p.drawRoundedRect(QtCore.QRectF(x0, y0, larg, fm.height() + 6), 8, 8)
                p.setPen(self._cor("#f6f0ff"))
                p.drawText(QtCore.QPointF(x0 + 8, y0 + 3 + fm.ascent()), rotulo)
        p.setOpacity(1.0)

    def _desenhar_balao(self, p, agora, cx, topo):
        self._rects_aviso = {}
        b = self.balao
        if not b.visivel(agora):
            return
        fonte = QtGui.QFont("Segoe UI", 10)
        p.setFont(fonte)
        fm = QtGui.QFontMetrics(fonte)
        linhas = L.quebrar(b.texto, 260, fm.horizontalAdvance, max_linhas=5)
        lembrete = b.tipo == "aviso" and L.eh_lembrete(b.texto)
        larg = max(max(fm.horizontalAdvance(x) for x in linhas) + 24, 170 if lembrete else 0)
        alt = len(linhas) * fm.lineSpacing() + 16 + (28 if lembrete else 0)
        x = cx - larg / 2
        y = max(4.0, topo + self.L.sprite_h * 0.04 - alt - 12)  # logo acima da cabeça
        p.setOpacity(b.alpha(agora))

        corpo = QtGui.QPainterPath()
        corpo.addRoundedRect(QtCore.QRectF(x, y, larg, alt), 12, 12)
        rabinho = QtGui.QPainterPath()
        rabinho.moveTo(cx - 8, y + alt - 1)
        rabinho.lineTo(cx, y + alt + 9)
        rabinho.lineTo(cx + 8, y + alt - 1)
        rabinho.closeSubpath()
        forma = corpo.united(rabinho)
        fundo = {"aviso": "#ffd95a", "pensando": "#efe6ff", "ouvindo": "#d9fff7", "voce": "#e8f0ff"}.get(b.tipo, "#fffafd")
        p.setBrush(QtGui.QColor(fundo))
        p.setPen(QtGui.QPen(QtGui.QColor("#5fd0c0" if b.tipo == "ouvindo" else "#ff5c93"), 2))
        p.drawPath(forma)
        p.setPen(QtGui.QColor("#2a0a17"))
        for i, linha in enumerate(linhas):
            p.drawText(QtCore.QPointF(x + 12, y + 8 + fm.ascent() + i * fm.lineSpacing()), linha)
        if lembrete:  # [ Ok ] [ +10 min ]
            self._rects_aviso = L.rects_aviso(x, y, larg, alt)
            p.setFont(QtGui.QFont("Segoe UI", 9))
            for nome, (bx, by, bw, bh) in self._rects_aviso.items():
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QtGui.QColor("#2a0a17"))
                p.drawRoundedRect(QtCore.QRectF(bx, by, bw, bh), 8, 8)
                p.setPen(QtGui.QColor("#ffd95a"))
                self._texto_centrado(p, "Ok" if nome == "ok" else "+10 min", bx + bw / 2, by + bh / 2, 9, "Segoe UI")
        p.setOpacity(1.0)

    # ------------------------------------------------------------------ mouse
    def _alvo_em(self, pos):
        """O que está sob o mouse: botão do lembrete, 🎤, ⌨ ou nada (então é o corpo dela)."""
        x, y = pos.x(), pos.y()
        for nome, rc in self._rects_aviso.items():
            if L.dentro_rect(rc, x, y):
                return "aviso_" + nome
        return L.botao_em(self.L, x, y, self._visiveis())

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            alvo = self._alvo_em(e.position().toPoint())
            if alvo:  # clicou num botão: não arrasta nem cutuca
                self._press_alvo, self._press = alvo, None
                return
            self._press = e.globalPosition().toPoint()
            self._offset = self._press - self.frameGeometry().topLeft()
            self._moveu = False
        elif e.button() == Qt.MouseButton.RightButton:
            self._menu().exec(QtGui.QCursor.pos())

    def mouseMoveEvent(self, e):
        if self._press is None:
            alvo = self._alvo_em(e.position().toPoint())  # só passando o mouse: destaca o botão
            self._hover = alvo if alvo in ("mic", "texto") else None
            self.setCursor(Qt.CursorShape.PointingHandCursor if alvo else Qt.CursorShape.ArrowCursor)
            return
        pos = e.globalPosition().toPoint()
        if not self._moveu and (pos - self._press).manhattanLength() > 6:
            self._moveu, self.arrastando = True, True
            self.salto = None
            self.fisica.parar()
        if self._moveu:
            self.move(pos - self._offset)

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if self._press_alvo:
            alvo, self._press_alvo = self._press_alvo, None
            if self._alvo_em(e.position().toPoint()) == alvo:  # soltou ainda em cima do mesmo botão
                self._acionar(alvo)
            return
        if self._press is None:
            return
        self._press = None
        if self._moveu:
            self.arrastando = False
            self.fisica.soltar()  # solta no ar: cai e quica
            self.cfg["x"] = self.x()
        else:
            self._clique.start(230)  # espera: se vier o 2º clique, é duplo clique (conversar)

    def mouseDoubleClickEvent(self, e):
        if self._alvo_em(e.position().toPoint()):
            return  # duplo clique rápido num botão conta uma vez só
        self._clique.stop()
        self.abrir_caixa()

    def leaveEvent(self, e):
        self._hover = None
        super().leaveEvent(e)

    def _acionar(self, alvo):
        if alvo == "mic":
            self.clique_mic()
        elif alvo == "texto":
            self.abrir_caixa()
        elif alvo == "aviso_ok":
            self.balao.fechar()
        elif alvo == "aviso_mais":
            self._adiar_lembrete()

    def _adiar_lembrete(self):
        texto = L.limpar_lembrete(self.balao.texto)
        self.balao.fechar()

        def adiar():
            try:
                self.cliente.adiar(texto, 10)
                self.ponte.texto.emit("Tá, te aviso de novo daqui a 10 minutos.", "aviso")
            except Exception as e:
                self.ponte.texto.emit(f"Não consegui adiar: {e}", "aviso")
        threading.Thread(target=adiar, daemon=True).start()

    def _cutucar(self):
        if self.balao.tipo == "aviso" and self.balao.visivel(time.time()):
            self.balao.fechar()  # clicar no aviso só dispensa
            return
        self._async(self.cliente.toque)

    # ------------------------------------------------------------------ menu e bandeja
    def _set(self, chave, valor):
        self.cfg[chave] = valor
        if chave == "chamada" and not valor:
            self.chamada.desligar()
        L.salvar_config(self.cfg)
        if chave == "voz":  # as falas de iniciativa também seguem a voz alta
            self._async(self.cliente.iniciativa, None, bool(valor))

    def _definir_iniciativa(self, nivel):
        self._set("iniciativa", nivel)
        self._async(self.cliente.iniciativa, nivel, None)

    def _set_gen_chat(self):
        self._gen_chat += 1  # solta a resposta que estava chegando

    def _menu(self):
        m = QtWidgets.QMenu(self)
        m.addAction("🎤 Falar (microfone)", self.clique_mic)
        m.addAction(f"⌨ Tecla para falar: {self._rotulo_tecla or 'nenhuma'}…", self.capturar_tecla)
        if self.cfg["tecla"]:
            m.addAction("🚫 Tirar a tecla de falar", lambda checked=False: self._aplicar_tecla(""))
        m.addAction("💬 Digitar…", self.abrir_caixa)
        m.addAction("🔇 Calar a Alice", lambda checked=False: (self._set_gen_chat(), self._async(self.cliente.parar_fala)))

        exp = m.addMenu("🎭 Expressões")
        for nome, c in self.cat.items():
            exp.addAction(c["rotulo"], lambda checked=False, n=nome: self._async(self.cliente.definir, n))

        ritmo = m.addMenu("⏱ Ritmo das expressões")
        for rotulo, v in (("Parada (só reage)", 0), ("Calma", 2), ("Normal", 1), ("Animada", 0.6)):
            ritmo.addAction(rotulo, lambda checked=False, v=v: self._async(self.cliente.ritmo, v))

        ini = m.addMenu("💬 Iniciativa da Alice (ela puxa assunto)")
        for rotulo, v in (("Desligada", 0), ("Calma", 1), ("Normal", 2), ("Faladeira", 3)):
            marca = "● " if self.cfg["iniciativa"] == v else "○ "
            ini.addAction(marca + rotulo, lambda checked=False, v=v: self._definir_iniciativa(v))
        a = ini.addAction("👋 Dizer oi ao ligar")
        a.setCheckable(True)
        a.setChecked(bool(self.cfg["abertura"]))
        a.toggled.connect(lambda v: self._set("abertura", bool(v)))
        ini.addSeparator()
        for rotulo, tipo, extra in (("▶ Testar: oi", "abertura", {}), ("▶ Testar: 'tá fazendo algo importante?'", "checkin", {}),
                                    ("▶ Testar: espreguiçando", "expressao", {"emocao": "espreguicando"}),
                                    ("▶ Testar: voltou", "volta", {})):
            ini.addAction(rotulo, lambda checked=False, t=tipo, x=extra: self._async(self.cliente.disparar, t, **x))

        m.addAction("💤 Dormir", lambda checked=False: self._async(self.cliente.dormir))
        m.addAction("☀️ Acordar", lambda checked=False: self._async(self.cliente.acordar))
        m.addSeparator()

        tam = m.addMenu("📏 Tamanho")
        for rotulo, v in (("Pequena", 0.5), ("Média", 0.7), ("Grande", 1.0), ("Enorme", 1.4)):
            tam.addAction(rotulo, lambda checked=False, v=v: self.mudar_escala(v))

        botoes = m.addMenu("🔘 Botões ao lado dela")
        for rotulo, chave in (("🎤 Microfone", "btn_mic"), ("⌨ Digitar", "btn_texto"),
                              ("Só aparecer quando o mouse estiver perto", "btn_hover")):
            a = botoes.addAction(rotulo)
            a.setCheckable(True)
            a.setChecked(bool(self.cfg[chave]))
            a.toggled.connect(lambda v, c=chave: self._set(c, bool(v)))

        for rotulo, chave in (("🔊 Alice fala em voz alta", "voz"),
                              ("📞 Modo chamada (ouve de novo depois de responder)", "chamada"),
                              ("👀 Olhar para o mouse", "olhar"),
                              ("🐾 Passear pela tela", "passear"),
                              ("⚙️ Executar ações do PC ao conversar", "acoes")):
            a = m.addAction(rotulo)
            a.setCheckable(True)
            a.setChecked(bool(self.cfg[chave]))
            a.toggled.connect(lambda v, c=chave: self._set(c, bool(v)))
        a = m.addAction("📌 Sempre por cima")
        a.setCheckable(True)
        a.setChecked(bool(self.cfg["topo"]))
        a.toggled.connect(self.alternar_topo)

        m.addSeparator()
        m.addAction("🌐 Abrir painel no navegador", lambda checked=False: webbrowser.open(self.cliente.base))
        m.addAction("🙈 Esconder", self.hide)
        m.addAction("❌ Sair", QtWidgets.QApplication.quit)
        return m

    def _bandeja(self):
        self.tray = None
        if not QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
            return
        icone = QtGui.QIcon(self._pix("seria"))
        self.tray = QtWidgets.QSystemTrayIcon(icone, self)
        self.tray.setToolTip("Alice")
        menu = QtWidgets.QMenu()
        menu.addAction("Mostrar", lambda checked=False: (self.show(), self.raise_()))
        menu.addAction("Esconder", self.hide)
        menu.addAction("Falar 🎤", lambda checked=False: (self.show(), self.clique_mic()))
        menu.addAction("Digitar…", lambda checked=False: (self.show(), self.abrir_caixa()))
        menu.addSeparator()
        menu.addAction("Sair", QtWidgets.QApplication.quit)
        self._menu_bandeja = menu  # precisa ficar referenciado
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda motivo: (self.show(), self.raise_()))
        self.tray.show()

    def mudar_escala(self, v):
        self._set("escala", v)
        self._aplicar_layout()
        self.move(self.x(), self._chao_y())

    def alternar_topo(self, v):
        self._set("topo", bool(v))
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, bool(v))
        self.show()  # trocar a flag esconde a janela: precisa mostrar de novo

    def encerrar(self):
        self.atalho.parar()
        self._gen_escuta += 1
        if self.voz_estado in ("preparando", "ouvindo", "gravando", "transcrevendo"):
            try:
                self.cliente.ouvir_cancelar()  # não deixa o microfone aberto no servidor
            except Exception:
                pass
        self._parar.set()
        self.cfg["x"] = self.x()
        L.salvar_config(self.cfg)


def main():
    ap = argparse.ArgumentParser(description="Desktop pet da Alice")
    ap.add_argument("--servidor", help="endereço do servidor (padrão: o salvo, http://127.0.0.1:5000)")
    ap.add_argument("--sem-servidor", action="store_true", help="não liga o server.py sozinho")
    ap.add_argument("--escala", type=float, help="tamanho: 0.5 pequena, 0.7 média, 1.0 grande")
    args = ap.parse_args()

    cfg = L.carregar_config()
    if args.servidor:
        cfg["servidor"] = args.servidor
    if args.escala:
        cfg["escala"] = min(2.0, max(0.3, args.escala))
    cliente = L.Cliente(cfg["servidor"])

    proc = None
    if not args.sem_servidor and ("127.0.0.1" in cfg["servidor"] or "localhost" in cfg["servidor"]):
        print("Conferindo se a Alice (server.py) está no ar…")
        try:
            proc = L.garantir_servidor(cliente, os.path.join(PASTA, "server.py"), RAIZ)
            print("Servidor ligado pelo pet." if proc else "Servidor já estava no ar.")
        except Exception as e:
            print("Aviso:", e, "\nO pet abre mesmo assim e conecta quando o servidor subir.")

    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # esconder o pet não encerra o programa
    janela = JanelaPet(cfg, cliente, ligou_servidor=proc is not None)
    janela.show()

    def sair():
        janela.encerrar()
        if proc and proc.poll() is None:  # só desliga o servidor se foi o pet que ligou
            proc.terminate()
    app.aboutToQuit.connect(sair)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
