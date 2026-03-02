# control_panel.py
from flask import Flask, render_template, request, jsonify
import flask
#import soundcard as sc
import threading
import queue
import tempfile
import os
import time
from werkzeug.exceptions import RequestEntityTooLarge

app = Flask(__name__)
MAX_DIRECT_REQUEST_BYTES = 4 * 1024 * 1024
MAX_SINGLE_CHUNK_B64_BYTES = 1 * 1024 * 1024
MAX_CHUNKED_AUDIO_B64_BYTES = 64 * 1024 * 1024
UPLOAD_TTL_SECONDS = 15 * 60
app.config["MAX_CONTENT_LENGTH"] = MAX_DIRECT_REQUEST_BYTES

@app.context_processor
def example():
    audio_status = '✓' if 1==1 else '✕'
    network_status = '✓' if flask.request.remote_addr else '✕'
    return dict(system_status='✓', audio_status=audio_status, network_status=network_status)

app.debug = False
app.use_reloader = False

# Constants for commands (avoiding enums)
SWITCH_STYLE = "SWITCH_STYLE"
SWITCH_PAGE = "SWITCH_PAGE"
QUIT = "QUIT"

# This queue will be shared with the Pygame application.
command_queue = None  # Will be set by the main Pygame application
chunk_uploads = {}
chunk_uploads_lock = threading.Lock()

def _as_bool(value):
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on", "last", "final"}

def _request_value(name, header_name=None):
    value = request.form.get(name)
    if value is not None:
        return value
    value = request.args.get(name)
    if value is not None:
        return value
    if header_name:
        return request.headers.get(header_name)
    return None

def _cleanup_stale_uploads(now=None):
    now = now or time.time()
    stale_paths = []
    with chunk_uploads_lock:
        for upload_id, state in list(chunk_uploads.items()):
            if now - state["updated_at"] > UPLOAD_TTL_SECONDS:
                stale_paths.append(state["path"])
                del chunk_uploads[upload_id]
    for stale_path in stale_paths:
        try:
            os.remove(stale_path)
        except OSError:
            pass

def _handle_chunked_send():
    _cleanup_stale_uploads()
    upload_id = _request_value("upload_id", "X-Upload-Id")
    if not upload_id:
        return jsonify({"error": "Missing upload_id"}), 400

    chunk = _request_value("raw_audio_chunk")
    if chunk is None:
        chunk = request.get_data(cache=False, as_text=True) or ""

    if len(chunk) > MAX_SINGLE_CHUNK_B64_BYTES:
        return jsonify({
            "error": "Chunk too large",
            "max_chunk_bytes": MAX_SINGLE_CHUNK_B64_BYTES,
        }), 413

    header = _request_value("eas_header")
    description = _request_value("description") or ""
    mime_type = _request_value("audio_mime_type", "X-Audio-Mime-Type") or "audio/wav"
    finalize = _as_bool(_request_value("is_last_chunk", "X-Last-Chunk")) or _as_bool(_request_value("finalize"))

    with chunk_uploads_lock:
        state = chunk_uploads.get(upload_id)
        if state is None:
            if not header:
                return jsonify({"error": "Missing eas_header for new chunked upload"}), 400
            fd, path = tempfile.mkstemp(prefix="myod_audio_chunk_", suffix=".b64")
            os.close(fd)
            state = {
                "path": path,
                "headers": header,
                "description": description,
                "mime_type": mime_type,
                "size": 0,
                "updated_at": time.time(),
            }
            chunk_uploads[upload_id] = state
        else:
            if header:
                state["headers"] = header
            if _request_value("description") is not None:
                state["description"] = description
            if _request_value("audio_mime_type", "X-Audio-Mime-Type") is not None:
                state["mime_type"] = mime_type

        state["updated_at"] = time.time()
        state["size"] += len(chunk)
        if state["size"] > MAX_CHUNKED_AUDIO_B64_BYTES:
            overflow_path = state["path"]
            del chunk_uploads[upload_id]
            try:
                os.remove(overflow_path)
            except OSError:
                pass
            return jsonify({
                "error": "Chunked upload exceeded max supported size",
                "max_audio_b64_bytes": MAX_CHUNKED_AUDIO_B64_BYTES,
            }), 413
        target_path = state["path"]

    if chunk:
        try:
            with open(target_path, "ab") as audio_buffer:
                audio_buffer.write(chunk.encode("ascii"))
        except UnicodeEncodeError:
            return jsonify({"error": "raw_audio_chunk must be ASCII/base64"}), 400

    if not finalize:
        return jsonify({"status": "chunk_received", "upload_id": upload_id}), 202

    with chunk_uploads_lock:
        state = chunk_uploads.pop(upload_id, None)
    if state is None:
        return jsonify({"error": "Unknown upload_id"}), 404

    try:
        with open(state["path"], "rb") as audio_buffer:
            encoded_audio = audio_buffer.read().decode("ascii")
    except UnicodeDecodeError:
        try:
            os.remove(state["path"])
        except OSError:
            pass
        return jsonify({"error": "Uploaded audio chunks were not valid ASCII/base64"}), 400

    try:
        os.remove(state["path"])
    except OSError:
        pass

    raw_audio = encoded_audio
    if raw_audio and not raw_audio.startswith("data:"):
        raw_audio = f"data:{state['mime_type']};base64,{raw_audio}"

    command_queue.put(("DISPLAY_ALERT", {
        "headers": state["headers"],
        "description": state["description"],
        "raw_audio": raw_audio or None,
    }))
    return "OK"

@app.errorhandler(RequestEntityTooLarge)
def handle_request_entity_too_large(_error):
    return jsonify({
        "error": "Request body too large for direct /send uploads",
        "max_direct_bytes": MAX_DIRECT_REQUEST_BYTES,
        "hint": "Use chunked upload via /send_chunk or /send with upload_id/raw_audio_chunk/is_last_chunk",
    }), 202

@app.route("/")
def index():
    return render_template("dashboard.html", active_page="dashboard")

@app.route("/status")
def status():
    return example()

@app.route("/originate")
def originate():
    return render_template("originate.html", active_page="originate")

@app.route("/send_alert")
def send_alert():
    return render_template("send_alert.html", active_page="send_alert")

@app.route("/switch_style", methods=["POST"])
def switch_style():
    style_index = int(request.form["style_index"])  # Get style from Form Input
    command_queue.put((SWITCH_STYLE, style_index)) # Put Command
    return "OK"

@app.route("/switch_page", methods=["POST"])
def switch_page():
    page = request.form["page"]
    command_queue.put((SWITCH_PAGE, page))
    return "OK"

@app.route("/originate-alert", methods=["POST"])
def originate_alert():
    command_queue.put(("ORIGINATE_ALERT", {
        "type": request.form["alert_type"],
        "areas": request.form.getlist("selected_areas"),
        "message": request.form["alert_message"],
        "duration": request.form["alert_duration"],
    }))
    return "OK"

@app.route("/quit", methods=["POST"])
def quit_app():
    command_queue.put((QUIT,))
    return "OK"

@app.route("/send", methods=["POST"])
def send():
    if _request_value("upload_id", "X-Upload-Id") is not None and (
        _request_value("raw_audio_chunk") is not None
        or _as_bool(_request_value("is_last_chunk", "X-Last-Chunk"))
        or _as_bool(_request_value("finalize"))
    ):
        return _handle_chunked_send()

    # Something has sent us the header
    headers = request.form["eas_header"]
    description = request.form["description"]
    try:
        raw_audio = request.form["raw_audio"]
    except KeyError as e:
        raw_audio = None

    command_queue.put(("DISPLAY_ALERT", {"headers": headers, "description": description, "raw_audio": raw_audio}))
    return "OK"

@app.route("/send_chunk", methods=["POST"])
def send_chunk():
    return _handle_chunked_send()

@app.route("/clear", methods=["POST"])
def clear_alert():
    command_queue.put(("CLEAR_ALERT",))
    return "OK"

def run_flask():
    app.run(debug=False, host="0.0.0.0", port=5000, use_reloader=False)  # VERY IMPORTANT: Turn off reloader

def start_control_panel(queue):
    """Starts the Flask control panel in a separate thread.
    Takes the command queue as an argument.
    """
    global command_queue
    command_queue = queue # Set the global command queue
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    print("Flask control panel running at http://localhost:5000")
