"""Enumerações persistidas e públicas; especificação §§1, 2 e 5."""

from enum import StrEnum


class TipoAgente(StrEnum):
    SORA = "sora"
    INDIVIDUAL = "individual"
    ESPECIALISTA = "especialista"


class TipoConversa(StrEnum):
    CHAT = "chat"
    PROJETO = "projeto"
    AGENTE = "agente"


class Movimento(StrEnum):
    GIRA = "gira"
    VIBRACAO = "vibracao"
    ESPIRAL = "espiral"
    ONDAS = "ondas"


class AutorMensagem(StrEnum):
    USUARIO = "usuario"
    SORA = "sora"
    AGENTE = "agente"
    SISTEMA = "sistema"


class StatusCadeia(StrEnum):
    PLANEJANDO = "planejando"
    EXECUTANDO = "executando"
    VERIFICANDO = "verificando"
    AGUARDANDO_USUARIO = "aguardando_usuario"
    CONCLUIDA = "concluida"
    FALHOU = "falhou"
    CANCELADA = "cancelada"


class StatusEtapa(StrEnum):
    PENDENTE = "pendente"
    EXECUTANDO = "executando"
    AGUARDANDO_USUARIO = "aguardando_usuario"
    AGUARDANDO_APROVACAO = "aguardando_aprovacao"
    CONCLUIDA = "concluida"
    REPROVADA = "reprovada"
    FALHOU = "falhou"
    CANCELADA = "cancelada"


class StatusAprovacao(StrEnum):
    PENDENTE = "pendente"
    PERMITIDA = "permitida"
    NEGADA = "negada"
    EXPIRADA = "expirada"


class TipoPasso(StrEnum):
    PROMPT = "prompt"
    PENSAMENTO = "pensamento"
    FERRAMENTA = "ferramenta"
    ENTREGA = "entrega"
    HANDOFF = "handoff"


class StatusPasso(StrEnum):
    EXECUTANDO = "executando"
    CONCLUIDO = "concluido"
    ERRO = "erro"


class Nivel(StrEnum):
    N1 = "N1"
    N2 = "N2"
    N3 = "N3"


class TipoEntrega(StrEnum):
    TEXTO = "texto"
    LINKS = "links"
    IMAGEM = "imagem"
    CALENDARIO = "calendario"
    ARQUIVO = "arquivo"


class TipoMemoria(StrEnum):
    PERFIL = "perfil"
    LOG = "log"


class OrigemMemoria(StrEnum):
    EXPLICITA = "explicita"
    SINTESE = "sintese"


class TipoProvedor(StrEnum):
    GROQ = "groq"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OPENROUTER = "openrouter"
    COMPATIVEL_OPENAI = "compativel_openai"
    OLLAMA = "ollama"


class Prioridade(StrEnum):
    CUSTO = "custo"
    VELOCIDADE = "velocidade"
    QUALIDADE = "qualidade"


class DecisaoAprovacao(StrEnum):
    PERMITIR_UMA_VEZ = "permitir_uma_vez"
    SEMPRE_PERMITIR = "sempre_permitir"
    NEGAR = "negar"
