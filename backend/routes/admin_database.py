"""
Database inspection routes for admins.
Allows viewing database schema and data directly.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import inspect, text
from typing import List, Dict, Any
from ..models import get_db, Faculty
from ..auth import require_admin

router = APIRouter(prefix="/api/admin/database", tags=["admin-database"])


@router.get("/tables")
def list_tables(
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    List all tables in the database.
    Requires admin authentication.
    """
    inspector = inspect(db.get_bind())
    tables = inspector.get_table_names()

    # Get row counts for each table
    table_info = []
    for table_name in tables:
        try:
            result = db.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
            count = result.scalar()
            table_info.append({
                "name": table_name,
                "row_count": count
            })
        except Exception as e:
            table_info.append({
                "name": table_name,
                "row_count": None,
                "error": str(e)
            })

    return {"tables": table_info}


@router.get("/tables/{table_name}/schema")
def get_table_schema(
    table_name: str,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Get the schema (columns and types) for a specific table.
    Requires admin authentication.
    """
    inspector = inspect(db.get_bind())

    # Check if table exists
    if table_name not in inspector.get_table_names():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table '{table_name}' not found"
        )

    # Get columns
    columns = inspector.get_columns(table_name)

    # Get primary keys
    pk_constraint = inspector.get_pk_constraint(table_name)
    primary_keys = pk_constraint.get('constrained_columns', [])

    # Get foreign keys
    foreign_keys = inspector.get_foreign_keys(table_name)

    # Get unique constraints
    unique_constraints = inspector.get_unique_constraints(table_name)

    # Format column information
    column_info = []
    for col in columns:
        column_info.append({
            "name": col['name'],
            "type": str(col['type']),
            "nullable": col['nullable'],
            "default": col.get('default'),
            "primary_key": col['name'] in primary_keys
        })

    return {
        "table_name": table_name,
        "columns": column_info,
        "primary_keys": primary_keys,
        "foreign_keys": foreign_keys,
        "unique_constraints": unique_constraints
    }


@router.get("/tables/{table_name}/data")
def get_table_data(
    table_name: str,
    limit: int = 100,
    offset: int = 0,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Get data from a specific table.
    Requires admin authentication.

    Args:
        table_name: Name of the table to query
        limit: Maximum number of rows to return (default 100, max 1000)
        offset: Number of rows to skip (for pagination)
    """
    inspector = inspect(db.get_bind())

    # Check if table exists
    if table_name not in inspector.get_table_names():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table '{table_name}' not found"
        )

    # Limit the limit to prevent excessive data retrieval
    limit = min(limit, 1000)

    # Get column names
    columns = inspector.get_columns(table_name)
    column_names = [col['name'] for col in columns]

    # Query data
    try:
        # Get total count
        count_result = db.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
        total_count = count_result.scalar()

        # Get data
        query = text(f"SELECT * FROM {table_name} LIMIT :limit OFFSET :offset")
        result = db.execute(query, {"limit": limit, "offset": offset})

        # Convert to list of dicts
        rows = []
        for row in result:
            row_dict = {}
            for i, col_name in enumerate(column_names):
                value = row[i]
                # Convert datetime to string for JSON serialization
                if hasattr(value, 'isoformat'):
                    value = value.isoformat()
                row_dict[col_name] = value
            rows.append(row_dict)

        return {
            "table_name": table_name,
            "columns": column_names,
            "rows": rows,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total_count
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error querying table: {str(e)}"
        )


@router.post("/query")
def execute_query(
    query_data: Dict[str, str],
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Execute a custom SQL query (SELECT only for safety).
    Requires admin authentication.
    """
    query_text = query_data.get("query", "").strip()

    if not query_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query cannot be empty"
        )

    # Only allow SELECT queries for safety
    if not query_text.upper().startswith("SELECT"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only SELECT queries are allowed for safety. Use specific endpoints for modifications."
        )

    try:
        result = db.execute(text(query_text))

        # Get column names
        column_names = list(result.keys())

        # Convert to list of dicts
        rows = []
        for row in result:
            row_dict = {}
            for i, col_name in enumerate(column_names):
                value = row[i]
                # Convert datetime to string for JSON serialization
                if hasattr(value, 'isoformat'):
                    value = value.isoformat()
                row_dict[col_name] = value
            rows.append(row_dict)

        return {
            "columns": column_names,
            "rows": rows,
            "row_count": len(rows)
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error executing query: {str(e)}"
        )


@router.get("/duplicates/faculty")
def find_duplicate_faculty(
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Find duplicate faculty members by ID or email.
    Requires admin authentication.
    """
    # Find duplicate IDs (case-insensitive)
    id_duplicates_query = text("""
        SELECT LOWER(id) as id_lower, COUNT(*) as count
        FROM faculty
        GROUP BY LOWER(id)
        HAVING COUNT(*) > 1
    """)
    id_duplicates = db.execute(id_duplicates_query).fetchall()

    # Find duplicate emails (case-insensitive, non-null)
    email_duplicates_query = text("""
        SELECT LOWER(email) as email_lower, COUNT(*) as count
        FROM faculty
        WHERE email IS NOT NULL AND email != ''
        GROUP BY LOWER(email)
        HAVING COUNT(*) > 1
    """)
    email_duplicates = db.execute(email_duplicates_query).fetchall()

    # Get details for duplicate IDs
    duplicate_id_details = []
    for dup in id_duplicates:
        faculty_query = text("""
            SELECT id, name, email, active, is_admin, registered
            FROM faculty
            WHERE LOWER(id) = :id_lower
        """)
        faculty_records = db.execute(faculty_query, {"id_lower": dup[0]}).fetchall()
        duplicate_id_details.append({
            "id_lower": dup[0],
            "count": dup[1],
            "records": [
                {
                    "id": rec[0],
                    "name": rec[1],
                    "email": rec[2],
                    "active": rec[3],
                    "is_admin": rec[4],
                    "registered": rec[5]
                }
                for rec in faculty_records
            ]
        })

    # Get details for duplicate emails
    duplicate_email_details = []
    for dup in email_duplicates:
        faculty_query = text("""
            SELECT id, name, email, active, is_admin, registered
            FROM faculty
            WHERE LOWER(email) = :email_lower
        """)
        faculty_records = db.execute(faculty_query, {"email_lower": dup[0]}).fetchall()
        duplicate_email_details.append({
            "email_lower": dup[0],
            "count": dup[1],
            "records": [
                {
                    "id": rec[0],
                    "name": rec[1],
                    "email": rec[2],
                    "active": rec[3],
                    "is_admin": rec[4],
                    "registered": rec[5]
                }
                for rec in faculty_records
            ]
        })

    return {
        "duplicate_ids": duplicate_id_details,
        "duplicate_emails": duplicate_email_details,
        "has_duplicates": len(duplicate_id_details) > 0 or len(duplicate_email_details) > 0
    }
