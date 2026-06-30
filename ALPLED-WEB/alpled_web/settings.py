import os
import sys
import tempfile
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
IS_TESTING = "test" in sys.argv


def load_dotenv(path):
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]

        os.environ.setdefault(key, value)


load_dotenv(BASE_DIR / ".env")


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-#%inopjx=kh@cxo0^2vyvx3ry(mve=e+803(@jkj@uut--=bdo'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv(
        "DJANGO_ALLOWED_HOSTS",
        "127.0.0.1,localhost,host.docker.internal",
    ).split(",")
    if host.strip()
]
LOCAL_DEV_HOSTS = {"127.0.0.1", "localhost", "host.docker.internal"}
SERVE_STATIC_LOCALLY = bool(ALLOWED_HOSTS) and set(ALLOWED_HOSTS).issubset(LOCAL_DEV_HOSTS)


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'common.apps.CommonConfig',
    'users.apps.UsersConfig',
    'projects.apps.ProjectsConfig',
    'docs.apps.DocsConfig',
    'files.apps.FilesConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'users.middleware.TempPasswordChangeRequiredMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'alpled_web.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'common.context_processors.sidebar_projects',
            ],
        },
    },
]

WSGI_APPLICATION = 'alpled_web.wsgi.application'


DB_DRIVER = os.getenv("DB_DRIVER", "").strip()
USE_MYSQL = not IS_TESTING and DB_DRIVER == "mysql+pymysql"

if USE_MYSQL:
    try:
        import pymysql
    except ModuleNotFoundError as exc:
        raise ImproperlyConfigured("PyMySQL is required when DB_DRIVER=mysql+pymysql.") from exc

    pymysql.install_as_MySQLdb()
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.getenv("DB_NAME", ""),
            "USER": os.getenv("DB_USER", ""),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", ""),
            "PORT": os.getenv("DB_PORT", "3306"),
            "OPTIONS": {
                "charset": "utf8mb4",
                "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            },
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = 'static/'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'users.User'

# ONLYOFFICE 연결
ONLYOFFICE_DOCUMENT_SERVER_URL = os.getenv("ONLYOFFICE_DOCUMENT_SERVER_URL", "")
ONLYOFFICE_JWT_SECRET = os.getenv("ONLYOFFICE_JWT_SECRET", "")
DJANGO_PUBLIC_BASE_URL = os.getenv("DJANGO_PUBLIC_BASE_URL", "")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True


# FASTAPI 연결
FASTAPI_BASE_URL = os.getenv("FASTAPI_BASE_URL", "https://ntavqzbxvtbjz9-8000.proxy.runpod.net").rstrip("/")
FASTAPI_API_KEY = os.getenv("FASTAPI_API_KEY", "").strip()
DOC_JOB_POLL_INTERVAL_SECONDS = int(os.getenv("DOC_JOB_POLL_INTERVAL_SECONDS", "10"))


# AWS S3 연결
AWS_ACCESS_KEY_ID = os.getenv("S3_ACCESS_KEY", "")
AWS_SECRET_ACCESS_KEY = os.getenv("S3_SECRET_KEY", "")
AWS_STORAGE_BUCKET_NAME = os.getenv("S3_BUCKET", "")
AWS_S3_REGION_NAME = os.getenv("S3_REGION", "")
AWS_S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT", "").rstrip("/")
ALPLED_STORAGE_BACKEND = (
    "filesystem"
    if IS_TESTING or not (AWS_STORAGE_BUCKET_NAME and AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY)
    else "s3"
)
ALPLED_LOCAL_STORAGE_ROOT = Path(
    os.getenv("ALPLED_LOCAL_STORAGE_ROOT", "")
    or (Path(tempfile.gettempdir()) / "alpled_web" / "storage")
)
