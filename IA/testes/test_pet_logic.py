"""Lógica do desktop pet (python -m unittest testes.test_pet_logic, dentro da pasta IA)."""
import json
import math
import os
import random
import socket
import sys
import tempfile
import textwrap
import threading
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["ALICE_DADOS"] = tempfile.mkdtemp()
os.environ.pop("ALICE_TOKEN", None)
try:
    import ollama  # noqa: F401
except ImportError:
    sys.modules["ollama"] = types.SimpleNamespace(chat=lambda **k: None)

import pet_logic as L  # noqa: E402
from brain.emocoes import EMOCOES, MOVIMENTOS  # noqa: E402


def zerar_motor(server):
    """O motor é global no server.py: cada teste começa de um estado limpo."""
    e = server.emo
    e.bloqueio_ate = e.ocupado_ate = 0.0
    e.fila.clear()
    e.toques.clear()
    e.ultima_interacao = e.agora()
    e.atual, e.ate = "neutra", e.agora() + 3600


def porta_livre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ComServidor(unittest.TestCase):
    """Sobe o server.py de verdade (modelo falso) numa porta e usa o Cliente do pet."""

    @classmethod
    def setUpClass(cls):
        import server
        from werkzeug.serving import make_server
        cls.server = server
        texto = "<emo:feliz> Abrindo agora mesmo, viu. <emo:irritada> Eu fico esperando aqui sozinha."
        server.brain._chat_stream = lambda msgs: iter([texto[i:i + 6] for i in range(0, len(texto), 6)])
        server.brain.clima.atualizar = lambda: None
        cls.porta = porta_livre()
        cls.http = make_server("127.0.0.1", cls.porta, server.app, threaded=True)
        threading.Thread(target=cls.http.serve_forever, daemon=True).start()
        cls.c = L.Cliente(f"http://127.0.0.1:{cls.porta}")

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()

    def setUp(self):
        zerar_motor(self.server)

    def test_no_ar_e_catalogo(self):
        self.assertTrue(self.c.no_ar())
        cat = self.c.catalogo()
        self.assertEqual(set(cat["emocoes"]), set(EMOCOES))
        self.assertFalse(L.Cliente("http://127.0.0.1:1").no_ar())

    def test_eventos_primeira_chamada_e_incrementais(self):
        evs, ultimo, atual = self.c.eventos(None)
        self.assertEqual(evs, [])
        self.assertIn("nome", atual)
        self.c.definir("vitoria")
        evs, ultimo2, atual = self.c.eventos(ultimo)
        self.assertEqual([e["nome"] for e in evs if e["tipo"] == "emocao"], ["vitoria"])
        self.assertGreater(ultimo2, ultimo)
        self.assertEqual(atual["nome"], "vitoria")

    def test_toque_ritmo_dormir_acordar(self):
        _, u, _ = self.c.eventos(None)
        self.c.toque()
        self.assertTrue(self.c.eventos(u)[0])
        self.assertEqual(self.c.ritmo(1)["atual"]["ritmo"], 1.0)
        self.assertEqual(self.c.dormir()["atual"]["nome"], "dormindo")
        self.assertEqual(self.c.acordar()["atual"]["nome"], "espreguicando")

    def test_conversar_le_o_stream_sse(self):
        _, u, _ = self.c.eventos(None)
        evs = list(self.c.conversar("abre o youtube", falar=False, acoes=False))
        nomes = [n for n, _ in evs]
        self.assertEqual(nomes.count("sentence"), 2)
        self.assertEqual(nomes[-1], "fim")
        self.assertEqual([d["emocao"] for n, d in evs if n == "sentence"], ["feliz", "irritada"])
        falas = [e for e in self.c.eventos(u)[0] if e["tipo"] == "fala"]
        self.assertEqual([f["emocao"] for f in falas], ["feliz", "irritada"])
        self.assertTrue(all("<" not in f["texto"] for f in falas))


class GarantirServidor(unittest.TestCase):
    def script(self, corpo):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "fake_server.py")
        with open(p, "w") as f:
            f.write(textwrap.dedent(corpo))
        return p, d

    def test_liga_o_servidor_quando_nao_esta_no_ar(self):
        porta = porta_livre()
        p, d = self.script(f"""
            import json
            from http.server import BaseHTTPRequestHandler, HTTPServer
            class H(BaseHTTPRequestHandler):
                def do_GET(self):
                    b = json.dumps({{"emocoes": {{}}}}).encode()
                    self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b)
                def log_message(self, *a): pass
            HTTPServer(("127.0.0.1", {porta}), H).serve_forever()
        """)
        c = L.Cliente(f"http://127.0.0.1:{porta}")
        proc = L.garantir_servidor(c, p, d, espera=15)
        try:
            self.assertIsNotNone(proc)
            self.assertTrue(c.no_ar())
            self.assertIsNone(L.garantir_servidor(c, p, d), "já no ar: não liga outro")
        finally:
            proc.terminate()

    def test_erro_claro_se_o_servidor_fecha(self):
        p, d = self.script("raise SystemExit(1)")
        with self.assertRaises(RuntimeError):
            L.garantir_servidor(L.Cliente(f"http://127.0.0.1:{porta_livre()}"), p, d, espera=10)


class Fila(unittest.TestCase):
    def test_ritmo_minimo_entre_expressoes(self):
        f = L.FilaExpressao()
        f.push({"tipo": "fala", "texto": "a", "emocao": "feliz", "dur": 3})
        f.push({"tipo": "fala", "texto": "b", "emocao": "irritada", "dur": 2})
        f.push({"tipo": "aviso", "texto": "ignorado"})
        self.assertEqual(f.proximo(0)["emocao"], "feliz")
        self.assertIsNone(f.proximo(2.9))
        self.assertEqual(f.proximo(3.0)["emocao"], "irritada")
        self.assertIsNone(f.proximo(100))

    def test_fala_curta_dura_pelo_menos_1s2_e_longa_no_maximo_6s(self):
        f = L.FilaExpressao()
        f.push({"tipo": "fala", "dur": 0.1})
        f.proximo(0)
        self.assertAlmostEqual(f.ocupado_ate, 1.2)
        f.push({"tipo": "fala", "dur": 30})
        f.proximo(2)
        self.assertAlmostEqual(f.ocupado_ate, 8.0)

    def test_emocao_solta_ocupa_pouco(self):
        f = L.FilaExpressao()
        f.push({"tipo": "emocao", "nome": "feliz"})
        f.proximo(0)
        self.assertAlmostEqual(f.ocupado_ate, 0.6)

    def test_descarta_o_excesso_mantendo_o_mais_recente(self):
        f = L.FilaExpressao(maximo=3)
        for i in range(10):
            f.push({"tipo": "emocao", "nome": str(i)})
        self.assertEqual([e["nome"] for e in f.itens], ["7", "8", "9"])


class Balao(unittest.TestCase):
    medir = staticmethod(lambda s: len(s) * 7)

    def test_quebra_em_linhas_que_cabem(self):
        linhas = L.quebrar("uma frase um pouco mais comprida para quebrar em linhas", 140, self.medir)
        self.assertGreater(len(linhas), 1)
        self.assertTrue(all(self.medir(x) <= 140 for x in linhas))
        self.assertEqual(" ".join(linhas), "uma frase um pouco mais comprida para quebrar em linhas")

    def test_limita_linhas_com_reticencias(self):
        linhas = L.quebrar("palavra " * 60, 140, self.medir, max_linhas=3)
        self.assertEqual(len(linhas), 3)
        self.assertTrue(linhas[-1].endswith("…"))
        self.assertTrue(all(self.medir(x) <= 140 for x in linhas))

    def test_palavra_gigante_nao_trava(self):
        self.assertEqual(L.quebrar("x" * 100, 50, self.medir), ["x" * 100])

    def test_alpha_entra_e_sai(self):
        b = L.Balao()
        self.assertEqual(b.alpha(0), 0)
        b.mostrar("oi", 3, 10.0)
        self.assertAlmostEqual(b.alpha(10.0), 0.0)
        self.assertEqual(b.alpha(11.0), 1.0)
        self.assertLess(b.alpha(12.8), 0.5)
        self.assertEqual(b.alpha(13.5), 0.0)
        self.assertFalse(b.visivel(13.5))
        b.mostrar("de novo", 3, 20)
        b.fechar()
        self.assertFalse(b.visivel(20.5))


class Movimento(unittest.TestCase):
    def test_todo_movimento_do_catalogo_existe_e_fica_limitado(self):
        for mov in MOVIMENTOS:
            for i in range(0, 600):
                dx, dy, sx, sy, rot = L.transformar(mov, i / 30)
                for v in (dx, dy, sx, sy, rot):
                    self.assertTrue(math.isfinite(v), mov)
                self.assertLess(abs(dx), 0.05, mov)
                self.assertTrue(-0.2 < dy < 0.06, mov)
                self.assertTrue(0.9 < sx < 1.1 and 0.9 < sy < 1.12, mov)
                self.assertLess(abs(rot), 6, mov)

    def test_desconhecido_nao_mexe(self):
        self.assertEqual(L.transformar("nada", 1.0), (0, 0, 1, 1, 0))

    def test_continuo_sem_saltos(self):
        for mov in MOVIMENTOS:
            ant = L.transformar(mov, 0)
            for i in range(1, 300):
                atual = L.transformar(mov, i / 60)
                passo = max(abs(a - b) for a, b in zip(atual[:4], ant[:4]))
                self.assertLess(passo, 0.05, mov)
                ant = atual

    def test_pular_sobe_e_volta(self):
        ys = [L.transformar("pular", i / 100)[1] for i in range(60)]
        self.assertLess(min(ys), -0.12)
        self.assertGreater(max(ys), -0.01)


class Particulas(unittest.TestCase):
    def test_solta_sobe_e_some(self):
        p = L.Particulas(random.Random(1))
        p.configurar(["♥"], 0)
        p.atualizar(0.3)
        self.assertEqual(len(p.lista), 1)
        d0 = p.desenho(0.3)[0]
        d1 = p.desenho(1.4)[0]
        self.assertEqual(d0[0], "♥")
        self.assertLess(d1[2], d0[2], "sobe")
        self.assertGreater(d1[3], d0[3], "vai ficando visível")
        p.atualizar(0.3 + L.Particulas.VIDA + 0.1)
        self.assertTrue(all(x[1] > 0.3 for x in p.lista))

    def test_sem_particulas_nao_solta(self):
        p = L.Particulas(random.Random(1))
        p.configurar([], 0)
        for t in range(50):
            p.atualizar(t)
        self.assertEqual(p.lista, [])

    def test_alpha_sempre_entre_0_e_1(self):
        p = L.Particulas(random.Random(2))
        p.configurar(["✨"], 0)
        for i in range(400):
            p.atualizar(i * 0.05)
            for _, _, _, a, e in p.desenho(i * 0.05):
                self.assertTrue(0 <= a <= 1 and e > 0)


class Pop(unittest.TestCase):
    def test_comeca_esticada_passa_do_ponto_e_assenta(self):
        self.assertEqual(L.pop(1.0), (1.0, 1.0))
        self.assertEqual(L.pop(5), (1.0, 1.0))
        sx0, sy0 = L.pop(0)
        self.assertLess(sx0, 1)
        self.assertGreater(sy0, 1)
        sx1, sy1 = L.pop(0.55)
        self.assertGreater(sx1, 1)
        self.assertLess(sy1, 1)
        for i in range(101):
            sx, sy = L.pop(i / 100)
            self.assertTrue(0.85 < sx < 1.1 and 0.9 < sy < 1.1)


class Fisica(unittest.TestCase):
    def test_cai_quica_e_para(self):
        f = L.Fisica()
        y, chao, t, toques = 100.0, 800.0, 0.0, 0
        f.soltar()
        while f.caindo and t < 10:
            y, tocou, imp = f.passo(y, chao, 1 / 60)
            toques += tocou
            t += 1 / 60
            self.assertLessEqual(y, chao)
        self.assertFalse(f.caindo, "termina de cair")
        self.assertEqual(y, chao)
        self.assertGreaterEqual(toques, 1)
        self.assertLess(t, 5)

    def test_parada_nao_move(self):
        f = L.Fisica()
        self.assertEqual(f.passo(50, 800, 0.1), (50, False, 0.0))

    def test_ja_no_chao_nao_quica_para_sempre(self):
        f = L.Fisica()
        f.soltar()
        y = 799.0
        for _ in range(600):
            y, _, _ = f.passo(y, 800.0, 1 / 60)
        self.assertFalse(f.caindo)


class Passeio(unittest.TestCase):
    def novo(self, seed=1):
        return L.Passeio(random.Random(seed), 0)

    def test_quieta_ou_ocupada_nao_passeia(self):
        for emo in ("dormindo", "sonolenta", "irritada", "timida"):
            p = self.novo()
            self.assertIsNone(p.decidir(1000, emo, True, 500, 0, 1920, 360, 900), emo)
        p = self.novo()
        self.assertIsNone(p.decidir(1000, "feliz", False, 500, 0, 1920, 360, 900), "ocupada")
        p = self.novo()
        self.assertIsNone(p.decidir(1000, "feliz", True, 500, 0, 1920, 360, 900, ativo=False), "desligado")

    def test_espera_o_intervalo(self):
        p = self.novo()
        self.assertIsNone(p.decidir(1, "feliz", True, 500, 0, 1920, 360, 900))

    def test_destino_sempre_dentro_da_tela(self):
        for seed in range(200):
            p = self.novo(seed)
            for x in (0, 10, 700, 1500, 1560):
                s = p.decidir(1000 + seed, "feliz", True, x, 0, 1920, 360, 900)
                p.proximo = 0
                if s:
                    self.assertTrue(0 <= s.x1 <= 1920 - 360, (seed, x, s.x1))
                    self.assertGreaterEqual(abs(s.x1 - s.x0), 40)

    def test_salto_e_parabola_do_inicio_ao_fim(self):
        s = L.Salto(100, 400, 900, 10, 0.8, 60)
        x0, y0, fim0 = s.pos(10)
        xm, ym, _ = s.pos(10.4)
        x1, y1, fim1 = s.pos(11)
        self.assertEqual((x0, y0, fim0), (100, 900, False))
        self.assertAlmostEqual(ym, 840, delta=1)
        self.assertEqual((x1, y1, fim1), (400, 900, True))
        self.assertTrue(100 < xm < 400)

    def test_energica_passeia_mais_que_quieta(self):
        def saltos(emo):
            n = 0
            p = self.novo(3)
            for t in range(0, 3600, 5):
                n += bool(p.decidir(t, emo, True, 800, 0, 1920, 360, 900))
            return n
        self.assertGreater(saltos("feliz"), saltos("neutra"))


class Config(unittest.TestCase):
    def test_ida_e_volta_e_limites(self):
        d = os.path.join(tempfile.mkdtemp(), "pet.json")
        cfg = L.carregar_config(d)
        self.assertEqual(cfg["escala"], 0.7)
        cfg.update(escala=5.0, x=10, y=20, passear=False, lixo="x")
        self.assertTrue(L.salvar_config(cfg, d))
        volta = L.carregar_config(d)
        self.assertEqual((volta["x"], volta["y"], volta["passear"]), (10, 20, False))
        self.assertEqual(volta["escala"], 2.0)
        self.assertNotIn("lixo", volta)

    def test_arquivo_estragado_cai_no_padrao(self):
        d = os.path.join(tempfile.mkdtemp(), "pet.json")
        with open(d, "w") as f:
            f.write("{ isso nao e json")
        self.assertEqual(L.carregar_config(d)["escala"], 0.7)


class LayoutTeste(unittest.TestCase):
    def test_cresce_com_a_escala_e_cabe_o_balao(self):
        a, b = L.layout(0.5), L.layout(1.0)
        self.assertLess(a.sprite_w, b.sprite_w)
        for lay in (a, b):
            self.assertGreaterEqual(lay.janela_w, lay.sprite_w)
            self.assertEqual(lay.janela_h, lay.sprite_h + lay.balao_h + lay.margem)
        self.assertEqual(L.layout(1.0).sprite_w, 320)


if __name__ == "__main__":
    unittest.main()
