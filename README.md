# Telegram Premium Shop Bot (Completo)

## Descripción
Bot de Telegram semiautomático para vender y regalar Telegram Premium.  
Incluye comandos, menús, IPN de PayPal y personalización con emojis.

## Comandos
- `/start`: Iniciar y mostrar menú de compra  
- `/help`: Mostrar comandos disponibles  
- `/miestado`: Ver tu historial de compras  
- `/comprobante`: Enviar comprobante de pago  

## Archivos
- `config.py`: Configuración de token, admins y métodos de pago.  
- `main.py`: Lógica del bot y servidor Flask para IPN.  
- `compras.json`: Historial de compras y comprobantes.  
- `requirements.txt`: Dependencias.  
- `README.md`: Este documento.

## Configuración
1. Edita `config.py` con tu TOKEN y datos de admins.  
2. Ajusta métodos de pago si es necesario.  
3. Configura en PayPal tu webhook/IPN apuntando a `/paypal-ipn`.

## Instalación
```bash
pip install python-telegram-bot flask requests
```

## Ejecución
```bash
python main.py
```
