"""Configuração do Portal de Acesso lida de variáveis de ambiente (único lugar que lê o ambiente)."""
import os

# Carrega automaticamente o .env local em desenvolvimento se presente
env_local = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.isfile(env_local):
    try:
        with open(env_local, "r", encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if linha and not linha.startswith("#") and "=" in linha:
                    k, v = linha.split("=", 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k and k not in os.environ:
                        os.environ[k] = v
    except Exception:
        pass

MODOS = ("observar", "bloquear")


class Config:
    # Banco SQLite com usuários, permissões e sessões (fica num volume do Docker)
    BANCO: str = os.environ.get("ACESSO_BANCO", "/dados/acesso.db")
    # observar = ninguém é barrado, só registra quem seria; bloquear = aplica as permissões
    MODO: str = os.environ.get("ACESSO_MODO", "observar").strip().lower()
    SESSAO_HORAS: float = float(os.environ.get("ACESSO_SESSAO_HORAS", "12"))
    COOKIE_NOME: str = os.environ.get("ACESSO_COOKIE", "portal_sessao")
    # Ligue (1) quando TODO acesso for por HTTPS; com 1 o login deixa de funcionar via http://
    COOKIE_SEGURO: bool = os.environ.get("ACESSO_COOKIE_SEGURO", "0") == "1"
    # Caminho em que o serviço é publicado pelo Nginx do servidor
    BASE: str = "/" + os.environ.get("ACESSO_BASE", "acesso").strip("/")
    # Tentativas de login erradas antes de travar por alguns minutos
    MAX_TENTATIVAS: int = int(os.environ.get("ACESSO_MAX_TENTATIVAS", "5"))
    TRAVA_MINUTOS: int = int(os.environ.get("ACESSO_TRAVA_MINUTOS", "5"))

    # Cadastro de crachás no Supabase (o mesmo do VisionStock), usado para importar os usuários
    SUPABASE_URL: str = os.environ.get("ACESSO_SUPABASE_URL", "").strip().rstrip("/")
    SUPABASE_CHAVE: str = os.environ.get("ACESSO_SUPABASE_CHAVE", "").strip()
    TABELA_CRACHAS: str = os.environ.get("ACESSO_TABELA_CRACHAS", "crachas").strip()

    def __init__(self) -> None:
        if self.MODO not in MODOS:
            self.MODO = "observar"


config = Config()
