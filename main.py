import json
import logging
import os
from threading import Thread
from flask import Flask, request
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

import config

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Asegurar que compras.json exista
if not os.path.isfile('compras.json'):
    with open('compras.json', 'w') as f:
        json.dump([], f, indent=4)

# Flask app para PayPal IPN
app = Flask(__name__)

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_first = update.effective_user.first_name or ""
    text = (
        f"👋 ¡Hola {user_first}! Bienvenido a <b>Francho Shop Premium</b>! 🎉\n\n"
        "Selecciona un plan para comenzar:"
    )
    # Teclado inferior con las opciones de plan
    reply_keyboard = [
        ["1 mes – 11 USD"],
        ["3 meses – 15 USD"],
        ["1 año – 27 USD"],
    ]
    markup = ReplyKeyboardMarkup(
        reply_keyboard,
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=markup)

# /help command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "ℹ️ <b>Comandos disponibles</b>:\n"
        "/start – Mostrar menú de compra\n"
        "/comprobante – Enviar comprobante de pago\n"
        "/miestado – Ver tu historial de compras\n"
        "/help – Mostrar esta ayuda\n"
    )
    await update.message.reply_text(text, parse_mode="HTML")

# /miestado command
async def estado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.username or str(update.effective_user.id)
    with open('compras.json', 'r') as f:
        compras = json.load(f)
    user_compras = [
        c for c in compras
        if c.get('payer_username') == user or c.get('payer') == user
    ]
    if not user_compras:
        await update.message.reply_text("📭 No tienes compras registradas aún.")
        return
    lines = ["📑 <b>Tu historial de compras</b>:"]
    for c in user_compras:
        lines.append(f"• {c.get('plan')} - {c.get('price')} USD - {c.get('txn_id')}")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

# Handler de texto para selección de plan
async def plan_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    m = {
        "1 mes – 11 USD": ("1 mes", 11),
        "3 meses – 15 USD": ("3 meses", 15),
        "1 año – 27 USD": ("1 año", 27),
    }
    plan_label, price = m.get(text, ("Desconocido", 0))
    link = config.generate_paypal_link(plan_label, price)
    resp = (
        f"✅ Has seleccionado <b>{plan_label} – {price} USD</b>\n\n"
        f"💳 Paga por PayPal aquí: <a href=\"{link}\">Click para pagar</a>\n\n"
        f"📲 <b>Zelle</b>: {config.ZELLE_NAME} – {config.ZELLE_NUMBER}\n"
        f"🏦 <b>CUP</b>: {config.CUP_CARD} (1 USD = {config.CUP_RATE} CUP)\n"
        f"🔒 <b>Confirmación obligatoria</b>: {config.CONFIRM_NUMBER}\n"
        f"📱 <b>Saldo móvil</b>: {config.MOBILE_NUMBER} (1 USD = {config.MOBILE_RATE} Saldo)\n\n"
        "Cuando termines, pulsa el botón de abajo para enviar tu comprobante."
    )
    # Botón inline para enviar comprobante
    inline_kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("📤 Enviar comprobante", callback_data="send_proof")]]
    )
    await update.message.reply_text(
        resp,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=inline_kb
    )

# Handler inline para el botón de comprobante
async def send_proof_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "📤 Por favor, envía ahora la imagen o documento de tu comprobante de pago."
    )

# /comprobante command (alternativo)
async def comprobante(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📤 Por favor, envía aquí la imagen o documento de tu comprobante de pago."
    )

# Handler de recibo de comprobante (fotos o documentos)
async def proof_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo or update.message.document:
        with open('compras.json', 'r+') as f:
            compras = json.load(f)
            compras.append({
                'txn_id': f"proof_{update.message.message_id}",
                'plan': 'comprobante',
                'price': '',
                'payer_username': update.message.from_user.username,
                'status': 'proof_sent'
            })
            f.seek(0)
            json.dump(compras, f, indent=4)
        # Notificar a admins
        for admin in config.ADMINS:
            await context.bot.send_message(
                chat_id=admin,
                text=(
                    "🛎️ <b>Nuevo comprobante recibido</b>\n"
                    f"👤 Usuario: @{update.message.from_user.username}\n"
                    "Envía tu regalo desde @PremiumBot."
                ),
                parse_mode="HTML"
            )
        await update.message.reply_text("✅ Comprobante recibido. En breve recibirás tu Premium.")

# Endpoint de PayPal IPN
@app.route('/paypal-ipn', methods=['POST'])
def paypal_ipn():
    data = request.form.to_dict()
    with open('compras.json', 'r+') as f:
        compras = json.load(f)
        compras.append({
            'txn_id': data.get('txn_id'),
            'plan': data.get('item_name'),
            'price': data.get('mc_gross'),
            'payer': data.get('payer_email'),
            'payer_username': data.get('custom', '')
        })
        f.seek(0)
        json.dump(compras, f, indent=4)
    # Notificar a admins
    from telegram import Bot
    bot = Bot(token=config.TOKEN)
    msg = (
        "🛍️ <b>Nueva compra registrada</b>\n"
        f"Plan: {data.get('item_name')}\n"
        f"Precio: {data.get('mc_gross')} USD\n"
        f"Payer: {data.get('payer_email')}"
    )
    for admin in config.ADMINS:
        bot.send_message(chat_id=admin, text=msg, parse_mode="HTML")
    return '', 200

def run_flask():
    app.run(host='0.0.0.0', port=5000)

if __name__ == '__main__':
    # Iniciar Flask en hilo separado
    Thread(target=run_flask).start()

    # Construir y arrancar el bot
    bot_app = ApplicationBuilder().token(config.TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("help", help_command))
    bot_app.add_handler(CommandHandler("miestado", estado))
    # Manejar selección de plan con teclado inferior
    bot_app.add_handler(MessageHandler(
        filters.Regex(r"^(1 mes – 11 USD|3 meses – 15 USD|1 año – 27 USD)$"),
        plan_text_handler
    ))
    # Botón inline para comprobante
    bot_app.add_handler(CallbackQueryHandler(send_proof_inline, pattern="send_proof"))
    # Comando alternativo para comprobante
    bot_app.add_handler(CommandHandler("comprobante", comprobante))
    # Handler para fotos/documentos como comprobante
    bot_app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, proof_handler))
    bot_app.run_polling()
