// Painel de gestão de acessos e autoatendimento de senha do colaborador
let eu = null;
let usuarios = [];
let sistemas = [];
let eventosCache = [];

// Estados de filtro e paginação da matriz
let filtroStatus = 'todos';
let filtroSetor = '';
let itensPorPagina = 20;
let paginaAtual = 1;

// Utilitários de estética visual do colaborador
const PALETAS_AVATAR = [
  { bg: '#fee2e2', color: '#991b1b' }, // Vermelho suave
  { bg: '#dbeafe', color: '#1e40af' }, // Azul suave
  { bg: '#d1fae5', color: '#065f46' }, // Esmeralda suave
  { bg: '#fef3c7', color: '#92400e' }, // Âmbar suave
  { bg: '#ede9fe', color: '#5b21b6' }, // Roxo suave
  { bg: '#ffedd5', color: '#9a3412' }, // Laranja suave
  { bg: '#cffafe', color: '#155e75' }, // Ciano suave
  { bg: '#fce7f3', color: '#9d174d' }, // Rosa suave
  { bg: '#f1f5f9', color: '#334155' }, // Ardósia suave
];

function obterPaletaAvatar(texto) {
  let hash = 0;
  for (let i = 0; i < (texto || '').length; i++) {
    hash = (hash << 5) - hash + texto.charCodeAt(i);
    hash |= 0;
  }
  const idx = Math.abs(hash) % PALETAS_AVATAR.length;
  return PALETAS_AVATAR[idx];
}

function extrairIniciais(nome) {
  if (!nome) return '??';
  const limpo = nome.trim().replace(/\s+/g, ' ');
  const partes = limpo.split(' ');
  if (partes.length === 1) return partes[0].slice(0, 2).toUpperCase();
  return (partes[0][0] + partes[partes.length - 1][0]).toUpperCase();
}

function mostrarAba(nome) {
  document.querySelectorAll('[data-aba]').forEach((b) => {
    const ativa = b.dataset.aba === nome;
    b.setAttribute('aria-selected', String(ativa));
  });
  document.querySelectorAll('main > section').forEach((s) => {
    s.classList.toggle('oculto', s.id !== 'aba-' + nome);
  });
  if (nome === 'historico') carregarEventos();
}

function mensagem(id, texto, ok = false) {
  const alvo = document.getElementById(id);
  if (!alvo) return;
  alvo.textContent = texto;
  alvo.classList.toggle('ok', ok);
  alvo.classList.toggle('erro', !ok && Boolean(texto));
}

async function alterarUsuario(usuario, mudanca) {
  mensagem('erro-matriz', '');
  try {
    const atualizado = await api(`/api/usuarios/${usuario.id}`, { method: 'PUT', body: mudanca });
    Object.assign(usuario, atualizado);
    toast(`Permissões de ${usuario.nome} atualizadas.`, 'sucesso');
  } catch (e) {
    mensagem('erro-matriz', e.message);
    toast(e.message, 'erro');
  }
  atualizarContadoresStatus();
  desenharMatriz();
}

function atualizarContadoresStatus() {
  const total = usuarios.length;
  let ativos = 0;
  let inativos = 0;
  let pendentes = 0;
  let admins = 0;

  for (const u of usuarios) {
    if (u.ativo) ativos++; else inativos++;
    if (u.senha_pendente) pendentes++;
    if (u.admin) admins++;
  }

  const setTexto = (id, val) => {
    const elemento = document.getElementById(id);
    if (elemento) elemento.textContent = val;
  };

  setTexto('count-todos', total);
  setTexto('count-ativos', ativos);
  setTexto('count-inativos', inativos);
  setTexto('count-pendentes', pendentes);
  setTexto('count-admins', admins);
}

function atualizarOpcoesSetor() {
  const select = document.getElementById('filtro-setor');
  if (!select) return;
  const valorAtual = select.value;

  const contagem = {};
  for (const u of usuarios) {
    const s = (u.setor || '').trim();
    if (s) {
      contagem[s] = (contagem[s] || 0) + 1;
    }
  }

  const setoresOrdenados = Object.keys(contagem).sort((a, b) => a.localeCompare(b, 'pt-BR'));

  select.replaceChildren(
    el('option', { value: '' }, `Todos os Setores (${usuarios.length})`),
    ...setoresOrdenados.map((s) => el('option', { value: s }, `${s} (${contagem[s]})`))
  );

  if (setoresOrdenados.includes(valorAtual)) {
    select.value = valorAtual;
  } else {
    select.value = '';
    filtroSetor = '';
  }
}

function desenharMatriz() {
  const tabela = document.getElementById('matriz');
  if (!tabela) return;

  const cabecalho = el('tr', {},
    el('th', {}, 'Colaborador / Crachá'),
    sistemas.map((s) => el('th', { class: 'marca', title: `${s.nome} (${s.caminho})` },
      el('span', {}, s.nome),
      s.aberto ? el('div', { class: 'selo sucesso', style: 'margin-top:4px; font-size:0.68rem;' },) : null,
    )),
    el('th', { class: 'marca' }, 'Admin'),
    el('th', { class: 'marca' }, 'Ativo'),
    el('th', {}, 'Ações'),
  );

  const campoFiltro = document.getElementById('filtro');
  const btnLimpar = document.getElementById('limpar-filtro');
  const termo = campoFiltro ? campoFiltro.value.trim().toLowerCase() : '';
  if (btnLimpar) btnLimpar.classList.toggle('oculto', !termo);

  // 1. Filtragem combinada por busca textual, status e setor
  const filtrados = usuarios.filter((u) => {
    if (termo) {
      const bateu = (u.nome || '').toLowerCase().includes(termo) ||
                    (u.usuario || '').toLowerCase().includes(termo) ||
                    (u.email || '').toLowerCase().includes(termo) ||
                    (u.setor || '').toLowerCase().includes(termo);
      if (!bateu) return false;
    }

    if (filtroStatus === 'ativos' && !u.ativo) return false;
    if (filtroStatus === 'inativos' && u.ativo) return false;
    if (filtroStatus === 'pendentes' && !u.senha_pendente) return false;
    if (filtroStatus === 'admins' && !u.admin) return false;

    if (filtroSetor && (u.setor || '').trim().toLowerCase() !== filtroSetor.trim().toLowerCase()) {
      return false;
    }

    return true;
  });

  const totalFiltrados = filtrados.length;

  // 2. Cálculo da paginação
  const limite = itensPorPagina === 'todos' ? (totalFiltrados || 1) : Number(itensPorPagina);
  const totalPaginas = Math.ceil(totalFiltrados / limite) || 1;

  if (paginaAtual > totalPaginas) paginaAtual = totalPaginas;
  if (paginaAtual < 1) paginaAtual = 1;

  const inicio = (paginaAtual - 1) * limite;
  const fim = itensPorPagina === 'todos' ? totalFiltrados : Math.min(inicio + limite, totalFiltrados);
  const visiveis = totalFiltrados === 0 ? [] : filtrados.slice(inicio, fim);

  // 3. Indicadores de contagem e resumo
  const contador = document.getElementById('contador-usuarios');
  if (contador) {
    const temFiltroAtivo = termo || filtroStatus !== 'todos' || filtroSetor;
    contador.textContent = temFiltroAtivo
      ? `Filtrados: ${totalFiltrados} de ${usuarios.length}`
      : `Total de ${usuarios.length} colaboradores cadastrados`;
  }

  const paginacaoInfo = document.getElementById('paginacao-info');
  if (paginacaoInfo) {
    if (totalFiltrados === 0) {
      paginacaoInfo.textContent = 'Nenhum colaborador encontrado';
    } else {
      paginacaoInfo.textContent = `Mostrando ${inicio + 1}–${fim} de ${totalFiltrados} colaboradores`;
    }
  }

  // 4. Renderização das linhas da página corrente
  const linhas = visiveis.map((u) => {
    const ehProprioUsuario = eu && u.usuario === eu.usuario;
    const paleta = obterPaletaAvatar(u.nome || u.usuario);
    const iniciais = extrairIniciais(u.nome || u.usuario);

    const avatarEl = el('div', {
      class: `colaborador-avatar ${u.admin ? 'admin-ring' : ''}`,
      style: `background-color: ${paleta.bg}; color: ${paleta.color};`,
      title: `${u.nome} (Crachá: ${u.usuario})`,
    }, iniciais);

    const linhaTopo = el('div', { class: 'colaborador-linha-topo' },
      el('span', { class: 'colaborador-nome', title: u.nome }, u.nome),
      u.admin ? el('span', { class: 'selo-admin-tag', title: 'Administrador do Portal' }, 'Admin') : null,
      ehProprioUsuario ? el('span', { class: 'selo-voce-tag', title: 'Seu usuário conectado' }, 'Você') : null,
    );

    const partesSub = [];

    // Crachá
    partesSub.push(el('span', { class: 'cracha-tag', title: `Nº do Crachá: ${u.usuario}` }, `#${u.usuario}`));

    // Setor / Unidade
    if (u.setor) {
      partesSub.push(el('span', { class: 'divisor-ponto' }, '•'));
      const textoSetor = u.setor + (u.unidade ? ` (${u.unidade})` : '');
      partesSub.push(el('span', { class: 'setor-tag', title: `Setor: ${textoSetor}` }, textoSetor));
    } else if (u.email) {
      partesSub.push(el('span', { class: 'divisor-ponto' }, '•'));
      partesSub.push(el('span', { class: 'setor-tag', title: u.email }, u.email));
    }

    // Status de Primeiro Acesso Pendente
    if (u.senha_pendente) {
      partesSub.push(el('span', { class: 'divisor-ponto' }, '•'));
      const txtAcesso = u.codigo_acesso ? `1º Acesso · Cód: ${u.codigo_acesso}` : '1º Acesso';
      partesSub.push(el('span', { class: 'status-acesso-dot', title: u.codigo_acesso ? `Colaborador ainda não cadastrou senha. Código fora da empresa: ${u.codigo_acesso}` : 'Colaborador ainda não cadastrou sua primeira senha' }, txtAcesso));
    }

    const linhaSub = el('div', { class: 'colaborador-linha-sub' }, ...partesSub);

    const celulaColaborador = el('div', { class: 'colaborador-celula' },
      avatarEl,
      el('div', { class: 'colaborador-corpo' },
        linhaTopo,
        linhaSub,
      ),
    );

    return el('tr', { class: u.ativo ? '' : 'inativo' },
      el('td', {}, celulaColaborador),
      sistemas.map((s) => el('td', { class: 'marca' }, el('input', {
        type: 'checkbox',
        'aria-label': `${u.nome} acessa ${s.nome}`,
        checked: u.admin || s.aberto || u.sistemas.includes(s.slug),
        disabled: u.admin || s.aberto,
        title: u.admin ? 'Administradores possuem acesso a todos os sistemas' : s.aberto ? 'Liberado para todos os usuários' : `Alternar acesso de ${u.nome} a ${s.nome}`,
        onchange: (ev) => {
          const lista = new Set(u.sistemas);
          if (ev.target.checked) lista.add(s.slug); else lista.delete(s.slug);
          alterarUsuario(u, { sistemas: [...lista] });
        },
      }))),
      el('td', { class: 'marca' }, el('input', {
        type: 'checkbox',
        'aria-label': `${u.nome} é administrador`,
        checked: u.admin,
        disabled: ehProprioUsuario,
        title: ehProprioUsuario ? 'Você não pode revogar seu próprio privilégio de admin' : `Alternar privilégio de administrador para ${u.nome}`,
        onchange: (ev) => alterarUsuario(u, { admin: ev.target.checked }),
      })),
      el('td', { class: 'marca' }, el('input', {
        type: 'checkbox',
        'aria-label': `${u.nome} está ativo`,
        checked: u.ativo,
        disabled: ehProprioUsuario,
        title: ehProprioUsuario ? 'Você não pode desativar seu próprio usuário' : `Ativar ou suspender acesso de ${u.nome}`,
        onchange: (ev) => alterarUsuario(u, { ativo: ev.target.checked }),
      })),
      el('td', {}, el('div', { class: 'acoes-container' },
        el('button', {
          type: 'button',
          class: 'secundario',
          title: `Redefinir ou limpar senha de ${u.nome}`,
          onclick: () => redefinirSenha(u),
        }, 'Senha'),
        ehProprioUsuario ? null : el('button', {
          type: 'button',
          class: 'perigo',
          title: `Excluir cadastro de ${u.nome}`,
          onclick: () => excluirUsuario(u),
        }, 'Excluir'),
      )),
    );
  });

  if (linhas.length === 0) {
    linhas.push(el('tr', {},
      el('td', { colspan: sistemas.length + 4, style: 'text-align:center; padding: 28px;' },
        el('span', { class: 'suave' }, 'Nenhum colaborador encontrado para os filtros selecionados.'),
      ),
    ));
  }

  tabela.replaceChildren(el('thead', {}, cabecalho), el('tbody', {}, linhas));
  desenharControlesPaginacao(totalPaginas);
}

function desenharControlesPaginacao(totalPaginas) {
  const container = document.getElementById('paginacao-nav');
  if (!container) return;

  if (totalPaginas <= 1 || itensPorPagina === 'todos') {
    container.replaceChildren();
    return;
  }

  const botoes = [];

  // Primeira página «
  botoes.push(el('button', {
    type: 'button',
    class: 'paginacao-btn',
    disabled: paginaAtual === 1,
    title: 'Primeira página',
    onclick: () => { paginaAtual = 1; desenharMatriz(); },
  }, '«'));

  // Página anterior ‹
  botoes.push(el('button', {
    type: 'button',
    class: 'paginacao-btn',
    disabled: paginaAtual === 1,
    title: 'Página anterior',
    onclick: () => { paginaAtual = Math.max(1, paginaAtual - 1); desenharMatriz(); },
  }, '‹'));

  // Janela dinâmica de páginas numéricas
  const maxVisiveis = 5;
  let inicio = Math.max(1, paginaAtual - Math.floor(maxVisiveis / 2));
  let fim = Math.min(totalPaginas, inicio + maxVisiveis - 1);

  if (fim - inicio + 1 < maxVisiveis) {
    inicio = Math.max(1, fim - maxVisiveis + 1);
  }

  if (inicio > 1) {
    botoes.push(el('button', {
      type: 'button',
      class: 'paginacao-btn',
      onclick: () => { paginaAtual = 1; desenharMatriz(); },
    }, '1'));
    if (inicio > 2) {
      botoes.push(el('span', { class: 'paginacao-elipse' }, '…'));
    }
  }

  for (let p = inicio; p <= fim; p++) {
    const ehAtual = p === paginaAtual;
    botoes.push(el('button', {
      type: 'button',
      class: `paginacao-btn ${ehAtual ? 'ativo' : ''}`,
      'aria-current': ehAtual ? 'page' : undefined,
      onclick: () => { paginaAtual = p; desenharMatriz(); },
    }, String(p)));
  }

  if (fim < totalPaginas) {
    if (fim < totalPaginas - 1) {
      botoes.push(el('span', { class: 'paginacao-elipse' }, '…'));
    }
    botoes.push(el('button', {
      type: 'button',
      class: 'paginacao-btn',
      onclick: () => { paginaAtual = totalPaginas; desenharMatriz(); },
    }, String(totalPaginas)));
  }

  // Próxima página ›
  botoes.push(el('button', {
    type: 'button',
    class: 'paginacao-btn',
    disabled: paginaAtual === totalPaginas,
    title: 'Próxima página',
    onclick: () => { paginaAtual = Math.min(totalPaginas, paginaAtual + 1); desenharMatriz(); },
  }, '›'));

  // Última página »
  botoes.push(el('button', {
    type: 'button',
    class: 'paginacao-btn',
    disabled: paginaAtual === totalPaginas,
    title: 'Última página',
    onclick: () => { paginaAtual = totalPaginas; desenharMatriz(); },
  }, '»'));

  container.replaceChildren(...botoes);
}

async function redefinirSenha(u) {
  const senha = await modalPrompt({
    titulo: `Redefinir Senha · ${u.nome}`,
    descricao: `Digite uma nova senha para ${u.nome} (${u.usuario}) ou deixe o campo em branco para que a senha seja criada no próximo acesso.`,
    placeholder: 'Nova senha (mínimo 6 caracteres) ou deixe vazio',
    dica: 'Caso deixe vazio, o usuário verá a tela de primeiro acesso para definir a própria senha.',
    botaoConfirmar: 'Salvar Senha',
    botaoCancelar: 'Cancelar',
  });

  if (senha === null) return;

  try {
    const atualizado = await api(`/api/usuarios/${u.id}`, { method: 'PUT', body: { senha } });
    Object.assign(u, atualizado);
    desenharMatriz();
    const textoMsg = senha ? `Senha de ${u.nome} redefinida com sucesso.` : `${u.nome} vai criar uma nova senha no próximo acesso${u.codigo_acesso ? ` (código fora da empresa: ${u.codigo_acesso})` : ''}.`;
    mensagem('erro-matriz', textoMsg, true);
    toast(textoMsg, 'sucesso');
  } catch (e) {
    mensagem('erro-matriz', e.message);
    toast(e.message, 'erro');
  }
}

async function excluirUsuario(u) {
  const confirmou = await modalConfirm({
    titulo: 'Excluir Colaborador',
    mensagem: `Deseja realmente remover o cadastro de ${u.nome} (${u.usuario})?`,
    detalhe: 'Dica: Caso deseje apenas impedir o acesso temporariamente, basta desmarcar a caixa "Ativo".',
    botaoConfirmar: 'Excluir Definitivamente',
    botaoCancelar: 'Cancelar',
    perigoso: true,
  });

  if (!confirmou) return;

  try {
    await api(`/api/usuarios/${u.id}`, { method: 'DELETE' });
    usuarios = usuarios.filter((x) => x.id !== u.id);
    atualizarContadoresStatus();
    atualizarOpcoesSetor();
    desenharMatriz();
    toast(`Usuário ${u.nome} removido do portal.`, 'sucesso');
  } catch (e) {
    mensagem('erro-matriz', e.message);
    toast(e.message, 'erro');
  }
}

function desenharMarcasNovo() {
  for (const id of ['novo-sistemas', 'importar-sistemas']) {
    const container = document.getElementById(id);
    if (!container) continue;

    // Preserva seleções caso a função seja chamada durante atualização de estado
    const marcadosAnteriormente = new Set(
      [...container.querySelectorAll('input:checked')].map((c) => c.value)
    );

    const cards = sistemas.map((s) => {
      const estaMarcado = marcadosAnteriormente.has(s.slug);
      const chk = el('input', {
        type: 'checkbox',
        value: s.slug,
        'aria-label': `Liberar sistema ${s.nome}`
      });
      chk.checked = estaMarcado;

      const card = el('label', {
        class: `sistema-card-item ${estaMarcado ? 'selecionado' : ''}`,
      },
        chk,
        el('div', { class: 'sistema-card-info' },
          el('span', { class: 'sistema-card-nome' }, s.nome),
          el('span', { class: 'sistema-card-slug' }, `/${s.slug}/`)
        )
      );

      chk.addEventListener('change', () => {
        card.classList.toggle('selecionado', chk.checked);
      });

      return card;
    });

    container.replaceChildren(...cards);
  }
}

window.selecionarTodosSistemas = function(containerId, marcar) {
  const container = document.getElementById(containerId);
  if (!container) return;
  const cards = container.querySelectorAll('.sistema-card-item');
  cards.forEach((card) => {
    const chk = card.querySelector('input[type="checkbox"]');
    if (chk) {
      chk.checked = marcar;
      card.classList.toggle('selecionado', marcar);
    }
  });
};


let filtroEventoTipo = '';

function desenharSistemas() {
  const tabela = document.getElementById('tabela-sistemas');
  const badgeTotal = document.getElementById('badge-total-sistemas');
  if (badgeTotal) {
    badgeTotal.textContent = `${sistemas.length} Sistemas Ativos`;
  }

  const linhas = sistemas.map((s) => {
    const nome = el('input', {
      type: 'text',
      value: s.nome,
      class: 'input-sistema-tabela',
      'aria-label': `Nome de ${s.slug}`
    });
    const caminho = el('input', {
      type: 'text',
      value: s.caminho,
      class: 'input-sistema-tabela',
      style: 'font-family:monospace;',
      'aria-label': `Caminho de ${s.slug}`
    });
    const ordem = el('input', {
      type: 'number',
      value: s.ordem,
      class: 'input-sistema-tabela',
      'aria-label': `Ordem de ${s.slug}`,
      style: 'max-width:75px; text-align:center;'
    });
    const aberto = el('input', {
      type: 'checkbox',
      checked: s.aberto,
      'aria-label': `${s.nome} liberado para todos`
    });

    return el('tr', {},
      el('td', {}, el('span', { class: 'tag-slug' }, `/${s.slug}/`)),
      el('td', {}, nome),
      el('td', {},
        el('div', { class: 'celula-caminho-link' },
          caminho,
          el('a', {
            href: s.caminho,
            target: '_blank',
            rel: 'noopener noreferrer',
            class: 'btn-link-externo-sis',
            title: `Abrir ${s.nome} no servidor (${s.caminho})`,
          }, '↗')
        )
      ),
      el('td', {}, ordem),
      el('td', { class: 'marca' }, aberto),
      el('td', { style: 'text-align: right;' }, el('div', { style: 'display:inline-flex; gap:6px;' },
        el('button', {
          type: 'button',
          class: 'btn-acao-salvar',
          onclick: async () => {
            try {
              sistemas = await api(`/api/sistemas/${s.slug}`, {
                method: 'PUT', body: {
                  slug: s.slug, nome: nome.value, caminho: caminho.value, ordem: Number(ordem.value) || 0, aberto: aberto.checked,
                }
              });
              toast(`Sistema ${s.nome} salvo com sucesso.`, 'sucesso');
              atualizarTudo();
            } catch (e) {
              mensagem('erro-sistemas', e.message);
              toast(e.message, 'erro');
            }
          },
        }, 'Salvar'),
        el('button', {
          type: 'button',
          class: 'btn-acao-remover',
          onclick: async () => {
            const confirmou = await modalConfirm({
              titulo: 'Remover Sistema Integrado',
              mensagem: `Deseja remover ${s.nome} (${s.slug}) do portal?`,
              detalhe: 'As permissões vinculadas a este sistema serão excluídas da base de acessos.',
              botaoConfirmar: 'Remover Sistema',
              botaoCancelar: 'Cancelar',
              perigoso: true,
            });
            if (!confirmou) return;
            try {
              await api(`/api/sistemas/${s.slug}`, { method: 'DELETE' });
              toast(`Sistema ${s.nome} removido.`, 'sucesso');
              await carregar();
            } catch (e) {
              mensagem('erro-sistemas', e.message);
              toast(e.message, 'erro');
            }
          },
        }, 'Remover'),
      )),
    );
  });

  tabela.replaceChildren(
    el('thead', {}, el('tr', {}, ['Identificador (Slug)', 'Nome da Aplicação', 'Caminho no Servidor (URL)', 'Ordem', 'Livre para Todos', 'Ações'].map((t, idx) =>
      el('th', { class: idx === 4 ? 'marca' : '' }, t)))),
    el('tbody', {}, linhas),
  );
}

function desenharEventosFiltrados() {
  const tabela = document.getElementById('tabela-eventos');
  const contador = document.getElementById('contador-eventos');
  const termo = (document.getElementById('filtro-eventos')?.value || '').trim().toLowerCase();

  let filtrados = eventosCache;

  if (filtroEventoTipo) {
    filtrados = filtrados.filter((ev) => {
      const t = (ev.tipo || '').toLowerCase();
      if (filtroEventoTipo === 'login') return t.includes('login');
      if (filtroEventoTipo === 'atualizou_permissoes') return t.includes('permiss') || t.includes('atualizou');
      if (filtroEventoTipo === 'usuario') return t.includes('usuario') || t.includes('criou') || t.includes('import');
      if (filtroEventoTipo === 'negado') return t.includes('negado') || t.includes('bloqueio') || t.includes('falhou');
      return t.includes(filtroEventoTipo);
    });
  }

  if (termo) {
    filtrados = filtrados.filter((ev) =>
      (ev.usuario || '').toLowerCase().includes(termo) ||
      (ev.tipo || '').toLowerCase().includes(termo) ||
      (ev.detalhe || '').toLowerCase().includes(termo) ||
      (ev.quando || '').includes(termo)
    );
  }

  if (contador) {
    contador.textContent = `Exibindo ${filtrados.length} de ${eventosCache.length} eventos`;
  }

  const formatarData = (iso) => {
    try {
      const d = new Date(iso);
      if (isNaN(d.getTime())) return { dia: iso.replace('T', ' '), hora: '' };
      const dia = d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' });
      const hora = d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      return { dia, hora };
    } catch {
      return { dia: iso.replace('T', ' '), hora: '' };
    }
  };

  const badgeTipo = (tipo) => {
    let classe = 'selo';
    let label = tipo.replaceAll('_', ' ');
    if (tipo.includes('login')) {
      classe += ' sucesso';
      label = 'Login Realizado';
    } else if (tipo.includes('permiss')) {
      classe += ' admin';
      label = 'Permissões Alteradas';
    } else if (tipo.includes('criou') || tipo.includes('import')) {
      classe += ' sucesso';
      label = 'Cadastro / Importação';
    } else if (tipo.includes('negado') || tipo.includes('falhou')) {
      classe += ' perigo';
      label = 'Acesso Bloqueado';
    }
    return el('span', { class: classe }, label);
  };

  const linhas = filtrados.map((ev) => {
    const { dia, hora } = formatarData(ev.quando);
    const dataEl = el('div', { class: 'data-evento-wrapper' },
      el('span', { class: 'data-evento-dia' }, dia),
      hora ? el('span', { class: 'data-evento-hora' }, hora) : null,
    );

    const userEl = el('div', { class: 'usuario-evento-celula' },
      el('span', { class: 'cracha-tag' }, `#${ev.usuario || 'Anônimo'}`),
    );

    return el('tr', {},
      el('td', {}, dataEl),
      el('td', {}, userEl),
      el('td', {}, badgeTipo(ev.tipo || '')),
      el('td', { class: 'suave' }, ev.detalhe || '—'),
    );
  });

  if (linhas.length === 0) {
    linhas.push(el('tr', {},
      el('td', { colspan: 4, style: 'text-align:center; padding: 28px;' },
        el('span', { class: 'suave' }, (termo || filtroEventoTipo) ? 'Nenhum evento corresponde aos filtros informados.' : 'Nenhum evento registrado ainda.'),
      ),
    ));
  }

  tabela.replaceChildren(
    el('thead', {}, el('tr', {}, ['Data / Horário', 'Usuário / Crachá', 'Operação', 'Detalhes da Ocorrência'].map((t) => el('th', {}, t)))),
    el('tbody', {}, linhas),
  );
}

async function carregarEventos() {
  const tabela = document.getElementById('tabela-eventos');
  try {
    eventosCache = await api('/api/eventos');
    desenharEventosFiltrados();
  } catch (e) {
    tabela.replaceChildren(el('tr', {}, el('td', { colspan: 4, class: 'erro' }, e.message)));
  }
}

function obterIconeDoSistema(slug) {
  switch (slug) {
    case 'bobinas':
      return '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><circle cx="12" cy="12" r="4"></circle><line x1="4.93" y1="4.93" x2="9.17" y2="9.17"></line><line x1="14.83" y1="14.83" x2="19.07" y2="19.07"></line></svg>';
    case 'imobilizados':
      return '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>';
    case 'visionstock':
      return '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>';
    case 'rateios':
      return '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.21 15.89A10 10 0 1 1 8 2.83"></path><path d="M22 12A10 10 0 0 0 12 2v10z"></path></svg>';
    case 'terceirizados':
      return '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="8.5" cy="7" r="4"></circle><line x1="20" y1="8" x2="20" y2="14"></line><line x1="23" y1="11" x2="17" y2="11"></line></svg>';
    default:
      return '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect><rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect><line x1="6" y1="6" x2="6.01" y2="6"></line><line x1="6" y1="18" x2="6.01" y2="18"></line></svg>';
  }
}

function desenharMinhaConta() {
  if (!eu) return;

  const avatarEl = document.getElementById('conta-avatar');
  if (avatarEl) {
    avatarEl.textContent = extrairIniciais(eu.nome);
    const paleta = obterPaletaAvatar(eu.nome);
    avatarEl.style.backgroundColor = paleta.color;
    avatarEl.style.color = '#ffffff';
  }

  const nomeEl = document.getElementById('conta-nome');
  if (nomeEl) nomeEl.textContent = eu.nome;

  const seloAdmin = document.getElementById('conta-selo-admin');
  if (seloAdmin) seloAdmin.classList.toggle('oculto', !eu.admin);

  const crachaEl = document.getElementById('conta-cracha');
  if (crachaEl) crachaEl.textContent = `#${eu.usuario}`;

  const setorEl = document.getElementById('conta-setor');
  if (setorEl) setorEl.textContent = eu.setor || 'Setor Geral';

  const unidadeEl = document.getElementById('conta-unidade');
  if (unidadeEl) unidadeEl.textContent = `Unidade ${eu.unidade || 1001}`;

  const emailEl = document.getElementById('conta-email');
  if (emailEl) emailEl.textContent = eu.email || 'E-mail corporativo não informado';

  const meusSistemasEl = document.getElementById('meus-sistemas');
  if (meusSistemasEl) {
    const sistemasDisponiveis = eu.sistemas || [];
    if (sistemasDisponiveis.length === 0) {
      meusSistemasEl.replaceChildren(
        el('p', { class: 'suave', style: 'padding:16px;' }, 'Nenhum sistema liberado para seu perfil no momento.')
      );
    } else {
      meusSistemasEl.replaceChildren(...sistemasDisponiveis.map((s) => {
        const link = el('a', {
          href: s.caminho,
          class: 'launcher-card',
          title: `Acessar ${s.nome}`
        },
          el('div', { class: 'launcher-info' },
            el('div', { class: 'launcher-icone' }),
            el('div', { class: 'launcher-texto' },
              el('strong', {}, s.nome),
              el('span', {}, s.caminho),
            )
          ),
          el('span', { class: 'launcher-seta' }),
        );

        const iconeEl = link.querySelector('.launcher-icone');
        if (iconeEl) {
          iconeEl.innerHTML = obterIconeDoSistema(s.slug);
        }

        const setaEl = link.querySelector('.launcher-seta');
        if (setaEl) {
          setaEl.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="7" y1="17" x2="17" y2="7"></line><polyline points="7 7 17 7 17 17"></polyline></svg>';
        }

        return link;
      }));
    }
  }
}

function atualizarTudo() {
  atualizarContadoresStatus();
  atualizarOpcoesSetor();
  desenharMatriz();
  desenharMarcasNovo();
  desenharSistemas();
  desenharMinhaConta();
}

async function carregar() {
  const dados = await api('/api/usuarios');
  usuarios = dados.usuarios;
  sistemas = dados.sistemas;
  atualizarTudo();
}

// ─── Listeners de Formulários e Eventos ─────────────────────────────

document.getElementById('form-novo').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  mensagem('erro-novo', '');
  const btn = document.getElementById('btn-cadastrar-usuario');
  btn.disabled = true;

  try {
    const emailEl = document.getElementById('novo-email');
    const setorEl = document.getElementById('novo-setor');
    const { aviso, ...novo } = await api('/api/usuarios', {
      method: 'POST', body: {
        usuario: document.getElementById('novo-usuario').value.trim(),
        nome: document.getElementById('novo-nome').value.trim(),
        email: emailEl ? emailEl.value.trim() : '',
        setor: setorEl ? setorEl.value.trim() : '',
        senha: document.getElementById('novo-senha').value,
        admin: document.getElementById('novo-admin').checked,
        sistemas: [...document.querySelectorAll('#novo-sistemas input:checked')].map((c) => c.value),
      }
    });
    usuarios.push(novo);
    usuarios.sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR'));
    ev.target.reset();
    document.getElementById('card-toggle-admin')?.classList.remove('ativo');
    selecionarTodosSistemas('novo-sistemas', false);
    atualizarContadoresStatus();
    atualizarOpcoesSetor();
    desenharMatriz();
    const pronto = (novo.senha_pendente && novo.codigo_acesso)
      ? `Colaborador ${novo.nome} cadastrado com sucesso. Código fora da empresa: ${novo.codigo_acesso}.`
      : `Colaborador ${novo.nome} cadastrado com sucesso.`;
    mensagem('erro-novo', aviso || pronto, !aviso);
    toast(`${novo.nome} adicionado ao portal.`, 'sucesso');
  } catch (e) {
    mensagem('erro-novo', e.message);
  } finally {
    btn.disabled = false;
  }
});

// Interação com o card de perfil Administrador
const cardToggleAdmin = document.getElementById('card-toggle-admin');
const chkAdmin = document.getElementById('novo-admin');
if (cardToggleAdmin && chkAdmin) {
  cardToggleAdmin.addEventListener('click', (ev) => {
    if (ev.target !== chkAdmin && !ev.target.closest('.switch-toggle')) {
      chkAdmin.checked = !chkAdmin.checked;
      cardToggleAdmin.classList.toggle('ativo', chkAdmin.checked);
    }
  });

  chkAdmin.addEventListener('change', () => {
    cardToggleAdmin.classList.toggle('ativo', chkAdmin.checked);
  });
}


const inputFiltro = document.getElementById('filtro');
if (inputFiltro) {
  inputFiltro.addEventListener('input', () => {
    paginaAtual = 1;
    desenharMatriz();
  });
}

const btnLimparFiltro = document.getElementById('limpar-filtro');
if (btnLimparFiltro) {
  btnLimparFiltro.addEventListener('click', () => {
    if (inputFiltro) inputFiltro.value = '';
    paginaAtual = 1;
    desenharMatriz();
    if (inputFiltro) inputFiltro.focus();
  });
}

// Chips de filtro por status
document.querySelectorAll('.filtro-chip').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.filtro-chip').forEach((b) => b.classList.remove('ativo'));
    btn.classList.add('ativo');
    filtroStatus = btn.dataset.status;
    paginaAtual = 1;
    desenharMatriz();
  });
});

// Seletor de Setor
const selectSetor = document.getElementById('filtro-setor');
if (selectSetor) {
  selectSetor.addEventListener('change', () => {
    filtroSetor = selectSetor.value;
    paginaAtual = 1;
    desenharMatriz();
  });
}

// Seletor de itens por página
const selectLimite = document.getElementById('itens-por-pagina');
if (selectLimite) {
  selectLimite.addEventListener('change', () => {
    itensPorPagina = selectLimite.value === 'todos' ? 'todos' : Number(selectLimite.value);
    paginaAtual = 1;
    desenharMatriz();
  });
}

const inputFiltroEventos = document.getElementById('filtro-eventos');
if (inputFiltroEventos) {
  inputFiltroEventos.addEventListener('input', desenharEventosFiltrados);
}

document.getElementById('form-importar').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const botao = document.getElementById('btn-importar');
  botao.disabled = true;
  mensagem('erro-importar', 'Consultando base de crachás...', true);

  try {
    const r = await api('/api/importar-crachas', {
      method: 'POST', body: {
        sistemas: [...document.querySelectorAll('#importar-sistemas input:checked')].map((c) => c.value),
      }
    });
    await carregar();
    selecionarTodosSistemas('importar-sistemas', false);
    const textoMsg = `${r.novos} novos crachás importados (${r.existentes} já cadastrados).`;
    mensagem('erro-importar', textoMsg, true);
    toast(textoMsg, 'sucesso');
  } catch (e) {
    mensagem('erro-importar', e.message);
    toast(e.message, 'erro');
  } finally {
    botao.disabled = false;
  }
});

// Toggle de sistema livre para todos
const cardToggleAberto = document.getElementById('card-toggle-aberto');
const chkAberto = document.getElementById('sis-aberto');
if (cardToggleAberto && chkAberto) {
  cardToggleAberto.addEventListener('click', (ev) => {
    if (ev.target !== chkAberto && !ev.target.closest('.switch-toggle')) {
      chkAberto.checked = !chkAberto.checked;
      cardToggleAberto.classList.toggle('ativo', chkAberto.checked);
    }
  });

  chkAberto.addEventListener('change', () => {
    cardToggleAberto.classList.toggle('ativo', chkAberto.checked);
  });
}

document.getElementById('form-sistema').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  mensagem('erro-sistema', '');
  const btn = document.getElementById('btn-cadastrar-sistema');
  if (btn) btn.disabled = true;

  try {
    sistemas = await api('/api/sistemas', {
      method: 'POST', body: {
        slug: document.getElementById('sis-slug').value.trim(),
        nome: document.getElementById('sis-nome').value.trim(),
        caminho: document.getElementById('sis-caminho').value.trim(),
        ordem: Number(document.getElementById('sis-ordem').value) || 0,
        aberto: Boolean(chkAberto && chkAberto.checked),
      }
    });
    ev.target.reset();
    if (cardToggleAberto) cardToggleAberto.classList.remove('ativo');
    atualizarTudo();
    mensagem('erro-sistema', 'Sistema integrado com sucesso.', true);
    toast('Aplicação integrada com sucesso.', 'sucesso');
  } catch (e) {
    mensagem('erro-sistema', e.message);
  } finally {
    if (btn) btn.disabled = false;
  }
});

// Chips de filtro da trilha de auditoria
document.querySelectorAll('.filtro-chip-evento').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.filtro-chip-evento').forEach((b) => b.classList.remove('ativo'));
    btn.classList.add('ativo');
    filtroEventoTipo = btn.dataset.tipo || '';
    desenharEventosFiltrados();
  });
});

// Validação em tempo real dos requisitos de nova senha
const inputSenhaNova = document.getElementById('senha-nova');
if (inputSenhaNova) {
  inputSenhaNova.addEventListener('input', () => {
    const val = inputSenhaNova.value;
    const reqTamanho = document.getElementById('req-tamanho');
    const reqDiferente = document.getElementById('req-diferente');
    if (reqTamanho) reqTamanho.classList.toggle('atendido', val.length >= 6);
    if (reqDiferente) reqDiferente.classList.toggle('atendido', Boolean(val && (!eu || val !== eu.usuario)));
  });
}

document.getElementById('form-senha').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const btn = document.getElementById('btn-salvar-minha-senha');
  btn.disabled = true;
  mensagem('erro-senha', '');

  try {
    await api('/api/minha-senha', {
      method: 'POST', body: {
        atual: document.getElementById('senha-atual').value,
        nova: document.getElementById('senha-nova').value,
      }
    });
    ev.target.reset();
    const reqTamanho = document.getElementById('req-tamanho');
    const reqDiferente = document.getElementById('req-diferente');
    if (reqTamanho) reqTamanho.classList.remove('atendido');
    if (reqDiferente) reqDiferente.classList.remove('atendido');
    mensagem('erro-senha', 'Senha alterada com sucesso.', true);
    toast('Sua senha foi atualizada com sucesso.', 'sucesso');
  } catch (e) {
    mensagem('erro-senha', e.message);
  } finally {
    btn.disabled = false;
  }
});

document.querySelectorAll('[data-aba]').forEach((b) => b.addEventListener('click', () => mostrarAba(b.dataset.aba)));

// Conecta os botões de toggle de senha
configurarAlternadorSenha(document.getElementById('novo-senha'), document.getElementById('toggle-novo-senha'));
configurarAlternadorSenha(document.getElementById('senha-atual'), document.getElementById('toggle-senha-atual'));
configurarAlternadorSenha(document.getElementById('senha-nova'), document.getElementById('toggle-senha-nova'));

// Botão de Sincronização rápida direta com o Supabase
const btnSyncSupabase = document.getElementById('btn-sync-supabase');
if (btnSyncSupabase) {
  btnSyncSupabase.addEventListener('click', async () => {
    btnSyncSupabase.disabled = true;
    toast('Consultando e sincronizando base com o Supabase...', 'info');
    try {
      const res = await api('/api/importar-crachas', { method: 'POST', body: { sistemas: [] } });
      await carregar();
      toast(`Supabase sincronizado: ${res.novos} novos colaboradores, ${res.existentes} atualizados.`, 'sucesso');
    } catch (e) {
      toast(`Erro ao sincronizar com Supabase: ${e.message}`, 'erro');
    } finally {
      btnSyncSupabase.disabled = false;
    }
  });
}

// ─── Inicialização da Aplicação ────────────────────────────────────

(async function iniciar() {
  try {
    eu = await api('/api/eu');
  } catch (e) {
    if (e.status === 401) {
      location.href = BASE + '/entrar?volta=' + encodeURIComponent(BASE + '/');
      return;
    }
    throw e;
  }

  // Preenche dados do usuário logado na barra superior
  const quemEl = document.getElementById('quem');
  if (quemEl) {
    quemEl.textContent = `${eu.nome} (${eu.usuario})`;
  }

  // Preenche a tela Minha Conta e Launcher de Aplicações
  desenharMinhaConta();

  const tituloEl = document.getElementById('titulo-painel');

  // Modo Usuário Comum (não-administrador)
  if (!eu.admin) {
    if (tituloEl) tituloEl.textContent = 'Minha Conta';
    mostrarAba('conta');
    return;
  }

  // Modo Administrador
  const avisoModo = document.getElementById('aviso-modo');
  if (avisoModo) avisoModo.classList.toggle('oculto', eu.modo !== 'observar');

  const abasNav = document.getElementById('abas');
  if (abasNav) abasNav.classList.remove('oculto');

  await carregar();
  carregarEventos();
  mostrarAba('usuarios');
})();
