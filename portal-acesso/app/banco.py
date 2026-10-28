"""Acesso ao SQLite: esquema, usuários, sistemas, permissões, sessões e histórico."""
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime

from .config import config
from .seguranca import novo_codigo

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY,
    usuario TEXT NOT NULL UNIQUE COLLATE NOCASE,
    nome TEXT NOT NULL,
    senha_hash TEXT NOT NULL,
    admin INTEGER NOT NULL DEFAULT 0,
    ativo INTEGER NOT NULL DEFAULT 1,
    criado_em TEXT NOT NULL,
    codigo_acesso TEXT NOT NULL DEFAULT ''  -- pedido no primeiro acesso de fora da empresa; só existe sem senha
);
CREATE TABLE IF NOT EXISTS sistemas (
    slug TEXT PRIMARY KEY,
    nome TEXT NOT NULL,
    caminho TEXT NOT NULL,
    ordem INTEGER NOT NULL DEFAULT 0,
    aberto INTEGER NOT NULL DEFAULT 0  -- 1 = qualquer usuário logado pode abrir
);
CREATE TABLE IF NOT EXISTS permissoes (
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    sistema_slug TEXT NOT NULL REFERENCES sistemas(slug) ON DELETE CASCADE ON UPDATE CASCADE,
    PRIMARY KEY (usuario_id, sistema_slug)
);
CREATE TABLE IF NOT EXISTS sessoes (
    token_hash TEXT PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    expira_em REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS eventos (
    id INTEGER PRIMARY KEY,
    quando TEXT NOT NULL,
    usuario TEXT,
    tipo TEXT NOT NULL,
    detalhe TEXT
);
"""

# Sistemas que já rodam no servidor; o administrador pode incluir outros pelo painel
SISTEMAS_INICIAIS = [
    ("bobinas", "Inventário de Bobinas", "/bobinas/", 1),
    ("imobilizados", "Imobilizados", "/imobilizados/", 2),
    ("visionstock", "VisionStock (Almoxarifado)", "/visionstock/", 3),
    ("rateios", "Rateios", "/rateios/", 4),
    ("terceirizados", "Portaria de Terceiros", "/terceirizados/", 5),
]


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


@contextmanager
def conexao():
    con = sqlite3.connect(config.BANCO, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def iniciar() -> None:
    pasta = os.path.dirname(config.BANCO)
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    with conexao() as con:
        con.execute("PRAGMA journal_mode = WAL")
        con.executescript(ESQUEMA)
        # Bancos criados antes da opção "liberado para todos"
        colunas = {r[1] for r in con.execute("PRAGMA table_info(sistemas)")}
        if "aberto" not in colunas:
            con.execute("ALTER TABLE sistemas ADD COLUMN aberto INTEGER NOT NULL DEFAULT 0")
        # Bancos criados antes do código de primeiro acesso
        if "codigo_acesso" not in {r[1] for r in con.execute("PRAGMA table_info(usuarios)")}:
            con.execute("ALTER TABLE usuarios ADD COLUMN codigo_acesso TEXT NOT NULL DEFAULT ''")
        garantir_codigos(con)
        if con.execute("SELECT COUNT(*) FROM sistemas").fetchone()[0] == 0:
            con.executemany("INSERT INTO sistemas (slug, nome, caminho, ordem) VALUES (?, ?, ?, ?)", SISTEMAS_INICIAIS)


def registrar(con, usuario: str | None, tipo: str, detalhe: str = "") -> None:
    con.execute(
        "INSERT INTO eventos (quando, usuario, tipo, detalhe) VALUES (?, ?, ?, ?)", (agora(), usuario, tipo, detalhe)
    )
    # Mantém o histórico enxuto
    con.execute("DELETE FROM eventos WHERE id <= (SELECT MAX(id) FROM eventos) - 5000")


# ---------- Usuários ----------

def _usuario_dict(con, linha) -> dict:
    sistemas = [r[0] for r in con.execute(
        "SELECT sistema_slug FROM permissoes WHERE usuario_id = ? ORDER BY sistema_slug", (linha["id"],)
    )]
    return {
        "id": linha["id"],
        "usuario": linha["usuario"],
        "nome": linha["nome"],
        "admin": bool(linha["admin"]),
        "ativo": bool(linha["ativo"]),
        # Sem senha: a pessoa cria a própria senha no primeiro acesso
        "senha_pendente": linha["senha_hash"] == "",
        # De fora da empresa, o primeiro acesso pede este código (o administrador repassa)
        "codigo_acesso": linha["codigo_acesso"] if linha["senha_hash"] == "" else "",
        "criado_em": linha["criado_em"],
        "sistemas": sistemas,
    }


def listar_usuarios(con) -> list[dict]:
    return [_usuario_dict(con, u) for u in con.execute("SELECT * FROM usuarios ORDER BY nome COLLATE NOCASE")]


def buscar_usuario(con, usuario_id: int) -> dict | None:
    linha = con.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
    return _usuario_dict(con, linha) if linha else None


def buscar_por_login(con, usuario: str):
    return con.execute("SELECT * FROM usuarios WHERE usuario = ?", (usuario.strip(),)).fetchone()


def criar_usuario(con, usuario: str, nome: str, senha_hash: str, admin: bool, sistemas: list[str]) -> int:
    cur = con.execute(
        "INSERT INTO usuarios (usuario, nome, senha_hash, admin, ativo, criado_em, codigo_acesso) VALUES (?, ?, ?, ?, 1, ?, ?)",
        (usuario.strip(), nome.strip(), senha_hash, int(admin), agora(), "" if senha_hash else novo_codigo()),
    )
    definir_sistemas(con, cur.lastrowid, sistemas)
    return cur.lastrowid


def garantir_codigos(con) -> None:
    """Todo usuário sem senha tem um código de primeiro acesso (bancos antigos e crachás importados)."""
    for (usuario_id,) in con.execute("SELECT id FROM usuarios WHERE senha_hash = '' AND codigo_acesso = ''").fetchall():
        con.execute("UPDATE usuarios SET codigo_acesso = ? WHERE id = ?", (novo_codigo(), usuario_id))


def importar_crachas(con, crachas: list[tuple[str, str]], sistemas: list[str]) -> dict:
    """Cria um usuário (login = nº do crachá, sem senha) para cada crachá que ainda não existe."""
    novos, existentes = 0, 0
    for cracha, nome in crachas:
        if buscar_por_login(con, cracha):
            existentes += 1
            continue
        criar_usuario(con, cracha, nome or f"Crachá {cracha}", "", False, sistemas)
        novos += 1
    return {"novos": novos, "existentes": existentes}


def definir_sistemas(con, usuario_id: int, sistemas: list[str]) -> None:
    validos = {r[0] for r in con.execute("SELECT slug FROM sistemas")}
    con.execute("DELETE FROM permissoes WHERE usuario_id = ?", (usuario_id,))
    con.executemany(
        "INSERT INTO permissoes (usuario_id, sistema_slug) VALUES (?, ?)",
        [(usuario_id, s) for s in sorted(set(sistemas)) if s in validos],
    )


def admins_ativos(con) -> int:
    return con.execute("SELECT COUNT(*) FROM usuarios WHERE admin = 1 AND ativo = 1").fetchone()[0]


def pode_acessar(con, usuario, sistema: str) -> bool:
    if usuario["admin"]:
        return True
    if con.execute("SELECT 1 FROM sistemas WHERE slug = ? AND aberto = 1", (sistema,)).fetchone():
        return True
    return con.execute(
        "SELECT 1 FROM permissoes WHERE usuario_id = ? AND sistema_slug = ?", (usuario["id"], sistema)
    ).fetchone() is not None


# ---------- Sistemas ----------

def listar_sistemas(con) -> list[dict]:
    return [
        {**dict(r), "aberto": bool(r["aberto"])}
        for r in con.execute("SELECT slug, nome, caminho, ordem, aberto FROM sistemas ORDER BY ordem, nome")
    ]


def sistema_existe(con, slug: str) -> bool:
    return con.execute("SELECT 1 FROM sistemas WHERE slug = ?", (slug,)).fetchone() is not None


# ---------- Sessões ----------

def criar_sessao(con, token_hash: str, usuario_id: int) -> None:
    con.execute("DELETE FROM sessoes WHERE expira_em < ?", (time.time(),))
    con.execute(
        "INSERT INTO sessoes (token_hash, usuario_id, expira_em) VALUES (?, ?, ?)",
        (token_hash, usuario_id, time.time() + config.SESSAO_HORAS * 3600),
    )


def usuario_da_sessao(con, token_hash: str):
    return con.execute(
        """SELECT u.* FROM sessoes s JOIN usuarios u ON u.id = s.usuario_id
           WHERE s.token_hash = ? AND s.expira_em > ? AND u.ativo = 1""",
        (token_hash, time.time()),
    ).fetchone()


def encerrar_sessao(con, token_hash: str) -> None:
    con.execute("DELETE FROM sessoes WHERE token_hash = ?", (token_hash,))


def encerrar_sessoes_do_usuario(con, usuario_id: int) -> None:
    con.execute("DELETE FROM sessoes WHERE usuario_id = ?", (usuario_id,))


def listar_eventos(con, limite: int = 300) -> list[dict]:
    return [dict(r) for r in con.execute(
        "SELECT quando, usuario, tipo, detalhe FROM eventos ORDER BY id DESC LIMIT ?", (limite,)
    )]
