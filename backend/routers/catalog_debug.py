import json

from fastapi import APIRouter, HTTPException, Query

from cache.duckdb_store import db_store


router = APIRouter()
ALLOWED_TABLES = {"products", "skus", "providers"}


def _serialize_value(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    return value


@router.get("/catalog/tables")
async def list_catalog_tables():
    tables = []
    for table in sorted(ALLOWED_TABLES):
        count = db_store.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        tables.append({"name": table, "row_count": count})
    return {"tables": tables}


@router.get("/catalog/{table}/schema")
async def get_catalog_schema(table: str):
    if table not in ALLOWED_TABLES:
        raise HTTPException(status_code=404, detail="Unknown catalog table")

    rows = db_store.conn.execute(f"PRAGMA table_info('{table}')").fetchall()
    return {
        "table": table,
        "columns": [
            {
                "index": row[0],
                "name": row[1],
                "type": row[2],
                "not_null": row[3],
                "default": row[4],
                "primary_key": row[5],
            }
            for row in rows
        ],
    }


@router.get("/catalog/{table}/rows")
async def get_catalog_rows(
    table: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    if table not in ALLOWED_TABLES:
        raise HTTPException(status_code=404, detail="Unknown catalog table")

    cursor = db_store.conn.execute(
        f"SELECT * FROM {table} LIMIT ? OFFSET ?",
        (limit, offset),
    )
    columns = [column[0] for column in cursor.description]
    rows = [
        {column: _serialize_value(value) for column, value in zip(columns, row)}
        for row in cursor.fetchall()
    ]
    return {"table": table, "limit": limit, "offset": offset, "rows": rows}
