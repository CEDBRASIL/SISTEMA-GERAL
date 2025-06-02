from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.routers import assinatura, assinatura_teste, cursos, matricula, webhook, autenticacao

app = FastAPI(title="CED Plataforma Integrada", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cursos.router, prefix="/api/cursos", tags=["Cursos"])
app.include_router(matricula.router, prefix="/api/matricula", tags=["Matrícula"])
app.include_router(autenticacao.router, prefix="/api/auth", tags=["Autenticação"])
app.include_router(assinatura.router, prefix="/api/assinatura", tags=["Assinatura"])
app.include_router(assinatura_teste.router, prefix="/api/teste", tags=["Assinatura Teste"])
app.include_router(webhook.router, prefix="/webhook", tags=["Webhooks"])

app.mount("/", StaticFiles(directory="static", html=True), name="static")

@app.get("/api")
def status():
    return {"status": "API CED pronta"}
