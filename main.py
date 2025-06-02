from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Importando apenas os módulos desejados
import cursos
import matricular
import secure
import assinaturamp
import pre_matricula



app = FastAPI(title="CED API - Cursos e Matrícula", version="1.0")

# Middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Roteadores incluídos
app.include_router(cursos.router, prefix="/cursos", tags=["Cursos"])
app.include_router(matricular.router, prefix="/matricular", tags=["Matrícula"])
app.include_router(secure.router, tags=["Autenticação"])
app.include_router(assinaturamp.router, tags=["Assinatura"])
app.include_router(pre_matricula.router, tags=["Pré Matrícula"])



# Endpoint de status
@app.get("/api")
def status():
    return {"status": "API Operando OK - CED API 1.0 made by @furionnzxt"}
