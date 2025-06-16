# SISTEMA-GERAL Backend

Este repositório concentra o backend da aplicação do CED Brasília.

## Executando localmente

Instale as dependências e inicie o servidor FastAPI:

```bash
pip install -r requirements.txt
python main.py
```

A API ficará disponível em `http://localhost:8000` (ou na porta definida pela variável `PORT`).

## Principais rotas

- `POST /matricular`: realiza matrícula de alunos.
- `GET  /alunos`: lista todos os alunos da unidade.
- `POST /bloquear/{id_aluno}?status=0|1`: define o bloqueio de um aluno.

Um status `0` equivale a **desbloqueado**, enquanto `1` indica **bloqueado**. Exemplo:

```bash
curl -X POST "https://api.cedbrasilia.com.br/bloquear/123?status=1"
```

## Utilitário de linha de comando

Alguns módulos podem ser executados diretamente. Por exemplo, para alterar o bloqueio de um aluno:

```bash
python bloquear.py 123 0
```

Isso envia a solicitação correspondente à API configurada por meio das variáveis de ambiente `OM_BASE`, `BASIC_B64` e `UNIDADE_ID`.

## Nova rota de cobrança

É possível gerar cobranças usando a integração com o ASAAS. Configure as variáveis `ASAAS_KEY` e `ASAAS_BASE_URL` e utilize a rota:

```bash
POST /cobrar
{
  "customer": "ID do cliente ASAAS",
  "value": 123.45,
  "dueDate": "2025-12-31",
  "billingType": "BOLETO",
  "description": "Cobrança"
}
```

O endpoint retorna o JSON da API do ASAAS ou gera erro em caso de falha.

