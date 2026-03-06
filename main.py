import os
import re
import time
import queue
import socket
import base64
import threading
import traceback
import subprocess
import binascii
import logging
import uuid
from datetime import timedelta
from types import SimpleNamespace

import tzlocal
from EAS2Text_NG import (
    _build_fips_context as eas_build_fips_context,
    _lookup_same as eas_lookup_same,
    _process_das_fips_string as eas_process_das_fips_string,
    _resolve_output_timezone as eas_resolve_output_timezone,
    _to_output_timezone as eas_to_output_timezone,
    parse_header as parse_eas_header,
)
from dotenv import load_dotenv
from Xlib import X, display
from Xlib.protocol import event
from Xlib.xobject.drawable import Window
import pygame
import control_panel

logger = logging.getLogger(__name__)
if not logger.handlers:
    _stream_handler = logging.StreamHandler()
    _stream_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(_stream_handler)
logger.setLevel(logging.INFO)
logger.propagate = False

load_dotenv()  # Load environment variables from .env file

name = tzlocal.get_localzone_name()
TIME_ZONE = name

def pulse_env_for(uid=1000):
    xdg = f"/run/user/{uid}"
    env = os.environ.copy()
    env["XDG_RUNTIME_DIR"] = xdg
    env["PULSE_SERVER"] = f"unix:{xdg}/pulse/native"
    return env

if os.name == "posix":
    os.environ["DISPLAY"] = ":0"
    os.environ["XAUTHORITY"] = "/home/pi/.Xauthority"
    # os.environ["SDL_AUDIODRIVER"] = "pulseaudio"
    # Use wmctrl to find the window ID of an existing window (wf-piconsole in our case)
    wfpi_window_id_output = subprocess.check_output(["wmctrl", "-lG"]).decode("utf-8")
    wfpi_window_id = None
    for line in wfpi_window_id_output.splitlines():
        if "weatherflow-piconsole" in line:
            wfpi_window_id = line.split()[0]
            break

    if wfpi_window_id:
        # Set the window to hidden
        subprocess.run(["wmctrl", "-i", "-r", wfpi_window_id, "-b", "add,hidden"])

    else:
        print("Could not find the weatherflow-piconsole window to hide it.")

    screen_width = 1280
    screen_height = 720

    d = display.Display(":0")
    motif_wm_hints_atom = d.intern_atom('_MOTIF_WM_HINTS')
    motif_hints_data = [2, 0, 0, 0, 0]
    root = d.screen().root
    screen = d.screen()
    window = root.create_window(0, 0, screen_width, screen_height, 0,
        screen.root_depth,
        X.InputOutput,
        background_pixel=screen.white_pixel,
        event_mask=X.ExposureMask | X.StructureNotifyMask
    )
    window.change_property(
        motif_wm_hints_atom,
        motif_wm_hints_atom,  # Type of property
        32,  # Format (bits per element)
        motif_hints_data
    )
    window.set_wm_name("DASDEC")
    window.set_wm_class("DASDEC", "DASDEC")
    window.map()
    d.sync()
    d.flush()

    pygame_window_id = window.id
    os.environ["SDL_WINDOWID"] = str(pygame_window_id)
    pygame.init()
    pygame.display.set_caption("DASDEC")
    screen = pygame.display.set_mode((screen_width, screen_height), pygame.FULLSCREEN)

    pygame.display.iconify()

    subprocess.run(["wmctrl", "-i", "-r", str(pygame_window_id), "-b", "remove,hidden"])
    subprocess.run(["wmctrl", "-i", "-r", str(wfpi_window_id), "-b", "remove,hidden"])
    subprocess.run(["wmctrl", "-i", "-r", str(wfpi_window_id), "-b", "add,above"])
else:
    screen = pygame.display.set_mode((screen_width, screen_height))

pygame.mouse.set_visible(False)

# Constants for commands (avoiding enums)
SWITCH_STYLE = "SWITCH_STYLE"
SWITCH_PAGE = "SWITCH_PAGE"
QUIT = "QUIT"

# --- style Definitions  ---
class Style:
    def __init__(self, background, text, border, margin, font):
        self.background = background
        self.text = text
        self.border = border
        self.margin = margin
        self.font = font

style1 = Style((46, 50, 81), (255, 255, 255), (108, 29, 35), (0, 0, 0), "luximb.ttf")  # Original
style2 = Style((0, 0, 0), (255, 255, 255), (0, 0, 0), (0, 0, 0), "luximb.ttf")        # All Black/White
style3 = Style((0, 1, 228), (255, 255, 255), (0, 1, 228), (0, 0, 0), "arialbd.ttf") # Black Background, Blue Box/Border

styles = [style1, style2, style3]  # List of styles
current_style_index = 0          # Start with the first style

def set_style(style):
    global background_color, text_color, border_color, margin_color, font
    background_color = style.background
    text_color = style.text
    border_color = style.border
    margin_color = style.margin
    try:
        font = pygame.font.Font(style.font, font_size)
    except FileNotFoundError:
        print(f"Font '{style.font}' not found. Using default font.")
        font = pygame.font.Font(None, font_size)

# --- End style Definitions ---

# Margin widths
margin_width_vertical = 40  # Top and bottom margin
margin_width_horizontal = 120  # Left and right margin

# Border width
border_width = 5

# Font
font_size = 40
try:
    font = pygame.font.Font("luximb.ttf", font_size)
except FileNotFoundError:
    print("Font 'luximb.ttf' not found. Using default font.")
    font = pygame.font.Font(None, font_size)

# Default page
defaultPages = [
    [
        "Emergency Alert Details",
        "", "", "", "", "", "", "", "", "", "", "", "1/1"
    ]
]

# Text content for each page
#test example
alertPages = [
    [
        "THE PRIMARY ENTRY POINT EAS SYSTEM",
        "has issued A NATIONAL PERIODIC TEST",
        "for the following counties or",
        "areas:",
        "United States;",
        "District of Columbia, DC;",
        "at 1:20 PM",
        "on AUG 7, 2019",
        "Effective until 1:50 PM.",
        "Message from WBAP 1.",
        "",
        "",
        "1/3",
    ],
    [
        "This is page 2 of the EAS test.",
        "This test is designed to ensure the",
        "Emergency Alert System is functioning",
        "correctly.",
        "",
        "Remember, this is only a test.",
        "",
        "More information can be found at",
        "www.fcc.gov/eas",
        "",
        "",
        "",
        "2/3",
    ],
    [
        "This is page 3 of the EAS test.",
        "In a real emergency, follow the",
        "instructions provided by local",
        "authorities.",
        "",
        "Stay safe and be prepared.",
        "",
        "Thank you for your attention.",
        "",
        "",
        "",
        "",
        "3/3",
    ],
]

pages = defaultPages # starts with the Alert pages, press 'd' to switch to default

num_pages = len(pages)
current_page = 0
page_display_duration = 5  # Seconds to display each page

last_page_switch_time = time.time()  # Track when the page was last switched

audio_finished = False

info_visible = False
info_display_time = 0
info_lines = []

def render_text(lines):
    """Renders the given lines of text to surfaces and rects."""
    text_positions = []
    line_spacing = 5
    start_y = 50

    for i, line in enumerate(lines):
        text_surface = font.render(line, True, text_color)
        text_rect = text_surface.get_rect(centerx=screen_width // 2, y=start_y + i * (font_size + line_spacing))
        text_positions.append((text_surface, text_rect))
    return text_positions

def audio_finished_callback():
    """Callback function executed when the audio finishes playing."""
    global audio_finished
    audio_finished = True
    print("Audio finished playing. Back to default page.")

audio_playback_lock = threading.Lock()
audio_playback_active = False
pending_alert_queue = queue.Queue()

def _safe_upload_id(upload_id):
    safe_value = re.sub(r"[^A-Za-z0-9_.-]", "_", str(upload_id or "unknown"))
    return safe_value or "unknown"

def play_audio(file_path, cleanup_files=None):
    global audio_playback_active
    try:
        # Block until playback completes so alert visibility is not reset early.
        process = subprocess.Popen(["paplay", file_path], env=pulse_env_for(1000))
        process.wait()
    except Exception:
        print("Error playing audio:", traceback.format_exc())
    finally:
        clear_alert()
        if cleanup_files:
            for cleanup_file in cleanup_files:
                try:
                    if cleanup_file and os.path.exists(cleanup_file):
                        os.remove(cleanup_file)
                except Exception:
                    pass
        with audio_playback_lock:
            audio_playback_active = False

def _start_audio_playback(file_path, cleanup_files=None):
    global audio_playback_active
    with audio_playback_lock:
        if audio_playback_active:
            return False
        audio_playback_active = True
    thread = threading.Thread(target=play_audio, args=(file_path, cleanup_files), daemon=True)
    thread.start()
    return True

def _decode_raw_audio(raw_audio):
    if not raw_audio:
        return None, None

    mime_type = "audio/wav"
    encoded_audio = raw_audio.strip()

    if encoded_audio.startswith("data:"):
        header, encoded_audio = encoded_audio.split(",", 1)
        mime_part = header[5:].split(";", 1)[0].strip()
        if mime_part:
            mime_type = mime_part

    try:
        audio_data = base64.b64decode(encoded_audio, validate=True)
    except binascii.Error:
        # Keep compatibility with non-strict base64 payloads.
        audio_data = base64.b64decode(encoded_audio)

    return mime_type, audio_data

def _audio_extension_for_mime(mime_type):
    normalized = (mime_type or "").lower()
    if normalized in ("audio/wav", "audio/x-wav", "audio/wave"):
        return "wav"
    if normalized in ("audio/mpeg", "audio/mp3"):
        return "mp3"
    if normalized == "audio/ogg":
        return "ogg"
    if normalized == "audio/flac":
        return "flac"
    if normalized == "audio/aac":
        return "aac"
    if normalized in ("audio/mp4", "audio/m4a"):
        return "m4a"
    return "bin"

def _prepare_playable_audio_file(audio_file, playable_file):
    ffmpeg_command = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-i",
        audio_file,
        "-ac",
        "2",
        "-ar",
        "44100",
        "-f",
        "wav",
        playable_file,
    ]
    try:
        subprocess.check_output(ffmpeg_command, stderr=subprocess.STDOUT)
        return playable_file
    except Exception:
        return audio_file

def _display_alert(alert_data):
    global pages, num_pages, current_page, last_page_switch_time, TIME_ZONE
    if os.name == "posix":
        # Ensure the weather window is hidden and pygame is visible/focused.
        if wfpi_window_id:
            subprocess.run(["wmctrl", "-i", "-r", str(wfpi_window_id), "-b", "remove,above"])
            subprocess.run(["wmctrl", "-i", "-r", str(wfpi_window_id), "-b", "add,hidden"])
        subprocess.run(["wmctrl", "-i", "-r", str(pygame_window_id), "-b", "remove,hidden"])
        subprocess.run(["wmctrl", "-i", "-a", str(pygame_window_id)])
    time.sleep(3)
    print("GUI: Displaying Alert")
    try:
        parsed = parse_eas_header(alert_data["headers"])
        output_tz = eas_resolve_output_timezone(TIME_ZONE)
        start_time_utc = parsed.start_time
        end_time_utc = start_time_utc + timedelta(
            hours=parsed.duration.hours,
            minutes=parsed.duration.minutes,
        )

        org_text = eas_lookup_same("ORGS", parsed.originator) or parsed.originator
        if parsed.originator == "EAS":
            org_text = "A broadcast or cable system"
        elif parsed.originator == "CIV":
            org_text = "A civil authority"
        elif parsed.originator == "PEP":
            org_text = "THE PRIMARY ENTRY POINT EAS SYSTEM"

        event_text = eas_lookup_same("EVENTS", parsed.event_code) or parsed.event_code
        fips_context = eas_build_fips_context(parsed.locations, False)
        das_fips, _ = eas_process_das_fips_string(fips_context.str_fips, combine_same_state=True)

        msg = SimpleNamespace(
            orgText=org_text,
            evntText=event_text,
            FIPSText=[entry.strip() for entry in das_fips.rstrip(";").split(";") if entry.strip()],
            startTime=eas_to_output_timezone(start_time_utc, output_tz),
            endTime=eas_to_output_timezone(end_time_utc, output_tz),
            callsign=parsed.senderid.strip(),
        )
    except Exception as e:
        print("Error parsing EAS message:", e)
        return

    desc = alert_data["description"]

    orgText = msg.orgText
    orgText = orgText.replace("An EAS Participant", "A broadcast or cable system")
    orgText = re.sub(r"the national weather service in.*", "the national weather service", orgText, flags=re.IGNORECASE)

    msgFrom = ".\n"
    if "Message from" not in desc:
        msgFrom = ".\nMessage from " + msg.callsign + ".\n"

    text = (str.upper(orgText) +
            "\nhas issued " + str.upper(msg.evntText) +
            "\nfor the following counties or\nareas:\n" +
            ";\n".join(msg.FIPSText) +
            ";\nat " + msg.startTime.strftime("%I:%M %p") +
            "\non " + str.upper(msg.startTime.strftime("%b %d, %Y")) +
            "\nEffective until " +
            msg.endTime.strftime("%I:%M %p") +
            msgFrom +
            desc)
    pages = format_eas_message(text)
    print(pages)
    num_pages = len(pages)
    current_page = 0

    try:
        raw_audio = alert_data.get("raw_audio")
        upload_id = alert_data.get("upload_id") or "unknown"
        if raw_audio:
            mime_type, audio_data = _decode_raw_audio(raw_audio)
            audio_ext = _audio_extension_for_mime(mime_type)
            file_suffix = f"{_safe_upload_id(upload_id)}_{time.time_ns()}_{uuid.uuid4().hex[:8]}"
            audio_file = f"temp_alert_audio_{file_suffix}.{audio_ext}"
            playback_file = f"temp_alert_audio_playback_{file_suffix}.wav"

            with open(audio_file, "wb") as f:
                f.write(audio_data)

            playable_audio_file = _prepare_playable_audio_file(audio_file, playback_file)
            print("Playing audio from link.")
            _start_audio_playback(
                playable_audio_file,
                cleanup_files=(audio_file, playback_file),
            )
        else:
            print("No audio link or file provided.")
            threading.Timer(3.0, lambda: clear_alert()).start()
    except Exception:
        print("Error loading audio:", traceback.format_exc())

    last_page_switch_time = time.time()

def _play_next_alert_if_idle():
    with audio_playback_lock:
        if audio_playback_active:
            return
    try:
        alert_data = pending_alert_queue.get_nowait()
    except queue.Empty:
        return
    _display_alert(alert_data)

def format_eas_message(eas_text):
    MAX_LINE_LENGTH = 35
    MAX_LINES_PER_PAGE = 13

    # Ensure areas are split into separate lines
    eas_text = re.sub(r'; ', '\n', eas_text)
    lines = eas_text.split('\n')
    formatted_lines = []

    for line in lines:
        words = line.split()
        current_line = ""

        for word in words:
            if len(current_line) + len(word) + 1 <= MAX_LINE_LENGTH:
                current_line += (" " if current_line else "") + word
            else:
                formatted_lines.append(current_line)
                current_line = word

        if current_line:
            formatted_lines.append(current_line)

    # Split into pages
    pages = []
    total_pages = (len(formatted_lines) + (MAX_LINES_PER_PAGE - 1) - 1) // (MAX_LINES_PER_PAGE - 1)

    for i in range(0, len(formatted_lines), MAX_LINES_PER_PAGE - 1):
        page_content = formatted_lines[i:i + (MAX_LINES_PER_PAGE - 1)]
        while len(page_content) < (MAX_LINES_PER_PAGE - 1):
            page_content.append("")  # Fill empty lines if necessary
        page_content.append(f"{len(pages) + 1}/{total_pages}")
        pages.append(page_content)

    return pages

def get_system_info():
    """Gathers network information and returns it as a list of strings."""
    lines = []
    try:
        hostname = socket.gethostname()
        lines.append(f"Hostname: {hostname}")
        # reliable way to get the primary IP address
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.1)
            s.connect(("8.8.8.8", 80)) # Connect to a public DNS server
            ip_address = s.getsockname()[0]
        lines.append(f"IP Address: {ip_address}")
    except Exception:
        lines.append("Network Info: Could not determine IP.")

    # Get gateway on Linux systems
    if os.name == "posix":
        try:
            result = subprocess.check_output("ip route | grep default", shell=True, text=True)
            gateway = result.split(' ')[2]
            lines.append(f"Gateway: {gateway}")
        except Exception:
            lines.append("Gateway: N/A")
    return lines

def looks_like_plaintext(data):
    if callable(data):
        data = data(4096)
    elif hasattr(data, "read"):
        data = data.read(4096)

    if data is None:
        return True
    if isinstance(data, str):
        data = data.encode("utf-8", "ignore")
    elif isinstance(data, memoryview):
        data = data.tobytes()
    elif not isinstance(data, (bytes, bytearray)):
        return False

    sample = bytes(data[:4096])
    if not sample:
        return True
    if b"\x00" in sample:
        return False

    head = sample[:256].lstrip().lower()
    if (
        head.startswith(b"<!doctype html")
        or head.startswith(b"<html")
        or head.startswith(b"<?xml")
        or head.startswith(b"{")
        or head.startswith(b"[")
        or b"<body" in head
        or b"<title" in head
    ):
        return True

    printable = 0
    control = 0
    for b in sample:
        if b in (9, 10, 13) or 32 <= b <= 126:
            printable += 1
        elif b < 32:
            control += 1

    if control * 10 > len(sample) * 3:
        return False
    return printable * 10 >= len(sample) * 9

# ----  Command Queue and Handling  ----

command_queue = queue.Queue()

def handle_commands():
    global current_style_index, pages, num_pages, current_page, TIME_ZONE
    try:
        while True:
            command = command_queue.get_nowait()  # Non-blocking get

            if command[0] == SWITCH_STYLE:
                current_style_index = (command[1]) % len(styles)
                set_style(styles[current_style_index])
                print(f"GUI: Switched to style {current_style_index}")

            elif command[0] == SWITCH_PAGE:
                if command[1] == "default":
                    pages = defaultPages
                elif command[1] == "alert":
                    pages = alertPages
                num_pages = len(pages)
                current_page = 0
                print(f"GUI: Switched to page {command[1]}")

            elif command[0] == "ORIGINATE_ALERT":
                #Do not use
                pass

            elif command[0] == "DISPLAY_ALERT":
                pending_alert_queue.put(command[1])
                logger.info("Alert queued pending_alerts=%d", pending_alert_queue.qsize())

            elif command[0] == "CLEAR_ALERT":
                print("GUI: Clearing Alert")
                threading.Timer(3.0, lambda: clear_alert()).start()
            elif command[0] == QUIT:
              print("GUI: Quitting application")
              pygame.quit()
              exit()
            command_queue.task_done() # Mark as handled
    except queue.Empty:
        pass # No commands, continue
    _play_next_alert_if_idle()

def clear_alert():
    global pages, num_pages, current_page, last_page_switch_time
    pages = defaultPages
    num_pages = len(pages)
    current_page = 0
    pygame.mixer.quit()
    last_page_switch_time = time.time()
    if os.name == "posix":
        # Hide the Pygame window and show the wf-piconsole window
        subprocess.run(["wmctrl", "-i", "-r", str(pygame_window_id), "-b", "add,hidden"])
        subprocess.run(["wmctrl", "-i", "-r", str(wfpi_window_id), "-b", "remove,hidden"])

# Initialize colors based on the starting style
set_style(styles[current_style_index])

#start Control Panel in a thread.
control_panel.start_control_panel(command_queue)

# main loop
try:
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.USEREVENT + 1:  # Audio finished event
                audio_finished_callback()
            elif event.type == pygame.KEYDOWN: # Switch Style
                if event.key == pygame.K_SPACE:  # Press space to switch styles
                    current_style_index = (current_style_index + 1) % len(styles)
                    set_style(styles[current_style_index]) # Update global colors
                elif event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_i:
                    info_lines = get_system_info()
                    info_display_time = time.time()
                    info_visible = True
                elif event.key == pygame.K_o:
                    info_visible = False

        # Check if it's time to switch to the next page
        current_time = time.time()
        if current_time - last_page_switch_time >= page_display_duration:
            current_page = (current_page + 1) % num_pages  # Cycle through pages
            last_page_switch_time = current_time

        # ---- Handle commands from the GUI  ----
        handle_commands()

        # Clear the screen with margin color
        screen.fill(margin_color)

        # Calculate the inner rectangle's coordinates with different margins
        inner_rect_x = margin_width_horizontal
        inner_rect_y = margin_width_vertical
        inner_rect_width = screen_width - 2 * margin_width_horizontal
        inner_rect_height = screen_height - 2 * margin_width_vertical

        # Draw the background color inside the margin
        pygame.draw.rect(screen, background_color, (inner_rect_x, inner_rect_y, inner_rect_width, inner_rect_height))

        # Draw the border
        pygame.draw.rect(screen, border_color, (inner_rect_x, inner_rect_y, inner_rect_width, inner_rect_height), border_width)

        # Render and blit the text for the current page
        text_positions = render_text(pages[current_page])  # Get text for current page
        for text_surface, text_rect in text_positions:
            screen.blit(text_surface, text_rect)

        if info_visible:
            # Hide the overlay after 10 seconds
            if time.time() - info_display_time > 10:
                info_visible = False
            else:
                # Set up font for the info text
                info_font_size = 28
                try:
                    info_font = pygame.font.Font("luximb.ttf", info_font_size)
                except FileNotFoundError:
                    info_font = pygame.font.Font(None, info_font_size)

                # Calculate overlay size based on number of lines
                line_height = info_font_size + 5
                num_lines = len(info_lines)
                overlay_width = 600
                overlay_height = 20 + num_lines * line_height + 20  # 20px padding top/bottom

                overlay = pygame.Surface((overlay_width, overlay_height), pygame.SRCALPHA)
                overlay.fill((10, 10, 10, 210)) # Dark, semi-transparent background

                # Render each line of info text onto the overlay
                line_y = 20
                for line in info_lines:
                    text_surf = info_font.render(line, True, (255, 255, 255))
                    overlay.blit(text_surf, (20, line_y))
                    line_y += line_height

                # Position and draw the overlay in the center of the screen
                overlay_x = (screen_width - overlay_width) // 2
                overlay_y = (screen_height - overlay_height) // 2
                screen.blit(overlay, (overlay_x, overlay_y))

        # Update the display
        pygame.display.flip()

        time.sleep(0.01)
except KeyboardInterrupt:
    clear_alert()
    running = False
    print("Exiting on keyboard interrupt.")
    pygame.quit()
    os._exit(0)
finally:
    clear_alert()
    running = False
    pygame.quit()
    os._exit(0)
