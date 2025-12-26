import json
import requests
from aqt import mw
from aqt.qt import QAction, QDialog, QVBoxLayout, QTextEdit, QLabel, QComboBox, QPushButton, QProgressDialog, QMessageBox
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from aqt import mw

def get_config():
    return mw.addonManager.getConfig(__name__)

def save_config(cfg):
    mw.addonManager.writeConfig(__name__, cfg)

cfg = get_config()

OPENAI_API_KEY = cfg["openai_api_key"]
OPENAI_BASE_URL = cfg["openai_base_url"]
MODEL = cfg["model"]

class GPTWorker(QThread):
    finished_signal = pyqtSignal(list)
    error_signal = pyqtSignal(str)

    def __init__(self, words):
        super().__init__()
        self.words = words

    def run(self):
        try:
            prompt = f"""
Generate vocabulary flashcards as STRICT JSON.

Rules:
- Output ONLY valid JSON (no markdown, no explanation)
- Output must be a JSON array
- Each item represents ONE word
- SentenceGap must contain "_____"
- MeaningFA must contain exactly two Persian meanings, separated by comma
- Example must be a normal English sentence
- No extra fields

JSON format:
[
  {{
    "Word": "",
    "SentenceGap": "",
    "Hint": "",
    "MeaningFA": "",
    "DefinitionEN": "",
    "Example": "",
    "Synonyms": "",
    "Antonyms": "",
    "OtherForms": ""
  }}
]

Words:
{", ".join(self.words)}
"""

            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": MODEL,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.4,
            }

            resp = requests.post(
                f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60,
            )

            if resp.status_code != 200:
                raise Exception(f"API Error {resp.status_code}: {resp.text}")

            data = resp.json()

            raw = data["choices"][0]["message"]["content"].strip()
            parsed = json.loads(raw)

            if not isinstance(parsed, list):
                raise ValueError("JSON root is not a list")

            self.finished_signal.emit(parsed)

        except Exception as e:
            self.error_signal.emit(str(e))

# ====== GUI برای چندکلمه و انتخاب Deck ======
class MultiWordDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Generate Flashcards from AI")
        layout = QVBoxLayout()
        
        if not OPENAI_API_KEY:
            QMessageBox.information(
                self,
                "API Key not set",
                "API Key not set, Please set it from here, then re-run the app:\n\n"
                "Tools → AI Vocabulary Generator → Settings"
            )
            return

        layout.addWidget(QLabel("Enter words (one per line):"))
        self.words_edit = QTextEdit()
        layout.addWidget(self.words_edit)

        layout.addWidget(QLabel("Select target deck:"))
        self.deck_box = QComboBox()
        for deck in mw.col.decks.allNames():
            self.deck_box.addItem(deck)
        layout.addWidget(self.deck_box)

        self.generate_btn = QPushButton("Generate Cards")
        self.generate_btn.clicked.connect(self.generate_cards)
        layout.addWidget(self.generate_btn)

        self.setLayout(layout)

    def generate_cards(self):
        self.model = ensure_vocabulary_card_model()

        words = [w.strip() for w in self.words_edit.toPlainText().splitlines() if w.strip()]
        deck_name = self.deck_box.currentText()

        if not words:
            QMessageBox.warning(self, "Error", "No words provided.")
            return

        new_words = []
        for word in words:
            if not mw.col.findNotes(f'Word:"{word}"'):
                new_words.append(word)

        if not new_words:
            QMessageBox.information(self, "Info", "All words already exist.")
            return

        self.progress = QProgressDialog(
            "Generating flashcards...", "Cancel", 0, len(new_words), self
        )
        self.progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.progress.show()

        self.worker = GPTWorker(new_words)
        self.worker.finished_signal.connect(
            lambda data: self.process_output(data, deck_name)
        )
        self.worker.error_signal.connect(
            lambda err: QMessageBox.critical(self, "Error", err)
        )
        self.worker.start()

    def process_output(self, data, deck_name):
        deck_id = mw.col.decks.id(deck_name)

        field_names = [
            "Word",
            "SentenceGap",
            "Hint",
            "MeaningFA",
            "DefinitionEN",
            "Example",
            "Synonyms",
            "Antonyms",
            "OtherForms",
        ]

        added = 0

        for i, item in enumerate(data):
            note = mw.col.newNote(self.model)
            note.model()["did"] = deck_id

            for field in field_names:
                note[field] = item.get(field, "")

            mw.col.addNote(note)
            added += 1

            self.progress.setValue(i + 1)
            if self.progress.wasCanceled():
                break

        self.progress.close()
        mw.reset()

        QMessageBox.information(
            self,
            "Done",
            f"Successfully added {added} flashcards."
        )

def open_multi_word_dialog():
    dlg = MultiWordDialog()
    dlg.exec()

def ensure_vocabulary_card_model():
    model_name = "Vocabulary Card"

    required_fields = [
        "Word",
        "SentenceGap",
        "Hint",
        "MeaningFA",
        "DefinitionEN",
        "Example",
        "Synonyms",
        "Antonyms",
        "OtherForms",
    ]

    models = mw.col.models
    model = models.byName(model_name)

    template_name = "Vocabulary Card"

    qfmt = """
<div class="container">
  <div class="word">{{Word}}</div>

  {{#SentenceGap}}
  <div class="section">
    <div class="section-title">Sentence</div>
    <div class="sentence">{{SentenceGap}}</div>
  </div>
  {{/SentenceGap}}

  {{#Hint}}
  <div class="hint">💡 {{Hint}}</div>
  {{/Hint}}
</div>
"""

    afmt = """
<div class="container">
    <div class="word">{{Word}}</div>

    {{#MeaningFA}}
    <div class="section">
        <div class="section-title">Meaning (FA)</div>
        <div class="section-text">{{MeaningFA}}</div>
    </div>
    {{/MeaningFA}}

    {{#DefinitionEN}}
    <div class="section">
        <div class="section-title">Definition</div>
        <div class="section-text">{{DefinitionEN}}</div>
    </div>
    {{/DefinitionEN}}

    {{#Example}}
    <div class="section">
        <div class="section-title">Example</div>
        <div class="section-text">{{Example}}</div>
    </div>
    {{/Example}}

    {{#Synonyms}}
    <div class="section">
        <div class="section-title">Synonyms</div>
        <div class="section-text">{{Synonyms}}</div>
    </div>
    {{/Synonyms}}

    {{#Antonyms}}
    <div class="section">
        <div class="section-title">Antonyms</div>
        <div class="section-text">{{Antonyms}}</div>
    </div>
    {{/Antonyms}}

    {{#OtherForms}}
    <div class="section">
        <div class="section-title">Other Forms</div>
        <div class="section-text">{{OtherForms}}</div>
    </div>
    {{/OtherForms}}
</div>
"""

    css = """
.card {
    font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", sans-serif;
    padding: 0;
    margin: 0;
    text-align: left;
    line-height: 1.65;
    background: #f5f5f5;
}

/* Container with elevation */
.container {
    background: #ffffff;
    max-width: 620px;
    margin: 30px auto;
    padding: 26px 28px;
    border-radius: 14px;
    box-shadow:
        0 3px 6px rgba(0,0,0,0.12),
        0 2px 4px rgba(0,0,0,0.08);
    animation: fadeIn 0.3s ease;
}

/* --- TYPOGRAPHY --- */
.word {
    font-size: 2.25rem;
    font-weight: 700;
    margin-bottom: 18px;
    color: #212121;
}

.section {
    background: #fafafa;
    padding: 14px 16px;
    border-radius: 10px;
    margin-bottom: 14px;
    border-left: 4px solid #2196f3; /* Material blue */
}

.section-title {
    font-size: 0.9rem;
    text-transform: uppercase;
    font-weight: 600;
    margin-bottom: 4px;
    color: #2196f3;
    letter-spacing: 0.5px;
}

.section-text {
    font-size: 1.1rem;
    color: #424242;
}

.hint {
    font-size: 0.95rem;
    color: #757575;
    font-style: italic;
    margin-top: 10px;
}

/* --- Fade animation --- */
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
}

/* --- DARK MODE --- */
@media (prefers-color-scheme: dark) {
    .card {
        background: #0d0d0d;
    }

    .container {
        background: #1c1c1c;
        box-shadow:
            0 3px 6px rgba(0,0,0,0.7),
            0 2px 4px rgba(0,0,0,0.6);
    }

    .word { color: #fff; }
    .section {
        background: #2a2a2a;
        border-left: 4px solid #64b5f6;
    }
    .section-title { color: #64b5f6; }
    .section-text { color: #ddd; }
    .hint { color: #aaa; }
}
"""

    # ======================================
    # CREATE MODEL IF NOT EXISTS
    # ======================================
    if not model:
        model = models.new(model_name)

        for field in required_fields:
            models.addField(model, models.newField(field))

        template = models.newTemplate(template_name)
        template["qfmt"] = qfmt
        template["afmt"] = afmt
        models.addTemplate(model, template)

        model["css"] = css
        models.add(model)
        return model

    # ======================================
    # UPDATE EXISTING MODEL
    # ======================================
    changed = False
    existing_fields = [f["name"] for f in model["flds"]]

    for field in required_fields:
        if field not in existing_fields:
            models.addField(model, models.newField(field))
            changed = True

    tmpl = None
    for t in model["tmpls"]:
        if t["name"] == template_name:
            tmpl = t
            break

    if tmpl:
        if tmpl["qfmt"] != qfmt or tmpl["afmt"] != afmt:
            tmpl["qfmt"] = qfmt
            tmpl["afmt"] = afmt
            changed = True
    else:
        tmpl = models.newTemplate(template_name)
        tmpl["qfmt"] = qfmt
        tmpl["afmt"] = afmt
        models.addTemplate(model, tmpl)
        changed = True

    if model.get("css") != css:
        model["css"] = css
        changed = True

    if changed:
        models.save(model)

    return model

action = QAction("Generate Flashcards (Multi-Word)", mw)
action.triggered.connect(open_multi_word_dialog)
mw.form.menuTools.addAction(action)
