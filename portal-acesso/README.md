# Portal de Acesso

Login único e controle de **quais usuários veem cada sistema** do servidor (Bobinas, Imobilizados,
VisionStock, Rateios, Portaria de Terceiros e os que forem incluídos depois).

- **Painel** em `/acesso/`: matriz usuário × sistema (marca e salva na hora), cadastro, ativar/desativar,
  redefinir senha, cadastro de sistemas e histórico (logins, alterações e acessos negados).
- **Proteção no Nginx** (`auth_request`): antes de abrir `/rateios/`, `/visionstock/` etc., o Nginx pergunta
  ao serviço se aquele login pode. Os sistemas não foram alterados e os logins internos deles continuam valendo.
- **Portal** (`/`): um script esconde os cards que o usuário não pode abrir e mostra quem está logado.
- **Crachás importados** da base do VisionStock (tabela `crachas` do Supabase): o login é o número do crachá
  e cada pessoa cria a própria senha no primeiro acesso. O botão "Senha" com o campo vazio faz a pessoa criar outra.
- **Usuário criado no portal com login numérico** também entra na tabela `crachas` do Supabase (se ainda não existir),
  porque o Bobinas confere o crachá lá depois do login. Para quem foi criado antes disso:
  `docker compose exec acesso python -m app.cli sincronizar-crachas`.
- **Usuários em SQLite** dentro de um volume Docker: funciona sem internet e não depende do Supabase.
  Senhas com scrypt; sessões guardadas só como hash e derrubadas ao desativar o usuário ou trocar a senha.

## Modos (implantação sem trancar ninguém para fora)

| Modo | O que acontece |
| :--- | :--- |
| `observar` (padrão) | Ninguém é barrado. Quem **seria** barrado aparece no Histórico. Se o serviço cair, os sistemas seguem abertos. |
| `bloquear` | Sem login vai para a tela de entrar; sem permissão vai para "Sem acesso". |

## Implantação no servidor

```bash
git clone https://github.com/WandersonGuimaraesOlv/VisionStock.git ~/acesso-src
bash ~/acesso-src/portal-acesso/deploy/implantar.sh instalar     # serviço na porta 8093 + /acesso/ no Nginx + portal
bash ~/acesso-src/portal-acesso/deploy/implantar.sh criar-admin  # primeiro administrador
bash ~/acesso-src/portal-acesso/deploy/implantar.sh importar     # cadastra os crachás do VisionStock (opcional: importar visionstock,bobinas)
bash ~/acesso-src/portal-acesso/deploy/implantar.sh atualizar    # baixa a versão nova do código
bash ~/acesso-src/portal-acesso/deploy/implantar.sh proteger     # liga a checagem nos sistemas (ainda observando)
bash ~/acesso-src/portal-acesso/deploy/implantar.sh bloquear     # passa a barrar
bash ~/acesso-src/portal-acesso/deploy/implantar.sh observar     # emergência: libera todo mundo de novo
bash ~/acesso-src/portal-acesso/deploy/implantar.sh desfazer     # remove tudo do Nginx e do portal
```

Toda alteração no Nginx faz backup, roda `nginx -t` e volta sozinha se der erro. Os trechos de Nginx
estão em `deploy/nginx-acesso.conf`.

Senha esquecida do administrador: `cd ~/acesso-src/portal-acesso && docker compose exec acesso python -m app.cli redefinir-senha <usuario>`.

## Desenvolvimento

```bash
cd portal-acesso
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q
ACESSO_BANCO=./dev.db uvicorn main:app --reload --port 8093   # abre http://localhost:8093/acesso/
```
