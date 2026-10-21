# Setting up Rot2Gold

This guide takes you from nothing to your first notes, on macOS, Windows or Linux. It takes about 15 minutes, most of it waiting for downloads.

You will install, in this order:

1. **Obsidian**, the notes app, and a vault (a folder of notes).
2. **Git and uv:** uv installs Rot2Gold and the Python it runs on; it needs Git to download it.
3. **Rot2Gold itself.**
4. **An AI option** that writes the notes: Claude Code, Codex CLI, Gemini CLI or a local model.
5. **Tesseract**, which reads the text shown on screen in videos and slides (recommended, not required).
6. Then you open Rot2Gold, and its **setup page** asks where everything goes.

Go to the section for your system: [macOS](#macos), [Windows](#windows), [Linux](#linux). Then read [The setup page](#the-setup-page).

---

## macOS

Open **Terminal** (in Applications → Utilities) for the commands below.

**1. Obsidian.** Download it from [obsidian.md](https://obsidian.md), open it, and create a vault or open the folder you already use.

**2. Homebrew, Git and uv.** Homebrew installs the other tools. Skip the first line if you already have it (`brew --version` answers).

```sh
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
xcode-select --install          # Git, from Apple's command line tools (skip if `git --version` works)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Close Terminal and open it again, so the new commands are found.

**3. Rot2Gold.**

```sh
uv tool install git+https://github.com/MarcoSburlino/rot2gold
```

**4. An AI option:** see [Installing your AI option](#installing-your-ai-option).

**5. Tesseract,** with every language:

```sh
brew install tesseract tesseract-lang
```

**6. Open Rot2Gold:**

```sh
r2g
```

Your browser opens the setup page. If you tick "Add Rot2Gold to my app menu", it also appears as **Rot2Gold** in `~/Applications`, and you can open it from Launchpad or Spotlight from then on.

---

## Windows

Open **PowerShell** (Start menu → type "PowerShell") for the commands below. `winget` comes with Windows 10 and 11.

**1. Obsidian.** Download it from [obsidian.md](https://obsidian.md), open it, and create a vault or open the folder you already use.

**2. Git and uv.**

```powershell
winget install Git.Git
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Close PowerShell and open it again, so the new commands are found.

**3. Rot2Gold.**

```powershell
uv tool install git+https://github.com/MarcoSburlino/rot2gold
```

**4. An AI option:** see [Installing your AI option](#installing-your-ai-option).

**5. Tesseract.** The `-i` opens the installer's own window: under **Additional language data**, tick the languages of the videos you save (English is always included).

```powershell
winget install -i UB-Mannheim.TesseractOCR
```

It installs into `C:\Program Files\Tesseract-OCR`, where Rot2Gold finds it by itself.

**6. Open Rot2Gold:**

```powershell
r2g
```

Your browser opens the setup page. If you tick "Add Rot2Gold to my app menu", **Rot2Gold** appears in the Start menu. Opening it from there also starts a small minimised console window: that is the app running. Close it with **Quit** in the app, not by closing the window.

**On Windows, use Firefox for private collections:** Chrome, Edge and other Chrome-based browsers lock their cookies, so Rot2Gold can't borrow your TikTok login from them.

---

## Linux

The commands are for Fedora, Debian/Ubuntu and Arch; other distributions have the same packages under similar names.

**1. Obsidian.** Install it from [obsidian.md](https://obsidian.md) (AppImage or `.deb`), from Flathub (`flatpak install flathub md.obsidian.Obsidian`) or as a Snap, then create or open a vault. Rot2Gold finds the vaults of all three kinds.

**2. Git and uv.** Git is usually there already (`git --version`).

```sh
sudo dnf install git            # Fedora
sudo apt install git curl       # Debian, Ubuntu
sudo pacman -S git              # Arch

curl -LsSf https://astral.sh/uv/install.sh | sh
```

Open a new terminal, so the new commands are found.

**3. Rot2Gold.**

```sh
uv tool install git+https://github.com/MarcoSburlino/rot2gold
```

**4. An AI option:** see [Installing your AI option](#installing-your-ai-option).

**5. Tesseract,** with a language pack for each language you need (English is included; the examples add Italian):

```sh
sudo dnf install tesseract tesseract-langpack-ita           # Fedora
sudo apt install tesseract-ocr tesseract-ocr-ita            # Debian, Ubuntu
sudo pacman -S tesseract tesseract-data-eng tesseract-data-ita   # Arch
```

**6. Open Rot2Gold:**

```sh
r2g
```

Your browser opens the setup page. If you tick "Add Rot2Gold to my app menu", **Rot2Gold** appears with your other apps (GNOME, KDE and most desktops). If its icon doesn't show at first, log out and back in.

---

## Installing your AI option

You need one of these. Setup shows which ones it finds, so you can also do this step later and press **check again**.

| Option | Good for | You need |
|---|---|---|
| **Claude Code** | the best notes, with web search | a Claude Pro or Max subscription, or an Anthropic API key |
| **Codex CLI** | good notes, with web search | a ChatGPT plan, or an OpenAI API key |
| **Gemini CLI** | good notes, with web search; free tier | a Google account, or a Gemini API key |
| **A local model** | free and private: nothing leaves your computer | a computer that can run an 8B model or larger; notes are simpler, without fact checks |

### Claude Code

```sh
curl -fsSL https://claude.ai/install.sh | bash      # macOS, Linux
```

```powershell
irm https://claude.ai/install.ps1 | iex             # Windows (PowerShell)
```

Then run `claude` once and sign in with your Claude account. With an API key instead, choose "An Anthropic API key" in setup and paste the key there.

### Codex CLI and Gemini CLI

Both need **Node.js 20 or newer** (`node --version`):

| System | Node.js |
|---|---|
| macOS | `brew install node` |
| Windows | `winget install OpenJS.NodeJS.LTS` |
| Linux | your package manager (`sudo dnf install nodejs`, `sudo apt install nodejs npm`); if its version is older than 20, use [nodejs.org](https://nodejs.org) |

Then:

```sh
npm install -g @openai/codex          # Codex CLI; then sign in with: codex login
npm install -g @google/gemini-cli     # Gemini CLI; then run `gemini` once and sign in with Google
```

Codex's Windows support is newer than on macOS and Linux; if it gives you trouble there, pick another option.

### A local model

**Ollama** is the simplest:

| System | Install |
|---|---|
| macOS, Windows | download the app from [ollama.com](https://ollama.com) and open it |
| Linux | `curl -fsSL https://ollama.com/install.sh \| sh` |

Then download a model, for example `ollama pull qwen3:8b`. In setup, choose **Local model**: the server address is filled in (`http://localhost:11434/v1`) and the model list comes from Ollama.

**LM Studio** works too: load a model, turn on its server (Developer tab), and use `http://localhost:1234/v1` as the address in setup. So does **llama.cpp's** `llama-server`: use its address with `/v1` at the end, and if you started it with `--api-key`, paste that key into setup's API key field.

---

## The setup page

The first time you run `r2g`, every page leads to setup. It's one page with six steps; nothing is saved until you press **Finish setup**.

1. **What's on this computer.** Which AI options are installed and signed in, whether Tesseract is there (with the command that installs it on your system), and ffmpeg (it comes with the app if you don't have it). After installing something, press **check again**.
2. **Your Obsidian vault.** Pick one of the vaults Obsidian knows, or choose **Another folder** and type the path or press **Browse…**. Then the **folder for Rot2Gold** inside the vault (default `Rot2Gold`): it gets `Videos`, `Ideas`, `Learnings`, `Events` and `Templates`, a hub note and a quotes note, and the app writes nowhere else. If the vault is a Git repository, leave **commit each change** ticked so any run can be undone from History.
3. **Where to keep videos and other content.** Frames, slide images, the app's database and logs, about 1 MB per video (videos are deleted after reading). It must be outside the vault; the default is your system's app-data folder (see [Where things are](#where-things-are)).
4. **Who writes the notes.** The AI option, and for Claude whether you use your subscription or an API key. **Model** can stay empty to use the option's default (a local model needs one: pick it from the list). An **API key** is only needed if you don't sign in to the tool itself; it's stored in your system's keychain. **Note language** is the language your notes are written in; what creators say stays in their own language.
5. **Languages on screen.** The languages Tesseract should read. Speech is recognised in any language by itself.
6. **Your first collection** (optional). Open the collection on TikTok, copy its address and paste it here, and pick the browser you're logged into TikTok with (only used if the collection is private). Finally, choose whether to **add Rot2Gold to your app menu**.

After **Finish setup**, Rot2Gold creates its folder in your vault, adds the collection, restarts with your choices, and offers **Open Rot2Gold**. Press **Extract new videos** in the sidebar to write the first notes.

To change anything later: **Settings → About → Run setup again**, or `r2g setup` in a terminal (the same questions, without a browser). `r2g setup --check` shows where everything is and what's installed.

---

## Where things are

| | macOS | Windows | Linux |
|---|---|---|---|
| Settings (`config.toml`) | `~/Library/Application Support/rot2gold/` | `%APPDATA%\rot2gold\` | `~/.config/rot2gold/` |
| Videos, images, database, logs (default) | `~/Library/Application Support/rot2gold/` | `%LOCALAPPDATA%\rot2gold\` | `~/.local/share/rot2gold/` |
| The `r2g` command | `~/.local/bin/r2g` | `%USERPROFILE%\.local\bin\r2g.exe` | `~/.local/bin/r2g` |
| App menu entry | `~/Applications/Rot2Gold.app` | Start menu → Rot2Gold | `~/.local/share/applications/rot2gold.desktop` |
| API keys | Keychain | Credential Manager | the keyring (GNOME Keyring, KWallet) |
| Your notes | in your vault, under the folder you chose | | |

The app itself runs in your browser at `http://127.0.0.1:8740` and only answers on your own computer.

---

## Private collections and browser cookies

Public collections need nothing. For a private one, Rot2Gold borrows the TikTok login from your browser: log into TikTok there, and pick that browser in setup (or later in the collection's **⋯** menu).

- **Windows:** use Firefox (Chrome-based browsers lock their cookies).
- **macOS:** Chrome-based browsers ask once for access to their "Safe Storage" key in your keychain: allow it. Reading Safari's cookies needs **Full Disk Access** for the terminal you start Rot2Gold from (System Settings → Privacy & Security); Firefox avoids both.
- **Linux:** Firefox and Chrome-based browsers both work; Chrome-based ones use your keyring, which is unlocked when you log in.

---

## Updating

```sh
uv tool upgrade rot2gold         # a new version of Rot2Gold
r2g update-downloaders           # newer TikTok downloaders, when downloads start failing
```

`r2g update-downloaders` is also a button in **Settings → About**.

## Removing it

```sh
r2g uninstall-launcher           # remove the app menu entry
uv tool uninstall rot2gold       # remove the app
```

Your notes stay in your vault. The settings and data folders (see [Where things are](#where-things-are)) stay too; delete them if you don't need them. An API key, if you saved one, is under the name `rot2gold` in your keychain (Keychain Access on macOS, Credential Manager on Windows, "Passwords and Keys" or KWalletManager on Linux).

---

## If something goes wrong

| Problem | What to do |
|---|---|
| `r2g` is not found | Open a new terminal. If it still isn't found, run `uv tool update-shell`, then open a new terminal again. |
| `uv tool install` fails with a Git error | Install Git (step 2 for your system), open a new terminal, and try again. |
| "Port 8740 is already in use by another app" | Another program uses that address. Add `[app]` `port = 8741` to your `config.toml`. |
| Tesseract is installed but setup says it isn't | Put its full path in `config.toml` under `[ocr]`: `tesseract = "…"` (for example `C:\Program Files\Tesseract-OCR\tesseract.exe`), and `tessdata = "…"` if its languages live elsewhere. |
| Setup doesn't list your vault | Open the vault once in Obsidian, or choose **Another folder** and type its path. |
| No notes are written | **Settings → General → Check** tells you whether the AI option is installed and signed in. The run's page in **History** shows what happened. |
| A private collection can't be read | Log into TikTok in the browser chosen for the collection; on Windows use Firefox. |
| TikTok downloads fail | `r2g update-downloaders`, and wait a while before the next Extract. |

Still stuck? Open an issue on [GitHub](https://github.com/MarcoSburlino/rot2gold/issues) with what you did and the message you saw (leave out keys and private links).
