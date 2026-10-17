"""Voz (fase 3): falar as respostas e transcrever o microfone com a chave do usuário.

Adaptado do Rakazo (github.com/elie222/rakazo, Apache-2.0): ``openai-voice.ts``,
``elevenlabs-voice.ts``, ``cartesia-voice.ts``, ``fish-audio-voice.ts``, ``voice-http.ts``
e ``core/src/speech-text.ts``.

- ``texto.py``: transforma a resposta em falas;
- ``provedores.py``: OpenAI, ElevenLabs, Cartesia e Fish Audio atrás da mesma interface
  (``ProvedorVoz``), chamados direto pelo ``httpx`` com a chave do usuário.
"""
