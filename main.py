import json
import logging
import os
from threading import Thread
from flask import Flask, request
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

import config

# Logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    level=logging.INFO)

# Archivos de historial y settings
HISTORY_FILE = "compras.json"
SETTINGS_FILE = "settings.json"

# Asegurar archivos
if not os.path.isfile(HISTORY_FILE):
    with open(HISTORY_FILE, "w") as f:
        json.dump([], f, indent=4)

def load_settings():
    if not os.path.isfile(SETTINGS_FILE):
        default = {
            "admins": config.ADMINS.copy(),
            "cup_rate": config.CUP_RATE,
            "mobile_rate": config.MOBILE_RATE,
            "support_username": config.SUPPORT_USERNAME
        }
        with open(SETTINGS_FILE, "w") as f:
            json.dump(default, f, indent=4)
    with open(SETTINGS_FILE) as f:
        return json.load(f)

def save_settings(s):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(s, f, indent=4)

settings = load_settings()
ADMINS = settings["admins"]
CUP_RATE = settings["cup_rate"]
MOBILE_RATE = settings["mobile_rate"]
SUPPORT_USERNAME = settings["support_username"]

def save_purchase(entry):
    with open(HISTORY_FILE, "r+") as f:
        data = json.load(f)
        data.append(entry)
        f.seek(0)
        json.dump(data, f, indent=4)

app = Flask(__name__)

# Conversation states
(CHOOSING,
 SELECT_PLAN,
 SELECT_PAYMENT,
 WAIT_PROOF,
 ADMIN_CUP,
 ADMIN_MOBILE,
 ADMIN_ADD,
 ADMIN_REMOVE) = range(8)

# Planes y métodos
PLANS = {
    "1 mes – 11 USD": ("1 mes", 11),
    "3 meses – 15 USD": ("3 meses", 15),
    "1 año – 27 USD": ("1 año", 27),
}
PAY_METHODS = ["PayPal", "Zelle", "CUP", "Saldo móvil"]

# ————————————— Handler /start —————————————
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    kb = [["🛒 Comprar Premium", "🤝 Invitar amigos"],
          ["💁‍♂️ Soporte"]]
    if user.id in ADMINS:
        kb[1].append("🔐 Panel Admin")
    markup = ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(
        f"👋 ¡Hola <b>{user.first_name}</b>!\n"
        "Bienvenido a Francho Shop Premium.\n"
        "Selecciona una opción:",
        parse_mode="HTML",
        reply_markup=markup
    )
    return CHOOSING

# ————————————— Handler /help —————————————
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_markdown(
        "ℹ️ *Comandos disponibles*:\n"
        "/start – Menú principal\n"
        "/help – Ayuda\n"
        "/cancel – Cancelar"
    )

# ————————————— Handler menú principal —————————————
async def choice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user

    if text == "🛒 Comprar Premium":
        kb = [[p] for p in PLANS.keys()] + [["⬅️ Volver"]]
        await update.message.reply_markdown(
            "🎁 *Planes Premium*: elige uno",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
        )
        return SELECT_PLAN

    if text == "🤝 Invitar amigos":
        link = f"https://t.me/{context.bot.username}?start={user.username}"
        await update.message.reply_text(f"📨 Invita con este enlace:\n{link}")
        return CHOOSING

    if text == "💁‍♂️ Soporte":
        await update.message.reply_text(
            f"🛠️ Soporte: <a href=\"https://t.me/{SUPPORT_USERNAME}\">@{SUPPORT_USERNAME}</a>",
            parse_mode="HTML"
        )
        return CHOOSING

    if text == "🔐 Panel Admin" and user.id in ADMINS:
        kb = [
            ["Ver compras", "Ver total compr."],
            ["Tasa CUP", "Tasa Saldo"],
            ["Agregar admin", "Eliminar admin"],
            ["⬅️ Volver"]
        ]
        await update.message.reply_markdown(
            "🔐 *Panel Admin*: elige acción",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
        )
        return SELECT_PLAN

    await update.message.reply_text("⚠️ Opción no válida.")
    return CHOOSING

# ————————————— Handler SELECT_PLAN —————————————
async def plan_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user

    # Volver al inicio
    if text == "⬅️ Volver":
        return await start(update, context)

    # Admin: ver compras
    if user.id in ADMINS and text == "Ver compras":
        with open(HISTORY_FILE) as f:
            compras = json.load(f)
        last = compras[-10:]
        msg = "\n".join(
            f"• {c['plan']} – {c['price']} USD – @{c.get('payer_username','-')}"
            for c in last
        ) or "No hay compras."
        await update.message.reply_text(msg)
        return CHOOSING

    # Admin: ver total vendido
    if user.id in ADMINS and text == "Ver total compr.":
        with open(HISTORY_FILE) as f:
            compras = json.load(f)
        total = sum(float(c.get("price", 0)) 
                    for c in compras if c.get("status")=="completed")
        await update.message.reply_text(f"📊 Total vend.: {total} USD")
        return CHOOSING

    # Admin: modificar tasa CUP
    if user.id in ADMINS and text == "Tasa CUP":
        await update.message.reply_text("🌟 Ingresa nueva tasa de CUP (CUP por USD):",
                                        reply_markup=ReplyKeyboardRemove())
        return ADMIN_CUP

    # Admin: modificar tasa móvil
    if user.id in ADMINS and text == "Tasa Saldo":
        await update.message.reply_text("🌟 Ingresa nueva tasa de Saldo móvil (Saldo por USD):",
                                        reply_markup=ReplyKeyboardRemove())
        return ADMIN_MOBILE

    # Admin: agregar admin
    if user.id in ADMINS and text == "Agregar admin":
        await update.message.reply_text("🌟 Envía el ID numérico del nuevo admin:",
                                        reply_markup=ReplyKeyboardRemove())
        return ADMIN_ADD

    # Admin: eliminar admin
    if user.id in ADMINS and text == "Eliminar admin":
        await update.message.reply_text("🌟 Envía el ID numérico del admin a eliminar:",
                                        reply_markup=ReplyKeyboardRemove())
        return ADMIN_REMOVE

    # Flujo usuario normal: plan
    if text in PLANS:
        plan_label, price = PLANS[text]
        context.user_data["plan"], context.user_data["price"] = plan_label, price
        kb = [[m] for m in PAY_METHODS] + [["🚫 Cancelar"]]
        await update.message.reply_markdown(
            f"✅ Plan: *{plan_label}* – *{price} USD*\n"
            "Elige método:",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
        )
        return SELECT_PAYMENT

    await update.message.reply_text("⚠️ Selecciona un plan válido.")
    return SELECT_PLAN

# ————————————— Handler SELECT_PAYMENT —————————————
async def payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🚫 Cancelar":
        await update.message.reply_text("❌ Operación cancelada.",
                                        reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    method = text
    if method in PAY_METHODS:
        plan = context.user_data["plan"]
        price = context.user_data["price"]
        context.user_data["method"] = method

        if method == "PayPal":
            link = config.generate_paypal_link(plan, price)
            pay_text = f"💳 <a href=\"{link}\">Paga con PayPal</a>"
        elif method == "Zelle":
            pay_text = f"💲 Zelle: {config.ZELLE_NAME} – {config.ZELLE_NUMBER}"
        elif method == "CUP":
            pay_text = (
                f"🏦 CUP: {config.CUP_CARD}\n"
                f"1 USD = {CUP_RATE} CUP\n"
                f"Conf: {config.CONFIRM_NUMBER}"
            )
        else:
            pay_text = (
                f"📱 Saldo móvil: {config.MOBILE_NUMBER}\n"
                f"1 USD = {MOBILE_RATE} Saldo\n"
                f"Conf: {config.CONFIRM_NUMBER}"
            )

        kb = [["📤 Enviar comprobante"], ["🚫 Cancelar"]]
        await update.message.reply_text(
            f"{pay_text}\n\n"
            "Cuando pagues, pulsa el botón:",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True),
            disable_web_page_preview=True
        )
        return WAIT_PROOF

    await update.message.reply_text("⚠️ Método no válido.")
    return SELECT_PAYMENT

# ————————————— Handler WAIT_PROOF —————————————
async def proof_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🚫 Cancelar":
        await update.message.reply_text("❌ Operación cancelada.",
                                        reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    if update.message.photo or update.message.document:
        u = update.effective_user
        entry = {
            "txn_id": f"proof_{update.message.message_id}",
            "plan": context.user_data["plan"],
            "price": context.user_data["price"],
            "payer_username": u.username or str(u.id),
            "method": context.user_data["method"],
            "status": "proof_sent",
        }
        save_purchase(entry)
        # Notificar admins
        msg = (
            f"🛎️ *Nueva solicitud*\n"
            f"👤 @{entry['payer_username']}\n"
            f"📦 {entry['plan']} – {entry['price']} USD\n"
            f"💳 {entry['method']}"
        )
        for a in ADMINS:
            await context.bot.send_message(chat_id=a, text=msg, parse_mode="Markdown")
        # Confirmar al usuario
        await update.message.reply_text("✅ Recibido, en breve confirmamos.",
                                        reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    await update.message.reply_text("⚠️ Envía foto o doc, o pulsa '🚫 Cancelar'.")
    return WAIT_PROOF

# ————————————— Handlers ADMIN —————————————
async def set_cup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        rate = float(update.message.text)
        settings["cup_rate"] = rate
        save_settings(settings)
        global CUP_RATE
        CUP_RATE = rate
        await update.message.reply_text(f"✅ Tasa CUP actualizada a {rate}.")
    except:
        await update.message.reply_text("⚠️ Valor inválido. Ingresa número:")
        return ADMIN_CUP
    return CHOOSING

async def set_mobile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        rate = float(update.message.text)
        settings["mobile_rate"] = rate
        save_settings(settings)
        global MOBILE_RATE
        MOBILE_RATE = rate
        await update.message.reply_text(f"✅ Tasa saldo actualizada a {rate}.")
    except:
        await update.message.reply_text("⚠️ Valor inválido. Ingresa número:")
        return ADMIN_MOBILE
    return CHOOSING

async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        new_id = int(update.message.text)
        if new_id not in settings["admins"]:
            settings["admins"].append(new_id)
            save_settings(settings)
            global ADMINS
            ADMINS = settings["admins"]
            await update.message.reply_text(f"✅ Admin agregado: {new_id}")
        else:
            await update.message.reply_text("⚠️ Ya es admin.")
    except:
        await update.message.reply_text("⚠️ Envía ID numérico:")
        return ADMIN_ADD
    return CHOOSING

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        rem = int(update.message.text)
        if rem in settings["admins"]:
            settings["admins"].remove(rem)
            save_settings(settings)
            global ADMINS
            ADMINS = settings["admins"]
            await update.message.reply_text(f"✅ Admin eliminado: {rem}")
        else:
            await update.message.reply_text("⚠️ No existe.")
    except:
        await update.message.reply_text("⚠️ Envía ID numérico:")
        return ADMIN_REMOVE
    return CHOOSING

# ————————————— Handler cancel —————————————
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelado.",
                                    reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# ————————————— IPN PayPal —————————————
@app.route("/paypal-ipn", methods=["POST"])
def paypal_ipn():
    data = request.form.to_dict()
    entry = {
        "txn_id": data.get("txn_id"),
        "plan": data.get("item_name"),
        "price": data.get("mc_gross"),
        "payer": data.get("payer_email"),
        "status": "completed",
    }
    save_purchase(entry)
    from telegram import Bot
    bot = Bot(token=config.TOKEN)
    msg = (
        f"🛍️ *Compra confirmada*\n"
        f"📦 {entry['plan']} – {entry['price']} USD\n"
        f"📧 {entry['payer']}"
    )
    for a in ADMINS:
        bot.send_message(chat_id=a, text=msg, parse_mode="Markdown")
    return "", 200

def run_flask():
    app.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    Thread(target=run_flask).start()
    bot = ApplicationBuilder().token(config.TOKEN).build()

    # Handlers básicos
    bot.add_handler(CommandHandler("help", help_command))

    # Conversation
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING: [MessageHandler(filters.TEXT & ~filters.COMMAND, choice_handler)],
            SELECT_PLAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_handler)],
            SELECT_PAYMENT:[MessageHandler(filters.TEXT & ~filters.COMMAND, payment_handler)],
            WAIT_PROOF:   [MessageHandler(filters.PHOTO | filters.Document.ALL, proof_handler)],
            ADMIN_CUP:    [MessageHandler(filters.TEXT & ~filters.COMMAND, set_cup)],
            ADMIN_MOBILE:[MessageHandler(filters.TEXT & ~filters.COMMAND, set_mobile)],
            ADMIN_ADD:    [MessageHandler(filters.TEXT & ~filters.COMMAND, add_admin)],
            ADMIN_REMOVE:[MessageHandler(filters.TEXT & ~filters.COMMAND, remove_admin)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )
    bot.add_handler(conv)
    bot.run_polling()
