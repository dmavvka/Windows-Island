<p align="center">
  <img src="https://github.com/user-attachments/assets/ae5a1d1a-b1af-47f0-996a-c3a2912d6e7d" alt="Dynamic Island" width="120"/>
</p>
<h1 align="center">Dynamic Island for Windows</h1>

<p align="center">
  <b>Elegant Apple-style Dynamic Island media widget for Windows</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/platform-Windows-blue?style=flat-square"/>
  <img src="https://img.shields.io/badge/python-3.10+-green?style=flat-square"/>
  <img src="https://img.shields.io/badge/license-MIT-orange?style=flat-square"/>
</p>

<p align="center">
  <img src="https://github.com/user-attachments/assets/d58daf92-3702-42b4-9f20-fcb7833f89ed" alt="Demo" width="600"/>
</p>

---

<h2 align="center">✨ Features</h2>

<table align="center" width="100%">
<tr>
<td align="center" width="25%" valign="top">
<h3>🎵 Media Control</h3>
• Windows Media API integration<br/>
• Play/Pause, Next, Previous<br/>
• Seekable progress bar<br/>
• Album art display<br/>
• Click to open source app<br/>
• Compact progress indicator
</td>
<td align="center" width="25%" valign="top">
<h3>🎨 Animations</h3>
• Flip animation on track change<br/>
• 5 text animation styles<br/>
• Smooth scrolling for long titles<br/>
• Bounce effect on expand<br/>
• Smooth corner radius transitions<br/>
• Startup slide-in animation
</td>
<td align="center" width="25%" valign="top">
<h3>🎛️ Equalizer</h3>
• Real-time audio visualization<br/>
• Up to 12 frequency bands<br/>
• Adaptive colors from album art<br/>
• Sensitivity up to 400%<br/>
• Pause animation effect<br/>
• System audio capture
</td>
<td align="center" width="25%" valign="top">
<h3>⚙️ Customization</h3>
• Idle and media width<br/>
• Corner radius (compact/expanded)<br/>
• Auto-start with Windows<br/>
• Multi-monitor support<br/>
• Double-click actions<br/>
• Auto-hide when no media
</td>
</tr>
</table>

<p align="center">
  <sub>...and many more options in settings!</sub>
</p>

---

## 📥 Installation

### Pre-built Binaries

Download the latest release from [Releases](../../releases):

| Build | Size | Description |
|-------|------|-------------|
| `DynamicIsland-PyInstaller.exe` | ~25 MB | Standard build |
| `DynamicIsland-Nuitka.exe` | ~15 MB | Optimized, faster startup |

### From Source

```bash
# Clone the repository
git clone https://github.com/username/dynamic-island-windows.git
cd dynamic-island-windows

# Install dependencies
pip install -r requirements.txt

# Run
python dynamic_island.py
```

---

## 🔧 Building

### PyInstaller
```bash
pip install pyinstaller
pyinstaller --onefile --noconsole --add-data "Play.png;." --add-data "Pause.png;." --add-data "Previous.png;." --add-data "Next.png;." --icon=icon.ico --name "WindowsIsland" dynamic_island.py
```

### Nuitka (recommended)
```bash
pip install nuitka
nuitka --standalone --onefile --windows-console-mode=disable --include-data-files=Play.png=Play.png --include-data-files=Pause.png=Pause.png --include-data-files=Previous.png=Previous.png --include-data-files=Next.png=Next.png --windows-icon-from-ico=icon.ico --output-filename=WindowsIsland.exe dynamic_island.py
```

---

## 📋 Dependencies

```
PyQt5
numpy
winsdk
pyaudiowpatch
```

---

## ⚙️ Settings

Right-click tray icon → **Settings**

| Section | Options |
|---------|---------|
| **Appearance** | Size, corner radius, position |
| **Animations** | Text style, speed, bounce |
| **Equalizer** | Bar count, sensitivity, colors |
| **Behavior** | Auto-start, double-click action |

---

## 🌐 Languages

- English
- Russian

---

## 📄 License

MIT License — use, modify, and distribute freely, even commercially.

---

<p align="center">
  <sub>Made with ❤️ for Windows users who miss Dynamic Island</sub>
</p>
