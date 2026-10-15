"""Testes do motor de emoções (python -m unittest testes.test_emocoes, dentro da pasta IA)."""
import os
import random
import sys
import unittest
from collections import Counter
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from brain import emocoes as E  # noqa: E402
from brain.personality import Personality  # noqa: E402

PASTA_PET = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "pet")


class Relogio:
    def __init__(self, hora=14):
        self.t = datetime(2026, 10, 13, hora, 0, 0).timestamp()

    def __call__(self):
        return self.t

    def passa(self, s):
        self.t += s


def novo(seed=1, hora=14, p=None, ritmo=1.0):
    r = Relogio(hora)
    return E.Emocoes(p or Personality(), agora=r, rng=random.Random(seed), ritmo=ritmo), r


def simular(e, r, segundos, passo=0.5):
    """Avança o relógio e devolve os eventos de emoção gerados."""
    _, ultimo = e.eventos(0)
    for _ in range(int(segundos / passo)):
        r.passa(passo)
        e.tick()
    evs, _ = e.eventos(ultimo)
    return [x for x in evs if x["tipo"] == "emocao"]


class Catalogo(unittest.TestCase):
    def test_sprites_existem(self):
        for nome, c in E.EMOCOES.items():
            self.assertTrue(os.path.exists(os.path.join(PASTA_PET, c["sprite"] + ".png")), nome)

    def test_movimentos_validos(self):
        for nome, c in E.EMOCOES.items():
            self.assertIn(c["mov"], E.MOVIMENTOS, nome)

    def test_grafo_consistente(self):
        for de, alvos in E.VIZINHAS.items():
            self.assertIn(de, E.EMOCOES)
            for a in alvos:
                self.assertIn(a, E.EMOCOES)
        for a in E.ALIAS.values():
            self.assertIn(a, E.EMOCOES)

    def test_mais_emocoes_que_antes(self):
        self.assertGreaterEqual(len(E.EMOCOES), 15)

    def test_normalizar(self):
        self.assertEqual(E.normalizar_nome("Animada"), "feliz")
        self.assertEqual(E.normalizar_nome("TÍMIDA"), "timida")
        self.assertEqual(E.normalizar_nome("excited"), "feliz")
        self.assertIsNone(E.normalizar_nome("inventada"))
        self.assertIsNone(E.normalizar_nome(None))


class Reacoes(unittest.TestCase):
    def frequencias(self, texto, n=300):
        c = Counter()
        for s in range(n):
            e, _ = novo(s)
            c[e.on_usuario(texto)] += 1
        return c

    def test_saudacao_deixa_animada(self):
        c = self.frequencias("oi, tudo bem?")
        self.assertGreater((c["feliz"] + c["brincalhona"] + c["timida"]) / 300, 0.95)

    def test_xingamento_irrita(self):
        c = self.frequencias("você é uma inútil")
        self.assertGreater(c["irritada"] / 300, 0.55)

    def test_elogio_deixa_timida_ou_apaixonada(self):
        c = self.frequencias("você é linda")
        self.assertGreater((c["timida"] + c["apaixonada"]) / 300, 0.7)

    def test_agradecimento(self):
        c = self.frequencias("valeu!")
        self.assertGreater((c["timida"] + c["feliz"]) / 300, 0.8)

    def test_comando_vira_ideia(self):
        c = self.frequencias("abre o youtube pra mim")
        self.assertGreater(c["ideia"] / 300, 0.4)

    def test_boa_noite_sonolenta(self):
        c = self.frequencias("boa noite, vou dormir")
        self.assertGreater(c["sonolenta"] / 300, 0.6)

    def test_publica_evento(self):
        e, _ = novo()
        e.on_usuario("te odeio")
        evs, ultimo = e.eventos(0)
        self.assertEqual(evs[-1]["tipo"], "emocao")
        self.assertEqual(evs[-1]["fonte"], "usuario")
        self.assertEqual(ultimo, evs[-1]["id"])

    def test_traits_inclinam_reacao(self):
        manso, seco = Personality(), Personality()
        manso.traits["carinho"] = 10
        c1 = Counter(novo(s, p=manso)[0].on_usuario("você é linda") for s in range(300))
        c0 = Counter(novo(s)[0].on_usuario("você é linda") for s in range(300))
        self.assertGreater(c1["apaixonada"], c0["apaixonada"])


class Frases(unittest.TestCase):
    def setUp(self):
        self.e, self.r = novo()

    def test_tag_do_modelo_vence(self):
        self.assertEqual(self.e.escolher_frase("Bom dia", tag="irritada"), "irritada")
        self.assertEqual(self.e.escolher_frase("Qualquer coisa", tag="Animada"), "feliz")

    def test_tag_invalida_cai_na_heuristica(self):
        self.assertEqual(self.e.escolher_frase("Consegui! Pronto.", tag="xyz"), "vitoria")

    def test_palavras_da_frase(self):
        casos = {
            "kkkk boa essa": "brincalhona", "Desculpa, foi mal": "timida", "Que tal assim?": "ideia",
            "Não entendi nada": "confusa", "Que sono, viu": "sonolenta", "Amo esse nome": "apaixonada",
            "Para com isso, chega": "irritada", "Tanto faz": "entediada", "Sinto muito mesmo": "choramingando",
            "Duvido muito, hmm": "desconfiada", "Oba, legal!": "feliz",
        }
        for frase, esperado in casos.items():
            self.assertEqual(self.e.escolher_frase(frase), esperado, frase)

    def test_sem_pista_mantem_mas_respostas_longas_variam(self):
        e, _ = novo(7)
        vistos = {e.escolher_frase("Aqui está o resultado da conta.") for _ in range(12)}
        self.assertGreaterEqual(len(vistos), 2)  # a partir da 2ª frase aparece variação

    def test_emitir_fala_publica_e_ocupa(self):
        self.e.emitir_fala("Oi, tudo bem com você hoje?", "feliz")
        evs, _ = self.e.eventos(0)
        f = evs[-1]
        self.assertEqual((f["tipo"], f["emocao"]), ("fala", "feliz"))
        self.assertGreater(f["dur"], 1.8)
        self.assertGreater(self.e.ocupado_ate, self.r())
        self.assertEqual(self.e.atual, "feliz")

    def test_nao_troca_sozinha_enquanto_fala(self):
        self.e.emitir_fala("Uma frase bem longa para ela demorar um pouco a falar tudo isso aí.", "feliz")
        antes = self.e.atual
        trocas = simular(self.e, self.r, 3)  # menos que a duração da fala
        self.assertEqual(trocas, [])
        self.assertEqual(self.e.atual, antes)


class Ociosidade(unittest.TestCase):
    def test_muda_com_frequencia_e_variedade(self):
        e, r = novo(3)
        evs = simular(e, r, 90)
        self.assertGreaterEqual(len(evs), 5, "troca de expressão pelo menos a cada ~15 s")
        self.assertGreaterEqual(len({x["nome"] for x in evs}), 4)

    def test_nunca_repete_a_mesma_em_eventos_seguidos(self):
        e, r = novo(5)
        evs = simular(e, r, 600)
        nomes = [x["nome"] for x in evs]
        for a, b in zip(nomes, nomes[1:]):
            self.assertNotEqual(a, b)

    def test_transicoes_sao_vizinhas_ou_do_acaso_controlado(self):
        """Pelo menos 70% das trocas seguem o grafo de vizinhança (continuidade natural)."""
        seguem = total = 0
        for s in range(20):
            e, r = novo(s)
            nomes = ["neutra"] + [x["nome"] for x in simular(e, r, 80)]
            for a, b in zip(nomes, nomes[1:]):
                total += 1
                seguem += b in E.VIZINHAS.get(a, {})
        self.assertGreater(seguem / total, 0.7)

    def test_escada_do_sono(self):
        e, r = novo(2)
        evs = simular(e, r, 15 * 60)
        nomes = [x["nome"] for x in evs]
        self.assertIn("espreguicando", nomes)
        self.assertIn("sonolenta", nomes)
        self.assertEqual(nomes[-1], "dormindo")
        self.assertLess(nomes.index("espreguicando"), nomes.index("dormindo"))
        i = nomes.index("dormindo")
        self.assertEqual(i, len(nomes) - 1, "depois de dormir ela não muda mais sozinha")

    def test_bocejo_dura_antes_de_ficar_sonolenta(self):
        e, r = novo(2)
        evs = simular(e, r, 8 * 60)
        for a, b in zip(evs, evs[1:]):
            if a["nome"] == "espreguicando":
                self.assertGreaterEqual(b["t"] - a["t"], 3.0, "o bocejo precisa aparecer na tela")

    def test_sem_motivo_quase_nunca_irrita(self):
        irritadas = total = 0
        for s in range(30):
            e, r = novo(s)
            for x in simular(e, r, 90):
                total += 1
                irritadas += x["nome"] == "irritada"
        self.assertLess(irritadas / total, 0.04)

    def test_demora_para_dormir_de_dia(self):
        e, r = novo(2, hora=14)
        evs = simular(e, r, 9 * 60)
        self.assertNotIn("dormindo", [x["nome"] for x in evs])

    def test_de_madrugada_dorme_mais_cedo(self):
        e, r = novo(2, hora=2)
        evs = simular(e, r, 7 * 60)
        self.assertIn("dormindo", [x["nome"] for x in evs])

    def test_acorda_espreguicando_e_depois_reage(self):
        e, r = novo(2)
        simular(e, r, 15 * 60)
        self.assertEqual(e.atual, "dormindo")
        _, ult = e.eventos(0)
        e.on_usuario("oi")
        evs, _ = e.eventos(ult)
        self.assertEqual(evs[0]["nome"], "espreguicando")
        self.assertEqual(e.atual, "espreguicando")
        trocas = simular(e, r, 4)
        self.assertTrue(trocas and trocas[0]["fonte"] == "usuario")
        self.assertIn(trocas[0]["nome"], ("feliz", "brincalhona", "timida"))

    def test_primeira_conversa_do_dia_espreguica(self):
        e, r = novo(1, hora=8)
        r.passa(10 * 3600)
        e.on_usuario("bom dia")
        evs, _ = e.eventos(0)
        self.assertEqual(evs[-1]["nome"], "espreguicando")

    def test_modo_foco_nao_muda_sozinha(self):
        e, r = novo(1, ritmo=0)
        self.assertEqual(simular(e, r, 300), [])

    def test_ritmo_calmo_troca_menos(self):
        a, ra = novo(4, ritmo=1.0)
        b, rb = novo(4, ritmo=2.0)
        self.assertGreater(len(simular(a, ra, 120)), len(simular(b, rb, 120)))

    def test_energia_alta_fica_mais_feliz_que_energia_baixa(self):
        def freq(energia):
            p = Personality()
            p.traits["energia"] = energia
            c = Counter()
            for s in range(15):
                e, r = novo(s, p=p)
                for x in simular(e, r, 85):
                    c[x["nome"]] += 1
            return (c["feliz"] + c["brincalhona"] + c["vitoria"]) / max(1, sum(c.values()))
        self.assertGreater(freq(9), freq(1))

    def test_humor_irritado_aparece_mais(self):
        p = Personality()
        p.state = "irritated"
        p.traits["paciencia"] = 1
        c = Counter()
        for s in range(15):
            e, r = novo(s, p=p)
            for x in simular(e, r, 85):
                c[x["nome"]] += 1
        base = Counter()
        for s in range(15):
            e, r = novo(s)
            for x in simular(e, r, 85):
                base[x["nome"]] += 1
        self.assertGreater(c["irritada"], base["irritada"] * 2)


class Ouvindo(unittest.TestCase):
    def test_microfone_aberto_deixa_atenta_e_nao_troca_sozinha(self):
        e, r = novo(1)
        e.ouvindo(True)
        self.assertEqual(e.atual, "ouvindo")
        self.assertEqual(simular(e, r, 60), [], "enquanto ouve, nada de trocar de cara")
        self.assertEqual(e.atual, "ouvindo")

    def test_acorda_na_hora_sem_espreguicar(self):
        e, r = novo(2)
        simular(e, r, 15 * 60)
        self.assertEqual(e.atual, "dormindo")
        e.ouvindo(True)
        self.assertEqual(e.atual, "ouvindo")
        self.assertEqual(e.fila, [])

    def test_fechou_e_entendeu_deixa_a_reacao_para_on_usuario(self):
        e, r = novo(1)
        e.ouvindo(True)
        e.ouvindo(False, entendeu=True)
        self.assertEqual(e.ocupado_ate, 0.0)
        e.on_usuario("oi alice")
        self.assertIn(e.atual, ("feliz", "brincalhona", "timida"))

    def test_fechou_sem_entender_fica_confusa(self):
        e, r = novo(1)
        e.ouvindo(True)
        e.ouvindo(False, entendeu=False)
        simular(e, r, 1)
        self.assertEqual(e.atual, "confusa")

    def test_fechar_sem_ter_aberto_nao_faz_nada(self):
        e, r = novo(1)
        _, u = e.eventos(0)
        e.definir("feliz")
        e.ouvindo(False, entendeu=False)
        self.assertEqual(e.atual, "feliz")

    def test_nunca_aparece_no_sorteio_nem_em_frases(self):
        e, r = novo(3)
        nomes = {x["nome"] for x in simular(e, r, 600)}
        self.assertNotIn("ouvindo", nomes)
        self.assertNotEqual(e.escolher_frase("oi", tag="ouvindo"), "ouvindo")
        self.assertEqual(E.normalizar_nome("escutando"), "ouvindo")

    def test_humor_para_o_prompt(self):
        e, _ = novo()
        e.ouvindo(True)
        self.assertIn("Ouvindo", e.humor_para_prompt())


class Eventos(unittest.TestCase):
    def test_cutucao_escala_para_irritacao(self):
        def ultimo(n, seed):
            e, r = novo(seed)
            for _ in range(n):
                e.on_toque()
                r.passa(1)
            return e.atual
        um = Counter(ultimo(1, s) for s in range(200))
        quatro = Counter(ultimo(4, s) for s in range(200))
        self.assertLess(um["irritada"] / 200, 0.05)
        self.assertGreater(quatro["irritada"] / 200, 0.55)

    def test_toque_forca_evento_mesmo_se_igual(self):
        e, r = novo(1)
        e.on_toque()
        n1 = len(e.eventos(0)[0])
        e.on_toque()
        self.assertGreater(len(e.eventos(0)[0]), n1)

    def test_aviso(self):
        e, _ = novo()
        e.on_aviso("Lembrete: beber água")
        evs, _ = e.eventos(0)
        self.assertEqual([x["tipo"] for x in evs], ["emocao", "aviso"])
        self.assertEqual(e.atual, "ideia")
        self.assertIn("beber", evs[-1]["texto"])

    def test_aviso_acorda_quem_dorme(self):
        e, r = novo(2)
        simular(e, r, 15 * 60)
        e.on_aviso("Lembrete: remédio")
        self.assertEqual(e.atual, "espreguicando")
        simular(e, r, 4)
        self.assertEqual(e.atual, "ideia")

    def test_acao_que_falha_deixa_confusa(self):
        e, r = novo()
        e.on_acao(False)
        simular(e, r, 1)
        self.assertEqual(e.atual, "confusa")

    def test_acao_ok_as_vezes_comemora(self):
        c = Counter()
        for s in range(200):
            e, r = novo(s)
            e.on_acao(True)
            simular(e, r, 1)
            c[e.atual == "vitoria"] += 1
        self.assertTrue(0.2 < c[True] / 200 < 0.5)

    def test_eventos_incrementais(self):
        e, _ = novo()
        e.definir("feliz")
        _, u1 = e.eventos(0)
        e.definir("irritada")
        evs, u2 = e.eventos(u1)
        self.assertEqual([x["nome"] for x in evs], ["irritada"])
        self.assertGreater(u2, u1)
        self.assertEqual(e.eventos(u2)[0], [])

    def test_dormir_e_acordar_manual(self):
        e, r = novo()
        e.dormir()
        self.assertEqual(e.atual, "dormindo")
        e.acordar()
        simular(e, r, 4)
        self.assertEqual(e.atual, "neutra")

    def test_estado_e_catalogo_serializaveis(self):
        import json
        e, _ = novo()
        json.dumps(e.estado())
        json.dumps(E.catalogo())
        self.assertIn("(", e.humor_para_prompt())


if __name__ == "__main__":
    unittest.main()
