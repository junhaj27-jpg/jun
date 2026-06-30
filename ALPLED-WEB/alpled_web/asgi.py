"""
ASGI config for alpled_web project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os
import mimetypes
from pathlib import Path
from urllib.parse import unquote

from django.conf import settings
from django.core.asgi import get_asgi_application
from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'alpled_web.settings')


class LocalStaticFilesApp:
    def __init__(self, app):
        self.app = app
        self.static_url = settings.STATIC_URL if settings.STATIC_URL.startswith("/") else f"/{settings.STATIC_URL}"
        self.static_roots = [Path(path).resolve() for path in getattr(settings, "STATICFILES_DIRS", [])]

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)

        path = unquote(scope.get("path") or "")
        if not path.startswith(self.static_url):
            return await self.app(scope, receive, send)

        relative_path = path[len(self.static_url):].lstrip("/")
        for root in self.static_roots:
            candidate = (root / relative_path).resolve()
            if root == candidate or root not in candidate.parents or not candidate.is_file():
                continue

            body = candidate.read_bytes()
            content_type = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        (b"content-type", content_type.encode("ascii", "ignore")),
                        (b"content-length", str(len(body)).encode("ascii")),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        await send(
            {
                "type": "http.response.start",
                "status": 404,
                "headers": [(b"content-type", b"text/plain; charset=utf-8")],
            }
        )
        await send({"type": "http.response.body", "body": b"Not found"})


application = LocalStaticFilesApp(ASGIStaticFilesHandler(get_asgi_application()))
