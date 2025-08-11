import os
import sys
import secrets
import tempfile
import subprocess
import re
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, request, render_template_string, jsonify, send_file, redirect, url_for, flash
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from flask_talisman import Talisman
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS
from functools import wraps
from dotenv import load_dotenv
import json

# --- ENV GENERATOR ---
def generate_env():
    secret_key = secrets.token_urlsafe(32)
    api_token = secrets.token_hex(20)
    with open(".env", "w") as f:
        f.write(f"FLASK_SECRET_KEY={secret_key}\n")
        f.write(f"FLASK_API_TOKEN={api_token}\n")
        f.write(f"FLASK_DEBUG=False\n")
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
DEBUG_MODE = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'

if not SECRET_KEY or not API_TOKEN:
    raise RuntimeError("FLASK_SECRET_KEY and FLASK_API_TOKEN must be set (use --genenv to create .env)")

# --- FLASK APP CONFIGURATION ---
app = Flask(__name__)
app.secret_key = SECRET_KEY

# Enhanced app configuration
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE='Lax',
    MAX_CONTENT_LENGTH=1024 * 1024,  # 1MB limit
    DEBUG=DEBUG_MODE
)

# --- LOGGING CONFIGURATION ---
if not app.debug:
    if not os.path.exists('logs'):
        os.mkdir('logs')
    file_handler = RotatingFileHandler('logs/app.log', maxBytes=10240, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('Flask application startup')

# --- SECURITY CONFIGURATION ---
def configure_security_headers(app):
    """Configure security headers for Flask-Talisman 1.0.0 compatibility"""
    
    # Enhanced CSP configuration - different for development vs production
    if app.debug:
        # Development CSP - allows inline styles and scripts for easier development
        csp = {
            'default-src': ["'self'"],
            'script-src': ["'self'", 'https://cdn.jsdelivr.net', "'unsafe-inline'"],
            'style-src': ["'self'", 'https://cdn.jsdelivr.net', "'unsafe-inline'"],
            'img-src': ["'self'", 'data:'],
            'font-src': ["'self'", 'https://cdn.jsdelivr.net'],
            'connect-src': ["'self'"],
            'frame-ancestors': ["'none'"],
            'base-uri': ["'self'"],
            'form-action': ["'self'"]
        }
    else:
        # Production CSP - strict security policy
        csp = {
            'default-src': ["'self'"],
            'script-src': ["'self'", 'https://cdn.jsdelivr.net'],
            'style-src': ["'self'", 'https://cdn.jsdelivr.net'],
            'img-src': ["'self'", 'data:'],
            'font-src': ["'self'", 'https://cdn.jsdelivr.net'],
            'connect-src': ["'self'"],
            'frame-ancestors': ["'none'"],
            'base-uri': ["'self'"],
            'form-action': ["'self'"]
        }
    
    # Initialize Talisman with enhanced configuration
    Talisman(app,
        content_security_policy=csp,
        force_https=not app.debug,  # Only force HTTPS in production
        strict_transport_security=not app.debug,  # Only enable HSTS in production
        strict_transport_security_max_age=31536000 if not app.debug else 0,
        strict_transport_security_include_subdomains=not app.debug,
        frame_options='DENY',
        x_content_type_options=True,
        referrer_policy='strict-origin-when-cross-origin'
    )
    
    # Manual headers for Flask-Talisman 1.0.0 compatibility
    @app.after_request
    def add_security_headers(response):
        # Disable deprecated X-XSS-Protection (version 1.0.0 compatibility)
        response.headers['X-XSS-Protection'] = '0'
        
        # Add Permissions-Policy for privacy (version 1.0.0 compatibility)
        response.headers['Permissions-Policy'] = 'browsing-topics=()'
        
        # Additional security headers
        response.headers['X-Download-Options'] = 'noopen'
        response.headers['X-Permitted-Cross-Domain-Policies'] = 'none'
        
        return response

# Apply security configuration
configure_security_headers(app)

# Enable CORS for all routes
CORS(app)

# Enhanced rate limiting configuration
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["1000/day", "100/hour"],
    storage_uri="memory://"  # Use Redis in production
)

# --- INPUT VALIDATION ---
def validate_input_text(text: str) -> bool:
    """Validate input text for security"""
    # Size limit (1MB)
    if len(text.encode('utf-8')) > 1024 * 1024:
        return False
    
    # Content validation - only allow printable characters and common whitespace
    if not re.match(r'^[\x20-\x7E\s]*$', text):
        return False
    
    return True

def validate_api_input(data):
    """Validate API input data"""
    if not isinstance(data, dict):
        raise ValueError("Invalid data format")
    
    input_text = data.get("input_text", "")
    if not isinstance(input_text, str):
        raise ValueError("input_text must be a string")
    
    if len(input_text.strip()) == 0:
        raise ValueError("input_text cannot be empty")
    
    if len(input_text.encode('utf-8')) > 1024 * 1024:  # 1MB
        raise ValueError("input_text too large")
    
    return True

# --- FILE UPLOAD VALIDATION ---
ALLOWED_EXTENSIONS = {'.ep'}
MAX_FILE_SIZE = 1024 * 1024  # 1MB

def validate_file_upload(file):
    """Enhanced file validation"""
    if not file or not file.filename:
        return False, "No file provided"
    
    # Check file extension
    filename = secure_filename(file.filename)
    if not any(filename.endswith(ext) for ext in ALLOWED_EXTENSIONS):
        return False, "Invalid file type"
    
    # Check file size
    file.seek(0, 2)  # Seek to end
    size = file.tell()
    file.seek(0)  # Reset
    
    if size > MAX_FILE_SIZE:
        return False, "File too large"
    
    # Basic content validation
    try:
        content = file.read().decode('utf-8')
        file.seek(0)  # Reset
        
        # Validate content is text
        if not content.isprintable() and not all(c in '\n\r\t' for c in content if not c.isprintable()):
            return False, "Invalid file content"
            
    except UnicodeDecodeError:
        return False, "File must be valid UTF-8 text"
    
    return True, "Valid file"

# --- SECURE SUBPROCESS EXECUTION ---
def get_formatter_version():
    """Get formatter version safely"""
    try:
        if not os.path.exists(MOJO_FMT_PATH):
            app.logger.warning(f"Formatter script not found at {MOJO_FMT_PATH}")
            return "Unknown"
            
        result = subprocess.run(
            ["python3", MOJO_FMT_PATH, "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10  # Add timeout
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            app.logger.warning(f"Could not get formatter version: {result.stderr}")
            return "Unknown"
    except subprocess.TimeoutExpired:
        app.logger.warning("Formatter version check timed out")
        return "Unknown"
    except Exception as e:
        app.logger.warning(f"Could not get formatter version: {e}")
        return "Unknown"

def run_mojofmt(input_text: str) -> str:
    """Secure mojofmt execution with comprehensive validation"""
    # Validate input first
    if not validate_input_text(input_text):
        raise ValueError("Invalid input text")
    
    app.logger.debug("Running mojofmt")
    with tempfile.TemporaryDirectory() as tmpdir:
        in_path = os.path.join(tmpdir, "input.txt")
        out_path = os.path.join(tmpdir, "output.txt")
        
        # Secure file writing
        try:
            with open(in_path, 'w', encoding='utf-8') as f:
                f.write(input_text)
        except Exception as e:
            app.logger.error(f"Failed to write input file: {e}")
            raise RuntimeError("Failed to write input file")
        
        # Validate formatter script exists
        if not os.path.exists(MOJO_FMT_PATH):
            app.logger.error(f"Formatter script not found at {MOJO_FMT_PATH}")
            raise RuntimeError("Formatter script not found")
        
        # Secure subprocess execution with timeout
        try:
            result = subprocess.run(
                ['python3', MOJO_FMT_PATH, '-o', out_path, in_path],
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True,
                timeout=30,  # Add timeout
                cwd=tmpdir   # Set working directory
            )
        except subprocess.TimeoutExpired:
            app.logger.error("Formatting operation timed out")
            raise RuntimeError("Formatting operation timed out")
        except Exception as e:
            app.logger.error(f"Subprocess execution failed: {e}")
            raise RuntimeError("Formatting failed")
        
        if result.returncode != 0:
            # Don't expose internal error details
            app.logger.error(f"mojofmt failed with return code {result.returncode}: {result.stderr}")
            raise RuntimeError("Formatting failed")
        
        try:
            with open(out_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            app.logger.error(f"Failed to read output file: {e}")
            raise RuntimeError("Failed to read output file")

FORMATTER_VERSION = get_formatter_version()

# --- AUTHENTICATION ---
def require_api_token(f):
    """API token authentication decorator (unchanged)"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer ') or auth[len('Bearer '):] != API_TOKEN:
            app.logger.warning(f"Unauthorized API access attempt from {request.remote_addr}")
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

# --- ERROR HANDLERS ---
@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(e):
    app.logger.warning(f"File too large from {request.remote_addr}")
    return jsonify({"error": "File too large"}), 413

@app.errorhandler(400)
def handle_bad_request(e):
    app.logger.warning(f"Bad request from {request.remote_addr}: {e}")
    return jsonify({"error": "Bad request"}), 400

@app.errorhandler(404)
def handle_not_found(e):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(429)
def handle_rate_limit(e):
    app.logger.warning(f"Rate limit exceeded from {request.remote_addr}")
    return jsonify({"error": "Rate limit exceeded"}), 429

@app.errorhandler(500)
def handle_internal_error(e):
    app.logger.error(f"Internal server error: {e}")
    return jsonify({"error": "Internal server error"}), 500

@app.errorhandler(Exception)
def handle_exception(e):
    """Global exception handler"""
    app.logger.error(f"Unhandled exception: {e}", exc_info=True)
    return jsonify({"error": "Internal server error"}), 500

# --- HTML TEMPLATE (unchanged) ---
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
                  border-radius:7px; color:#432d67; resize:vertical; transition:height .2s; margin-left:auto;margin-right:auto;}
        select {padding:6px 10px; border-radius:5px; border:1px solid #b993d6;
                background:#eee0f6; color:#6d378d; font-size:15px;}
        #output_block {background:#16151a !important; color:white !important; border-radius:8px; padding:1em;
                       margin-top:10px; overflow-y:auto; resize:vertical; white-space:pre-wrap;
                       border:2px solid #bdb0da; flex:1 1 auto; min-height:0;}
        @media (max-width:800px) {.container {flex-direction:column; height:auto;}
                                  .panel {height:auto; min-width:0;}}
.output-header {
  margin-top: 8px;
  display: flex;
  justify-content: space-between; /* Push left and right sections apart */
  align-items: center;           /* Vertically align */
}

.syntax-select {
  display: flex;
  align-items: center;
  gap: 6px; /* Space between label and dropdown */
}

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
<div class="output-header">
  <label>Formatted Output:</label>
  <div class="syntax-select">
    <label for="syntaxmode">Output Syntax:</label>
    <select id="syntaxmode" name="syntaxmode">
      <option value="none">Plain Text</option>
      <option value="perl">Perl</option>
      <option value="html">HTML</option>
    </select>
  </div>
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

# --- ROUTES ---
@app.route("/", methods=["GET", "POST"])
def index():
    """Main page route with enhanced security"""
    # Handle both GET and POST requests
    # POST requests are redirected to use AJAX instead
    if request.method == "POST":
        # If someone tries to submit the form traditionally, redirect to GET
        app.logger.info(f"Traditional form submission redirected from {request.remote_addr}")
        return redirect(url_for('index'))
    
    # Serve the HTML template
    return render_template_string(
        HTML_TEMPLATE,
        formatter_version=FORMATTER_VERSION
    )

@app.route("/api/format_ajax", methods=["POST"])
@limiter.limit("5/minute")  # Stricter rate limiting
def api_format_ajax():
    """AJAX endpoint for formatting text with enhanced security"""
    if not request.is_json:
        app.logger.warning(f"Non-JSON request to format_ajax from {request.remote_addr}")
        return jsonify({"error": "JSON body required"}), 400
    
    try:
        data = request.get_json()
        validate_api_input(data)  # Enhanced input validation
        
        input_text = data.get("input_text", "")
        remove_empty = bool(data.get("remove_empty", False))
        
        app.logger.info(f"Processing format request from {request.remote_addr}, size: {len(input_text)} chars")
        
        formatted_text = run_mojofmt(input_text)
        if remove_empty:
            formatted_text = "\n".join(
                line for line in formatted_text.splitlines() if line.strip()
            )
        
        app.logger.info(f"Successfully formatted text for {request.remote_addr}")
        return jsonify({"formatted_text": formatted_text})
        
    except ValueError as e:
        app.logger.warning(f"Validation error from {request.remote_addr}: {e}")
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        app.logger.error(f"Runtime error from {request.remote_addr}: {e}")
        return jsonify({"error": "Processing failed"}), 500
    except Exception as e:
        app.logger.error(f"Unexpected error from {request.remote_addr}: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/api/format", methods=["POST"])
@limiter.limit("5/minute")  # Stricter rate limiting
@require_api_token
def api_format():
    """Original API endpoint with token authentication and enhanced security"""
    if not request.is_json:
        app.logger.warning(f"Non-JSON request to format API from {request.remote_addr}")
        return jsonify({"error": "JSON body required"}), 400
    
    try:
        data = request.get_json()
        
        # Validate input using the same validation as AJAX endpoint
        input_data = {
            "input_text": data.get("text", ""),
            "remove_empty": data.get("remove_empty", False)
        }
        validate_api_input(input_data)
        
        text = input_data["input_text"]
        remove_empty = bool(input_data["remove_empty"])
        
        app.logger.info(f"Processing authenticated API request from {request.remote_addr}, size: {len(text)} chars")
        
        formatted = run_mojofmt(text)
        if remove_empty:
            formatted = "\n".join([line for line in formatted.splitlines() if line.strip()])
        
        app.logger.info(f"Successfully processed authenticated API request from {request.remote_addr}")
        return jsonify({"formatted_text": formatted})
        
    except ValueError as e:
        app.logger.warning(f"API validation error from {request.remote_addr}: {e}")
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        app.logger.error(f"API runtime error from {request.remote_addr}: {e}")
        return jsonify({"error": "Processing failed"}), 500
    except Exception as e:
        app.logger.error(f"API unexpected error from {request.remote_addr}: {e}")
        return jsonify({"error": "Internal server error"}), 500

# --- HEALTH CHECK ENDPOINT ---
@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "version": FORMATTER_VERSION,
        "debug": app.debug
    })

if __name__ == "__main__":
    app.logger.info(f"Starting Flask application in {'debug' if app.debug else 'production'} mode")
    app.run(host="0.0.0.0", port=8000, debug=app.debug)