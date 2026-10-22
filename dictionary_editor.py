"""Plain-language dictionary editor; configuration syntax stays internal."""
import tkinter as tk
from tkinter import ttk, messagebox
from amber_core import ConfigError


class DictionaryEditor(ttk.Frame):
    def __init__(self, parent, terms, replacements):
        super().__init__(parent)
        self.rows = dict(replacements)
        self.selected = None
        ttk.Label(self, text="Begriffe besser erkennen – ein Begriff pro Zeile:").pack(anchor="w")
        ttk.Label(self, text="Beispiele: Projektbesprechung, Angebotsnummer, Kundendienst",
                  style="Muted.TLabel").pack(anchor="w")
        self.terms = self.text_box(3)
        self.terms.insert("1.0", "\n".join(terms))
        ttk.Label(self, text="Gesprochene Wörter durch Text oder Zeichen ersetzen:").pack(anchor="w", pady=(8, 4))
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True)
        self.table = ttk.Treeview(frame, columns=("spoken", "written"), show="headings", height=5, selectmode="browse")
        self.table.heading("spoken", text="Was du sagst")
        self.table.heading("written", text="Was eingefügt wird")
        for column in ("spoken", "written"):
            self.table.column(column, width=260, minwidth=100)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.table.pack(fill="both", expand=True)
        self.table.bind("<<TreeviewSelect>>", self.select)
        ttk.Label(self, text="Was du sagst:").pack(anchor="w", pady=(6, 0))
        self.spoken = ttk.Entry(self)
        self.spoken.pack(fill="x")
        ttk.Label(self, text="Was eingefügt wird (Enter für einen Zeilenumbruch):").pack(anchor="w", pady=(4, 0))
        ttk.Label(self, text="↵ = Zeilenumbruch; ↵ ↵ = Absatz. Im Eingabefeld einmal bzw. zweimal Enter drücken.",
                  wraplength=580).pack(anchor="w")
        self.written = self.text_box(2)
        self.literal_hint = tk.StringVar()
        ttk.Label(self, textvariable=self.literal_hint, wraplength=580).pack(anchor="w")
        self.written.bind("<<Modified>>", self.update_hint)
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=4)
        ttk.Button(bar, text="Neu", command=self.new).pack(side="left")
        ttk.Button(bar, text="Eintrag übernehmen", command=self.apply).pack(side="left", padx=6)
        ttk.Button(bar, text="Entfernen", command=self.remove).pack(side="left")
        self.refresh()

    def update_hint(self, _event=None):
        if not self.written.edit_modified():
            return
        value = self.written.get("1.0", "end-1c")
        self.literal_hint.set("Hinweis: " + chr(92) + "n ist hier wörtlicher Text. Für einen Umbruch Enter drücken."
                              if chr(92) + "n" in value else "")
        self.written.edit_modified(False)

    def text_box(self, height):
        box = tk.Text(self, height=height, wrap="word", bg="#27272a", fg="#f4f4f5",
                      insertbackground="white", selectbackground="#2563eb", relief="flat", padx=8, pady=4)
        box.pack(fill="x", pady=4)
        return box

    def refresh(self):
        self.table.delete(*self.table.get_children())
        for index, (spoken, written) in enumerate(self.rows.items()):
            display = written.replace("\n", " ↵ ") or "(entfernen)"
            if chr(92) + "n" in written:
                display += " (wörtlich, kein Umbruch)"
            self.table.insert("", "end", iid=spoken, values=(spoken, display))

    def values(self):
        return self.spoken.get().strip(), self.written.get("1.0", "end-1c")

    def commit(self):
        spoken, written = self.values()
        if not spoken:
            if written or self.selected is not None:
                raise ConfigError("Bitte bei ‚Was du sagst‘ ein Wort oder einen Sprachbefehl eingeben.")
            return
        if any(key.casefold() == spoken.casefold() and key != self.selected for key in self.rows):
            raise ConfigError("Diesen Sprachbefehl gibt es bereits. Wähle den vorhandenen Eintrag zum Bearbeiten aus.")
        if self.selected is not None and self.selected != spoken:
            del self.rows[self.selected]
        self.rows[spoken] = written
        self.selected = spoken

    def apply(self):
        try:
            self.commit()
        except ConfigError as exc:
            messagebox.showerror("Wörterbuch", str(exc), parent=self)
            return False
        self.refresh()
        return True

    def select(self, _event=None):
        selection = self.table.selection()
        if not selection:
            return
        key = selection[0]
        # Preserve edits when switching rows; refresh is deliberately deferred.
        try:
            self.commit()
        except ConfigError as exc:
            messagebox.showerror("Wörterbuch", str(exc), parent=self)
            return
        self.refresh()
        self.selected = key
        self.spoken.delete(0, "end")
        self.spoken.insert(0, key)
        self.written.delete("1.0", "end")
        self.written.insert("1.0", self.rows[key])

    def new(self):
        if not self.apply():
            return
        self.selected = None
        self.spoken.delete(0, "end")
        self.written.delete("1.0", "end")
        self.spoken.focus_set()

    def remove(self):
        if self.selected is not None:
            self.rows.pop(self.selected, None)
        self.selected = None
        self.spoken.delete(0, "end")
        self.written.delete("1.0", "end")
        self.refresh()

    def get(self):
        self.commit()  # Saving also accepts the entry currently being edited.
        terms = [line.strip() for line in self.terms.get("1.0", "end").splitlines() if line.strip()]
        return terms, dict(self.rows)
