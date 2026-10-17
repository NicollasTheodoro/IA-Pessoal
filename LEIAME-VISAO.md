# Alice vendo a sua tela

Ela só olha **quando você pede**: "olha minha tela", "o que você tá vendo?", "lê esse erro aqui",
"o que tem na tela?". Em conversa normal não captura nada. Pedidos de print ("tira um print") e do painel
("mostra o clima na tela") continuam sendo as ações de antes.

## Como funciona (pensado para PC fraco)
| Modo | O que ela usa | Custo |
|---|---|---|
| `texto` (**padrão**) | nome da janela ativa + texto da tela lido por OCR, entregue ao qwen2.5:7b | ~0,3 a 2 s de CPU, quase nenhuma RAM extra |
| `modelo` | o de cima + um modelo de visão do Ollama descrevendo a imagem | dezenas de segundos e +2 GB de RAM na CPU |
| `0` | desligado | zero |

Por que OCR e não um modelo de imagem: a GPU interna da CPU quase não acelera o Ollama (por isso o projeto roda
com `num_gpu=0`), e um modelo de visão disputaria RAM com o qwen2.5:7b. O OCR dá o que mais importa numa tela
(texto, erros, código, mensagens). O modo `modelo` serve para o que não é texto (layout, gráficos, fotos, jogos).

## Instalar
```
pip install -r requirements-visao.txt
```
No Windows isso instala o `winocr` (OCR do próprio Windows; precisa do idioma Português (Brasil) instalado em
Configurações > Hora e idioma). Se não funcionar, use `pip install rapidocr-onnxruntime` ou o Tesseract.
Para o modo `modelo`: `ollama pull qwen3-vl:2b` (ou `moondream`, mais leve e mais fraco).

## Usar
```
set ALICE_VISAO=texto        (padrão; use 0 para desligar, modelo para a descrição por imagem)
python IA\server.py          (ou o iniciar_pet.bat)
```
Teste antes, sem Ollama: dentro de `IA`, rode `python testar_visao.py`. Ele espera 3 s (troque de janela), captura
e mostra o que a Alice leria e quanto tempo levou cada etapa. No servidor: `GET /tela/estado`, `POST /tela/ver`,
`POST /tela/modo {"modo":"texto"}` (troca sem reiniciar).

## Ajustes para deixar mais leve
- `ALICE_VISAO_CHARS=800`: menos texto no prompt = resposta mais rápida (cada 4 caracteres ≈ 1 token; a CPU lê o prompt devagar). Padrão 1200.
- `ALICE_VISAO_LADO=640` e `ALICE_VISAO_MODELO=moondream` no modo `modelo`.
- `ALICE_VISAO_KEEP=0` (padrão) descarrega o modelo de visão logo após usar, para liberar RAM. O Ollama pode ter que
  recarregar o qwen2.5:7b depois se a RAM for curta (a fala seguinte demora mais).
- `ALICE_VISAO_MONITOR=2` para olhar outro monitor.

## Privacidade
- A captura fica só na memória: não grava arquivo (diferente de `tirar_print`). Tudo é local (Ollama no seu PC).
- Ela **não olha** se o título da janela ativa tiver algo como KeePass, Bitwarden, "senha", Nubank, Itaú...
  Edite com `ALICE_VISAO_BLOQUEAR=trecho1,trecho2` (substitui a lista padrão).
- O texto da tela entra no prompt marcado como dado: instruções escritas na tela não são obedecidas, e ações
  só rodam se **você** disse algo que combine com elas (a trava `GATILHOS` de sempre).
- Se você acessa a Alice pelo celular (`ALICE_TOKEN`), quem conversar com ela também pode pedir para olhar a tela
  do PC. Não quer isso? `ALICE_VISAO=0`.

## Limites honestos
- Só olha o momento do pedido; "e esse erro?" dito em até 2 minutos reaproveita a última captura.
- OCR erra com letra pequena, fundo estampado e jogos. Vídeos e imagens não são lidos no modo `texto`.
- Não consegui rodar o Windows OCR, o RapidOCR nem o Ollama no ambiente onde escrevi. Testei com leitor e modelo
  simulados, e com o Tesseract de verdade numa imagem. A primeira vez com `winocr` é no seu PC: rode
  `python testar_visao.py` e me diga o que apareceu.

## Testes
Dentro de `IA`: `python -m unittest testes.test_visao`
