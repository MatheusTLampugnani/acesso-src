# Portal de Acesso

Login único e permissões por sistema do servidor da Videplast. O Nginx pergunta ao Portal, a cada pedido, se o login pode abrir aquele sistema. O código fica em `portal-acesso/`, e o `README.md` explica a instalação.

## Regras

- **Admin e senha são do Portal.** Nunca leia nem grave esses dois campos na tabela `crachas`. O `admin` de lá vale para Bobinas, VisionStock e Mín/Máx, e no Portal abriria também RH e Jornada da Escuta.
- **Só nome, setor, unidade e e-mail circulam** entre o Portal e `crachas`. Crachá que já existe não é sobrescrito na criação (`garantir_cracha`).
- **A tela de entrar é aberta para a internet.** Rota sem login não devolve dado pessoal para quem está fora da rede, e quem não existe responde igual a quem já tem senha.
- **Texto que vem do banco** entra na tela com `textContent` ou `el()`, nunca com `innerHTML`.
- **Quem manda nos sistemas é o painel.** `SISTEMAS_INICIAIS` só vale para banco vazio, e usuário excluído não volta sozinho.
- **Nenhuma chave no repositório**, que é público. Os segredos ficam no `.env` do servidor.

## Publicar

O servidor publica sozinho o que chega no `master` em até 2 minutos e volta à versão anterior se o Portal não responder. Por isso, toda mudança vem por PR com os testes passando:

```bash
cd portal-acesso
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q
```
