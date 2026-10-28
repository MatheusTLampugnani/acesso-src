// src/app/App.jsx — Orquestrador: monta os módulos conforme a máquina de estados (app/estados.js).
import { useState } from 'react';
import Header from '../shared/components/Header';
import ModalDialogo from '../shared/components/ModalDialogo';
import StatusRede from '../shared/components/StatusRede';
import BannerAtualizacao from '../shared/components/BannerAtualizacao';
import { useDialogo } from '../shared/hooks/useDialogo';
import { useSyncManager } from '../modules/sync';
import { useOperador, LoginOperador, BarraOperador } from '../modules/auth';
import { ImportacaoSap } from '../modules/importacao-sap';
import { useInventario, SelecaoLocal, Bipagem, ModalQuantidade } from '../modules/inventario';
import { PainelConciliacao } from '../modules/conciliacao';
import { ETAPAS } from './estados';
import './App.css';

function App() {
  const { dialogo, fechar, abrirAlerta, abrirConfirmacao } = useDialogo();
  const { isOnline, pendingCount, syncNow, ultimoErro, servidorConfigurado } = useSyncManager();
  const { operador, logado, verificandoPortal, entrar, sair } = useOperador();
  const inventario = useInventario({ operador, abrirAlerta, aoRegistrar: syncNow });
  const [mostrarConciliacao, setMostrarConciliacao] = useState(false);

  const fazerLogout = () => {
    abrirConfirmacao('Sair', 'Deseja encerrar a sessão do operador?', () => {
      sair();
      setMostrarConciliacao(false);
      inventario.setEtapa(ETAPAS.IMPORT_SAP);
    });
  };

  const confirmarNovoInventario = () => {
    abrirConfirmacao(
      'Encerrar inventário',
      'A base SAP e as contagens deste aparelho serão apagadas (as já enviadas continuam no Supabase). Deseja começar um novo inventário?',
      () => { inventario.novoInventario(); },
      'Encerrar',
    );
  };

  const renderizarEtapa = () => {
    switch (inventario.etapa) {
      case ETAPAS.SELECAO_LOCAL:
        return (
          <SelecaoLocal
            deposito={inventario.depositoAtual}
            endereco={inventario.enderecoAtual}
            aoMudarDeposito={inventario.setDepositoAtual}
            aoMudarEndereco={inventario.setEnderecoAtual}
            aoVoltar={() => inventario.setEtapa(ETAPAS.IMPORT_SAP)}
            aoConfirmar={inventario.confirmarLocal}
          />
        );
      case ETAPAS.BIPAGEM:
        return (
          <Bipagem
            deposito={inventario.depositoAtual}
            endereco={inventario.enderecoAtual}
            leituras={inventario.leituras}
            bloqueado={!!inventario.coletaAtual || dialogo.show}
            aoLerCodigos={inventario.registrarCodigos}
            aoAlterarLocal={() => inventario.setEtapa(ETAPAS.SELECAO_LOCAL)}
          />
        );
      default:
        return (
          <ImportacaoSap
            totalItens={inventario.itensSap.length}
            totalLeituras={inventario.leituras.length}
            aoImportar={inventario.importarItens}
            aoIniciar={inventario.iniciarContagem}
            aoNovoInventario={confirmarNovoInventario}
            abrirAlerta={abrirAlerta}
          />
        );
    }
  };

  return (
    <div className="container px-3 px-md-0 pt-2 pb-5 text-start" style={{ maxWidth: mostrarConciliacao ? '1100px' : '800px', width: '100%' }}>
      {logado && <Header />}
      <BannerAtualizacao />
      {logado && (
        <div className="vp-topo-status">
          <StatusRede isOnline={isOnline} servidorConfigurado={servidorConfigurado} pendingCount={pendingCount} ultimoErro={ultimoErro} aoSincronizar={syncNow} />
        </div>
      )}

      <ModalDialogo dialogo={dialogo} aoFechar={fechar} />

      {inventario.coletaAtual && (
        <ModalQuantidade
          key={inventario.coletaAtual.chave}
          coleta={inventario.coletaAtual}
          restantes={inventario.restantesNaFila}
          aoConfirmar={inventario.confirmarQuantidade}
          aoCancelar={inventario.descartarAtual}
        />
      )}

      {verificandoPortal ? (
        // Enquanto confere o login do Portal, não mostra o operador anterior nem a tela de crachá
        <div className="d-flex flex-column align-items-center justify-content-center gap-2" style={{ minHeight: '60vh' }}>
          <div className="spinner-border text-danger" role="status" />
          <span className="small text-muted">Entrando com o seu login do Portal...</span>
        </div>
      ) : !logado ? (
        <LoginOperador aoEntrar={entrar} abrirAlerta={abrirAlerta} />
      ) : (
        <>
          <BarraOperador
            operador={operador}
            mostrandoConciliacao={mostrarConciliacao}
            aoAlternarTela={() => setMostrarConciliacao(v => !v)}
            aoSair={fazerLogout}
          />

          {mostrarConciliacao ? (
            <PainelConciliacao itensSap={inventario.itensSap} leituras={inventario.leituras} abrirAlerta={abrirAlerta} />
          ) : (
            <main>
              {inventario.carregado ? renderizarEtapa() : <div className="text-muted">Carregando dados do aparelho...</div>}
            </main>
          )}
        </>
      )}
    </div>
  );
}

export default App;
