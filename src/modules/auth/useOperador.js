// src/modules/auth/useOperador.js — Sessão do operador identificado pelo crachá.
import { useEffect, useState } from 'react';
import { supabase } from '../../shared/lib/supabase';

const CHAVES = { cracha: 'usuario_cracha', nome: 'usuario_nome', admin: 'usuario_is_admin' };
const VAZIO = { cracha: '', nome: '', isAdmin: false };

// Portal de Acesso no mesmo endereço (Nginx): informa quem está logado e encerra a sessão de todos os sistemas
const PORTAL_EU = '/acesso/api/eu';
const PORTAL_SAIR = '/acesso/api/sair';

const lerSessao = () => ({
  cracha: sessionStorage.getItem(CHAVES.cracha) || '',
  nome: sessionStorage.getItem(CHAVES.nome) || '',
  isAdmin: sessionStorage.getItem(CHAVES.admin) === 'true',
});

/**
 * Busca o crachá no Supabase (tabela "crachas").
 * Offline, com erro de rede ou crachá não cadastrado, entra como operador comum (nunca como admin).
 */
const buscarOperador = async (cracha) => {
  const padrao = { cracha, nome: `Operador ${cracha}`, isAdmin: false };
  if (!navigator.onLine || !supabase) return padrao;
  try {
    const { data, error } = await supabase
      .from('crachas')
      .select('id, nome_completo, admin')
      .eq('id', cracha)
      .maybeSingle();
    if (error) throw error;
    if (!data) return padrao;
    return { cracha, nome: data.nome_completo || padrao.nome, isAdmin: !!data.admin };
  } catch (err) {
    console.warn('Login em modo offline:', err);
    return padrao;
  }
};

export function useOperador() {
  const [operador, setOperador] = useState(lerSessao);
  // Offline o Portal não responde: segue direto com a sessão do aparelho ou a tela de crachá
  const [verificandoPortal, setVerificandoPortal] = useState(() => navigator.onLine);

  // Login único: com rede, o operador é quem entrou no Portal. Um login do Portal que não é crachá
  // (ex.: administrador) descarta o operador anterior e a tela de crachá aparece.
  useEffect(() => {
    if (!navigator.onLine) return undefined;
    let cancelado = false;
    (async () => {
      try {
        const resposta = await fetch(PORTAL_EU, { credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json' } });
        if (!resposta.ok) return;
        const eu = await resposta.json();
        const crachaPortal = String(eu?.usuario || '').trim();
        if (!crachaPortal || crachaPortal === lerSessao().cracha) return;
        const novo = /^\d+$/.test(crachaPortal) ? await buscarOperador(crachaPortal) : VAZIO;
        if (!cancelado) setOperador(novo);
      } catch {
        // Sem Portal (ex.: desenvolvimento) ou rede instável: mantém o login por crachá
      } finally {
        if (!cancelado) setVerificandoPortal(false);
      }
    })();
    return () => { cancelado = true; };
  }, []);

  useEffect(() => {
    if (operador.cracha) {
      sessionStorage.setItem(CHAVES.cracha, operador.cracha);
      sessionStorage.setItem(CHAVES.nome, operador.nome);
      sessionStorage.setItem(CHAVES.admin, String(operador.isAdmin));
    } else {
      Object.values(CHAVES).forEach(c => sessionStorage.removeItem(c));
    }
  }, [operador]);

  const entrar = async (crachaDigitado) => {
    const cracha = String(crachaDigitado || '').trim();
    if (!cracha) return false;
    setOperador(await buscarOperador(cracha));
    return true;
  };

  // Com rede, Sair encerra também o login do Portal; senão o login único entraria de novo na mesma hora.
  // Offline, apenas volta para a tela de crachá (o inventário do aparelho é mantido).
  const sair = async () => {
    setOperador(VAZIO);
    if (!navigator.onLine) return;
    try {
      const resposta = await fetch(PORTAL_SAIR, { method: 'POST', credentials: 'same-origin', headers: { 'X-Portal': '1' } });
      if (resposta.ok) window.location.href = `/acesso/entrar?volta=${encodeURIComponent(window.location.pathname)}`;
    } catch {
      // Sem Portal: a tela de crachá já aparece
    }
  };

  return { operador, logado: !!operador.cracha, verificandoPortal, entrar, sair };
}
