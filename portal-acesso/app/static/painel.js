// Painel de gestão de acessos: matriz usuário × sistema, cadastro, sistemas e histórico.
let eu = null;
let usuarios = [];
let sistemas = [];

function mostrarAba(nome) {
  document.querySelectorAll('[data-aba]').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.aba === nome)));
  document.querySelectorAll('main > section').forEach((s) => s.classList.toggle('oculto', s.id !== 'aba-' + nome));
  if (nome === 'historico') carregarEventos();
}

function mensagem(id, texto, ok = false) {
  const alvo = document.getElementById(id);
  alvo.textContent = texto;
  alvo.classList.toggle('ok', ok);
}

async function alterarUsuario(usuario, mudanca) {
  mensagem('erro-matriz', '');
  try {
    const atualizado = await api(`/api/usuarios/${usuario.id}`, { method: 'PUT', body: mudanca });
    Object.assign(usuario, atualizado);
  } catch (e) {
    mensagem('erro-matriz', e.message);
  }
  desenharMatriz();
}

function desenharMatriz() {
  const tabela = document.getElementById('matriz');
  const cabecalho = el('tr', {},
    el('th', {}, 'Usuário'),
    sistemas.map((s) => el('th', { class: 'marca', title: s.caminho }, s.nome,
      s.aberto ? el('div', { class: 'suave', style: 'font-weight:400' }, 'todos') : null)),
    el('th', { class: 'marca' }, 'Admin'),
    el('th', { class: 'marca' }, 'Ativo'),
    el('th', {}, ''),
  );
  const filtro = document.getElementById('filtro').value.trim().toLowerCase();
  const visiveis = filtro
    ? usuarios.filter((u) => u.nome.toLowerCase().includes(filtro) || u.usuario.toLowerCase().includes(filtro))
    : usuarios;
  const linhas = visiveis.map((u) => el('tr', { class: u.ativo ? '' : 'inativo' },
    el('td', {}, el('strong', {}, u.nome), el('div', { class: 'suave' }, u.usuario,
      u.senha_pendente ? el('span', {
        class: 'selo', style: 'margin-left:6px',
        title: 'Fora da rede da empresa, a pessoa precisa deste código para criar a senha',
      }, u.codigo_acesso ? `sem senha ainda · código ${u.codigo_acesso}` : 'sem senha ainda') : null)),
    sistemas.map((s) => el('td', { class: 'marca' }, el('input', {
      type: 'checkbox',
      'aria-label': `${u.nome} acessa ${s.nome}`,
      checked: u.admin || s.aberto || u.sistemas.includes(s.slug),
      disabled: u.admin || s.aberto,
      title: u.admin ? 'Administradores veem todos os sistemas' : s.aberto ? 'Liberado para todos (aba Sistemas)' : '',
      onchange: (ev) => {
        const lista = new Set(u.sistemas);
        if (ev.target.checked) lista.add(s.slug); else lista.delete(s.slug);
        alterarUsuario(u, { sistemas: [...lista] });
      },
    }))),
    el('td', { class: 'marca' }, el('input', {
      type: 'checkbox', 'aria-label': `${u.nome} é administrador`, checked: u.admin,
      onchange: (ev) => alterarUsuario(u, { admin: ev.target.checked }),
    })),
    el('td', { class: 'marca' }, el('input', {
      type: 'checkbox', 'aria-label': `${u.nome} está ativo`, checked: u.ativo, disabled: u.usuario === eu.usuario,
      onchange: (ev) => alterarUsuario(u, { ativo: ev.target.checked }),
    })),
    el('td', {}, el('div', { class: 'marcas' },
      el('button', { type: 'button', onclick: () => redefinirSenha(u) }, 'Senha'),
      u.usuario === eu.usuario ? null : el('button', { type: 'button', class: 'perigo', onclick: () => excluirUsuario(u) }, 'Excluir'),
    )),
  ));
  tabela.replaceChildren(el('thead', {}, cabecalho), el('tbody', {}, linhas));
}

async function redefinirSenha(u) {
  const senha = prompt(`Nova senha para ${u.nome} (mínimo 6 caracteres).\nDeixe em branco para a pessoa criar uma nova no próximo acesso.`);
  if (senha === null) return;
  try {
    Object.assign(u, await api(`/api/usuarios/${u.id}`, { method: 'PUT', body: { senha } }));
    desenharMatriz();
    mensagem('erro-matriz', senha ? `Senha de ${u.nome} redefinida.`
      : `${u.nome} vai criar uma nova senha no próximo acesso (fora da empresa, com o código ${u.codigo_acesso}).`, true);
  } catch (e) { mensagem('erro-matriz', e.message); }
}

async function excluirUsuario(u) {
  if (!confirm(`Excluir o usuário ${u.nome} (${u.usuario})? Para só bloquear, desmarque "Ativo".`)) return;
  try {
    await api(`/api/usuarios/${u.id}`, { method: 'DELETE' });
    usuarios = usuarios.filter((x) => x.id !== u.id);
    desenharMatriz();
  } catch (e) { mensagem('erro-matriz', e.message); }
}

function desenharMarcasNovo() {
  for (const id of ['novo-sistemas', 'importar-sistemas']) {
    document.getElementById(id).replaceChildren(...sistemas.map((s) =>
      el('label', {}, el('input', { type: 'checkbox', value: s.slug }), s.nome)));
  }
}

function desenharSistemas() {
  const tabela = document.getElementById('tabela-sistemas');
  const linhas = sistemas.map((s) => {
    const nome = el('input', { type: 'text', value: s.nome, 'aria-label': 'Nome' });
    const caminho = el('input', { type: 'text', value: s.caminho, 'aria-label': 'Caminho' });
    const ordem = el('input', { type: 'number', value: s.ordem, 'aria-label': 'Ordem', style: 'max-width:80px' });
    const aberto = el('input', { type: 'checkbox', checked: s.aberto, 'aria-label': `${s.nome} liberado para todos` });
    return el('tr', {},
      el('td', {}, el('code', {}, s.slug)), el('td', {}, nome), el('td', {}, caminho), el('td', {}, ordem),
      el('td', { class: 'marca' }, aberto),
      el('td', {}, el('div', { class: 'marcas' },
        el('button', { type: 'button', onclick: async () => {
          try {
            sistemas = await api(`/api/sistemas/${s.slug}`, { method: 'PUT', body: {
              slug: s.slug, nome: nome.value, caminho: caminho.value, ordem: Number(ordem.value) || 0, aberto: aberto.checked,
            } });
            mensagem('erro-sistemas', 'Salvo.', true);
            atualizarTudo();
          } catch (e) { mensagem('erro-sistemas', e.message); }
        } }, 'Salvar'),
        el('button', { type: 'button', class: 'perigo', onclick: async () => {
          if (!confirm(`Remover ${s.nome} do portal? As permissões desse sistema serão apagadas.`)) return;
          try {
            await api(`/api/sistemas/${s.slug}`, { method: 'DELETE' });
            await carregar();
          } catch (e) { mensagem('erro-sistemas', e.message); }
        } }, 'Remover'),
      )),
    );
  });
  tabela.replaceChildren(
    el('thead', {}, el('tr', {}, ['Código', 'Nome', 'Caminho', 'Ordem', 'Para todos', ''].map((t) => el('th', {}, t)))),
    el('tbody', {}, linhas),
  );
}

async function carregarEventos() {
  const tabela = document.getElementById('tabela-eventos');
  try {
    const eventos = await api('/api/eventos');
    tabela.replaceChildren(
      el('thead', {}, el('tr', {}, ['Quando', 'Quem', 'O quê', 'Detalhe'].map((t) => el('th', {}, t)))),
      el('tbody', {}, eventos.map((ev) => el('tr', {},
        el('td', {}, ev.quando.replace('T', ' ')), el('td', {}, ev.usuario || ''),
        el('td', {}, ev.tipo.replaceAll('_', ' ')), el('td', {}, ev.detalhe || ''),
      ))),
    );
  } catch (e) { tabela.replaceChildren(el('tr', {}, el('td', {}, e.message))); }
}

function atualizarTudo() {
  desenharMatriz();
  desenharMarcasNovo();
  desenharSistemas();
}

async function carregar() {
  const dados = await api('/api/usuarios');
  usuarios = dados.usuarios;
  sistemas = dados.sistemas;
  atualizarTudo();
}

document.getElementById('form-novo').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  mensagem('erro-novo', '');
  try {
    const { aviso, ...novo } = await api('/api/usuarios', { method: 'POST', body: {
      usuario: document.getElementById('novo-usuario').value,
      nome: document.getElementById('novo-nome').value,
      senha: document.getElementById('novo-senha').value,
      admin: document.getElementById('novo-admin').checked,
      sistemas: [...document.querySelectorAll('#novo-sistemas input:checked')].map((c) => c.value),
    } });
    usuarios.push(novo);
    usuarios.sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR'));
    ev.target.reset();
    desenharMatriz();
    const pronto = novo.senha_pendente
      ? `${novo.nome} cadastrado. Código de primeiro acesso (fora da empresa): ${novo.codigo_acesso}.`
      : `${novo.nome} cadastrado.`;
    mensagem('erro-novo', aviso || pronto, !aviso);
  } catch (e) { mensagem('erro-novo', e.message); }
});

document.getElementById('filtro').addEventListener('input', desenharMatriz);

document.getElementById('form-importar').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const botao = ev.target.querySelector('button');
  botao.disabled = true;
  mensagem('erro-importar', 'Importando...', true);
  try {
    const r = await api('/api/importar-crachas', { method: 'POST', body: {
      sistemas: [...document.querySelectorAll('#importar-sistemas input:checked')].map((c) => c.value),
    } });
    await carregar();
    mensagem('erro-importar', `${r.novos} crachás importados (${r.existentes} já estavam cadastrados).`, true);
  } catch (e) { mensagem('erro-importar', e.message); }
  botao.disabled = false;
});

document.getElementById('form-sistema').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  mensagem('erro-sistema', '');
  try {
    sistemas = await api('/api/sistemas', { method: 'POST', body: {
      slug: document.getElementById('sis-slug').value.trim(),
      nome: document.getElementById('sis-nome').value,
      caminho: document.getElementById('sis-caminho').value,
      ordem: Number(document.getElementById('sis-ordem').value) || 0,
    } });
    ev.target.reset();
    atualizarTudo();
    mensagem('erro-sistema', 'Sistema incluído.', true);
  } catch (e) { mensagem('erro-sistema', e.message); }
});

document.getElementById('form-senha').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  try {
    await api('/api/minha-senha', { method: 'POST', body: {
      atual: document.getElementById('senha-atual').value,
      nova: document.getElementById('senha-nova').value,
    } });
    ev.target.reset();
    mensagem('erro-senha', 'Senha alterada.', true);
  } catch (e) { mensagem('erro-senha', e.message); }
});

document.querySelectorAll('[data-aba]').forEach((b) => b.addEventListener('click', () => mostrarAba(b.dataset.aba)));

(async function iniciar() {
  try {
    eu = await api('/api/eu');
  } catch (e) {
    if (e.status === 401) { location.href = BASE + '/entrar?volta=' + BASE + '/'; return; }
    throw e;
  }
  document.getElementById('quem').textContent = `${eu.nome} (${eu.usuario})`;
  document.getElementById('meus-sistemas').replaceChildren(...eu.sistemas.map((s) => el('a', { href: s.caminho }, s.nome)));
  if (eu.sistemas.length === 0) document.getElementById('meus-sistemas').append(el('p', { class: 'suave' }, 'Nenhum sistema liberado ainda.'));
  if (!eu.admin) {
    document.querySelector('.topo h1').textContent = 'Minha conta';
    mostrarAba('conta');
    return;
  }
  document.getElementById('meus-sistemas-cartao').classList.add('oculto');
  document.getElementById('aviso-modo').classList.toggle('oculto', eu.modo !== 'observar');
  document.getElementById('abas').classList.remove('oculto');
  await carregar();
  mostrarAba('usuarios');
})();
