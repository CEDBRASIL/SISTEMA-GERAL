import os
import threading
from typing import List, Tuple, Optional
import requests
from fastapi import APIRouter, HTTPException
from datetime import datetime
from cursos import CURSOS_OM  # Importa o dicionário de mapeamento
import json # Importar json para serializar o payload do ChatPro

router = APIRouter()

# Variáveis de ambiente
BASIC_B64 = os.getenv("BASIC_B64")
UNIDADE_ID = os.getenv("UNIDADE_ID")
OM_BASE = os.getenv("OM_BASE")

# Variáveis de Ambiente para ChatPro (AGORA AQUI)
CHATPRO_URL = os.getenv("CHATPRO_URL")
CHATPRO_TOKEN = os.getenv("CHATPRO_TOKEN")

# Prefixo para gerar CPFs sequenciais na OM
CPF_PREFIXO = "20254158"
cpf_lock = threading.Lock()


def _log(msg: str):
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{agora}] {msg}")


def _obter_token_unidade() -> str:
    """
    Faz GET em /unidades/token/{UNIDADE_ID} para obter token da unidade na OM.
    """
    if not all([OM_BASE, BASIC_B64, UNIDADE_ID]):
        raise RuntimeError("Variáveis de ambiente OM não configuradas.")
    url = f"{OM_BASE}/unidades/token/{UNIDADE_ID}"
    try: # Adicionado try-except para lidar com erros de requisição
        r = requests.get(url, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=8)
        r.raise_for_status() # Levanta HTTPException para erros 4xx/5xx
        if r.json().get("status") == "true":
            return r.json()["data"]["token"]
        raise RuntimeError(f"Falha ao obter token da unidade: Resposta inesperada - {r.text}")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Erro de conexão ao obter token da unidade: {e}")
    except ValueError:
        raise RuntimeError(f"Resposta inválida (não JSON) ao obter token da unidade: {r.text}")


def _total_alunos() -> int:
    """
    Retorna o total de alunos cadastrados na unidade OM (para gerar CPF).
    """
    url = f"{OM_BASE}/alunos/total/{UNIDADE_ID}"
    try: # Adicionado try-except para lidar com erros de requisição
        r = requests.get(url, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=8)
        r.raise_for_status()
        if r.json().get("status") == "true":
            return int(r.json()["data"]["total"])
    except requests.exceptions.RequestException as e:
        _log(f"Erro de conexão no endpoint /alunos/total: {e}. Tentando contagem alternativa.")
    except (ValueError, TypeError) as e:
        _log(f"Erro ao processar resposta de /alunos/total: {e}. Tentando contagem alternativa.")

    # Fallback: busca todos que tenham CPF começando com o prefixo
    url2 = f"{OM_BASE}/alunos?unidade_id={UNIDADE_ID}&cpf_like={CPF_PREFIXO}"
    try: # Adicionado try-except para lidar com erros de requisição
        r2 = requests.get(url2, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=8)
        r2.raise_for_status()
        if r2.json().get("status") == "true":
            return len(r2.json()["data"])
    except requests.exceptions.RequestException as e:
        _log(f"Erro de conexão na contagem alternativa de alunos: {e}")
    except ValueError:
        _log(f"Resposta inválida (não JSON) na contagem alternativa de alunos: {r2.text}")

    raise RuntimeError("Falha ao apurar total de alunos")


# Melhorias na geração de CPF
CPF_MAX_RETRIES = 100  # Limite de tentativas para evitar colisões

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
        raise RuntimeError("Limite de tentativas para gerar CPF excedido.")

def _cpf_em_uso(cpf: str) -> bool:
    """
    Verifica se o CPF já está em uso na base de dados da OM.
    """
    url = f"{OM_BASE}/alunos?unidade_id={UNIDADE_ID}&cpf={cpf}"
    try: # Adicionado try-except para lidar com erros de requisição
        r = requests.get(url, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=8)
        r.raise_for_status()
        if r.json().get("status") == "true":
            return len(r.json().get("data", [])) > 0
    except requests.exceptions.RequestException as e:
        _log(f"Erro de conexão ao verificar CPF em uso: {e}")
    except ValueError:
        _log(f"Resposta inválida (não JSON) ao verificar CPF em uso: {r.text}")
    return False


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
        try: # Adicionado try-except para lidar com erros de requisição
            r = requests.post(
                f"{OM_BASE}/alunos",
                data=payload,
                headers={"Authorization": f"Basic {BASIC_B64}"},
                timeout=10
            )
            r.raise_for_status()
            _log(f"[CAD] Tentativa {tentativa+1}/60 | Status {r.status_code} | Retorno OM: {r.text}")
            if r.json().get("status") == "true":
                aluno_id = r.json()["data"]["id"]
                return aluno_id, cpf

            info = (r.json() or {}).get("info", "").lower()
            if "já está em uso" not in info:
                break
        except requests.exceptions.RequestException as e:
            _log(f"Erro de conexão ao cadastrar aluno (tentativa {tentativa+1}): {e}")
            break
        except ValueError:
            _log(f"Resposta inválida (não JSON) ao cadastrar aluno (tentativa {tentativa+1}): {r.text}")
            break

    raise RuntimeError("Falha ao cadastrar o aluno")


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
    try: # Adicionado try-except para lidar com erros de requisição
        r = requests.post(
            f"{OM_BASE}/alunos/matricula/{aluno_id}",
            data=payload,
            headers={"Authorization": f"Basic {BASIC_B64}"},
            timeout=10
        )
        r.raise_for_status()
        sucesso = r.json().get("status") == "true"
        _log(f"[MAT] {'✅' if sucesso else '❌'} Status {r.status_code} | Retorno OM: {r.text}")
        return sucesso
    except requests.exceptions.RequestException as e:
        _log(f"Erro de conexão ao matricular aluno: {e}")
        return False
    except ValueError:
        _log(f"Resposta inválida (não JSON) ao matricular aluno: {r.text}")
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

def _send_chatpro_message(whatsapp: str, message: str):
    """Envia uma mensagem via API ChatPro."""
    if not CHATPRO_URL or not CHATPRO_TOKEN:
        _log("AVISO: CHATPRO_URL ou CHATPRO_TOKEN não configurados. Mensagem ChatPro NÃO será enviada.")
        return

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHATPRO_TOKEN}"
    }
    # Formata o número de WhatsApp para o padrão esperado pelo ChatPro (apenas dígitos, incluindo código do país)
    # Assumindo que o whatsapp vem no formato "(XX) XXXXX-XXXX" ou "(XX) XXXX-XXXX"
    # E que o código do país é 55 (Brasil). Ajuste se necessário.
    whatsapp_clean = whatsapp.replace("(", "").replace(")", "").replace(" ", "").replace("-", "")
    if not whatsapp_clean.startswith("55"): # Adiciona código do país se não presente
        whatsapp_clean = "55" + whatsapp_clean

    payload = {
        "number": whatsapp_clean,
        "message": message
    }

    try:
        _log(f"Enviando mensagem ChatPro para {whatsapp_clean}...")
        response = requests.post(CHATPRO_URL, headers=headers, data=json.dumps(payload), timeout=10)
        response.raise_for_status() # Levanta um erro para status HTTP 4xx/5xx
        _log(f"Mensagem ChatPro enviada com sucesso para {whatsapp_clean}. Resposta: {response.text}")
    except requests.exceptions.Timeout:
        _log(f"Timeout ao enviar mensagem ChatPro para {whatsapp_clean}.")
    except requests.exceptions.HTTPError as http_err:
        _log(f"Erro HTTP ao enviar mensagem ChatPro para {whatsapp_clean}: {http_err}. Resposta: {http_err.text}")
    except requests.exceptions.RequestException as e:
        _log(f"Erro de conexão ao enviar mensagem ChatPro para {whatsapp_clean}: {e}")
    except Exception as e:
        _log(f"Erro inesperado ao enviar mensagem ChatPro para {whatsapp_clean}: {e}")


# Melhorias na função de matrícula
@router.post("/", summary="Cadastra (e opcionalmente matricula) um aluno na OM a partir do nome dos cursos")
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
        token_unit = _obter_token_unidade()
        aluno_id, cpf = _cadastrar_aluno_om(nome, whatsapp, email, cursos_ids, token_unit)
        
        # Envio da mensagem ChatPro após matrícula bem-sucedida
        chatpro_message = (
            f"Olá {nome}! 👋\n\n"
            "Bem-vindo(a) ao CED! Sua matrícula foi realizada com sucesso.\n\n"
            "Seus dados de acesso são:\n"
            f"Login: `{cpf}`\n"
            "Senha: `123456`\n\n"
            "Acesse nossa plataforma e comece seus estudos agora mesmo!\n"
            "Em caso de dúvidas, estamos à disposição."
        )
        _send_chatpro_message(whatsapp, chatpro_message)

        return {
            "status": "ok",
            "aluno_id": aluno_id,
            "cpf": cpf,
            "disciplinas_matriculadas": cursos_ids,
            "message": "Aluno cadastrado e matriculado com sucesso. Mensagem ChatPro enviada."
        }
    except RuntimeError as e:
        _log(f"❌ Erro em /matricular: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        _log(f"❌ Erro inesperado em /matricular: {str(e)}")
        raise HTTPException(status_code=500, detail="Erro inesperado. Consulte os logs para mais detalhes.")
