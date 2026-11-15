"""Placeholder support contacts for demo brands."""

from app.db import connect, load_env

PLACEHOLDERS = {
    "kitchenaid": "KitchenAid brand support team (placeholder)",
    "nespresso": "Nespresso customer care team (placeholder)",
    "breville": "Breville consumer support team (placeholder)",
    "instant": "Instant Brands support team (placeholder)",
    "ninja": "Ninja consumer care team (placeholder)",
    "traeger": "Traeger customer support team (placeholder)",
    "delonghi": "De'Longhi support team (placeholder)",
    "vitamix": "Vitamix customer care (placeholder)",
    "lodge": "Lodge consumer support (placeholder)",
    "fellow": "Fellow support team (placeholder)",
    "caraway": "Caraway support team (placeholder)",
    "madein": "Made In customer team (placeholder)",
    "ourplace": "Our Place support team (placeholder)",
    "anova": "Anova culinary support (placeholder)",
    "meater": "Meater support team (placeholder)",
    "solostove": "Solo Stove support (placeholder)",
    "lamarzocco": "La Marzocco service team (placeholder)",
}

PLATFORMS = ("youtube", "instagram", "tiktok", "x", "reddit")


def main() -> None:
    load_env()
    with connect() as conn:
        with conn.cursor() as cur:
            for brand_id, contact in PLACEHOLDERS.items():
                cur.execute(
                    """
                    UPDATE brands
                    SET support_contact = %s,
                        reply_sla_hours = COALESCE(reply_sla_hours, 48)
                    WHERE id = %s
                    """,
                    (contact, brand_id),
                )
            for brand_id in PLACEHOLDERS:
                for platform in PLATFORMS:
                    cur.execute(
                        """
                        INSERT INTO brand_connections (brand_id, platform, status, note)
                        VALUES (%s, %s, 'pilot_pending', 'Connect in Phase 1.5 pilot onboarding')
                        ON CONFLICT (brand_id, platform) DO NOTHING
                        """,
                        (brand_id, platform),
                    )
        conn.commit()
    print("support contacts and connection stubs seeded")


if __name__ == "__main__":
    main()