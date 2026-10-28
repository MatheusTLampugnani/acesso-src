"""Comandos de manutenção, rodados dentro do container:

    docker compose exec acesso python -m app.cli criar-admin
    docker compose exec acesso python -m app.cli redefinir-senha <usuario>
    docker compose exec acesso python -m app.cli listar
    docker compose exec acesso python -m app.cli importar-crachas [sistema1,sistema2]
    docker compose exec acesso python -m app.cli sincronizar-crachas
    docker compose exec acesso python -m app.cli liberar-para-todos <sistema> [<sistema> ...]
    docker compose exec acesso python -m app.cli so-marcados <sistema> [<sistema> ...]
"""
import getpass
import sys

from . import banco
from .config import config
from .crachas import ErroCrachas, buscar_crachas, garantir_cracha
from .seguranca import gerar_hash_senha, senha_valida


def _pedir_senha() -> str:
    while True:
        senha = getpass.getpass("Senha: ")
        if erro := senha_valida(senha):
            print(erro)
            continue
        if getpass.getpass("Repita a senha: ") != senha:
            print("As senhas não conferem.")
            continue
        return senha


def criar_admin() -> None:
    usuario = input("Usuário (login): ").strip()
    nome = input("Nome: ").strip() or usuario
    with banco.conexao() as con:
        if banco.buscar_por_login(con, usuario):
            sys.exit(f"Já existe o usuário {usuario}. Use: python -m app.cli redefinir-senha {usuario}")
    senha = _pedir_senha()
    with banco.conexao() as con:
        banco.criar_usuario(con, usuario, nome, gerar_hash_senha(senha), True, [])
        banco.registrar(con, "terminal", "criou_usuario", f"{usuario} (admin)")
    print(f"ADMIN OK: {usuario}")


def redefinir_senha(usuario: str) -> None:
    with banco.conexao() as con:
        linha = banco.buscar_por_login(con, usuario)
    if not linha:
        sys.exit(f"Usuário {usuario} não encontrado.")
    senha = _pedir_senha()
    with banco.conexao() as con:
        # Também reativa a conta, para o administrador nunca ficar trancado para fora do painel
        con.execute("UPDATE usuarios SET senha_hash = ?, ativo = 1 WHERE id = ?", (gerar_hash_senha(senha), linha["id"]))
        banco.encerrar_sessoes_do_usuario(con, linha["id"])
        banco.registrar(con, "terminal", "alterou_usuario", f"{linha['usuario']}: senha redefinida")
    print(f"SENHA OK: {linha['usuario']}")


def listar() -> None:
    with banco.conexao() as con:
        for u in banco.listar_usuarios(con):
            papel = "admin" if u["admin"] else ", ".join(u["sistemas"]) or "nenhum sistema"
            print(f"{u['usuario']:<20} {'ativo' if u['ativo'] else 'INATIVO':<8} {u['nome']:<30} {papel}")


def importar(sistemas: list[str]) -> None:
    try:
        crachas = buscar_crachas()
    except ErroCrachas as erro:
        sys.exit(f"ERRO: {erro}")
    with banco.conexao() as con:
        resultado = banco.importar_crachas(con, crachas, sistemas)
        banco.registrar(con, "terminal", "importou_crachas", f"{resultado['novos']} novos, {resultado['existentes']} já existiam")
    print(f"IMPORTAÇÃO OK: {resultado['novos']} novos, {resultado['existentes']} já existiam (de {len(crachas)} crachás)")


def sincronizar() -> None:
    """Cadastra no Supabase o crachá de quem foi criado direto no portal (login numérico, ativo) e ainda não estava lá."""
    if not config.SUPABASE_URL or not config.SUPABASE_CHAVE:
        sys.exit("ERRO: Supabase não configurado (ACESSO_SUPABASE_URL e ACESSO_SUPABASE_CHAVE).")
    with banco.conexao() as con:
        usuarios = [u for u in banco.listar_usuarios(con) if u["ativo"]]
    criados, falhas = [], 0
    for u in usuarios:
        try:
            if garantir_cracha(u["usuario"], u["nome"]):
                criados.append(u["usuario"])
        except ErroCrachas as erro:
            falhas += 1
            print(f"  {erro}")
    if criados:
        with banco.conexao() as con:
            banco.registrar(con, "terminal", "cadastrou_cracha", f"{len(criados)} no Supabase: {', '.join(criados)[:400]}")
    print(f"SINCRONIZAÇÃO {'COM FALHAS' if falhas else 'OK'}: {len(criados)} crachás cadastrados no Supabase"
          f"{': ' + ', '.join(criados) if criados else ''}")
    if falhas:
        sys.exit(1)


def para_todos(slugs: list[str], aberto: bool) -> None:
    with banco.conexao() as con:
        for slug in slugs:
            if not banco.sistema_existe(con, slug):
                sys.exit(f"Sistema {slug} não existe. Cadastrados: {', '.join(s['slug'] for s in banco.listar_sistemas(con))}")
            con.execute("UPDATE sistemas SET aberto = ? WHERE slug = ?", (int(aberto), slug))
            banco.registrar(con, "terminal", "alterou_sistema", f"{slug} {'(para todos)' if aberto else '(só marcados)'}")
            print(f"{'LIBERADO PARA TODOS' if aberto else 'SÓ MARCADOS'}: {slug}")


def principal(argv: list[str]) -> None:
    banco.iniciar()
    if argv[:1] == ["criar-admin"]:
        criar_admin()
    elif argv[:1] == ["redefinir-senha"] and len(argv) == 2:
        redefinir_senha(argv[1])
    elif argv[:1] == ["importar-crachas"] and len(argv) <= 2:
        importar([s for s in (argv[1] if len(argv) == 2 else "").split(",") if s])
    elif argv[:1] == ["sincronizar-crachas"]:
        sincronizar()
    elif argv[:1] == ["liberar-para-todos"] and len(argv) >= 2:
        para_todos(argv[1:], True)
    elif argv[:1] == ["so-marcados"] and len(argv) >= 2:
        para_todos(argv[1:], False)
    elif argv[:1] == ["listar"]:
        listar()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    principal(sys.argv[1:])
