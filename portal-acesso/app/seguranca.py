"""Senhas (scrypt da biblioteca padrão), tokens de sessão e trava de tentativas de login."""
import base64
import hashlib
import hmac
import secrets
import threading
import time

_N, _R, _P = 2**14, 8, 1


def _b64(dados: bytes) -> str:
    return base64.b64encode(dados).decode()


def gerar_hash_senha(senha: str) -> str:
    sal = secrets.token_bytes(16)
    chave = hashlib.scrypt(senha.encode(), salt=sal, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${_b64(sal)}${_b64(chave)}"


def conferir_senha(senha: str, guardado: str) -> bool:
    try:
        algoritmo, n, r, p, sal, chave = guardado.split("$")
        if algoritmo != "scrypt":
            return False
        calculada = hashlib.scrypt(
            senha.encode(), salt=base64.b64decode(sal), n=int(n), r=int(r), p=int(p), dklen=32
        )
        return hmac.compare_digest(calculada, base64.b64decode(chave))
    except (ValueError, TypeError):
        return False


def senha_valida(senha: str) -> str | None:
    """Retorna a mensagem de erro, ou None se a senha serve."""
    if len(senha) < 6:
        return "A senha precisa ter pelo menos 6 caracteres."
    if len(senha) > 200:
        return "A senha é longa demais."
    return None


def novo_token() -> str:
    return secrets.token_urlsafe(32)


def novo_codigo() -> str:
    """Código de 6 dígitos para criar a senha no primeiro acesso feito de fora da empresa."""
    return f"{secrets.randbelow(10**6):06d}"


def hash_token(token: str) -> str:
    # O banco guarda só o hash: quem copiar o arquivo não consegue usar as sessões
    return hashlib.sha256(token.encode()).hexdigest()


class TravaLogin:
    """Conta erros de senha por (IP, usuário) e trava por alguns minutos ao passar do limite."""

    def __init__(self, maximo: int, minutos: int) -> None:
        self.maximo = maximo
        self.segundos = minutos * 60
        self._erros: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def travado(self, chave: str) -> bool:
        with self._lock:
            erros, desde = self._erros.get(chave, (0, 0.0))
            if erros >= self.maximo and time.time() - desde < self.segundos:
                return True
            if erros >= self.maximo:
                self._erros.pop(chave, None)
            return False

    def erro(self, chave: str) -> None:
        with self._lock:
            erros, _ = self._erros.get(chave, (0, 0.0))
            self._erros[chave] = (erros + 1, time.time())

    def limpar(self, chave: str) -> None:
        with self._lock:
            self._erros.pop(chave, None)
