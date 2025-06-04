de fastapi importar APIRouter, Solicitação, Depende , HTTPException
de fastapi.responses importar JSONResponse
importar sistema operacional
importar json
solicitações
 de importação
de cursos importar CURSOS_OM

roteador = APIRouter()

OM_BASE = os.getenv( "OM_BASE" )
BASIC_B64 = os.getenv( "BASIC_B64" )
CHATPRO_TOKEN = os.getenv( "CHATPRO_TOKEN" )
CHATPRO_URL = os.getenv( "CHATPRO_URL" )
UNIDADE_ID = os.getenv( "UNIDADE_ID" )
DISCORD_WEBHOOK = os.getenv( "DISCORD_WEBHOOK" )

TOKEN_UNIDADE = Nenhum


def enviar_log_discord ( mensagem: str ) -> Nenhum :
 
    se não for DISCORD_WEBHOOK:
 
        print ( "Discord webhook não configurado" )
        retornar
    tentar :
        resp = requests.post(DISCORD_WEBHOOK, json={ "content" : mensagem})
        se resp.status_code != 204 :
            print ( "❌ Falha ao enviar log para Discord:" , resp.text)
    exceto Exceção como e:
        print ( "❌ Erro ao enviar log para Discord:" , str (e))


def obter_token_unidade () -> str | Nenhum :
    global TOKEN_UNIDADE
    tentar :
        resp= solicitações.obter(
            f" {OM_BASE} /unidades/token/ {UNIDADE_ID} " ,
            cabeçalhos={ "Autorização" : f"Básico {BASIC_B64} " },
        )
        dados = resp.json()
        se resp.ok e dados.get( "status" ) == "true" :
  
            TOKEN_UNIDADE = dados[ "dados" ][ "token" ]
            enviar_log_discord( "🔁 Token atualizado com sucesso!" )
            retornar TOKEN_UNIDADE
        enviar_log_discord( f"❌ Erro ao obter token: {dados} " )
    exceto Exceção como e:
        enviar_log_discord( f"❌ Exceção ao obter token: {e} " )
    retornar Nenhum 


def buscar_aluno_por_cpf ( cpf: str ) -> str | Nenhum :
 
    tentar :
        resp = solicitações.obter(
            f" {OM_BASE} /alunos" ,
            cabeçalhos={ "Autorização" : f"Básico {BASIC_B64} " },
            parâmetros={ "cpf" : cpf},
        )
        se não resp.ok:
 
            enviar_log_discord( f"❌ Falha ao buscar aluno: {resp.text} " )
            retornar Nenhum 
        alunos = resp.json().get( "dados" , [])
        se não alunos:
 
            retornar Nenhum 
        retornar alunos[ 0 ].get( "id" )
    exceto Exceção como e:
        enviar_log_discord( f"❌ Erro ao buscar aluno: {e} " )
        retornar Nenhum 


def obter_cursos_ids ( nome_plano: str ):
 
    """Busca cursos ignorando diferença de caixa."""
    chave = next ((k para k em CURSOS_OM se k.lower() == nome_plano.lower()), Nenhum )
    return CURSOS_OM.get(chave) if chave else Nenhuma 


def log_request_info ( solicitação: Solicitação ) -> Nenhum :
 
    mensagem = (
        f"\n 📥 Requisição recebida:\n"
        f" 🔗 URL completa: {request.url} \n"
        f" 📍 Método: {request.method} \n"
        f" 📦 Cabeçalhos: { dict (request.headers)} "
    )
    imprimir (mensagem)
    enviar_log_discord(mensagem)


router.dependencies.append(Depende(log_request_info))

# Inicializa token ao importar o módulo
TOKEN_UNIDADE = obter_token_unidade()


@router.get( "/seguro" )
async def secure_check ():
  
    novo = obter_token_unidade()
    se novo:
        return "🔐 Token atualizado com sucesso via /secure" 
    return JSONResponse(content= "❌ Falha ao atualizar token via /secure" , status_code= 500 )


@router.post( "/" )
async def webhook ( carga útil: dict ):
  
    tentar :
        evento = payload.get( "webhook_event_type" )

        se evento == "pedido_reembolsado" :
            cliente = payload.get( "Cliente" , {})
            cpf = cliente.obter( "CPF" , "" ).substituir( "." , "" ).substituir( "-" , "" )
            se não for cpf:
 
                msg = "❌ CPF do aluno não encontrado sem carga de reembolso."
                enviar_log_discord(msg)
                return JSONResponse(status_code= 400 , content={ "error" : "CPF do aluno não encontrado." })

            aluno_id = buscar_aluno_por_cpf(cpf)
            se não for aluno_id:
 
                msg = "❌ ID do aluno não encontrado para o CPF fornecido."
                enviar_log_discord(msg)
                return JSONResponse(status_code= 400 , content={ "error" : "ID do aluno não encontrado." })

            resp_exclusao = requests.delete(
                f" {OM_BASE} /alunos/ {aluno_id} " ,
                cabeçalhos={ "Autorização" : f"Básico {BASIC_B64} " },
            )
            se não resp_exclusao.ok:
 
                mensagem = (
                    f"❌ ERRO AO EXCLUIR ALUNO\nAluno ID: {aluno_id} \n🔧 Detalhes: {resp_exclusao.text} "
                )
                enviar_log_discord(msg)
                return JSONResponse(status_code= 500 , content={ "error" : "Falha ao excluir aluno" , " detalhes" : resp_exclusao.text})

            msg = f"✅ Conta do aluno com ID {aluno_id} arquivo com sucesso."
            enviar_log_discord(msg)
            return { "message" : "Conta do aluno com sucesso." }

        se evento != "order_approved" :
            return { "message" : "Evento ignorado" }

        cliente = payload.get( "Cliente" , {})
        nome = cliente.get( "nome_completo" )
        cpf = cliente.obter( "CPF" , "" ).substituir( "." , "" ).substituir( "-" , "" )
        email = cliente.get( "email" )
        celular = cliente.get( "mobile" ) ou "(00) 00000-0000" 
        cidade = cliente.get( "cidade" ) ou "" 
        estado = cliente.get( "estado" ) ou "" 
        endereco = (cliente.get( "rua" ) ou "" ) + ", " + str (cliente.get( "número" ) ou "" )
  
        bairro = cliente.get( "bairro" ) ou "" 
        complemento = customer.get( "complemento" ) ou "" 
        cep = cliente.get( "cep" ) ou "" 

        plano_assinatura = payload.get( "Assinatura" , {}).get( "plano" , {}).get( "nome" )
        cursos_ids = obter_cursos_ids(plano_assinatura)
        se não cursos_ids:
 
            return JSONResponse(status_code= 400 , content={ "error" : f"Plano ' {plano_assinatura} ' não mapeado." })

        dados_aluno = {
            "token" : TOKEN_UNIDADE,
            "nome" : nome,
            "data_nascimento" : "2000-01-01" ,
            "e-mail" : e-mail,
            "fone" : celular,
            "senha" : "123456" ,
            "celular" : celular,
            "doc_cpf" : cpf,
            "doc_rg" : "00000000000" ,
            "pais" : "Brasil" ,
            "uf" : estado,
            "cidade" : cidade,
            "endereco" : endereco,
            "complemento" : complemento,
            "bairro" : bairro,
            "cep" : cep,
        }

        resp_cadastro = requests.post(
            f" {OM_BASE} /alunos" ,
            dados=dados_aluno,
            cabeçalhos={ "Autorização" : f"Básico {BASIC_B64} " },
        )
        aluno_resposta = resp_cadastro.json()
        se não resp_cadastro.ok ou aluno_response.get( "status" ) != "true" :
 
            msg = f"❌ ERRO NO CADASTRO: {resp_cadastro.text} "
            enviar_log_discord(msg)
            return JSONResponse(status_code= 500 , content={ "error" : "Falha ao criar aluno" , "detalhes " : resp_cadastro.text})

        aluno_id = aluno_response.get( "dados" , {}).get( "id" )
        se não for aluno_id:
 
            msg = "❌ ID do aluno não retornado!"
            enviar_log_discord(msg)
            return JSONResponse(status_code= 500 , content={ "error" : "ID do aluno não encontrado na resposta de cadastro." })

        dados_matricula = {
            "token" : TOKEN_UNIDADE,
            "cursos" : "," .join( str (c) para c em cursos_ids),
        }

        resp_matricula = requests.post(
            f" {OM_BASE} /alunos/matricula/ {aluno_id} " ,
            dados=dados_matricula,
            cabeçalhos={ "Autorização" : f"Básico {BASIC_B64} " },
        )
        se não resp_matricula.ok ou resp_matricula.json().get( "status" ) != "true" :
 
            msg = f"❌ ERRO NA MATRÍCULA\nAluno ID: {aluno_id} \n🔧 Detalhes: {resp_matricula.text} "
            enviar_log_discord(msg)
            return JSONResponse(status_code= 500 , content={ "error" : "Falha ao matricular" , "detalhes" : resp_matricula.text})

        numero_whatsapp = "55" + "" .join( filter ( str .isdigit, celular))[- 11 :]
        mensagem = (
            f"Oii {nome} , Seja bem Vindo/a Ao CED BRASIL\n\n"
            f"📦 *Plano adquirido:* {plano_assinatura} \n\n"
            "*Seu acesso:*\n"
            f"Login: * {cpf} *\n"
            "Senha: *123456*\n\n"
            "🌐 *Portal do aluno:* https://ead.cedbrasilia.com.br\n"
            "📲 *Aplicativo Android:* https://play.google.com/store/apps/details?id=br.com.om.app&hl=pt_BR\n"
            "📱 *Aplicativo iOS:* https://apps.apple.com/br/app/meu-app-de-cursos/id1581898914\n\n"
        )

        resp_whatsapp = solicitações.post(
            URL_DO_CHATPRO,
            json={ "número" : numero_whatsapp, "mensagem" : mensagem},
            cabeçalhos={ "Autorização" : CHATPRO_TOKEN, "Tipo de conteúdo" : "application/json" , "Aceitar" : "application/json" },
        )
        se resp_whatsapp.status_code != 200 :
            enviar_log_discord( f"❌ Erro ao enviar WhatsApp: {resp_whatsapp.text} " )
        outro :
            enviar_log_discord( "✅ Mensagem enviada com sucesso" )

        retornar {
            "message" : "Aluno cadastrado, matriculado e notificado com sucesso!" ,
            "aluno_id" : aluno_id,
            "cursos" : cursos_ids,
        }

    exceto Exceção como e:
        msg = f"❌ EXCEÇÃO NO PROCESSAMENTO: {e} "
        enviar_log_discord(msg)
        gerar HTTPException(status_code= 500 , detail= str (e))
