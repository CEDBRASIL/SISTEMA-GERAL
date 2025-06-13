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



## Backend WhatsApp (Node + TypeScript)

Este projeto também disponibiliza um pequeno servidor em Node 20 para integração com o WhatsApp via [wppconnect](https://github.com/wppconnect-team/wppconnect).

### Executando localmente

```bash
npm install
npm run dev
```

O servidor escutará em `http://localhost:10000` (ou na porta definida pela variável `PORT`).

### Endpoints

- `GET /qr` – retorna `{ qr, status }` onde `status` é `loading` ou `ready`.
- `POST /send` – corpo `{ numero: string, mensagem: string }`. O `numero` deve seguir o padrão E.164 (ex.: `+5561999998888`).
