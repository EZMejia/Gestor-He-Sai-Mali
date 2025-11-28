from django import template
from decimal import Decimal

# Necesitas una instancia de template.Library para registrar el filtro
register = template.Library()

@register.filter(name='get_item')
def get_item(dictionary, key):
    """
    Permite acceder a un valor en un diccionario usando una clave (key)
    proporcionada dinámicamente en la plantilla.
    Uso en plantilla: {{ diccionario|get_item:clave }}
    """
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None

@register.filter
def mul(value, arg):
    """
    Multiplica el valor (value) por el argumento (arg). 
    Asegura que los operandos sean de tipo Decimal para precisión monetaria.
    """
    try:
        # Intenta convertir ambos a Decimal si son diferentes de None
        val_decimal = Decimal(str(value)) if value is not None else Decimal('0')
        arg_decimal = Decimal(str(arg)) if arg is not None else Decimal('0')
        return val_decimal * arg_decimal
    except:
        # Retorna 0 o None si la conversión falla
        return 0