from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
import os
import requests
import unicodedata
import difflib
from cursos import CURSOS_OM

router = APIRouter()

# Variáveis de ambiente
OM_BASE = os.getenv("OM_BASE")
BASIC_B64 = os.getenv("BASIC_B64")
CHATPRO_TOKEN = os.getenv("CHATPRO_TOKEN")
CHATPRO_URL = os.getenv("CHATPRO_URL")
UNIDADE_ID = os.getenv("UNIDADE_ID")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")

# Token de unidade em memória
TOKEN_UNIDADE: str | None = None


def enviar_log_discord(mensagem: str) -> None:
    if not DISCORD_WEBHOOK:
        print("Discord webhook não configurado")
        return
    try:
        resp = requests.post(DISCORD_WEBHOOK, json={"content": mensagem})
        if resp.status_code != 204:
            print("❌ Falha ao enviar log para Discord:", resp.text)
    except Exception as e:
        print("❌ Erro ao enviar log para Discord:", str(e))


def obter_token_unidade() -> str | None:
    """
    Busca um token de unidade no OM e atualiza a variável global TOKEN_UNIDADE.
    """
    global TOKEN_UNIDADE
    try:
        resp = requests.get(
            f"{OM_BASE}/unidades/token/{UNIDADE_ID}",
            headers={"Authorization": f"Basic {BASIC_B64}"},
        )
        dados = resp.json()
        if resp.ok and dados.get("status") == "true":
            TOKEN_UNIDADE = dados["data"]["token"]
            enviar_log_discord("🔁 Token atualizado com sucesso!")
            return TOKEN_UNIDADE
        enviar_log_discord(f"❌ Erro ao obter token: {dados}")
    except Exception as e:
        enviar_log_discord(f"❌ Exceção ao obter token: {e}")
    return None


def buscar_aluno_por_cpf(cpf: str) -> str | None:
    """
    Retorna o ID do primeiro aluno registrado no OM com o CPF informado.
    """
    try:
        resp = requests.get(
            f"{OM_BASE}/alunos",
            headers={"Authorization": f"Basic {BASIC_B64}"},
            params={"cpf": cpf},
        )
        if not resp.ok:
            enviar_log_discord(f"❌ Falha ao buscar aluno: {resp.text}")
            return None
        alunos = resp.json().get("data", [])
        if not alunos:
            return None
        return alunos[0].get("id")
    except Exception as e:
        enviar_log_discord(f"❌ Erro ao buscar aluno: {e}")
        return None


def _normalize(text: str) -> str:
    """
    Remove acentos e converte para caixa baixa para comparação flexível.
    """
    return (
        unicodedata.normalize("NFKD", text or "")
        .encode("ASCII", "ignore")
        .decode()
        .lower()
    )


def obter_cursos_ids(nome_plano: str):
    """
    Retorna a lista de IDs de cursos mapeadas por nome do plano (product_offer_name).
    Faz correspondência exata (sem acentos) ou fuzzy se necessário.
    """
    if not nome_plano:
        return None

    norm_plano = _normalize(nome_plano)

    # Correspondência exata (ignorando acentos)
    for key in CURSOS_OM:
        if _normalize(key) == norm_plano:
            return CURSOS_OM[key]

    # Tentativa de fuzzy match
    nomes_norm = {_normalize(k): k for k in CURSOS_OM}
    match = difflib.get_close_matches(norm_plano, nomes_norm.keys(), n=1, cutoff=0.8)
    if match:
        return CURSOS_OM[nomes_norm[match[0]]]

    return None


def log_request_info(request: Request) -> None:
    """
    Dependência do FastAPI para logar todas as requisições no terminal e no Discord.
    """
    mensagem = (
        f"\n📥 Requisição recebida:\n"
        f"🔗 URL completa: {request.url}\n"
        f"📍 Método: {request.method}\n"
        f"📦 Cabeçalhos: {dict(request.headers)}"
    )
    print(mensagem)
    enviar_log_discord(mensagem)


# Aplica o logger em todas as rotas
router.dependencies.append(Depends(log_request_info))

# Busca token assim que o módulo é importado
TOKEN_UNIDADE = obter_token_unidade()


@router.get("/secure")
async def secure_check():
    """
    Força atualização manual de TOKEN_UNIDADE via GET /secure
    """
    novo = obter_token_unidade()
    if novo:
        return "🔐 Token atualizado com sucesso via /secure"
    return JSONResponse(
        content="❌ Falha ao atualizar token via /secure", status_code=500
    )


async def _process_webhook(payload: dict):
    """
    Processa o payload de pedido (já extraído de payload["order"] ou do próprio body)
    e executa cadastro, matrícula ou exclusão de aluno conforme o evento.
    """
    try:
        evento = payload.get("webhook_event_type")

        # 1) Tratamento de reembolso → exclui o aluno
        if evento == "order_refunded":
            customer = payload.get("Customer", {})
            cpf = customer.get("CPF", "").replace(".", "").replace("-", "")
            if not cpf:
                msg = "❌ CPF do aluno não encontrado no payload de reembolso."
                enviar_log_discord(msg)
                return JSONResponse(
                    status_code=400, content={"error": "CPF do aluno não encontrado."}
                )

            aluno_id = buscar_aluno_por_cpf(cpf)
            if not aluno_id:
                msg = "❌ ID do aluno não encontrado para o CPF fornecido."
                enviar_log_discord(msg)
                return JSONResponse(
                    status_code=400, content={"error": "ID do aluno não encontrado."}
                )

            resp_exclusao = requests.delete(
                f"{OM_BASE}/alunos/{aluno_id}",
                headers={"Authorization": f"Basic {BASIC_B64}"},
            )
            if not resp_exclusao.ok:
                msg = (
                    f"❌ ERRO AO EXCLUIR ALUNO\nAluno ID: {aluno_id}\n"
                    f"🔧 Detalhes: {resp_exclusao.text}"
                )
                enviar_log_discord(msg)
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": "Falha ao excluir aluno",
                        "detalhes": resp_exclusao.text,
                    },
                )

            msg = f"✅ Conta do aluno com ID {aluno_id} excluída com sucesso."
            enviar_log_discord(msg)
            return {"message": "Conta do aluno excluída com sucesso."}

        # 2) Se não for pedido aprovado, ignora
        if evento != "order_approved":
            return {"message": "Evento ignorado"}

        # 3) Pedido aprovado → cadastro e matrícula
        customer = payload.get("Customer", {})
        nome = customer.get("full_name")
        cpf = customer.get("CPF", "").replace(".", "").replace("-", "")
        email = customer.get("email")
        celular = customer.get("mobile") or "(00) 00000-0000"
        cidade = customer.get("city") or ""
        estado = customer.get("state") or ""
        endereco = (customer.get("street") or "") + ", " + str(customer.get("number") or "")
        bairro = customer.get("neighborhood") or ""
        complemento = customer.get("complement") or ""
        cep = customer.get("zipcode") or ""

        # >>> Sempre usa product_offer_name para mapear o pacote comprado
        plano_assinatura = payload.get("Product", {}).get("product_offer_name")
        cursos_ids = obter_cursos_ids(plano_assinatura)
        if not cursos_ids:
            return JSONResponse(
                status_code=400,
                content={"error": f"Plano '{plano_assinatura}' não mapeado."},
            )

        # Dados para cadastro no OM
        dados_aluno = {
            "token": TOKEN_UNIDADE,
            "nome": nome,
            "data_nascimento": "2000-01-01",
            "email": email,
            "fone": celular,
            "senha": "123456",
            "celular": celular,
            "doc_cpf": cpf,
            "doc_rg": "00000000000",
            "pais": "Brasil",
            "uf": estado,
            "cidade": cidade,
            "endereco": endereco,
            "complemento": complemento,
            "bairro": bairro,
            "cep": cep,
        }

        # 3.1) Cadastra o aluno no OM
        resp_cadastro = requests.post(
            f"{OM_BASE}/alunos",
            data=dados_aluno,
            headers={"Authorization": f"Basic {BASIC_B64}"},
        )
        aluno_response = resp_cadastro.json()
        if not resp_cadastro.ok or aluno_response.get("status") != "true":
            msg = f"❌ ERRO NO CADASTRO: {resp_cadastro.text}"
            enviar_log_discord(msg)
            return JSONResponse(
                status_code=500,
                content={"error": "Falha ao criar aluno", "detalhes": resp_cadastro.text},
            )

        aluno_id = aluno_response.get("data", {}).get("id")
        if not aluno_id:
            msg = "❌ ID do aluno não retornado!"
            enviar_log_discord(msg)
            return JSONResponse(
                status_code=500,
                content={"error": "ID do aluno não encontrado na resposta de cadastro."},
            )

        # 3.2) Matricula o aluno nos cursos obtidos
        dados_matricula = {
            "token": TOKEN_UNIDADE,
            "cursos": ",".join(str(c) for c in cursos_ids),
        }
        resp_matricula = requests.post(
            f"{OM_BASE}/alunos/matricula/{aluno_id}",
            data=dados_matricula,
            headers={"Authorization": f"Basic {BASIC_B64}"},
        )
        if not resp_matricula.ok or resp_matricula.json().get("status") != "true":
            msg = f"❌ ERRO NA MATRÍCULA\nAluno ID: {aluno_id}\n🔧 Detalhes: {resp_matricula.text}"
            enviar_log_discord(msg)
            return JSONResponse(
                status_code=500,
                content={"error": "Falha ao matricular", "detalhes": resp_matricula.text},
            )

        # 3.3) Envia mensagem via ChatPro/WhatsApp
        numero_whatsapp = "55" + "".join(filter(str.isdigit, celular))[-11:]
        mensagem = (
            f"Oii {nome}, Seja bem Vindo/a Ao CED BRASIL\n\n"
            f"📦 *Plano adquirido:* {plano_assinatura}\n\n"
            "*Seu acesso:*\n"
            f"Login: *{cpf}*\n"
            "Senha: *123456*\n\n"
            "🌐 *Portal do aluno:* https://ead.cedbrasilia.com.br\n"
            "📲 *App Android:* https://play.google.com/store/apps/details?id=br.com.om.app&hl=pt_BR\n"
            "📱 *App iOS:* https://apps.apple.com/br/app/meu-app-de-cursos/id1581898914\n\n"
            "🌐 *Site da Escola* https://www.cedbrasilia.com.br\n"
        )
        resp_whatsapp = requests.post(
            CHATPRO_URL,
            json={"number": numero_whatsapp, "message": mensagem},
            headers={
                "Authorization": CHATPRO_TOKEN,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        if resp_whatsapp.status_code != 200:
            enviar_log_discord(f"❌ Erro ao enviar WhatsApp: {resp_whatsapp.text}")
        else:
            enviar_log_discord("✅ Mensagem enviada com sucesso")

        return {
            "message": "Aluno cadastrado, matriculado e notificado com sucesso!",
            "aluno_id": aluno_id,
            "cursos": cursos_ids,
        }

    except Exception as e:
        msg = f"❌ EXCEÇÃO NO PROCESSAMENTO: {e}"
        enviar_log_discord(msg)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webhook")
async def webhook_kiwify(payload: dict):
    """
    Rota oficial para receber o webhook do Kiwify.
    Extrai payload['order'] quando presente, senão usa payload direto.
    """
    # Se vier {"order": { … } }, usa payload["order"].
    # Se o body já for o objeto de pedido, usa payload diretamente.
    order_payload = payload.get("order") or payload
    return await _process_webhook(order_payload)


@router.post("/")
async def webhook_root(payload: dict):
    """
    Alias para /webhook, mantendo compatibilidade.
    """
    order_payload = payload.get("order") or payload
    return await _process_webhook(order_payload)
