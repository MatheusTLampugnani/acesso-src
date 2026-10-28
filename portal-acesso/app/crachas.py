"""Crachás no Supabase (tabela usada pelo login do VisionStock e do Bobinas): leitura e cadastro."""
import json
import re
import urllib.request

from .config import config

CRACHA = re.compile(r"^[A-Za-z0-9._@-]{1,60}$")
NUMERO = re.compile(r"^\d{1,18}$")  # o id da tabela crachas é bigint
POR_PAGINA = 1000


class ErroCrachas(Exception):
    pass


def buscar_crachas() -> list[tuple[str, str]]:
    """Retorna [(crachá, nome)] lendo a API REST do Supabase, de 1000 em 1000."""
    if not config.SUPABASE_URL or not config.SUPABASE_CHAVE:
        raise ErroCrachas("Supabase não configurado (ACESSO_SUPABASE_URL e ACESSO_SUPABASE_CHAVE).")
    resultado, inicio = [], 0
    while True:
        pedido = urllib.request.Request(
            f"{config.SUPABASE_URL}/rest/v1/{config.TABELA_CRACHAS}?select=id,nome_completo&order=id",
            headers={
                "apikey": config.SUPABASE_CHAVE,
                "Authorization": f"Bearer {config.SUPABASE_CHAVE}",
                "Range-Unit": "items",
                "Range": f"{inicio}-{inicio + POR_PAGINA - 1}",
            },
        )
        try:
            with urllib.request.urlopen(pedido, timeout=20) as resposta:
                pagina = json.load(resposta)
        except Exception as erro:  # rede, chave errada, tabela inexistente
            raise ErroCrachas(f"Não foi possível ler os crachás do Supabase: {erro}") from erro
        for linha in pagina:
            cracha = str(linha.get("id") or "").strip()
            if CRACHA.match(cracha):
                resultado.append((cracha, (linha.get("nome_completo") or "").strip()[:120]))
        if len(pagina) < POR_PAGINA:
            return resultado
        inicio += POR_PAGINA


def garantir_cracha(cracha: str, nome: str) -> bool:
    """Cadastra o crachá no Supabase se ainda não existir, para os sistemas que conferem a tabela
    (ex.: Bobinas) reconhecerem quem foi criado direto no portal. Crachá que já existe não é alterado.
    Retorna True se cadastrou; False se já existia, se o login não é número ou se o Supabase não está configurado."""
    cracha = cracha.strip()
    if not NUMERO.match(cracha) or not config.SUPABASE_URL or not config.SUPABASE_CHAVE:
        return False
    pedido = urllib.request.Request(
        f"{config.SUPABASE_URL}/rest/v1/{config.TABELA_CRACHAS}?on_conflict=id",
        data=json.dumps([{"id": int(cracha), "nome_completo": nome.strip()[:120]}]).encode(),
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
