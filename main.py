import os
import uuid
import time
import shutil
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from fastapi.staticfiles import StaticFiles
from selenium.webdriver.chrome.service import Service

# Setup
app = FastAPI()
STATIC_DIR = "static"
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Define CHROMEDRIVER_PATH.
# On a Render deployment, you would typically install chromedriver and Google Chrome
# via your Dockerfile or build script and then set these environment variables.
# For example, in a Dockerfile:
# RUN apt-get update && apt-get install -y google-chrome-stable chromedriver
# ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
# ENV CHROME_BIN=/usr/bin/google-chrome
#
# If running locally, you'd replace these with the actual paths on your system.
# !!! IMPORTANT CHANGE HERE: Set default to /usr/local/bin/chromedriver !!!
CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "/usr/local/bin/chromedriver")
CHROME_BIN = os.getenv("CHROME_BIN", "/usr/bin/google-chrome") # Default for Render


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
    # Set the binary location for Chrome
    options.binary_location = CHROME_BIN

    # Set the executable path for Chromedriver
    service = Service(executable_path=CHROMEDRIVER_PATH)
    driver = None # Initialize driver to None for safety

    screenshot_paths = []
    try:
        driver = webdriver.Chrome(service=service, options=options)
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
        if driver: # Ensure driver exists before trying to quit
            driver.quit()
        if os.path.exists(html_path): # Ensure file exists before trying to remove
            os.remove(html_path)

    # Return public URLs relative to the /static endpoint
    return [f"/static/{os.path.basename(p)}" for p in screenshot_paths]


def cleanup_screenshots(unique_id: str):
    # Iterate through files in the STATIC_DIR
    for file in os.listdir(STATIC_DIR):
        # Check if the file starts with the unique_id
        if file.startswith(unique_id):
            try:
                os.remove(os.path.join(STATIC_DIR, file))
            except Exception as e:
                print(f"Error deleting file {file}: {e}") # Log any deletion errors


def cleanup_screenshots_later(unique_id: str):
    time.sleep(120)  # wait 2 minutes before cleaning up
    cleanup_screenshots(unique_id)

@app.post("/screenshot/")
async def screenshot_html(data: HTMLInput, background_tasks: BackgroundTasks):
    unique_id = uuid.uuid4().hex
    urls = take_screenshots(data.html, unique_id)
    # Schedule the cleanup task to run in the background
    background_tasks.add_task(cleanup_screenshots_later, unique_id)
    
    # Construct full URLs for the client response
    # Replace "https://your-service-name.onrender.com" with your actual Render service URL
    full_urls = [f"https://gethtmltoimg.onrender.com{path}" for path in urls]
    return {"images": full_urls}