"""Testes da iniciativa da Alice (python -m unittest testes.test_iniciativa, dentro da pasta IA)."""
import os
import random
import sys
import tempfile
import types
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["ALICE_DADOS"] = tempfile.mkdtemp()
os.environ.pop("ALICE_TOKEN", None)
try:
    import ollama  # noqa: F401
except ImportError:
    sys.modules["ollama"] = types.SimpleNamespace(chat=lambda **k: None)

from brain import emocoes as E  # noqa: E402
from brain import iniciativa as I  # noqa: E402
from brain.personality import Personality  # noqa: E402


class Relogio:
    def __init__(self, hora=14, dia=13):
        self.t = datetime(2026, 10, dia, hora, 0, 0).timestamp()

    def __call__(self):
        return self.t

    def passa(self, s):
        self.t += s


class Mundo:
    """Motor de emoções + iniciativa com relógio, sorteio, voz e presença falsos."""

    def __init__(self, hora=14, nivel=2, seed=1, idle=0.0, arquivo=None, agenda=None, clima=None, ocupado=False):
        self.r = Relogio(hora)
        self.emo = E.Emocoes(Personality(), agora=self.r, rng=random.Random(seed))
        self.falas, self.historico, self.aqueceu = [], [], []
        self.idle, self.ocupado = idle, ocupado
        self.ini = I.Iniciativa(self.emo, lambda t, e, v: self.falas.append((t, e, v)), agenda=agenda, clima=clima,
                                ocupado=lambda: self.ocupado, historico=self.historico.append,
                                ao_abrir=lambda: self.aqueceu.append(1), presenca=lambda: self.idle,
                                arquivo=arquivo, rng=random.Random(seed), nivel=nivel)

    def sai_do_pc(self):
        """Você se afasta do PC (já faz 3 min sem mexer)."""
        self.idle = I.PRESENTE_ATE + 1

    def so_perguntas(self):
        """O que ela disse como pergunta/aviso (vai para o histórico), sem os comentários de expressão."""
        return list(self.historico)

    def anda(self, segundos, passo=0.5, mexendo=True):
        """Avança o tempo rodando os dois motores. mexendo=True: você está no PC (idle baixo)."""
        for _ in range(int(segundos / passo)):
            self.r.passa(passo)
            if mexendo:
                self.idle = 5.0
            else:
                self.idle += passo
            self.emo.tick()
            self.ini.tick()

    def textos(self):
        return [t for t, _, _ in self.falas]


class AgendaFalsa:
    def __init__(self, itens):
        self.itens = itens

    def pendentes(self, limite=None):
        return self.itens


class ClimaFalso:
    def __init__(self, **d):
        self.dados = d


class TestAbertura(unittest.TestCase):
    def test_diz_oi_pela_hora_do_dia_e_aquece_o_modelo(self):
        for hora, palavra in ((8, "bom dia"), (15, "tarde"), (20, "noite"), (3, "")):
            m = Mundo(hora=hora)
            partes = m.ini.abrir()
            self.assertTrue(partes, hora)
            self.assertEqual(m.aqueceu, [1])
            if palavra:
                self.assertIn(palavra, " ".join(m.textos()).lower())
            self.assertEqual(len(m.historico), 1)  # a resposta dela fica no histórico
            self.assertTrue(all(e in E.EMOCOES for _, e, _ in m.falas))

    def test_so_uma_vez_a_cada_5_minutos(self):
        m = Mundo()
        self.assertTrue(m.ini.abrir())
        self.assertIsNone(m.ini.abrir())
        m.r.passa(301)
        self.assertTrue(m.ini.abrir())

    def test_desligada_nao_diz_oi(self):
        m = Mundo(nivel=0)
        self.assertIsNone(m.ini.abrir())
        self.assertEqual(m.falas, [])

    def test_lembra_da_agenda_de_hoje(self):
        ag = AgendaFalsa([{"quando": "2026-10-13T18:00:00", "texto": "treino de perna"},
                          {"quando": "2026-10-14T09:00:00", "texto": "amanhã"}])
        for seed in range(6):
            m = Mundo(agenda=ag, seed=seed)
            m.ini.rng = random.Random(0)  # 1º sorteio < 0.85: sempre inclui o contexto
            m.ini.abrir()
            self.assertIn("treino de perna", " ".join(m.textos()))
            self.assertNotIn("amanhã", " ".join(m.textos()))

    def test_avisa_de_chuva(self):
        m = Mundo(clima=ClimaFalso(chuva=80, max=25))
        m.ini.rng = random.Random(0)
        m.ini.abrir()
        self.assertIn("chover", " ".join(m.textos()))

    def test_sem_agenda_nem_clima_funciona(self):
        m = Mundo(clima=ClimaFalso())
        self.assertTrue(m.ini.abrir())

    def test_sumiu_por_dias_e_reinicio_rapido(self):
        arq = os.path.join(tempfile.mkdtemp(), "ini.json")
        m = Mundo(arquivo=arq)
        m.anda(61)  # grava "visto"
        self.assertTrue(os.path.exists(arq))
        # 5 dias depois
        antigo = Mundo(arquivo=arq)
        antigo.ini._visto_antes = antigo.r.t - 5 * 86400
        antigo.ini.abrir()
        self.assertIn("5 dias", " ".join(antigo.textos()))
        # reiniciou há 3 min
        rapido = Mundo(arquivo=arq)
        rapido.ini._visto_antes = rapido.r.t - 180
        rapido.ini.abrir()
        self.assertTrue(any(w in " ".join(rapido.textos()).lower() for w in ("reset", "reiniciei")))

    def test_acorda_a_alice_ao_ligar(self):
        m = Mundo()
        m.emo.definir("dormindo", fonte="manual", forcar=True, respeitar_bloqueio=False)
        m.ini.abrir()
        self.assertNotEqual(m.emo.atual, "dormindo")


class TestSilencio(unittest.TestCase):
    def test_pergunta_se_esta_fazendo_algo_importante(self):
        m = Mundo()
        m.anda(400)
        self.assertEqual(m.so_perguntas(), [])  # antes dos 7 min só há comentários de expressão
        m.anda(120)
        self.assertEqual(len(m.so_perguntas()), 1, m.textos())
        self.assertIn("importante", m.so_perguntas()[0])

    def test_pergunta_cada_vez_mais_espacada_e_para_na_terceira(self):
        m = Mundo()
        m.anda(3 * 3600)
        n = sum(1 for _, _, _ in m.falas)
        perguntas = [h for h in m.historico if "<emo:" in h]
        self.assertEqual(len(perguntas), 3, perguntas)
        self.assertGreater(n, 0)

    def test_nao_fala_com_cadeira_vazia(self):
        m = Mundo()
        m.sai_do_pc()
        m.anda(1800, mexendo=False)  # 30 min sem encostar no PC
        self.assertEqual(m.falas, [])

    def test_voce_falando_zera_a_contagem(self):
        m = Mundo()
        m.anda(300)
        m.emo.on_usuario("oi")
        m.anda(300)  # 5 min depois do "oi": ainda não chegou nos 7
        self.assertEqual([t for t in m.textos() if "importante" in t], [])

    def test_nao_interrompe_conversa_nem_microfone(self):
        m = Mundo()
        m.ocupado = True
        m.anda(900)
        self.assertEqual(m.falas, [])
        m.ocupado = False
        m.anda(5)
        self.assertTrue(m.falas)

    def test_nivel_zero_e_ritmo_zero_calam_a_alice(self):
        for cfg in ("nivel", "ritmo"):
            m = Mundo(nivel=0 if cfg == "nivel" else 2)
            if cfg == "ritmo":
                m.emo.ritmo = 0
            m.anda(3600)
            self.assertEqual(m.falas, [], cfg)

    def test_nivel_faladeira_pergunta_antes_que_calma(self):
        def quando(nivel):
            m = Mundo(nivel=nivel)
            for i in range(4000):
                m.anda(1)
                if m.historico:
                    return i
            return 10 ** 9
        self.assertLess(quando(3), quando(2))
        self.assertLess(quando(2), quando(1))

    def test_dormindo_acorda_para_perguntar(self):
        m = Mundo()
        m.emo.definir("dormindo", fonte="manual", forcar=True, respeitar_bloqueio=False)
        m.emo.ultima_interacao = m.r.t - 500
        m.ini._base_silencio = m.r.t - 500
        m.ini._vi = m.emo.ultima_interacao
        m.anda(10)
        self.assertTrue(m.falas)
        self.assertEqual(m.falas[0][1], "espreguicando")


class TestVoltou(unittest.TestCase):
    def test_comenta_quando_voce_volta_depois_de_um_tempo(self):
        m = Mundo()
        m.sai_do_pc()
        m.anda(1200, mexendo=False)
        self.assertEqual(m.falas, [])
        m.anda(3, mexendo=True)
        self.assertTrue(m.falas)
        self.assertEqual(len(m.historico), 1)

    def test_ausencia_curta_nao_comenta_e_reinicia_o_silencio(self):
        m = Mundo()
        m.sai_do_pc()
        m.anda(660, mexendo=False)  # 11 min fora
        m.anda(3, mexendo=True)
        self.assertEqual(m.so_perguntas(), [])
        m.anda(60)  # chegou agora: não pode perguntar "tá fazendo algo importante?" logo em seguida
        self.assertEqual(m.so_perguntas(), [])

    def test_ausencia_longa_tem_fala_dramatica(self):
        m = Mundo()
        m.sai_do_pc()
        m.anda(3 * 3600, mexendo=False)
        m.anda(3, mexendo=True)
        self.assertTrue(any(w in " ".join(m.textos()) for w in ("demora", "esperar")), m.textos())


class TestExpressao(unittest.TestCase):
    def test_espreguicando_fala_que_cansaco(self):
        m = Mundo()
        m.ini.rng = random.Random(0)
        m.emo.ultima_interacao = m.r.t - 300
        m.ini._vi = m.emo.ultima_interacao
        m.ini._base_silencio = m.r.t - 300
        m.emo.ultimo_bocejo = m.r.t - 10_000
        m.ini._ultima_fala = m.ini._ultima_expr = -1e9
        m.emo.definir("espreguicando", fonte="ocioso", forcar=True, bloquear=True)
        m.ini.tick()
        self.assertEqual(len(m.falas), 1)
        texto, emocao, _ = m.falas[0]
        self.assertEqual(emocao, "espreguicando")
        self.assertIn(texto, I.EXPRESSAO["espreguicando"])

    def test_so_comenta_mudancas_sozinhas_e_recentes(self):
        m = Mundo()
        m.ini.rng = random.Random(0)
        m.emo.definir("entediada", fonte="usuario", forcar=True)  # veio de você, não da vida própria
        m.ini.tick()
        self.assertEqual(m.falas, [])
        m.emo.definir("carente", fonte="ocioso", forcar=True)
        m.r.passa(10)  # evento velho
        m.ini.tick()
        self.assertEqual(m.falas, [])

    def test_respeita_intervalo_entre_comentarios(self):
        m = Mundo(nivel=3)
        m.ini.rng = random.Random(0)
        m.ini.rng.random = lambda: 0.0  # sempre sorteia "comentar"
        m.emo.definir("carente", fonte="ocioso", forcar=True)
        m.ini.tick()
        m.r.passa(3)
        m.emo.ocupado_ate = 0
        m.emo.definir("entediada", fonte="ocioso", forcar=True)
        m.ini.tick()
        self.assertEqual(len(m.falas), 1)

    def test_toda_emocao_comentavel_existe_no_catalogo_e_tem_chance(self):
        for nome in I.EXPRESSAO:
            self.assertIn(nome, E.EMOCOES)
            self.assertIn(nome, I.PROB_EXPRESSAO)

    def test_na_madrugada_comenta_menos(self):
        def conta(hora):
            m = Mundo(hora=hora)
            n = 0
            for seed in range(300):
                m.ini.rng = random.Random(seed)
                m.ini._ultima_expr = m.ini._ultima_fala = -1e9
                m.emo.ocupado_ate = 0
                m.emo.definir("carente", fonte="ocioso", forcar=True)
                m.ini.tick()
                n = len(m.falas)
            return n
        self.assertGreater(conta(14), conta(4))


class TestExtras(unittest.TestCase):
    def test_pergunta_do_almoco_uma_vez_por_dia(self):
        m = Mundo(hora=12)
        m.anda(120)
        almoco = [h for h in m.historico if "almo" in h.lower()]
        self.assertEqual(len(almoco), 1)
        m.anda(1800)
        self.assertEqual(len([h for h in m.historico if "almo" in h.lower()]), 1)

    def test_nao_pergunta_do_almoco_fora_do_horario(self):
        m = Mundo(hora=16)
        m.anda(300)
        self.assertEqual([h for h in m.historico if "almo" in h.lower() or "jant" in h.lower()], [])

    def test_manda_dormir_na_madrugada_uma_vez(self):
        m = Mundo(hora=1)
        m.anda(200)
        self.assertEqual(len([h for h in m.historico if "dormir" in h or "meia-noite" in h or "tarde" in h]), 1)
        antes = len(m.historico)
        m.anda(1800)
        self.assertEqual(len([h for h in m.historico[antes:] if "meia-noite" in h]), 0)

    def test_reage_aos_cutucoes(self):
        m = Mundo()
        m.ini.rng.random = lambda: 0.0
        for _ in range(4):
            m.emo.on_toque()
        m.ini.on_toque()
        m.ini.tick()
        self.assertEqual(len(m.falas), 1)
        self.assertEqual(m.falas[0][1], "irritada")
        self.assertIn(m.falas[0][0], I.TOQUE[4])
        # logo depois não repete (cooldown)
        m.r.passa(2)
        m.ini.on_toque()
        m.ini.tick()
        self.assertEqual(len(m.falas), 1)

    def test_cutucar_quem_dorme_acorda_reclamando(self):
        m = Mundo()
        m.emo.definir("dormindo", fonte="manual", forcar=True, respeitar_bloqueio=False)
        m.emo.on_toque()
        m.ini.on_toque()
        m.ini.tick()
        self.assertIn(m.falas[0][0], [t for t, _ in I.ACORDOU_TOQUE])

    def test_voz_desligada_vai_so_para_o_balao(self):
        m = Mundo()
        m.ini.configurar(voz=False)
        m.ini.abrir()
        self.assertTrue(m.falas and all(v is False for _, _, v in m.falas))


class TestConfig(unittest.TestCase):
    def test_nivel_invalido(self):
        m = Mundo()
        with self.assertRaises(ValueError):
            m.ini.configurar(nivel=7)
        m.ini.configurar(nivel="3")
        self.assertEqual(m.ini.nivel, 3)

    def test_disparar_cada_tipo(self):
        m = Mundo()
        for tipo in ("abertura", "checkin", "volta", "almoco", "jantar", "madrugada", "expressao"):
            self.assertTrue(m.ini.disparar(tipo), tipo)
        self.assertEqual(m.ini.disparar("expressao", emocao="espreguicando")[0][1], "espreguicando")
        self.assertIsNone(m.ini.disparar("inexistente"))
        self.assertIsNone(m.ini.disparar("expressao", emocao="nada"))

    def test_falas_sao_validas(self):
        """Toda fala usa emoção do catálogo e nada de gênero para o usuário."""
        textos = []

        def varre(x):
            if isinstance(x, tuple) and len(x) == 2 and isinstance(x[0], str):
                self.assertIn(x[1], E.EMOCOES, x)
                textos.append(x[0])
            elif isinstance(x, (list, tuple)):
                for y in x:
                    varre(y)
            elif isinstance(x, dict):
                for y in x.values():
                    varre(y)
        for banco in (I.SAUDACAO, I.CONVITE, I.REINICIO, I.SUMIU_DIAS, I.CHECKIN, I.ACORDEI, I.VOLTOU,
                      I.REFEICAO, I.MADRUGADA, I.ACORDOU_TOQUE):
            varre(banco)
        for t in textos:
            for proibida in ("sumido", "ocupado", "acordado", "quieto"):
                if proibida == "quieto" and "quieto demais por aqui" in t:
                    continue
                self.assertNotIn(proibida, t.lower(), t)
        self.assertGreater(len(textos), 40)

    def test_persistencia_corrompida_nao_quebra(self):
        arq = os.path.join(tempfile.mkdtemp(), "x.json")
        open(arq, "w", encoding="utf-8").write("{lixo")
        self.assertTrue(Mundo(arquivo=arq).ini.abrir())


class TestPresenca(unittest.TestCase):
    def test_fora_do_windows_devolve_none(self):
        from brain import presenca
        if sys.platform != "win32":
            self.assertIsNone(presenca.segundos_sem_input())

    def test_sem_presenca_conhecida_ela_considera_voce_por_perto(self):
        m = Mundo()
        m.ini._presenca = lambda: None
        for _ in range(1200):
            m.r.passa(0.5)
            m.emo.tick()
            m.ini.tick()
        self.assertTrue(m.falas)


class TestServidor(unittest.TestCase):
    """Rotas do servidor e configuração do pet."""

    @classmethod
    def setUpClass(cls):
        import server
        cls.server = server

    def setUp(self):
        self.c = self.server.app.test_client()
        self.original = (self.server.speaker, self.server.ini.nivel, self.server.ini._abriu_em)
        self.server.speaker = None
        self.server.ini._abriu_em = -1e9
        self.server.ini.nivel = 2
        self.server._aquecer_modelo = lambda: None
        self.server.ini._ao_abrir = lambda: self.aquecido.append(1)
        self.aquecido = []

    def tearDown(self):
        self.server.speaker, self.server.ini.nivel, self.server.ini._abriu_em = self.original

    def test_configurar_e_ler(self):
        r = self.c.post("/pet/iniciativa", json={"nivel": 3, "voz": False}).get_json()
        self.assertEqual((r["nivel"], r["voz"]), (3, False))
        self.assertEqual(self.c.get("/pet/iniciativa").get_json()["nome"], "Faladeira")
        self.assertEqual(self.c.post("/pet/iniciativa", json={"nivel": 9}).status_code, 400)
        self.c.post("/pet/iniciativa", json={"nivel": 2, "voz": True})

    def test_abertura_fala_publica_evento_e_aquece(self):
        _, antes = self.server.emo.eventos(0)
        r = self.c.post("/pet/iniciativa/abertura").get_json()
        self.assertTrue(r["falou"] and r["texto"])
        self.assertEqual(self.aquecido, [1])
        evs, _ = self.server.emo.eventos(antes)
        self.assertTrue([e for e in evs if e["tipo"] == "fala"])  # o pet e a web recebem como qualquer fala
        self.assertFalse(self.c.post("/pet/iniciativa/abertura").get_json()["falou"])  # não repete

    def test_disparar(self):
        r = self.c.post("/pet/iniciativa/disparar", json={"tipo": "expressao", "emocao": "espreguicando"})
        self.assertEqual(r.status_code, 200)
        self.assertIn(r.get_json()["texto"][0], I.EXPRESSAO["espreguicando"])
        self.assertEqual(self.c.post("/pet/iniciativa/disparar", json={"tipo": "xis"}).status_code, 400)

    def test_toque_nao_trava_e_nao_fala_na_hora(self):
        _, antes = self.server.emo.eventos(0)
        self.assertEqual(self.c.post("/pet/toque").status_code, 200)
        evs, _ = self.server.emo.eventos(antes)
        self.assertEqual([e for e in evs if e["tipo"] == "fala"], [])  # a reação falada sai pela thread

    def test_config_do_pet(self):
        from pet_logic import carregar_config, PADRAO
        self.assertEqual((PADRAO["iniciativa"], PADRAO["abertura"]), (2, True))
        arq = os.path.join(tempfile.mkdtemp(), "cfg.json")
        open(arq, "w", encoding="utf-8").write('{"iniciativa": 99}')
        self.assertEqual(carregar_config(arq)["iniciativa"], 3)
        open(arq, "w", encoding="utf-8").write('{"iniciativa": "lixo"}')
        self.assertEqual(carregar_config(arq)["iniciativa"], 2)


if __name__ == "__main__":
    unittest.main()
