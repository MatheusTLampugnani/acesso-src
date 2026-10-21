"""Integração com a tabela crachas no Supabase: leitura, busca e atualização de senha/email."""
import json
import re
import urllib.parse
import urllib.request

from .config import config

CRACHA = re.compile(r"^[A-Za-z0-9._@-]{1,60}$")
POR_PAGINA = 1000


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


def buscar_crachas() -> list[dict]:
    """Retorna a lista completa de colaboradores do Supabase com todos os campos estruturados."""
    headers = _headers()
    headers["Range-Unit"] = "items"
    colunas = "id,nome_completo,setor,unidade,admin,email,senha_hash"
    resultado, inicio = [], 0

    while True:
        headers["Range"] = f"{inicio}-{inicio + POR_PAGINA - 1}"
        pedido = urllib.request.Request(
            f"{config.SUPABASE_URL}/rest/v1/{config.TABELA_CRACHAS}?select={colunas}&order=id",
            headers=headers,
        )
        try:
            with urllib.request.urlopen(pedido, timeout=20) as resposta:
                pagina = json.load(resposta)
        except Exception as erro:
            raise ErroCrachas(f"Não foi possível ler os crachás do Supabase: {erro}") from erro

        for linha in pagina:
            cracha = str(linha.get("id") or "").strip()
            if CRACHA.match(cracha):
                resultado.append({
                    "cracha": cracha,
                    "nome": (linha.get("nome_completo") or "").strip()[:120],
                    "setor": (linha.get("setor") or "").strip() if linha.get("setor") else "",
                    "unidade": linha.get("unidade"),
                    "admin": bool(linha.get("admin")),
                    "email": (linha.get("email") or "").strip().lower() if linha.get("email") else "",
                    "senha_hash": (linha.get("senha_hash") or "").strip(),
                })
        if len(pagina) < POR_PAGINA:
            return resultado
        inicio += POR_PAGINA


def buscar_cracha_no_supabase(termo: str) -> dict | None:
    """Busca um colaborador no Supabase diretamente pelo número de crachá ou pelo e-mail."""
    if not config.SUPABASE_URL or not config.SUPABASE_CHAVE:
        return None
    termo = termo.strip()
    if not termo:
        return None

    headers = _headers()
    colunas = "id,nome_completo,setor,unidade,admin,email,senha_hash"

    # Se for numérico, busca por id.eq ou email.eq; se tiver @, busca por email
    if termo.isdigit():
        filtro = f"or=(id.eq.{termo},email.eq.{urllib.parse.quote(termo)})"
    else:
        filtro = f"email.eq.{urllib.parse.quote(termo)}"

    url = f"{config.SUPABASE_URL}/rest/v1/{config.TABELA_CRACHAS}?select={colunas}&{filtro}&limit=1"
    pedido = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(pedido, timeout=10) as resposta:
            linhas = json.load(resposta)
            if linhas:
                linha = linhas[0]
                return {
                    "cracha": str(linha.get("id")),
                    "nome": (linha.get("nome_completo") or "").strip()[:120],
                    "setor": (linha.get("setor") or "").strip() if linha.get("setor") else "",
                    "unidade": linha.get("unidade"),
                    "admin": bool(linha.get("admin")),
                    "email": (linha.get("email") or "").strip().lower() if linha.get("email") else "",
                    "senha_hash": (linha.get("senha_hash") or "").strip(),
                }
    except Exception:
        pass
    return None


def atualizar_usuario_supabase(
    cracha_id: int | str,
    nome: str | None = None,
    setor: str | None = None,
    unidade: int | None = None,
    admin: bool | None = None,
    email: str | None = None,
    senha_hash: str | None = None,
) -> bool:
    """Atualiza dados do colaborador diretamente na tabela crachas do Supabase."""
    if not config.SUPABASE_URL or not config.SUPABASE_CHAVE:
        return False
    corpo = {}
    if nome is not None:
        corpo["nome_completo"] = nome.strip()
    if setor is not None:
        corpo["setor"] = setor.strip()
    if unidade is not None:
        corpo["unidade"] = unidade
    if admin is not None:
        corpo["admin"] = bool(admin)
    if email is not None:
        corpo["email"] = email.strip().lower()
    if senha_hash is not None:
        corpo["senha_hash"] = senha_hash

    if not corpo:
        return True

    url = f"{config.SUPABASE_URL}/rest/v1/{config.TABELA_CRACHAS}?id=eq.{cracha_id}"
    req = urllib.request.Request(
        url,
        data=json.dumps(corpo).encode("utf-8"),
        headers=_headers(),
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resposta:
            return resposta.status in (200, 204)
    except Exception:
        return False


def criar_usuario_supabase(
    cracha_id: int | str,
    nome: str,
    setor: str = "",
    unidade: int | None = None,
    admin: bool = False,
    email: str = "",
    senha_hash: str = "",
) -> bool:
    """Insere ou atualiza um colaborador na tabela crachas do Supabase."""
    if not config.SUPABASE_URL or not config.SUPABASE_CHAVE:
        return False
    # Converte para int se possível (id da tabela crachas é numérico)
    cid = int(cracha_id) if str(cracha_id).isdigit() else cracha_id
    corpo = {
        "id": cid,
        "nome_completo": nome.strip(),
        "setor": setor.strip() if setor else None,
        "unidade": unidade if unidade is not None else 1001,
        "admin": bool(admin),
        "email": email.strip().lower() if email else None,
        "senha_hash": senha_hash.strip() if senha_hash else None,
    }
    headers = _headers()
    headers["Prefer"] = "resolution=merge-duplicates"
    url = f"{config.SUPABASE_URL}/rest/v1/{config.TABELA_CRACHAS}"
    req = urllib.request.Request(
        url,
        data=json.dumps([corpo]).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resposta:
            return resposta.status in (200, 201, 204)
    except Exception:
        return False


def excluir_usuario_supabase(cracha_id: int | str) -> bool:
    """Exclui um colaborador da tabela crachas do Supabase se necessário."""
    if not config.SUPABASE_URL or not config.SUPABASE_CHAVE:
        return False
    url = f"{config.SUPABASE_URL}/rest/v1/{config.TABELA_CRACHAS}?id=eq.{cracha_id}"
    req = urllib.request.Request(url, headers=_headers(), method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=10) as resposta:
            return resposta.status in (200, 204)
    except Exception:
        return False

