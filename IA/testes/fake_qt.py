"""Qt de mentira: só o bastante para EXECUTAR o pet.py sem tela (pega erro de nome, de fluxo e de lógica).
Não valida a API real do Qt: isso só o Qt de verdade faz."""
import sys
import types


class Flag:
    """Qualquer Qt.Alguma.Coisa; aceita '|'."""
    def __init__(self, nome=""):
        self.nome = nome
    def __getattr__(self, n):
        if n.startswith("__"):
            raise AttributeError(n)
        return Flag(f"{self.nome}.{n}")
    def __or__(self, o):
        return Flag(f"{self.nome}|{getattr(o, 'nome', o)}")
    __ror__ = __or__
    def __eq__(self, o):
        return isinstance(o, Flag) and self.nome == o.nome
    def __hash__(self):
        return hash(self.nome)


class _Bound:
    def __init__(self):
        self.slots = []
    def connect(self, f):
        self.slots.append(f)
    def emit(self, *a):
        for f in list(self.slots):
            f(*a)


class Signal:
    def __init__(self, *tipos):
        pass
    def __set_name__(self, dono, nome):
        self.nome = nome
    def __get__(self, obj, tipo=None):
        if obj is None:
            return self
        return obj.__dict__.setdefault("_sig_" + self.nome, _Bound())


class QObject:
    def __init__(self, *a, **k):
        pass


class QPoint:
    def __init__(self, x=0, y=0):
        self._x, self._y = x, y
    def x(self): return self._x
    def y(self): return self._y
    def __sub__(self, o): return QPoint(self._x - o._x, self._y - o._y)
    def __add__(self, o): return QPoint(self._x + o._x, self._y + o._y)
    def manhattanLength(self): return abs(self._x) + abs(self._y)
    def toPoint(self): return self


class QPointF(QPoint):
    pass


class QRectF:
    def __init__(self, *a):
        self.a = a


class Rect:
    def __init__(self, x, y, w, h):
        self._x, self._y, self._w, self._h = x, y, w, h
    def left(self): return self._x
    def top(self): return self._y
    def right(self): return self._x + self._w - 1
    def bottom(self): return self._y + self._h - 1
    def topLeft(self): return QPoint(self._x, self._y)
    def center(self): return QPoint(self._x + self._w // 2, self._y + self._h // 2)


class QTimer(QObject):
    timeout = Signal()
    def __init__(self, *a):
        self.ativo, self.ms = False, None
    def setSingleShot(self, v): self.unico = v
    def start(self, ms=None): self.ativo, self.ms = True, ms
    def stop(self): self.ativo = False


class _Event:
    class Type:
        ActivationChange = Flag("ActivationChange")


class QWidget(QObject):
    def __init__(self, parent=None, flags=None):
        self._pos, self._size, self._visivel = QPoint(100, 100), (100, 100), False
        self.flags = flags
    def setWindowFlags(self, f): self.flags = f
    def setWindowFlag(self, f, v=True): pass
    def setAttribute(self, a): pass
    def setWindowTitle(self, t): pass
    def setFixedSize(self, w, h): self._size = (w, h)
    def width(self): return self._size[0]
    def height(self): return self._size[1]
    def x(self): return self._pos.x()
    def y(self): return self._pos.y()
    def pos(self): return self._pos
    def move(self, a, b=None): self._pos = a if b is None else QPoint(a, b)
    def frameGeometry(self): return Rect(self._pos.x(), self._pos.y(), *self._size)
    def show(self): self._visivel = True
    def hide(self): self._visivel = False
    def isVisible(self): return self._visivel
    def raise_(self): pass
    def activateWindow(self): pass
    def isActiveWindow(self): return True
    def update(self): self.atualizacoes = getattr(self, "atualizacoes", 0) + 1
    def setFocus(self): pass
    def keyPressEvent(self, e): pass
    def changeEvent(self, e): pass


class _Acao:
    def __init__(self, texto, cb=None):
        self.texto, self.cb, self.toggled, self.checavel = texto, cb, _Bound(), False
    def setCheckable(self, v): self.checavel = v
    def setChecked(self, v): self.marcado = v


class QMenu(QWidget):
    def __init__(self, *a):
        super().__init__()
        self.itens = []
    def addAction(self, texto, cb=None):
        a = _Acao(texto, cb)
        self.itens.append(a)
        return a
    def addMenu(self, texto):
        m = QMenu()
        self.itens.append(m)
        m.texto = texto
        return m
    def addSeparator(self): pass
    def exec(self, pos=None): self.executado = True


class QApplication:
    saiu = False
    def __init__(self, *a): pass
    @staticmethod
    def quit(): QApplication.saiu = True
    def setQuitOnLastWindowClosed(self, v): pass


class QSystemTrayIcon(QObject):
    activated = Signal()
    @staticmethod
    def isSystemTrayAvailable(): return True
    def __init__(self, icone=None, pai=None): pass
    def setToolTip(self, t): pass
    def setContextMenu(self, m): self.menu = m
    def show(self): pass


class QFrame(QWidget):
    def setObjectName(self, n): pass
    def setStyleSheet(self, s): pass


class QLineEdit(QWidget):
    returnPressed = Signal()
    def __init__(self, *a):
        super().__init__()
        self.t = ""
    def setPlaceholderText(self, t): pass
    def text(self): return self.t
    def clear(self): self.t = ""
    def setText(self, t): self.t = t


class QVBoxLayout:
    def __init__(self, *a): pass
    def setContentsMargins(self, *a): pass
    def addWidget(self, w): pass


# ---------------- QtGui
class QPixmap:
    def __init__(self, caminho=None):
        self.caminho = caminho
    def isNull(self): return False
    def scaled(self, *a): return self
    def transformed(self, t): return self


class QPainter:
    class RenderHint:
        Antialiasing = Flag("A")
        SmoothPixmapTransform = Flag("S")
    chamadas = []
    def __init__(self, alvo=None): QPainter.chamadas = []
    def __getattr__(self, n):
        def f(*a, **k):
            QPainter.chamadas.append((n, a))
        return f


class QFont:
    def __init__(self, *a): pass


class QFontMetrics:
    def __init__(self, f): pass
    def horizontalAdvance(self, s): return len(s) * 7
    def lineSpacing(self): return 16
    def ascent(self): return 12


class QColor:
    def __init__(self, *a): pass


class QPen:
    def __init__(self, *a): pass


class QPainterPath:
    def addRoundedRect(self, *a): pass
    def moveTo(self, *a): pass
    def lineTo(self, *a): pass
    def closeSubpath(self): pass
    def united(self, o): return self


class QTransform:
    def scale(self, *a): pass


class QIcon:
    def __init__(self, *a): pass


class _Tela:
    def availableGeometry(self): return Rect(0, 0, 1920, 1040)


class QGuiApplication:
    @staticmethod
    def screenAt(p): return _Tela()
    @staticmethod
    def primaryScreen(): return _Tela()


class QCursor:
    @staticmethod
    def pos(): return QPoint(500, 500)


def instalar():
    qtcore = types.ModuleType("PySide6.QtCore")
    qtcore.Qt, qtcore.Signal, qtcore.QObject, qtcore.QTimer = Flag("Qt"), Signal, QObject, QTimer
    qtcore.QPointF, qtcore.QPoint, qtcore.QRectF, qtcore.QEvent = QPointF, QPoint, QRectF, _Event
    qtgui = types.ModuleType("PySide6.QtGui")
    for n in ("QPixmap", "QPainter", "QFont", "QFontMetrics", "QColor", "QPen", "QPainterPath", "QTransform",
              "QIcon", "QGuiApplication", "QCursor"):
        setattr(qtgui, n, globals()[n])
    qtw = types.ModuleType("PySide6.QtWidgets")
    for n in ("QWidget", "QMenu", "QApplication", "QSystemTrayIcon", "QFrame", "QLineEdit", "QVBoxLayout"):
        setattr(qtw, n, globals()[n])
    raiz = types.ModuleType("PySide6")
    raiz.QtCore, raiz.QtGui, raiz.QtWidgets = qtcore, qtgui, qtw
    sys.modules.update({"PySide6": raiz, "PySide6.QtCore": qtcore, "PySide6.QtGui": qtgui, "PySide6.QtWidgets": qtw})
