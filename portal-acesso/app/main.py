"""Aplicação FastAPI do Portal de Acesso."""
import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse

from . import banco
from .config import config
from .crachas import buscar_crachas
from .rotas import router

log = logging.getLogger(__name__)
PORTAL_VITRINE = Path(__file__).resolve().parent.parent / "deploy" / "portal-vitrine.html"


def _sincronizar_crachas() -> None:
    """Traz nome, setor, unidade e e-mail da tabela crachas e cria quem ainda não está no Portal, sem nenhum sistema."""
    try:
        crachas = buscar_crachas()
        with banco.conexao() as con:
            resultado = banco.importar_crachas(con, crachas, [])
            banco.registrar(con, "sistema", "sincronizou_supabase", f"{resultado['novos']} novos, {resultado['existentes']} atualizados")
    except Exception as erro:  # o Portal funciona sem o Supabase
        log.warning("Não sincronizou com a tabela crachas: %s", erro)


@asynccontextmanager
async def ciclo_de_vida(_app: FastAPI):
    banco.iniciar()
    if config.SUPABASE_URL and config.SUPABASE_CHAVE:
        threading.Thread(target=_sincronizar_crachas, daemon=True).start()
    yield


app = FastAPI(title="Portal de Acesso", docs_url=None, redoc_url=None, openapi_url=None, lifespan=ciclo_de_vida)
app.include_router(router)


@app.get(config.BASE, include_in_schema=False)
def sem_barra():
    return RedirectResponse(config.BASE + "/")


@app.get("/", include_in_schema=False)
def vitrine_raiz():
    if PORTAL_VITRINE.is_file():
        return FileResponse(PORTAL_VITRINE, headers={"Cache-Control": "no-cache"})
    return RedirectResponse(config.BASE + "/")
