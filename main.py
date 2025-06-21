import json
import logging
import os
from threading import Thread
from flask import Flask, request
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

import config

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# Asegurar que compras.json exista
if not os.path.isfile("compras.json"):
    with open("compras.json", "w") as f:
        json.dump([], f, indent=4)

# Flask para IPN de PayPal
app = Flask(__name__)

# Estados de la conversación
CHOOSING, SELECT_PLAN, SELECT_PAYMENT, WAIT_PROOF = range(4)

# Planes disponibles
PLANS = {
    "1 mes – 11 USD": ("1 mes", 11),
    "3 meses – 15 USD": ("3 meses", 15),
    "1 año – 27 USD": ("1 año", 27),
}

# Métodos de pago
PAY_METHODS = ["PayPal", "Zelle", "CUP", "Saldo móvil"]

def save_purchase(entry):
    with open("compras.json", "r+") as f:
        compras = json.load(f)
        compras.append(entry)
        f.seek(0)
        json.dump(compras, f, indent=4)

# ————————————————
# Handler para /start
# ————————————————
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    kb = [
        ["🛒 Comprar Premium", "🤝 Invitar amigos"],
        ["💁‍♂️ Soporte", "🔐 Panel Admin"]
    ]
    if user.id not in config.ADMINS:
        kb[1].remove("🔐 Panel Admin")
    markup = ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(
        f"👋 ¡Hola <b>{user.first_name}</b>!\n\n"
        "Este bot te permite comprar y regalar Telegram Premium.\n"
        "Elige una opción del menú:",
        parse_mode="HTML",
        reply_markup=markup,
    )
    return CHOOSING

# ————————————————
# Handler para /help
# ————————————————
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_markdown(
        "ℹ️ *Comandos disponibles*:\n"
        "/start – Volver al menú principal\n"
        "/help – Mostrar esta ayuda\n"
        "/miestado – Ver tu historial de compras\n"
        "/cancel – Cancelar la operación"
    )

# ————————————————
# Handler opción menú principal
# ————————————————
async def choice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user

    if text == "🛒 Comprar Premium":
        kb = [[p] for p in PLANS.keys()]
        kb.append(["⬅️ Volver al inicio"])
        markup = ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(
            "🎁 *Nuestros planes Premium*:\nSelecciona el que quieras comprar.",
            parse_mode="Markdown",
            reply_markup=markup,
        )
        return SELECT_PLAN

    if text == "🤝 Invitar amigos":
        link = f"https://t.me/{context.bot.username}?start={user.username}"
        await update.message.reply_text(f"📨 Invita a tus amigos: {link}")
        return CHOOSING

    if text == "💁‍♂️ Soporte":
        await update.message.reply_text(
            f"🛠️ Soporte: <a href=\"https://t.me/{config.SUPPORT_USERNAME}\">@{config.SUPPORT_USERNAME}</a>\n"
            "Estamos para ayudarte.",
            parse_mode="HTML"
        )
        return CHOOSING

    if text == "🔐 Panel Admin" and user.id in config.ADMINS:
        kb = [["Ver compras"], ["⬅️ Volver al inicio"]]
        markup = ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(
            "🔐 <b>Panel Administrativo</b>:\nElige una opción.",
            parse_mode="HTML",
            reply_markup=markup,
        )
        return SELECT_PLAN

    await update.message.reply_text("⚠️ Opción no válida, elige del menú.")
    return CHOOSING

# ————————————————
# Handler selección de plan
# ————————————————
async def plan_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "⬅️ Volver al inicio":
        return await start(update, context)

    if update.effective_user.id in config.ADMINS and text == "Ver compras":
        with open("compras.json") as f:
            compras = json.load(f)
        resumen = compras[-10:]
        msg = "🛍️ Últimas compras:\n"
        for c in resumen:
            msg += f"• {c.get('plan')} – {c.get('price')} USD – {c.get('payer_username','-')}\n"
        await update.message.reply_text(msg or "No hay compras.")
        return CHOOSING

    if text in PLANS:
        plan_label, price = PLANS[text]
        context.user_data["plan"] = plan_label
        context.user_data["price"] = price
        kb = [[m] for m in PAY_METHODS]
        kb.append(["⬅️ Volver a planes"])
        markup = ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(
            f"✅ Has elegido *{plan_label}* por *{price} USD*.\n\nSelecciona método de pago:",
            parse_mode="Markdown",
            reply_markup=markup,
        )
        return SELECT_PAYMENT

    await update.message.reply_text("⚠️ Selecciona un plan válido.")
    return SELECT_PLAN

# ————————————————
# Handler selección método de pago
# ————————————————
async def payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "⬅️ Volver a planes":
        return await choice_handler(update, context)

    if text in PAY_METHODS:
        method = text
        plan = context.user_data["plan"]
        price = context.user_data["price"]
        context.user_data["method"] = method

        # Construir texto de pago
        if method == "PayPal":
            link = config.generate_paypal_link(plan, price)
            pay_text = f"💳 PayPal: <a href=\"{link}\">Paga aquí</a>"
        elif method == "Zelle":
            pay_text = f"💲 Zelle: {config.ZELLE_NAME} – {config.ZELLE_NUMBER}"
        elif method == "CUP":
            pay_text = (
                f"🏦 CUP: {config.CUP_CARD}\n"
                f"1 USD = {config.CUP_RATE} CUP\n"
                f"Conf: {config.CONFIRM_NUMBER}"
            )
        else:
            pay_text = (
                f"📱 Saldo móvil: {config.MOBILE_NUMBER}\n"
                f"1 USD = {config.MOBILE_RATE} Saldo\n"
                f"Conf: {config.CONFIRM_NUMBER}"
            )

        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("📤 Enviar comprobante", callback_data="send_proof")]]
        )
        await update.message.reply_text(
            f"✅ <b>{plan}</b> – <b>{price} USD</b> via <b>{method}</b>\n\n"
            f"{pay_text}\n\n"
            "Cuando completes el pago, pulsa el botón de abajo.",
            parse_mode="HTML",
            reply_markup=kb,
            disable_web_page_preview=True,
        )
        return WAIT_PROOF

    await update.message.reply_text("⚠️ Elige un método válido.")
    return SELECT_PAYMENT

# ————————————————
# Handler inline para enviar comprobante
# ————————————————
async def send_proof_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("📤 Ahora envía tu comprobante (foto o documento).")
    return WAIT_PROOF

# ————————————————
# Handler recibo comprobante
# ————————————————
async def proof_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo or update.message.document:
        user = update.effective_user
        entry = {
            "txn_id": f"proof_{update.message.message_id}",
            "plan": context.user_data.get("plan"),
            "price": context.user_data.get("price"),
            "payer_username": user.username or str(user.id),
            "method": context.user_data.get("method"),
            "status": "proof_sent",
        }
        save_purchase(entry)
        admin_msg = (
            f"🛎️ *Nueva solicitud de pago*\n"
            f"👤 @{entry['payer_username']}\n"
            f"📦 {entry['plan']} – {entry['price']} USD\n"
            f"💳 Método: {entry['method']}"
        )
        for a in config.ADMINS:
            await context.bot.send_message(chat_id=a, text=admin_msg, parse_mode="Markdown")
        await update.message.reply_text("✅ Comprobante recibido. ¡Gracias! En breve confirmamos.")
        return ConversationHandler.END

    await update.message.reply_text("⚠️ Envía una foto o documento.")
    return WAIT_PROOF

# ————————————————
# Handler cancel
# ————————————————
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔙 Operación cancelada.",
        reply_markup=ReplyKeyboardMarkup([["/start"]], resize_keyboard=True)
    )
    return ConversationHandler.END

# ————————————————
# Endpoint IPN PayPal
# ————————————————
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
    for a in config.ADMINS:
        bot.send_message(chat_id=a, text=msg, parse_mode="Markdown")
    return "", 200

def run_flask():
    app.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    Thread(target=run_flask).start()

    app_bot = ApplicationBuilder().token(config.TOKEN).build()

    # Registrar /help antes del ConversationHandler
    app_bot.add_handler(CommandHandler("help", help_command))
    app_bot.add_handler(CommandHandler("miestado", choice_handler))

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING: [MessageHandler(filters.TEXT & ~filters.COMMAND, choice_handler)],
            SELECT_PLAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_handler)],
            SELECT_PAYMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, payment_handler)],
            WAIT_PROOF: [
                CallbackQueryHandler(send_proof_inline, pattern="send_proof"),
                MessageHandler(filters.PHOTO | filters.Document.ALL, proof_handler),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
    app_bot.add_handler(conv)
    app_bot.run_polling()
