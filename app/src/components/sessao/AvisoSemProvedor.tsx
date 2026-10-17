// Aviso na Home enquanto a conta não tem nenhum provedor de IA conectado.
import { Link } from 'react-router-dom';
import { useSessao } from '../../state/sessao';
import './sessao.css';

export function AvisoSemProvedor() {
  const { usuario } = useSessao();
  if (!usuario || usuario.tem_provedor) return null;
  return (
    <p className="aviso-provedor" role="status">
      Nenhuma API de IA conectada ainda. <Link to="/configuracoes">Conectar em Configurações</Link>
    </p>
  );
}
