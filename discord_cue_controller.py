"""
Discord Scripted Cue Controller & REST API Bridge
Author: Waseequr Rahman
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import tkinter as tk
from tkinter import scrolledtext, ttk
from typing import List

import discord
import requests
from discord.ext import commands
from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("discord_cue_controller")

TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
TARGET_USER_ID = int(os.getenv("DISCORD_TARGET_USER_ID", "0"))
PORT = int(os.getenv("FLASK_PORT", "5001"))

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

app = Flask(__name__)
script_lines: List[str] = []
current_line: int = 0


@app.route("/upload_script", methods=["POST"])
def upload_script():
    global script_lines, current_line
    payload = request.get_json(silent=True) or {}
    raw_script = str(payload.get("script", ""))
    script_lines = [line.strip() for line in raw_script.splitlines() if line.strip()]
    current_line = 0
    return jsonify({"status": "uploaded", "total_lines": len(script_lines)})


@app.route("/current_line", methods=["GET"])
def get_current_line():
    if current_line < len(script_lines):
        return jsonify(
            {
                "current_line": script_lines[current_line],
                "line_number": current_line + 1,
                "total_lines": len(script_lines),
            }
        )
    return jsonify({"current_line": "End of script", "line_number": -1, "total_lines": len(script_lines)})


@app.route("/next_line", methods=["POST"])
def next_line_endpoint():
    global current_line
    if current_line >= len(script_lines):
        return jsonify({"status": "end_of_script"})

    line_to_send = script_lines[current_line]

    async def _send() -> None:
        target = await bot.fetch_user(TARGET_USER_ID)
        await target.send(line_to_send)

    future = asyncio.run_coroutine_threadsafe(_send(), bot.loop)
    future.result(timeout=10)
    current_line += 1
    return jsonify({"status": "sent", "sent_line": line_to_send, "next_index": current_line})


@app.route("/skip_line", methods=["POST"])
def skip_line():
    global current_line
    if current_line < len(script_lines):
        skipped = script_lines[current_line]
        current_line += 1
        return jsonify({"status": "skipped", "skipped_line": skipped})
    return jsonify({"status": "end_of_script"})


@bot.event
async def on_ready():
    logger.info("Discord Cue Bot connected as %s", bot.user)


def launch_operator_gui() -> None:
    base_url = f"http://127.0.0.1:{PORT}"
    root = tk.Tk()
    root.title("Discord Scripted Cue Operator Console")
    root.geometry("540x430")

    ttk.Label(root, text="Cue Script (one message per line):").pack(pady=6)
    script_area = scrolledtext.ScrolledText(root, width=58, height=12, wrap=tk.WORD)
    script_area.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

    status_var = tk.StringVar(value="Current Cue: None")

    def refresh_status() -> None:
        try:
            data = requests.get(f"{base_url}/current_line", timeout=5).json()
            status_var.set(f"Next Cue ({data.get('line_number')}/{data.get('total_lines')}): {data.get('current_line')}")
        except Exception as exc:
            status_var.set(f"API Error: {exc}")

    def on_upload() -> None:
        text = script_area.get("1.0", tk.END).strip()
        requests.post(f"{base_url}/upload_script", json={"script": text}, timeout=5)
        refresh_status()

    def on_next() -> None:
        requests.post(f"{base_url}/next_line", timeout=10)
        refresh_status()

    def on_skip() -> None:
        requests.post(f"{base_url}/skip_line", timeout=5)
        refresh_status()

    btns = ttk.Frame(root)
    btns.pack(pady=8)
    ttk.Button(btns, text="Load Queue", command=on_upload).pack(side=tk.LEFT, padx=5)
    ttk.Button(btns, text="Send Next Cue", command=on_next).pack(side=tk.LEFT, padx=5)
    ttk.Button(btns, text="Skip Cue", command=on_skip).pack(side=tk.LEFT, padx=5)

    ttk.Label(root, textvariable=status_var, padding=6).pack(fill=tk.X)
    root.mainloop()


if __name__ == "__main__":
    threading.Thread(target=lambda: app.run(host="127.0.0.1", port=PORT), daemon=True).start()
    threading.Thread(target=launch_operator_gui, daemon=True).start()
    if TOKEN:
        bot.run(TOKEN)
    else:
        logger.warning("DISCORD_BOT_TOKEN not set in .env. Running GUI + REST server in local mode.")
        threading.Event().wait()
