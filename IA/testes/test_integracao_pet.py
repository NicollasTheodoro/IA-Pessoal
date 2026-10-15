"""Servidor + motor de emoções + protocolo do pet (python -m unittest testes.test_integracao_pet, dentro da pasta IA)."""
import json
import os
import sys
import tempfile
import threading
import time
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["ALICE_DADOS"] = tempfile.mkdtemp()
os.environ.pop("ALICE_TOKEN", None)
try:
    import ollama  # noqa: F401
except ImportError:  # o sandbox/CI pode não ter o Ollama: o teste usa um "modelo" falso
    sys.modules["ollama"] = types.SimpleNamespace(chat=lambda **k: None)

import server  # noqa: E402

LOCAL = {"REMOTE_ADDR": "127.0.0.1"}


def zerar_motor(server):
    """O motor é global no server.py: cada teste começa de um estado limpo."""
    e = server.emo
    e.bloqueio_ate = e.ocupado_ate = 0.0
    e.fila.clear()
    e.toques.clear()
    e.ultima_interacao = e.agora()
    e.atual, e.ate = "neutra", e.agora() + 3600


class SpeakerFalso:
    """Guarda as frases; tocar() dispara o gancho como se a voz tivesse começado."""

    def __init__(self):
        self.fila = []

    def enfileirar(self, texto, ao_iniciar=None):
        self.fila.append((texto, ao_iniciar))

    def parar(self):
        self.fila.clear()

    def esperar(self):
        pass

    def tocar_tudo(self):
        for texto, cb in self.fila:
            if cb:
                cb()
        self.fila.clear()


def sse(resp):
    saida = []
    for bloco in resp.get_data(as_text=True).strip().split("\n\n"):
        if not bloco.strip():
            continue
        ev, dados = bloco.split("\n", 1)
        saida.append((ev.replace("event: ", ""), json.loads(dados.replace("data: ", "", 1))))
    return saida


class Base(unittest.TestCase):
    def setUp(self):
        self.c = server.app.test_client()
        self.original_stream = server.brain._chat_stream
        self.original_speaker = server.speaker
        server.brain.messages = []
        zerar_motor(server)

    def tearDown(self):
        server.brain._chat_stream = self.original_stream
        server.speaker = self.original_speaker

    def modelo(self, texto):
        server.brain._chat_stream = lambda msgs: iter([texto[i:i + 4] for i in range(0, len(texto), 4)])

    def conversar(self, msg, **extra):
        """POST /chat lendo o stream inteiro (o Flask só roda o gerador quando o corpo é lido)."""
        r = self.c.post("/chat", json={"message": msg, **extra}, environ_base=LOCAL)
        return sse(r)

    def ultimo_id(self):
        return self.c.get("/pet/eventos", environ_base=LOCAL).get_json()["ultimo"]

    def eventos(self, desde):
        return self.c.get(f"/pet/eventos?desde={desde}", environ_base=LOCAL).get_json()["eventos"]


class Chat(Base):
    def test_cada_frase_leva_a_sua_emocao_sem_voz(self):
        self.modelo("<emo:feliz> Abrindo agora mesmo. <emo:desconfiada> Mas não some lá dentro, hein.")
        antes = self.ultimo_id()
        evs = self.conversar("abre o youtube")
        frases = [d for t, d in evs if t == "sentence"]
        self.assertEqual([f["emocao"] for f in frases], ["feliz", "desconfiada"])
        self.assertTrue(all("<" not in f["text"] for f in frases), "a tag nunca aparece no texto")
        falas = [e for e in self.eventos(antes) if e["tipo"] == "fala"]
        self.assertEqual([f["emocao"] for f in falas], ["feliz", "desconfiada"])
        self.assertEqual(falas[0]["texto"], "Abrindo agora mesmo.")
        self.assertEqual([t for t, _ in evs][-1], "fim")

    def test_sem_tag_usa_as_palavras_da_frase(self):
        self.modelo("Consegui, pronto! Agora vai.")
        antes = self.ultimo_id()
        self.conversar("faz isso")
        falas = [e for e in self.eventos(antes) if e["tipo"] == "fala"]
        self.assertTrue(falas)
        self.assertEqual(falas[0]["emocao"], "vitoria")

    def test_reage_a_mensagem_antes_da_resposta(self):
        self.modelo("Oi. Demorou, hein.")
        antes = self.ultimo_id()
        self.conversar("você é uma inútil")
        evs = self.eventos(antes)
        self.assertEqual(evs[0]["tipo"], "emocao")
        self.assertEqual(evs[0]["fonte"], "usuario")

    def test_com_voz_a_fala_so_aparece_quando_comeca_a_tocar(self):
        sp = SpeakerFalso()
        server.speaker = sp
        self.modelo("<emo:timida> Para com isso, sério. <emo:apaixonada> Continua, vai.")
        antes = self.ultimo_id()
        self.conversar("você é linda", speak=True)
        self.assertEqual(len(sp.fila), 2)
        self.assertEqual([e for e in self.eventos(antes) if e["tipo"] == "fala"], [], "ainda não tocou")
        sp.tocar_tudo()
        falas = [e for e in self.eventos(antes) if e["tipo"] == "fala"]
        self.assertEqual([f["emocao"] for f in falas], ["timida", "apaixonada"])

    def test_historico_guarda_as_tags_de_emocao(self):
        self.modelo("<emo:feliz> Oi, tudo bem com você? <emo:brincalhona> Demorou, hein, sumida.")
        self.conversar("oi")
        resposta = server.brain.messages[-1]["content"]
        self.assertIn("<emo:feliz>", resposta)
        self.assertIn("<emo:brincalhona>", resposta)

    def test_erro_do_modelo_deixa_confusa(self):
        def quebra(msgs):
            raise RuntimeError("ollama fora do ar")
            yield  # noqa
        server.brain._chat_stream = quebra
        self.assertIn("erro", [t for t, _ in self.conversar("oi")])
        server.emo.fila.clear()  # (só para não vazar para outros testes)

    def test_estado_traz_a_expressao(self):
        j = self.c.get("/state", environ_base=LOCAL).get_json()
        self.assertIn(j["expressao"]["nome"], server.catalogo_emocoes())


class MicFalso:
    """Listener de mentira: ouvir_som devolve o texto combinado (ou None) depois de um instante."""
    estado, nivel, limiar_atual = "parado", 0.0, 0.01

    def __init__(self, texto="abre o youtube", demora=0.0):
        self.texto, self.demora, self.chamadas = texto, demora, []

    def ouvir_som(self, espera_max=None, cancelar=None):
        self.chamadas.append(espera_max)
        self.estado, self.nivel = "gravando", 0.12
        fim = time.time() + self.demora
        while time.time() < fim:
            if cancelar is not None and cancelar.is_set():
                self.estado, self.nivel = "parado", 0.0
                return None
            time.sleep(0.01)
        self.estado, self.nivel = "parado", 0.0
        return self.texto


class Microfone(Base):
    def setUp(self):
        super().setUp()
        self.mic0, self.ok0 = server.mic, server.ouvido_ok
        server.ouvido_ok = True

    def tearDown(self):
        server.mic, server.ouvido_ok = self.mic0, self.ok0
        super().tearDown()

    def test_estado_sem_microfone_instalado(self):
        server.ouvido_ok, server.mic = False, None
        j = self.c.get("/ouvir/estado", environ_base=LOCAL).get_json()
        self.assertEqual((j["ouvido"], j["pronto"], j["ativo"], j["estado"]), (False, False, False, "parado"))
        self.assertEqual(self.c.post("/ouvir", environ_base=LOCAL).status_code, 501)

    def test_ouvir_devolve_o_texto_e_passa_a_espera(self):
        server.mic = MicFalso("tudo bem")
        r = self.c.post("/ouvir?espera=7", environ_base=LOCAL)
        self.assertEqual(r.get_json()["texto"], "tudo bem")
        self.assertEqual(server.mic.chamadas, [7.0])
        self.c.post("/ouvir?espera=1000", environ_base=LOCAL)
        self.assertEqual(server.mic.chamadas[-1], 60.0, "limita a espera")
        self.c.post("/ouvir", environ_base=LOCAL)
        self.assertEqual(server.mic.chamadas[-1], 20.0, "padrão de sempre (a interface web não manda nada)")

    def test_fica_atenta_enquanto_ouve_e_solta_depois(self):
        server.mic = MicFalso("oi", demora=0.4)
        antes = self.ultimo_id()
        done = []
        t = threading.Thread(target=lambda: done.append(self.c.post("/ouvir", environ_base=LOCAL)))
        t.start()
        time.sleep(0.15)
        self.assertEqual(server.emo.atual, "ouvindo")
        est = self.c.get("/ouvir/estado", environ_base=LOCAL).get_json()
        self.assertEqual((est["ativo"], est["estado"], est["nivel"]), (True, "gravando", 0.12))
        t.join()
        nomes = [e["nome"] for e in self.eventos(antes) if e["tipo"] == "emocao"]
        self.assertEqual(nomes[0], "ouvindo")
        self.assertEqual(server.emo.ocupado_ate, 0.0, "liberou a vida própria")
        self.assertFalse(self.c.get("/ouvir/estado", environ_base=LOCAL).get_json()["ativo"])

    def test_ninguem_falou_fica_confusa(self):
        server.mic = MicFalso(None)
        self.c.post("/ouvir", environ_base=LOCAL)
        time.sleep(0.02)
        server.emo.tick()
        self.assertEqual(server.emo.atual, "confusa")

    def test_cancelar_nao_deixa_confusa(self):
        server.mic = MicFalso("x", demora=2)
        t = threading.Thread(target=lambda: self.c.post("/ouvir", environ_base=LOCAL))
        t.start()
        time.sleep(0.15)
        self.c.post("/ouvir/cancelar", environ_base=LOCAL)
        t.join(2)
        server.emo.tick()
        self.assertNotEqual(server.emo.atual, "confusa")
        self.assertEqual(server.emo.fila, [])

    def test_ocupado_devolve_409(self):
        server.mic = MicFalso("x", demora=0.5)
        t = threading.Thread(target=lambda: self.c.post("/ouvir", environ_base=LOCAL))
        t.start()
        time.sleep(0.15)
        self.assertEqual(self.c.post("/ouvir", environ_base=LOCAL).status_code, 409)
        t.join()

    def test_preparar_carrega_uma_vez_em_segundo_plano(self):
        server.mic = None
        cargas = []
        original = server.carregar_mic
        def lento():
            cargas.append(1)
            time.sleep(0.2)
            server.mic = MicFalso()
            return server.mic
        server.carregar_mic = lento
        try:
            j = self.c.post("/ouvir/preparar", environ_base=LOCAL).get_json()
            self.assertTrue(j["carregando"])
            self.c.post("/ouvir/preparar", environ_base=LOCAL)  # repetir não carrega de novo
            self.assertTrue(esperar_ate(lambda: self.c.get("/ouvir/estado", environ_base=LOCAL).get_json()["pronto"]))
            self.assertEqual(len(cargas), 1)
            self.assertFalse(server.mic_carregando)
        finally:
            server.carregar_mic = original

    def test_remoto_sem_senha_nao_acessa_o_microfone(self):
        for rota, metodo in (("/ouvir/estado", "get"), ("/ouvir/preparar", "post"), ("/ouvir", "post")):
            r = getattr(self.c, metodo)(rota, environ_base={"REMOTE_ADDR": "100.64.1.2"})
            self.assertIn(r.status_code, (401, 403), rota)


def esperar_ate(cond, s=2.0):
    fim = time.time() + s
    while time.time() < fim:
        if cond():
            return True
        time.sleep(0.02)
    return False


class Rotas(Base):
    def test_catalogo(self):
        j = self.c.get("/pet/catalogo", environ_base=LOCAL).get_json()
        self.assertGreaterEqual(len(j["emocoes"]), 15)
        for e in j["emocoes"].values():
            self.assertIn(e["mov"], j["movimentos"])

    def test_primeira_chamada_so_devolve_estado(self):
        j = self.c.get("/pet/eventos", environ_base=LOCAL).get_json()
        self.assertEqual(j["eventos"], [])
        self.assertIn("nome", j["atual"])

    def test_definir_toque_ritmo_dormir_acordar(self):
        post = lambda rota, **b: self.c.post(rota, json=b, environ_base=LOCAL)  # noqa: E731
        self.assertEqual(post("/pet/definir", nome="irritada").get_json()["atual"]["nome"], "irritada")
        self.assertEqual(post("/pet/definir", nome="Animada").get_json()["atual"]["nome"], "feliz")
        self.assertEqual(post("/pet/definir", nome="inventada").status_code, 400)
        antes = self.ultimo_id()
        post("/pet/toque")
        self.assertTrue(self.eventos(antes))
        self.assertEqual(post("/pet/ritmo", ritmo=2).get_json()["atual"]["ritmo"], 2.0)
        self.assertEqual(post("/pet/ritmo", ritmo="x").status_code, 400)
        post("/pet/ritmo", ritmo=1)
        self.assertEqual(post("/pet/dormir").get_json()["atual"]["nome"], "dormindo")
        self.assertEqual(post("/pet/acordar").get_json()["atual"]["nome"], "espreguicando")

    def test_aviso_vira_evento_no_pet(self):
        antes = self.ultimo_id()
        server.notificar("Lembrete: testar")
        tipos = [e["tipo"] for e in self.eventos(antes)]
        self.assertIn("aviso", tipos)
        server.avisos.clear()

    def test_remoto_exige_senha(self):
        r = self.c.get("/pet/eventos", environ_base={"REMOTE_ADDR": "100.64.1.2"})
        self.assertIn(r.status_code, (401, 403))


if __name__ == "__main__":
    unittest.main()
