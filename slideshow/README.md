![Python](https://img.shields.io/badge/Python-3.9--3.11-blue?logo=python&logoColor=white)
![Tkinter](https://img.shields.io/badge/GUI-Tkinter-informational?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

# Slideshow

A Tkinter-based image slideshow with GIF support, keyboard controls, and a lightweight on-screen HUD.

---

## Features

| Feature | Description |
|---|---|
| 🖼️ Image display | Show all images from a folder with a configurable delay |
| 🎞️ GIF animation | Native GIF playback with per-frame timing |
| 🔀 Shuffle mode | Randomize image order at startup |
| 📍 Start index | Jump to a specific image to begin the show |
| ⏱️ Auto-stop | Automatically exit after a given duration |
| ☀️ Brightness | Adjust image brightness on the fly |
| 📺 HUD | On-screen overlay showing current file and progress |

---

## Installation

**With uv (recommended):**

```bash
uv tool install "slideshow @ git+https://github.com/obeone/scripts#subdirectory=slideshow"
```

**With pipx:**

```bash
pipx install "slideshow @ git+https://github.com/obeone/scripts#subdirectory=slideshow"
```

> Tkinter must be available in your Python installation (`python3-tk` on Debian/Ubuntu).

---

## Usage

```bash
slideshow /path/to/images
```

```bash
slideshow --help
```

---

## License

MIT — [obeone](https://github.com/obeone)
