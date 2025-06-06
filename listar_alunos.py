import os
import requests
import json


OM_BASE = os.getenv("OM_BASE")
BASIC_B64 = os.getenv("BASIC_B64")
UNIDADE_ID = os.getenv("UNIDADE_ID")


def listar_alunos(page: int = 1, size: int = 1000):
    if not OM_BASE or not BASIC_B64 or not UNIDADE_ID:
        raise RuntimeError("Variáveis de ambiente OM não configuradas.")

    url = f"{OM_BASE}/alunos?page={page}&size={size}&id_unidade={UNIDADE_ID}"
    r = requests.get(url, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=10)
    if r.ok and r.json().get("status") == "true":
        return r.json()
    raise RuntimeError(f"Falha ao obter lista de alunos: HTTP {r.status_code}")


def obter_todos_alunos() -> list:
    alunos = []
    page = 1
    while True:
        dados = listar_alunos(page=page)
        for item in dados.get("data", []):
            alunos.append(item)
        pagina = dados.get("pagina", {})
        total = int(pagina.get("total", 0))
        size = int(pagina.get("size", 1000))
        if page * size >= total:
            break
        page += 1
    return alunos


if __name__ == "__main__":
    try:
        lista = obter_todos_alunos()
        print(json.dumps({"alunos": lista}, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"Erro: {e}")
