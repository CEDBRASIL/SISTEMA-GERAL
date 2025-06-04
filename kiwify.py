from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
import os
import json
import requests
from cursos import CURSOS_OM

router = APIRouter()

OM_BASE = os.getenv("OM_BASE")
BASIC_B64 = os.getenv("BASIC_B64")
CHATPRO_TOKEN = os.getenv("CHATPRO_TOKEN")
CHATPRO_URL = os.getenv("CHATPRO_URL")
UNIDADE_ID = os.getenv("UNIDADE_ID")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")

TOKEN_UNIDADE = None


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


def obter_cursos_ids(nome_plano: str):
    """Busca cursos ignorando diferença de caixa."""
    chave = next((k for k in CURSOS_OM if k.lower() == nome_plano.lower()), None)
    return CURSOS_OM.get(chave) if chave else None


def log_request_info(request: Request) -> None:
    mensagem = (
        f"\n📥 Requisição recebida:\n"
        f"🔗 URL completa: {request.url}\n"
        f"📍 Método: {request.method}\n"
        f"📦 Cabeçalhos: {dict(request.headers)}"
    )
    print(mensagem)
    enviar_log_discord(mensagem)


router.dependencies.append(Depends(log_request_info))

# Inicializa token ao importar o módulo
TOKEN_UNIDADE = obter_token_unidade()


@router.get("/secure")
async def secure_check():
    novo = obter_token_unidade()
    if novo:
        return "🔐 Token atualizado com sucesso via /secure"
    return JSONResponse(content="❌ Falha ao atualizar token via /secure", status_code=500)


@router.post("/webhook")
async def webhook(payload: dict):
    try:
        evento = payload.get("webhook_event_type")

        if evento == "order_refunded":
            customer = payload.get("Customer", {})
            cpf = customer.get("CPF", "").replace(".", "").replace("-", "")
            if not cpf:
                msg = "❌ CPF do aluno não encontrado no payload de reembolso."
                enviar_log_discord(msg)
                return JSONResponse(status_code=400, content={"error": "CPF do aluno não encontrado."})

            aluno_id = buscar_aluno_por_cpf(cpf)
            if not aluno_id:
                msg = "❌ ID do aluno não encontrado para o CPF fornecido."
                enviar_log_discord(msg)
                return JSONResponse(status_code=400, content={"error": "ID do aluno não encontrado."})

            resp_exclusao = requests.delete(
                f"{OM_BASE}/alunos/{aluno_id}",
                headers={"Authorization": f"Basic {BASIC_B64}"},
            )
            if not resp_exclusao.ok:
                msg = (
                    f"❌ ERRO AO EXCLUIR ALUNO\nAluno ID: {aluno_id}\n🔧 Detalhes: {resp_exclusao.text}"
                )
                enviar_log_discord(msg)
                return JSONResponse(status_code=500, content={"error": "Falha ao excluir aluno", "detalhes": resp_exclusao.text})

            msg = f"✅ Conta do aluno com ID {aluno_id} excluída com sucesso."
            enviar_log_discord(msg)
            return {"message": "Conta do aluno excluída com sucesso."}

        if evento != "order_approved":
            return {"message": "Evento ignorado"}

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

        plano_assinatura = payload.get("Subscription", {}).get("plan", {}).get("name")
        cursos_ids = obter_cursos_ids(plano_assinatura)
        if not cursos_ids:
            return JSONResponse(status_code=400, content={"error": f"Plano '{plano_assinatura}' não mapeado."})

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

        resp_cadastro = requests.post(
            f"{OM_BASE}/alunos",
            data=dados_aluno,
            headers={"Authorization": f"Basic {BASIC_B64}"},
        )
        aluno_response = resp_cadastro.json()
        if not resp_cadastro.ok or aluno_response.get("status") != "true":
            msg = f"❌ ERRO NO CADASTRO: {resp_cadastro.text}"
            enviar_log_discord(msg)
            return JSONResponse(status_code=500, content={"error": "Falha ao criar aluno", "detalhes": resp_cadastro.text})

        aluno_id = aluno_response.get("data", {}).get("id")
        if not aluno_id:
            msg = "❌ ID do aluno não retornado!"
            enviar_log_discord(msg)
            return JSONResponse(status_code=500, content={"error": "ID do aluno não encontrado na resposta de cadastro."})

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
            return JSONResponse(status_code=500, content={"error": "Falha ao matricular", "detalhes": resp_matricula.text})

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
        )

        resp_whatsapp = requests.post(
            CHATPRO_URL,
            json={"number": numero_whatsapp, "message": mensagem},
            headers={"Authorization": CHATPRO_TOKEN, "Content-Type": "application/json", "Accept": "application/json"},
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
