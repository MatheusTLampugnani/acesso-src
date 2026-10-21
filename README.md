# 🌐 Portal de Acesso · Videplast

Sistema centralizado de **autenticação única (SSO)**, controle de permissões por crachá e hub de sistemas do servidor da Videplast.

---

## 📌 Visão Geral

O Portal de Acesso atua como o ponto de entrada unificado para todas as aplicações industriais e administrativas hospedadas no servidor, protegendo as rotas via **Nginx (`auth_request`)** sem interferir no funcionamento interno de cada sistema.

### 🚀 Sistemas Integrados no Servidor

| Sistema | Caminho / Link | Descrição |
| :--- | :--- | :--- |
| **Inventário de Bobinas** | `/bobinas/` | Contagem física e conciliação de bobinas flexíveis (leitor, câmera, drone) |
| **Controle de Imobilizados** | `/imobilizados/` | Gestão patrimonial e inventário de bens e ativos fixos |
| **VisionStock (Almox)** | `/visionstock/` | Conferência e inventário universal de almoxarifado por SKU |
| **Rateios Operacionais** | `/rateios/` | Distribuição e rateio de custos por centros de custo e linhas |
| **Portaria de Terceiros** | `/terceirizados/` | Controle de entrada e saída de terceiros, visitantes e equipamentos |
| **Gestão de Acessos** | `/acesso/` | Painel administrativo de controle de permissões e auditoria |
| **Vitrine do Portal** | `/` | Página inicial com cards dinâmicos que exibem apenas os sistemas autorizados |

---

## ⚡ Integração com o Supabase

- **Base Corporativa:** Todos os colaboradores e crachás vêm da tabela `crachas` no Supabase (`id`, `nome_completo`, `setor`, `unidade`, `admin`, `email`, `senha_hash`).
- **Sincronização Automática:** Ao inicializar o container, o portal sincroniza em segundo plano os 180+ colaboradores cadastrados.
- **Espelhamento Contínuo:** Alterações de senha, cadastros ou edições de usuários feitas no painel são salvas localmente no SQLite e espelhadas diretamente no Supabase.
- **Resiliência Offline:** O banco SQLite local garante que a validação de rotas do Nginx responda em menos de 1ms sem dependência de internet externa.

---

## 🛠️ Implantação no Servidor Linux

Para atualizar ou instalar no servidor (`~/acesso-src`):

```bash
# 1. Clonar ou atualizar o repositório no servidor
git clone https://github.com/WandersonGuimaraesOlv/VisionStock.git ~/acesso-src
cd ~/acesso-src/portal-acesso

# 2. Instalar o serviço e configurar o Nginx
bash deploy/implantar.sh instalar

# 3. Criar o primeiro administrador ou sincronizar a base
bash deploy/implantar.sh criar-admin
bash deploy/implantar.sh sincronizar

# 4. Ativar proteção nos sistemas (modo observar para testes)
bash deploy/implantar.sh proteger

# 5. Ativar bloqueio para quem não tiver acesso
bash deploy/implantar.sh bloquear

# Em caso de emergência (libera todos os acessos sem derrubar nada):
bash deploy/implantar.sh observar
```

---

## 📁 Estrutura do Projeto

```
portal-acesso/
├── app/
│   ├── assets/              # Logotipos e identidades visuais da Videplast
│   ├── static/              # Interface do painel, login, estilos e portal.js
│   ├── banco.py             # SQLite, esquema, permissões e sessões
│   ├── crachas.py           # Cliente REST para a tabela crachas do Supabase
│   ├── rotas.py             # Endpoints FastAPI, auth_request e API REST
│   ├── seguranca.py         # Criptografia scrypt, proteção anti-brute-force
│   └── main.py              # Inicialização FastAPI com ciclo de vida assíncrono
├── deploy/
│   ├── implantar.sh         # Script de automação e deploy no Nginx/Docker
│   ├── nginx-acesso.conf    # Trecho de configuração do proxy reverso
│   └── portal-vitrine.html  # Página inicial do servidor (/var/www/portal/index.html)
├── Dockerfile               # Build leve em Python 3.12 Alpine/Debian
└── docker-compose.yml       # Orquestração do container do portal na porta 8093
```
