TOKEN = "7996381032:AAHGXxjLHdPp1n77RomiRZQO1L0sAzPJIyo"
ADMINS = [1383931339, 7907625643]
# Usuario de soporte para el comando “Soporte”
SUPPORT_USERNAME = "frankosme1"
# PayPal Configuration
PAYPAL_BUSINESS = "Paypalfrancho@gmail.com"
PAYPAL_RETURN_URL = "https://t.me/micuenta_ff_id_bot"
PAYPAL_CANCEL_URL = "https://t.me/micuenta_ff_id_bot"

# Payment Methods Configuration
ZELLE_NAME = "Daikel Gonzalez Quintero"
ZELLE_NUMBER = "+1 (708) 768-1132"

CUP_CARD = "9204 1299 7691 8161"
CUP_RATE = 260  # 1 USD = 260 CUP
MOBILE_NUMBER = "56246700"
MOBILE_RATE = 300  # 1 USD = 300 saldo
CONFIRM_NUMBER = "56246700"

def generate_paypal_link(plan: str, price: float) -> str:
    return (
        f"https://www.paypal.com/cgi-bin/webscr?cmd=_xclick"
        f"&business={PAYPAL_BUSINESS}"
        f"&item_name={plan}"
        f"&amount={price}"
        f"&currency_code=USD"
        f"&no_shipping=1"
        f"&return={PAYPAL_RETURN_URL}"
        f"&cancel_return={PAYPAL_CANCEL_URL}"
    )
