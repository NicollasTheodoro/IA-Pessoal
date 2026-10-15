"""
Detector de início e fim de fala, sem dependências (por isso dá para testar sem microfone).

Melhorias sobre o limiar fixo de antes:
  - Limiar adaptativo: acompanha o ruído de fundo (o mínimo dos últimos ~1,5 s) e sobe o limiar
    em quarto barulhento (ventilador, rua). Em ambiente silencioso fica exatamente no limiar de
    sempre, então nada muda para quem já usa.
  - Voz mínima: um estalo, batida na mesa ou tecla (menos de `voz_min` segundos acima do limiar)
    é descartado e a escuta continua, em vez de mandar "nada" para o Whisper.
  - Pré-roll: guarda os últimos blocos antes da voz para não cortar a primeira sílaba.
  - Aquecimento: os 2 primeiros blocos (0,2 s) só aprendem o ruído; ficam no pré-roll, então quem
    já começa a falar de imediato não perde nada.
"""
from collections import deque


class Vad:
    def __init__(self, limiar=0.01, silencio=1.0, max_seg=20.0, pre_roll=4, dur_bloco=0.1,
                 voz_min=0.25, auto=True, fator=2.5, teto=0.08, janela_ruido=15, aquecimento=2):
        self.limiar_base, self.silencio, self.max_seg = limiar, silencio, max_seg
        self.dur_bloco, self.voz_min = dur_bloco, voz_min
        self.auto, self.fator, self.teto = auto, fator, teto
        self.buffer = []
        self.pre = deque(maxlen=pre_roll)
        self.recentes = deque(maxlen=janela_ruido)
        self.nivel = 0.0
        self.aquecimento, self.blocos = aquecimento, 0
        self.reiniciar()

    def reiniciar(self):
        """Volta a esperar a voz (início, ou depois de descartar um ruído curto)."""
        self.buffer = []
        self.pre.clear()
        self.gravando = False
        self.t_inicio = self.t_voz = None
        self.blocos_voz = 0
        self._limiar_fixo = None

    def limiar(self):
        """Limiar em vigor. Congela quando a gravação começa (a própria voz não pode subir o limiar)."""
        if self._limiar_fixo is not None:
            return self._limiar_fixo
        if not self.auto or len(self.recentes) < 2:
            return self.limiar_base
        ruido = min(self.recentes)
        return min(self.teto, max(self.limiar_base, ruido * self.fator))

    def alimentar(self, volume, bloco, agora):
        """Recebe o volume (RMS) de um bloco de áudio e o próprio bloco."""
        self.nivel = volume
        self.blocos += 1
        if self.blocos <= self.aquecimento and not self.gravando:
            self.pre.append(bloco)  # ainda aprendendo o ruído de fundo (e já guardando para o pré-roll)
            self.recentes.append(volume)
            return
        lim = self.limiar()
        if volume > lim:
            if not self.gravando:
                self.gravando, self.t_inicio, self.blocos_voz = True, agora, 0
                self._limiar_fixo = lim
                self.buffer.extend(self.pre)
                self.pre.clear()
            self.buffer.append(bloco)
            self.t_voz = agora
            self.blocos_voz += 1
        elif self.gravando:
            self.buffer.append(bloco)
        else:
            self.pre.append(bloco)
            self.recentes.append(volume)

    def acabou(self, agora):
        """'silencio' ou 'maximo' quando a fala terminou; None se ainda não (ou se descartou um ruído curto)."""
        if not self.gravando:
            return None
        if agora - self.t_voz > self.silencio:
            if self.blocos_voz * self.dur_bloco < self.voz_min:
                self.reiniciar()  # foi só um estalo: ignora e continua esperando
                return None
            return "silencio"
        if agora - self.t_inicio > self.max_seg:
            return "maximo"
        return None
