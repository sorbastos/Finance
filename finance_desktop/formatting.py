"""Formatação de apresentação: centavos nunca passam por ponto flutuante."""

from decimal import Decimal
import re


def installment_title(description: str, status: str) -> str:
    """Separa a numeração da parcela da descrição comercial para leitura rápida."""
    if status != 'Previsto':
        return status
    match = re.search(r'Parcela\s+(\d+)\s+de\s+(\d+)', description, re.I)
    return f'{match[1]} de {match[2]}' if match else 'A conferir'


def month_title(period: str) -> str:
    """Exibe a competência em português sem depender do locale do computador."""
    from finance import validate_month
    validate_month(period)
    names = ('Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
             'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro')
    year, month = period.split('-')
    return f'{names[int(month)-1]} de {year}'


def currency(cents: int | None) -> str:
    """Formata centavos em reais; ausência de metadado não significa valor zero."""
    if cents is None:
        return 'Não informado'
    sign = '-' if cents < 0 else ''
    units, fraction = divmod(abs(cents), 100)
    return f'R$ {sign}{units:,}'.replace(',', '.') + f',{fraction:02d}'


def editable_money(cents: int | None) -> str:
    """Retorna texto decimal exato para formulários, aceito por core.money."""
    return '' if cents is None else str(Decimal(cents) / 100)


def trend(current: int, previous: int, has_base: bool) -> str:
    """Evita inventar crescimento quando não existe base ou ela é zero."""
    if not has_base or not previous:
        return 'Sem base no mês anterior'
    percent = Decimal(current - previous) * 100 / abs(previous)
    arrow = '↑' if percent > 0 else '↓' if percent < 0 else '→'
    return f'{arrow} {abs(percent):.1f}% vs. mês anterior'
