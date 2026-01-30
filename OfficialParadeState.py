import re
import os
import time
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- KOYEB HEALTH CHECK SERVER ---
# This tiny server tells Koyeb "I am alive" so the free tier doesn't shut down.
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is active")

    def log_message(self, format, *args):
        return # Quiet logs to keep the console clean

def run_health_server():
    # Port 8000 is the default for Koyeb health checks
    server = HTTPServer(('0.0.0.0', 8000), HealthCheckHandler)
    server.serve_forever()

# Start the health server in a background thread
threading.Thread(target=run_health_server, daemon=True).start()

# --- 1. CONFIGURATION ---
os.environ['TZ'] = 'Asia/Singapore'
try:
    time.tzset()
except AttributeError:
    pass

TOKEN = "8486319366:AAHCzqbC9W-iQPi6iByMRc9ysS0rQb7m6Gg"

DISPLAY_ORDER = ["HQ", "Alpha", "Bravo", "Charlie", "MSC", "Support"]
NSF_RANKS = r'\b(2LT|3SG|2SG|1SG|CFC|CPL|LCP|PTE|REC)\b'

parade_data = {coy: None for coy in DISPLAY_ORDER}

# --- 2. LOGIC FUNCTIONS ---

def parse_parade_state(text, coy_name):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    lines = [l for l in lines if "kranji camp" not in l.lower()]
    date_pattern = re.compile(r'\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4}')
    lines = [l for l in lines if not date_pattern.search(l)]

    parsed = {"personnel": [], "attached": []}
    attached_idx = next((i for i, l in enumerate(lines) if "attached" in l.lower()), None)
    content_lines = lines[1:] if "parade state" in lines[0].lower() else lines

    if attached_idx is not None:
        adj_idx = attached_idx - (1 if "parade state" in lines[0].lower() else 0)
        main_lines = content_lines[:adj_idx]
        attached_lines = content_lines[adj_idx + 1:]
    else:
        main_lines, attached_lines = content_lines, []

    def process_lines(line_list):
        res = []
        for l in line_list:
            l = re.sub(r'^\d+\.\s*', '', l)
            status = 'Present' if '✅' in l else 'Absent' if '❌' in l else 'Unknown'
            
            # NSF Detection with Exception for 3SG Yong Yuan
            is_nsf = bool(re.search(NSF_RANKS, l, re.IGNORECASE))
            if "yong yuan" in l.lower():
                is_nsf = False 
            
            if coy_name == "Support":
                remark_match = re.search(r'\((.*?)\)', l)
                remark = f"({remark_match.group(1)})" if remark_match else ""
                name_part = re.sub(r'✅|❌|\(.*?\)', '', l).strip()
                formatted = f"{name_part} {'✅' if status == 'Present' else '❌'} {remark}".strip()
                res.append({'text': formatted, 'status': status, 'is_nsf': is_nsf})
            else:
                res.append({'text': l, 'status': status, 'is_nsf': is_nsf})
        return res

    parsed["personnel"] = process_lines(main_lines)
    parsed["attached"] = process_lines(attached_lines)
    return parsed

def detect_company(text):
    header = "\n".join(text.lower().splitlines()[:3])
    mapping = {
        "hq parade": "HQ", "alpha parade": "Alpha", "a coy": "Alpha",
        "bravo parade": "Bravo", "b coy": "Bravo", "charlie parade": "Charlie",
        "c coy": "Charlie", "msc parade": "MSC", "msc coy": "MSC",
        "support coy": "Support", "support parade": "Support", "sp coy": "Support"
    }
    for key, val in mapping.items():
        if key in header: return val
    return None

def format_full_parade():
    date_str = datetime.now().strftime("%d %B %Y").lower()
    coy_summary = []
    total_reg, total_nsf = 0, 0

    for coy in DISPLAY_ORDER:
        data = parade_data[coy]
        if data:
            regs = sum(1 for p in data["personnel"] if not p['is_nsf'])
            nsfs = sum(1 for p in data["personnel"] if p['is_nsf'])
            total_reg += regs
            total_nsf += nsfs
            label = "SP" if coy == "Support" else coy
            coy_summary.append(f"{label} - {regs}/{nsfs}")
        else:
            label = "SP" if coy == "Support" else coy
            coy_summary.append(f"{label} - 0/0")

    msg = f"MBTC 2 Strength CAA {date_str}\n\n"
    msg += f"Total Strength - {total_reg + total_nsf} ({total_reg} Regulars / {total_nsf} NSFs)\n\n"
    msg += "Regulars/NSFs\n" + "\n".join(coy_summary) + "\n\nBreakdown\n"

    for coy in DISPLAY_ORDER:
        data = parade_data[coy]
        if data:
            total = len(data["personnel"])
            present = sum(1 for p in data["personnel"] if p['status'] == 'Present')
            msg += f"*{coy} Parade State for {date_str}*\n"
            msg += f"Current Strength: {present}/{total}\n\n"
            for idx, p in enumerate(data["personnel"], start=1):
                msg += f"{idx}. {p['text']}\n"
            if data["attached"]:
                msg += "\nAttached Personnel\n"
                for idx, a in enumerate(data["attached"], start=1):
                    msg += f"{idx}. {a['text']}\n"
            msg += "\n" + ("—" * 15) + "\n\n"
    return msg

# --- 3. TELEGRAM HANDLERS ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text: return
    coy = detect_company(text)

    if coy:
        parade_data[coy] = parse_parade_state(text, coy)
        sent_msg = await update.message.reply_text(f"✅ {coy} Parade State saved.")
        # Wait 5 seconds then delete confirmation to keep group clean
        await asyncio.sleep(5)
        await sent_msg.delete()

async def print_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(format_full_parade(), parse_mode="Markdown")

async def check_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_text = "📊 *Submission Status:*\n"
    for coy in DISPLAY_ORDER:
        icon = "✅" if parade_data[coy] else "❌"
        status_text += f"{icon} {coy}\n"
    await update.message.reply_text(status_text, parse_mode="Markdown")

async def clear_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global parade_data
    parade_data = {coy: None for coy in DISPLAY_ORDER}
    await update.message.reply_text("Data cleared for new day. 🧹")

# --- 4. MAIN ENTRY ---

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("print", print_report))
    app.add_handler(CommandHandler("status", check_status))
    app.add_handler(CommandHandler("clear", clear_data))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Bot is starting with Health Server on Port 8000...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()