"""Servidor + motor de emoções + protocolo do pet (python -m unittest testes.test_integracao_pet, dentro da pasta IA)."""
import json
import os
import sys
import tempfile
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
