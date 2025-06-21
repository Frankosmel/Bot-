import json
import logging
import os
from threading import Thread
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

import config

# Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Ensure compras.json exists
if not os.path.isfile('compras.json'):
    with open('compras.json', 'w') as f:
        json.dump([], f, indent=4)

# Flask app for PayPal IPN
app = Flask(__name__)

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_first = update.effective_user.first_name or ""
    text = (
        f"👋 ¡Hola {user_first}! Bienvenido a *Francho Shop Premium*! 🎉\n\n"
        "Aquí puedes comprar *Telegram Premium* de forma *segura* y *rápida*. ✨\n\n"
        "*Beneficios Premium*:\n"
        "• Subir archivos hasta 4GB\n"
        "• Reacciones exclusivas 💬\n"
        "• Insignia premium 🏅\n"
        "• Mayor velocidad 🚀\n"
        "• Stickers únicos 🌟\n\n"
        "Selecciona un plan para comenzar:"
    )
    keyboard = [
        [InlineKeyboardButton("1 mes – 11 USD", callback_data='1m')],
        [InlineKeyboardButton("3 meses – 15 USD", callback_data='3m')],
        [InlineKeyboardButton("1 año – 27 USD", callback_data='12m')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_markdown(text, reply_markup=reply_markup)

# /help command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "ℹ️ *Comandos disponibles*:
"
        "/start - Mostrar menú de compra
"
        "/comprobante - Enviar comprobante de pago
"
        "/miestado - Ver tu historial de compras
"
        "/help - Mostrar esta ayuda
"
    )
    await update.message.reply_markdown(text)

# /miestado command
async def estado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.username or str(update.effective_user.id)
    with open('compras.json', 'r') as f:
        compras = json.load(f)
    user_compras = [c for c in compras if c.get('payer_username') == user or c.get('payer') == user]
    if not user_compras:
        await update.message.reply_text("📭 No tienes compras registradas aún.")
        return
    lines = ["📑 *Tu historial de compras*:"]
    for c in user_compras:
        lines.append(f"• {c.get('plan')} - {c.get('price')} USD - {c.get('txn_id')}")
    text = "\n".join(lines)
    await update.message.reply_markdown(text)

# Button handler
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_map = {'1m': ('1 mes', 11), '3m': ('3 meses', 15), '12m': ('1 año', 27)}
    plan_label, price = plan_map.get(query.data, ('Desconocido', 0))
    link = config.generate_paypal_link(plan_label, price)
    text = (
        f"✅ Has seleccionado *{plan_label} – {price} USD*\n\n"
        f"💳 *Paga por PayPal aquí*:\n{link}\n\n"
        f"📲 *Zelle*: {config.ZELLE_NAME} – {config.ZELLE_NUMBER}\n"
        f"🏦 *CUP*: {config.CUP_CARD} (1 USD = {config.CUP_RATE} CUP)\n"
        f"🔒 *Confirmación obligatoria*: {config.CONFIRM_NUMBER}\n"
        f"📱 *Saldo móvil*: {config.MOBILE_NUMBER} (1 USD = {config.MOBILE_RATE} Saldo)\n\n"
        f"Cuando termines, usa /comprobante para enviar tu comprobante."
    )
    await query.message.reply_markdown(text)

# /comprobante command and proof handler
async def comprobante(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📤 Por favor, envía aquí la imagen o documento de tu comprobante de pago."
    )

async def proof_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo or update.message.document:
        # Save proof info
        filename = f"proof_{update.message.from_user.id}_{update.message.message_id}"
        # (Skipping file download for brevity)
        # Record in compras.json as proof pending
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
        # Notify admins
        for admin in config.ADMINS:
            await context.bot.send_message(
                chat_id=admin,
                text=(
                    f"🛎️ *Nuevo comprobante recibido*\n"
                    f"👤 Usuario: @{update.message.from_user.username}\n"
                    f"Envía tu regalo desde @PremiumBot."
                ),
                parse_mode='Markdown'
            )
        await update.message.reply_text("✅ Comprobante recibido. En breve recibirás tu Premium.")

# PayPal IPN endpoint
@app.route('/paypal-ipn', methods=['POST'])
def paypal_ipn():
    data = request.form.to_dict()
    # In production, verify IPN here
    # Save purchase
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
    # Notify admins
    from telegram import Bot
    bot = Bot(token=config.TOKEN)
    msg = (
        f"🛍️ *Nueva compra registrada*\n"
        f"Plan: {data.get('item_name')}\n"
        f"Precio: {data.get('mc_gross')} USD\n"
        f"Payer: {data.get('payer_email')}"
    )
    for admin in config.ADMINS:
        bot.send_message(chat_id=admin, text=msg, parse_mode='Markdown')
    return '', 200

def run_flask():
    app.run(host='0.0.0.0', port=5000)

if __name__ == '__main__':
    Thread(target=run_flask).start()
    bot_app = ApplicationBuilder().token(config.TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("help", help_command))
    bot_app.add_handler(CommandHandler("miestado", estado))
    bot_app.add_handler(CallbackQueryHandler(button_handler))
    bot_app.add_handler(CommandHandler("comprobante", comprobante))
    bot_app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, proof_handler))
    bot_app.run_polling()
