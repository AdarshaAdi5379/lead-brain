from __future__ import annotations

from src.settings import DB_PATH
from src.storage.db import connect, init_db


def main() -> None:
    connection = connect(DB_PATH)
    try:
        init_db(connection)
    finally:
        connection.close()


if __name__ == "__main__":
    main()

