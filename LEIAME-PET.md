# Alice, desktop pet

Ela fica na sua tela, por cima das janelas, com as 10 poses do pacote de expressões, e
conversa, reage e muda de cara sozinha. A interface web (navegador) usa as **mesmas** expressões.

## Como ligar
1. Uma vez: `pip install PySide6` (ou clique em `iniciar_pet.bat`, que instala sozinho).
2. `python IA\pet.py`, ou dois cliques em `iniciar_pet.bat`.

Se o servidor (`server.py`) ainda não estiver no ar, o pet liga ele sem janela de console e o
desliga ao sair (só se foi o pet que ligou). Se você já roda o servidor, ele só conecta.
Opções: `--sem-servidor`, `--servidor http://...`, `--escala 1.0`.

> **Aviso honesto:** eu não consegui abrir uma janela Qt nem usar um microfone de verdade no
> ambiente onde escrevi isso. O detector de fala e o fluxo de voz foram testados com microfone e
> Whisper simulados (som sintético: voz, silêncio, ruído, estalo). A lógica
> (emoções, conversa com o servidor, fila de expressões, balão, queda, passeio) tem testes que
> passam, e a janela foi executada com um Qt de mentira, mas **a primeira vez com o PySide6 de
> verdade é no seu PC**. Se algo ficar estranho (transparência, fonte, posição), me diga o que viu.

## Conversar por voz (como uma chamada)
Junto aos pés dela ficam dois botões: **🎤** (falar) e **⌨** (digitar).

1. Clique no 🎤. Ela inclina a cabeça, aparece "🎧 Pode falar…" e um anel pulsa.
2. Fale. O anel acompanha o volume da sua voz.
3. Pare de falar: ela percebe o silêncio sozinha (cerca de 1 s), mostra o que entendeu
   ("🎤 abre o youtube"), responde em voz alta e executa o que você pediu.
4. Para falar de novo, **clique outra vez no 🎤**.

| Se você... | O que acontece |
|---|---|
| clicar no 🎤 enquanto ela ouve | cancela |
| clicar no 🎤 enquanto ela pensa ou fala | cala a Alice na hora e já abre o microfone para você |
| não falar nada por 10 s | "Não ouvi nada. Clique no 🎤 e tente de novo." |
| digitar enquanto o microfone está aberto | cancela a escuta e envia o texto |

**Modo chamada** (menu > 📞, vem desligado): depois que ela termina de responder, o microfone
abre de novo sozinho, e a conversa segue até você clicar no 🎤 para encerrar ou ficar em silêncio
duas vezes seguidas. Use **fone de ouvido** nesse modo: sem fone, o microfone pode captar a voz
dela. No modo normal isso não acontece, porque você só abre o microfone quando ela não está falando.

O microfone e o Whisper são os do `server.py` (os mesmos da "Chamada" da interface web), então
precisa de `pip install faster-whisper sounddevice`, que o projeto já usava. O pet carrega o
Whisper ao abrir, então o primeiro clique não espera.

### Falar com uma tecla (sem usar o mouse)
Botão direito no pet > **⌨ Tecla para falar…**, depois aperte a tecla ou combinação que quiser
(ex.: `F9`, `Ctrl+Alt+Espaço`, `Pause`). Pronto: apertar essa tecla faz **exatamente o mesmo que
clicar no 🎤** (começa a ouvir; apertar de novo cancela; durante a resposta, interrompe e ouve).

- Vale **de qualquer programa**, inclusive com o pet escondido na bandeja (ele aparece ao ouvir).
- Fica salva em `~/.alice_pet.json` (`"tecla": "f9"`). Para tirar: menu > 🚫 Tirar a tecla de falar.
- Só Windows (usa o `RegisterHotKey` do próprio sistema: sem biblioteca extra e sem ficar
  espiando o teclado, só avisa quando a combinação escolhida é apertada).
- Teclas comuns sozinhas (uma letra, Espaço, Enter, setas) são recusadas, porque roubariam
  a tecla do Windows inteiro. Sozinhas valem F1 a F24, Pause, ScrollLock e PrintScreen; as outras
  precisam de Ctrl, Alt, Shift ou Win junto.
- Se outro programa já usa a combinação, ela avisa e continua com a anterior. Escolha outra.

### Como ela percebe que você parou de falar
`IA/audio/vad.py` (usado pelo `listener.py`), com três cuidados:
- **Ruído de fundo**: o limiar acompanha o barulho do ambiente (ventilador, rua). Em sala
  silenciosa fica no valor de sempre (0,01).
- **Estalos**: batida na mesa ou tecla (menos de 0,25 s) são descartados; ela continua esperando
  sua voz em vez de mandar "nada" ao Whisper.
- **Primeira sílaba**: guarda 0,4 s antes da voz, então não corta o começo da frase.

Ajustes em `IA/audio/listener.py`: `silence_time_limit` (quanto silêncio encerra a fala, 1,0 s),
`voz_min`, `auto_limiar`. Para esperar mais antes de desistir: `"espera"` em `~/.alice_pet.json`.

## O que fazer com ela
| Ação | Resultado |
|---|---|
| Botão 🎤 / ⌨ | falar por voz / abrir a caixa de texto (dá para esconder, veja abaixo) |
| Clique nela | cutuca. Uma vez ela é simpática; várias seguidas e ela se irrita |
| Duplo clique nela | abre a caixa de texto (Enter envia, Esc ou clicar fora fecha) |
| Arrastar | muda de lugar; solta no ar e ela cai e quica |
| Botão direito | menu: falar, digitar, calar, expressões, ritmo, dormir/acordar, tamanho, voz alta, modo chamada, olhar, passear, ações do PC, sempre por cima |
| Ícone na bandeja | mostrar, esconder, conversar, sair |

### Esconder os botões 🎤 e ⌨
Menu > **🔘 Botões ao lado dela**: desmarque o 🎤 e/ou o ⌨, ou marque "Só aparecer quando o mouse
estiver perto" (eles surgem quando o mouse chega nela e somem logo depois). Nada se perde: a
tecla de atalho, o menu e o duplo clique nela continuam funcionando. Com o 🎤 oculto ele
reaparece sozinho **enquanto** a conversa por voz está ativa (para você ver que ela está
ouvindo e poder cancelar) e some de novo no fim.

Lembretes aparecem num balão amarelo com os botões **Ok** e **+10 min** (adiar). Ela também vira
o corpo para o lado do mouse (menu > 👀 para desligar) e, quando pula para a direita, olha para a
direita. No menu, **"Executar ações do
PC ao conversar"** vem ligado: o pet é no seu PC, então "pula esse vídeo" ou "abre o youtube"
funcionam direto. Desligue se preferir.

## As emoções (17, antes eram 4)
Como o pacote tem 10 poses, algumas emoções reaproveitam a pose e se diferenciam pelo movimento
e pelas partículas.

| Emoção | Pose | Movimento / extra |
|---|---|---|
| Neutra · Desconfiada | séria | respira · inclina a cabeça |
| Animada · Brincalhona | piscadinha | pula leve ✨ · balança ♪ |
| Vitoriosa | paz e amor | pula 🎉✨ |
| Apaixonada | encantada | balança ♥ |
| Ideia! | apontando | pula leve 💡 |
| Irritada | brava | treme |
| Entediada · Confusa | entediada | respira · inclina ❓ |
| Sonolenta · Dormindo | sonolenta | cochila · cochila 💤 |
| Espreguiçando | bocejo | estica |
| Tímida · Chorosa · Carente | tímida | encolhe · treme leve 💧 · balança ♥ |
| Ouvindo | séria | inclina a cabeça 🎧 (só enquanto o microfone está aberto) |

Para ver todas: menu do pet > Expressões, ou na interface web o painel "Expressões".

## Por que a troca parece natural
- **Reage a você antes de responder**: "oi" anima, elogio deixa tímida ou apaixonada, xingamento
  irrita, comando vira "ideia", "boa noite" dá sono.
- **Uma emoção por frase**: o modelo marca cada frase com `<emo:nome>` (a tag não é falada nem
  aparece). Se ele esquecer, as palavras e a pontuação da frase decidem. Com voz, a expressão
  muda quando a frase **começa a ser falada**.
- **Parada, ela vive**: troca a cada poucos segundos para uma emoção "vizinha" da atual
  (animada vai para brincalhona, não direto para irritada). Os traços do painel (carinho,
  energia, sarcasmo, paciência) e o humor inclinam as escolhas, e ela raramente se irrita sem motivo.
- **Escada do sono**: ~1:40 sem você e vem o tédio; ~4:20 ela espreguiça e boceja; ~10 min dorme
  (metade do tempo de madrugada). Ao falar com ela, acorda espreguiçando e só depois reage.
  A primeira conversa do dia também começa com um espreguiçar.
- **Ritmo**: menu do pet > Ritmo (Parada, Calma, Normal, Animada). Para definir ao ligar o
  servidor: `$env:ALICE_EMO_RITMO="2"` (2 = mais calma, 0.6 = mais agitada, 0 = só reage).

## Onde ajustar
- Tempos, vizinhanças e pesos: `IA/brain/emocoes.py` (`EMOCOES` tem a duração de cada emoção,
  `VIZINHAS` quem vai para quem, `T_TEDIO`/`T_BOCEJO`/`T_SONO`/`T_DORME` a escada do sono).
- O que ela diz em cada humor: exemplos em `IA/brain/prompt_builder.py`.
- Sprites: `IA/static/pet/*.png` (fundo já recortado). Para uma pose nova, ponha o PNG ali e
  aponte `sprite` da emoção em `EMOCOES`; pet e navegador passam a usar.
- Tamanho, passear, posição: salvos em `~/.alice_pet.json`.

## Se algo der errado
- **`'charmap' codec can't encode character '\U0001f3a7'`** (erro do microfone): corrigido. Acontecia
  quando o servidor era ligado sem console e o Python do Windows tentava imprimir um emoji em
  cp1252. Agora a saída é sempre UTF-8 (`IA/brain/saida.py`), no servidor, no pet e no microfone,
  e o servidor que o pet liga já recebe UTF-8. Se ainda ver esse erro, reinicie o servidor
  (o antigo pode estar rodando em segundo plano).
- **A tecla de atalho não faz nada**: outro programa pode estar usando a combinação (o pet avisa
  num balão ao abrir); escolha outra no menu.

## Limites
- 10 poses sem boca animada: a "vida" vem de troca de pose, movimento e partículas.
- Os sprites têm 320 px: em "Enorme" ficam um pouco suaves.
- O qwen2.5:7b às vezes erra a tag `<emo:>` ou esquece; o plano B por palavras cobre, mas pode
  ficar menos preciso (ironia, por exemplo).
- Jogos em tela cheia exclusiva escondem qualquer janela; use o modo janela sem bordas ou
  "Esconder" na bandeja.
- Ela não ouve enquanto fala (no modo normal você abre o microfone depois); interromper é pelo 🎤.
- O reconhecimento é do Whisper no seu PC: em CPU a transcrição leva alguns segundos depois que
  você para de falar (o balão mostra "🧠 Entendendo…"). Se ele ouvir errado, o balão "🎤 ..." mostra
  o que foi entendido antes de ela responder.
- Não existe atalho de teclado global para falar (precisaria de uma biblioteca extra); por ora é
  o botão 🎤 ou o menu da bandeja (Falar 🎤).

## Testes
Dentro da pasta `IA`:
`python -m unittest testes.test_emocoes testes.test_integracao_pet testes.test_pet_logic testes.test_pet_janela testes.test_voz testes.test_hotkey testes.test_saida`
