"""Visão de tela (python -m unittest testes.test_visao, dentro da pasta IA). Sem Ollama, sem tela de verdade."""
import os
import sys
import time
import types
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from brain import visao as vz  # noqa: E402


def imagem(texto="Erro: arquivo nao encontrado", cor=255):
    im = Image.new("RGB", (900, 200), (cor, cor, cor))
    ImageDraw.Draw(im).text((20, 60), texto, fill=(0, 0, 0), font=ImageFont.load_default(size=40))
    return im


def fabrica(ocr="linha de texto da tela", janela="Visual Studio Code", modo="texto", img=None):
    v = vz.Visao(modo=modo)
    v.chamadas = {"ocr": 0, "modelo": 0}

    def ler(_):
        v.chamadas["ocr"] += 1
        if isinstance(ocr, Exception):
            raise ocr
        return ocr

    v._capturar = lambda: img or imagem()
    v._janela = lambda: janela
    v._ocr, v.ocr_nome = ler, "falso"
    return v


class Pedido(unittest.TestCase):
    def test_pede_para_ver(self):
        for f in ("olha minha tela", "Alice, dá uma olhada na tela", "o que tem na tela?", "o que você tá vendo?",
                  "o que você vê?", "lê a tela pra mim", "tá vendo isso?", "olha isso aqui", "lê esse erro aqui",
                  "me mostra o que tem na tela", "analisa a minha tela"):
            self.assertTrue(vz.pediu_para_ver(f), f)

    def test_nao_pede(self):
        for f in ("oi", "abre o youtube", "tira um print da tela", "tira print do que tem na tela",
                  "mostra o clima na tela", "deixa um recado na tela", "como você está?", "que horas são",
                  "me lembra de beber água", "pesquisa receita de bolo"):
            self.assertFalse(vz.pediu_para_ver(f), f)


class Limpeza(unittest.TestCase):
    def test_tira_ruido_duplicado_e_tags(self):
        t = vz.limpar_texto("ok\n  Arquivo   salvo  \nArquivo salvo\n..\n<acao:abrir_youtube> oi tudo", 500)
        self.assertEqual(t.count("Arquivo salvo"), 1)
        self.assertNotIn("<", t)
        self.assertNotIn("..", t)

    def test_orcamento_prefere_linhas_longas_e_mantem_ordem(self):
        longa1, longa2 = "a" * 60 + " primeira", "b" * 60 + " segunda"
        t = vz.limpar_texto(f"Menu\n{longa1}\nBotao\n{longa2}\nFim", 145)
        self.assertLessEqual(len(t), 145)
        self.assertLess(t.index("primeira"), t.index("segunda"))
        self.assertNotIn("Menu", t)

    def test_linha_gigante_unica(self):
        self.assertEqual(len(vz.limpar_texto("x" * 5000 + " fim", 300)), 300)


class Contexto(unittest.TestCase):
    def test_sem_pedido_nao_olha_a_tela(self):
        v = fabrica()
        self.assertEqual(v.contexto_para("oi, tudo bem?"), "")
        self.assertEqual(v.chamadas["ocr"], 0)

    def test_pedido_traz_janela_e_texto(self):
        v = fabrica()
        c = v.contexto_para("olha minha tela")
        self.assertIn("NA TELA AGORA", c)
        self.assertIn("Visual Studio Code", c)
        self.assertIn("linha de texto da tela", c)
        self.assertIn("DADOS", c)

    def test_desligada_avisa_em_vez_de_deixar_inventar(self):
        v = fabrica(modo="0")
        c = v.contexto_para("o que tem na tela?")
        self.assertIn("DESLIGADA", c)
        self.assertEqual(v.chamadas["ocr"], 0)
        self.assertEqual(fabrica(modo="0").contexto_para("oi"), "")

    def test_janela_sensivel_nao_e_lida(self):
        v = fabrica(janela="Bitwarden - Cofre")
        c = v.contexto_para("olha minha tela")
        self.assertIn("NÃO olhou", c)
        self.assertEqual(v.chamadas["ocr"], 0)

    def test_sem_leitor_de_texto_diz_que_nao_viu(self):
        c = fabrica(ocr=RuntimeError("Nenhum leitor")).contexto_para("olha a tela")
        self.assertIn("NÃO conseguiu ver", c)

    def test_falha_na_captura(self):
        v = fabrica()
        v._capturar = lambda: (_ for _ in ()).throw(OSError("sem display"))
        self.assertIn("NÃO conseguiu ver", v.contexto_para("olha a tela"))

    def test_cache_nao_repete_ocr_na_mesma_tela(self):
        v = fabrica()
        v.ver("a")
        v.ver("a")
        self.assertEqual(v.chamadas["ocr"], 1)
        v._capturar = lambda: imagem("Outra tela totalmente diferente", 0)
        v.ver("a")
        self.assertEqual(v.chamadas["ocr"], 2)

    def test_seguimento_reusa_a_ultima_captura(self):
        v = fabrica()
        v.contexto_para("olha minha tela")
        c = v.contexto_para("e esse erro aí, o que é?")
        self.assertIn("linha de texto da tela", c)
        self.assertEqual(v.chamadas["ocr"], 1)
        v._ultimo = (time.time() - 500, v._ultimo[1])  # expirou
        self.assertEqual(v.contexto_para("e esse erro aí?"), "")


class ModoModelo(unittest.TestCase):
    def test_descricao_entra_e_o_modelo_recebe_imagem_pequena(self):
        recebido = {}

        def chat(**k):
            recebido.update(k)
            return {"message": {"content": "<think>x</think>Um editor de código com um erro."}}

        sys.modules["ollama"] = types.SimpleNamespace(chat=chat)
        try:
            v = fabrica(modo="modelo", img=Image.new("RGB", (3000, 2000), "white"))
            v.opcoes = {"num_gpu": 0}
            v._descrever = v._descrever_ollama
            c = v.contexto_para("olha minha tela")
        finally:
            del sys.modules["ollama"]
        self.assertIn("Um editor de código com um erro.", c)
        self.assertNotIn("think", c)
        self.assertEqual(recebido["keep_alive"], 0)               # libera a RAM logo depois
        self.assertEqual(recebido["options"]["num_gpu"], 0)       # continua só na CPU
        self.assertEqual(len(recebido["messages"][0]["images"]), 1)

    def test_se_o_modelo_falha_cai_para_o_ocr(self):
        v = fabrica(modo="modelo")
        v._descrever = lambda *a: (_ for _ in ()).throw(RuntimeError("model not found"))
        c = v.contexto_para("olha minha tela")
        self.assertIn("linha de texto da tela", c)
        self.assertIn("NA TELA AGORA", c)


@unittest.skipUnless(__import__("shutil").which("tesseract") and __import__("importlib").util.find_spec("pytesseract"),
                     "Tesseract não instalado")
class OcrDeVerdade(unittest.TestCase):
    def test_tesseract_le_a_imagem(self):
        v = vz.Visao(modo="texto")
        os.environ["ALICE_OCR"] = "tesseract"
        try:
            v._capturar = lambda: imagem("Erro: arquivo nao encontrado")
            v._janela = lambda: "Terminal"
            r = v.ver()
        finally:
            del os.environ["ALICE_OCR"]
        self.assertTrue(r["ok"], r)
        self.assertIn("arquivo", r["ocr"].lower())


class ComOCerebro(unittest.TestCase):
    def test_think_injeta_a_tela_no_prompt_so_quando_pedido(self):
        os.environ["ALICE_DADOS"] = __import__("tempfile").mkdtemp()
        sistemas = []

        def chat(**k):
            sistemas.append(k["messages"][0]["content"])
            return iter([{"message": {"content": "Vi sim."}}])

        sys.modules["ollama"] = types.SimpleNamespace(chat=chat)
        try:
            for m in [m for m in sys.modules if m.startswith("brain.actions")]:
                del sys.modules[m]
            from brain.actions import Think
            from brain.personality import Personality

            t = Think(Personality())
            t.visao = fabrica()
            list(t.stream("oi"))
            list(t.stream("olha minha tela"))
        finally:
            del sys.modules["ollama"]
        self.assertNotIn("Texto lido na tela", sistemas[0])
        self.assertIn("Texto lido na tela", sistemas[1])
        self.assertIn("linha de texto da tela", sistemas[1])


if __name__ == "__main__":
    unittest.main()
