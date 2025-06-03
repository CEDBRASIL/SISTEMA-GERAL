# matricular.py

"""
matricular.py – Prepara o processo de matrícula e pagamento com Mercado Pago.
A matrícula final no sistema OM é feita via webhook.
Inclui endpoint para gerar descrição de curso com Gemini API.
"""

import os, threading
from typing import List, Tuple, Optional, Dict
import requests
from fastapi import APIRouter, HTTPException, Request
from datetime import datetime
import uuid # Para gerar IDs únicos para as matrículas pendentes
from cursos import CURSOS_OM # Presumo que CURSOS_OM esteja definido em cursos.py
import mercadopago # Importar o SDK do Mercado Pago
import json # Para lidar com JSON da resposta da API Gemini

router = APIRouter()

OM_BASE     = os.getenv("OM_BASE")
BASIC_B64   = os.getenv("BASIC_B64")
UNIDADE_ID  = os.getenv("UNIDADE_ID")

# ──────────────────────────────────────────────────────────
# ATENÇÃO: Valores hardcoded - MUITO CUIDADO EM PRODUÇÃO!
# Substitua os placeholders pelos seus valores reais.
# ──────────────────────────────────────────────────────────
MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")
MP_PREAPPROVAL_PLAN_ID = "S2c93808496d9dcdf0196f2ff3b5f0b11" # <--- SUBSTITUA PELO ID DO SEU PLANO REAL
THANK_YOU_PAGE_URL = "https://www.cedbrasilia.com.br/obrigado" # <--- SUBSTITUA PELA SUA PÁGINA DE OBRIGADO REAL

# ──────────────────────────────────────────────────────────
# Credenciais da API Gemini (Deixe vazio, será preenchido pelo ambiente Canvas)
# ──────────────────────────────────────────────────────────
GEMINI_API_KEY = "" # Deixe vazio, o Canvas preencherá em tempo de execução.

# ──────────────────────────────────────────────────────────
# Armazenamento Temporário de Matrículas Pendentes (ATENÇÃO: Não persistente!)
# Para produção, use um banco de dados (Redis, PostgreSQL, etc.)
# ──────────────────────────────────────────────────────────
PENDING_ENROLLMENTS: Dict[str, Dict] = {} # { 'uuid': { 'nome': '...', 'whatsapp': '...', 'email': '...', 'cursos_nomes': [...] } }

CPF_PREFIXO = "20254158"
cpf_lock = threading.Lock()

# ──────────────────────────────────────────────────────────
# Configuração Mercado Pago
# ──────────────────────────────────────────────────────────
if MP_ACCESS_TOKEN != "SEU_ACCESS_TOKEN_DO_MERCADO_PAGO": # Verifica se o token foi realmente configurado
    mercadopago.configure({
        "access_token": MP_ACCESS_TOKEN
    })
else:
    _log("AVISO: MP_ACCESS_TOKEN não configurado no código. A integração com Mercado Pago não funcionará.")

# ──────────────────────────────────────────────────────────
# Funções Auxiliares (já existentes, algumas adaptadas)
# ──────────────────────────────────────────────────────────
def _log(msg: str):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}")

def _obter_token_unidade() -> str:
    if not all([OM_BASE, BASIC_B64, UNIDADE_ID]):
        raise RuntimeError("Variáveis OM não configuradas. Verifique .env ou ambiente.")
    url = f"{OM_BASE}/unidades/token/{UNIDADE_ID}"
    r = requests.get(url, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=8)
    if r.ok and r.json().get("status") == "true":
        return r.json()["data"]["token"]
    raise RuntimeError("Falha ao obter token da unidade")

def _total_alunos() -> int:
    url = f"{OM_BASE}/alunos/total/{UNIDADE_ID}"
    r = requests.get(url, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=8)
    if r.ok and r.json().get("status") == "true":
        return int(r.json()["data"]["total"])
    url = f"{OM_BASE}/alunos?unidade_id={UNIDADE_ID}&cpf_like={CPF_PREFIXO}"
    r = requests.get(url, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=8)
    if r.ok and r.json().get("status") == "true":
        return len(r.json()["data"])
    raise RuntimeError("Falha ao apurar total de alunos")

def _proximo_cpf(incr:int=0)->str:
    with cpf_lock:
        seq = _total_alunos() + 1 + incr
        return CPF_PREFIXO + str(seq).zfill(3)

def _matricular_om(aluno_id:str, cursos_ids:List[int], token:str)->bool:
    payload = {"token": token, "cursos": ",".join(map(str, cursos_ids))}
    r = requests.post(f"{OM_BASE}/alunos/matricula/{aluno_id}",
                      data=payload,
                      headers={"Authorization": f"Basic {BASIC_B64}"},
                      timeout=10)
    _log(f"[MAT] {r.status_code} {r.text[:120]}")
    return r.ok and r.json().get("status") == "true"

def _cadastrar_aluno(nome:str, whatsapp:str, email:str, cursos_ids:List[int], token:str, cpf:Optional[str]=None)->Tuple[str,str]:
    # Adaptação: Se o CPF for fornecido, usa-o. Caso contrário, gera um novo.
    final_cpf = cpf if cpf else _proximo_cpf()

    for i in range(60): # Tentar múltiplos CPFs em caso de conflito (se não for fornecido)
        if not cpf: # Apenas gera novo CPF se não foi fornecido
            final_cpf = _proximo_cpf(i)

        payload = {
            "token": token,
            "nome": nome,
            "email": email or f"{whatsapp}@nao-informado.com",
            "whatsapp": whatsapp,
            "fone": whatsapp,
            "celular": whatsapp,
            "data_nascimento": "2000-01-01", # Ajustar se tiver dado real
            "doc_cpf": final_cpf, # Usar o CPF final
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
            "senha": "123456" # Considere gerar senhas mais seguras ou um fluxo de recuperação
        }
        r = requests.post(f"{OM_BASE}/alunos", data=payload,
                          headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=10)
        if r.ok and r.json().get("status") == "true":
            aluno_id = r.json()["data"]["id"]
            if _matricular_om(aluno_id, cursos_ids, token):
                return aluno_id, final_cpf
        # Se o CPF já está em uso E não foi um CPF fornecido (ou seja, foi gerado), tenta de novo.
        if "já está em uso" not in (r.json() or {}).get("info", "").lower() or cpf:
            break # Sair se o erro não for de CPF em uso (evitar loops infinitos em outros erros) ou se o CPF foi fornecido.
    raise RuntimeError("Falha ao cadastrar/matricular aluno")

def _nome_para_ids(cursos_nomes:List[str])->List[int]:
    ids=[]
    for nome in cursos_nomes:
        # CURSOS_OM deve ser um dicionário que mapeia nomes de cursos para listas de IDs de disciplinas
        # Ex: CURSOS_OM = {"Curso de Programação Web": [101, 102], "Curso de Design Gráfico": [201]}
        ids.extend(CURSOS_OM.get(nome.strip(), []))
    return ids

# Funções que serão chamadas pelo webhook
def matricular_aluno_final(nome:str, whatsapp:str, email:Optional[str], cursos_nomes:List[str])->Tuple[str,str,List[int]]:
    """
    Função para realizar a matrícula final no sistema OM, chamada após a confirmação do pagamento.
    """
    cursos_ids = _nome_para_ids(cursos_nomes)
    if not cursos_ids:
        raise RuntimeError("Nenhum ID de disciplina encontrado para os cursos fornecidos")
    token = _obter_token_unidade()
    # Aqui, o CPF será gerado internamente se não for passado, ou você pode passar um CPF pré-gerado se necessário.
    aluno_id, cpf = _cadastrar_aluno(nome, whatsapp, email or "", cursos_ids, token)
    return aluno_id, cpf, cursos_ids

# ──────────────────────────────────────────────────────────
# Endpoint de Matrícula (Modificado para iniciar o MP)
# ──────────────────────────────────────────────────────────
@router.post("/")
async def endpoint_iniciar_matricula(body: dict):
    nome = body.get("nome")
    whatsapp = body.get("whatsapp")
    email = body.get("email","")
    cursos_nomes = body.get("cursos",[]) # Agora é uma lista de nomes de cursos
    curso_principal_nome = cursos_nomes[0] if cursos_nomes else "Matrícula CED" # Nome para MP

    # ──────────────────────────────────────────────────────────
    # PREÇO FIXO PARA TODOS OS CHECKOUTS
    # ──────────────────────────────────────────────────────────
    valor_total_curso = 49.90 # Preço fixo de R$49,90

    if not nome or not whatsapp or not cursos_nomes:
        raise HTTPException(400, detail="nome, whatsapp e cursos são obrigatórios.")
    
    # Validação do valor fixo (opcional, mas boa prática)
    if valor_total_curso != 49.90:
        raise HTTPException(500, detail="Erro interno: Valor do curso não está configurado corretamente.")
    
    if not MP_PREAPPROVAL_PLAN_ID:
        raise HTTPException(500, detail="MP_PREAPPROVAL_PLAN_ID não configurado no ambiente.")

    try:
        # Gerar um ID único para esta matrícula pendente
        pending_enrollment_id = str(uuid.uuid4())
        
        # Armazenar os dados do aluno temporariamente
        PENDING_ENROLLMENTS[pending_enrollment_id] = {
            "nome": nome,
            "whatsapp": whatsapp,
            "email": email,
            "cursos_nomes": cursos_nomes,
            "status": "pending_payment" # Novo status
        }
        _log(f"Matrícula pendente ID: {pending_enrollment_id} armazenada.")

        # -------------------------------------------------------------
        # 1. Criar a Preferência de Assinatura no Mercado Pago
        # -------------------------------------------------------------
        # Você DEVE ter criado um PREAPPROVAL PLAN no painel do Mercado Pago
        # e usar o ID desse plano aqui.
        
        preapproval_data = {
            "reason": f"Assinatura: {curso_principal_nome}",
            "preapproval_plan_id": MP_PREAPPROVAL_PLAN_ID,
            "payer_email": email,
            # back_url é a URL para onde o Mercado Pago redireciona o usuário após o pagamento.
            # Deve ser a sua página de "Obrigado".
            "back_url": THANK_YOU_PAGE_URL, # Usando a variável hardcoded
            "external_reference": pending_enrollment_id # Usar o ID da matrícula pendente como referência externa
        }
        
        preapproval_response = mercadopago.preapproval.create(preapproval_data)
        
        if preapproval_response.status == 201: # 201 Created
            init_point = preapproval_response.body["init_point"]
            mp_preapproval_id = preapproval_response.body["id"]
            _log(f"Assinatura MP criada (ID: {mp_preapproval_id}). Redirect: {init_point}")
            
            # Atualizar o registro pendente com o ID da pré-aprovação do MP
            PENDING_ENROLLMENTS[pending_enrollment_id]["mp_preapproval_id"] = mp_preapproval_id
            
            # Retorna a URL de redirecionamento para o front-end
            return {
                "status": "ok",
                "message": "Matrícula iniciada, redirecionando para o pagamento.",
                "redirect_url": init_point,
                "pending_enrollment_id": pending_enrollment_id # Retornar para o front-end para referência
            }
        else:
            _log(f"Erro ao criar assinatura MP: {preapproval_response.status} - {preapproval_response.content}")
            # Limpar o registro pendente se a criação da assinatura falhar
            PENDING_ENROLLMENTS.pop(pending_enrollment_id, None)
            raise HTTPException(500, detail="Falha ao iniciar o pagamento com Mercado Pago.")

    except mercadopago.exceptions.MPRestException as mp_e:
        _log(f"Erro no SDK do Mercado Pago: {mp_e.status_code} - {mp_e.message}")
        PENDING_ENROLLMENTS.pop(pending_enrollment_id, None) # Limpar
        raise HTTPException(mp_e.status_code, detail=f"Erro no pagamento: {mp_e.message}")
    except Exception as e:
        _log(f"Erro geral na matrícula/pagamento: {str(e)}")
        PENDING_ENROLLMENTS.pop(pending_enrollment_id, None) # Limpar
        raise HTTPException(500, detail=f"Erro interno: {str(e)}")

# ──────────────────────────────────────────────────────────
# NOVO ENDPOINT: Gerar Descrição de Curso com Gemini API
# ──────────────────────────────────────────────────────────
@router.post("/generate-course-description")
async def generate_course_description(body: dict):
    course_name = body.get("course_name")

    if not course_name:
        raise HTTPException(400, detail="O nome do curso é obrigatório para gerar a descrição.")

    if not GEMINI_API_KEY:
        _log("ERRO: GEMINI_API_KEY não está configurada para a API Gemini.")
        raise HTTPException(500, detail="Serviço de geração de descrição indisponível. Chave de API não configurada.")

    prompt = f"Gere uma descrição envolvente e concisa para um curso de {course_name} focado em atrair novos alunos. Inclua 3-4 pontos-chave sobre o que o aluno aprenderá e os benefícios de se matricular. Use um tom entusiasmado e profissional. A descrição deve ter no máximo 150 palavras."

    # URL da API Gemini
    gemini_api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}]
    }

    headers = {
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(gemini_api_url, headers=headers, data=json.dumps(payload), timeout=30)
        response.raise_for_status() # Levanta um erro para status HTTP 4xx/5xx
        
        gemini_result = response.json()
        
        if gemini_result and gemini_result.get("candidates") and gemini_result["candidates"][0].get("content") and gemini_result["candidates"][0]["content"].get("parts"):
            generated_text = gemini_result["candidates"][0]["content"]["parts"][0]["text"]
            _log(f"Descrição Gemini gerada para '{course_name}': {generated_text[:50]}...")
            return {"status": "ok", "description": generated_text}
        else:
            _log(f"Resposta inesperada da API Gemini para '{course_name}': {gemini_result}")
            raise HTTPException(500, detail="Falha ao gerar descrição do curso (resposta inesperada da IA).")

    except requests.exceptions.RequestException as e:
        _log(f"Erro de conexão com a API Gemini para '{course_name}': {e}")
        raise HTTPException(500, detail=f"Erro de conexão ao gerar descrição: {e}")
    except Exception as e:
        _log(f"Erro geral ao gerar descrição para '{course_name}': {e}")
        raise HTTPException(500, detail=f"Erro interno ao gerar descrição: {e}")

