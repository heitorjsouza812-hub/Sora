export interface CampaignPieceData {
  titulo: string;
  formato: string;
  imagem: string;
}

const copy: Record<string, { eyebrow: string; title: string; detail: string }> = {
  'Post de inauguração': { eyebrow: 'NOVA CAFETERIA', title: 'O café que abraça.', detail: 'Inauguração · Sábado, 9h' },
  Story: { eyebrow: 'CAFETERIA AROMA', title: 'Sua nova pausa favorita.', detail: 'Vem aí · Sábado, 9h' },
  'Cartaz da vitrine': { eyebrow: 'CAFETERIA AROMA', title: 'Abrimos!', detail: 'Cafeteria Aroma · Sábado, 9h' },
};

export function CampaignPiece({ piece, generating = false }: { piece: CampaignPieceData; generating?: boolean }) {
  const text = copy[piece.titulo] ?? copy.Story;
  const slug = piece.titulo === 'Cartaz da vitrine' ? 'poster' : piece.titulo === 'Story' ? 'story' : 'post';
  return (
    <div className={`campaign-piece campaign-piece-${slug} ${generating ? 'is-generating' : ''}`}>
      <img src={piece.imagem} alt="" />
      <span className="campaign-piece-shade" />
      <div className="campaign-piece-copy"><small>{text.eyebrow}</small><strong>{text.title}</strong><span>{text.detail}</span></div>
    </div>
  );
}

