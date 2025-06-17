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

## Nova rota de assinatura

Para criar uma cobrança recorrente via ASAAS configure `ASAAS_KEY` e utilize:

```bash
POST /asaas/assinatura
{
  "nome": "João da Silva",
  "cpf": "12345678909",
  "whatsapp": "(61) 99999-9999",
  "valor": 59.9,
  "ciclo": "MONTHLY",
  "descricao": "Plano Mensal",
  "cursos_ids": [130]
}
```

O retorno inclui o `subscription` gerado pelo ASAAS e o link para pagamento.

### Assinatura automática após compra na Kiwify

Quando um pedido aprovado é recebido pelo webhook da Kiwify, o aluno é cadastrado
no ASAAS como **assinatura**. A data de vencimento inicial é sempre no mesmo dia
do mês seguinte ao pagamento realizado na Kiwify. O valor da assinatura pode ser enviado no payload ou,
caso não informado, será utilizado o valor definido na variável de ambiente
`ASSINATURA_VALOR_PADRAO` (padrão `0`).

### Checkout único

Envie um JSON para `POST /asaas/checkout` contendo os mesmos campos do exemplo
acima. Por padrão a cobrança é criada com `billingType="UNDEFINED"`, permitindo
que o aluno escolha entre boleto, PIX ou cartão. O link de pagamento também é
enviado automaticamente via WhatsApp.

### Matrícula com geração de fatura

Se preferir disparar a cobrança diretamente a partir do formulário de matrícula,
utilize `POST /asaas/matricula` com os mesmos campos do checkout. O endpoint
gera a fatura no ASAAS e envia o link via WhatsApp para o aluno.

### Regras de matrícula via ASAAS

1. O aluno é sempre cadastrado usando o **CPF informado** na compra.
2. Pagamentos recorrentes não geram nova matrícula quando o CPF já existir na OM.

