"""
Tecla de atalho GLOBAL para falar com a Alice (funciona com qualquer programa em primeiro plano).

Usa o RegisterHotKey do próprio Windows: não precisa de biblioteca extra e não "escuta" o teclado
inteiro, só avisa quando a combinação escolhida é apertada. Só funciona no Windows.

AtalhoGlobal roda numa thread com o loop de mensagens do Windows (é o que o RegisterHotKey exige:
registrar, receber e desregistrar na MESMA thread). A parte do Windows fica atrás de uma "api"
(classe Win32 abaixo) para a lógica poder ser testada com uma api falsa.
"""
import os
import threading

import pet_logic as L

MOD_NOREPEAT = 0x4000  # segurar a tecla não dispara de novo
_ID = 1


class Win32:
    """As chamadas reais ao Windows (user32/kernel32 via ctypes)."""
    WM_HOTKEY, WM_APP = 0x0312, 0x8000
    ERRO_JA_REGISTRADA = 1409

    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ct, self.wt = ctypes, wintypes
        self.u = ctypes.WinDLL("user32", use_last_error=True)
        self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        self.u.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        self.u.RegisterHotKey.restype = wintypes.BOOL
        self.u.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        self.u.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.u.PostThreadMessageW.restype = wintypes.BOOL
        self.u.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        self.u.GetMessageW.restype = ctypes.c_int
        self.u.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT,
                                        wintypes.UINT]
        self.k.GetCurrentThreadId.restype = wintypes.DWORD

    def preparar_fila(self):
        """Chamada pela thread do loop: cria a fila de mensagens dela e devolve o id da thread."""
        msg = self.wt.MSG()
        self.u.PeekMessageW(self.ct.byref(msg), None, 0, 0, 0)
        return self.k.GetCurrentThreadId()

    def registrar(self, id_, mods, vk):
        ok = self.u.RegisterHotKey(None, id_, mods, vk)
        return bool(ok), (None if ok else self.ct.get_last_error())

    def desregistrar(self, id_):
        self.u.UnregisterHotKey(None, id_)

    def esperar_mensagem(self):
        msg = self.wt.MSG()
        if self.u.GetMessageW(self.ct.byref(msg), None, 0, 0) <= 0:
            return "sair", None
        if msg.message == self.WM_HOTKEY:
            return "hotkey", msg.wParam
        if msg.message == self.WM_APP:
            return "comando", None
        if msg.message == self.WM_APP + 1:
            return "sair", None
        return "outro", None

    def postar(self, id_thread, tipo):
        self.u.PostThreadMessageW(id_thread, self.WM_APP if tipo == "comando" else self.WM_APP + 1, 0, 0)


class AtalhoGlobal:
    def __init__(self, ao_pressionar, api=None):
        """ao_pressionar: função chamada (na thread do atalho!) quando a tecla é apertada."""
        self.cb, self._api, self._tid = ao_pressionar, api, None
        self._thread = None
        self._lock = threading.Lock()
        self._pronto, self._feito = threading.Event(), threading.Event()
        self._cmd, self._resultado = None, (True, None)
        self.atual = None  # Atalho registrado agora (ou None)

    @staticmethod
    def disponivel():
        return os.name == "nt"

    def _api_ou_erro(self):
        if self._api is None:
            if not self.disponivel():
                return None
            self._api = Win32()
        return self._api

    def _iniciar(self):
        if self._thread and self._thread.is_alive():
            return True
        self._pronto.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self._pronto.wait(3)

    def definir(self, atalho):
        """Registra `atalho` (pet_logic.Atalho) ou remove (None). Devolve (ok, mensagem)."""
        with self._lock:
            try:
                api = self._api_ou_erro()
            except Exception as e:
                return False, f"Não consegui usar o atalho global: {e}"
            if api is None:
                return False, "A tecla de atalho global só funciona no Windows."
            if atalho is None and self.atual is None and not self._thread:
                return True, None
            if not self._iniciar():
                return False, "Não consegui iniciar o atalho global."
            self._cmd, self._resultado = atalho, (True, None)
            self._feito.clear()
            api.postar(self._tid, "comando")
            if not self._feito.wait(3):
                return False, "O Windows não respondeu ao registrar a tecla."
            ok, erro = self._resultado
            if ok:
                self.atual = atalho
                return True, None
            if erro == getattr(api, "ERRO_JA_REGISTRADA", 1409):
                return False, f"A tecla {atalho.rotulo} já está sendo usada por outro programa. Escolha outra."
            return False, f"O Windows recusou a tecla {atalho.rotulo} (erro {erro})."

    def parar(self):
        if self._thread and self._thread.is_alive() and self._tid is not None:
            self._api.postar(self._tid, "sair")
            self._thread.join(2)
        self.atual = None

    def _loop(self):
        api = self._api
        self._tid = api.preparar_fila()
        self._pronto.set()
        registrado = None  # (mods, vk) em vigor
        while True:
            tipo, _ = api.esperar_mensagem()
            if tipo == "hotkey":
                try:
                    self.cb()
                except Exception:  # um erro na interface não pode matar o atalho
                    pass
            elif tipo == "comando":
                novo, self._cmd = self._cmd, None
                anterior = registrado
                if registrado:
                    api.desregistrar(_ID)
                    registrado = None
                if novo is None:
                    self._resultado = (True, None)
                else:
                    ok, erro = api.registrar(_ID, novo.mods | MOD_NOREPEAT, novo.vk)
                    if ok:
                        registrado, self._resultado = (novo.mods, novo.vk), (True, None)
                    else:
                        if anterior:  # a nova falhou: volta a valer a tecla de antes
                            ok2, _ = api.registrar(_ID, anterior[0] | MOD_NOREPEAT, anterior[1])
                            registrado = anterior if ok2 else None
                        self._resultado = (False, erro)
                self._feito.set()
            elif tipo == "sair":
                break
        if registrado:
            api.desregistrar(_ID)
