import os
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from deep_translator import GoogleTranslator

# Optional extras - app still works if these aren't installed
try:
    import pyperclip
    CLIPBOARD_AVAILABLE = True
except ImportError:
    CLIPBOARD_AVAILABLE = False

try:
    from gtts import gTTS
    from gtts.lang import tts_langs as _gtts_langs
    import pygame
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False

try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
except ImportError:
    PYTTSX3_AVAILABLE = False

# pyttsx3 relies on the OS speech engine (SAPI5 / NSSpeech / espeak), which
# usually has no Urdu/Hindi/Arabic voice installed and either stays silent
# or mispronounces the text. gTTS uses Google's own multilingual voices, so
# we prefer it whenever it's available and only fall back to pyttsx3 (e.g.
# fully offline) if gTTS can't be used.
TTS_AVAILABLE = GTTS_AVAILABLE or PYTTSX3_AVAILABLE

# ----------------------------------------------------------------------
# Palette
# ----------------------------------------------------------------------
COLORS = {
    "bg":          "#0f172a",   # app background (deep slate)
    "surface":     "#1a2438",   # card background
    "surface_alt": "#141d2f",   # slightly darker card (output)
    "border":      "#2a3652",
    "border_soft": "#232d47",
    "text":        "#e8ecf5",
    "text_dim":    "#98a2bb",
    "text_faint":  "#6b7590",
    "accent":      "#6366f1",   # indigo
    "accent_hover":"#7678f5",
    "accent_dark": "#4f52d4",
    "accent_soft": "#242a52",
    "success":     "#34d399",
    "warning":     "#fbbf24",
    "danger":      "#f87171",
    "chip":        "#232d47",
}

# Language list ( common subset understood by Google Translate)
LANGUAGES = {
    "Auto Detect": "auto",
    "English": "en",
    "Urdu": "ur",
    "Arabic": "ar",
    "French": "fr",
    "Spanish": "es",
    "German": "de",
    "Italian": "it",
    "Portuguese": "pt",
    "Russian": "ru",
    "Chinese (Simplified)": "zh-CN",
    "Japanese": "ja",
    "Korean": "ko",
    "Hindi": "hi",
    "Turkish": "tr",
    "Persian": "fa",
    "Punjabi": "pa",
    "Bengali": "bn",
    "Dutch": "nl",
    "Greek": "el",
    "Hebrew": "iw",
    "Indonesian": "id",
    "Vietnamese": "vi",
    "Thai": "th",
    "Swahili": "sw",
    "Polish": "pl",
    "Ukrainian": "uk",
}

# Target language cannot be "auto"
TARGET_LANGUAGES = {k: v for k, v in LANGUAGES.items() if v != "auto"}


class RoundedButton(tk.Canvas):
    """A flat, modern 'pill' style button drawn on a canvas so we get
    rounded corners and smooth hover/press states that plain ttk/tk
    buttons can't easily provide."""

    def __init__(self, parent, text, command=None, *, width=140, height=40,
                 radius=12, bg=None, fg="#ffffff", hover_bg=None,
                 font=("Segoe UI", 10, "bold"), disabled_bg="#2a3652",
                 disabled_fg="#6b7590"):
        super().__init__(parent, width=width, height=height,
                          bg=parent["bg"] if isinstance(parent, (tk.Frame, tk.Canvas)) else COLORS["bg"],
                          highlightthickness=0, bd=0, cursor="hand2")
        self.command = command
        self.radius = radius
        self.width = width
        self.height = height
        self.bg_color = bg or COLORS["accent"]
        self.hover_color = hover_bg or COLORS["accent_hover"]
        self.disabled_bg = disabled_bg
        self.disabled_fg = disabled_fg
        self.fg_color = fg
        self.font = font
        self.text = text
        self.enabled = True

        self._draw(self.bg_color, self.fg_color)

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

    def _round_rect(self, x1, y1, x2, y2, r, **kwargs):
        points = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        return self.create_polygon(points, smooth=True, **kwargs)

    def _draw(self, fill, text_fill):
        self.delete("all")
        self._round_rect(1, 1, self.width - 1, self.height - 1, self.radius,
                          fill=fill, outline="")
        self.create_text(self.width / 2, self.height / 2, text=self.text,
                          fill=text_fill, font=self.font)

    def _on_enter(self, _event):
        if self.enabled:
            self._draw(self.hover_color, self.fg_color)

    def _on_leave(self, _event):
        if self.enabled:
            self._draw(self.bg_color, self.fg_color)

    def _on_click(self, _event):
        if self.enabled and self.command:
            self.command()

    def set_enabled(self, enabled):
        self.enabled = enabled
        if enabled:
            self.configure(cursor="hand2")
            self._draw(self.bg_color, self.fg_color)
        else:
            self.configure(cursor="arrow")
            self._draw(self.disabled_bg, self.disabled_fg)


class IconButton(tk.Label):
    """Small ghost/icon style button (for Copy / Speak actions) that
    lights up subtly on hover."""

    def __init__(self, parent, text, command=None, *, fg=None):
        super().__init__(
            parent, text=text, bg=COLORS["surface"], fg=fg or COLORS["text_dim"],
            font=("Segoe UI", 9, "bold"), padx=10, pady=5, cursor="hand2",
        )
        self.command = command
        self.default_bg = COLORS["surface"]
        self.hover_bg = COLORS["chip"]
        self.bind("<Enter>", lambda e: self.configure(bg=self.hover_bg))
        self.bind("<Leave>", lambda e: self.configure(bg=self.default_bg))
        self.bind("<Button-1>", self._on_click)
        self._enabled = True

    def _on_click(self, _event):
        if self._enabled and self.command:
            self.command()

    def set_enabled(self, enabled):
        self._enabled = enabled
        if enabled:
            self.configure(fg=COLORS["text_dim"], cursor="hand2")
        else:
            self.configure(fg=COLORS["text_faint"], cursor="arrow")


class TranslatorApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Language Translator")
        self.geometry("860x640")
        self.minsize(680, 540)
        self.configure(bg=COLORS["bg"])

        self._build_styles()
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background=COLORS["bg"])
        style.configure("Card.TFrame", background=COLORS["surface"])
        style.configure("TLabel", background=COLORS["bg"], font=("Segoe UI", 10), foreground=COLORS["text_dim"])
        style.configure("Card.TLabel", background=COLORS["surface"], font=("Segoe UI", 10), foreground=COLORS["text_dim"])
        style.configure(
            "Header.TLabel", font=("Segoe UI", 22, "bold"),
            background=COLORS["bg"], foreground=COLORS["text"],
        )
        style.configure(
            "Sub.TLabel", font=("Segoe UI", 10),
            background=COLORS["bg"], foreground=COLORS["text_faint"],
        )
        style.configure(
            "SectionTitle.TLabel", font=("Segoe UI", 10, "bold"),
            background=COLORS["surface"], foreground=COLORS["text"],
        )

        # Combobox: modern flat dark style
        style.configure(
            "Lang.TCombobox",
            font=("Segoe UI", 10),
            fieldbackground=COLORS["chip"],
            background=COLORS["chip"],
            foreground=COLORS["text"],
            arrowcolor=COLORS["text_dim"],
            bordercolor=COLORS["border"],
            lightcolor=COLORS["chip"],
            darkcolor=COLORS["chip"],
            padding=6,
            relief="flat",
        )
        style.map(
            "Lang.TCombobox",
            fieldbackground=[("readonly", COLORS["chip"])],
            foreground=[("readonly", COLORS["text"])],
            background=[("readonly", COLORS["chip"])],
        )
        self.option_add("*TCombobox*Listbox.background", COLORS["surface"])
        self.option_add("*TCombobox*Listbox.foreground", COLORS["text"])
        self.option_add("*TCombobox*Listbox.selectBackground", COLORS["accent"])
        self.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        self.option_add("*TCombobox*Listbox.font", ("Segoe UI", 10))

    def _build_ui(self):
        outer = tk.Frame(self, bg=COLORS["bg"])
        outer.pack(fill="both", expand=True, padx=28, pady=24)

        # ---- Header --------------------------------------------------
        header_row = tk.Frame(outer, bg=COLORS["bg"])
        header_row.pack(fill="x", pady=(0, 20))

        title_col = tk.Frame(header_row, bg=COLORS["bg"])
        title_col.pack(side="left")

        header = ttk.Label(title_col, text="🌐  Language Translator", style="Header.TLabel")
        header.pack(anchor="w")
        sub = ttk.Label(title_col, text="Fast, free translation between 25+ languages", style="Sub.TLabel")
        sub.pack(anchor="w", pady=(2, 0))

        # ---- Language selector card ----------------------------------
        lang_card = tk.Frame(outer, bg=COLORS["surface"], highlightbackground=COLORS["border"],
                              highlightthickness=1, bd=0)
        lang_card.pack(fill="x", pady=(0, 16))
        lang_inner = tk.Frame(lang_card, bg=COLORS["surface"])
        lang_inner.pack(fill="x", padx=18, pady=14)

        lang_inner.grid_columnconfigure(0, weight=1)
        lang_inner.grid_columnconfigure(2, weight=0)
        lang_inner.grid_columnconfigure(4, weight=1)

        from_col = tk.Frame(lang_inner, bg=COLORS["surface"])
        from_col.grid(row=0, column=0, sticky="ew")
        ttk.Label(from_col, text="TRANSLATE FROM", style="Card.TLabel",
                  font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 4))
        self.source_lang = ttk.Combobox(
            from_col, values=list(LANGUAGES.keys()), state="readonly",
            style="Lang.TCombobox", font=("Segoe UI", 10),
        )
        self.source_lang.set("Auto Detect")
        self.source_lang.pack(fill="x")

        swap_wrap = tk.Frame(lang_inner, bg=COLORS["surface"])
        swap_wrap.grid(row=0, column=1, padx=16)
        self.swap_btn = tk.Label(
            swap_wrap, text="⇄", font=("Segoe UI", 15, "bold"),
            bg=COLORS["chip"], fg=COLORS["accent_hover"], width=3, height=1,
            cursor="hand2",
        )
        self.swap_btn.pack(pady=(14, 0))
        self.swap_btn.bind("<Button-1>", lambda e: self.swap_languages())
        self.swap_btn.bind("<Enter>", lambda e: self.swap_btn.configure(bg=COLORS["accent_soft"]))
        self.swap_btn.bind("<Leave>", lambda e: self.swap_btn.configure(bg=COLORS["chip"]))

        to_col = tk.Frame(lang_inner, bg=COLORS["surface"])
        to_col.grid(row=0, column=2, sticky="ew")
        ttk.Label(to_col, text="TRANSLATE TO", style="Card.TLabel",
                  font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 4))
        self.target_lang = ttk.Combobox(
            to_col, values=list(TARGET_LANGUAGES.keys()), state="readonly",
            style="Lang.TCombobox", font=("Segoe UI", 10),
        )
        self.target_lang.set("Urdu")
        self.target_lang.pack(fill="x")

        lang_inner.grid_columnconfigure(0, weight=1, uniform="col")
        lang_inner.grid_columnconfigure(2, weight=1, uniform="col")

        # ---- Input card -------------------------------------------------
        in_card = tk.Frame(outer, bg=COLORS["surface"], highlightbackground=COLORS["border"],
                            highlightthickness=1, bd=0)
        in_card.pack(fill="both", expand=True, pady=(0, 12))

        in_label_row = tk.Frame(in_card, bg=COLORS["surface"])
        in_label_row.pack(fill="x", padx=16, pady=(12, 6))
        ttk.Label(in_label_row, text="Enter text", style="SectionTitle.TLabel").pack(side="left")

        in_btns = tk.Frame(in_label_row, bg=COLORS["surface"])
        in_btns.pack(side="right")
        self.in_speak_btn = IconButton(in_btns, "🔊  Speak", command=self.speak_input)
        self.in_speak_btn.pack(side="right", padx=(6, 0))
        if not TTS_AVAILABLE:
            self.in_speak_btn.set_enabled(False)

        in_copy_btn = IconButton(in_btns, "📋  Copy", command=self.copy_input)
        in_copy_btn.pack(side="right")
        if not CLIPBOARD_AVAILABLE:
            in_copy_btn.set_enabled(False)

        text_wrap_in = tk.Frame(in_card, bg=COLORS["chip"])
        text_wrap_in.pack(fill="both", expand=True, padx=16, pady=(0, 14))
        self.input_text = tk.Text(
            text_wrap_in, height=6, wrap="word", font=("Segoe UI", 11),
            relief="flat", borderwidth=0, padx=12, pady=10,
            bg=COLORS["chip"], fg=COLORS["text"], insertbackground=COLORS["text"],
            selectbackground=COLORS["accent"], selectforeground="#ffffff",
        )
        self.input_text.pack(fill="both", expand=True)
        self.input_text.bind("<<Modified>>", self._on_input_change)

        # ---- Action row -------------------------------------------------
        action_row = tk.Frame(outer, bg=COLORS["bg"])
        action_row.pack(fill="x", pady=(0, 12))

        self.translate_btn = RoundedButton(
            action_row, "Translate  ➜", command=self.start_translation,
            width=160, height=42, radius=14,
        )
        self.translate_btn.pack(side="left")

        self.clear_btn = RoundedButton(
            action_row, "Clear", command=self.clear_all,
            width=100, height=42, radius=14, bg=COLORS["chip"],
            hover_bg=COLORS["border_soft"], fg=COLORS["text_dim"],
        )
        self.clear_btn.pack(side="left", padx=(10, 0))

        status_wrap = tk.Frame(action_row, bg=COLORS["bg"])
        status_wrap.pack(side="right")
        self.status_dot = tk.Canvas(status_wrap, width=9, height=9, bg=COLORS["bg"],
                                     highlightthickness=0)
        self.status_dot.pack(side="left", padx=(0, 6))
        self._set_status_dot(None)
        self.status_label = tk.Label(status_wrap, text="", bg=COLORS["bg"],
                                      fg=COLORS["text_faint"], font=("Segoe UI", 9))
        self.status_label.pack(side="left")

        # ---- Output card -------------------------------------------------
        out_card = tk.Frame(outer, bg=COLORS["surface_alt"], highlightbackground=COLORS["border"],
                             highlightthickness=1, bd=0)
        out_card.pack(fill="both", expand=True)

        out_label_row = tk.Frame(out_card, bg=COLORS["surface_alt"])
        out_label_row.pack(fill="x", padx=16, pady=(12, 6))
        ttk.Label(out_label_row, text="Translation", style="Card.TLabel",
                  font=("Segoe UI", 10, "bold"), background=COLORS["surface_alt"],
                  foreground=COLORS["text"]).pack(side="left")

        out_btns = tk.Frame(out_label_row, bg=COLORS["surface_alt"])
        out_btns.pack(side="right")
        self.speak_btn = IconButton(out_btns, "🔊  Speak", command=self.speak_output)
        self.speak_btn.configure(bg=COLORS["surface_alt"])
        self.speak_btn.default_bg = COLORS["surface_alt"]
        self.speak_btn.pack(side="right", padx=(6, 0))
        if not TTS_AVAILABLE:
            self.speak_btn.set_enabled(False)

        copy_btn = IconButton(out_btns, "📋  Copy", command=self.copy_output)
        copy_btn.configure(bg=COLORS["surface_alt"])
        copy_btn.default_bg = COLORS["surface_alt"]
        copy_btn.pack(side="right")
        if not CLIPBOARD_AVAILABLE:
            copy_btn.set_enabled(False)

        text_wrap_out = tk.Frame(out_card, bg=COLORS["bg"])
        text_wrap_out.pack(fill="both", expand=True, padx=16, pady=(0, 14))
        self.output_text = tk.Text(
            text_wrap_out, height=6, wrap="word", font=("Segoe UI", 11),
            relief="flat", borderwidth=0, padx=12, pady=10,
            bg=COLORS["bg"], fg=COLORS["text"],
            selectbackground=COLORS["accent"], selectforeground="#ffffff",
        )
        self.output_text.pack(fill="both", expand=True)
        self.output_text.config(state="disabled")

        # ---- Footer note for missing optional deps -----------------------
        if not CLIPBOARD_AVAILABLE or not TTS_AVAILABLE:
            missing = []
            if not CLIPBOARD_AVAILABLE:
                missing.append("pyperclip")
            if not TTS_AVAILABLE:
                missing.append("gTTS + pygame")
            tk.Label(
                outer,
                text=f"⚠  Install {', '.join(missing)} to unlock all features",
                bg=COLORS["bg"], fg=COLORS["warning"], font=("Segoe UI", 9),
            ).pack(anchor="w", pady=(10, 0))

    # ------------------------------------------------------------------
    # Small visual helpers
    # ------------------------------------------------------------------
    def _set_status_dot(self, kind):
        """kind: None | 'busy' | 'ok' | 'error'"""
        self.status_dot.delete("all")
        color = {
            None: COLORS["border"],
            "busy": COLORS["warning"],
            "ok": COLORS["success"],
            "error": COLORS["danger"],
        }.get(kind, COLORS["border"])
        self.status_dot.create_oval(1, 1, 8, 8, fill=color, outline="")

    def _on_input_change(self, _event):
        self.input_text.edit_modified(False)

    # ------------------------------------------------------------------
    # Logic
    # ------------------------------------------------------------------
    def swap_languages(self):
        src = self.source_lang.get()
        tgt = self.target_lang.get()
        if src == "Auto Detect":
            messagebox.showinfo("Can't swap", "Choose a specific source language before swapping.")
            return
        self.source_lang.set(tgt)
        self.target_lang.set(src)

    def clear_all(self):
        self.input_text.delete("1.0", "end")
        self._set_output("")
        self.status_label.config(text="")
        self._set_status_dot(None)

    def start_translation(self):
        text = self.input_text.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning("Empty input", "Please enter some text to translate.")
            return

        self.translate_btn.set_enabled(False)
        self._set_status_dot("busy")
        self.status_label.config(text="Translating…", fg=COLORS["warning"])
        self._set_output("")

        # Run the network call in a background thread so the UI never freezes
        thread = threading.Thread(target=self._translate_worker, args=(text,), daemon=True)
        thread.start()

    def _translate_worker(self, text):
        try:
            source_code = LANGUAGES[self.source_lang.get()]
            target_code = TARGET_LANGUAGES[self.target_lang.get()]

            translator = GoogleTranslator(source=source_code, target=target_code)
            result = translator.translate(text)
        except Exception as exc:
            self.after(0, self._on_translation_error, str(exc))
            return

        self.after(0, self._on_translation_done, result)

    def _on_translation_done(self, result):
        self._set_output(result)
        self._set_status_dot("ok")
        self.status_label.config(text="Done ✔", fg=COLORS["success"])
        self.translate_btn.set_enabled(True)

    def _on_translation_error(self, error_message):
        self._set_status_dot("error")
        self.status_label.config(text="Error", fg=COLORS["danger"])
        self.translate_btn.set_enabled(True)
        messagebox.showerror(
            "Translation failed",
            f"Could not translate the text.\n\nDetails: {error_message}\n\n"
            "Check your internet connection and try again.",
        )

    def _set_output(self, text):
        self.output_text.config(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.insert("1.0", text)
        self.output_text.config(state="disabled")

    # ------------------------------------------------------------------
    # Shared copy / speak helpers
    # ------------------------------------------------------------------
    def _copy_text(self, text, label):
        if not text:
            messagebox.showinfo("Nothing to copy", "There's no text to copy yet.")
            return
        if not CLIPBOARD_AVAILABLE:
            messagebox.showwarning("Unavailable", "Install 'pyperclip' to enable copying.")
            return
        try:
            pyperclip.copy(text)
            self._set_status_dot("ok")
            self.status_label.config(text=f"{label} copied to clipboard ✔", fg=COLORS["success"])
        except Exception as exc:
            # Most common cause on Linux: no clipboard backend installed.
            messagebox.showerror(
                "Copy failed",
                "Could not copy to the clipboard.\n\n"
                f"Details: {exc}\n\n"
                "On Linux, install a clipboard tool and try again:\n"
                "    sudo apt-get install xclip\n"
                "  (or)  sudo apt-get install xsel",
            )

    def _resolve_gtts_lang(self, lang_code):
        """gTTS needs a code it actually recognizes. Try the code as-is,
        then its base (e.g. 'zh-CN' -> 'zh'), then fall back to English
        rather than silently failing on an unsupported/unknown tag."""
        try:
            supported = _gtts_langs()
        except Exception:
            # Couldn't fetch the live list (e.g. no internet yet) - just
            # try the code as given and let gTTS itself raise if it's bad.
            return lang_code

        code = lang_code.lower()
        if code in supported:
            return code
        base = code.split("-")[0]
        if base in supported:
            return base
        # A couple of known historical mismatches between Google Translate
        # codes and gTTS codes.
        aliases = {"iw": "he", "in": "id"}
        if base in aliases and aliases[base] in supported:
            return aliases[base]
        return "en"

    def _speak_text(self, text, button, lang_code="en"):
        if not text:
            messagebox.showinfo("Nothing to speak", "There's no text to read yet.")
            return
        if not TTS_AVAILABLE:
            messagebox.showwarning(
                "Unavailable",
                "Install 'gTTS' and 'pygame' to enable text-to-speech\n"
                "(recommended - supports Urdu, Hindi, Arabic, etc. properly).",
            )
            return

        # Disable the button while speaking to avoid overlapping calls.
        button.set_enabled(False)
        self._set_status_dot("busy")
        self.status_label.config(text="Speaking…", fg=COLORS["warning"])

        def _speak():
            tmp_path = None
            try:
                if GTTS_AVAILABLE:
                    # gTTS uses Google's own multilingual voices, so Urdu,
                    # Hindi, Arabic, etc. are pronounced correctly - unlike
                    # pyttsx3, which depends on whatever voices happen to
                    # be installed on the OS.
                    resolved = self._resolve_gtts_lang(lang_code)
                    tts = gTTS(text=text, lang=resolved)
                    fd, tmp_path = tempfile.mkstemp(suffix=".mp3")
                    os.close(fd)
                    tts.save(tmp_path)

                    pygame.mixer.init()
                    pygame.mixer.music.load(tmp_path)
                    pygame.mixer.music.play()
                    while pygame.mixer.music.get_busy():
                        pygame.time.wait(100)
                    pygame.mixer.music.unload()
                    pygame.mixer.quit()
                elif PYTTSX3_AVAILABLE:
                    # Offline fallback - fine for English, unreliable for
                    # Urdu/Hindi/Arabic depending on what's installed on
                    # this machine.
                    engine = pyttsx3.init()
                    engine.say(text)
                    engine.runAndWait()
                    engine.stop()
                else:
                    raise RuntimeError("No text-to-speech engine available.")

                self.after(0, lambda: (
                    self._set_status_dot("ok"),
                    self.status_label.config(text="Done speaking ✔", fg=COLORS["success"]),
                ))
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror(
                    "Speech failed",
                    f"Could not play speech.\n\nDetails: {exc}\n\n"
                    "Make sure you're connected to the internet (gTTS needs it),"
                    " or install 'espeak' on Linux for the offline fallback.",
                ))
            finally:
                if tmp_path:
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
                self.after(0, lambda: button.set_enabled(True))

        threading.Thread(target=_speak, daemon=True).start()

    def copy_input(self):
        text = self.input_text.get("1.0", "end").strip()
        self._copy_text(text, "Input")

    def speak_input(self):
        text = self.input_text.get("1.0", "end").strip()
        # If the source language is "Auto Detect" we have no explicit code
        # to give gTTS, so default to English for the input side.
        src_name = self.source_lang.get()
        lang_code = LANGUAGES.get(src_name, "en")
        if lang_code == "auto":
            lang_code = "en"
        self._speak_text(text, self.in_speak_btn, lang_code)

    def copy_output(self):
        text = self.output_text.get("1.0", "end").strip()
        self._copy_text(text, "Translation")

    def speak_output(self):
        text = self.output_text.get("1.0", "end").strip()
        lang_code = TARGET_LANGUAGES.get(self.target_lang.get(), "en")
        self._speak_text(text, self.speak_btn, lang_code)


if __name__ == "__main__":
    app = TranslatorApp()
    app.mainloop()
