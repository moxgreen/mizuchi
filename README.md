# Mizuchi

Django project con configurazione completa per SQLite, gestione ambiente con django-environ, e serving di static/media files con Whitenoise.

## Requisiti

- Python 3.8+
- pip

## Setup del progetto

### 1. Clona il repository

```bash
git clone <repository-url>
cd mizuchi
```

### 2. Crea e attiva il virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate  # Su macOS/Linux
# oppure
.venv\Scripts\activate  # Su Windows
```

### 3. Installa le dipendenze

```bash
pip install -r requirements.txt
```

### 4. Configura le variabili d'ambiente

Copia il file `.env.example` in `.env` e configura le variabili:

```bash
cp .env.example .env
```

Genera una nuova `SECRET_KEY`:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Modifica il file `.env` con la tua `SECRET_KEY`.

### 5. Esegui le migrazioni

```bash
python manage.py migrate
```

### 6. Crea un superuser (opzionale)

```bash
python manage.py createsuperuser
```

### 7. Raccogli i file statici

```bash
python manage.py collectstatic --noinput
```

### 8. Avvia il server di sviluppo

```bash
python manage.py runserver
```

Il progetto sarà disponibile su [http://127.0.0.1:8000](http://127.0.0.1:8000)

## Struttura del progetto

```
mizuchi/
├── .venv/              # Virtual environment (escluso da git)
├── core/               # App Django principale
├── mizuchi/            # Configurazione del progetto
│   ├── settings.py     # Configurazione con django-environ
│   ├── urls.py         # URL routing
│   ├── wsgi.py         # WSGI config
│   └── asgi.py         # ASGI config
├── static/             # File statici (CSS, JS, images)
│   ├── css/
│   ├── js/
│   └── images/
├── staticfiles/        # File statici raccolti (escluso da git)
├── media/              # File caricati dagli utenti (escluso da git)
├── manage.py           # CLI di Django
├── requirements.txt    # Dipendenze Python
├── .env                # Variabili d'ambiente (escluso da git)
├── .env.example        # Template per variabili d'ambiente
└── .gitignore          # File da escludere da git
```

## Tecnologie utilizzate

- **Django 6.0.1** - Web framework
- **django-environ** - Gestione variabili d'ambiente
- **Whitenoise** - Serving di file statici in produzione
- **SQLite** - Database (default)

## Comandi utili

```bash
# Avvia il server di sviluppo
python manage.py runserver

# Crea nuove migrazioni
python manage.py makemigrations

# Applica le migrazioni
python manage.py migrate

# Crea un superuser
python manage.py createsuperuser

# Raccogli file statici
python manage.py collectstatic

# Avvia la shell Django
python manage.py shell

# Crea una nuova app
python manage.py startapp <nome_app>
```

## Configurazione

Le variabili d'ambiente sono gestite tramite il file `.env`:

- `SECRET_KEY`: Chiave segreta di Django
- `DEBUG`: Modalità debug (True/False)
- `ALLOWED_HOSTS`: Host permessi (separati da virgola)

## Produzione

Per il deployment in produzione:

1. Imposta `DEBUG=False` nel file `.env`
2. Configura `ALLOWED_HOSTS` con i domini appropriati
3. Genera una nuova `SECRET_KEY`
4. Usa un database come PostgreSQL invece di SQLite
5. Configura un server web (nginx) e un application server (gunicorn)
6. Whitenoise gestirà automaticamente i file statici compressi

## License

[Specifica la licenza]
