// Exemplo de integração no site (frontend)
// Envia os dados do aluno para a API e redireciona para o link de pagamento.

async function gerarLinkPagamento(dadosAluno) {
  const resposta = await fetch('https://api.cedbrasilia.com.br/asaas/checkout', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(dadosAluno)
  });

  if (!resposta.ok) {
    throw new Error('Falha ao gerar cobrança');
  }

  const json = await resposta.json();
  if (json.url) {
    window.location.href = json.url; // redireciona para o pagamento
  }
}

/*
Exemplo de uso:

const dados = {
  nome: 'Maria',
  cpf: '12345678909',
  whatsapp: '(61) 99999-9999',
  valor: 29.9,
  descricao: 'Pacote Office',
  cursos_ids: [130]
};

gerarLinkPagamento(dados);
*/
