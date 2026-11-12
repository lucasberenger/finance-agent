# Assistente financeiro no Telegram

Registre despesas e receitas em português e consulte suas finanças pelo Telegram.
Python 3.12+, FastAPI, Groq e Google Sheets.

## Funcionalidades

- Lançamentos com descrição, valor, categoria/origem e pagamento.
- Datas relativas ou explícitas: “gastei 30 no almoço ontem via pix”.
- `/resumo`: receitas, despesas, resultado e despesas por categoria no mês atual.
- Perguntas específicas: “quanto gastei?”, “quanto recebi?” e “qual o resultado do mês?”.
- Períodos: hoje, ontem, mês atual ou outro mês, como “quanto gastei em outubro de 2026?”.
- “Resumo de outubro de 2026”: consulta completa de outro mês.
- `/ultimos`: cinco lançamentos mais recentes por data financeira; “últimos 10 lançamentos” permite até 20.
- `/desfazer`: cancela o último lançamento novo, pela ordem de registro, preservando a linha na planilha.
- `/ajuda`: exemplos e comandos.

Consultas sem período usam o mês atual e sempre informam o período na resposta.
“Quanto gastei?” retorna somente as despesas; “quanto recebi?” retorna somente as
receitas. Perguntas como “quanto ainda tenho no mês?”, “quanto me resta?” e
“quanto sobrou?” retornam o resultado: receitas menos despesas registradas.
A resposta explicita essa base; ela não representa saldo bancário nem inclui
valores de meses anteriores. Pedidos explícitos de saldo da conta bancária geram
uma explicação da limitação, sem executar esse cálculo como se fosse saldo. `/resumo` continua mostrando a
visão completa mensal. A IA identifica o pedido, mas os filtros, cálculos e frases
de resposta são executados pelo código, sem uma segunda chamada ao modelo.

Exemplo com receita de R$ 3.250,00 e uma despesa ativa de R$ 12,50 no mês:

```text
Você: Quanto gastei?
Bot: Você gastou R$ 12,50 em 11/2026.

Você: Quanto recebi?
Bot: Você recebeu R$ 3.250,00 em 11/2026.
```

Valores numéricos são convertidos no código a partir do trecho original extraído
pela IA, sem depender da conversão numérica do modelo:

| Valor enviado | Valor registrado |
|---|---|
| `3.250` | R$ 3.250,00 |
| `12,50` ou `12,5` | R$ 12,50 |
| `R$ 3.250,90` | R$ 3.250,90 |
| `3250` | R$ 3.250,00 |
| `12.50` | R$ 12,50 |

Ponto com grupos de três dígitos é separador de milhares. Valores malformados,
negativos, zero, mais de duas casas decimais ou sem valor numérico explícito geram
pedido de esclarecimento. Valores por extenso e abreviações como `3k` ainda não são
suportados. Registros antigos não são reescritos; a leitura de valores textuais na
planilha usa a mesma convenção de separadores.

Campos opcionais ausentes ficam como “Não informado”. Mensagens incompletas geram
um pedido de esclarecimento: reenvie a frase completa, pois não há memória de conversa.
Não há ainda comparação entre períodos, filtros por categoria, orçamento, áudio,
parcelas ou recorrências. Consultas por semana ou intervalos arbitrários ainda não
são suportadas. O resultado mensal não é o saldo disponível em contas.

## Configuração

```bash
uv sync
test -f .env || cp .env.example .env
```

Se você já tem um `.env`, preserve-o e adicione apenas as variáveis que faltarem.
Preencha os valores abaixo; não versione o arquivo nem as chaves baixadas:

| Variável | Uso |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token do bot |
| `TELEGRAM_OWNER_ID` | Seu ID numérico de usuário no Telegram |
| `TELEGRAM_WEBHOOK_SECRET` | Segredo exigido pelo servidor para autenticar o encaminhamento local |
| `GROQ_API_KEY` | Credencial da Groq |
| `GROQ_MODEL` | ID de um modelo disponível na sua conta Groq e compatível com respostas JSON |
| `GOOGLE_CLOUD_CREDENTIALS` | JSON da conta de serviço Google, em uma linha |
| `SHEET_ID` | ID da planilha, extraído da URL |
| `STATE_DB_PATH` | Caminho para SQLite em armazenamento persistente |
| `LOG_LEVEL` | Nível dos logs operacionais; padrão `INFO` |

O modelo do `.env.example` também é o padrão do código, mas pode não estar
mais disponível na sua conta. Defina `GROQ_MODEL` explicitamente para o modelo que
você validou; erros de disponibilidade aparecem nos logs da etapa `groq_request`.

Para gerar `TELEGRAM_WEBHOOK_SECRET`, execute `openssl rand -hex 32` e salve o
resultado no `.env`. Use um valor diferente do token do bot.

Compartilhe a planilha com o e-mail da conta de serviço. São necessárias duas abas,
com cabeçalho na primeira linha e estas colunas, nesta ordem:

- **Entrada:** Data, Descrição, Origem, Valor, ID, Proprietário, Criado em, Status.
- **Saída:** Data, Descrição, Categoria, Valor, Pagamento, ID, Proprietário, Criado em, Status.

Datas: `DD/MM/AAAA`. Valores: numéricos ou texto como `1.234,56`.
Os lançamentos novos usam entrada RAW para não executar descrições como fórmulas.

### Planilha existente

Faça uma cópia antes da atualização. Mantenha as colunas originais na ordem acima e
adicione apenas os quatro cabeçalhos de metadados à direita; deixe seus valores antigos vazios.
O código não altera automaticamente o cabeçalho nem reescreve registros antigos.
Linhas antigas são consideradas pertencentes ao único proprietário configurado e
entram nos relatórios, mas não podem ser desfeitas pelo bot. Linhas vazias são ignoradas;
datas ou valores inválidos interrompem a consulta, evitando mostrar totais incompletos.
Registros com Status `void` ficam fora das consultas; não remova nem reutilize os IDs.

## Execução

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

Em outro terminal, confira a inicialização:

```bash
curl --fail http://127.0.0.1:8000/health
```

O retorno esperado é `{"ok":true}`. O processo deve emitir o evento
`application_started` no terminal. Isso confirma a inicialização, mas não valida
as credenciais nem a disponibilidade das integrações externas.

### Recebimento de mensagens no teste local

O fluxo validado atualmente usa **long polling**: um script auxiliar consulta
`getUpdates` no Telegram e encaminha as mensagens ao servidor em
`http://127.0.0.1:8000`. O servidor interpreta a mensagem, executa a ação e envia a
resposta pela API do Telegram.

O auxiliar temporário está em `app/polling.py`. Com o servidor já iniciado,
execute em outro terminal, na raiz do projeto:

```bash
uv run python -m app.polling
```

Para outra porta local, use `--server-url http://127.0.0.1:8001`.
O módulo carrega o `.env` do projeto, usa os logs operacionais e verifica a saúde
do servidor antes de começar. Iniciar apenas o Uvicorn não inicia o recebimento
de mensagens do bot. Os dois processos precisam permanecer rodando; encerre o
polling com `Ctrl+C`. Execute apenas um receptor de mensagens por bot.

Em falhas transitórias, ele aguarda cinco segundos antes de tentar novamente,
sem confirmar a mensagem que falhou. Erros de autenticação ou conflito de receptor
interrompem a execução. Uma configuração de recebimento externo já ativa também
impede a inicialização; o auxiliar não altera essa configuração automaticamente.
Este polling é temporário e será substituído pelo webhook público no futuro.

Com os dois processos ativos, envie `/ajuda`, registre um gasto de teste e consulte
`/ultimos` e `/resumo`. Use `/desfazer` para cancelar o gasto; ele permanecerá na
planilha com status `void` e deixará de compor os totais. Esse teste usa a planilha
real configurada no `.env`. Somente mensagens privadas do proprietário são aceitas.

Reinicie o servidor sempre que alterar o `.env` ou o código; o comando acima não
ativa recarga automática.

## Persistência e falhas

Use **um processo e uma réplica**. As operações são serializadas no processo e as
chamadas síncronas rodam fora do event loop. Não há fila distribuída nesta versão.

O SQLite guarda a interpretação, o alvo de desfazer e a resposta por `update_id`
antes/depois da execução. A planilha recebe o mesmo ID, conferido antes de inserir.
Isso permite retomar reentregas sem repetir a mutação, inclusive após uma falha de
resposta da planilha. Guarde o arquivo SQLite em um local preservado entre
reinícios e inclua-o no backup.
Não compartilhe uma planilha entre bots/instâncias independentes.

Se houver falha de integração, o servidor retorna 503. No teste local, o auxiliar
não avança a confirmação da mensagem e tenta encaminhá-la novamente. Se o envio da resposta falhar após o lançamento, a reentrega reutiliza a
resposta salva. Uma confirmação pode aparecer novamente no chat em uma reentrega;
o envio ao Telegram não oferece uma transação conjunta com o armazenamento.
Não apague o SQLite para tentar resolver falhas: ele também protege operações de desfazer.

## Logs operacionais

A aplicação escreve um objeto JSON por linha em stdout. Use `LOG_LEVEL=INFO`
(padrão) para acompanhar a operação; `WARNING` ou `ERROR` reduzem o volume.
Valores aceitos: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.
Não são criados arquivos de log pela aplicação. Configure o nível no `.env`:

```dotenv
LOG_LEVEL=INFO
```

Reinicie o servidor para aplicar a mudança. `DEBUG` usa o mesmo conjunto de
eventos de `INFO` nesta versão; não habilita payloads nem logs dos SDKs.

Cada mensagem autorizada recebe contexto com seu `update_id`, compartilhado entre
as etapas e a thread de processamento. Os eventos mostram:

- Recebimento e conclusão das requisições; rejeições e mensagens ignoradas têm um motivo.
- Ação selecionada, resposta reaproveitada (`update_replayed`) ou operação retomada (`update_resumed`).
- `stage_completed` / `stage_failed` com `stage` e `duration_ms` para interpretação,
  Groq, consultas/gravações no Sheets, diário SQLite, execução e envio ao Telegram.
- Falhas com `error_type` e, quando disponível, código HTTP; saída inválida da IA
  gera `llm_output_invalid` no nível WARNING e pede esclarecimento ao usuário.
- Inicialização e encerramento do processo.

O evento `action_selected` identifica a ação escolhida. As durações ficam nos
eventos `stage_completed` e `stage_failed`. A interpretação de comandos como
`/resumo` é local e não chama a Groq. Reentregas com resposta salva emitem
`update_replayed`, sem executar a ação novamente.

As principais etapas para diagnóstico são:

| `stage` | O que verificar |
|---|---|
| `startup` | Variáveis obrigatórias e acesso ao arquivo SQLite |
| `groq_request` | Autenticação, modelo, limite de requisições ou conexão com a Groq |
| `sheets_connect`, `sheets_read`, `sheets_add`, `sheets_undo` | Credenciais Google, compartilhamento, abas e dados da planilha |
| `journal_read`, `journal_save_action`, `journal_save_response` | Leitura e gravação no diário SQLite |
| `telegram_send` | Envio da resposta ao Telegram |

Exemplo ilustrativo:

```json
{"timestamp":"2026-11-09T15:00:00+00:00","level":"ERROR","event":"stage_failed","update_id":"42","stage":"groq_request","duration_ms":210.5,"error_type":"RateLimitError","status_code":429}
```

Procure o `update_id` para reunir os eventos da mesma mensagem. Uma falha pode
aparecer tanto na etapa específica quanto nas etapas que a envolvem; isso não
representa várias tentativas. Durações externas incluem espera nas etapas internas.
Os logs de rejeição não incluem identificadores fornecidos por usuários não autorizados.

Texto das mensagens, respostas, valores, categorias, credenciais, IDs de usuário e
URLs das APIs não são registrados. O formatador usa campos permitidos e omite
mensagens de exceção e tracebacks. Logs dos clientes HTTP e SDKs são silenciados
para evitar exposição de tokens em URLs ou de payloads, inclusive com LOG_LEVEL=DEBUG.
Os logs próprios do Uvicorn (acessos e ciclo de vida) continuam com seu formato padrão.
A configuração de logs é aplicada no ciclo de inicialização do FastAPI.

## Testes

```bash
uv run python -m unittest discover -s tests -v
```

Os testes usam repositório e chamadas HTTP simulados, SQLite temporário e nenhuma
credencial real. Cobrem validação, precisão monetária, períodos, compatibilidade
com linhas antigas, controle de acesso e retomada de operações após falhas.
Consultas específicas têm testes de métrica, datas, virada de mês/ano, ano bissexto,
períodos sem lançamentos e garantia de não gravar registros financeiros.
Também verificam a correlação dos logs entre tarefas e threads, os eventos de
falha, a configuração sem handlers duplicados e a ausência de dados sensíveis
nos eventos emitidos. Os testes do polling cobrem encaminhamento, confirmação
após sucesso, repetição após falha e restrição ao proprietário. Não é necessário
preencher o `.env` para executar a suíte.

### Avaliação opcional da interpretação real

Os casos em `tests/fixtures/result_intents.json` verificam a distinção entre
“quanto ainda tenho no mês?” (resultado dos registros) e uma consulta explícita
sobre saldo bancário. Para executá-los contra o modelo configurado na Groq:

```bash
RUN_LIVE_EVALS=1 uv run python -m unittest discover -s tests -p test_result_intents_live.py -v
```

Essa avaliação carrega o `.env`, consome a API da Groq e está desativada na suíte
normal. Não acessa a planilha nem envia mensagens ao Telegram. Limites de uso ou
indisponibilidade da API podem causar falhas; repita quando a conta estiver disponível.

Para avaliar os formatos brasileiros com o modelo real, sem gravar lançamentos:

```bash
RUN_LIVE_EVALS=1 uv run python -m unittest discover -s tests -p test_brazilian_amounts_live.py -v
```

Os exemplos ficam em `tests/fixtures/brazilian_amounts.json`. A avaliação exige
credenciais da Groq e está sujeita aos limites de requisições da conta.

## Arquitetura

`Telegram → app.polling → FastAPI local → interpretação validada → ações → Google Sheets`

O servidor envia a confirmação de volta ao Telegram pela API de mensagens.

SQLite mantém o diário de processamento. O cálculo dos relatórios usa `Decimal`;
as consultas leem as abas para agregar os registros em Python.
