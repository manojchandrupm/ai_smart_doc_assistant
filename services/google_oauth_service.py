import httpx
from urllib.parse import urlencode
from config import env

GOOGLE_AUTH_URL     = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL    = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

def get_google_auth_url(state: str = "") -> str:
    """Build the Google authorization URL to redirect the user to."""
    params = {
        "client_id":     env.GOOGLE_CLIENT_ID,
        "redirect_uri":  env.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope":         "openid email profile",  # urlencode handles spaces → %20/+
        "access_type":   "offline",
        "state":         state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_token(code: str) -> dict:
    """Exchange the authorization code for an access token."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code":          code,
                "client_id":     env.GOOGLE_CLIENT_ID,
                "client_secret": env.GOOGLE_CLIENT_SECRET,
                "redirect_uri":  env.GOOGLE_REDIRECT_URI,
                "grant_type":    "authorization_code",
            },
        )
        response.raise_for_status()
        return response.json()


async def get_google_user_info(access_token: str) -> dict:
    """Fetch the user's profile from Google using the access token."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        return response.json()
        # Returns: { "id": "...", "email": "...", "name": "...", "picture": "..." }
