from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import re
from datetime import datetime


TOKEN = "8486319366:AAHCzqbC9W-iQPi6iByMRc9ysS0rQb7m6Gg"

# Memory for all parade data
parade_data = {
    "date": None,
    "HQ": None,
    "Alpha": None,
    "Bravo": None,
    "Charlie": None,
    "Support": None,
    "MSC": None
}

company_strengths = {
    "HQ": 17,
    "Alpha": 7,
    "Bravo": 7,
    "Charlie": 6,
    "Support": 10,
    "MSC": 5
}


# --- 1️⃣ Parse individual parade states ---
def parse_parade_state(text):
    # Split text into lines and strip whitespace
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # --- Remove lines containing 'Kranji Camp' ---
    lines = [l for l in lines if "kranji camp" not in l.lower()]

    # --- Remove lines that look like a date (DD MMM YY) ---
    date_pattern = re.compile(r'\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4}')
    lines = [l for l in lines if not date_pattern.search(l)]

    parsed = {"date": None, "personnel": [], "attached": []}

    # --- Detect date from remaining lines (optional) ---
    for l in lines:
        m1 = re.search(r"(\d{1,2}\s*[A-Z]{3}\s*\d{2,4})", l, re.IGNORECASE)
        if m1:
            parsed["date"] = m1.group(1).upper()
            break

        m2 = re.match(r'^(\d{2})(\d{2})(\d{2})$', l)
        if m2:
            day, month, year = m2.groups()
            try:
                dt = datetime.strptime(f"{day}{month}{year}", "%d%m%y")
                parsed["date"] = dt.strftime("%d %b %y").upper()
                break
            except ValueError:
                continue

    # --- Handle "Attached Personnel" split safely ---
    attached_idx = next((i for i, l in enumerate(lines) if "attached" in l.lower()), None)

    # ✅ Skip the first line if it’s clearly a header (e.g. “HQ Parade State”)
    if lines and "parade state" in lines[0].lower():
        content_lines = lines[1:]
    else:
        content_lines = lines

    if attached_idx is not None:
        adjusted_idx = attached_idx - (1 if lines and "parade state" in lines[0].lower() else 0)
        main_lines = content_lines[:adjusted_idx]
        attached_lines = content_lines[adjusted_idx + 1:]
    else:
        main_lines = content_lines
        attached_lines = []

    # --- Parse lines into personnel dicts ---
    def parse_lines(line_list):
        res = []
        for l in line_list:
            # Remove numbering like "1." or "1. "
            l = re.sub(r'^\d+\.\s*', '', l)

            # Detect status
            if '✅' in l:
                status = 'Present'
            elif '❌' in l:
                status = 'Absent'
            else:
                status = 'Unknown'

            # ✅ Special formatting for Support Coy only
            if "support" in text.lower():
                remark_match = re.search(r'\((.*?)\)', l)
                remark = f"({remark_match.group(1)})" if remark_match else ""
                name_part = re.sub(r'✅|❌|\(.*?\)', '', l).strip()

                if status == 'Present':
                    formatted_text = f"{name_part} ✅ {remark}".strip()
                elif status == 'Absent':
                    formatted_text = f"{name_part} ❌ {remark}".strip()
                else:
                    formatted_text = name_part
                res.append({'text': formatted_text, 'status': status})
            else:
                res.append({'text': l, 'status': status})
        return res

    parsed["personnel"] = parse_lines(main_lines)
    parsed["attached"] = parse_lines(attached_lines)

    return parsed


# --- 2️⃣ Detect which company sent it ---
def detect_company(text):
    text_low = text.lower()
    # ✅ Look only at the header area (first 2 lines)
    header = "\n".join(text_low.splitlines()[:2])

    if header.startswith("hq parade"):
        return "HQ"
    elif header.startswith("alpha parade") or header.startswith("a coy"):
        return "Alpha"
    elif header.startswith("bravo parade") or header.startswith("b coy"):
        return "Bravo"
    elif header.startswith("charlie parade") or header.startswith("c coy"):
        return "Charlie"
    elif "support coy parade" in header or header.startswith("support parade") or "sp coy" in header:
        return "Support"
    elif header.startswith("msc parade") or "msc coy" in header:
        return "MSC"
    return None


# --- 3️⃣ Format the entire MBTC 2 message ---
def format_full_parade():
    date = datetime.now().strftime("%d %B %Y")
    msg = f"MBTC 2 Strength CAA {date}\n\n"
    msg += "Total Strength - 51 (47 Regulars / 4 NSFs)\n\n"
    msg += "Regulars/NSFs\nHQ - 12/4\nA Coy - 8/0\nB Coy - 6/0\nC Coy - 5/0\nSP Coy - 11/0\nMSC - 5/0\n\n"
    msg += "Breakdown\n"

    for coy in ["HQ", "Alpha", "Bravo", "Charlie", "MSC", "Support"]:
        section = parade_data[coy]
        if section:
            msg += f"*{coy} Parade State for {date}*\n\n"

            # Numbered personnel
            for idx, p in enumerate(section["personnel"], start=1):
                msg += f"{idx}. {p['text']}\n"

            # Attached personnel
            if section["attached"]:
                msg += "\nAttached Personnel\n"
                for idx, a in enumerate(section["attached"], start=1):
                    msg += f"{idx}. {a['text']}\n"

        msg += "\n"

    return msg


# --- 4️⃣ Telegram Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Parade Bot Active ✅\nSend your coy parade states here.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    coy = detect_company(text)

    if coy:
        parsed = parse_parade_state(text)
        parade_data[coy] = parsed
        parade_data["date"] = parsed["date"]
        msg = format_full_parade()
        await update.message.reply_text(msg)
    else:
        await update.message.reply_text(
            "Not recognised. Please start with ‘HQ Parade State’, ‘Alpha Parade State’, etc."
        )


def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()
