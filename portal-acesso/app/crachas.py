"""Integração com a tabela crachas do Supabase: leitura e cadastro de colaboradores.

Entre o Portal e a tabela circulam só nome, setor, unidade e e-mail. Admin e senha do Portal ficam no banco local:
o campo admin de crachas vale para o Bobinas, o VisionStock e o Mín/Máx, e senha não sai do Portal.
"""
import json
import re
import time
import urllib.parse
import urllib.request

from .config import config

CRACHA = re.compile(r"^[A-Za-z0-9._@-]{1,60}$")
NUMERO = re.compile(r"^\d{1,18}$")  # o id da tabela crachas é bigint
POR_PAGINA = 1000
COLUNAS = "id,nome_completo,setor,unidade,email"
# A tela de entrar é aberta para a internet: quem não está em crachas só é consultado de novo depois deste tempo
SEGUNDOS_SEM_CONSULTAR = 300
_ausentes: dict[str, float] = {}


class ErroCrachas(Exception):
    pass


def _headers() -> dict[str, str]:
    if not config.SUPABASE_URL or not config.SUPABASE_CHAVE:
        raise ErroCrachas("Supabase não configurado (ACESSO_SUPABASE_URL e ACESSO_SUPABASE_CHAVE).")
    return {
        "apikey": config.SUPABASE_CHAVE,
        "Authorization": f"Bearer {config.SUPABASE_CHAVE}",
        "Content-Type": "application/json",
    }


def _colaborador(linha: dict) -> dict:
    return {
        "cracha": str(linha.get("id") or "").strip(),
        "nome": (linha.get("nome_completo") or "").strip()[:120],
        "setor": (linha.get("setor") or "").strip(),
        "unidade": linha.get("unidade"),
        "email": (linha.get("email") or "").strip().lower(),
    }


def buscar_crachas() -> list[dict]:
    """Retorna a lista completa de colaboradores do Supabase."""
    headers = _headers()
    headers["Range-Unit"] = "items"
    resultado, inicio = [], 0

    while True:
        headers["Range"] = f"{inicio}-{inicio + POR_PAGINA - 1}"
        pedido = urllib.request.Request(
            f"{config.SUPABASE_URL}/rest/v1/{config.TABELA_CRACHAS}?select={COLUNAS}&order=id",
            headers=headers,
        )
        try:
            with urllib.request.urlopen(pedido, timeout=20) as resposta:
                pagina = json.load(resposta)
        except Exception as erro:
            raise ErroCrachas(f"Não foi possível ler os crachás do Supabase: {erro}") from erro

        resultado += [c for c in map(_colaborador, pagina) if CRACHA.match(c["cracha"])]
        if len(pagina) < POR_PAGINA:
            return resultado
        inicio += POR_PAGINA


def buscar_cracha_no_supabase(termo: str) -> dict | None:
    """Busca um colaborador pelo número do crachá ou pelo e-mail. E-mail repetido em mais de um crachá não vale."""
    termo = termo.strip().lower()
    if not config.SUPABASE_URL or not config.SUPABASE_CHAVE:
        return None
    if NUMERO.match(termo):
        filtro = f"id=eq.{termo}"
    elif "@" in termo and len(termo) <= 120:
        filtro = f"email=eq.{urllib.parse.quote(termo)}"
    else:
        return None
    if time.monotonic() - _ausentes.get(termo, -SEGUNDOS_SEM_CONSULTAR) < SEGUNDOS_SEM_CONSULTAR:
        return None

    url = f"{config.SUPABASE_URL}/rest/v1/{config.TABELA_CRACHAS}?select={COLUNAS}&{filtro}&limit=2"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=_headers()), timeout=10) as resposta:
            linhas = json.load(resposta)
    except Exception:  # sem o Supabase, quem já está no Portal continua entrando
        return None
    if len(linhas) == 1:
        return _colaborador(linhas[0])
    if len(_ausentes) > 5000:
        _ausentes.clear()
    _ausentes[termo] = time.monotonic()
    return None


def atualizar_usuario_supabase(
    cracha_id: int | str,
    nome: str | None = None,
    setor: str | None = None,
    unidade: int | None = None,
    email: str | None = None,
) -> bool:
    """Copia o cadastro para a tabela crachas. Login que não é número não está na tabela e não precisa de cópia."""
    corpo = {}
    if nome is not None:
        corpo["nome_completo"] = nome.strip()
    if setor is not None:
        corpo["setor"] = setor.strip()
    if unidade is not None:
        corpo["unidade"] = unidade
    if email is not None:
        corpo["email"] = email.strip().lower()

    cracha = str(cracha_id).strip()
    if not corpo or not NUMERO.match(cracha) or not config.SUPABASE_URL or not config.SUPABASE_CHAVE:
        return True

    req = urllib.request.Request(
        f"{config.SUPABASE_URL}/rest/v1/{config.TABELA_CRACHAS}?id=eq.{cracha}",
        data=json.dumps(corpo).encode("utf-8"),
        headers=_headers(),
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resposta:
            return resposta.status in (200, 204)
    except Exception:
        return False


def garantir_cracha(cracha: str, nome: str, setor: str = "", unidade: int | None = None, email: str = "") -> bool:
    """Cadastra o crachá no Supabase se ainda não existir, para os sistemas que conferem a tabela
    (ex.: Bobinas) reconhecerem quem foi criado direto no portal. Crachá que já existe não é alterado.
    Retorna True se cadastrou; False se já existia, se o login não é número ou se o Supabase não está configurado."""
    cracha = cracha.strip()
    if not NUMERO.match(cracha) or not config.SUPABASE_URL or not config.SUPABASE_CHAVE:
        return False
    corpo = {"id": int(cracha), "nome_completo": nome.strip()[:120]}
    if setor.strip():
        corpo["setor"] = setor.strip()
    if unidade is not None:
        corpo["unidade"] = unidade
    if email.strip():
        corpo["email"] = email.strip().lower()
    pedido = urllib.request.Request(
        f"{config.SUPABASE_URL}/rest/v1/{config.TABELA_CRACHAS}?on_conflict=id",
        data=json.dumps([corpo]).encode(),
        method="POST",
        headers={
            "apikey": config.SUPABASE_CHAVE,
            "Authorization": f"Bearer {config.SUPABASE_CHAVE}",
            "Content-Type": "application/json",
            # Se já existe, não mexe (setor, unidade e admin continuam como estão no Supabase)
            "Prefer": "resolution=ignore-duplicates,return=representation",
        },
    )
    try:
        with urllib.request.urlopen(pedido, timeout=10) as resposta:
            return bool(json.load(resposta))
    except Exception as erro:  # rede, chave sem permissão de escrita, tabela inexistente
        raise ErroCrachas(f"Não foi possível cadastrar o crachá {cracha} no Supabase: {erro}") from erro
