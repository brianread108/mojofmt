import os
import sys
import secrets
import tempfile
import subprocess
from flask import Flask, request, render_template_string, jsonify, send_file, redirect, url_for, flash
from werkzeug.utils import secure_filename
from flask_talisman import Talisman
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS
from functools import wraps
from dotenv import load_dotenv
from flask import send_file
import json

# --- ENV GENERATOR ---
def generate_env():
    secret_key = secrets.token_urlsafe(32)
    api_token = secrets.token_hex(20)
    with open(".env", "w") as f:
        f.write(f"FLASK_SECRET_KEY={secret_key}\n")
        f.write(f"FLASK_API_TOKEN={api_token}\n")
    print("✅ .env generated")
    print(f"FLASK_SECRET_KEY={secret_key}")
    print(f"FLASK_API_TOKEN={api_token}")
    print("⚠ Keep .env out of version control!")
    sys.exit(0)

if "--genenv" in sys.argv:
    generate_env()

# --- LOAD ENV ---
load_dotenv()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MOJO_FMT_PATH = os.path.join(BASE_DIR, "mojofmt.py")

SECRET_KEY = os.environ.get('FLASK_SECRET_KEY')
API_TOKEN = os.environ.get('FLASK_API_TOKEN')
if not SECRET_KEY or not API_TOKEN:
    raise RuntimeError("FLASK_SECRET_KEY and FLASK_API_TOKEN must be set (use --genenv to create .env)")

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE='Lax'
)

# Enable CORS for all routes
CORS(app)

# CSP — only self and cdn.jsdelivr.net for scripts/styles
csp = {
    'default-src': ["'self'"],
    'script-src': ["'self'", 'https://cdn.jsdelivr.net', "'unsafe-inline'"],
    'style-src': ["'self'", 'https://cdn.jsdelivr.net', "'unsafe-inline'"],
}
Talisman(app, content_security_policy=csp)

limiter = Limiter(key_func=get_remote_address, app=app, default_limits=["100/hour"])

def get_formatter_version():
    try:
        result = subprocess.run(
            ["python3", MOJO_FMT_PATH, "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            return "Unknown"
    except Exception as e:
        app.logger.warning(f"Could not get formatter version: {e}")
        return "Unknown"

FORMATTER_VERSION = get_formatter_version()

def require_api_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer ') or auth[len('Bearer '):] != API_TOKEN:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Mojolicious Template Code Formatter</title>
    <style>
        body {font-family:'Segoe UI', Arial, sans-serif; margin:0; padding:0;
              background:linear-gradient(90deg,#fdeff9 0%,#ecb6ff 100%);
              height:100vh; display:flex; flex-direction:column;}
        header {background:#8247c2; color:#fff; display:flex; align-items:center;
                justify-content:space-between; padding:1em;}
        header h1 {margin:0; font-size:1.6em;}
        .icon-links {display:flex; align-items:center;}
        .icon-links a {display:inline-flex; align-items:center; margin-left:16px; color:white;}
        .icon-links a svg {width:28px; height:28px; fill:white;}
        .flash-messages ul {margin:0; padding:0; list-style:none; color:#d91454;text-align:center;}
        .flash-messages {min-height:20px;}
        form {flex:1; display:flex; flex-direction:column;}
        .container {display:flex; flex-direction:row; gap:16px; padding:20px; flex:1;
                    box-sizing:border-box; height:calc(100vh - 140px);}
        .panel {background:#fff; border-radius:10px; box-shadow:0 8px 18px -7px #ac83ce44;
                padding:22px; flex:1 1 50%; min-width:300px; display:flex; flex-direction:column; height:100%;}
        label {font-weight:bold; margin-bottom:5px;}
		.controls {
			display: flex;
			justify-content: space-between;  /* left group stays left, right goes right */
			align-items: center;
			margin: 14px 0 8px 0;
		}

		.controls-left, 
		.controls-right {
			display: flex;
			gap: 8px;
		}
		.version-label {
			font-size: 0.8em;         /* smaller than title */
			font-weight: normal;      /* keep normal weight */
			margin-left: 8px;         /* space between title and version */
			opacity: 0.8;             /* slightly subdued */
		}
		
		.file-upload {
			display: flex;
			align-items: center;    /* perfect vertical centering */
			gap: 0.9rem;            /* nice spacing, tweak as needed */
			margin-top: 18px;       /* whitespace above this row */
			margin-bottom: 10px;    /* space below */
		}

		.file-upload label {
			margin: 0;
			font-weight: bold;
			white-space: nowrap;
			line-height: 1.5;
			/* align baseline to button - fixes Chrome/Firefox difference */
			display: flex;
			align-items: center;
		}

		.file-upload input[type="file"] {
			margin: 0;
			padding: 3px 0;
			font-size: 1em;
			/* Remove outline/extra vertical space browsers add */
			vertical-align: middle;
		}


        button {background:#a950e6; border:none; color:#fff; border-radius:5px;
                padding:9px 16px; font-size:15px; cursor:pointer; box-shadow:0 2px 7px -3px #bb76c1;}
        button:hover {background:#7634a2;}
        button:disabled {background:#ccc; cursor:not-allowed;}
        input[type="file"] {margin-bottom:10px;}
        textarea {width:100%; flex:1 1 auto; min-height:30px; max-height:60vh; font-family:'Fira Mono', monospace;
                  font-size:15px; border:2px solid #bdb0da; background:#f6eafe;
                  border-radius:7px; padding:8px; color:#432d67; resize:vertical; transition:height .2s;}
        select {padding:6px 10px; border-radius:5px; border:1px solid #b993d6;
                background:#eee0f6; color:#6d378d; font-size:15px;}
        #output_block {background:#16151a !important; color:white !important; border-radius:8px; padding:1em;
                       margin-top:10px; overflow-y:auto; resize:vertical; white-space:pre-wrap;
                       border:2px solid #bdb0da; flex:1 1 auto; min-height:0;}
        @media (max-width:800px) {.container {flex-direction:column; height:auto;}
                                  .panel {height:auto; min-width:0;}}
    </style>
    <link href="https://cdn.jsdelivr.net/npm/prismjs@1/themes/prism-tomorrow.min.css"
          rel="stylesheet"
          integrity="sha384-wFjoQjtV1y5jVHbt0p35Ui8aV8GVpEZkyF99OXWqP/eNJDU93D3Ugxkoyh6Y2I4A"
          crossorigin="anonymous" />
    <script src="https://cdn.jsdelivr.net/npm/prismjs@1/prism.min.js"
            integrity="sha384-guvyurEPUUeAKyomgXWf/3v1dYx+etnMZ0CeHWsUXSqT1sRwh4iLpr9Z+Lw631fX"
            crossorigin="anonymous"></script>
    <script src="https://cdn.jsdelivr.net/npm/prismjs@1/components/prism-markup.min.js"
            integrity="sha384-HkMr0bZB9kBW4iVtXn6nd35kO/L/dQtkkUBkL9swzTEDMdIe5ExJChVDSnC79aNA"
            crossorigin="anonymous"></script>
    <script src="https://cdn.jsdelivr.net/npm/prismjs@1/components/prism-perl.min.js"
            integrity="sha384-TBezSCOvSMb3onoz0oj0Yi0trDW0ZQIz7CaneDU5q4gsUSqaPKMD6DlepFFJj+qa"
            crossorigin="anonymous"></script>
</head>
<body>
    <header>
		 <h1>
			Mojolicious Template Code Formatter
			<span class="version-label">v{{ formatter_version }}</span>
		</h1>
		<div class="icon-links">
			<a href="https://github.com/brianread108" target="_blank" aria-label="GitHub">
			  <svg viewBox="0 0 16 16" role="img" aria-hidden="true" width="28" height="28" fill="white" xmlns="http://www.w3.org/2000/svg">
				<path fill-rule="evenodd"
				  d="M8 0C3.58 0 0 3.58 0 8a8.003 8.003 0 0 0 5.47 7.59c.4.07.55-.17.55-.38
					0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94
					-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53
					.63-.01 1.08.58 1.23.82.72 1.21 
					1.87.87 2.33.66.07-.52.28-.87.51-1.07
					-1.78-.2-3.64-.89-3.64-3.95 
					0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 
					0 0 .67-.21 2.2.82a7.5 7.5 0 0 1 
					4.01 0c1.53-1.04 2.2-.82 2.2-.82
					.44 1.1.16 1.92.08 2.12.51.56.82 
					1.27.82 2.15 0 3.07-1.87 3.75-3.65 
					3.95.29.25.54.73.54 1.48 
					0 1.07-.01 1.93-.01 2.2 
					0 .21.15.46.55.38A8.003 8.003 0 0 0 
					16 8c0-4.42-3.58-8-8-8z"/>
			  </svg>
			</a>
			<a href="https://mojolicious.org" target="_blank" aria-label="Mojolicious Website">
			  <svg viewBox="0 0 64 64" width="28" height="28" role="img" aria-hidden="false" fill="white" xmlns="http://www.w3.org/2000/svg">
				<path d="M32 2C20 18 20 30 20 40a12 12 0 0 0 24 0c0-14-12-24-12-38zM32 56a16 16 0 0 1-16-16c0-12 16-20 16-38 8 16 16 24 16 38a16 16 0 0 1-16 16z"/>
			  </svg>
			</a>
		</div>
    </header>
    <div class="flash-messages" id="flash-messages">
    </div>
    <form id="mainform" onsubmit="return false;">
      <div class="container">
        <div class="panel">
          <label for="input_text">Input data:</label>
          <textarea name="input_text" id="input_text"></textarea>
			<div class="file-upload">
				<label for="input_file">Upload a file:</label>
				<input type="file" name="input_file" id="input_file" accept=".ep">
			</div>
			<div class="controls">
				<div class="controls-left">
					<button type="button" id="format_btn">Format</button>
				</div>
				<div class="controls-right">
					<button type="button" id="download_btn">Download</button>
					<button type="button" id="clear_btn">Clear</button>
				</div>
			</div>
          <label style="margin-top:12px;">
            <input type="checkbox" name="remove_empty" id="remove_empty">
            Remove empty lines from output
          </label>
        </div>
        <div class="panel">
            <label>Formatted Output:</label>
            <div style="margin-top:8px;">
                <label for="syntaxmode">Output Syntax:</label>
                <select id="syntaxmode" name="syntaxmode">
                    <option value="none">Plain Text</option>
                    <option value="perl">Perl</option>
                    <option value="html">HTML</option>
                </select>
            </div>
            <pre id="output_block"><code id="output_code" class="language-none"></code></pre>
        </div>
      </div>
    </form>
    <script>
    document.addEventListener("DOMContentLoaded", function() {
        const inputTextEl = document.getElementById("input_text");
        const inputFileEl = document.getElementById("input_file");
        const outputCodeEl = document.getElementById("output_code");
        const clearBtnEl = document.getElementById("clear_btn");
        const formatBtn = document.getElementById("format_btn");
        const downloadBtn = document.getElementById("download_btn");
        const syntaxModeEl = document.getElementById("syntaxmode");
        const removeEmptyEl = document.getElementById("remove_empty");
        const flashMessagesEl = document.getElementById("flash-messages");
        const mainForm = document.getElementById("mainform");
        
        let currentFormattedText = '';
        let uploadedFilename = '';

        // Prevent form submission completely
        mainForm.addEventListener("submit", function(e) {
            e.preventDefault();
            return false;
        });

        // Flash message functions
        function showFlashMessage(message, isError = true) {
            flashMessagesEl.innerHTML = `<ul><li style="color: ${isError ? '#d91454' : '#28a745'}">${message}</li></ul>`;
            setTimeout(() => {
                flashMessagesEl.innerHTML = '';
            }, 5000);
        }

        // Update file input display
        function updateFileInputDisplay() {
            const fileInput = inputFileEl;
            const label = fileInput.parentElement;
            const displaySpan = label.querySelector('.filename-display') || document.createElement('span');
            displaySpan.className = 'filename-display';
            displaySpan.style.marginLeft = '10px';
            displaySpan.style.fontWeight = 'normal';
            displaySpan.style.color = '#666';
            
            if (uploadedFilename) {
                displaySpan.textContent = `(${uploadedFilename})`;
            } else {
                displaySpan.textContent = '(none)';
            }
            
            if (!label.querySelector('.filename-display')) {
                label.appendChild(displaySpan);
            }
        }

        // Initialize filename display
        updateFileInputDisplay();

        // Resize textarea
        function autoResizeTextarea() {
            inputTextEl.style.height = "auto";
            let max = Math.max(60, Math.round(window.innerHeight*0.6));
            inputTextEl.style.height = Math.min(inputTextEl.scrollHeight, max) + "px";
        }
        
        inputTextEl.addEventListener("input", function() {
            clearOutput();
            autoResizeTextarea();
        });

        clearBtnEl.addEventListener("click", function() {
            inputTextEl.value = '';
            inputFileEl.value = '';
            uploadedFilename = '';
            updateFileInputDisplay();
            autoResizeTextarea();
            clearOutput();
        });

        inputFileEl.addEventListener("change", function(event) {
            const file = event.target.files[0];
            if (!file) {
                uploadedFilename = '';
                updateFileInputDisplay();
                return;
            }
            
            uploadedFilename = file.name;
            updateFileInputDisplay();
            
            const reader = new FileReader();
            reader.onload = function(e) {
                inputTextEl.value = e.target.result;
                autoResizeTextarea();
                clearOutput();
            };
            reader.readAsText(file);
        });

        syntaxModeEl.addEventListener("change", highlightOutput);

        function clearOutput() {
            outputCodeEl.textContent = '';
            currentFormattedText = '';
            Prism.highlightElement(outputCodeEl);
        }
        
        function highlightOutput() {
            outputCodeEl.className = "";
            if (syntaxModeEl.value === "perl") outputCodeEl.classList.add("language-perl");
            else if (syntaxModeEl.value === "html") outputCodeEl.classList.add("language-markup");
            else outputCodeEl.classList.add("language-none");
            Prism.highlightElement(outputCodeEl);
        }

        // Generate download filename
        function getDownloadFilename() {
            if (uploadedFilename) {
                const lastDotIndex = uploadedFilename.lastIndexOf('.');
                if (lastDotIndex > 0) {
                    const name = uploadedFilename.substring(0, lastDotIndex);
                    const ext = uploadedFilename.substring(lastDotIndex);
                    return `${name}_fmt${ext}`;
                } else {
                    return `${uploadedFilename}_fmt.txt`;
                }
            } else {
                return 'formatted_fmt.txt';
            }
        }

        // Format button AJAX handler
        formatBtn.addEventListener("click", function() {
            const inputText = inputTextEl.value.trim();
            if (!inputText) {
                showFlashMessage("No input data provided.");
                return;
            }

            // Show formatting state
            const originalText = formatBtn.textContent;
            formatBtn.textContent = "Formatting...";
            formatBtn.disabled = true;

            // Prepare data
            const formData = {
                input_text: inputText,
                remove_empty: removeEmptyEl.checked
            };

            // Make AJAX request
            fetch('/api/format_ajax', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(formData)
            })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    showFlashMessage(data.error);
                } else {
                    currentFormattedText = data.formatted_text;
                    outputCodeEl.textContent = currentFormattedText;
                    highlightOutput();
                }
            })
            .catch(error => {
                showFlashMessage("Error formatting text: " + error.message);
            })
            .finally(() => {
                formatBtn.textContent = originalText;
                formatBtn.disabled = false;
            });
        });

        // Download button AJAX handler
        downloadBtn.addEventListener("click", function() {
            if (!currentFormattedText) {
                showFlashMessage("No formatted text to download. Please format first.");
                return;
            }

            // Create and trigger download with proper filename
            const blob = new Blob([currentFormattedText], { type: 'text/plain' });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = getDownloadFilename();
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
        });

        highlightOutput();
    });
    </script>
</body>
</html>
"""

def run_mojofmt(input_text: str) -> str:
    app.logger.debug("Running mojofmt")
    with tempfile.TemporaryDirectory() as tmpdir:
        in_path = os.path.join(tmpdir, "input.txt")
        out_path = os.path.join(tmpdir, "output.txt")
        with open(in_path, 'w', encoding='utf-8') as f:
            f.write(input_text)
        result = subprocess.run(
            ['python3', MOJO_FMT_PATH, '-o', out_path, in_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"mojofmt failed:\n{result.stderr.strip()}")
        with open(out_path, 'r', encoding='utf-8') as f:
            return f.read()


@app.route("/", methods=["GET", "POST"])
def index():
    # Handle both GET and POST requests
    # POST requests are redirected to use AJAX instead
    if request.method == "POST":
        # If someone tries to submit the form traditionally, redirect to GET
        return redirect(url_for('index'))
    
    # Serve the HTML template
    return render_template_string(
        HTML_TEMPLATE,
        formatter_version=FORMATTER_VERSION
    )


@app.route("/api/format_ajax", methods=["POST"])
@limiter.limit("10/minute")
def api_format_ajax():
    """AJAX endpoint for formatting text"""
    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 400
    
    data = request.get_json()
    input_text = data.get("input_text", "")
    remove_empty = bool(data.get("remove_empty", False))
    
    if not input_text.strip():
        return jsonify({"error": "No input data provided."}), 400
    
    try:
        formatted_text = run_mojofmt(input_text)
        if remove_empty:
            formatted_text = "\n".join(
                line for line in formatted_text.splitlines() if line.strip()
            )
        return jsonify({"formatted_text": formatted_text})
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/format", methods=["POST"])
@limiter.limit("10/minute")
@require_api_token
def api_format():
    """Original API endpoint with token authentication"""
    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 400
    data = request.get_json()
    text = data.get("text", "")
    remove_empty = bool(data.get("remove_empty"))
    if not text:
        return jsonify({"error": "Missing 'text'"}), 400
    try:
        formatted = run_mojofmt(text)
        if remove_empty:
            formatted = "\n".join([line for line in formatted.splitlines() if line.strip()])
        return jsonify({"formatted_text": formatted})
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)