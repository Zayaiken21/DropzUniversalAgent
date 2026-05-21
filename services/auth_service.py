from database.db import get_connection


def login_user(email, password):

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT,
            password TEXT
        )
        """
    )

    conn.commit()

    cursor.execute(
        """
        SELECT * FROM users
        WHERE email = ?
        AND password = ?
        """,
        (email, password)
    )

    user = cursor.fetchone()

    if user:

        return {
            "success": True,
            "user": {
                "email": email
            }
        }

    return {
        "success": False,
        "message": "Invalid credentials"
    }