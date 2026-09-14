from html import escape


TRUSTED_AVATAR_PREFIXES = (
    "/static/avatars/",
    "https://cdn.example.com/avatars/",
)


def render_profile_card(display_name: str, avatar_url: str) -> str:
    """Render a user profile card.

    Bug: the URL is prefix-checked but not escaped before being placed inside an
    HTML attribute.
    """
    name = escape(display_name, quote=True)
    avatar = (
        avatar_url
        if avatar_url.startswith(TRUSTED_AVATAR_PREFIXES)
        else "/static/avatars/default.png"
    )
    return f'<article class="profile"><img src="{avatar}" alt="{name}"><span>{name}</span></article>'
