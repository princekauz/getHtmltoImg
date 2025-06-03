# Use an official Python runtime as a parent image
FROM python:3.11-slim-bookworm

# 1. Install System Dependencies:
#    - gnupg, wget: For adding external repositories and fetching files.
#    - unzip: Needed to extract the downloaded chromedriver.
#    - curl: Used to retrieve the ChromeDriver version information.
#    - xvfb: X Virtual Framebuffer, a dependency often needed for headless Chrome environments, even with --headless.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gnupg \
        wget \
        unzip \
        curl \
        xvfb && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

# 2. Add Google Chrome Repository and Install Chrome:
#    - Adds the official Google Chrome stable repository key and source.
#    - Installs 'google-chrome-stable'.
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /etc/apt/keyrings/google-archive-keyring.gpg && \
    echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-archive-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        google-chrome-stable && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

# 3. Dynamically Install the Correct ChromeDriver Version:
#    This step ensures the installed ChromeDriver version precisely matches the installed Chrome version.
#    We will try to use the chrome-for-testing API which is the official source.
#    Note: This API sometimes returns the full version string like "114.0.5735.90",
#    or the short major version. Our parsing tries to be flexible.
RUN CHROME_VERSION=$(google-chrome-stable --version | cut -d ' ' -f 3) && \
    echo "Detected Chrome Version: $CHROME_VERSION" && \
    # Fetch the download URL from the JSON API for the detected Chrome version
    # This approach assumes 'downloads' and 'chromedriver' will be under 'versions' with a matching 'version' string.
    DOWNLOAD_URL=$(curl -s "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json" | \
                   grep -B 10 -A 10 "\"version\": \"$CHROME_VERSION\"" | \
                   grep -oE "\"chromedriver\":.*\"url\": \"[^\"]+\"" | \
                   grep -oE "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/[0-9\.]+/linux64/chromedriver-linux64.zip") && \
    echo "Identified ChromeDriver download URL: ${DOWNLOAD_URL}" && \
    if [ -z "$DOWNLOAD_URL" ]; then \
        echo "Error: Could not find matching ChromeDriver download URL for Chrome version ${CHROME_VERSION} from the main API. Trying a fallback..." && \
        # Fallback for Chrome versions 114 and older that might not be in the exact JSON format or specific stable builds
        CHROME_MAJOR_VERSION=$(echo "$CHROME_VERSION" | cut -d '.' -f 1) && \
        echo "Trying fallback with major version ${CHROME_MAJOR_VERSION}" && \
        DOWNLOAD_URL=$(curl -s "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_${CHROME_MAJOR_VERSION}" | \
                       xargs -I {} echo "https://chromedriver.storage.googleapis.com/{}/chromedriver_linux64.zip") && \
        echo "Fallback URL: ${DOWNLOAD_URL}" && \
        if [ -z "$DOWNLOAD_URL" ]; then \
            echo "Error: Fallback also failed to find a matching ChromeDriver download URL. Exiting." && \
            exit 1; \
        fi; \
    fi && \
    # Download, unzip, move, and cleanup ChromeDriver
    wget -q --continue --show-progress -O chromedriver.zip "$DOWNLOAD_URL" && \
    unzip chromedriver.zip && \
    mv chromedriver-linux64/chromedriver /usr/bin/chromedriver && \
    chmod +x /usr/bin/chromedriver && \
    rm -rf chromedriver.zip chromedriver-linux64/

# 4. Set Environment Variables:
#    These are used by your Python application (main.py) to locate Chrome and ChromeDriver.
ENV CHROME_BIN=/usr/bin/google-chrome
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

# 5. Set Working Directory inside the container:
WORKDIR /app

# 6. Copy and Install Python Dependencies:
#    It's efficient to copy requirements.txt separately to leverage Docker layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 7. Copy Your Application Code:
COPY . .

# 8. Create Static Files Directory:
#    Ensures the directory for screenshots exists before the app starts.
RUN mkdir -p static

# 9. Expose Port:
#    Informs Docker that the container listens on port 8000.
EXPOSE 8000

# 10. Define the Command to Run Your Application:
#     Uvicorn starts your FastAPI app. Render.com typically maps internal port 8000
#     to its public-facing port automatically.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]