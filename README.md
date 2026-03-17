# Crear entorno virtual

python -m venv venv

# Activar entorno (Windows)

venv\Scripts\activate

# Entrar a la carpeta del proyecto

D:
cd D:\app_multi_tenant
D:\app_multi_tenant\venv\Scripts\activate
cd tenant
python manage.py runserver --settings=config.settings.development

# crear una app

python manage.py startapp jobs

# eliminar archivos de cache en la raíz del proyecto

del /s /q **pycache**
del /s /q \*.pyc

# Instalar dependencias

pip install -r requirements.txt

# Crear migraciones de apps locales

python manage.py makemigrations --settings=config.settings.development

# Aplicar migraciones

python manage.py migrate --settings=config.settings.development

# Crear superusuario

python manage.py createsuperuser --settings=config.settings.development

# Ver estado de migraciones

python manage.py showmigrations --settings=config.settings.development

# Shell de Django

python manage.py shell --settings=config.settings.development

# Crear migración específica

python manage.py makemigrations authentication --settings=config.settings.development
python manage.py makemigrations organizations --settings=config.settings.development
python manage.py makemigrations profiles --settings=config.settings.development

# Resetear base de datos (SQLite)

del db.sqlite3

# Borrar migraciones de authentication (para recrearlas limpias)

del authentication\migrations\0001_initial.py
python manage.py migrate --settings=config.settings.development

# URLs

    API: http://127.0.0.1:8000/api/v1/
    Admin: http://127.0.0.1:8000/admin/

Identifier: 123456789321
Email: admin@admin.com
Username: admin
Password:Vivayo123!

# Crear superusuario con organización

User.objects.create_superuser(

    email='admin@admin.com',
    username='admin',
    password='admin123',
    organization=org
    )
