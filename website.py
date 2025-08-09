import os
import tempfile
import subprocess
from flask import (
    Flask, request, render_template_string,
    jsonify, send_file, redirect, url_for, flash
)
from werkzeug.utils import secure_filename
from flask_talisman import Talisman
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from functools import wraps
from dotenv import load_dotenv

# Load environment variables from .env (for local dev only)
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MOJO_FMT_PATH = os.path.join(BASE_DIR, "mojofmt.py")

# Get secrets from environment variables
SECRET_KEY = os.environ.get('FLASK_SECRET_KEY')
API_TOKEN = os.environ.get('FLASK_API_TOKEN')
if not SECRET_KEY or not API_TOKEN:
    raise RuntimeError("FLASK_SECRET_KEY and FLASK_API_TOKEN must be set")

app = Flask(__name__)
app.secret_key = SECRET_KEY

# Secure cookies
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,  # requires HTTPS in production
    SESSION_COOKIE_SAMESITE='Lax'
)

# Security headers with Flask‑Talisman (CSP allowing only self + cdn.jsdelivr.net)
csp = {
    'default-src': ["'self'"],
    'script-src': ["'self'", 'https://cdn.jsdelivr.net'],
    'style-src': ["'self'", 'https://cdn.jsdelivr.net', "'unsafe-inline'"],
}
Talisman(app, content_security_policy=csp)

# Rate limiting
limiter = Limiter(key_func=get_remote_address, app=app, default_limits=["100/hour"])

# Token authentication decorator
def require_api_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer ') or auth[len('Bearer '):] != API_TOKEN:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

# ----------------------------- HTML TEMPLATE -----------------------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Mojolicious Template Code Formatter</title>
    <style>
        body { font-family: 'Segoe UI', Arial, sans-serif; margin:0; padding:0;
               background:linear-gradient(90deg, #fdeff9 0%, #ecb6ff 100%);
               height:100vh; display:flex; flex-direction:column; }
        header { background:#8247c2; color:#fff; display:flex; align-items:center;
                 justify-content:space-between; padding:1em; }
        header h1 { margin:0; font-size:1.6em; }
        .icon-links { display:flex; align-items:center; }
        .icon-links a { display:inline-flex; align-items:center; margin-left:16px; color:white; text-decoration:none; }
        .icon-links a svg { width:28px; height:28px; fill:white; }
        .flash-messages ul { margin:0; padding:0; list-style:none; color:#d91454; text-align:center; }
        form { flex:1; display:flex; flex-direction:column; margin:0; }
        .container { display:flex; flex-direction:row; gap:16px; padding:20px; flex:1;
                     box-sizing:border-box; height:calc(100vh - 140px); }
        .panel { background:#fff; border-radius:10px; box-shadow:0 8px 18px -7px #ac83ce44;
                 padding:22px; flex:1 1 50%; min-width:300px; display:flex; flex-direction:column; height:100%; }
        label { font-weight:bold; margin-bottom:5px; }
        .controls { display:flex; gap:8px; margin:14px 0 8px 0; }
        button { background:#a950e6; border:none; color:#fff; border-radius:5px;
                 padding:9px 16px; font-size:15px; cursor:pointer; box-shadow:0 2px 7px -3px #bb76c1; }
        button:hover { background:#7634a2; }
        input[type="file"] { margin-bottom:10px; }
        textarea { width:100%; flex:1 1 auto; min-height:0; font-family:'Fira Mono', monospace;
                   font-size:15px; border:2px solid #bdb0da; background:#f6eafe;
                   border-radius:7px; padding:8px; color:#432d67; resize:vertical; }
        select { padding:6px 10px; border-radius:5px; border:1px solid #b993d6;
                 background:#eee0f6; color:#6d378d; font-size:15px; }
        #output_block, #output_code, pre[class*="language-"], code[class*="language-"] {
            font-family:'Fira Mono', monospace !important; font-size:15px !important; line-height:1 !important;
        }
        #output_block { background:#16151a !important; color:white !important; border-radius:8px; padding:1em;
                        margin-top:10px; overflow-y:auto; resize:vertical; white-space:pre-wrap;
                        border:2px solid #bdb0da; flex:1 1 auto; min-height:0; }
        @media (max-width:800px) {
            .container { flex-direction:column; height:auto; }
            .panel { height:auto; min-width:0; }
        }
    </style>
    <link href="https://cdn.jsdelivr.net/npm/prismjs@1/themes/prism-tomorrow.min.css" rel="stylesheet" />
    <script src="https://cdn.jsdelivr.net/npm/prismjs@1/prism.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/prismjs@1/components/prism-perl.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/prismjs@1/components/prism-markup.min.js"></script>
</head>
<body>
    <header>
        <h1>Mojolicious Template Code Formatter</h1>
        <div class="icon-links">
            <a href="https://github.com/brianread108" target="_blank" aria-label="GitHub">
                <svg viewBox="0 0 16 16"><path fill-rule="evenodd"
                d="M8 0C3.58 0 0 3.58 0 8a8..."/></svg>
            </a>
            <a href="https://mojolicious.org" target="_blank" aria-label="Mojolicious">
                <svg viewBox="0 0 64 64"><path d="M32 2C20 18..."/></svg>
            </a>
        </div>
    </header>
    <div class="flash-messages">
    {% with messages = get_flashed_messages() %}
      {% if messages %}<ul>{% for m in messages %}<li>{{ m }}</li>{% endfor %}</ul>{% endif %}
    {% endwith %}
    </div>
    <form method="post" action="/" enctype="multipart/form-data">
      <div class="container">
        <div class="panel">
          <label for="input_text">Input data:</label>
          <textarea name="input_text" id="input_text">{{ input_text|default('') }}</textarea>
          <label for="input_file">Upload a file:</label>
          <input type="file" name="input_file" id="input_file" accept=".txt,.mojo,.pl,.html,.tmpl,.tt,.tt2,.template,text/plain">
          <div class="controls">
              <button type="submit" name="action" value="format">Format</button>
              <button type="submit" name="action" value="download">Download</button>
              <button type="button" onclick="clearFields()">Clear</button>
          </div>
        </div>
        <div class="panel">
            <label>Formatted Output:</label>
            <div style="margin-top:8px;">
                <label for="syntaxmode">Output Syntax:</label>
                <select id="syntaxmode" onchange="highlightOutput()">
                    <option value="none">Plain Text</option>
                    <option value="perl">Perl</option>
                    <option value="html">HTML</option>
                </select>
            </div>
            <pre id="output_block"><code id="output_code" class="language-none">{% if formatted_text is defined %}{{ formatted_text|e }}{% endif %}</code></pre>
        </div>
      </div>
    </form>
    <script>
    document.addEventListener("DOMContentLoaded", function() {
        const inputTextEl = document.getElementById("input_text");
        const inputFileEl = document.getElementById("input_file");
        const outputCodeEl = document.getElementById("output_code");

        function clearOutput() {
            outputCodeEl.textContent = '';
            Prism.highlightElement(outputCodeEl);
        }
        function clearFields() {
            inputTextEl.value = '';
            clearOutput();
        }
        window.clearFields = clearFields;

        inputTextEl.addEventListener("input", clearOutput);
        inputFileEl.addEventListener("change", e => {
            const file = e.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = ev => {
                inputTextEl.value = ev.target.result;
                clearOutput();
            };
            reader.readAsText(file);
        });

        highlightOutput();
    });

    function highlightOutput() {
        const mode = document.getElementById("syntaxmode").value;
        const code = document.getElementById("output_code");
        code.className = "";
        if (mode === "perl") code.classList.add("language-perl");
        else if (mode === "html") code.classList.add("language-markup");
        else code.classList.add("language-none");
        Prism.highlightElement(code);
    }
    </script>
</body>
</html>
"""

# ----------------------------- Core logic -----------------------------
def run_mojofmt(input_text: str) -> str:
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
    input_text, formatted_text = "", None
    if request.method == "POST":
        action = request.form.get("action")
        f_obj = request.files.get("input_file")
        input_text = request.form.get("input_text", "")
        if f_obj and f_obj.filename:
            try:
                input_text = f_obj.read().decode('utf-8')
            except Exception as e:
                flash(f"Error reading uploaded file: {e}")
                return render_template_string(HTML_TEMPLATE, input_text=input_text)

        if action in ("format", "download"):
            if not input_text.strip():
                flash("No input data provided.")
                return render_template_string(HTML_TEMPLATE, input_text=input_text)
            try:
                formatted_text = run_mojofmt(input_text)
            except RuntimeError as e:
                flash(str(e))
                return render_template_string(HTML_TEMPLATE, input_text=input_text)
            if action == "download":
                tmpfile = tempfile.NamedTemporaryFile(delete=False, mode='w', encoding='utf-8', suffix='.txt')
                tmpfile.write(formatted_text)
                tmpfile.close()
                return redirect(url_for('download_file', filename=os.path.basename(tmpfile.name)))
    return render_template_string(HTML_TEMPLATE, input_text=input_text, formatted_text=formatted_text)

@app.route("/download/<filename>")
def download_file(filename):
    safe_name = secure_filename(filename)
    path = os.path.join(tempfile.gettempdir(), safe_name)
    if not os.path.exists(path):
        return "File not found", 404
    resp = send_file(path, as_attachment=True, download_name="formatted_output.txt")
    try:
        os.unlink(path)
    except Exception:
        pass
    return resp

@app.route("/api/format", methods=["POST"])
@limiter.limit("10/minute")
@require_api_token
def api_format():
    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 400
    data = request.get_json()
    text = data.get("text", "")
    if not text:
        return jsonify({"error": "Missing 'text'"}), 400
    try:
        formatted = run_mojofmt(text)
        return jsonify({"formatted_text": formatted})
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)  # debug=False in prod