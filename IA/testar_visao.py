"""
Testa a visão de tela da Alice no SEU PC, sem Ollama e sem servidor (rode dentro da pasta IA/):

    python testar_visao.py                       olha a tela agora e mostra o que ela leria + os tempos
    python testar_visao.py "o que é esse erro?"  idem, com uma pergunta (ajuda o modo "modelo")
    python testar_visao.py --imagem foto.png     testa o leitor de texto num arquivo, sem capturar a tela
    set ALICE_VISAO=modelo & python testar_visao.py   inclui o modelo de visão (precisa do Ollama no ar)

Dica: troque para a janela que quer testar; o script espera 3 s antes de capturar (use --ja para não esperar).
"""
import sys
import time

from brain.saida import forcar_utf8

forcar_utf8()

from brain.visao import Visao  # noqa: E402

args = sys.argv[1:]
imagem = None
if "--imagem" in args:
    i = args.index("--imagem")
    imagem = args[i + 1]
    del args[i:i + 2]
esperar = "--ja" not in args and imagem is None
pergunta = " ".join(a for a in args if a != "--ja")

v = Visao()
print(f"Modo: {v.modo}" + (f"  (modelo de visão: {v.modelo})" if v.modo == "modelo" else ""))
if imagem:
    from PIL import Image

    v._capturar = lambda: Image.open(imagem).convert("RGB")
    v._janela = lambda: ""
elif esperar:
    print("Capturando em 3 s... troque para a janela que quer testar.")
    time.sleep(3)

t0 = time.time()
r = v.ver(pergunta)
print(f"\nLeitor de texto: {r['ocr_nome'] or v.ocr_nome or 'nenhum'}   tempos (ms): {r['ms']}   total: {time.time() - t0:.1f} s")
print(f"Janela ativa: {r['janela'] or '(desconhecida)'}")
if r["aviso"]:
    print("Aviso:", r["aviso"])
print("\n=== O que vai para a Alice ===")
print(v.formatar(r))
