import html
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = ROOT / "templates"

def render_dashboard(policy: dict[str, Any]) -> str:
    site_name = html.escape(str(policy.get("site", {}).get("name", "EDC")))
    try:
        template = (TEMPLATES_DIR / "dashboard.html").read_text(encoding="utf-8")
    except FileNotFoundError:
        return "<h1>Error: dashboard.html not found</h1>"
    return template.replace("{SITE_NAME}", site_name)

def render_honeypot_page(policy: dict[str, Any], catalog: dict[str, Any], sensor_id: str, module_id: str) -> str | None:
    # Проверка наличия модуля в каталоге (упрощенно, можно вынести в state.py)
    # Здесь логика поиска title
    title = "Honeypot Config"
    for mod in catalog.get("modules", []):
        if mod.get("id") == module_id:
            title = html.escape(str(mod.get("title") or module_id))
            break
            
    safe_module_id = html.escape(module_id)
    safe_sensor_id = html.escape(sensor_id)
    
    try:
        template = (TEMPLATES_DIR / "honeypot.html").read_text(encoding="utf-8")
    except FileNotFoundError:
        return "<h1>Error: honeypot.html not found</h1>"
        
    return template.replace("{TITLE}", title).replace("{MODULE_ID}", safe_module_id).replace("{SENSOR_ID}", safe_sensor_id)