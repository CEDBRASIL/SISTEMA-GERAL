from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Importando apenas os módulos desejados
import cursos
import matricular
import secure


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
app.include_router(cursos.router, prefix="/api/cursos", tags=["Cursos"])
app.include_router(matricular.router, prefix="/api/matricula", tags=["Matrícula"])
app.include_router(secure.router, prefix="/api/auth", tags=["Autenticação"])


# Endpoint de status
@app.get("/api")
def status():
    return {"status": "API CED ativa"}
