from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse
from playwright.sync_api import sync_playwright
import tempfile
import os

app = FastAPI()

@app.post("/render-screenshot/")
async def render_screenshot(request: Request):
    data = await request.json()
    code = data.get("code")
    language = data.get("language")

    if not code or not language:
        raise HTTPException(status_code=400, detail="code and language are required")

    if language.lower() != "html":
        raise HTTPException(status_code=400, detail="Currently only HTML rendering is supported")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 375, "height": 812})  # Mobile viewport
        page.set_content(code)
        
        # Save screenshot to a temp file
        tmp_dir = tempfile.gettempdir()
        screenshot_path = os.path.join(tmp_dir, "screenshot.png")
        page.screenshot(path=screenshot_path, full_page=True)
        
        browser.close()

    return FileResponse(screenshot_path, media_type="image/png")
