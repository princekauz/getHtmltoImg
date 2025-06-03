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
from typing import Optional # New import: Used for Optional fields in Pydantic models

# Setup
app = FastAPI()
STATIC_DIR = "static"
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Define CHROMEDRIVER_PATH and CHROME_BIN.
# These environment variables are expected to be set by your Dockerfile or Render's environment.
# Defaults are provided for local testing or if environment variables are not explicitly set.
CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "/usr/local/bin/chromedriver")
CHROME_BIN = os.getenv("CHROME_BIN", "/usr/bin/google-chrome")

# Pydantic model for request body validation
class HTMLInput(BaseModel):
    html: str
    # device_type can be "desktop" or "phone"
    # Default is "desktop"
    device_type: Optional[str] = "desktop"
    # orientation can be "portrait" or "landscape".
    # Primarily affects rendering when device_type is "phone".
    # Default is "portrait"
    orientation: Optional[str] = "portrait"

# 1. Health check endpoint
@app.get("/health")
async def health_check():
    """
    Returns an OK status for health checks.
    """
    return {"status": "OK"}

def take_screenshots(html_content: str, unique_id: str, device_type: str, orientation: str) -> list[str]:
    """
    Renders HTML content in a headless Chrome browser and takes screenshots,
    handling scrolling for long pages and device emulation.
    """
    # Save HTML to a temporary file
    html_path = f"/tmp/{unique_id}.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    # Chrome options setup
    options = Options()
    options.add_argument("--headless")      # Run Chrome in headless mode (no UI)
    options.add_argument("--disable-gpu")   # Recommended for headless on some systems
    options.add_argument("--no-sandbox")    # Necessary for running as root in Docker
    options.binary_location = CHROME_BIN    # Path to Google Chrome executable

    # Define viewport dimensions and apply device emulation if necessary
    viewport_width = 0
    viewport_height = 0

    if device_type and device_type.lower() == "phone":
        mobile_emulation = {}
        if orientation and orientation.lower() == "landscape":
            # Common landscape phone dimensions (e.g., iPhone X in landscape)
            viewport_width = 667
            viewport_height = 375
        else: # Default or invalid orientation for phone -> portrait
            # Common portrait phone dimensions (e.g., iPhone X in portrait)
            viewport_width = 375
            viewport_height = 667
        
        # Apply mobile emulation with specific device metrics and a mobile user agent
        mobile_emulation["deviceMetrics"] = {"width": viewport_width, "height": viewport_height, "pixelRatio": 2.0}
        mobile_emulation["userAgent"] = "Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0.3 Mobile/15E148 Safari/604.1"
        options.add_experimental_option("mobileEmulation", mobile_emulation)
        
        # Set the browser window size to match the viewport dimensions for consistent screenshot sizing
        # Note: When mobileEmulation is active, deviceMetrics dictate the rendering area,
        # but --window-size still sets the overall browser window size. Setting it to match
        # helps ensure the saved screenshot has the expected dimensions.
        options.add_argument(f"--window-size={viewport_width},{viewport_height}")

    else: # Default to desktop (or if device_type is explicitly "desktop")
        viewport_width = 1280
        viewport_height = 800
        options.add_argument(f"--window-size={viewport_width},{viewport_height}")
        # No mobile emulation for desktop

    # Set the executable path for Chromedriver service
    service = Service(executable_path=CHROMEDRIVER_PATH)
    driver = None # Initialize driver to None for safety

    screenshot_paths = []
    MAX_SCREENSHOTS = 20 # Limit the number of screenshots to prevent excessive resource usage

    try:
        driver = webdriver.Chrome(service=service, options=options)
        driver.get(f"file://{html_path}")
        time.sleep(2)  # Give the page time to load all content and execute JavaScript

        # Get the total scrollable height of the document body
        scroll_height = driver.execute_script("return document.body.scrollHeight")
        # Get the actual viewport height (this will reflect mobile emulation if applied)
        viewport_height = driver.execute_script("return window.innerHeight") 

        # Debugging output (can be uncommented for local testing)
        # print(f"DEBUG: Rendered with Viewport: {driver.execute_script('return window.innerWidth')}x{viewport_height}")
        # print(f"DEBUG: Document Scroll Height: {scroll_height}")
        # print(f"DEBUG: Device Type: {device_type}, Orientation: {orientation}")

        scroll_pos = 0
        index = 0

        # Loop to take screenshots by scrolling down the page
        while scroll_pos < scroll_height and index < MAX_SCREENSHOTS:
            driver.execute_script(f"window.scrollTo(0, {scroll_pos})")
            time.sleep(0.5) # Short pause to allow content to render correctly after scrolling
            
            filename = f"{unique_id}_{index}.png"
            filepath = os.path.join(STATIC_DIR, filename)
            driver.save_screenshot(filepath) # Take screenshot of the current viewport
            screenshot_paths.append(filepath)
            
            scroll_pos += viewport_height # Move to the next viewport position
            index += 1 # Increment screenshot index

    finally:
        # Ensure the WebDriver is quit and the temporary HTML file is removed
        if driver:
            driver.quit()
        if os.path.exists(html_path):
            os.remove(html_path)

    # Return public URLs relative to the /static endpoint
    return [f"/static/{os.path.basename(p)}" for p in screenshot_paths]


def cleanup_screenshots(unique_id: str):
    """
    Deletes all screenshot files associated with a given unique_id from the STATIC_DIR.
    """
    for file in os.listdir(STATIC_DIR):
        if file.startswith(unique_id):
            try:
                os.remove(os.path.join(STATIC_DIR, file))
            except Exception as e:
                print(f"Error deleting file {file}: {e}") # Log any deletion errors


def cleanup_screenshots_later(unique_id: str):
    """
    Schedules a cleanup task to run after a delay.
    """
    time.sleep(120)  # Wait 2 minutes before cleaning up
    cleanup_screenshots(unique_id)

@app.post("/screenshot/")
async def screenshot_html(data: HTMLInput, background_tasks: BackgroundTasks):
    """
    Receives HTML content and generates one or more screenshots based on device type and orientation.
    Screenshots are temporary and cleaned up automatically.
    """
    unique_id = uuid.uuid4().hex
    
    # Pass device_type and orientation from the request data to take_screenshots
    urls = take_screenshots(data.html, unique_id, data.device_type, data.orientation)
    
    # Schedule the cleanup task to run in the background
    background_tasks.add_task(cleanup_screenshots_later, unique_id)
    
    # Construct full URLs for the client response
    # IMPORTANT: Replace "https://gethtmltoimg.onrender.com" with your actual deployed Render service URL
    full_urls = [f"https://gethtmltoimg.onrender.com{path}" for path in urls]
    return {"images": full_urls}