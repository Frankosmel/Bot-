import json
import logging
import os
from math import ceil
from threading import Thread
from flask import Flask, request
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
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

# Datos de los planes
PLANS = [
    ("1 mes – 11 USD", "1m", 11),
    ("3 meses – 15 USD", "3m", 15),
    ("1 año – 27 USD", "12m", 27),
]
PAGE_SIZE = 2
TOTAL_PAGES = ceil(len(PLANS) / PAGE_SIZE)

# Flask app para PayPal IPN
app = Flask(__name__)

def build_plans_keyboard(page: int):
    """Construye el inline keyboard para la página dada."""
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    buttons = []
    for label, data, _ in PLANS[start:end]:
        buttons.append([InlineKeyboardButton(label, callback_data=f"plan_{data}")])
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"page_{page-1}"))
    if page < TOTAL_PAGES:
        nav.append(InlineKeyboardButton("Siguiente ➡️", callback_data=f"page_{page+1}"))
    buttons.append(nav)
    return InlineKeyboardMarkup(buttons)

async def show_plans(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 1):
    """Envía o edita el menú de planes en la página solicitada."""
    text = (
        "🛍️ *Nuestros planes de Telegram Premium* 🛍️\n\n"
        "Navega entre las páginas para ver todos los planes disponibles. 👇"
    )
    markup = build_plans_keyboard(page)
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode="Markdown", reply_markup=markup
        )
        await update.callback_query.answer()
    else:
        await update.message.reply_markdown(text, reply_markup=markup)

# Comandos de bot
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_plans(update, context, page=1)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "ℹ️ *Comandos disponibles*:\n"
        "/start – Ver planes y precios\n"
        "/miestado – Ver tu historial de compras\n"
        "/help – Mostrar esta ayuda\n"
    )
    await update.message.reply_markdown(text)

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
    lines = ["📑 *Tu historial de compras*:"]
    for c in user_compras:
        lines.append(f"• {c.get('plan')} - {c.get('price')} USD - {c.get('txn_id')}")
    await update.message.reply_markdown("\n".join(lines))

# Handler de callback de paginación
async def pagination_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    page = int(query.data.split("_")[1])
    await show_plans(update, context, page=page)

# Handler de selección de plan
async def plan_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, data = query.data.split("_")
    # Buscar plan
    plan_label, _, price = next(p for p in PLANS if p[1] == data)
    link = config.generate_paypal_link(plan_label, price)
    text = (
        f"✅ Has seleccionado *{plan_label}* por *{price} USD*.\n\n"
        f"💳 *Paga con PayPal*:\n[Haz clic aquí]({link})\n\n"
        f"📲 *Zelle*: {config.ZELLE_NAME} – {config.ZELLE_NUMBER}\n"
        f"🏦 *CUP*: {config.CUP_CARD} (1 USD = {config.CUP_RATE} CUP)\n"
        f"🔒 *Confirmación obligatoria*: {config.CONFIRM_NUMBER}\n"
        f"📱 *Saldo móvil*: {config.MOBILE_NUMBER} (1 USD = {config.MOBILE_RATE} Saldo)\n\n"
        "Cuando completes el pago, pulsa el botón de abajo para enviar tu comprobante."
    )
    inline_kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("📤 Enviar comprobante", callback_data="send_proof")]]
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=inline_kb)

# Handler inline para enviar comprobante
async def send_proof_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "📤 Por favor, envía ahora la imagen o documento de tu comprobante de pago."
    )

# Handler de recibo de comprobante
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
                    "🛎️ *Nuevo comprobante recibido*\n"
                    f"👤 Usuario: @{update.message.from_user.username}\n"
                    "Envía tu regalo desde @PremiumBot."
                ),
                parse_mode="Markdown"
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
        "🛍️ *Nueva compra registrada*\n"
        f"Plan: {data.get('item_name')}\n"
        f"Precio: {data.get('mc_gross')} USD\n"
        f"Payer: {data.get('payer_email')}"
    )
    for admin in config.ADMINS:
        bot.send_message(chat_id=admin, text=msg, parse_mode="Markdown")
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
    bot_app.add_handler(CallbackQueryHandler(pagination_handler, pattern=r"^page_"))
    bot_app.add_handler(CallbackQueryHandler(plan_handler, pattern=r"^plan_"))
    bot_app.add_handler(CallbackQueryHandler(send_proof_inline, pattern="send_proof"))
    bot_app.add_handler(CommandHandler("comprobante", lambda u, c: proof_handler(u, c)))
    bot_app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, proof_handler))
    bot_app.run_polling()
