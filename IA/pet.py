"""
Desktop pet da Alice: ela vive na sua tela, sempre por cima, e usa as mesmas expressões da interface web.

    pip install PySide6          (uma vez)
    python IA/pet.py             (liga o servidor sozinho se ele ainda não estiver no ar)

O que dá para fazer:
    clique              cutuca (1x simpática, várias seguidas ela se irrita)
    duplo clique        abre a caixa de texto para conversar (Enter envia, Esc fecha)
    arrastar            muda de lugar; ao soltar no ar ela cai e quica
    botão direito       menu: conversar, expressões, ritmo, tamanho, passear, dormir...
    ícone na bandeja    mostrar/esconder, conversar, sair

Toda a lógica (conversa com o servidor, fila de expressões, movimentos, física) está em pet_logic.py;
este arquivo só desenha a janela e repassa os eventos.
"""
import argparse
import os
import random
import sys
import threading
import time
import webbrowser

import pet_logic as L
from brain.emocoes import catalogo

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


class JanelaPet(QtWidgets.QWidget):
    def __init__(self, cfg, cliente, ligou_servidor=False):
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
        self._ultimo, self._offline_avisado = agora, False
        self._cache = {}

        self._aplicar_layout()

        # --- partes
        self.ponte = Ponte()
        self.ponte.evento.connect(self.on_evento)
        self.ponte.sync.connect(self.on_sync)
        self.ponte.online.connect(self.on_online)
        self.ponte.texto.connect(lambda t, tipo: self.balao.mostrar(t, 6 + len(t) / 20, time.time(), tipo))
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
        elif not self._offline_avisado:
            self._offline_avisado = True
            self.balao.mostrar("Perdi a conexão com a Alice (servidor). Vou tentando de novo…", 8, time.time(), "aviso")

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

    def enviar(self, texto):
        self.balao.mostrar("…", 90, time.time(), "pensando")  # some quando a primeira frase chegar
        if self.emo == "dormindo":
            self._async(self.cliente.acordar)

        def conversar():
            try:
                for nome, d in self.cliente.conversar(texto, falar=True, acoes=self.cfg["acoes"]):
                    if nome == "acao" and d.get("resultado"):
                        self.ponte.texto.emit("✓ " + str(d["resultado"])[:140], "aviso")
                    elif nome == "erro":
                        self.ponte.texto.emit("⚠ " + str(d.get("error", "erro"))[:140], "aviso")
            except Exception as e:
                self.ponte.texto.emit(f"Não consegui falar com o servidor: {e}", "aviso")
        threading.Thread(target=conversar, daemon=True).start()

    # ------------------------------------------------------------------ vida (a cada quadro)
    def tick(self):
        agora = time.time()
        dt = min(0.1, agora - self._ultimo)
        self._ultimo = agora
        ev = self.fila.proximo(agora)
        if ev:
            self._aplicar(ev)
        self._mover(agora, dt)
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
            self.salto, self.virado = s, s.x1 < s.x0

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

        self._desenhar_balao(p, agora, cx, topo)
        p.end()

    def _desenhar_balao(self, p, agora, cx, topo):
        b = self.balao
        if not b.visivel(agora):
            return
        fonte = QtGui.QFont("Segoe UI", 10)
        p.setFont(fonte)
        fm = QtGui.QFontMetrics(fonte)
        linhas = L.quebrar(b.texto, 260, fm.horizontalAdvance, max_linhas=5)
        larg = max(fm.horizontalAdvance(x) for x in linhas) + 24
        alt = len(linhas) * fm.lineSpacing() + 16
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
        fundo = {"aviso": "#ffd95a", "pensando": "#efe6ff"}.get(b.tipo, "#fffafd")
        p.setBrush(QtGui.QColor(fundo))
        p.setPen(QtGui.QPen(QtGui.QColor("#ff5c93"), 2))
        p.drawPath(forma)
        p.setPen(QtGui.QColor("#2a0a17"))
        for i, linha in enumerate(linhas):
            p.drawText(QtCore.QPointF(x + 12, y + 8 + fm.ascent() + i * fm.lineSpacing()), linha)
        p.setOpacity(1.0)

    # ------------------------------------------------------------------ mouse
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._press = e.globalPosition().toPoint()
            self._offset = self._press - self.frameGeometry().topLeft()
            self._moveu = False
        elif e.button() == Qt.MouseButton.RightButton:
            self._menu().exec(QtGui.QCursor.pos())

    def mouseMoveEvent(self, e):
        if self._press is None:
            return
        pos = e.globalPosition().toPoint()
        if not self._moveu and (pos - self._press).manhattanLength() > 6:
            self._moveu, self.arrastando = True, True
            self.salto = None
            self.fisica.parar()
        if self._moveu:
            self.move(pos - self._offset)

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or self._press is None:
            return
        self._press = None
        if self._moveu:
            self.arrastando = False
            self.fisica.soltar()  # solta no ar: cai e quica
            self.cfg["x"] = self.x()
        else:
            self._clique.start(230)  # espera: se vier o 2º clique, é duplo clique (conversar)

    def mouseDoubleClickEvent(self, e):
        self._clique.stop()
        self.abrir_caixa()

    def _cutucar(self):
        if self.balao.tipo == "aviso" and self.balao.visivel(time.time()):
            self.balao.fechar()  # clicar no aviso só dispensa
            return
        self._async(self.cliente.toque)

    # ------------------------------------------------------------------ menu e bandeja
    def _set(self, chave, valor):
        self.cfg[chave] = valor
        L.salvar_config(self.cfg)

    def _menu(self):
        m = QtWidgets.QMenu(self)
        m.addAction("💬 Conversar…", self.abrir_caixa)

        exp = m.addMenu("🎭 Expressões")
        for nome, c in self.cat.items():
            exp.addAction(c["rotulo"], lambda checked=False, n=nome: self._async(self.cliente.definir, n))

        ritmo = m.addMenu("⏱ Ritmo das expressões")
        for rotulo, v in (("Parada (só reage)", 0), ("Calma", 2), ("Normal", 1), ("Animada", 0.6)):
            ritmo.addAction(rotulo, lambda checked=False, v=v: self._async(self.cliente.ritmo, v))

        m.addAction("💤 Dormir", lambda checked=False: self._async(self.cliente.dormir))
        m.addAction("☀️ Acordar", lambda checked=False: self._async(self.cliente.acordar))
        m.addSeparator()

        tam = m.addMenu("📏 Tamanho")
        for rotulo, v in (("Pequena", 0.5), ("Média", 0.7), ("Grande", 1.0), ("Enorme", 1.4)):
            tam.addAction(rotulo, lambda checked=False, v=v: self.mudar_escala(v))

        for rotulo, chave in (("🐾 Passear pela tela", "passear"), ("⚙️ Executar ações do PC ao conversar", "acoes")):
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
        menu.addAction("Conversar…", lambda checked=False: (self.show(), self.abrir_caixa()))
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
