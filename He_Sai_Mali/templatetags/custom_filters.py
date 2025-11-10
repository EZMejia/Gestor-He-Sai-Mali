from django import template

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