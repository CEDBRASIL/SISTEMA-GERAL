import os
import threading
from typing import List, Tuple, Optional
import requests
from fastapi import APIRouter, HTTPException
from datetime import datetime
from cursos import CURSOS_OM  # Importa o dicionário de mapeamento

router = APIRouter()

# Variáveis de ambiente para OM
BASIC_B64 = os.getenv("BASIC_B64")
UNIDADE_ID = os.getenv("UNIDADE_ID")
OM_BASE = os.getenv("OM_BASE")

# Variáveis de ambiente para Call Me Bot (substituindo ChatPro)
# A chave de API padrão é a que você forneceu no exemplo
CALLMEBOT_API_KEY = os.getenv("CALLMEBOT_API_KEY", "2712587")
CALLMEBOT_URL = "https://api.callmebot.com/whatsapp.php"

# Prefixo para gerar CPFs sequenciais na OM
CPF_PREFIXO = "20254158"
cpf_lock = threading.Lock()


def _log(msg: str):
    """
    Função auxiliar para registrar mensagens com timestamp.
    """
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{agora}] {msg}")


def _obter_token_unidade() -> str:
    """
    Faz GET em /unidades/token/{UNIDADE_ID} para obter token da unidade na OM.
    """
    if not all([OM_BASE, BASIC_B64, UNIDADE_ID]):
        raise RuntimeError("Variáveis de ambiente OM não configuradas.")
    url = f"{OM_BASE}/unidades/token/{UNIDADE_ID}"
    try:
        r = requests.get(
            url,
            headers={"Authorization": f"Basic {BASIC_B64}"},
            timeout=8
        )
        r.raise_for_status() # Lança exceção para erros HTTP
        if r.json().get("status") == "true":
            return r.json()["data"]["token"]
        raise RuntimeError(f"Falha ao obter token da unidade: Resposta inesperada da OM: {r.text}")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Erro ao conectar ou obter token da unidade na OM: {e}")


def _total_alunos() -> int:
    """
    Retorna o total de alunos cadastrados na unidade OM (para gerar CPF).
    Prioriza o endpoint de total, com fallback para busca por prefixo de CPF.
    """
    url_total = f"{OM_BASE}/alunos/total/{UNIDADE_ID}"
    try:
        r_total = requests.get(
            url_total,
            headers={"Authorization": f"Basic {BASIC_B64}"},
            timeout=8
        )
        if r_total.ok and r_total.json().get("status") == "true":
            return int(r_total.json()["data"]["total"])
    except requests.exceptions.RequestException as e:
        _log(f"Aviso: Falha ao usar endpoint /alunos/total: {e}. Tentando fallback.")

    # Fallback: busca todos que tenham CPF começando com o prefixo
    url_fallback = f"{OM_BASE}/alunos?unidade_id={UNIDADE_ID}&cpf_like={CPF_PREFIXO}"
    try:
        r_fallback = requests.get(
            url_fallback,
            headers={"Authorization": f"Basic {BASIC_B64}"},
            timeout=8
        )
        if r_fallback.ok and r_fallback.json().get("status") == "true":
            return len(r_fallback.json().get("data", []))
    except requests.exceptions.RequestException as e:
        _log(f"Aviso: Falha ao usar endpoint /alunos com cpf_like: {e}.")

    raise RuntimeError("Falha ao apurar total de alunos (ambos os métodos falharam).")


# Melhorias na geração de CPF
CPF_MAX_RETRIES = 100  # Limite de tentativas para evitar colisões


def _proximo_cpf(incremento: int = 0) -> str:
    """
    Gera o próximo CPF sequencial, adicionando incremento para evitar colisões.
    """
    with cpf_lock:
        for tentativa in range(CPF_MAX_RETRIES):
            seq = _total_alunos() + 1 + incremento + tentativa
            cpf = CPF_PREFIXO + str(seq).zfill(3)
            if not _cpf_em_uso(cpf):
                return cpf
        raise RuntimeError("Limite de tentativas para gerar CPF excedido. Não foi possível encontrar um CPF único.")


def _cpf_em_uso(cpf: str) -> bool:
    """
    Verifica se o CPF já está em uso na base de dados da OM.
    """
    url = f"{OM_BASE}/alunos?unidade_id={UNIDADE_ID}&cpf={cpf}"
    try:
        r = requests.get(
            url,
            headers={"Authorization": f"Basic {BASIC_B64}"},
            timeout=8
        )
        r.raise_for_status() # Lança exceção para erros HTTP
        if r.json().get("status") == "true":
            return len(r.json().get("data", [])) > 0
        _log(f"Aviso: Resposta inesperada ao verificar CPF {cpf} em uso: {r.text}")
        return False # Assume que não está em uso se a resposta for inesperada
    except requests.exceptions.RequestException as e:
        _log(f"Erro ao verificar CPF {cpf} em uso: {e}. Assumindo que não está em uso para tentar novamente.")
        return False # Se houver erro de conexão, assume que não está em uso e tenta gerar outro CPF


def _cadastrar_somente_aluno(
    nome: str,
    whatsapp: str,
    email: Optional[str],
    token_key: str,
    senha_padrao: str = "123456"
) -> Tuple[str, str]:
    """
    Cadastra apenas o aluno na OM (gera e-mail dummy se não for fornecido).
    Retorna: (aluno_id, cpf).
    """
    # Se não houver e-mail, cria um e-mail dummy a partir do WhatsApp
    email_validado = email or f"{whatsapp}@nao-informado.com"

    for tentativa in range(60):
        cpf = _proximo_cpf(tentativa)
        payload = {
            "token": token_key,
            "nome": nome,
            "email": email_validado,
            "whatsapp": whatsapp,
            "fone": whatsapp,
            "celular": whatsapp,
            "data_nascimento": "2000-01-01",
            "doc_cpf": cpf,
            "doc_rg": "000000000",
            "pais": "Brasil",
            "uf": "DF",
            "cidade": "Brasília",
            "endereco": "Não informado",
            "bairro": "Centro",
            "cep": "70000-000",
            "complemento": "",
            "numero": "0",
            "unidade_id": UNIDADE_ID,
            "senha": senha_padrao,
        }
        try:
            r = requests.post(
                f"{OM_BASE}/alunos",
                data=payload,
                headers={"Authorization": f"Basic {BASIC_B64}"},
                timeout=10
            )
            _log(f"[CAD] Tentativa {tentativa+1}/60 | Status {r.status_code} | Retorno OM: {r.text}")

            if r.ok and r.json().get("status") == "true":
                aluno_id = r.json()["data"]["id"]
                return aluno_id, cpf

            info = (r.json() or {}).get("info", "").lower()
            if "já está em uso" not in info and "cpf já cadastrado" not in info:
                # Se o erro não for sobre CPF em uso, parar e levantar exceção
                raise RuntimeError(f"Falha no cadastro do aluno na OM: {r.text}")

        except requests.exceptions.RequestException as e:
            _log(f"[CAD] Erro de conexão/requisição na tentativa {tentativa+1}: {e}")
        except ValueError: # Erro ao decodificar JSON
            _log(f"[CAD] Erro ao decodificar JSON na tentativa {tentativa+1}: {r.text}")
        except Exception as e:
            _log(f"[CAD] Erro inesperado na tentativa {tentativa+1}: {e}")

    raise RuntimeError("Falha ao cadastrar o aluno após múltiplas tentativas ou erro persistente.")


def _matricular_aluno_om(aluno_id: str, cursos_ids: List[int], token_key: str) -> bool:
    """
    Efetua a matrícula (vincula disciplinas) para o aluno já cadastrado.
    Se não houver cursos_ids, pula a matrícula e retorna True.
    """
    if not cursos_ids:
        _log(f"[MAT] Nenhum curso informado para aluno {aluno_id}. Pulando matrícula.")
        return True

    cursos_str = ",".join(map(str, cursos_ids))
    payload = {"token": token_key, "cursos": cursos_str}
    _log(f"[MAT] Matriculando aluno {aluno_id} nos cursos: {cursos_str}")
    try:
        r = requests.post(
            f"{OM_BASE}/alunos/matricula/{aluno_id}",
            data=payload,
            headers={"Authorization": f"Basic {BASIC_B64}"},
            timeout=10
        )
        sucesso = r.ok and r.json().get("status") == "true"
        _log(f"[MAT] {'✅' if sucesso else '❌'} Status {r.status_code} | Retorno OM: {r.text}")
        return sucesso
    except requests.exceptions.RequestException as e:
        _log(f"[MAT] Erro de conexão/requisição ao matricular aluno {aluno_id}: {e}")
        return False
    except Exception as e:
        _log(f"[MAT] Erro inesperado ao matricular aluno {aluno_id}: {e}")
        return False


def _cadastrar_aluno_om(
    nome: str,
    whatsapp: str,
    email: Optional[str],
    cursos_ids: List[int],
    token_key: str,
    senha_padrao: str = "123456"
) -> Tuple[str, str]:
    """
    Cadastra aluno e, se houver cursos_ids, matricula nas disciplinas.
    Retorna: (aluno_id, cpf).
    """
    # 1) Cadastro básico do aluno
    aluno_id, cpf = _cadastrar_somente_aluno(nome, whatsapp, email, token_key, senha_padrao)

    # 2) Se houver cursos_ids, realiza a matrícula
    if cursos_ids:
        ok_matri = _matricular_aluno_om(aluno_id, cursos_ids, token_key)
        if not ok_matri:
            raise RuntimeError("Aluno cadastrado, mas falha ao matricular em disciplinas.")
    else:
        _log(f"[MAT] Curso não informado para {nome}. Cadastro concluído sem matrícula.")

    return aluno_id, cpf


def _send_whatsapp_message(
    nome: str,
    whatsapp: str,
    cursos_nomes: List[str]
) -> None:
    """
    Envia mensagem automática no WhatsApp via Call Me Bot, com boas-vindas e informações de acesso.
    """
    if not CALLMEBOT_API_KEY:
        _log("⚠️ Chave de API do Call Me Bot não configurada. Pulando envio de WhatsApp.")
        return

    # Garante que o número seja somente dígitos (sem parênteses, espaços ou traços)
    numero_telefone = "".join(filter(str.isdigit, whatsapp))

    # Monta a mensagem com emojis
    cursos_texto = "\n".join(f"• {c}" for c in cursos_nomes) if cursos_nomes else "Nenhum curso específico."
    mensagem = (
        f"👋 Olá, {nome}!\n\n"
        f"🎉 Seja bem-vindo(a) ao CED BRASIL!\n\n"
        f"📚 Curso adquirido:\n"
        f"{cursos_texto}\n\n"
        f"🌐 Portal do Aluno: https://ead.cedbrasilia.com.br\n"
        f"🤖 APP Android: https://play.google.com/store/apps/datasafety?id=br.com.om.app&hl=pt_BR\n"
        f"🍎 APP iOS: https://apps.apple.com/br/app/meu-app-de-cursos/id1581898914\n\n"
        f"Qualquer dúvida, estamos à disposição. Boa jornada de estudos! 🚀"
    )

    # Monta os parâmetros para a requisição GET do Call Me Bot
    params = {
        "phone": f"+{numero_telefone}", # Adiciona o '+' para garantir o formato internacional
        "text": mensagem,
        "apikey": CALLMEBOT_API_KEY
    }

    try:
        r = requests.get(
            CALLMEBOT_URL,
            params=params, # Use params para requisições GET
            timeout=10
        )
        if r.ok:
            _log(f"[Call Me Bot] Mensagem enviada com sucesso para {numero_telefone}. Resposta: {r.text}")
        else:
            _log(f"[Call Me Bot] Falha ao enviar mensagem para {numero_telefone}. HTTP {r.status_code} | {r.text}")
            if r.text:
                _log(f"[Call Me Bot] Detalhes do erro: {r.text}")
    except requests.exceptions.RequestException as e:
        _log(f"[Call Me Bot] Erro inesperado ao enviar WhatsApp para {numero_telefone}: {str(e)}")


@router.post("/", summary="Cadastra (e opcionalmente matricula) um aluno na OM e envia WhatsApp via Call Me Bot")
async def realizar_matricula(dados: dict):
    """
    Espera um JSON com:
      - nome: str (obrigatório)
      - whatsapp: str (obrigatório)
      - email: str (opcional)
      - cursos: List[str] (opcional, nomes dos cursos conforme mapeamento em cursos.py)
      - cursos_ids: List[int] (opcional, IDs diretos, caso queira forçar)
    """
    nome = dados.get("nome")
    whatsapp = dados.get("whatsapp")
    email = dados.get("email")
    cursos_nomes = dados.get("cursos") or []
    cursos_ids_input = dados.get("cursos_ids") or []

    if not nome or not whatsapp:
        raise HTTPException(
            status_code=400,
            detail="Dados incompletos: 'nome' e 'whatsapp' são obrigatórios."
        )

    cursos_ids: List[int] = []
    if cursos_ids_input:
        cursos_ids = cursos_ids_input
    else:
        for nome_curso in cursos_nomes:
            chave = next((k for k in CURSOS_OM if k.lower() == nome_curso.lower()), None)
            if not chave:
                raise HTTPException(
                    status_code=404,
                    detail=f"Curso '{nome_curso}' não encontrado no mapeamento."
                )
            cursos_ids.extend(CURSOS_OM[chave])

    try:
        # 1) obtém token da unidade OM
        token_unit = _obter_token_unidade()

        # 2) cadastra aluno e matricula
        aluno_id, cpf = _cadastrar_aluno_om(nome, whatsapp, email, cursos_ids, token_unit)

        # 3) envia mensagem automática no WhatsApp via Call Me Bot
        _send_whatsapp_message(nome, whatsapp, cursos_nomes)

        # Log de sucesso detalhado conforme solicitado
        _log("✅ MATRÍCULA REALIZADA COM SUCESSO")
        _log(f"👤 Nome: {nome}")
        _log(f"📄 CPF: {cpf}")
        _log(f"📱 Celular: {whatsapp}")
        _log(f"🎓 Cursos: {cursos_ids}")

        return {
            "status": "ok",
            "aluno_id": aluno_id,
            "cpf": cpf,
            "disciplinas_matriculadas": cursos_ids,
        }

    except RuntimeError as e:
        _log(f"❌ Erro em /matricular: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

    except Exception as e:
        _log(f"❌ Erro inesperado em /matricular: {str(e)}")
        raise HTTPException(status_code=500, detail="Erro inesperado. Consulte os logs para mais detalhes.")
