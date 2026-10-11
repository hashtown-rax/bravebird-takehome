import json
import os
import sys
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

# Add project root to path so we can import bot
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bot import run_bot


@require_GET
def index(request):
    return render(request, "index.html")


@require_POST
def run_bot_view(request):
    data = json.loads(request.body)

    items = data.get("items", [])
    customer = data.get("customer", {})

    # Credentials from env vars; role dropdown overrides the username
    username = data.get("role") or os.environ.get("SAUCE_USERNAME")
    password = os.environ.get("SAUCE_PASSWORD")

    if not username or not password:
        return JsonResponse({
            "result": {
                "status": "failed",
                "item_total": None,
                "tax": None,
                "total": None,
                "items_not_found": [],
                "error": "SAUCE_USERNAME and SAUCE_PASSWORD environment variables are required.",
            },
            "products": [],
            "added": [],
            "logs": ["FAILED: Set SAUCE_USERNAME and SAUCE_PASSWORD env vars before starting the server."],
            "customer": customer,
        })

    bot_output = run_bot(
        username=username,
        password=password,
        shopping_list=items,
        customer=customer,
        output_dir=settings.OUTPUT_DIR,
    )

    return JsonResponse(bot_output)


@require_GET
def download_file(request, filename):
    allowed_files = {"products.json", "result.json", "confirmation.png"}
    if filename not in allowed_files:
        raise Http404

    file_path = settings.OUTPUT_DIR / filename
    if not file_path.exists():
        raise Http404

    as_attachment = "preview" not in request.GET
    return FileResponse(open(file_path, "rb"), as_attachment=as_attachment, filename=filename)
