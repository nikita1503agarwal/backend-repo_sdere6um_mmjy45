"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Literal

# Core app schemas for Moviesque

class WatchlistItem(BaseModel):
    """
    Watchlist items for a user.
    Collection name: "watchlistitem"
    """
    user_id: str = Field(..., description="User identifier")
    tmdb_id: Optional[int] = Field(None, description="TMDb numeric ID if available")
    imdb_id: Optional[str] = Field(None, description="IMDB ID if available")
    title: str = Field(..., description="Movie or TV title")
    media_type: Literal["movie", "tv"] = Field("movie")
    year: Optional[int] = Field(None, description="Release year")
    poster: Optional[str] = Field(None, description="Poster URL")
    backdrop: Optional[str] = Field(None, description="Backdrop URL")
    rating: Optional[float] = Field(None, ge=0, le=10, description="User rating 0-10 scale")
    liked: bool = Field(False, description="User liked this title")
    status: Literal["later", "watching", "watched"] = Field("later", description="Watch status")

class RatingEntry(BaseModel):
    """
    User ratings timeline entries.
    Collection name: "ratingentry"
    """
    user_id: str
    tmdb_id: Optional[int] = None
    imdb_id: Optional[str] = None
    title: str
    media_type: Literal["movie", "tv"] = "movie"
    rating: float = Field(..., ge=0, le=10)
    review: Optional[str] = None

# Example schemas retained for reference (not used directly by the app but helpful for the DB viewer)
class User(BaseModel):
    name: str
    email: str
    is_active: bool = True

class Product(BaseModel):
    title: str
    description: Optional[str] = None
    price: float
    category: str
    in_stock: bool = True
