def es_rol(rol):
    return (lambda user: user.is_authenticated and user.rol in [rol,"Administrador"])