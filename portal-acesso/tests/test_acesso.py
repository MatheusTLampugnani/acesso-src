from app.rotas import volta_segura

H = {"X-Portal": "1"}
HI = {**H, "X-Real-IP": "192.168.1.50"}  # rede da empresa (o Nginx põe o IP de quem chamou neste cabeçalho)


def entrar(cliente, usuario="admin", senha="segredo1", volta=""):
    return cliente.post("/acesso/api/entrar", json={"usuario": usuario, "senha": senha, "volta": volta}, headers=H)


def cria_operador(cliente, sistemas):
    r = cliente.post(
        "/acesso/api/usuarios",
        json={"usuario": "joao", "nome": "João", "senha": "senha123", "sistemas": sistemas},
        headers=H,
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_sem_login_bloqueia_com_401(cria_cliente):
    c = cria_cliente("bloquear")
    assert c.get("/acesso/api/verificar/rateios").status_code == 401


def test_modo_observar_libera_mas_registra(cria_cliente):
    c = cria_cliente("observar")
    assert c.get("/acesso/api/verificar/rateios", headers={"X-Original-URI": "/rateios/"}).status_code == 200
    assert entrar(c).status_code == 200
    eventos = c.get("/acesso/api/eventos").json()
    assert any(e["tipo"] == "seria_negado" and "rateios" in e["detalhe"] for e in eventos)


def test_login_errado_e_trava(cria_cliente):
    c = cria_cliente()
    for _ in range(5):
        assert entrar(c, senha="errada").status_code == 401
    assert entrar(c).status_code == 429


def test_login_exige_cabecalho_do_portal(cria_cliente):
    c = cria_cliente()
    r = c.post("/acesso/api/entrar", json={"usuario": "admin", "senha": "segredo1"})
    assert r.status_code == 403


def test_permissao_por_sistema(cria_cliente):
    c = cria_cliente()
    assert entrar(c).status_code == 200
    operador = cria_operador(c, ["visionstock"])
    # Admin vê tudo
    assert c.get("/acesso/api/verificar/rateios").status_code == 200

    c.post("/acesso/api/sair", headers=H)
    assert entrar(c, "JOAO", "senha123").status_code == 200  # login sem diferenciar maiúsculas
    assert c.get("/acesso/api/verificar/visionstock").status_code == 200
    assert c.post("/acesso/api/verificar/visionstock").status_code == 200  # Nginx repete o método original
    assert c.get("/acesso/api/verificar/rateios").status_code == 403
    assert c.get("/acesso/api/verificar/inexistente").status_code == 403
    assert c.get("/acesso/api/usuarios").status_code == 403  # não é admin
    eu = c.get("/acesso/api/eu").json()
    assert [s["slug"] for s in eu["sistemas"]] == ["visionstock"]
    assert operador["sistemas"] == ["visionstock"]


def test_desativar_derruba_a_sessao(cria_cliente):
    c = cria_cliente()
    entrar(c)
    operador = cria_operador(c, ["rateios"])
    admin_cookie = c.cookies.get("portal_sessao")

    c.cookies.clear()
    entrar(c, "joao", "senha123")
    assert c.get("/acesso/api/verificar/rateios").status_code == 200
    joao_cookie = c.cookies.get("portal_sessao")

    c.cookies.set("portal_sessao", admin_cookie)
    assert c.put(f"/acesso/api/usuarios/{operador['id']}", json={"ativo": False}, headers=H).status_code == 200

    c.cookies.set("portal_sessao", joao_cookie)
    assert c.get("/acesso/api/verificar/rateios").status_code == 401
    assert entrar(c, "joao", "senha123").status_code == 401


def test_nao_remove_o_ultimo_admin(cria_cliente):
    c = cria_cliente()
    entrar(c)
    eu_id = c.get("/acesso/api/usuarios").json()["usuarios"][0]["id"]
    r = c.put(f"/acesso/api/usuarios/{eu_id}", json={"admin": False}, headers=H)
    assert r.status_code == 400
    assert c.delete(f"/acesso/api/usuarios/{eu_id}", headers=H).status_code == 400


def test_sistemas_crud_e_permissao_some_ao_remover(cria_cliente):
    c = cria_cliente()
    entrar(c)
    r = c.post("/acesso/api/sistemas", json={"slug": "compras", "nome": "Compras", "caminho": "compras"}, headers=H)
    assert r.status_code == 200
    assert any(s["caminho"] == "/compras/" for s in r.json())
    operador = cria_operador(c, ["compras", "nao-existe"])
    assert operador["sistemas"] == ["compras"]
    assert c.delete("/acesso/api/sistemas/compras", headers=H).status_code == 200
    usuarios = c.get("/acesso/api/usuarios").json()["usuarios"]
    assert next(u for u in usuarios if u["usuario"] == "joao")["sistemas"] == []
    r = c.post("/acesso/api/sistemas", json={"slug": "X Y", "nome": "a", "caminho": "/a/"}, headers=H)
    assert r.status_code == 400


def test_troca_de_senha(cria_cliente):
    c = cria_cliente()
    entrar(c)
    assert c.post("/acesso/api/minha-senha", json={"atual": "x", "nova": "novasenha"}, headers=H).status_code == 400
    assert c.post("/acesso/api/minha-senha", json={"atual": "segredo1", "nova": "novasenha"}, headers=H).status_code == 200
    c.cookies.clear()
    assert entrar(c, senha="novasenha").status_code == 200


def test_cookie_e_volta(cria_cliente):
    c = cria_cliente()
    r = entrar(c, volta="/rateios/?a=1&b=2")
    assert r.json()["volta"] == "/rateios/?a=1&b=2"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "path=/" in cookie and "samesite=lax" in cookie
    assert entrar(c, volta="https://outro.site/").json()["volta"] == "/"


def test_volta_segura():
    assert volta_segura("//malicioso.com") == "/"
    assert volta_segura("/\\malicioso.com") == "/"
    assert volta_segura("/acesso/entrar?volta=/x") == "/"
    assert volta_segura("/visionstock/") == "/visionstock/"


def test_paginas(cria_cliente):
    c = cria_cliente()
    for caminho in ("/acesso/", "/acesso/entrar", "/acesso/sem-acesso", "/acesso/portal.js", "/acesso/estilo.css"):
        assert c.get(caminho).status_code == 200, caminho
    assert c.get("/acesso/main.py").status_code == 404
    assert c.get("/acesso/api/health").json()["status"] == "online"


def test_importar_crachas_e_primeiro_acesso(cria_cliente, monkeypatch):
    c = cria_cliente()
    import app.rotas
    monkeypatch.setattr(app.rotas, "buscar_crachas", lambda: [("1234", "Ana Lima"), ("5678", ""), ("admin", "x")])
    entrar(c)
    r = c.post("/acesso/api/importar-crachas", json={"sistemas": ["visionstock"]}, headers=H)
    assert r.json() == {"novos": 2, "existentes": 1}
    usuarios = {u["usuario"]: u for u in c.get("/acesso/api/usuarios").json()["usuarios"]}
    assert usuarios["1234"]["senha_pendente"] and usuarios["1234"]["sistemas"] == ["visionstock"]
    assert usuarios["5678"]["nome"] == "Crachá 5678"
    assert not usuarios["admin"]["senha_pendente"]
    # Rodar de novo não duplica
    assert c.post("/acesso/api/importar-crachas", json={}, headers=H).json() == {"novos": 0, "existentes": 3}

    c.cookies.clear()
    # 1º passo da tela: só o crachá; inexistente responde igual a quem já tem senha
    ident = lambda u: c.post("/acesso/api/identificar", json={"usuario": u}, headers=H).json()["criar_senha"]
    assert ident("1234") is True and ident("admin") is False and ident("9999") is False
    r = entrar(c, "1234", "")
    assert r.status_code == 409 and r.json()["criar_senha"] is True
    assert c.get("/acesso/api/verificar/visionstock").status_code == 401
    r = c.post("/acesso/api/primeiro-acesso", json={"usuario": "1234", "senha": "abc", "volta": "/visionstock/"}, headers=H)
    assert r.status_code == 400  # senha curta
    r = c.post("/acesso/api/primeiro-acesso", json={"usuario": "1234", "senha": "minha123", "volta": "/visionstock/"}, headers=HI)
    assert r.status_code == 200 and r.json()["volta"] == "/visionstock/"
    assert c.get("/acesso/api/verificar/visionstock").status_code == 200
    # Depois de criada, ninguém sobrescreve pelo primeiro acesso
    c.cookies.clear()
    r = c.post("/acesso/api/primeiro-acesso", json={"usuario": "1234", "senha": "outra123"}, headers=H)
    assert r.status_code == 400
    assert entrar(c, "1234", "minha123").status_code == 200
    assert ident("1234") is False


def test_admin_zera_senha_e_pessoa_cria_outra(cria_cliente):
    c = cria_cliente()
    entrar(c)
    operador = cria_operador(c, ["rateios"])
    r = c.put(f"/acesso/api/usuarios/{operador['id']}", json={"senha": ""}, headers=H)
    assert r.json()["senha_pendente"] is True
    assert len(r.json()["codigo_acesso"]) == 6  # para criar a senha de fora da empresa
    c.cookies.clear()
    assert entrar(c, "joao", "senha123").status_code == 409
    novo = c.post("/acesso/api/usuarios", json={"usuario": "sem", "nome": "Sem Senha"}, headers=H)
    assert novo.status_code == 401  # sem login de admin


def test_primeiro_acesso_de_fora_exige_codigo(cria_cliente):
    c = cria_cliente()
    entrar(c)
    c.post("/acesso/api/usuarios", json={"usuario": "4321", "nome": "Bia"}, headers=H)
    codigo = next(u for u in c.get("/acesso/api/usuarios").json()["usuarios"] if u["usuario"] == "4321")["codigo_acesso"]
    assert len(codigo) == 6 and codigo.isdigit()
    c.cookies.clear()

    funnel = {**H, "X-Real-IP": "127.0.0.1"}  # internet: chega do próprio servidor, sem identificação da Tailscale
    tailscale = {**funnel, "Tailscale-User-Login": "fulano@videplast.com.br"}
    ident = lambda h: c.post("/acesso/api/identificar", json={"usuario": "4321"}, headers=h).json()
    assert ident(funnel) == {"criar_senha": True, "precisa_codigo": True, "pede_email": True, "nome": ""}
    assert ident(H)["precisa_codigo"] is True  # sem IP conhecido: trata como de fora
    assert ident(HI)["precisa_codigo"] is False
    assert ident(tailscale)["precisa_codigo"] is False
    tenta = lambda h: c.post("/acesso/api/entrar", json={"usuario": "4321", "senha": ""}, headers=h)
    assert tenta(HI).status_code == 409 and tenta(HI).json()["precisa_codigo"] is False
    assert tenta(funnel).json()["precisa_codigo"] is True

    criar = lambda h, cod: c.post(
        "/acesso/api/primeiro-acesso", json={"usuario": "4321", "senha": "minha123", "codigo": cod}, headers=h)
    assert criar(funnel, "").status_code == 403
    errado = "000000" if codigo != "000000" else "111111"
    for _ in range(4):
        assert criar(funnel, errado).status_code == 403
    assert criar(funnel, codigo).status_code == 429  # 5 erros travam, mesmo com o código certo
    assert criar({**H, "X-Real-IP": "200.150.10.20"}, codigo).status_code == 200

    c.cookies.clear()
    entrar(c)
    bia = next(u for u in c.get("/acesso/api/usuarios").json()["usuarios"] if u["usuario"] == "4321")
    assert bia["senha_pendente"] is False and bia["codigo_acesso"] == ""  # o código não serve mais
    assert sum(e["tipo"] == "codigo_errado" for e in c.get("/acesso/api/eventos").json()) == 5


def test_login_errado_fica_no_historico(cria_cliente):
    c = cria_cliente()
    assert entrar(c, senha="errada").status_code == 401
    entrar(c)
    assert any(e["tipo"] == "login_falhou" for e in c.get("/acesso/api/eventos").json())


def test_migra_banco_antigo_sem_codigo_de_acesso(cria_cliente, tmp_path):
    import sqlite3
    from app import banco
    c = cria_cliente()
    con = sqlite3.connect(tmp_path / "acesso.db")
    con.execute("ALTER TABLE usuarios DROP COLUMN codigo_acesso")
    con.execute("INSERT INTO usuarios (usuario, nome, senha_hash, admin, ativo, criado_em) VALUES ('777', 'Antigo', '', 0, 1, 'x')")
    con.commit()
    con.close()
    banco.iniciar()
    with banco.conexao() as con:
        assert len(banco.buscar_por_login(con, "777")["codigo_acesso"]) == 6
        assert banco.buscar_por_login(con, "admin")["codigo_acesso"] == ""  # quem tem senha não ganha código
    assert entrar(c).status_code == 200


def test_importar_sem_supabase_configurado(cria_cliente):
    c = cria_cliente()
    entrar(c)
    r = c.post("/acesso/api/importar-crachas", json={}, headers=H)
    assert r.status_code == 502 and "Supabase" in r.json()["detail"]


def test_sistema_liberado_para_todos(cria_cliente):
    c = cria_cliente()
    entrar(c)
    cria_operador(c, [])
    r = c.put("/acesso/api/sistemas/bobinas",
              json={"slug": "bobinas", "nome": "Bobinas", "caminho": "/bobinas/", "aberto": True}, headers=H)
    assert next(s for s in r.json() if s["slug"] == "bobinas")["aberto"] is True
    c.cookies.clear()
    assert c.get("/acesso/api/verificar/bobinas").status_code == 401  # ainda exige login
    entrar(c, "joao", "senha123")
    assert c.get("/acesso/api/verificar/bobinas").status_code == 200
    assert c.get("/acesso/api/verificar/rateios").status_code == 403
    assert [s["slug"] for s in c.get("/acesso/api/eu").json()["sistemas"]] == ["bobinas"]


def test_migra_banco_antigo_sem_coluna_aberto(cria_cliente, tmp_path):
    import sqlite3
    from app import banco
    c = cria_cliente()
    con = sqlite3.connect(tmp_path / "acesso.db")
    con.executescript("ALTER TABLE sistemas DROP COLUMN aberto;")
    con.close()
    banco.iniciar()
    with banco.conexao() as con:
        assert all(s["aberto"] is False for s in banco.listar_sistemas(con))
    assert entrar(c).status_code == 200


def test_criar_usuario_cadastra_cracha_no_supabase(cria_cliente, monkeypatch):
    c = cria_cliente()
    import app.rotas
    chamadas = []
    monkeypatch.setattr(app.rotas, "garantir_cracha", lambda cracha, nome, **_: chamadas.append((cracha, nome)) or True)
    entrar(c)
    r = c.post("/acesso/api/usuarios", json={"usuario": "13969", "nome": "Maria Souza"}, headers=H)
    assert r.status_code == 200 and "aviso" not in r.json()
    assert chamadas == [("13969", "Maria Souza")]
    eventos = c.get("/acesso/api/eventos").json()
    assert any(e["tipo"] == "cadastrou_cracha" and "13969" in e["detalhe"] for e in eventos)


def test_criar_usuario_avisa_quando_supabase_falha(cria_cliente, monkeypatch):
    c = cria_cliente()
    import app.rotas

    def falha(cracha, nome, **_):
        raise app.rotas.ErroCrachas("sem rede")

    monkeypatch.setattr(app.rotas, "garantir_cracha", falha)
    entrar(c)
    r = c.post("/acesso/api/usuarios", json={"usuario": "13970", "nome": "Ana"}, headers=H)
    assert r.status_code == 200 and "sem rede" in r.json()["aviso"]
    # O usuário do portal fica criado mesmo assim
    assert any(u["usuario"] == "13970" for u in c.get("/acesso/api/usuarios").json()["usuarios"])


def test_garantir_cracha_so_para_login_numerico(monkeypatch):
    import io
    import json
    from app import crachas
    monkeypatch.setattr(crachas.config, "SUPABASE_URL", "https://exemplo.supabase.co")
    monkeypatch.setattr(crachas.config, "SUPABASE_CHAVE", "chave")
    pedidos = []

    def urlopen(pedido, timeout):
        pedidos.append(pedido)
        return io.BytesIO(b'[{"id": 13969}]')

    monkeypatch.setattr(crachas.urllib.request, "urlopen", urlopen)
    assert crachas.garantir_cracha("wanderson.oliveira", "W") is False and pedidos == []
    assert crachas.garantir_cracha(" 13969 ", "Maria") is True
    assert json.loads(pedidos[0].data) == [{"id": 13969, "nome_completo": "Maria"}]
    assert "ignore-duplicates" in pedidos[0].get_header("Prefer")  # crachá existente não é alterado


def _usuario(cliente, login):
    return next((u for u in cliente.get("/acesso/api/usuarios").json()["usuarios"] if u["usuario"] == login), None)


def test_admin_e_senha_do_cadastro_nao_valem_no_portal(cria_cliente, monkeypatch):
    # O admin de crachas é do Bobinas, do VisionStock e do Mín/Máx: no Portal ele abriria o RH e a Escuta
    c = cria_cliente()
    import app.rotas
    from app import crachas
    assert "admin" not in crachas.COLUNAS and "senha" not in crachas.COLUNAS
    linha = {"cracha": "15811", "nome": "Marcelo", "setor": "Contabilidade", "unidade": 1001, "email": "", "admin": True, "senha_hash": "scrypt$x"}
    monkeypatch.setattr(app.rotas, "buscar_crachas", lambda: [linha])
    entrar(c)
    for _ in range(2):  # usuário novo e usuário que já existe
        assert c.post("/acesso/api/importar-crachas", json={}, headers=H).status_code == 200
    u = _usuario(c, "15811")
    assert u["admin"] is False and u["senha_pendente"] is True and u["sistemas"] == []
    assert u["setor"] == "Contabilidade" and u["unidade"] == 1001


def test_senha_e_admin_nao_vao_para_o_cadastro(cria_cliente, monkeypatch):
    c = cria_cliente()
    import app.rotas
    copias = []
    monkeypatch.setattr(app.rotas, "garantir_cracha", lambda *a, **k: False)
    monkeypatch.setattr(app.rotas, "atualizar_usuario_supabase", lambda cracha, **campos: copias.append((cracha, campos)) or True)
    entrar(c)
    operador = cria_operador(c, [])
    assert c.post("/acesso/api/minha-senha", json={"atual": "segredo1", "nova": "novasenha"}, headers=H).status_code == 200
    assert copias == []
    r = c.put(f"/acesso/api/usuarios/{operador['id']}", json={"admin": True, "senha": "outra123", "nome": "João Silva"}, headers=H)
    assert r.status_code == 200
    assert copias == [("joao", {"nome": "João Silva", "setor": None, "unidade": None, "email": None})]


def test_copia_que_falha_fica_no_historico(cria_cliente, monkeypatch):
    c = cria_cliente()
    import app.rotas
    monkeypatch.setattr(app.rotas, "garantir_cracha", lambda *a, **k: False)
    monkeypatch.setattr(app.rotas, "atualizar_usuario_supabase", lambda cracha, **campos: False)
    entrar(c)
    operador = cria_operador(c, [])
    assert c.put(f"/acesso/api/usuarios/{operador['id']}", json={"nome": "João Silva"}, headers=H).status_code == 200
    assert any(e["tipo"] == "supabase_falhou" and "joao" in e["detalhe"] for e in c.get("/acesso/api/eventos").json())


def test_identificar_nao_mostra_dados_para_quem_esta_fora(cria_cliente):
    c = cria_cliente()
    entrar(c)
    c.post("/acesso/api/usuarios", json={"usuario": "4322", "nome": "Bia Lima", "email": "bia@videplast.com.br"}, headers=H)
    c.cookies.clear()
    fora = {**H, "X-Real-IP": "127.0.0.1"}
    ident = lambda usuario, h: c.post("/acesso/api/identificar", json={"usuario": usuario}, headers=h).json()
    assert ident("4322", fora) == {"criar_senha": True, "precisa_codigo": True, "pede_email": False, "nome": ""}
    assert ident("4322", HI)["nome"] == "Bia Lima"
    # Quem não existe e quem já tem senha respondem igual para quem está fora
    igual = {"criar_senha": False, "precisa_codigo": False, "pede_email": False, "nome": ""}
    assert ident("9999", fora) == igual and ident("admin", fora) == igual


def test_usuario_excluido_nao_volta_sozinho(cria_cliente, monkeypatch):
    c = cria_cliente()
    import app.rotas
    monkeypatch.setattr(app.rotas, "buscar_crachas", lambda: [("1234", "Ana Lima")])
    monkeypatch.setattr(app.rotas, "buscar_cracha_no_supabase", lambda termo: {"cracha": "1234", "nome": "Ana Lima"})
    monkeypatch.setattr(app.rotas, "garantir_cracha", lambda *a, **k: False)
    importar = lambda: c.post("/acesso/api/importar-crachas", json={}, headers=H).json()
    entrar(c)
    assert importar() == {"novos": 1, "existentes": 0}
    assert c.delete(f"/acesso/api/usuarios/{_usuario(c, '1234')['id']}", headers=H).status_code == 200

    assert importar() == {"novos": 0, "existentes": 0}  # sincronização
    assert c.post("/acesso/api/identificar", json={"usuario": "1234"}, headers=H).json()["criar_senha"] is False  # login
    assert _usuario(c, "1234") is None

    # Criar de novo no painel vale
    assert c.post("/acesso/api/usuarios", json={"usuario": "1234", "nome": "Ana Lima"}, headers=H).status_code == 200
    assert importar() == {"novos": 0, "existentes": 1}


def test_email_nao_toma_o_login_de_outra_pessoa(cria_cliente):
    c = cria_cliente()
    entrar(c)
    novo = lambda login, **dados: c.post("/acesso/api/usuarios", json={"usuario": login, "nome": login, **dados}, headers=H)
    assert novo("4323").status_code == 200
    assert novo("4324", email="Dono@videplast.com.br").status_code == 200
    assert novo("4325", email="dono@videplast.com.br").status_code == 409
    assert novo("4326", email="sem-arroba").status_code == 400
    c.cookies.clear()
    criar = lambda email: c.post("/acesso/api/primeiro-acesso", json={"usuario": "4323", "senha": "minha123", "email": email}, headers=HI)
    assert criar("admin").status_code == 400  # o "e-mail" igual a um login não passa
    assert criar("dono@videplast.com.br").status_code == 409
    assert criar("caio@videplast.com.br").status_code == 200
    c.cookies.clear()
    assert entrar(c, "CAIO@videplast.com.br", "minha123").status_code == 200  # e-mail também entra
    c.cookies.clear()
    assert entrar(c).status_code == 200  # e o login do outro continua dele


def test_email_repetido_no_cadastro_nao_serve_de_login(cria_cliente, monkeypatch):
    c = cria_cliente()
    import app.rotas
    monkeypatch.setattr(app.rotas, "buscar_crachas", lambda: [
        {"cracha": "1", "nome": "Um", "email": "igual@videplast.com.br"},
        {"cracha": "2", "nome": "Dois", "email": "igual@videplast.com.br"},
    ])
    entrar(c)
    assert c.post("/acesso/api/importar-crachas", json={}, headers=H).status_code == 200
    from app import banco
    with banco.conexao() as con:
        assert banco.buscar_por_login(con, "igual@videplast.com.br") is None
        assert banco.buscar_por_login(con, "1")["nome"] == "Um"


def test_reiniciar_nao_desfaz_o_painel(cria_cliente):
    from app import banco
    c = cria_cliente()
    entrar(c)
    assert c.delete("/acesso/api/sistemas/rateios", headers=H).status_code == 200
    r = c.put("/acesso/api/sistemas/bobinas", json={"slug": "bobinas", "nome": "Bobinas", "caminho": "/bobinas/"}, headers=H)
    assert r.status_code == 200
    banco.iniciar()
    with banco.conexao() as con:
        sistemas = {s["slug"]: s for s in banco.listar_sistemas(con)}
    assert "rateios" not in sistemas and sistemas["bobinas"]["nome"] == "Bobinas"


def test_busca_no_cadastro_usa_o_filtro_certo(monkeypatch):
    import io
    from app import crachas
    monkeypatch.setattr(crachas.config, "SUPABASE_URL", "https://exemplo.supabase.co")
    monkeypatch.setattr(crachas.config, "SUPABASE_CHAVE", "chave")
    pedidos, resposta = [], [b'[{"id": 77, "nome_completo": "Ana", "email": "Ana@Videplast.com.br"}]']

    def urlopen(pedido, timeout):
        pedidos.append(pedido.full_url)
        return io.BytesIO(resposta[0])

    monkeypatch.setattr(crachas.urllib.request, "urlopen", urlopen)
    assert crachas.buscar_cracha_no_supabase("77")["email"] == "ana@videplast.com.br"
    assert "id=eq.77&" in pedidos[-1] and "senha" not in pedidos[-1] and "admin" not in pedidos[-1]
    assert crachas.buscar_cracha_no_supabase("Ana@Videplast.com.br")["cracha"] == "77"
    assert "email=eq.ana%40videplast.com.br&" in pedidos[-1]
    feitos = len(pedidos)
    assert crachas.buscar_cracha_no_supabase("sem.cadastro") is None and len(pedidos) == feitos

    # Quem não existe só é consultado uma vez a cada 5 minutos
    resposta[0] = b"[]"
    assert crachas.buscar_cracha_no_supabase("987654") is None
    assert crachas.buscar_cracha_no_supabase("987654") is None
    assert len(pedidos) == feitos + 1


def test_tela_de_entrar_sem_atalho_de_demonstracao(cria_cliente):
    assert "Pular Login" not in cria_cliente().get("/acesso/entrar").text
