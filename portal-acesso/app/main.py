"""Aplicação FastAPI do Portal de Acesso."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from . import banco
from .config import config
from .rotas import router


@asynccontextmanager
async def ciclo_de_vida(_app: FastAPI):
    banco.iniciar()
    if config.SUPABASE_URL and config.SUPABASE_CHAVE:
        import threading
        def _sincronizar_fundo():
            try:
                with banco.conexao() as con:
                    banco.sincronizar_com_supabase(con)
            except Exception:
                pass
        threading.Thread(target=_sincronizar_fundo, daemon=True).start()
    yield



app = FastAPI(title="Portal de Acesso", docs_url=None, redoc_url=None, openapi_url=None, lifespan=ciclo_de_vida)
app.include_router(router)


@app.get(config.BASE, include_in_schema=False)
def sem_barra():
    return RedirectResponse(config.BASE + "/")
