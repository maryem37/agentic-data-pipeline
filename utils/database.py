
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv


# Load the project-root .env even when this module is imported directly.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def _database_config() -> dict[str, str | int]:
    """Build psycopg2 config from the existing .env database settings."""
    required = ("host", "port", "user", "password")
    missing = [name for name in required if not os.getenv(name)]
    database = os.getenv("database") or os.getenv("dbname")
    if not database:
        missing.append("database")
    if missing:
        raise RuntimeError(
            "Missing database settings in the project .env file: "
            + ", ".join(missing)
        )

    return {
        "host": os.environ["host"],
        "port": int(os.environ["port"]),
        "user": os.environ["user"],
        "password": os.environ["password"],
        "dbname": database,
    }


db_config = _database_config()


class DatabaseUtil:

    def __init__(self, db_config):
        self.db_config = db_config

        try:
            self.connection = psycopg2.connect(**db_config)

        except Exception as e:
            print(f"Error connecting to the database: {e}")
            self.connection = None

    def schema_details(self, schema_name):

        schema_info_context = f"Database Schema: {schema_name}\n"

        connection = self.connection

        if connection is None:
            return "Database connection failed."

        cursor = None

        try:
            cursor = connection.cursor()

            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s;
                """,
                (schema_name,)
            )

            tables_list = cursor.fetchall()

            for table in tables_list:

                table_name = table[0]

                schema_info_context += f"\nTable: {table_name}\n"

                # Adding Columns & Data Types
                cursor.execute(
                    """
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = %s
                    AND table_name = %s;
                    """,
                    (schema_name, table_name)
                )

                columns_list = cursor.fetchall()

                for column in columns_list:

                    column_name = column[0]
                    data_type = column[1]

                    schema_info_context += (
                        f"  Column: {column_name}, "
                        f"Data Type: {data_type}\n"
                    )

                # Adding Sample Data
                cursor.execute(
                    f'SELECT * FROM "{schema_name}"."{table_name}" LIMIT 5;'
                )

                sample_data = cursor.fetchall()

                schema_info_context += "  Sample Data:\n"

                for row in sample_data:
                    schema_info_context += f"    {row}\n"

        except Exception as e:

            print(f"Error fetching schema details: {e}")
            schema_info_context = f"Error fetching schema details: {e}"

        finally:

            if cursor:
                cursor.close()

            connection.close()

        return schema_info_context

    def execute_sql(self, query):

        connection = None
        cursor = None

        try:
            connection = psycopg2.connect(**self.db_config)
            cursor = connection.cursor()

            cursor.execute(query)

            if cursor.description is None:
                return "Error: Query did not return rows."

            result = cursor.fetchall()

            return str(result)

        except Exception as e:

            print(f"Error executing query: {e}")
            return f"SQL execution error: {e}"

        finally:

            if cursor:
                cursor.close()

            if connection:
                connection.close()


# Test database connection
if __name__ == "__main__":

    obj = DatabaseUtil(db_config)

    result = obj.schema_details("public")

    with open("test_schema_details.txt", "w", encoding="utf-8") as f:
        f.write(result)

    print(result)
