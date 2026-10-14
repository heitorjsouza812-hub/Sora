"""Seletor de modelo (especificação §5).

Código comum, não um modelo: antes de toda chamada, converte papel e dificuldade num nível,
filtra os modelos que o usuário conectou e devolve uma lista ordenada (o primeiro é usado, os
outros ficam de reserva). Contém o catálogo, a política (``politica.yaml``), as flags
(``flags.yaml``) e ``escolher_modelos``.
"""
