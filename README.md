# Make Your Own DASDEC (MYOD) - Fork that works with WeatherFlow-PiConsole
What you need:

- A Raspberry Pi (any model should theoretically work, but a Raspberry Pi 3 or newer is recommended for better performance) running [WeatherFlow-PiConsole](https://github.com/peted-davis/WeatherFlow_PiConsole).
- A monitor with audio output (HDMI or 3.5mm jack), so you can hear the alert audio.

## Installation
1. Install Raspberry Pi OS and WeatherFlow-PiConsole (linked above). Make sure your WeatherFlow device is set up and working correctly, and that the dashboard shows up on the display out you have on the Pi.

2. Login and clone this repository:
    ```bash
    git clone https://github.com/wagwan-piffting-blud/MYOD/
    cd MYOD
    ```
3. Update and upgrade your system packages (not strictly necessary, but recommended):
    ```bash
    sudo apt-get update && sudo apt-get upgrade
    ```
4. Create a virtual environment (required due to PEP 668):
    ```bash
    python3 -m venv myod-env
    source myod-env/bin/activate
    ```
5. Install the required Python packages:
    ```bash
    pip install -r requirements.txt
    ```
6. Run main.py to start the application:
    ```bash
    python main.py
    ```
7. Upon running, the app should minimize WFPC, launch the DASDEC window, and then quickly restore WFPC. You should see the DASDEC interface on your monitor only when receiving an alert. If this does not happen, make sure the monitor is display :0 in your Raspberry Pi display settings. As well, the default username this fork uses is `pi` - if you changed the default username, you will need to change it in `main.py` on line 19.

## API
The MYOD API is mostly unfinished upstream, but you can use the following endpoints:
- `POST /send`: Send an alert to the DASDEC. The body should be x-www-form-urlencoded with the following fields:
    - `eas_header`: The EAS header (e.g. "ZCZC-WXR-RWT-123456+0100-1234567-SENDER-")
    - `description`: An optional description included after the alert text (e.g. "This is a test alert.")
    - `audio_deeplink`: The URL of the audio file to play. This should be a direct link to an audio file (e.g. "https://example.com/alert.mp3"). NOTE: This was mostly built for authenticated endpoints like the one my other (currently private) repo, ASMARA-Rust-Native uses, so you may need to modify the code to work with unauthenticated endpoints. It's just a cURL command, so you can easily modify it to your needs.
- `POST /clear`: Clear the current alert and stop any playing audio.
- `POST /switch_style`: Switch the DASDEC style. The body should be x-www-form-urlencoded with the following field:
    - `style_index`: The style to switch to (0-2). 0 is the default style, 1 is the all black/white style, and 2 is the black/blue style.
- `POST /switch_page`: Switch the DASDEC page. The body should be x-www-form-urlencoded with the following field:
    - `page`: The page to switch to (0-n). 0 is the main page, 1 is the next page, etc. for however many pages you have in the alert.
- `POST /quit`: Quit the application.

## Control Panel
You can access the control panel by navigating to `http://<IP_ADDRESS>:5000` in your web browser. The control panel is mostly unfinished as of right now. Additional features will be merged as they become available upstream.

## Troubleshooting
- Audio is set to go to custom audio device "alsa_output.platform-fef00700.hdmi.hdmi-stereo" by default using `paplay`. If you need to change this, modify main.py on line 355. You can find your audio device by running `pactl list short sinks` in the terminal. If you don't have PulseAudio installed, you can install it with `sudo apt-get install pulseaudio`.

- If you encounter issues with dependency conflicts, make sure you are using the virtual environment created in step 4. Activate it with `source myod-env/bin/activate` before running the application.

- If the DASDEC window does not appear, make sure your monitor is set to display :0 in your Raspberry Pi display settings. You can check this by running `echo $DISPLAY` in the terminal. If it is not :0, you can either change the display settings in the Raspberry Pi configuration tool (`sudo raspi-config`), or you can change the display main.py uses on line 18.

## Sample systemd service file
You can create a systemd service file to run MYOD on startup. Create a file named `myod.service` in `/etc/systemd/system/` with the following content (make sure to modify the paths and user as necessary):

```ini
[Unit]
Description=DASDEC
After=network.target

[Service]
Type=simple
ExecStart=/home/pi/dasdec/venv/bin/python3 /home/pi/dasdec/main.py
WorkingDirectory=/home/pi/dasdec
Restart=on-failure
RestartSec=5s
User=pi

[Install]
WantedBy=multi-user.target
```

Then enable and start the service with the following commands:

```bash
sudo systemctl daemon-reload
sudo systemctl enable /etc/systemd/system/myod.service
sudo systemctl start /etc/systemd/system/myod.service
```

## License
This project is licensed under the GNU General Public License v3.0 License like the parent repo this fork is under - see the [LICENSE](LICENSE) file for details.

## Credits
- [peted-davis - WeatherFlow-PiConsole](https://github.com/peted-davis/WeatherFlow-PiConsole)
- [playsamay4 - Upstream MYOD repo this fork is based on](https://github.com/playsamay4/MYOD)
