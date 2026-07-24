# Knowledge Base routes for faculty resources and documentation.
# Admin-managed articles with Markdown support.
# --------------------------------------------------------------

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import uuid

from ..models import SessionLocal, Faculty, KnowledgeBaseArticle
from ..auth import get_current_user

router = APIRouter(prefix="/api/knowledge-base", tags=["knowledge-base"])

# ===== Database dependency =====

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ===== Pydantic schemas =====

class ArticleListItem(BaseModel):
    id: str
    title: str
    description: str
    category: str
    division_key: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    author_name: str
    
    class Config:
        from_attributes = True


class ArticleFull(BaseModel):
    id: str
    title: str
    description: str
    content: str
    category: str
    division_key: Optional[str] = None
    is_published: bool
    display_order: int
    created_by: str
    created_at: datetime
    updated_at: datetime
    author_name: str
    
    class Config:
        from_attributes = True


class CreateArticleRequest(BaseModel):
    title: str
    description: str
    content: str
    category: str
    division_key: Optional[str] = None
    is_published: bool = True
    display_order: int = 0


class UpdateArticleRequest(BaseModel):
    title: Optional[str] = None
    division_key: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    is_published: Optional[bool] = None
    display_order: Optional[int] = None


# ===== Public Routes (All Users) =====

@router.get("/articles", response_model=List[ArticleListItem])
def get_articles(
    category: Optional[str] = None,
    search: Optional[str] = None,
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all published articles, optionally filtered by category or search term"""
    query = db.query(KnowledgeBaseArticle).filter(
        KnowledgeBaseArticle.is_published == True
    )

    # Non-admins see department-wide articles plus their division's own
    if not current_user.is_admin:
        query = query.filter(
            (KnowledgeBaseArticle.division_key.is_(None)) |
            (KnowledgeBaseArticle.division_key == current_user.division_key)
        )
    
    # Filter by category
    if category:
        query = query.filter(KnowledgeBaseArticle.category == category)
    
    # Search in title, description, and content
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (KnowledgeBaseArticle.title.ilike(search_term)) |
            (KnowledgeBaseArticle.description.ilike(search_term)) |
            (KnowledgeBaseArticle.content.ilike(search_term))
        )
    
    # Order by category, then display_order, then title
    articles = query.order_by(
        KnowledgeBaseArticle.category,
        KnowledgeBaseArticle.display_order,
        KnowledgeBaseArticle.title
    ).all()
    
    return [
        ArticleListItem(
            id=article.id,
            title=article.title,
            description=article.description,
            category=article.category,
            created_at=article.created_at,
            updated_at=article.updated_at,
            author_name=article.author.name,
            division_key=article.division_key
        )
        for article in articles
    ]


@router.get("/articles/{article_id}", response_model=ArticleFull)
def get_article(
    article_id: str,
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get full article content"""
    article = db.query(KnowledgeBaseArticle).filter(
        KnowledgeBaseArticle.id == article_id
    ).first()
    
    if not article:
        raise HTTPException(404, "Article not found")
    
    # Non-admins can only see published articles from their division (or department-wide)
    if not current_user.is_admin:
        if not article.is_published:
            raise HTTPException(404, "Article not found")
        if article.division_key and article.division_key != current_user.division_key:
            raise HTTPException(404, "Article not found")

    return ArticleFull(
        id=article.id,
        title=article.title,
        description=article.description,
        content=article.content,
        category=article.category,
        is_published=article.is_published,
        display_order=article.display_order,
        created_by=article.created_by,
        created_at=article.created_at,
        updated_at=article.updated_at,
        author_name=article.author.name,
        division_key=article.division_key
    )


@router.get("/categories")
def get_categories(
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get list of categories with article counts"""
    categories = ["Policies", "Procedures", "Clinical Guidelines", "IT Support"]
    
    result = []
    for category in categories:
        count = db.query(KnowledgeBaseArticle).filter(
            KnowledgeBaseArticle.category == category,
            KnowledgeBaseArticle.is_published == True
        ).count()
        
        result.append({
            "name": category,
            "count": count
        })
    
    return result


# ===== Admin Routes =====

@router.get("/admin/articles", response_model=List[ArticleFull])
def admin_get_all_articles(
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all articles including unpublished (admin only)"""
    if not current_user.is_admin:
        raise HTTPException(403, "Admin access required")
    
    articles = db.query(KnowledgeBaseArticle).order_by(
        KnowledgeBaseArticle.category,
        KnowledgeBaseArticle.display_order,
        KnowledgeBaseArticle.title
    ).all()
    
    return [
        ArticleFull(
            id=article.id,
            title=article.title,
            description=article.description,
            content=article.content,
            category=article.category,
            is_published=article.is_published,
            display_order=article.display_order,
            created_by=article.created_by,
            created_at=article.created_at,
            updated_at=article.updated_at,
            author_name=article.author.name,
            division_key=article.division_key
        )
        for article in articles
    ]


@router.post("/admin/articles")
def create_article(
    request: CreateArticleRequest,
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new article (admin only)"""
    if not current_user.is_admin:
        raise HTTPException(403, "Admin access required")
    
    # Validate category
    valid_categories = ["Policies", "Procedures", "Clinical Guidelines", "IT Support"]
    if request.category not in valid_categories:
        raise HTTPException(400, f"Invalid category. Must be one of: {', '.join(valid_categories)}")
    
    # Create article
    article = KnowledgeBaseArticle(
        id=str(uuid.uuid4()),
        title=request.title,
        description=request.description,
        content=request.content,
        category=request.category,
        is_published=request.is_published,
        display_order=request.display_order,
        division_key=request.division_key,
        created_by=current_user.id
    )
    
    db.add(article)
    db.commit()
    db.refresh(article)
    
    return {"status": "ok", "article_id": article.id}


@router.put("/admin/articles/{article_id}")
def update_article(
    article_id: str,
    request: UpdateArticleRequest,
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an article (admin only)"""
    if not current_user.is_admin:
        raise HTTPException(403, "Admin access required")
    
    article = db.query(KnowledgeBaseArticle).filter(
        KnowledgeBaseArticle.id == article_id
    ).first()
    
    if not article:
        raise HTTPException(404, "Article not found")
    
    # Update fields
    if request.title is not None:
        article.title = request.title
    if request.description is not None:
        article.description = request.description
    if request.content is not None:
        article.content = request.content
    if request.category is not None:
        valid_categories = ["Policies", "Procedures", "Clinical Guidelines", "IT Support"]
        if request.category not in valid_categories:
            raise HTTPException(400, f"Invalid category. Must be one of: {', '.join(valid_categories)}")
        article.category = request.category
    if request.is_published is not None:
        article.is_published = request.is_published
    if request.display_order is not None:
        article.display_order = request.display_order
    if request.division_key is not None:
        # empty string clears back to department-wide
        article.division_key = request.division_key or None

    article.updated_at = datetime.utcnow()
    
    db.commit()
    
    return {"status": "ok"}


@router.delete("/admin/articles/{article_id}")
def delete_article(
    article_id: str,
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete an article (admin only)"""
    if not current_user.is_admin:
        raise HTTPException(403, "Admin access required")
    
    article = db.query(KnowledgeBaseArticle).filter(
        KnowledgeBaseArticle.id == article_id
    ).first()
    
    if not article:
        raise HTTPException(404, "Article not found")
    
    db.delete(article)
    db.commit()
    
    return {"status": "ok"}
