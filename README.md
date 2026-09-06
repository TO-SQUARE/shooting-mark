# Shooting Mark

A lightweight Windows utility for displaying a customizable crosshair over your screen or a selected window.
Follow the development of the program, as source code for Linux systems may be released in the near future.

Created by **TOSQUARE0**.

## Features

- Choose from the crosshair designs included in the `data` folder.
- Adjust the crosshair size and opacity.
- Position the overlay on a selected display.
- Attach the overlay to a specific open window and follow its position and size.
- Use the global `Ctrl+Shift+C` shortcut to show or hide the crosshair.
- Click through the overlay without capturing mouse input.
- Open the built-in About dialog for project information.

## Requirements

- Windows
- Python 3.10 or newer
- PySide6 6.7 or newer, installed from `requirements.txt`

## Installation and Usage

1. Clone or download this repository.
2. Open a PowerShell window in the project directory.
3. Create and activate a virtual environment:

	```powershell
	python -m venv .venv
	.\.venv\Scripts\Activate.ps1
	```

4. Install the dependency:

	```powershell
	python -m pip install -r requirements.txt
	```

5. Start the application:

	```powershell
	python main.py
	```


## Using the Overlay

1. Select a design from **Design library**.
2. Adjust **Size** and **Opacity** under **Appearance**.
3. Select a display, or choose **Attach to a window** under **Overlay location**.
4. Click **Show crosshair** to toggle the overlay.
5. Press `Ctrl+Shift+C` at any time to toggle visibility.

To add a custom design, place an `.svg` file in the `data` folder and restart the application. The file is loaded automatically.

## Building a Windows Executable

Install PyInstaller:

```powershell
python -m pip install pyinstaller
```

Then build the executable:

```powershell
python -m PyInstaller --onefile --noconsole --windowed --name "SHOOTING MARK" --icon "shooting-mark.png" --add-data "data;data" --add-data "shooting-mark.png;." main.py
```

The executable will be created in the `dist` folder.

## Privacy

Shooting Mark does not contain an account system or an online data service. It uses Windows APIs locally to list visible windows and track the selected window's position and size. This information is used only to position the overlay and is not uploaded by the application.

Installing dependencies with `pip` requires an internet connection unless the packages are already available locally.

## Limitations

Some games or applications may block overlays, especially when using exclusive fullscreen mode or anti-cheat software. Use the overlay only where permitted by the relevant application or game's terms of service. Borderless or windowed mode may provide better compatibility.

## Disclaimer

The creator of Shooting Mark is not responsible for any misuse of the program, violations of applicable laws, or breaches of an application or game's terms of service. The user is solely responsible for how the program is used.

