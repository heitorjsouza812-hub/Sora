// Estado vazio da grade: a Sora em idle esperando o primeiro projeto (ou nada encontrado na busca/filtro).
import { SoraOrb } from '../mascot';

export function EstadoVazio({ corSora, nomeSora, busca, onLimpar }: { corSora: string; nomeSora: string; busca?: boolean; onLimpar?: () => void }) {
  return (
    <div className="pj-vazio">
      <SoraOrb size={busca ? 96 : 150} color={corSora} state="idle" seed={5} decorative />
      {busca ? <>
        <h3>Nenhum projeto encontrado</h3>
        <p>Tente outra palavra ou outro filtro.</p>
        {onLimpar && <button type="button" className="pj-limpar" onClick={onLimpar}>Limpar busca e filtro</button>}
      </> : <>
        <h3>Nenhum projeto ainda</h3>
        <p>Descreva um projeto acima. A {nomeSora} monta o plano, cria a equipe de agentes e te avisa quando estiver pronto para revisar.</p>
      </>}
    </div>
  );
}
