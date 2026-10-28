"""Rotas do Portal de Acesso: login, verificação para o Nginx (auth_request) e painel de administração."""
import hmac
import ipaddress
import re
import threading
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from . import banco
from .config import config
from .crachas import ErroCrachas, buscar_crachas, garantir_cracha
from .seguranca import TravaLogin, conferir_senha, gerar_hash_senha, hash_token, novo_codigo, novo_token, senha_valida

ESTATICOS = Path(__file__).parent / "static"
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
LOGIN = re.compile(r"^[A-Za-z0-9._@-]{2,60}$")

router = APIRouter(prefix=config.BASE)
trava = TravaLogin(config.MAX_TENTATIVAS, config.TRAVA_MINUTOS)


# ---------- Modelos ----------

class Entrada(BaseModel):
    usuario: str = Field(max_length=60)
    senha: str = Field(max_length=200)
    volta: str = ""


class NovoUsuario(BaseModel):
    usuario: str
    nome: str = Field(min_length=1, max_length=120)
    senha: str = ""  # vazio = a pessoa cria a senha no primeiro acesso
    admin: bool = False
    sistemas: list[str] = []


class AlteraUsuario(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=120)
    senha: str | None = None  # "" = apaga a senha e a pessoa cria outra no próximo acesso
    admin: bool | None = None
    ativo: bool | None = None
    sistemas: list[str] | None = None


class Sistema(BaseModel):
    slug: str
    nome: str = Field(min_length=1, max_length=120)
    caminho: str = Field(min_length=2, max_length=200)
    ordem: int = 0
    aberto: bool = False  # liberado para qualquer usuário logado


class PrimeiroAcesso(BaseModel):
    usuario: str = Field(max_length=60)
    senha: str = Field(max_length=200)
    codigo: str = Field(default="", max_length=12)  # só pedido de fora da empresa
    volta: str = ""


class Identificacao(BaseModel):
    usuario: str = Field(max_length=60)


class Importacao(BaseModel):
    sistemas: list[str] = []


class TrocaSenha(BaseModel):
    atual: str
    nova: str


# ---------- Utilitários ----------

def _ip(request: Request) -> str:
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "?")


REDES_DA_EMPRESA = [ipaddress.ip_network(r) for r in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10")]


def _interno(request: Request) -> bool:
    """Rede da empresa ou Tailscale. O Nginx põe o IP de quem chamou em X-Real-IP (o cliente não consegue trocar).
    Pela Tailscale o pedido chega do próprio servidor (127.0.0.1) com Tailscale-User-Login; pelo Funnel (internet)
    também chega de 127.0.0.1, mas sem esse cabeçalho, que a Tailscale apaga dos pedidos vindos de fora."""
    try:
        ip = ipaddress.ip_address(_ip(request))
    except ValueError:
        return False
    if ip.is_loopback:
        return bool(request.headers.get("tailscale-user-login"))
    return any(ip in rede for rede in REDES_DA_EMPRESA)


def _usuario_logado(request: Request, con):
    token = request.cookies.get(config.COOKIE_NOME)
    return banco.usuario_da_sessao(con, hash_token(token)) if token else None


def volta_segura(volta: str) -> str:
    """Só aceita caminhos do próprio servidor (evita redirecionar para sites externos)."""
    volta = (volta or "").strip()
    if not volta.startswith("/") or volta.startswith("//") or "\\" in volta or volta.startswith(config.BASE + "/entrar"):
        return "/"
    return volta


def exige_cabecalho(request: Request) -> None:
    # Formulários de outros sites não conseguem mandar este cabeçalho (proteção contra CSRF)
    if request.headers.get("x-portal") != "1":
        raise HTTPException(403, "Requisição sem o cabeçalho do portal.")


def exige_login(request: Request):
    with banco.conexao() as con:
        usuario = _usuario_logado(request, con)
    if not usuario:
        raise HTTPException(401, "Faça login.")
    return usuario


def exige_admin(usuario=Depends(exige_login)):
    if not usuario["admin"]:
        raise HTTPException(403, "Apenas administradores.")
    return usuario


# Em modo observar, registra no histórico quem SERIA barrado (uma vez a cada 10 min por pessoa/sistema)
_ja_registrado: dict[tuple, float] = {}
_lock_registro = threading.Lock()


def _registrar_negado(con, quem: str, sistema: str, motivo: str, uri: str) -> None:
    chave = (quem, sistema, motivo)
    with _lock_registro:
        if time.time() - _ja_registrado.get(chave, 0) < 600:
            return
        _ja_registrado[chave] = time.time()
    tipo = "seria_negado" if config.MODO == "observar" else "negado"
    banco.registrar(con, quem, tipo, f"{sistema}: {motivo} ({uri[:150]})")


# ---------- Verificação usada pelo Nginx (auth_request) ----------

@router.api_route(
    "/api/verificar/{sistema}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"], include_in_schema=False
)
def verificar(sistema: str, request: Request):
    """200 = libera; 401 = sem login (Nginx manda para a tela de login); 403 = sem permissão."""
    uri = request.headers.get("x-original-uri", "")
    with banco.conexao() as con:
        usuario = _usuario_logado(request, con)
        if usuario is None:
            codigo, quem, motivo = 401, f"anônimo {_ip(request)}", "sem login"
        elif not banco.sistema_existe(con, sistema):
            codigo, quem, motivo = 403, usuario["usuario"], "sistema não cadastrado no portal"
        elif not banco.pode_acessar(con, usuario, sistema):
            codigo, quem, motivo = 403, usuario["usuario"], "sem permissão"
        else:
            return Response(status_code=200, headers={"X-Usuario": usuario["usuario"]})
        _registrar_negado(con, quem, sistema, motivo, uri)
    if config.MODO == "observar":
        return Response(status_code=200)
    return Response(status_code=codigo)


# ---------- Login / sessão ----------

@router.post("/api/identificar", dependencies=[Depends(exige_cabecalho)])
def identificar(dados: Identificacao, request: Request):
    """1º passo da tela de entrar: diz se o crachá ainda precisa criar a senha.
    Crachá inexistente responde igual a quem já tem senha, para não revelar quem está cadastrado."""
    if trava.travado(f"{_ip(request)}|{dados.usuario.strip().lower()}"):
        raise HTTPException(429, f"Muitas tentativas. Aguarde {config.TRAVA_MINUTOS} minutos.")
    with banco.conexao() as con:
        usuario = banco.buscar_por_login(con, dados.usuario)
    criar = bool(usuario and usuario["ativo"] and usuario["senha_hash"] == "")
    return {"criar_senha": criar, "precisa_codigo": criar and not _interno(request)}


@router.post("/api/entrar", dependencies=[Depends(exige_cabecalho)])
def entrar(dados: Entrada, request: Request):
    chave = f"{_ip(request)}|{dados.usuario.strip().lower()}"
    if trava.travado(chave):
        raise HTTPException(429, f"Muitas tentativas. Aguarde {config.TRAVA_MINUTOS} minutos.")
    with banco.conexao() as con:
        usuario = banco.buscar_por_login(con, dados.usuario)
        if usuario and usuario["ativo"] and usuario["senha_hash"] == "":
            return JSONResponse(
                {"detail": "Primeiro acesso: crie a sua senha.", "criar_senha": True, "precisa_codigo": not _interno(request)},
                status_code=409,
            )
        if not usuario or not usuario["ativo"] or not conferir_senha(dados.senha, usuario["senha_hash"]):
            trava.erro(chave)
            banco.registrar(con, dados.usuario.strip()[:60], "login_falhou", _ip(request))
            con.commit()  # sem isto o erro abaixo desfaz o registro
            raise HTTPException(401, "Usuário ou senha incorretos.")
        trava.limpar(chave)
        return _abrir_sessao(con, usuario, request, dados.volta, "login")


def _abrir_sessao(con, usuario, request: Request, volta: str, evento: str) -> JSONResponse:
    token = novo_token()
    banco.criar_sessao(con, hash_token(token), usuario["id"])
    banco.registrar(con, usuario["usuario"], evento, _ip(request))
    resposta = JSONResponse({"ok": True, "volta": volta_segura(volta)})
    resposta.set_cookie(
        config.COOKIE_NOME, token, max_age=int(config.SESSAO_HORAS * 3600), path="/",
        httponly=True, samesite="lax", secure=config.COOKIE_SEGURO,
    )
    return resposta


@router.post("/api/primeiro-acesso", dependencies=[Depends(exige_cabecalho)])
def primeiro_acesso(dados: PrimeiroAcesso, request: Request):
    """Quem ainda não tem senha (crachá importado ou senha zerada pelo admin) cria a própria e já entra.
    De fora da empresa (internet) precisa também do código de primeiro acesso que o administrador vê no painel:
    sem ele, qualquer pessoa que acertasse o número de um crachá criaria a senha no lugar do dono."""
    chave = f"{_ip(request)}|{dados.usuario.strip().lower()}"
    if trava.travado(chave):
        raise HTTPException(429, f"Muitas tentativas. Aguarde {config.TRAVA_MINUTOS} minutos.")
    if erro := senha_valida(dados.senha):
        raise HTTPException(400, erro)
    with banco.conexao() as con:
        usuario = banco.buscar_por_login(con, dados.usuario)
        if not usuario or not usuario["ativo"] or usuario["senha_hash"] != "":
            raise HTTPException(400, "Este usuário já tem senha. Use a tela de entrar.")
        if not _interno(request):
            codigo = usuario["codigo_acesso"]
            if not codigo or not hmac.compare_digest(dados.codigo.strip().encode(), codigo.encode()):
                trava.erro(chave)
                banco.registrar(con, usuario["usuario"], "codigo_errado", _ip(request))
                con.commit()
                raise HTTPException(
                    403, "Código de primeiro acesso incorreto. Peça o código ao administrador do portal (TI) "
                         "ou crie a senha pela rede da empresa.",
                )
        # A condição no UPDATE impede duas pessoas criarem a senha ao mesmo tempo
        cur = con.execute(
            "UPDATE usuarios SET senha_hash = ?, codigo_acesso = '' WHERE id = ? AND senha_hash = ''",
            (gerar_hash_senha(dados.senha), usuario["id"]),
        )
        if cur.rowcount != 1:
            raise HTTPException(400, "Este usuário já tem senha. Use a tela de entrar.")
        trava.limpar(chave)
        return _abrir_sessao(con, usuario, request, dados.volta, "criou_senha")


@router.post("/api/sair", dependencies=[Depends(exige_cabecalho)])
def sair(request: Request):
    token = request.cookies.get(config.COOKIE_NOME)
    if token:
        with banco.conexao() as con:
            banco.encerrar_sessao(con, hash_token(token))
    resposta = JSONResponse({"ok": True})
    resposta.delete_cookie(config.COOKIE_NOME, path="/")
    return resposta


@router.get("/api/eu")
def eu(request: Request):
    with banco.conexao() as con:
        usuario = _usuario_logado(request, con)
        sistemas = banco.listar_sistemas(con)
        if not usuario:
            return JSONResponse({"detail": "Faça login.", "modo": config.MODO}, status_code=401)
        dados = banco.buscar_usuario(con, usuario["id"])
    permitidos = [s for s in sistemas if dados["admin"] or s["aberto"] or s["slug"] in dados["sistemas"]]
    return {
        "usuario": dados["usuario"], "nome": dados["nome"], "admin": dados["admin"], "modo": config.MODO,
        "sistemas": permitidos, "todos_caminhos": [s["caminho"] for s in sistemas],
    }


@router.post("/api/minha-senha", dependencies=[Depends(exige_cabecalho)])
def minha_senha(dados: TrocaSenha, usuario=Depends(exige_login)):
    if not conferir_senha(dados.atual, usuario["senha_hash"]):
        raise HTTPException(400, "Senha atual incorreta.")
    if erro := senha_valida(dados.nova):
        raise HTTPException(400, erro)
    with banco.conexao() as con:
        con.execute("UPDATE usuarios SET senha_hash = ? WHERE id = ?", (gerar_hash_senha(dados.nova), usuario["id"]))
        banco.registrar(con, usuario["usuario"], "trocou_senha")
    return {"ok": True}


# ---------- Administração ----------

@router.get("/api/usuarios")
def usuarios(_=Depends(exige_admin)):
    with banco.conexao() as con:
        return {"usuarios": banco.listar_usuarios(con), "sistemas": banco.listar_sistemas(con)}


@router.post("/api/usuarios", dependencies=[Depends(exige_cabecalho)])
def criar_usuario(dados: NovoUsuario, admin=Depends(exige_admin)):
    if not LOGIN.match(dados.usuario.strip()):
        raise HTTPException(400, "Usuário: 2 a 60 caracteres, sem espaços (letras, números, . _ - @).")
    if dados.senha and (erro := senha_valida(dados.senha)):
        raise HTTPException(400, erro)
    with banco.conexao() as con:
        if banco.buscar_por_login(con, dados.usuario):
            raise HTTPException(409, "Já existe um usuário com esse login.")
        novo_id = banco.criar_usuario(
            con, dados.usuario, dados.nome, gerar_hash_senha(dados.senha) if dados.senha else "", dados.admin, dados.sistemas
        )
        banco.registrar(con, admin["usuario"], "criou_usuario", dados.usuario.strip())
        novo = banco.buscar_usuario(con, novo_id)
    aviso = _cadastrar_cracha(admin["usuario"], novo["usuario"], novo["nome"])
    return {**novo, "aviso": aviso} if aviso else novo


def _cadastrar_cracha(quem: str, cracha: str, nome: str) -> str:
    """Cria o crachá no Supabase (o Bobinas confere lá depois do login). Se falhar, devolve um aviso:
    o usuário do portal já está criado e o portal não pode depender do Supabase."""
    try:
        criado = garantir_cracha(cracha, nome)
    except ErroCrachas as erro:
        return f"Usuário criado, mas o crachá não entrou no Supabase ({erro}). Cadastre-o na tabela crachas."
    if criado:
        with banco.conexao() as con:
            banco.registrar(con, quem, "cadastrou_cracha", f"{cracha} no Supabase")
    return ""


@router.put("/api/usuarios/{usuario_id}", dependencies=[Depends(exige_cabecalho)])
def alterar_usuario(usuario_id: int, dados: AlteraUsuario, admin=Depends(exige_admin)):
    with banco.conexao() as con:
        atual = banco.buscar_usuario(con, usuario_id)
        if not atual:
            raise HTTPException(404, "Usuário não encontrado.")
        perde_admin = atual["admin"] and atual["ativo"] and (dados.admin is False or dados.ativo is False)
        if perde_admin and banco.admins_ativos(con) <= 1:
            raise HTTPException(400, "Precisa sobrar pelo menos um administrador ativo.")
        mudancas = []
        if dados.nome is not None:
            con.execute("UPDATE usuarios SET nome = ? WHERE id = ?", (dados.nome.strip(), usuario_id))
            mudancas.append("nome")
        if dados.admin is not None:
            con.execute("UPDATE usuarios SET admin = ? WHERE id = ?", (int(dados.admin), usuario_id))
            mudancas.append(f"admin={'sim' if dados.admin else 'não'}")
        if dados.ativo is not None:
            con.execute("UPDATE usuarios SET ativo = ? WHERE id = ?", (int(dados.ativo), usuario_id))
            mudancas.append(f"ativo={'sim' if dados.ativo else 'não'}")
            if not dados.ativo:
                banco.encerrar_sessoes_do_usuario(con, usuario_id)
        if dados.senha is not None:
            if dados.senha and (erro := senha_valida(dados.senha)):
                raise HTTPException(400, erro)
            novo_hash = gerar_hash_senha(dados.senha) if dados.senha else ""
            con.execute(
                "UPDATE usuarios SET senha_hash = ?, codigo_acesso = ? WHERE id = ?",
                (novo_hash, "" if dados.senha else novo_codigo(), usuario_id),
            )
            banco.encerrar_sessoes_do_usuario(con, usuario_id)
            mudancas.append("senha redefinida" if dados.senha else "senha apagada (cria no próximo acesso)")
        if dados.sistemas is not None:
            banco.definir_sistemas(con, usuario_id, dados.sistemas)
            mudancas.append("sistemas=" + (",".join(sorted(set(dados.sistemas))) or "nenhum"))
        if mudancas:
            banco.registrar(con, admin["usuario"], "alterou_usuario", f"{atual['usuario']}: {'; '.join(mudancas)}")
        return banco.buscar_usuario(con, usuario_id)


@router.delete("/api/usuarios/{usuario_id}", dependencies=[Depends(exige_cabecalho)])
def excluir_usuario(usuario_id: int, admin=Depends(exige_admin)):
    with banco.conexao() as con:
        atual = banco.buscar_usuario(con, usuario_id)
        if not atual:
            raise HTTPException(404, "Usuário não encontrado.")
        if atual["id"] == admin["id"]:
            raise HTTPException(400, "Você não pode excluir a sua própria conta.")
        if atual["admin"] and atual["ativo"] and banco.admins_ativos(con) <= 1:
            raise HTTPException(400, "Precisa sobrar pelo menos um administrador ativo.")
        con.execute("DELETE FROM usuarios WHERE id = ?", (usuario_id,))
        banco.registrar(con, admin["usuario"], "excluiu_usuario", atual["usuario"])
    return {"ok": True}


@router.post("/api/importar-crachas", dependencies=[Depends(exige_cabecalho)])
def importar_crachas(dados: Importacao, admin=Depends(exige_admin)):
    try:
        crachas = buscar_crachas()
    except ErroCrachas as erro:
        raise HTTPException(502, str(erro)) from erro
    with banco.conexao() as con:
        resultado = banco.importar_crachas(con, crachas, dados.sistemas)
        banco.registrar(
            con, admin["usuario"], "importou_crachas",
            f"{resultado['novos']} novos, {resultado['existentes']} já existiam; sistemas: {','.join(dados.sistemas) or 'nenhum'}",
        )
    return resultado


@router.get("/api/sistemas")
def sistemas(_=Depends(exige_admin)):
    with banco.conexao() as con:
        return banco.listar_sistemas(con)


def _validar_sistema(dados: Sistema) -> str:
    if not SLUG.match(dados.slug):
        raise HTTPException(400, "Código: letras minúsculas, números e hífen (ex.: rateios).")
    caminho = "/" + dados.caminho.strip().strip("/") + "/"
    if caminho == "//" or not re.match(r"^/[A-Za-z0-9._~/-]+/$", caminho):
        raise HTTPException(400, "Caminho inválido (ex.: /rateios/).")
    return caminho


@router.post("/api/sistemas", dependencies=[Depends(exige_cabecalho)])
def criar_sistema(dados: Sistema, admin=Depends(exige_admin)):
    caminho = _validar_sistema(dados)
    with banco.conexao() as con:
        if banco.sistema_existe(con, dados.slug):
            raise HTTPException(409, "Já existe um sistema com esse código.")
        con.execute(
            "INSERT INTO sistemas (slug, nome, caminho, ordem, aberto) VALUES (?, ?, ?, ?, ?)",
            (dados.slug, dados.nome.strip(), caminho, dados.ordem, int(dados.aberto)),
        )
        banco.registrar(con, admin["usuario"], "criou_sistema", f"{dados.slug} {caminho}{' (para todos)' if dados.aberto else ''}")
        return banco.listar_sistemas(con)


@router.put("/api/sistemas/{slug}", dependencies=[Depends(exige_cabecalho)])
def alterar_sistema(slug: str, dados: Sistema, admin=Depends(exige_admin)):
    caminho = _validar_sistema(dados)
    with banco.conexao() as con:
        if not banco.sistema_existe(con, slug):
            raise HTTPException(404, "Sistema não encontrado.")
        con.execute(
            "UPDATE sistemas SET nome = ?, caminho = ?, ordem = ?, aberto = ? WHERE slug = ?",
            (dados.nome.strip(), caminho, dados.ordem, int(dados.aberto), slug),
        )
        banco.registrar(
            con, admin["usuario"], "alterou_sistema", f"{slug} {caminho}{' (para todos)' if dados.aberto else ' (só marcados)'}"
        )
        return banco.listar_sistemas(con)


@router.delete("/api/sistemas/{slug}", dependencies=[Depends(exige_cabecalho)])
def excluir_sistema(slug: str, admin=Depends(exige_admin)):
    with banco.conexao() as con:
        if not banco.sistema_existe(con, slug):
            raise HTTPException(404, "Sistema não encontrado.")
        con.execute("DELETE FROM sistemas WHERE slug = ?", (slug,))
        banco.registrar(con, admin["usuario"], "excluiu_sistema", slug)
    return {"ok": True}


@router.get("/api/eventos")
def eventos(_=Depends(exige_admin)):
    with banco.conexao() as con:
        return banco.listar_eventos(con)


@router.get("/api/health", include_in_schema=False)
def health():
    return {"status": "online", "modo": config.MODO}


# ---------- Páginas ----------

def _pagina(nome: str) -> FileResponse:
    return FileResponse(ESTATICOS / nome, headers={"Cache-Control": "no-cache"})


@router.get("/", include_in_schema=False)
def painel():
    return _pagina("painel.html")


@router.get("/entrar", include_in_schema=False)
def pagina_entrar():
    return _pagina("entrar.html")


@router.get("/sem-acesso", include_in_schema=False)
def pagina_sem_acesso():
    return _pagina("sem-acesso.html")


@router.get("/{arquivo}", include_in_schema=False)
def estatico(arquivo: str):
    if arquivo not in {"estilo.css", "painel.js", "portal.js", "comum.js"}:
        raise HTTPException(404)
    return _pagina(arquivo)
