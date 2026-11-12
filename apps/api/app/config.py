import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    paypal_client_id = os.getenv("PAYPAL_CLIENT_ID", "")
    paypal_client_secret = os.getenv("PAYPAL_CLIENT_SECRET", "")
    paypal_environment = os.getenv("PAYPAL_ENVIRONMENT", "sandbox").lower()
    # Must be a currency that the Sandbox business/payee account can receive.
    paypal_currency = os.getenv("PAYPAL_CURRENCY", "USD").upper()
    frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")

    @property
    def paypal_base_url(self) -> str:
        return "https://api-m.paypal.com" if self.paypal_environment == "live" else "https://api-m.sandbox.paypal.com"

    @property
    def paypal_configured(self) -> bool:
        return bool(self.paypal_client_id and self.paypal_client_secret)


settings = Settings()

