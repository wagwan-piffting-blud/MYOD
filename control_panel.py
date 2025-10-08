# control_panel.py
from flask import Flask, render_template, request
import threading
import queue

app = Flask(__name__)

app.debug = False
app.use_reloader = False

# Constants for commands (avoiding enums)
SWITCH_STYLE = "SWITCH_STYLE"
SWITCH_PAGE = "SWITCH_PAGE"
QUIT = "QUIT"

# This queue will be shared with the Pygame application.
command_queue = None  # Will be set by the main Pygame application

@app.route("/")
def index():
    return render_template("dashboard.html", active_page="dashboard")

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

@app.route("/shutdown", methods=["POST"])
def shutdown():
    command_queue.put(("SHUTDOWN",))
    return "OK"

@app.route("/send", methods=["POST"])
def send():
    # Something has sent us the header
    headers = request.form["eas_header"]
    description = request.form["description"]
    try:
        audio_link = request.form["audio_link"]
    except KeyError as e:
        audio_link = None
    try:
        local_audio_file = request.form["local_audio_file"]
    except KeyError as e:
        local_audio_file = None

    command_queue.put(("DISPLAY_ALERT", {"headers": headers, "description": description, "audio_link": audio_link, "local_audio_file": local_audio_file}))
    return "OK"

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
