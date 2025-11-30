def es_rol(rol):
    return (lambda user: user.is_authenticated and user.rol in [rol])

def es_rol_y_administrador(rol):
    return (lambda user: user.is_authenticated and user.rol in [rol,"Administrador"])