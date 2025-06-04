from flask import Flask, request, jsonify
import requests
from requests.auth import HTTPBasicAuth
import os
import json

app = Flask(__name__)

# 1. CONSTANTES E VARIÁVEIS DE AMBIENTE
OURO_BASE_URL        = os.getenv("OURO_BASE_URL")
BASIC_AUTH           = os.getenv("BASIC_AUTH")
SUPORTE_WHATSAPP     = os.getenv("SUPORTE_WHATSAPP")
CHATPRO_TOKEN        = os.getenv("CHATPRO_TOKEN")
CHATPRO_INSTANCIA    = os.getenv("CHATPRO_INSTANCIA")
CHATPRO_URL          = f"https://v5.chatpro.com.br/{CHATPRO_INSTANCIA}/api/v1/send_message"
CALLMEBOT_APIKEY     = os.getenv("CALLMEBOT_APIKEY")
CALLMEBOT_PHONE      = os.getenv("CALLMEBOT_PHONE")
API_URL_TOKEN        = os.getenv("API_URL")  # ex: https://meuappdecursos.com.br/ws/v2/unidades/token/
ID_UNIDADE           = int(os.getenv("ID_UNIDADE", 0))
KEY                  = os.getenv("KEY")
DISCORD_WEBHOOK      = os.getenv("DISCORD_WEBHOOK")

# 2. NOVA CONSTANTE PARA BUSCAR O MAPEAMENTO DE CURSOS
CURSOS_API_URL       = "https://api.cedbrasilia.com.br/cursos"

# 3. VARIÁVEL GLOBAL PARA ARMAZENAR O TOKEN DA UNIDADE
TOKEN_UNIDADE = None

# 4. VARIÁVEL GLOBAL PARA O MAPEAMENTO DINÂMICO DE CURSOS
MAPEAMENTO_CURSOS = {}



def enviar_log_discord(mensagem: str) -> None:
    """Envia mensagem de log para o Discord."""
    try:
        payload = {"content": mensagem}
        headers = {"Content-Type": "application/json"}
        resp = requests.post(DISCORD_WEBHOOK, data=json.dumps(payload), headers=headers)
        if resp.status_code == 204:
            print("✅ Log enviado ao Discord com sucesso.")
        else:
            print("❌ Falha ao enviar log para Discord:", resp.text)
    except Exception as e:
        print("❌ Erro ao enviar log para Discord:", str(e))


def enviar_log_whatsapp(mensagem: str) -> None:
    """Envia mensagem de log para o WhatsApp usando CallMeBot e também encaminha para Discord."""
    try:
        msg_formatada = requests.utils.quote(mensagem)
        url = f"https://api.callmebot.com/whatsapp.php?phone={CALLMEBOT_PHONE}&text={msg_formatada}&apikey={CALLMEBOT_APIKEY}"
        resp = requests.get(url)
        if resp.status_code == 200:
            print("✅ Log enviado ao WhatsApp com sucesso.")
        else:
            print("❌ Falha ao enviar log para WhatsApp:", resp.text)
    except Exception as e:
        print("❌ Erro ao enviar log para WhatsApp:", str(e))
    finally:
        # Em qualquer caso, repassar para Discord
        enviar_log_discord(mensagem)


def obter_token_unidade() -> str:
    """
    Faz requisição HTTP para obter o token da unidade.
    Armazena em TOKEN_UNIDADE e retorna.
    """
    global TOKEN_UNIDADE
    try:
        resposta = requests.get(f"{API_URL_TOKEN}{ID_UNIDADE}", auth=HTTPBasicAuth(KEY, ""))
        dados = resposta.json()
        if dados.get("status") == "true":
            TOKEN_UNIDADE = dados["data"]["token"]
            mensagem = "🔁 Token atualizado com sucesso!"
            print(mensagem)
            enviar_log_discord(mensagem)
            return TOKEN_UNIDADE

        mensagem = f"❌ Erro ao obter token: {dados}"
        print(mensagem)
        enviar_log_whatsapp(mensagem)
    except Exception as e:
        mensagem = f"❌ Exceção ao obter token: {str(e)}"
        print(mensagem)
        enviar_log_whatsapp(mensagem)

    return None


def obter_mapeamento_cursos() -> dict:
    """
    Faz GET em CURSOS_API_URL para buscar o dicionário de mapeamento de cursos.
    Espera que a resposta JSON tenha a chave "cursos" contendo um objeto nome->[ids].
    Em caso de falha, retorna dicionário vazio.
    """
    global MAPEAMENTO_CURSOS
    try:
        resp = requests.get(CURSOS_API_URL)
        resp.raise_for_status()
        dados = resp.json()
        cursos = dados.get("cursos", {})
        if not isinstance(cursos, dict):
            raise ValueError(f"Formato inesperado no JSON de cursos: {cursos}")
        MAPEAMENTO_CURSOS = cursos
        mensagem = "🔁 Mapeamento de cursos carregado com sucesso."
        print(mensagem)
        enviar_log_discord(mensagem)
        return MAPEAMENTO_CURSOS

    except Exception as e:
        mensagem = f"❌ Falha ao obter mapeamento de cursos: {str(e)}"
        print(mensagem)
        enviar_log_whatsapp(mensagem)
        # Mantém o MAPEAMENTO_CURSOS como {} (vazio) em caso de erro
        return {}


# 5. INICIALIZA TOKEN E MAPEAMENTO AO SUBIR APLICATIVO
TOKEN_UNIDADE = obter_token_unidade()
MAPEAMENTO_CURSOS = obter_mapeamento_cursos()


@app.before_request
def log_request_info():
    """
    Registra toda requisição recebida (URL, método, cabeçalhos) e envia para o Discord.
    """
    mensagem = (
        f"\n📥 Requisição recebida:\n"
        f"🔗 URL completa: {request.url}\n"
        f"📍 Método: {request.method}\n"
        f"📦 Cabeçalhos: {dict(request.headers)}"
    )
    print(mensagem)
    enviar_log_discord(mensagem)


@app.route('/secure', methods=['GET', 'HEAD'])
def secure_check():
    """
    Rota para forçar atualização manual do token da unidade.
    """
    novo = obter_token_unidade()
    if novo:
        return "🔐 Token atualizado com sucesso via /secure", 200
    return "❌ Falha ao atualizar token via /secure", 500


def buscar_aluno_por_cpf(cpf: str) -> int:
    """
    Busca um aluno na plataforma OURO Moderno pelo CPF.
    Retorna ID do aluno se encontrado ou None em caso de falha/ausência.
    """
    try:
        print(f"🔍 Buscando aluno com CPF: {cpf}")
        resp = requests.get(
            f"{OURO_BASE_URL}/alunos",
            headers={"Authorization": f"Basic {BASIC_AUTH}"},
            params={"cpf": cpf}
        )
        if not resp.ok:
            print(f"❌ Falha ao buscar aluno: {resp.text}")
            return None

        alunos = resp.json().get("data", [])
        if not alunos:
            print("❌ Nenhum aluno encontrado com o CPF fornecido.")
            return None

        aluno_id = alunos[0].get("id")
        print(f"✅ Aluno encontrado. ID: {aluno_id}")
        return aluno_id

    except Exception as e:
        print(f"❌ Erro ao buscar aluno: {str(e)}")
        return None


@app.route('/webhook', methods=['POST'])
def webhook():
    """
    Rota principal para processar webhooks de reembolso e aprovação de pedidos.
    - Se for 'order_refunded', exclui o aluno.
    - Se for 'order_approved', cadastra, matricula e notifica o aluno.
    """
    try:
        print("\n🔔 Webhook recebido com sucesso")
        payload = request.json
        evento = payload.get("webhook_event_type")

        # ─── TRATAMENTO DE REEMBOLSO ─────────────────────────────────────────────
        if evento == "order_refunded":
            customer = payload.get("Customer", {})
            cpf = customer.get("CPF", "").replace(".", "").replace("-", "")
            if not cpf:
                erro_msg = "❌ CPF do aluno não encontrado no payload de reembolso."
                print(erro_msg)
                enviar_log_whatsapp(erro_msg)
                return jsonify({"error": "CPF do aluno não encontrado."}), 400

            aluno_id = buscar_aluno_por_cpf(cpf)
            if not aluno_id:
                erro_msg = "❌ ID do aluno não encontrado para o CPF fornecido."
                print(erro_msg)
                enviar_log_whatsapp(erro_msg)
                return jsonify({"error": "ID do aluno não encontrado."}), 400

            print(f"🗑️ Excluindo conta do aluno com ID: {aluno_id}")
            resp_exclusao = requests.delete(
                f"{OURO_BASE_URL}/alunos/{aluno_id}",
                headers={"Authorization": f"Basic {BASIC_AUTH}"}
            )
            if not resp_exclusao.ok:
                erro_msg = (
                    f"❌ ERRO AO EXCLUIR ALUNO\n"
                    f"Aluno ID: {aluno_id}\n"
                    f"🔧 Detalhes: {resp_exclusao.text}"
                )
                print(erro_msg)
                enviar_log_whatsapp(erro_msg)
                return jsonify({"error": "Falha ao excluir aluno", "detalhes": resp_exclusao.text}), 500

            msg_exclusao = f"✅ Conta do aluno com ID {aluno_id} excluída com sucesso."
            print(msg_exclusao)
            enviar_log_whatsapp(msg_exclusao)
            return jsonify({"message": "Conta do aluno excluída com sucesso."}), 200

        # ─── IGNORA OUTROS EVENTOS MENOS 'order_approved' ─────────────────────────
        if evento != "order_approved":
            return jsonify({"message": "Evento ignorado"}), 200

        # ─── TRATAMENTO DE APROVAÇÃO DE PEDIDO ────────────────────────────────────
        # Atualiza o mapeamento de cursos antes de usar
        obter_mapeamento_cursos()

        customer = payload.get("Customer", {})
        nome     = customer.get("full_name")
        cpf      = customer.get("CPF", "").replace(".", "").replace("-", "")
        email    = customer.get("email")
        celular  = customer.get("mobile") or "(00) 00000-0000"
        cidade   = customer.get("city") or ""
        estado   = customer.get("state") or ""
        endereco = (customer.get("street") or "") + ", " + str(customer.get("number") or "")
        bairro       = customer.get("neighborhood") or ""
        complemento  = customer.get("complement") or ""
        cep          = customer.get("zipcode") or ""

        plano_assinatura = payload.get("Subscription", {}).get("plan", {}).get("name")
        print(f"📦 Plano de assinatura: {plano_assinatura}")

        cursos_ids = MAPEAMENTO_CURSOS.get(plano_assinatura)
        if not cursos_ids:
            return jsonify({"error": f"Plano '{plano_assinatura}' não mapeado."}), 400

        # ─── CADASTRO DO ALUNO ────────────────────────────────────────────────────
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
            "cep": cep
        }

        print("📨 Enviando dados do aluno para a API de cadastro...")
        resp_cadastro = requests.post(
            f"{OURO_BASE_URL}/alunos",
            data=dados_aluno,
            headers={"Authorization": f"Basic {BASIC_AUTH}"}
        )
        aluno_response = resp_cadastro.json()
        print("📨 Resposta completa do cadastro:", aluno_response)

        if not resp_cadastro.ok or aluno_response.get("status") != "true":
            erro_msg = (
                f"❌ ERRO NO CADASTRO: {resp_cadastro.text}\n"
                f"Aluno: {nome}, CPF: {cpf}, Email: {email}, Celular: {celular}"
            )
            print(erro_msg)
            enviar_log_whatsapp(erro_msg)
            return jsonify({"error": "Falha ao criar aluno", "detalhes": resp_cadastro.text}), 500

        aluno_id = aluno_response.get("data", {}).get("id")
        if not aluno_id:
            erro_msg = f"❌ ID do aluno não retornado!\nAluno: {nome}, CPF: {cpf}, Celular: {celular}"
            print(erro_msg)
            enviar_log_whatsapp(erro_msg)
            return jsonify({"error": "ID do aluno não encontrado na resposta de cadastro."}), 500

        print(f"✅ Aluno criado com sucesso. ID: {aluno_id}")

        # ─── MATRÍCULA DO ALUNO ───────────────────────────────────────────────────
        dados_matricula = {
            "token": TOKEN_UNIDADE,
            "cursos": ",".join(str(curso_id) for curso_id in cursos_ids)
        }
        print(f"📨 Dados para matrícula do aluno {aluno_id}: {dados_matricula}")
        resp_matricula = requests.post(
            f"{OURO_BASE_URL}/alunos/matricula/{aluno_id}",
            data=dados_matricula,
            headers={"Authorization": f"Basic {BASIC_AUTH}"}
        )

        if not resp_matricula.ok or resp_matricula.json().get("status") != "true":
            erro_msg = (
                f"❌ ERRO NA MATRÍCULA\n"
                f"Aluno ID: {aluno_id}\n"
                f"👤 Nome: {nome}\n"
                f"📄 CPF: {cpf}\n"
                f"📱 Celular: {celular}\n"
                f"🎓 Cursos: {cursos_ids}\n"
                f"🔧 Detalhes: {resp_matricula.text}"
            )
            print(erro_msg)
            enviar_log_whatsapp(erro_msg)
            return jsonify({"error": "Falha ao matricular", "detalhes": resp_matricula.text}), 500

        msg_matricula = (
            f"✅ MATRÍCULA REALIZADA COM SUCESSO\n"
            f"👤 Nome: {nome}\n"
            f"📄 CPF: {cpf}\n"
            f"📱 Celular: {celular}\n"
            f"🎓 Cursos: {cursos_ids}"
        )
        print(msg_matricula)
        enviar_log_whatsapp(msg_matricula)

        # ─── ENVIO DE MENSAGEM DE BOAS-VINDAS VIA CHATPRO ──────────────────────────
        mensagem = (
            f"Oii {nome}, Seja bem Vindo/a Ao CED BRASIL\n\n"
            f"📦 *Plano adquirido:* {plano_assinatura}\n\n"
            "*Seu acesso:*\n"
            f"Login: *{cpf}*\n"
            "Senha: *123456*\n\n"
            "🌐 *Portal do aluno:* https://ead.cedbrasilia.com.br\n"
            "📲 *App Android:* https://play.google.com/store/apps/details?id=br.com.om.app&hl=pt_BR\n"
            "📱 *App iOS:* https://apps.apple.com/br/app/meu-app-de-cursos/id1581898914\n\n"
            f"*Grupo da Turma* https://chat.whatsapp.com/Gzn00RNW15ABBfmTc6FEnP\n\n"
        )
        numero_whatsapp = "55" + ''.join(filter(str.isdigit, celular))[-11:]
        print(f"📤 Enviando mensagem via ChatPro para {numero_whatsapp}")
        resp_whatsapp = requests.post(
            CHATPRO_URL,
            json={"number": numero_whatsapp, "message": mensagem},
            headers={"Authorization": CHATPRO_TOKEN, "Content-Type": "application/json", "Accept": "application/json"}
        )
        if resp_whatsapp.status_code != 200:
            print("❌ Erro ao enviar WhatsApp:", resp_whatsapp.text)
        else:
            print("✅ Mensagem enviada com sucesso")

        return jsonify({
            "message": "Aluno cadastrado, matriculado e notificado com sucesso! Matrícula efetuada com sucesso!",
            "aluno_id": aluno_id,
            "cursos": cursos_ids
        }), 200

    except Exception as e:
        erro_msg = f"❌ EXCEÇÃO NO PROCESSAMENTO: {str(e)}"
        print(erro_msg)
        enviar_log_whatsapp(erro_msg)
        return jsonify({"error": "Erro interno no servidor", "detalhes": str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
