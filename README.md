# Assistente financeiro no Telegram

Registre despesas e receitas em português e consulte suas finanças pelo Telegram.
Python 3.12+, FastAPI, Groq e Google Sheets.

## Funcionalidades

- Lançamentos com descrição, valor, categoria/origem e pagamento.
- Datas relativas ou explícitas: “gastei 30 no almoço ontem via pix”.
- `/resumo`: receitas, despesas, resultado e despesas por categoria no mês atual.
- “Resumo de outubro de 2026”: consulta outro mês.
- `/ultimos`: cinco lançamentos mais recentes por data financeira; “últimos 10 lançamentos” permite até 20.
- `/desfazer`: cancela o último lançamento novo, pela ordem de registro, preservando a linha na planilha.
- `/ajuda`: exemplos e comandos.

Campos opcionais ausentes ficam como “Não informado”. Mensagens incompletas geram
um pedido de esclarecimento: reenvie a frase completa, pois não há memória de conversa.
Não há ainda comparação entre períodos, filtros por categoria, orçamento, áudio,
parcelas ou recorrências. O resultado mensal não é o saldo disponível em contas.

## Configuração

```bash
uv sync
cp .env.example .env
```

Preencha `.env`:

| Variável | Uso |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token do bot |
| `TELEGRAM_OWNER_ID` | Seu ID numérico de usuário no Telegram |
| `TELEGRAM_WEBHOOK_SECRET` | Segredo aleatório para autenticar o webhook |
| `GROQ_API_KEY` | Credencial da Groq |
| `GROQ_MODEL` | Modelo compatível com respostas JSON; opcional |
| `GOOGLE_CLOUD_CREDENTIALS` | JSON da conta de serviço Google, em uma linha |
| `SHEET_ID` | ID da planilha, extraído da URL |
| `STATE_DB_PATH` | Caminho para SQLite em armazenamento persistente |

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

Registre o webhook HTTPS usando `setWebhook` da API do Telegram, enviando:

```json
{
  "url": "https://SEU_DOMINIO/telegram/webhook",
  "secret_token": "MESMO_VALOR_DE_TELEGRAM_WEBHOOK_SECRET",
  "allowed_updates": ["message"]
}
```

A chamada usa `POST https://api.telegram.org/bot<TOKEN>/setWebhook`.
Somente mensagens privadas enviadas pelo proprietário são aceitas.
`GET /health` verifica o processo; não testa a disponibilidade das integrações.
O antigo endpoint `/test`, que gravava dados sem autenticação, foi removido.

## Persistência e falhas

Use **um processo e uma réplica**. As operações são serializadas no processo e as
chamadas síncronas rodam fora do event loop. Não há fila distribuída nesta versão.

O SQLite guarda a interpretação, o alvo de desfazer e a resposta por `update_id`
antes/depois da execução. A planilha recebe o mesmo ID, conferido antes de inserir.
Isso permite retomar reentregas sem repetir a mutação, inclusive após uma falha de
resposta da planilha. Guarde o arquivo SQLite em disco persistente (no Render,
configure um disco e aponte `STATE_DB_PATH` para ele) e inclua-o no backup.
Não compartilhe uma planilha entre bots/instâncias independentes.

Se houver falha de integração, o webhook retorna 503 para permitir reentrega pelo
Telegram. Se o envio da resposta falhar após o lançamento, a reentrega reutiliza a
resposta salva. Uma confirmação pode aparecer novamente no chat em uma reentrega;
o envio ao Telegram não oferece uma transação conjunta com o armazenamento.
Não apague o SQLite para tentar resolver falhas: ele também protege operações de desfazer.

## Testes

```bash
uv run python -m unittest discover -s tests -v
```

Os testes usam repositório e chamadas HTTP simulados, SQLite temporário e nenhuma
credencial real. Cobrem validação, precisão monetária, períodos, compatibilidade
com linhas antigas, controle de acesso e retomada de operações após falhas.

## Arquitetura

`Telegram → webhook autenticado → interpretação validada → ações → Google Sheets`

SQLite mantém o diário de processamento. O cálculo dos relatórios usa `Decimal`;
as consultas leem as abas para agregar os registros em Python.
