import os
import uuid
import time
import shutil
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from fastapi.staticfiles import StaticFiles

# Setup
app = FastAPI()
STATIC_DIR = "static"
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

class HTMLInput(BaseModel):
    html: str

def take_screenshots(html_content: str, unique_id: str) -> list[str]:
    # Save HTML to file
    html_path = f"/tmp/{unique_id}.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    # Chrome setup
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1280,800")
    options.binary_location = os.getenv("CHROME_BIN", "/usr/bin/google-chrome")

    driver = webdriver.Chrome(
        executable_path=os.getenv("CHROMEDRIVER_PATH", "/usr/local/bin/chromedriver"),
        options=options
    )

    screenshot_paths = []
    try:
        driver.get(f"file://{html_path}")
        time.sleep(2)  # Wait for content to load

        scroll_height = driver.execute_script("return document.body.scrollHeight")
        viewport_height = driver.execute_script("return window.innerHeight")

        scroll_pos = 0
        index = 0

        while scroll_pos < scroll_height:
            driver.execute_script(f"window.scrollTo(0, {scroll_pos})")
            time.sleep(0.5)
            filename = f"{unique_id}_{index}.png"
            filepath = os.path.join(STATIC_DIR, filename)
            driver.save_screenshot(filepath)
            screenshot_paths.append(filepath)
            scroll_pos += viewport_height
            index += 1

    finally:
        driver.quit()
        os.remove(html_path)

    return [f"/static/{os.path.basename(p)}" for p in screenshot_paths]

def cleanup_screenshots(unique_id: str):
    for file in os.listdir(STATIC_DIR):
        if file.startswith(unique_id):
            try:
                os.remove(os.path.join(STATIC_DIR, file))
            except:
                pass

@app.post("/screenshot/")
async def screenshot_html(data: HTMLInput, background_tasks: BackgroundTasks):
    unique_id = uuid.uuid4().hex
    urls = take_screenshots(data.html, unique_id)
    background_tasks.add_task(cleanup_screenshots_later, unique_id)
    full_urls = [f"https://your-service-name.onrender.com{path}" for path in urls]
    return {"images": full_urls}

def cleanup_screenshots_later(unique_id: str):
    time.sleep(120)  # wait 2 minutes
    cleanup_screenshots(unique_id)
